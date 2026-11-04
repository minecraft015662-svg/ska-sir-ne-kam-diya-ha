#!/usr/bin/env bash
# VIZION PANEL - one command menu
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

# Make box alignment reliable (counts characters, not bytes)
if locale -a 2>/dev/null | grep -qi '^c\.utf-\?8$'; then export LC_ALL=C.UTF-8; fi

BRAND_NAME="${OMEGA_BRAND:-VIZION  PANEL}"
BRAND_SUB="VPS · LXC · KVM control panel"
BRAND_CREDIT="Credit: sartahk34 · SKa"
BOX_W=46

if [[ -t 1 ]]; then
    C_BORDER=$'\033[36m'; C_TITLE=$'\033[1;97m'; C_SUB=$'\033[96m'; C_DIM=$'\033[2;37m'; C_RST=$'\033[0m'
    C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_WARN=$'\033[33m'
else
    C_BORDER=""; C_TITLE=""; C_SUB=""; C_DIM=""; C_RST=""; C_OK=""; C_BAD=""; C_WARN=""
fi

box_line() {   # box_line "text" "color"
    local text="$1" color="${2:-}" len l r
    len=${#text}
    l=$(( (BOX_W - len) / 2 )); r=$(( BOX_W - len - l ))
    printf '  %s║%s%*s%s%s%s%*s%s║%s\n' "$C_BORDER" "$C_RST" "$l" "" "$color" "$text" "$C_RST" "$r" "" "$C_BORDER" "$C_RST"
}

print_logo() {
    local bar
    bar="$(printf '═%.0s' $(seq 1 "$BOX_W"))"
    printf '\n  %s╔%s╗%s\n' "$C_BORDER" "$bar" "$C_RST"
    box_line "" ""
    box_line "$BRAND_NAME" "$C_TITLE"
    box_line "$BRAND_SUB" "$C_SUB"
    box_line "" ""
    box_line "$BRAND_CREDIT" "$C_DIM"
    printf '  %s╚%s╝%s\n' "$C_BORDER" "$bar" "$C_RST"
    print_state_line
    printf '\n'
}

print_state_line() {
    local state="not installed" color="$C_BAD"
    if command -v systemctl >/dev/null 2>&1 && [[ -f /etc/systemd/system/omega-panel.service ]]; then
        state="$(systemctl is-active omega-panel.service 2>/dev/null || true)"
        if [[ "$state" == "active" ]]; then color="$C_OK"; else color="$C_WARN"; fi
    fi
    printf '  Panel: %s%s%s   Port: %s   Dir: %s\n' "$color" "${state:-unknown}" "$C_RST" "$PANEL_PORT" "$INSTALL_DIR"
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
    echo "Panel status"
    echo "------------------"
    if command -v systemctl >/dev/null 2>&1; then
        for unit in omega-panel.service omega-bot.service omega-node.service omega-jobs.service omega-watchdog.timer omega-image-refresh.timer; do
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

fetch_latest() {   # downloads latest code into $1
    local dest="$1"
    command -v curl >/dev/null 2>&1 || die "curl is required for update."
    command -v tar  >/dev/null 2>&1 || die "tar is required for update."
    say "Downloading latest code (${REPO_SLUG}@${REPO_REF}) ..."
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$dest" --strip-components=1 \
        || die "Download failed. Check internet / repo access."
    [[ -f "$dest/setup.sh" && -f "$dest/app.py" ]] || die "Downloaded archive looks incomplete."
}

restart_services() {
    # Make sure the Discord bot / background worker unit exists (added in newer versions).
    if [[ -f "$INSTALL_DIR/bot_runner.py" && ! -f /etc/systemd/system/omega-bot.service ]]; then
        local svc_user="omega-panel"; id "$svc_user" >/dev/null 2>&1 || svc_user="root"
        cat > /etc/systemd/system/omega-bot.service <<UNIT
[Unit]
Description=Omega Panel Discord bot and background workers
After=network-online.target incus.service omega-panel.service
Wants=network-online.target

[Service]
Type=simple
User=${svc_user}
Group=${svc_user}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONPATH=${INSTALL_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/omega-panel/omega.env
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/bot_runner.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/var/lib/omega-panel /etc/omega-panel

[Install]
WantedBy=multi-user.target
UNIT
        systemctl daemon-reload 2>/dev/null || true
        systemctl enable omega-bot.service >/dev/null 2>&1 || true
    fi
    systemctl daemon-reload 2>/dev/null || true
    for unit in omega-panel.service omega-bot.service omega-jobs.service omega-node.service; do
        if [[ -f "/etc/systemd/system/$unit" ]]; then
            systemctl restart "$unit" 2>/dev/null && ok "restarted $unit" || warn "could not restart $unit"
        fi
    done
}

update_panel() {
    need_root
    need_systemd
    local tmp
    if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        say "Git checkout found - pulling the latest code ..."
        git -C "$ROOT_DIR" pull --ff-only || warn "git pull failed, continuing with local code."
        bash "$ROOT_DIR/setup.sh" --noninteractive
    else
        tmp="$(mktemp -d)"
        fetch_latest "$tmp"
        say "Applying update to ${INSTALL_DIR} (database and config are kept) ..."
        bash "$tmp/setup.sh" --noninteractive
        rm -rf "$tmp"
    fi
    restart_services
    ok "Update finished."
    doctor_panel quiet || true
}

fix_panel() {
    need_root
    need_systemd
    say "Repairing ${INSTALL_DIR} ..."
    [[ -d "$INSTALL_DIR" ]] || die "Panel is not installed. Choose Install first."
    if [[ "$ROOT_DIR" != "$INSTALL_DIR" && -f "$ROOT_DIR/app.py" ]]; then
        say "Syncing code from ${ROOT_DIR} ..."
        cp -a "$ROOT_DIR"/. "$INSTALL_DIR"/
    fi
    if [[ -x "$INSTALL_DIR/venv/bin/pip" ]]; then
        say "Re-installing Python requirements ..."
        "$INSTALL_DIR/venv/bin/pip" install --no-cache-dir -q -r "$INSTALL_DIR/requirements.txt" \
            && ok "requirements ok" || warn "pip install had errors"
    else
        warn "venv missing - run Update (it rebuilds everything)."
    fi
    chmod +x "$INSTALL_DIR"/scripts/*.sh "$INSTALL_DIR/omega.sh" 2>/dev/null || true
    if id omega-panel >/dev/null 2>&1; then chown -R omega-panel:omega-panel "$INSTALL_DIR" /var/lib/omega-panel 2>/dev/null || true; fi
    restart_services
    sleep 2
    doctor_panel quiet || true
    echo
    echo "  If an error still shows, run:  sudo bash ${INSTALL_DIR}/omega.sh --update"
}

doctor_panel() {
    local quiet="${1:-}" bad=0 py="python3"
    [[ "$quiet" == "quiet" ]] || { echo; echo "Panel doctor"; echo "------------"; }
    [[ -x "$INSTALL_DIR/venv/bin/python" ]] && py="$INSTALL_DIR/venv/bin/python"

    if [[ -f "$INSTALL_DIR/app.py" ]]; then
        if "$py" -m py_compile "$INSTALL_DIR/app.py" 2>/dev/null; then ok "app.py syntax ok"; else printf '%s✗%s app.py has a syntax error\n' "$C_BAD" "$C_RST"; bad=1; fi
        if out="$(cd "$INSTALL_DIR" && "$py" - <<'PY'
import ast, builtins, sys
src = open("app.py").read(); t = ast.parse(src)
d = set(dir(builtins))
for n in ast.walk(t):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        d.add(n.name)
        if not isinstance(n, ast.ClassDef):
            a = n.args
            for x in a.args + a.kwonlyargs + a.posonlyargs: d.add(x.arg)
            if a.vararg: d.add(a.vararg.arg)
            if a.kwarg: d.add(a.kwarg.arg)
    elif isinstance(n, ast.Lambda):
        for x in n.args.args + n.args.kwonlyargs: d.add(x.arg)
        if n.args.vararg: d.add(n.args.vararg.arg)
        if n.args.kwarg: d.add(n.args.kwarg.arg)
    elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)): d.add(n.id)
    elif isinstance(n, (ast.Import, ast.ImportFrom)):
        for a in n.names: d.add((a.asname or a.name).split(".")[0])
    elif isinstance(n, ast.ExceptHandler) and n.name: d.add(n.name)
    elif isinstance(n, (ast.Global, ast.Nonlocal)): d.update(n.names)
miss = sorted({(n.id, n.lineno) for n in ast.walk(t) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in d and n.id != "__file__"}, key=lambda x: x[1])
for name, line in miss: print(f"undefined name '{name}' at app.py line {line}")
sys.exit(1 if miss else 0)
PY
        )"; then ok "no undefined names in app.py"; else printf '%s✗%s %s\n' "$C_BAD" "$C_RST" "$out"; bad=1; fi
    else
        printf '%s✗%s %s/app.py not found (not installed?)\n' "$C_BAD" "$C_RST" "$INSTALL_DIR"; bad=1
    fi

    if command -v systemctl >/dev/null 2>&1; then
        for unit in omega-panel.service omega-bot.service omega-jobs.service omega-node.service; do
            [[ -f "/etc/systemd/system/$unit" ]] || continue
            if [[ "$(systemctl is-active "$unit" 2>/dev/null)" == "active" ]]; then ok "$unit running"; else printf '%s✗%s %s is not running\n' "$C_BAD" "$C_RST" "$unit"; bad=1; fi
        done
    fi

    if curl -fsS -o /dev/null --max-time 5 "http://127.0.0.1:${PANEL_PORT}/" 2>/dev/null; then ok "panel answers on port ${PANEL_PORT}"; else printf '%s✗%s panel does not answer on port %s\n' "$C_BAD" "$C_RST" "$PANEL_PORT"; bad=1; fi

    if [[ "$bad" -ne 0 ]] && command -v journalctl >/dev/null 2>&1; then
        echo; warn "Last panel log lines:"
        journalctl -u omega-panel.service -n 15 --no-pager 2>/dev/null | sed 's/^/    /' || true
        if [[ -f /etc/systemd/system/omega-bot.service ]]; then
            echo; warn "Last bot log lines:"
            journalctl -u omega-bot.service -n 15 --no-pager 2>/dev/null | sed 's/^/    /' || true
        fi
    fi
    return "$bad"
}

main_menu() {
    while true; do
        clear_screen
        print_logo
        printf '  %s[ SETUP ]%s\n' "$C_SUB" "$C_RST"
        echo "    1) Install panel"
        echo "    2) Update panel          (latest code from GitHub)"
        echo "    3) Fix / repair panel    (use when 'Something went wrong')"
        echo "    4) Doctor                (check errors + logs)"
        printf '\n  %s[ MANAGE ]%s\n' "$C_SUB" "$C_RST"
        echo "    5) Panel status"
        echo "    6) Node install + connect"
        echo "    7) Port forwarding"
        printf '\n  %s[ DANGER ]%s\n' "$C_SUB" "$C_RST"
        echo "    8) Uninstall panel"
        echo "    0) Exit"
        echo
        read -rp "  Choose [0-8]: " choice || exit 0
        case "${choice:-}" in
            1) install_panel ;;
            2) update_panel ;;
            3) fix_panel ;;
            4) doctor_panel || true ;;
            5) panel_status ;;
            6) node_connect ;;
            7) port_forward ;;
            8) uninstall_panel ;;
            0|q|Q) exit 0 ;;
            *) warn "Please choose 0-8." ;;
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
    --fix|--repair) fix_panel ;;
    --doctor) doctor_panel ;;
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
  --update        download latest code + re-run the installer
  --fix           repair deps/permissions and restart services
  --doctor        check code, services, port and show logs

One line (no clone):
  bash <(curl -sL https://raw.githubusercontent.com/${REPO_SLUG}/${REPO_REF}/omega.sh)

Default login after install: admin / admin
Credit: sartahk34 · SKa
EOF
        ;;
    "") main_menu ;;
    *) die "Unknown option: $1 (try --help)" ;;
esac
