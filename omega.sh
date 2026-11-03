#!/usr/bin/env bash
# OMEGA PANEL - one command menu
#
#   sudo bash omega.sh                 interactive menu
#   sudo bash omega.sh --install       install the panel
#   sudo bash omega.sh --uninstall     remove the panel services
#   sudo bash omega.sh --node          install this host as a node and connect it
#   sudo bash omega.sh --status        show service / health status
#   sudo bash omega.sh --update        git pull + re-run setup
#
# Default first login: admin / admin  (change it right after the first login)
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${OMEGA_INSTALL_DIR:-/opt/omega-panel}"
PANEL_PORT="${OMEGA_PORT:-5000}"
NODE_PORT="${OMEGA_NODE_PORT:-5001}"

say()  { printf '\033[36m>\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

print_logo() {
    cat <<'LOGO'
  ┌──────────────────────────────────────┐
  │            OMEGA  PANEL              │
  │    VPS · LXC · KVM control panel     │
  └──────────────────────────────────────┘
LOGO
    printf '\n'
}

need_root() {
    [[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo bash omega.sh $*"
}

need_systemd() {
    command -v systemctl >/dev/null 2>&1 || die "systemd is required (Ubuntu/Debian server)."
}

install_panel() {
    need_root
    need_systemd
    say "Installing Omega Panel from ${ROOT_DIR} ..."
    bash "$ROOT_DIR/setup.sh" "$@"
    ok "Install finished."
    echo
    echo "  Panel URL : http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PANEL_PORT}"
    echo "  Login     : admin / admin   (change it after first login)"
    echo "  Password  : /var/lib/omega-panel/first_admin_credentials.txt"
    echo "  Status    : sudo bash omega.sh --status"
}

uninstall_panel() {
    need_root
    need_systemd
    echo "This stops and removes the panel services."
    read -rp "Also delete the database and panel code in ${INSTALL_DIR}? type 'yes' to delete: " purge || true
    if [[ "${purge:-}" == "yes" ]]; then
        warn "Full purge selected: code, database and config will be deleted."
        bash "$ROOT_DIR/scripts/omega-panel-uninstall.sh" --purge
    else
        bash "$ROOT_DIR/scripts/omega-panel-uninstall.sh"
    fi
}

node_connect() {
    need_systemd
    echo
    echo "Connect this server as a node of an Omega panel."
    echo "The enrollment key is on the panel: Admin -> Node Install / Uninstall."
    echo
    read -rp "Panel URL [http://127.0.0.1:${PANEL_PORT}]: " panel || true
    panel="${panel:-http://127.0.0.1:${PANEL_PORT}}"
    read -rp "Enrollment key: " enroll_key || true
    [[ -n "${enroll_key:-}" ]] || die "Enrollment key is required."
    read -rp "Node name [$(hostname -s 2>/dev/null || hostname)]: " node_name || true
    node_name="${node_name:-$(hostname -s 2>/dev/null || hostname)}"
    read -rp "Node URL the panel should reach [http://127.0.0.1:${NODE_PORT}]: " node_url || true
    node_url="${node_url:-http://127.0.0.1:${NODE_PORT}}"

    if [[ "$(id -u)" -eq 0 ]]; then
        say "Installing the node agent on this host ..."
        bash "$ROOT_DIR/scripts/omega-node-install.sh"
    else
        warn "Not root: skipping agent install. Run 'sudo bash scripts/omega-node-install.sh' first if the agent is missing."
    fi

    say "Registering this node with the panel ..."
    bash "$ROOT_DIR/scripts/omega-node-connect.sh" \
        --panel "$panel" --key "$enroll_key" --name "$node_name" --url "$node_url"
    ok "Node '${node_name}' connected to ${panel}"
}

panel_status() {
    echo
    echo "Omega Panel status"
    echo "------------------"
    if command -v systemctl >/dev/null 2>&1; then
        for unit in omega-panel.service omega-node.service omega-jobs.service omega-watchdog.timer omega-image-refresh.timer; do
            state="$(systemctl is-active "$unit" 2>/dev/null || true)"
            printf '  %-28s %s\n' "$unit" "${state:-not-installed}"
        done
    else
        warn "systemctl not available"
    fi
    local health
    health="$(curl -fsS --max-time 4 "http://127.0.0.1:${NODE_PORT}/api/health" 2>/dev/null || true)"
    echo "  node agent health            ${health:-unreachable}"
    if [[ -r /var/lib/omega-panel/first_admin_credentials.txt ]]; then
        echo "  credentials file             /var/lib/omega-panel/first_admin_credentials.txt"
    fi
    echo
}

update_panel() {
    need_root
    need_systemd
    if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        say "Pulling the latest code ..."
        git -C "$ROOT_DIR" pull --ff-only
    else
        warn "Not a git checkout; skipping git pull."
    fi
    say "Re-running the installer ..."
    bash "$ROOT_DIR/setup.sh" --noninteractive
    ok "Update finished."
}

main_menu() {
    while true; do
        print_logo
        cat <<EOF
  1) Install panel
  2) Uninstall panel
  3) Node install + connect
  4) Panel status
  5) Update panel
  6) Exit
EOF
        echo
        read -rp "Choose [1-6]: " choice || exit 0
        case "${choice:-}" in
            1) install_panel ;;
            2) uninstall_panel ;;
            3) node_connect ;;
            4) panel_status ;;
            5) update_panel ;;
            6|q|Q) exit 0 ;;
            *) warn "Please choose 1-6." ;;
        esac
        echo
        read -rp "Press Enter to return to the menu..." _ || exit 0
    done
}

case "${1:-}" in
    --install) shift; install_panel "$@" ;;
    --uninstall) uninstall_panel ;;
    --node) node_connect ;;
    --status) panel_status ;;
    --update) update_panel ;;
    --help|-h)
        print_logo
        cat <<EOF
Usage: sudo bash omega.sh [option]

  (no option)    interactive menu
  --install      install the panel (runs setup.sh)
  --uninstall    stop and remove the panel services
  --node         install this host as a node and connect it to a panel
  --status       service and node agent health
  --update       git pull + re-run the installer

Default login after install: admin / admin
EOF
        ;;
    "") main_menu ;;
    *) die "Unknown option: $1 (try --help)" ;;
esac
