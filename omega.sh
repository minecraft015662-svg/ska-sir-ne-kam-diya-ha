#!/usr/bin/env bash
# OMEGA PANEL - one command menu
#
# No clone needed:
#   bash <(curl -sL https://raw.githubusercontent.com/minecraft015662-svg/ska-sir-ne-kam-diya-ha/main/omega.sh)
#
# Or from a checkout:
#   sudo bash omega.sh
#
# Credit: sartahk34 · SKa
set -Eeuo pipefail

REPO_SLUG="${OMEGA_REPO_SLUG:-minecraft015662-svg/ska-sir-ne-kam-diya-ha}"
REPO_REF="${OMEGA_REPO_REF:-main}"
ARCHIVE_URL="${OMEGA_REPO_ARCHIVE:-https://codeload.github.com/${REPO_SLUG}/tar.gz/refs/heads/${REPO_REF}}"

clear_screen() {
    if [[ -t 1 ]]; then
        clear 2>/dev/null || printf '\033[H\033[2J'
    fi
}

# When started as `bash <(curl ...)` there is no checkout; fetch one into tmp.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || echo /)"
if [[ ! -f "$ROOT_DIR/setup.sh" ]]; then
    command -v curl >/dev/null 2>&1 || { echo "curl is required for the one-line installer." >&2; exit 1; }
    command -v tar >/dev/null 2>&1 || { echo "tar is required for the one-line installer." >&2; exit 1; }
    BOOT_DIR="$(mktemp -d)"
    echo "Downloading Omega Panel (${REPO_SLUG}@${REPO_REF}) ..."
    if ! curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$BOOT_DIR" --strip-components=1; then
        echo "Download failed. Check the network or clone the repo manually." >&2
        exit 1
    fi
    [[ -f "$BOOT_DIR/setup.sh" ]] || { echo "Downloaded archive is missing setup.sh" >&2; exit 1; }
    exec bash "$BOOT_DIR/omega.sh" "$@"
fi

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
  │   Credit: sartahk34 · SKa            │
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

    local panel_host node_bind default_node_url chosen_bind
    panel_host="$(printf '%s' "$panel" | sed -E 's#^https?://([^/:]+).*#\1#')"
    if [[ "$panel_host" == "127.0.0.1" || "$panel_host" == "localhost" ]]; then
        node_bind="127.0.0.1"
        default_node_url="http://127.0.0.1:${NODE_PORT}"
    else
        node_bind="0.0.0.0"
        default_node_url="http://$(hostname -I 2>/dev/null | awk '{print $1}'):${NODE_PORT}"
    fi
    read -rp "Node agent bind address [${node_bind}]: " chosen_bind || true
    node_bind="${chosen_bind:-$node_bind}"
    [[ "$node_bind" == "127.0.0.1" ]] && default_node_url="http://127.0.0.1:${NODE_PORT}"
    read -rp "Node URL the panel should reach [${default_node_url}]: " node_url || true
    node_url="${node_url:-$default_node_url}"

    if [[ "$(id -u)" -eq 0 ]]; then
        say "Installing the node agent (bind ${node_bind}) ..."
        bash "$ROOT_DIR/scripts/omega-node-install.sh" "--bind=${node_bind}"
    else
        warn "Not root: skipping agent install. Run 'sudo bash scripts/omega-node-install.sh --bind=${node_bind}' first if the agent is missing."
    fi

    say "Registering this node with the panel ..."
    bash "$ROOT_DIR/scripts/omega-node-connect.sh" \
        --panel "$panel" --key "$enroll_key" --name "$node_name" --url "$node_url"
    ok "Node '${node_name}' connected to ${panel}"
    if [[ "$node_bind" != "127.0.0.1" ]]; then
        warn "Port ${NODE_PORT} should only be open to the panel, e.g.: ufw allow from PANEL_IP to any port ${NODE_PORT} proto tcp"
    fi
}

port_forward() {
    clear_screen
    bash "$ROOT_DIR/scripts/omega-portforward.sh" --interactive
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
        clear_screen
        print_logo
        cat <<EOF
  1) Install panel
  2) Uninstall panel
  3) Node install + connect
  4) Port forwarding
  5) Panel status
  6) Update panel
  7) Exit
EOF
        echo
        read -rp "Choose [1-7]: " choice || exit 0
        case "${choice:-}" in
            1) install_panel ;;
            2) uninstall_panel ;;
            3) node_connect ;;
            4) port_forward ;;
            5) panel_status ;;
            6) update_panel ;;
            7|q|Q) exit 0 ;;
            *) warn "Please choose 1-7." ;;
        esac
        echo
        read -rp "Press Enter to return to the menu..." _ || exit 0
    done
}

case "${1:-}" in
    --install) shift; install_panel "$@" ;;
    --uninstall) uninstall_panel ;;
    --node) node_connect ;;
    --port-forward) port_forward ;;
    --status) panel_status ;;
    --update) update_panel ;;
    --help|-h)
        clear_screen
        print_logo
        cat <<EOF
Usage: sudo bash omega.sh [option]

  (no option)     interactive menu
  --install       install the panel (runs setup.sh)
  --uninstall     stop and remove the panel services
  --node          install this host as a node and connect it to a panel
  --port-forward  create/list/remove socat port forwards
  --status        service and node agent health
  --update        git pull + re-run the installer

One line (no clone):
  bash <(curl -sL https://raw.githubusercontent.com/${REPO_SLUG}/${REPO_REF}/omega.sh)

Default login after install: admin / admin
Credit: sartahk34 · SKa
EOF
        ;;
    "") main_menu ;;
    *) die "Unknown option: $1 (try --help)" ;;
esac
