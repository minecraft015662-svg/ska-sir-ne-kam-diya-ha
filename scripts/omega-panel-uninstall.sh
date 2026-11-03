#!/usr/bin/env bash
# Omega Panel - uninstall the panel services.
#
#   sudo bash scripts/omega-panel-uninstall.sh           # services only, keep data
#   sudo bash scripts/omega-panel-uninstall.sh --purge   # also delete code/database/config
#
# The node agent can be removed separately with scripts/omega-node-uninstall.sh.
set -Eeuo pipefail

INSTALL_DIR="${OMEGA_INSTALL_DIR:-/opt/omega-panel}"
DATA_DIR="${OMEGA_DATA_DIR:-/var/lib/omega-panel}"
CONFIG_DIR="/etc/omega-panel"
PURGE=0

for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        --help|-h)
            cat <<EOF
Usage: sudo bash scripts/omega-panel-uninstall.sh [--purge]

  --purge   also delete ${INSTALL_DIR}, ${DATA_DIR} and ${CONFIG_DIR}
EOF
            exit 0 ;;
    esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo bash scripts/omega-panel-uninstall.sh [--purge]"
command -v systemctl >/dev/null 2>&1 || die "systemd is required"

UNITS=(omega-panel.service omega-node.service omega-jobs.service omega-watchdog.timer omega-image-refresh.timer)
for unit in "${UNITS[@]}"; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^${unit}"; then
        systemctl disable --now "$unit" >/dev/null 2>&1 || true
    fi
    rm -f "/etc/systemd/system/${unit}"
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
done
systemctl daemon-reload
echo "PANEL_SERVICES=removed"

if [[ "$PURGE" -eq 1 ]]; then
    rm -rf "$INSTALL_DIR" "$DATA_DIR" "$CONFIG_DIR"
    echo "PANEL_DATA=deleted"
    echo "PANEL_CODE=deleted"
    echo "System user was kept; remove it manually if you really need to: userdel omega-panel"
else
    echo "PANEL_DATA=kept (${DATA_DIR})"
    echo "PANEL_CODE=kept (${INSTALL_DIR})"
    echo "Run again with --purge to delete code, database and config."
fi

echo "PANEL_UNINSTALL=done"
