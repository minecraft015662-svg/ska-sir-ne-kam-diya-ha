#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Compatibility entrypoint retained for existing deployments; it no longer performs destructive package purges.
exec bash "$SCRIPT_DIR/setup.sh" --noninteractive "$@"
