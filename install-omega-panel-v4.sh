#!/usr/bin/env bash
# Omega Panel V4 - RGNODES™ enhanced installer
# Primary author: MrZetrix
# Original project/reference credit: NafiGamer (nafigamer0)
#
# Installs the public Omega-Panel-V4 repository, checks/chooses safe ports,
# prepares the host, starts the existing setup.sh, verifies services, and
# provides a small terminal UI for install/update/repair/status/uninstall.

set -Eeuo pipefail

REPO_URL="${OMEGA_REPO_URL:-https://github.com/mrzetrixyt-525/Omega-Panel-V4.git}"
BRANCH="${OMEGA_BRANCH:-main}"
SOURCE_DIR="${OMEGA_SOURCE_DIR:-/opt/omega-panel-v4-source}"
INSTALL_DIR="${OMEGA_INSTALL_DIR:-/opt/omega-panel}"
ENV_FILE="/etc/omega-panel/omega.env"
PANEL_SERVICE="omega-panel.service"
NODE_SERVICE="omega-node.service"

PANEL_PORT_DEFAULT=5000
NODE_PORT_DEFAULT=5001
PORT_MIN=1024
PORT_MAX=65535

LOG_FILE="/var/log/omega-panel-installer.log"
BACKUP_ROOT="/var/backups/omega-panel"

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE" 2>/dev/null || true
exec > >(tee -a "$LOG_FILE") 2>&1

RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
CYAN="\033[36m"
BOLD="\033[1m"
RESET="\033[0m"

info()  { echo -e "${CYAN}➜${RESET} $*"; }
ok()    { echo -e "${GREEN}✔${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
fail()  { echo -e "${RED}✖${RESET} $*" >&2; }
die()   { fail "$*"; exit 1; }

trap 'fail "Installer failed at line $LINENO: $BASH_COMMAND"; exit 1' ERR

require_root() {
    [[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo bash install-omega-panel-v4.sh"
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

OS_ID=""
OS_CODENAME=""
detect_os() {
    [[ -r /etc/os-release ]] || die "/etc/os-release not found."
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_CODENAME="${VERSION_CODENAME:-}"
}

apt_install() {
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

dnf_install() {
    dnf -y install "$@"
}

install_base_deps() {
    info "Installing base installer dependencies..."
    if command_exists apt-get; then
        apt-get update -y
        apt_install ca-certificates curl git iproute2 procps sudo openssl
    elif command_exists dnf; then
        dnf -y makecache
        dnf_install ca-certificates curl git iproute procps-ng sudo openssl
    elif command_exists yum; then
        yum -y makecache
        yum -y install ca-certificates curl git iproute procps sudo openssl
    else
        die "Unsupported package manager. Supported: apt, dnf, yum."
    fi
    command_exists git || die "git installation failed."
    command_exists ss || warn "'ss' is unavailable; Python fallback will be used for port checks."
}

port_is_free() {
    local port="$1"
    if command_exists ss; then
        ! ss -H -ltn "( sport = :$port )" 2>/dev/null | grep -q .
    elif command_exists python3; then
        python3 - "$port" <<'PY'
import socket, sys
p = int(sys.argv[1])
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("0.0.0.0", p))
    ok = True
except OSError:
    ok = False
finally:
    s.close()
print("FREE" if ok else "BUSY")
raise SystemExit(0 if ok else 1)
PY
    else
        die "No supported port-check method (ss/python3)."
    fi
}

valid_port() {
    local p="$1"
    [[ "$p" =~ ^[0-9]+$ ]] && (( p >= PORT_MIN && p <= PORT_MAX ))
}

next_free_port() {
    local start="$1"
    local p="$start"
    while (( p <= PORT_MAX )); do
        if port_is_free "$p"; then
            echo "$p"
            return 0
        fi
        ((p++))
    done
    return 1
}

choose_ports() {
    local old_panel="" old_node=""
    if [[ -r "$ENV_FILE" ]]; then
        old_panel="$(awk -F= '$1=="OMEGA_PORT"{print $2}' "$ENV_FILE" | tail -n1 || true)"
        old_node="$(awk -F= '$1=="OMEGA_NODE_PORT"{print $2}' "$ENV_FILE" | tail -n1 || true)"
    fi

    if valid_port "${old_panel:-}"; then
        PANEL_PORT="$old_panel"
    else
        PANEL_PORT="$(next_free_port "$PANEL_PORT_DEFAULT")" || die "No free panel port found."
    fi

    if valid_port "${old_node:-}" && [[ "$old_node" != "$PANEL_PORT" ]] && port_is_free "$old_node"; then
        NODE_PORT="$old_node"
    else
        NODE_PORT="$(next_free_port "$NODE_PORT_DEFAULT")" || die "No free node port found."
        while [[ "$NODE_PORT" == "$PANEL_PORT" ]]; do
            NODE_PORT="$(next_free_port "$((NODE_PORT + 1))")" || die "No free node port found."
        done
    fi

    info "Panel port selected: ${BOLD}${PANEL_PORT}${RESET}"
    info "Node port selected:  ${BOLD}${NODE_PORT}${RESET}"
}

prompt_settings() {
    if [[ "${NONINTERACTIVE:-0}" -eq 1 ]]; then
        return
    fi

    local answer
    read -r -p "Panel port [${PANEL_PORT}] (Enter=auto/current): " answer || true
    if [[ -n "$answer" ]]; then
        valid_port "$answer" || die "Invalid panel port: $answer"
        if [[ "$answer" != "$PANEL_PORT" ]] && ! port_is_free "$answer"; then
            die "Panel port $answer is already in use."
        fi
        PANEL_PORT="$answer"
    fi

    while [[ "$NODE_PORT" == "$PANEL_PORT" ]]; do
        NODE_PORT="$(next_free_port "$((NODE_PORT + 1))")" || die "No free node port found."
    done

    read -r -p "Node port [${NODE_PORT}] (Enter=auto/current): " answer || true
    if [[ -n "$answer" ]]; then
        valid_port "$answer" || die "Invalid node port: $answer"
        [[ "$answer" != "$PANEL_PORT" ]] || die "Node port cannot equal panel port."
        if [[ "$answer" != "$NODE_PORT" ]] && ! port_is_free "$answer"; then
            die "Node port $answer is already in use."
        fi
        NODE_PORT="$answer"
    fi

    read -r -p "Hostname [rgnodes-vps]: " OMEGA_HOSTNAME || true
    OMEGA_HOSTNAME="${OMEGA_HOSTNAME:-rgnodes-vps}"
}

set_defaults_noninteractive() {
    OMEGA_HOSTNAME="${OMEGA_HOSTNAME:-rgnodes-vps}"
    PANEL_PORT="${OMEGA_PORT:-$PANEL_PORT}"
    NODE_PORT="${OMEGA_NODE_PORT:-$NODE_PORT}"
    valid_port "$PANEL_PORT" || die "Invalid OMEGA_PORT: $PANEL_PORT"
    valid_port "$NODE_PORT" || die "Invalid OMEGA_NODE_PORT: $NODE_PORT"
    [[ "$PANEL_PORT" != "$NODE_PORT" ]] || die "Panel and node ports must differ."
    if ! port_is_free "$PANEL_PORT" && [[ ! -f "$ENV_FILE" ]]; then
        die "Requested panel port $PANEL_PORT is already in use."
    fi
}

clone_or_update() {
    info "Fetching ${REPO_URL} (${BRANCH})..."
    if [[ -d "$SOURCE_DIR/.git" ]]; then
        git -C "$SOURCE_DIR" fetch --depth=1 origin "$BRANCH"
        git -C "$SOURCE_DIR" reset --hard "origin/$BRANCH"
        git -C "$SOURCE_DIR" clean -fd
    else
        rm -rf "$SOURCE_DIR"
        mkdir -p "$(dirname "$SOURCE_DIR")"
        git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$SOURCE_DIR"
    fi

    [[ -f "$SOURCE_DIR/setup.sh" ]] || die "Repository does not contain setup.sh."
    [[ -f "$SOURCE_DIR/requirements.txt" ]] || die "Repository does not contain requirements.txt."
    chmod +x "$SOURCE_DIR/setup.sh"
    ok "Source is ready."
}

patch_service_ports() {
    # Current V4 service files use literal 5000/5001 in ExecStart while config.py
    # already supports OMEGA_PORT/OMEGA_NODE_PORT. Replace only those literals.
    local panel_unit="$SOURCE_DIR/systemd/omega-panel.service"
    local node_unit="$SOURCE_DIR/systemd/omega-node.service"

    [[ -f "$panel_unit" ]] || die "Missing $panel_unit"
    [[ -f "$node_unit" ]] || die "Missing $node_unit"

    sed -i -E \
        "s#(--bind[[:space:]]+0\\.0\\.0\\.0:)[0-9]+#\\1${PANEL_PORT}#g" \
        "$panel_unit"

    sed -i -E \
        "s#(--bind[[:space:]]+127\\.0\\.0\\.1:)[0-9]+#\\1${NODE_PORT}#g" \
        "$node_unit"

    # Keep the configured environment aligned with the service units.
    export OMEGA_PORT="$PANEL_PORT"
    export OMEGA_NODE_PORT="$NODE_PORT"
    export OMEGA_HOSTNAME

    grep -Eq -- "--bind[[:space:]]+0\.0\.0\.0:${PANEL_PORT}" "$panel_unit" \
        || die "Failed to patch panel service port."
    grep -Eq -- "--bind[[:space:]]+127\.0\.0\.1:${NODE_PORT}" "$node_unit" \
        || die "Failed to patch node service port."

    ok "Service ports patched: panel=${PANEL_PORT}, node=${NODE_PORT}"
}

backup_existing() {
    [[ -d "$INSTALL_DIR" ]] || return 0
    mkdir -p "$BACKUP_ROOT"
    local stamp backup
    stamp="$(date +%Y%m%d-%H%M%S)"
    backup="$BACKUP_ROOT/omega-panel-$stamp"
    info "Backing up existing installation to $backup"
    cp -a "$INSTALL_DIR" "$backup"
    [[ -d /var/lib/omega-panel ]] && cp -a /var/lib/omega-panel "$BACKUP_ROOT/data-$stamp" || true
    ok "Backup created."
}

run_setup() {
    info "Running the official V4 setup.sh with selected settings..."
    export OMEGA_PORT="$PANEL_PORT"
    export OMEGA_NODE_PORT="$NODE_PORT"
    export OMEGA_HOSTNAME
    export OMEGA_TIMEZONE="${OMEGA_TIMEZONE:-Asia/Dhaka}"

    bash "$SOURCE_DIR/setup.sh" --noninteractive
}

configure_firewall() {
    if command_exists ufw && ufw status 2>/dev/null | grep -qi "active"; then
        ufw allow "${PANEL_PORT}/tcp" >/dev/null || true
        ok "UFW rule checked for panel port ${PANEL_PORT}/tcp."
    elif command_exists firewall-cmd && firewall-cmd --state 2>/dev/null | grep -q running; then
        firewall-cmd --permanent --add-port="${PANEL_PORT}/tcp" >/dev/null || true
        firewall-cmd --reload >/dev/null || true
        ok "firewalld rule checked for panel port ${PANEL_PORT}/tcp."
    else
        info "No active UFW/firewalld detected; firewall was not modified."
    fi
}

verify_services() {
    info "Verifying systemd services..."
    local s
    for s in omega-panel.service omega-node.service omega-jobs.service; do
        if systemctl is-active --quiet "$s"; then
            ok "$s is active."
        else
            fail "$s is not active."
            systemctl --no-pager --full status "$s" || true
            return 1
        fi
    done

    systemctl is-enabled --quiet omega-panel.service || warn "omega-panel.service is not enabled."
    systemctl is-enabled --quiet omega-node.service || warn "omega-node.service is not enabled."
    systemctl is-enabled --quiet omega-jobs.service || warn "omega-jobs.service is not enabled."
    systemctl is-enabled --quiet omega-watchdog.timer || warn "omega-watchdog.timer is not enabled."
}

health_check() {
    info "Checking panel HTTP health..."
    local url="http://127.0.0.1:${PANEL_PORT}/healthz"
    local i code=""
    for i in {1..20}; do
        if command_exists curl; then
            code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "$url" || true)"
            if [[ "$code" == "200" ]]; then
                ok "Panel health: HTTP 200"
                return 0
            fi
        fi
        sleep 1
    done
    warn "Health endpoint did not return HTTP 200 at $url."
    return 1
}

show_status() {
    echo
    echo -e "${BOLD}${BLUE}Omega Panel V4 — RGNODES™ Status${RESET}"
    echo "------------------------------------------------------------"
    if [[ -r "$ENV_FILE" ]]; then
        grep -E '^(OMEGA_HOSTNAME|OMEGA_PORT|OMEGA_NODE_PORT|OMEGA_TIMEZONE)=' "$ENV_FILE" || true
    fi
    echo
    for s in omega-panel.service omega-node.service omega-jobs.service omega-watchdog.timer omega-image-refresh.timer; do
        printf "%-32s : " "$s"
        systemctl is-active "$s" 2>/dev/null || true
    done
    echo
    if [[ -r "$ENV_FILE" ]]; then
        local p n
        p="$(awk -F= '$1=="OMEGA_PORT"{print $2}' "$ENV_FILE" | tail -n1 || true)"
        n="$(awk -F= '$1=="OMEGA_NODE_PORT"{print $2}' "$ENV_FILE" | tail -n1 || true)"
        [[ -n "$p" ]] && echo "Panel URL : http://$(hostname -I 2>/dev/null | awk '{print $1}'):${p}"
        [[ -n "$n" ]] && echo "Node bind : 127.0.0.1:${n}"
    fi
    echo "------------------------------------------------------------"
}

install_or_update() {
    require_root
    detect_os
    install_base_deps

    if [[ ! -r /etc/systemd/system/omega-panel.service ]] && [[ -d "$INSTALL_DIR" ]]; then
        warn "Install directory exists without installed panel service; treating as repair."
    else
        backup_existing
    fi

    choose_ports
    set_defaults_noninteractive
    prompt_settings

    if ! port_is_free "$PANEL_PORT" && [[ ! -f /etc/systemd/system/omega-panel.service ]]; then
        die "Panel port ${PANEL_PORT} is busy."
    fi
    if ! port_is_free "$NODE_PORT" && [[ ! -f /etc/systemd/system/omega-node.service ]]; then
        die "Node port ${NODE_PORT} is busy."
    fi

    clone_or_update
    patch_service_ports
    run_setup
    configure_firewall

    # setup.sh installs its own systemd units; verify they exist before continuing.
    [[ -f "/etc/systemd/system/${PANEL_SERVICE}" ]] || die "Panel systemd unit was not installed."
    [[ -f "/etc/systemd/system/${NODE_SERVICE}" ]] || die "Node systemd unit was not installed."

    systemctl daemon-reload
    systemctl restart "$PANEL_SERVICE" "$NODE_SERVICE"
    systemctl restart omega-jobs.service
    systemctl restart omega-watchdog.timer 2>/dev/null || true

    verify_services
    health_check || warn "Service is running but health endpoint is not yet responding."

    # Re-check actual listeners after restart.
    if ! port_is_free "$PANEL_PORT"; then
        ok "Panel is listening on TCP ${PANEL_PORT}."
    else
        warn "Nothing is listening on TCP ${PANEL_PORT}."
    fi

    echo
    ok "Omega Panel V4 installation/update completed."
    echo "Panel: http://<SERVER-IP>:${PANEL_PORT}"
    echo "Node: 127.0.0.1:${NODE_PORT}"
    echo "Hostname: ${OMEGA_HOSTNAME}"
    echo "Installer log: ${LOG_FILE}"
}

repair_install() {
    require_root
    detect_os
    install_base_deps
    [[ -d "$SOURCE_DIR" ]] || clone_or_update
    [[ -f "$SOURCE_DIR/setup.sh" ]] || clone_or_update
    choose_ports
    set_defaults_noninteractive
    patch_service_ports
    run_setup
    systemctl daemon-reload
    systemctl restart omega-panel.service omega-node.service omega-jobs.service
    systemctl restart omega-watchdog.timer 2>/dev/null || true
    verify_services
    health_check || true
    ok "Repair completed."
}

uninstall_panel() {
    require_root
    echo
    warn "This removes Omega Panel services and application files."
    warn "Database backups under ${BACKUP_ROOT} are preserved when available."
    local ans=""
    if [[ "${NONINTERACTIVE:-0}" -ne 1 ]]; then
        read -r -p "Type REMOVE to continue: " ans || true
        [[ "$ans" == "REMOVE" ]] || { info "Cancelled."; return 0; }
    fi

    mkdir -p "$BACKUP_ROOT"
    [[ -d "$INSTALL_DIR" ]] && cp -a "$INSTALL_DIR" "$BACKUP_ROOT/uninstall-$(date +%Y%m%d-%H%M%S)" || true
    [[ -d /var/lib/omega-panel ]] && cp -a /var/lib/omega-panel "$BACKUP_ROOT/data-uninstall-$(date +%Y%m%d-%H%M%S)" || true

    systemctl disable --now \
        omega-image-refresh.timer omega-watchdog.timer \
        omega-image-refresh.service omega-watchdog.service \
        omega-jobs.service omega-node.service omega-panel.service 2>/dev/null || true

    rm -f /etc/systemd/system/omega-panel.service \
          /etc/systemd/system/omega-node.service \
          /etc/systemd/system/omega-jobs.service \
          /etc/systemd/system/omega-watchdog.service \
          /etc/systemd/system/omega-watchdog.timer \
          /etc/systemd/system/omega-image-refresh.service \
          /etc/systemd/system/omega-image-refresh.timer
    systemctl daemon-reload

    rm -rf "$INSTALL_DIR" "$SOURCE_DIR"
    ok "Panel services and files removed. Host virtualization packages were intentionally not removed."
}

menu() {
    clear || true
    echo -e "${BOLD}${CYAN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║              OMEGA PANEL V4 • RGNODES™                   ║"
    echo "║                 Stable Installer UI                      ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo " Author  : MrZetrix"
    echo " Credit  : NafiGamer (original/reference project)"
    echo " Backend : Incus containers + QEMU/KVM VMs"
    echo
    echo " 1) Install / Update"
    echo " 2) Repair"
    echo " 3) Status"
    echo " 4) Uninstall"
    echo " 5) Exit"
    echo
    read -r -p "Select [1-5]: " choice
    case "$choice" in
        1) install_or_update ;;
        2) repair_install ;;
        3) require_root; show_status ;;
        4) uninstall_panel ;;
        5) exit 0 ;;
        *) die "Invalid selection." ;;
    esac
}

NONINTERACTIVE=0
ACTION="menu"
for arg in "$@"; do
    case "$arg" in
        --install|--update) ACTION="install"; NONINTERACTIVE=1 ;;
        --repair) ACTION="repair"; NONINTERACTIVE=1 ;;
        --status) ACTION="status"; NONINTERACTIVE=1 ;;
        --uninstall) ACTION="uninstall"; NONINTERACTIVE=1 ;;
        --noninteractive|-y) NONINTERACTIVE=1 ;;
        --port=*) OMEGA_PORT="${arg#*=}" ;;
        --node-port=*) OMEGA_NODE_PORT="${arg#*=}" ;;
        --hostname=*) OMEGA_HOSTNAME="${arg#*=}" ;;
        --branch=*) BRANCH="${arg#*=}" ;;
        --help|-h)
            cat <<EOF
Omega Panel V4 • RGNODES™ installer

Usage:
  sudo bash install-omega-panel-v4.sh
  sudo bash install-omega-panel-v4.sh --install --port=8080 --node-port=8081
  sudo bash install-omega-panel-v4.sh --repair
  sudo bash install-omega-panel-v4.sh --status
  sudo bash install-omega-panel-v4.sh --uninstall

Defaults:
  Repository : ${REPO_URL}
  Branch     : ${BRANCH}
  Hostname   : rgnodes-vps
  Panel port : auto/current, normally 5000
  Node port  : auto/current, normally 5001

Notes:
  • The script does not remove Incus/LXD/libvirt packages during uninstall.
  • It checks ports before systemd starts.
  • It patches the current V4 service-unit literal ports to the selected values.
  • Existing data is backed up before update/repair when possible.
EOF
            exit 0 ;;
        *) die "Unknown argument: $arg" ;;
    esac
done

case "$ACTION" in
    menu) menu ;;
    install) install_or_update ;;
    repair) repair_install ;;
    status) require_root; show_status ;;
    uninstall) uninstall_panel ;;
esac
