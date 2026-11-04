#!/usr/bin/env bash
# Vizion Panel - non-KVM (software emulated QEMU/TCG) VPS manager.
#
# Creates real virtual machines on hosts that do not expose /dev/kvm. Each VPS is
# a qcow2 overlay on an Ubuntu cloud image, booted with cloud-init (root password
# + SSH) and reached through a host forwarded SSH port, so the panel can manage
# it exactly like an Incus instance.
#
# Actions:
#   create   --name N --alias ubuntu-22.04 --cpu 2 --ram-mb 2048 --disk-gb 20 --nesting on|off
#   start    --name N
#   stop     --name N
#   destroy  --name N
#   status   --name N
#   ip       --name N
#   nesting  --name N --state on|off       (persist for the next boot)
#   nesting  --name N --show
#
# Requirements: qemu-system-x86_64, qemu-img, cloud-localds (cloud-image-utils).
set -Eeuo pipefail

STATE_ROOT="${OMEGA_NONKVM_DIR:-/var/lib/omega-panel/nonkvm}"
IMAGE_ROOT="${OMEGA_NONKVM_IMAGE_DIR:-/var/lib/omega-panel/images}"
SSH_BIND="${OMEGA_NONKVM_SSH_BIND:-127.0.0.1}"
PORT_BASE="${OMEGA_NONKVM_PORT_BASE:-22000}"
ENV_BASE_IMAGE="${OMEGA_NONKVM_BASE_IMAGE:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
note() { echo "[nonkvm] $*" >&2; }

ACTION="${1:-}"
[[ -n "$ACTION" ]] || die "Missing action (create|start|stop|destroy|status|ip|nesting)"
shift

NAME=""; ALIAS="ubuntu-22.04"; CPU="2"; RAM_MB="2048"; DISK_GB="20"
NESTING="off"; BASE_IMAGE=""; SHOW_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="${2:-}"; shift 2 ;;
    --alias) ALIAS="${2:-}"; shift 2 ;;
    --cpu) CPU="${2:-}"; shift 2 ;;
    --ram-mb) RAM_MB="${2:-}"; shift 2 ;;
    --disk-gb) DISK_GB="${2:-}"; shift 2 ;;
    --nesting) NESTING="${2:-off}"; shift 2 ;;
    --base-image) BASE_IMAGE="${2:-}"; shift 2 ;;
    --state) NESTING="${2:-off}"; shift 2 ;;
    --show) SHOW_ONLY=1; shift ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$NAME" ]] || die "--name is required"
[[ "$NAME" =~ ^[a-z][a-z0-9-]{2,54}$ ]] || die "Invalid instance name: $NAME"
STATE_DIR="${STATE_ROOT}/${NAME}"
ENV_FILE="${STATE_DIR}/state.env"

need() { command -v "$1" >/dev/null 2>&1 || die "Missing '$1'. Install it and retry (apt-get install qemu-system-x86 qemu-utils cloud-image-utils)."; }

state_value() { # key default
  local key="$1" fallback="${2:-}"
  if [[ -f "$ENV_FILE" ]]; then
    local value
    value="$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
    [[ -n "$value" ]] && { echo "$value"; return; }
  fi
  echo "$fallback"
}

pid_alive() {
  local pidfile="${STATE_DIR}/qemu.pid"
  [[ -f "$pidfile" ]] || return 1
  local pid; pid="$(cat "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

free_port() {
  python3 - "$SSH_BIND" "$PORT_BASE" <<'PY'
import socket, sys
host, base = sys.argv[1], int(sys.argv[2])
for port in range(base, base + 2000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("no free port")
PY
}

base_image_path() {
  local alias="$1"
  [[ -n "$BASE_IMAGE" ]] && { echo "$BASE_IMAGE"; return; }
  [[ -n "$ENV_BASE_IMAGE" ]] && { echo "$ENV_BASE_IMAGE"; return; }
  local codename=""
  case "$alias" in
    ubuntu-22.04|22.04|ubuntu/22.04|jammy) codename="jammy" ;;
    ubuntu-24.04|24.04|ubuntu/24.04|noble) codename="noble" ;;
    *) return 1 ;;
  esac
  echo "${IMAGE_ROOT}/ubuntu-${codename}-cloudimg-amd64.qcow2"
}

ensure_base_image() {
  local alias="$1" path=""
  path="$(base_image_path "$alias")" || die "No cloud image mapping for '$alias'. Pass --base-image /path/to/cloud.qcow2 or set OMEGA_NONKVM_BASE_IMAGE."
  if [[ -s "$path" ]]; then
    note "Using base image ${path}"
    echo "$path"
    return
  fi
  local codename
  case "$alias" in
    ubuntu-22.04|22.04|ubuntu/22.04|jammy) codename="jammy" ;;
    ubuntu-24.04|24.04|ubuntu/24.04|noble) codename="noble" ;;
    *) die "Base image missing: ${path}" ;;
  esac
  need curl
  mkdir -p "$(dirname "$path")"
  local url="https://cloud-images.ubuntu.com/${codename}/current/${codename}-server-cloudimg-amd64.img"
  note "Downloading ${url}"
  curl -fL --retry 3 --retry-delay 2 -o "${path}.part" "$url"
  mv "${path}.part" "$path"
  echo "$path"
}

write_seed() {
  local password="$1"
  cat >"${STATE_DIR}/user-data" <<EOF
#cloud-config
hostname: ${NAME}
disable_root: false
ssh_pwauth: true
users:
  - name: root
    lock_passwd: false
    plain_text_passwd: "${password}"
chpasswd:
  expire: false
  users:
    - {name: root, password: "${password}", type: text}
package_update: false
package_upgrade: false
runcmd:
  - [ sh, -c, "sed -i 's/^#\\{0,1\\}PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config; systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true" ]
EOF
  cat >"${STATE_DIR}/meta-data" <<EOF
instance-id: iid-${NAME}
local-hostname: ${NAME}
EOF
  cloud-localds "${STATE_DIR}/seed.iso" "${STATE_DIR}/user-data" "${STATE_DIR}/meta-data"
}

qemu_boot() {
  local disk="${STATE_DIR}/disk.qcow2" seed="${STATE_DIR}/seed.iso"
  local port nesting cpu_model
  port="$(state_value PORT "")"
  nesting="$(state_value NESTING off)"
  [[ -n "$port" ]] || die "No SSH port recorded for ${NAME}"
  if [[ "$nesting" == "on" ]]; then cpu_model="max,+vmx,+svm"; else cpu_model="max"; fi

  local args=(
    -name "$NAME"
    -machine q35,accel=tcg
    -cpu "$cpu_model"
    -smp "$(state_value CPU 2)"
    -m "$(state_value RAM_MB 2048)M"
    -drive "file=${disk},if=virtio,format=qcow2,cache=writeback"
    -drive "file=${seed},if=virtio,format=raw,readonly=on"
    -device virtio-net-pci,netdev=net0
    -netdev "user,id=net0,hostfwd=tcp:${SSH_BIND}:${port}-:22"
    -display none
    -serial "file:${STATE_DIR}/console.log"
    -pidfile "${STATE_DIR}/qemu.pid"
    -daemonize
  )
  if ! qemu-system-x86_64 "${args[@]}" 2>"${STATE_DIR}/qemu.err"; then
    if [[ "$nesting" == "on" ]]; then
      note "Nested CPU features are unsupported by this QEMU; booting with plain TCG CPU instead."
      sed -i 's/^NESTING=.*/NESTING=off/' "$ENV_FILE" 2>/dev/null || true
      args[5]="max"
      qemu-system-x86_64 "${args[@]}" 2>"${STATE_DIR}/qemu.err" || { cat "${STATE_DIR}/qemu.err" >&2; die "QEMU failed to start"; }
    else
      cat "${STATE_DIR}/qemu.err" >&2
      die "QEMU failed to start"
    fi
  fi
}

do_create() {
  need qemu-system-x86_64; need qemu-img; need cloud-localds
  [[ -d "$STATE_DIR" && -f "${STATE_DIR}/disk.qcow2" ]] && die "Instance already exists: ${NAME}"
  mkdir -p "$STATE_DIR"
  chmod 0750 "$STATE_DIR"
  local base; base="$(ensure_base_image "$ALIAS")"
  local port password
  port="$(free_port)"
  password="$(python3 - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(20)))
PY
)"
  qemu-img create -q -f qcow2 -F qcow2 -b "$base" "${STATE_DIR}/disk.qcow2" "${DISK_GB}G"
  write_seed "$password"
  cat >"$ENV_FILE" <<EOF
NAME=${NAME}
ALIAS=${ALIAS}
CPU=${CPU}
RAM_MB=${RAM_MB}
DISK_GB=${DISK_GB}
NESTING=${NESTING}
PORT=${port}
SSH_USER=root
SSH_PASSWORD=${password}
CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
  chmod 0600 "$ENV_FILE"
  qemu_boot
  echo "OMEGA_INSTANCE=${NAME}"
  echo "OMEGA_VPS_TYPE=nonkvm"
  echo "OMEGA_SSH_HOST=${SSH_BIND}"
  echo "OMEGA_SSH_PORT=${port}"
  echo "OMEGA_SSH_USER=root"
  echo "OMEGA_SSH_PASSWORD=${password}"
  echo "OMEGA_STATE_DIR=${STATE_DIR}"
}

do_start() {
  need qemu-system-x86_64
  [[ -f "${STATE_DIR}/disk.qcow2" ]] || die "Instance does not exist: ${NAME}"
  if pid_alive; then echo "OMEGA_STATUS=running"; return; fi
  qemu_boot
  echo "OMEGA_STATUS=running"
}

do_stop() {
  if ! pid_alive; then echo "OMEGA_STATUS=stopped"; return; fi
  local pid; pid="$(cat "${STATE_DIR}/qemu.pid")"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "${STATE_DIR}/qemu.pid"
  echo "OMEGA_STATUS=stopped"
}

do_destroy() {
  do_stop >/dev/null 2>&1 || true
  rm -rf "$STATE_DIR"
  echo "OMEGA_STATUS=destroyed"
}

do_status() {
  [[ -f "${STATE_DIR}/disk.qcow2" ]] || die "Instance does not exist: ${NAME}"
  if pid_alive; then echo "OMEGA_STATUS=running"; else echo "OMEGA_STATUS=stopped"; fi
  echo "OMEGA_SSH_HOST=${SSH_BIND}"
  echo "OMEGA_SSH_PORT=$(state_value PORT "")"
}

do_ip() {
  [[ -f "${STATE_DIR}/disk.qcow2" ]] || die "Instance does not exist: ${NAME}"
  echo "${SSH_BIND}"
}

do_nesting() {
  [[ -f "$ENV_FILE" ]] || die "Instance does not exist: ${NAME}"
  if [[ "$SHOW_ONLY" -eq 1 ]]; then
    echo "nesting=$(state_value NESTING off)"
    exit 0
  fi
  case "$NESTING" in on|off) ;; *) die "--state must be on or off" ;; esac
  sed -i "s/^NESTING=.*/NESTING=${NESTING}/" "$ENV_FILE"
  echo "nesting=${NESTING}"
  echo "note=restart the VPS for the nested CPU flags to apply"
}

case "$ACTION" in
  create) do_create ;;
  start) do_start ;;
  stop) do_stop ;;
  destroy) do_destroy ;;
  status) do_status ;;
  ip) do_ip ;;
  nesting) do_nesting ;;
  *) die "Unknown action: $ACTION" ;;
esac
