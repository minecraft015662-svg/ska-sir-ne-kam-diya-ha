#!/usr/bin/env bash
# Vizion Panel - TCP port forwarding with socat + systemd.
#
#   sudo bash scripts/omega-portforward.sh add --listen 8080 --to 10.0.0.5:80
#   sudo bash scripts/omega-portforward.sh list
#   sudo bash scripts/omega-portforward.sh remove --listen 8080
#   sudo bash scripts/omega-portforward.sh --interactive
#
# Each forward becomes omega-forward-<listen>.service, restarts automatically
# and survives reboots.
set -Eeuo pipefail

ACTION="${1:---help}"
[[ $# -gt 0 ]] && shift

LISTEN=""
TARGET=""
NAME=""

die() { echo "ERROR: $*" >&2; exit 1; }
say() { printf '> %s\n' "$*"; }

usage() {
    cat <<EOF
Vizion port forwarding (socat)

Usage:
  sudo bash scripts/omega-portforward.sh add --listen 8080 --to 10.0.0.5:80
  sudo bash scripts/omega-portforward.sh list
  sudo bash scripts/omega-portforward.sh remove --listen 8080
  sudo bash scripts/omega-portforward.sh --interactive

  --listen PORT   host port to open
  --to HOST:PORT  destination (VPS IP and port)
  --name NAME     optional label for the unit description
EOF
}

require_root() { [[ "$(id -u)" -eq 0 ]] || die "Run as root."; }

valid_port() { [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 1 && $1 <= 65535 )); }

unit_for() { echo "/etc/systemd/system/omega-forward-$1.service"; }

add_forward() {
    require_root
    valid_port "${LISTEN:-}" || die "--listen must be a port number (1-65535)"
    [[ "$TARGET" =~ ^[A-Za-z0-9_.:\[\]-]+:[0-9]+$ ]] || die "--to must look like HOST:PORT"
    local target_port="${TARGET##*:}"
    valid_port "$target_port" || die "Destination port is invalid"
    command -v socat >/dev/null 2>&1 || die "socat is not installed. Run: apt-get install -y socat"
    local socat_bin; socat_bin="$(command -v socat)"
    local unit; unit="$(unit_for "$LISTEN")"
    local label="${NAME:-forward}"
    cat >"$unit" <<EOF
[Unit]
Description=Vizion port forward ${LISTEN} -> ${TARGET} (${label})
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=${socat_bin} TCP-LISTEN:${LISTEN},fork,reuseaddr TCP:${TARGET}
Restart=always
RestartSec=2
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now "omega-forward-${LISTEN}.service" >/dev/null 2>&1 || true
    systemctl restart "omega-forward-${LISTEN}.service"
    say "Forwarding host port ${LISTEN} -> ${TARGET}"
    say "Service: omega-forward-${LISTEN}.service ($(systemctl is-active "omega-forward-${LISTEN}.service" 2>/dev/null || echo unknown))"
    echo "PORT_FORWARD=${LISTEN}->${TARGET}"
}

list_forwards() {
    echo "Active Vizion port forwards:"
    local found=0
    for unit in /etc/systemd/system/omega-forward-*.service; do
        [[ -e "$unit" ]] || continue
        found=1
        local base; base="$(basename "$unit" .service)"
        local exec_line; exec_line="$(grep -m1 '^ExecStart=' "$unit" | sed 's/^ExecStart=//')"
        printf '  %-22s %-10s %s\n' "$base" "$(systemctl is-active "$base.service" 2>/dev/null || echo unknown)" "$exec_line"
    done
    [[ "$found" -eq 1 ]] || echo "  (none yet)"
}

remove_forward() {
    require_root
    [[ -n "$LISTEN" ]] || die "--listen is required"
    valid_port "$LISTEN" || die "--listen must be a port number"
    local unit; unit="$(unit_for "$LISTEN")"
    [[ -f "$unit" ]] || die "No forward found for port ${LISTEN}"
    systemctl disable --now "omega-forward-${LISTEN}.service" >/dev/null 2>&1 || true
    rm -f "$unit"
    systemctl daemon-reload
    say "Removed forward on port ${LISTEN}"
    echo "PORT_FORWARD_REMOVED=${LISTEN}"
}

interactive() {
    while true; do
        echo
        echo "Port forwarding"
        echo "  1) Add forward"
        echo "  2) List forwards"
        echo "  3) Remove forward"
        echo "  4) Back"
        read -rp "Choose [1-4]: " choice || return 0
        case "${choice:-}" in
            1)
                read -rp "Host port to open: " LISTEN || continue
                read -rp "Destination HOST:PORT (VPS IP:port): " TARGET || continue
                read -rp "Label (optional): " NAME || true
                add_forward || true
                ;;
            2) list_forwards ;;
            3)
                read -rp "Port to remove: " LISTEN || continue
                remove_forward || true
                ;;
            4|q|Q|"") return 0 ;;
            *) echo "Choose 1-4." ;;
        esac
    done
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        add) ACTION="add"; shift ;;
        list) ACTION="list"; shift ;;
        remove) ACTION="remove"; shift ;;
        --interactive) ACTION="interactive"; shift ;;
        --listen) LISTEN="${2:-}"; shift 2 ;;
        --to) TARGET="${2:-}"; shift 2 ;;
        --name) NAME="${2:-}"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

case "$ACTION" in
    add) add_forward ;;
    list) list_forwards ;;
    remove) remove_forward ;;
    interactive) interactive ;;
    --help|help|"") usage ;;
    *) die "Unknown action: $ACTION" ;;
esac
