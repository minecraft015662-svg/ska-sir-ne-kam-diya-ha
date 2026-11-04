#!/usr/bin/env bash
# Vizion Panel - install (or check) the node agent on this host.
#
#   sudo bash scripts/omega-node-install.sh --type=lxc     # LXC containers only (light)
#   sudo bash scripts/omega-node-install.sh --type=kvm     # + QEMU/KVM virtual machines (needs /dev/kvm)
#   sudo bash scripts/omega-node-install.sh --type=incus   # everything: LXC + KVM + non-KVM (default)
#   sudo bash scripts/omega-node-install.sh --check        # status only, no root needed
#
# The agent is what the panel talks to over HTTP (port 5001) to create and manage
# containers/VMs on a node. Running this on the panel host is harmless: it reuses
# the existing install directory, virtualenv and systemd unit.
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${OMEGA_INSTALL_DIR:-/opt/omega-panel}"
SERVICE_USER="${OMEGA_SERVICE_USER:-omega-panel}"
NODE_PORT="${OMEGA_NODE_PORT:-5001}"
NODE_BIND="${OMEGA_NODE_BIND:-127.0.0.1}"
UNIT="omega-node.service"
MODE="install"
TYPE_FILE="/etc/omega-panel/node-type"
NODE_TYPE="${OMEGA_NODE_TYPE:-}"

for arg in "$@"; do
  case "$arg" in
    --check|--status) MODE="check" ;;
    --bind=*) NODE_BIND="${arg#*=}" ;;
    --type=*) NODE_TYPE="${arg#*=}" ;;
    --help)
      cat <<EOF
Vizion node agent installer

Usage: sudo bash scripts/omega-node-install.sh [--type=lxc|kvm|incus] [--bind=ADDR] [--check]

  --type=lxc    Incus system containers only (no QEMU needed)
  --type=kvm    Incus containers + QEMU/KVM virtual machines (requires /dev/kvm)
  --type=incus  everything: containers, KVM VMs and non-KVM (QEMU TCG) VMs  [default]
  --check       print agent service and health status, install nothing

Environment:
  OMEGA_INSTALL_DIR   install path (default /opt/omega-panel)
  --bind=ADDR       listen address (default 127.0.0.1; use 0.0.0.0 for a remote panel)
  OMEGA_NODE_PORT     agent port (default 5001)
EOF
      exit 0 ;;
  esac
done

if [[ "$MODE" == "check" ]]; then
  state="$(systemctl is-active "$UNIT" 2>/dev/null || true)"
  echo "NODE_SERVICE=${state:-unknown}"
  if command -v curl >/dev/null 2>&1; then
    health="$(curl -fsS --max-time 4 "http://127.0.0.1:${NODE_PORT}/api/health" 2>/dev/null || true)"
    if [[ -n "$health" ]]; then echo "NODE_HEALTH=${health}"; else echo "NODE_HEALTH=unreachable"; fi
  fi
  if [[ -s /etc/omega-panel/node-token ]]; then echo "NODE_TOKEN=present"; else echo "NODE_TOKEN=missing"; fi
  echo "NODE_TYPE=$(cat "$TYPE_FILE" 2>/dev/null || echo unknown)"
  if [[ -S /var/lib/incus/unix.socket ]]; then echo "INCUS_SOCKET=present"; else echo "INCUS_SOCKET=missing"; fi
  if [[ -e /dev/kvm ]]; then echo "KVM_DEVICE=present"; else echo "KVM_DEVICE=missing"; fi
  if [[ -f "/etc/systemd/system/${UNIT}" ]]; then
    echo "NODE_BIND=$(grep -oE -- '--bind [^ ]+' "/etc/systemd/system/${UNIT}" | awk '{print $2}' | cut -d: -f1)"
  fi
  exit 0
fi

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo bash scripts/omega-node-install.sh"
command -v systemctl >/dev/null 2>&1 || die "systemd is required"

[[ -n "$NODE_TYPE" ]] || NODE_TYPE="$(cat "$TYPE_FILE" 2>/dev/null || echo incus)"
case "$NODE_TYPE" in lxc|kvm|incus) ;; *) die "--type must be lxc, kvm or incus (got: $NODE_TYPE)" ;; esac
echo "[node-install] node type: $NODE_TYPE"

# ---- host virtualisation stack, chosen by node type -----------------------
. /etc/os-release
apt_install() { apt-get update -y >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"; }
install_incus() {
  command -v incus >/dev/null 2>&1 && return 0
  command -v apt-get >/dev/null 2>&1 || die "Incus auto-install needs a Debian/Ubuntu node (apt). Install Incus manually, then re-run."
  if ! apt_install incus; then
    install -d -m 0755 /etc/apt/keyrings
    curl -fsSL https://pkgs.zabbly.com/key.asc -o /etc/apt/keyrings/zabbly.asc
    printf 'deb [signed-by=/etc/apt/keyrings/zabbly.asc] https://pkgs.zabbly.com/incus/stable %s main\n' \
      "${VERSION_CODENAME:-$(lsb_release -sc)}" > /etc/apt/sources.list.d/incus.list
    apt_install incus
  fi
}
command -v apt-get >/dev/null 2>&1 || die "This installer supports apt based nodes (Debian/Ubuntu)."
apt_install ca-certificates curl openssl python3 python3-venv python3-pip socat iproute2 >/dev/null
case "$NODE_TYPE" in
  kvm|incus)
    apt_install cpu-checker qemu-kvm qemu-system-x86 qemu-utils cloud-image-utils libvirt-daemon-system libvirt-clients >/dev/null
    systemctl enable --now libvirtd >/dev/null 2>&1 || systemctl enable --now virtqemud >/dev/null 2>&1 || true ;;
esac
install_incus
systemctl enable --now incus >/dev/null 2>&1 || systemctl enable --now incus.service >/dev/null 2>&1 || true
sleep 2
if ! incus storage show default >/dev/null 2>&1; then
  incus admin init --auto >/dev/null 2>&1 || incus admin init --minimal >/dev/null 2>&1 || true
fi
incus info >/dev/null 2>&1 || die "Incus is installed but not answering. Check: systemctl status incus"
echo "[node-install] Incus ready: $(incus --version 2>/dev/null)"
if [[ "$NODE_TYPE" == "kvm" && ! -e /dev/kvm ]]; then
  if [[ "${OMEGA_ALLOW_NO_KVM:-0}" != "1" ]]; then
    die "/dev/kvm is missing: this VPS has no hardware virtualisation (nested virt is off). KVM VMs cannot run here. Use --type=lxc, or enable nested virtualisation at your provider."
  fi
fi
[[ -e /dev/kvm ]] && echo "[node-install] /dev/kvm present - KVM virtual machines available"

echo "[node-install] install directory: $INSTALL_DIR"
id "$SERVICE_USER" >/dev/null 2>&1 || \
  useradd --system --create-home --home-dir /var/lib/omega-panel --shell /usr/sbin/nologin "$SERVICE_USER"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 /var/lib/omega-panel /etc/omega-panel "$INSTALL_DIR"
# The agent runs as $SERVICE_USER and talks to the Incus socket / /dev/kvm.
for grp in incus-admin incus kvm libvirt; do usermod -aG "$grp" "$SERVICE_USER" 2>/dev/null || true; done
printf '%s\n' "$NODE_TYPE" > "$TYPE_FILE"; chmod 0644 "$TYPE_FILE"

if [[ "$(readlink -f "$APP_DIR")" != "$(readlink -f "$INSTALL_DIR")" ]]; then
  cp -a "$APP_DIR/node.py" "$APP_DIR/node_requirements.txt" "$INSTALL_DIR/"
  rm -rf "$INSTALL_DIR/core"
  cp -a "$APP_DIR/core" "$INSTALL_DIR/core"
  install -d "$INSTALL_DIR/scripts" "$INSTALL_DIR/systemd"
  cp -a "$APP_DIR/scripts/." "$INSTALL_DIR/scripts/"
  cp -a "$APP_DIR/systemd/omega-node.service" "$INSTALL_DIR/systemd/omega-node.service"
fi

PYTHON_BIN="$(command -v python3)" || die "python3 is required"
if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"
  "$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip wheel >/dev/null
fi
"$INSTALL_DIR/venv/bin/pip" install --no-cache-dir -r "$INSTALL_DIR/node_requirements.txt" >/dev/null
echo "[node-install] python dependencies ready"

if [[ ! -s /etc/omega-panel/node-token ]]; then
  umask 077
  openssl rand -hex 32 > /etc/omega-panel/node-token
  echo "[node-install] generated a new node token"
fi
chown root:"$SERVICE_USER" /etc/omega-panel/node-token 2>/dev/null || true
chmod 0640 /etc/omega-panel/node-token

install -m 0644 "$INSTALL_DIR/systemd/omega-node.service" "/etc/systemd/system/${UNIT}"
# A node on another VPS must listen beyond loopback for the panel to reach it.
if [[ "$NODE_BIND" != "127.0.0.1" ]]; then
  sed -i -E "s#--bind [0-9.]+:[0-9]+#--bind ${NODE_BIND}:${NODE_PORT}#g" "/etc/systemd/system/${UNIT}"
fi
systemctl daemon-reload
systemctl enable "$UNIT" >/dev/null 2>&1 || true
systemctl restart "$UNIT"
echo "[node-install] waiting for the agent to answer on port ${NODE_PORT}"
status="unknown"
for _ in $(seq 1 20); do
  sleep 1
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 3 "http://127.0.0.1:${NODE_PORT}/api/health" >/dev/null 2>&1; then
    status="healthy"; break
  fi
  status="$(systemctl is-active "$UNIT" 2>/dev/null || true)"
done

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" >/dev/null 2>&1 || true
echo "NODE_SERVICE=$(systemctl is-active "$UNIT" 2>/dev/null || echo unknown)"
echo "NODE_HEALTH=${status}"
echo "NODE_TYPE=${NODE_TYPE}"
echo "NODE_PORT=${NODE_PORT}"
echo "NODE_BIND=${NODE_BIND}"
echo "NODE_TOKEN_FILE=/etc/omega-panel/node-token"
if [[ "$NODE_BIND" != "127.0.0.1" ]]; then
  echo "NODE_FIREWALL=allow ${NODE_PORT}/tcp only from the panel IP (ufw allow from PANEL_IP to any port ${NODE_PORT} proto tcp)"
fi
[[ "$status" == "healthy" ]] || {
  echo "The agent did not become healthy. Inspect: journalctl -u ${UNIT} -n 50 --no-pager" >&2
  exit 1
}
echo "[node-install] done"
