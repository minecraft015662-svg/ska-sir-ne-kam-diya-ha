#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "[Omega V4] ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${OMEGA_INSTALL_DIR:-/opt/omega-panel}"
SERVICE_USER="${OMEGA_SERVICE_USER:-omega-panel}"
WITH_LXD=0
NONINTERACTIVE=0
NODE_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --with-lxd) WITH_LXD=1 ;;
    --noninteractive|-y) NONINTERACTIVE=1 ;;
    --node-only) NODE_ONLY=1 ;;
    --service-user=*) SERVICE_USER="${arg#*=}" ;;
    --help)
      cat <<EOF
Omega Panel V4 Stable installer

Usage: sudo bash setup.sh [--noninteractive] [--with-lxd] [--node-only]

Features:
  * Incus containers + Incus/QEMU virtual machines
  * KVM/libvirt/QEMU capability detection
  * Optional LXD snap compatibility install (only when safe)
  * Flask + Gunicorn panel, SQLite WAL, 24/7 systemd restart
  * Automatic guest OS update configuration
  * Configurable hostname, default: rgnodes-vps
EOF
      exit 0 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then echo "Run as root: sudo bash setup.sh"; exit 1; fi
if ! command -v systemctl >/dev/null 2>&1; then echo "systemd is required for the 24/7 service mode."; exit 1; fi

. /etc/os-release
ID_FAMILY="${ID_LIKE:-$ID}"
install_apt() { apt-get update; DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"; }
install_dnf() { dnf -y makecache; dnf -y install "$@"; }

if command -v apt-get >/dev/null 2>&1; then
  if [[ "${ID:-}" == "ubuntu" ]]; then install_apt software-properties-common; add-apt-repository -y universe >/dev/null 2>&1 || true; fi
  install_apt ca-certificates curl wget git jq python3 python3-venv python3-pip sudo openssl \
    cpu-checker qemu-kvm qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients \
    bridge-utils virtinst virt-manager
  systemctl enable --now libvirtd 2>/dev/null || systemctl enable --now virtqemud 2>/dev/null || true
elif command -v dnf >/dev/null 2>&1; then
  install_dnf ca-certificates curl wget git jq python3 python3-pip sudo openssl \
    qemu-kvm qemu-img libvirt libvirt-daemon-config-network libvirt-client bridge-utils virt-install
  systemctl enable --now libvirtd 2>/dev/null || true
else
  echo "Supported package managers: apt-get or dnf."; exit 1
fi

# KVM is a capability, not a promise: nested/unprivileged hosts can legitimately lack /dev/kvm.
if command -v kvm-ok >/dev/null 2>&1; then
  echo "[Omega V4] $(kvm-ok 2>&1 || true)"
fi

# Install/validate Incus without purging LXD/Incus packages. This avoids the V3 destructive conflict path.
if ! command -v incus >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    if ! DEBIAN_FRONTEND=noninteractive apt-get install -y incus; then
      install -d -m 0755 /etc/apt/keyrings
      curl -fsSL https://pkgs.zabbly.com/key.asc -o /etc/apt/keyrings/zabbly.asc
      CODENAME="${VERSION_CODENAME:-$(lsb_release -sc)}"
      printf 'deb [signed-by=/etc/apt/keyrings/zabbly.asc] https://pkgs.zabbly.com/incus/stable %s main\n' "$CODENAME" >/etc/apt/sources.list.d/incus.list
      apt-get update
      DEBIAN_FRONTEND=noninteractive apt-get install -y incus
    fi
  else
    echo "Incus package is not available from this distro package manager."; exit 1
  fi
fi

systemctl enable --now incus 2>/dev/null || systemctl enable --now incus.service 2>/dev/null || true
if command -v incus >/dev/null 2>&1; then
  if ! incus info >/dev/null 2>&1; then
    incus admin init --auto || incus admin init --minimal
  fi
  incus config set images.auto_update_cached true || true
  incus config set images.auto_update_interval 6 || true
fi

# Optional LXD compatibility. Never purge Incus/LXC packages to make this happen.
if [[ "$WITH_LXD" -eq 1 ]]; then
  if ! command -v snap >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then install_apt snapd; systemctl enable --now snapd.socket 2>/dev/null || true; sleep 2; fi
  if command -v lxd >/dev/null 2>&1; then
    echo "[Omega V4] LXD already present: $(lxd --version 2>/dev/null || true)"
  elif command -v snap >/dev/null 2>&1; then
    snap install lxd
    lxd init --auto || true
  else
    echo "[Omega V4] snap not found; LXD was not installed. Incus remains the supported primary backend."
  fi
fi

# Copy the clean release into a stable service path.
mkdir -p "$INSTALL_DIR"
if [[ "$APP_DIR" != "$INSTALL_DIR" ]]; then cp -a "$APP_DIR"/. "$INSTALL_DIR"/; fi

# Service account + directories.
id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/omega-panel --shell /usr/sbin/nologin "$SERVICE_USER"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 /var/lib/omega-panel /etc/omega-panel

# Give both the interactive operator and service account access where appropriate.
PRIMARY_USER="${SUDO_USER:-}"
for u in "$PRIMARY_USER" "$SERVICE_USER"; do
  [[ -n "$u" ]] || continue
  usermod -aG kvm "$u" 2>/dev/null || true
  usermod -aG libvirt "$u" 2>/dev/null || true
  usermod -aG lxd "$u" 2>/dev/null || true
  usermod -aG incus-admin "$u" 2>/dev/null || true
  usermod -aG incus "$u" 2>/dev/null || true
  usermod -aG incus-admin "$u" 2>/dev/null || true
done

# Incus native access for service user when possible.
if command -v incus >/dev/null 2>&1; then
  usermod -aG incus-admin "$SERVICE_USER" 2>/dev/null || true
  usermod -aG incus "$SERVICE_USER" 2>/dev/null || true
fi

# Python virtualenv. Use the distro Python rather than downloading old interpreters.
PYTHON_BIN="$(command -v python3)"
"$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip wheel >/dev/null
"$INSTALL_DIR/venv/bin/pip" install --no-cache-dir -r "$INSTALL_DIR/requirements.txt"

# Initialize database and first admin. Credentials are random unless explicitly supplied.
export PYTHONPATH="$INSTALL_DIR"
"$INSTALL_DIR/venv/bin/python" - <<'PY'
from app import db, bootstrap_admin
from core.config import node_token

db.init_db()
boot=bootstrap_admin()
db.ensure_local_node(node_token())
if boot:
    print(f"[Omega V4] First admin: {boot[0]}")
    print(f"[Omega V4] Random password: {boot[1]}")
    print(f"[Omega V4] Credentials file: {boot[2]}")
else:
    print('[Omega V4] Existing user database detected; no credentials changed.')
PY
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" /var/lib/omega-panel
chown "$SERVICE_USER:$SERVICE_USER" /etc/omega-panel/secret /etc/omega-panel/node-token 2>/dev/null || true
chmod 0640 /etc/omega-panel/secret /etc/omega-panel/node-token 2>/dev/null || true
chmod 0750 /var/lib/omega-panel
chmod 0640 /etc/omega-panel/secret /etc/omega-panel/node-token 2>/dev/null || true
chmod 0600 /var/lib/omega-panel/first_admin_credentials.txt 2>/dev/null || true
cat > /etc/omega-panel/omega.env <<ENV
OMEGA_HOSTNAME=${OMEGA_HOSTNAME:-rgnodes-vps}
OMEGA_BIND=${OMEGA_BIND:-0.0.0.0}
OMEGA_PORT=${OMEGA_PORT:-5000}
OMEGA_SECRET_FILE=/etc/omega-panel/secret
OMEGA_NODE_TOKEN_FILE=/etc/omega-panel/node-token
OMEGA_DATA_DIR=/var/lib/omega-panel
OMEGA_DB=/var/lib/omega-panel/omega.db
OMEGA_TIMEZONE=${OMEGA_TIMEZONE:-Asia/Dhaka}
ENV
chown root:$SERVICE_USER /etc/omega-panel/omega.env
chmod 0640 /etc/omega-panel/omega.env

# Install services and reload systemd.
install -m 0644 "$INSTALL_DIR/systemd/omega-panel.service" /etc/systemd/system/omega-panel.service
install -m 0644 "$INSTALL_DIR/systemd/omega-node.service" /etc/systemd/system/omega-node.service
install -m 0644 "$INSTALL_DIR/systemd/omega-jobs.service" /etc/systemd/system/omega-jobs.service
install -m 0644 "$INSTALL_DIR/systemd/omega-watchdog.service" /etc/systemd/system/omega-watchdog.service
install -m 0644 "$INSTALL_DIR/systemd/omega-watchdog.timer" /etc/systemd/system/omega-watchdog.timer
install -m 0644 "$INSTALL_DIR/systemd/omega-image-refresh.service" /etc/systemd/system/omega-image-refresh.service
install -m 0644 "$INSTALL_DIR/systemd/omega-image-refresh.timer" /etc/systemd/system/omega-image-refresh.timer
systemctl daemon-reload
systemctl enable --now omega-panel.service
systemctl enable --now omega-node.service
systemctl enable --now omega-jobs.service
systemctl enable --now omega-watchdog.timer
systemctl enable --now omega-image-refresh.timer

if [[ "$NODE_ONLY" -eq 0 ]]; then
  echo
  echo "=============================================="
  echo " Omega Panel V4 Stable - installed"
  echo " Hostname: ${OMEGA_HOSTNAME:-rgnodes-vps}"
  echo " Panel: http://127.0.0.1:${OMEGA_PORT:-5000}"
  echo " Install path: $INSTALL_DIR"
  echo " Primary backend: Incus (containers + QEMU VMs)"
  echo " KVM/libvirt/QEMU: capability detected above"
  echo " 24/7: systemd Restart=always + watchdog timer"
  echo "=============================================="
fi
