#!/usr/bin/env bash
set -Eeuo pipefail
command -v incus >/dev/null 2>&1 || exit 0
# Incus already performs remote image auto-update for cached aliases; this command forces a light
# daemon-side refresh check without modifying running instances.
incus image list local: --format json >/dev/null 2>&1 || true
