#!/usr/bin/env bash
set -u
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ok=0
say(){ printf '[%s] %s\n' "$1" "$2"; }
check(){ if "$@" >/dev/null 2>&1; then say OK "$*"; else say WARN "$*"; ok=1; fi; }
[[ -x "$APP_DIR/venv/bin/python" ]] && say OK 'Python virtualenv present' || say WARN 'Python virtualenv missing (run setup.sh)';
command -v incus >/dev/null 2>&1 && say OK "Incus: $(incus --version 2>/dev/null || echo detected)" || say WARN 'Incus not installed/available'
command -v qemu-system-x86_64 >/dev/null 2>&1 && say OK 'QEMU installed' || say WARN 'QEMU not found'
command -v virsh >/dev/null 2>&1 && say OK 'libvirt/virsh installed' || say WARN 'virsh not found'
[[ -e /dev/kvm ]] && say OK '/dev/kvm present' || say WARN '/dev/kvm absent (VM acceleration unavailable)'
command -v kvm-ok >/dev/null 2>&1 && check kvm-ok || say WARN 'kvm-ok not installed'
if command -v systemctl >/dev/null 2>&1; then
  for unit in omega-panel.service omega-node.service omega-jobs.service omega-watchdog.timer omega-image-refresh.timer; do
    check systemctl is-enabled "$unit"
  done
fi
if [[ -x "$APP_DIR/venv/bin/python" ]]; then
  check "$APP_DIR/venv/bin/python" -m compileall -q "$APP_DIR"
fi
printf '\nUNL node policy is intentional: it removes a panel-imposed CPU cap; physical CPU/RAM/storage remain the actual limit.\n'
exit "$ok"
