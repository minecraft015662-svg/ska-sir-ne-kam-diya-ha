#!/usr/bin/env bash
# Omega Panel - register this host as a node of a panel (command based connect).
#
#   sudo bash scripts/omega-node-connect.sh \
#       --panel http://PANEL_IP:5000 \
#       --key   ENROLLMENT_KEY \
#       --name  node-2 \
#       --url   http://NODE_IP:5001
#
# The enrollment key is generated on the panel and shown in
# Admin -> Node Install / Uninstall. The node token is read from
# /etc/omega-panel/node-token (created by scripts/omega-node-install.sh).
set -Eeuo pipefail

PANEL=""
KEY=""
NAME="$(hostname -s 2>/dev/null || hostname)"
URL=""
PORT="${OMEGA_NODE_PORT:-5001}"
TOKEN_FILE="${OMEGA_NODE_TOKEN_FILE:-/etc/omega-panel/node-token}"
INSECURE=0

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --panel) PANEL="${2:-}"; shift 2 ;;
        --key) KEY="${2:-}"; shift 2 ;;
        --name) NAME="${2:-}"; shift 2 ;;
        --url) URL="${2:-}"; shift 2 ;;
        --port) PORT="${2:-}"; shift 2 ;;
        --token-file) TOKEN_FILE="${2:-}"; shift 2 ;;
        --insecure) INSECURE=1; shift ;;
        --help|-h)
            cat <<EOF
Usage: bash scripts/omega-node-connect.sh --panel URL --key KEY [options]

  --panel URL         panel base URL, e.g. http://1.2.3.4:5000
  --key KEY           enrollment key from Admin -> Node Install / Uninstall
  --name NAME         node name in the panel (default: hostname)
  --url URL           URL the panel should use for this node (default http://127.0.0.1:5001)
  --port PORT         node agent port (default 5001)
  --token-file PATH   node token file (default /etc/omega-panel/node-token)
  --insecure          allow self-signed TLS (curl -k)
EOF
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

[[ -n "$PANEL" ]] || die "--panel is required"
[[ -n "$KEY" ]] || die "--key is required (Admin -> Node Install / Uninstall)"
[[ -r "$TOKEN_FILE" ]] || die "Missing node token ${TOKEN_FILE}. Run scripts/omega-node-install.sh first."
command -v curl >/dev/null 2>&1 || die "curl is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
[[ -n "$TOKEN" ]] || die "Node token file is empty: ${TOKEN_FILE}"
PANEL="${PANEL%/}"
[[ -n "$URL" ]] || URL="http://127.0.0.1:${PORT}"
URL="${URL%/}"

PAYLOAD="$(python3 - "$NAME" "$URL" "$TOKEN" <<'PY'
import json
import socket
import sys

name, url, token = sys.argv[1:4]
print(json.dumps({
    "name": name,
    "node_url": url,
    "token": token,
    "hostname": socket.gethostname(),
    "port": None,
}))
PY
)"

CURL_ARGS=(-sS -f --max-time 25 -X POST "${PANEL}/api/nodes/enroll"
           -H "Content-Type: application/json" -H "X-Omega-Enroll: ${KEY}"
           --data "${PAYLOAD}")
if [[ "$INSECURE" -eq 1 ]]; then
    CURL_ARGS+=(-k)
fi

echo "Connecting ${NAME} -> ${PANEL} ..."
if RESPONSE="$(curl "${CURL_ARGS[@]}" 2>&1)"; then
    echo "$RESPONSE"
    echo "NODE_CONNECT=ok"
else
    echo "$RESPONSE" >&2
    echo "NODE_CONNECT=failed" >&2
    die "The panel rejected or could not be reached. Check the panel URL, the enrollment key and that port ${PORT} is reachable."
fi
