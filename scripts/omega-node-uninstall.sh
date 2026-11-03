#!/usr/bin/env bash
# Omega Panel - uninstall the node agent from this host.
#
#   sudo bash scripts/omega-node-uninstall.sh            # stop + disable + remove unit
#   sudo bash scripts/omega-node-uninstall.sh --purge    # also delete the node token
#
# The shared panel code in /opt/omega-panel is never deleted: the panel may run
# from the same directory. Only agent-specific runtime files are removed.
set -Eeuo pipefail

INSTALL_DIR="${OMEGA_INSTALL_DIR:-/opt/omega-panel}"
UNIT="omega-node.service"
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --help)
      cat <<EOF
Omega node agent uninstaller

Usage: sudo bash scripts/omega-node-uninstall.sh [--purge]

  --purge   also remove /etc/omega-panel/node-token
EOF
      exit 0 ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo bash scripts/omega-node-uninstall.sh"

if systemctl list-unit-files | grep -q "^${UNIT}"; then
  systemctl disable --now "$UNIT" >/dev/null 2>&1 || true
fi
rm -f "/etc/systemd/system/${UNIT}"
systemctl daemon-reload
systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
echo "NODE_SERVICE=removed"

if [[ "$PURGE" -eq 1 ]]; then
  rm -f /etc/omega-panel/node-token
  echo "NODE_TOKEN=removed"
else
  echo "NODE_TOKEN=kept (use --purge to delete it)"
fi

echo "Install directory kept: ${INSTALL_DIR}"
echo "[node-uninstall] done"
