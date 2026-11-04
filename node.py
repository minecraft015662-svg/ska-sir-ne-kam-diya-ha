"""
VPS Manager - Node Agent (LXC)
Runs on each remote VPS node. Handles all LXC operations.
Panel communicates with this agent via HTTP API.

Usage:
  pip3 install flask psutil
  python3 node.py

Or just run this file — it auto-installs dependencies.
"""
import os
import sys
import json
import secrets
import re
import shlex
import subprocess
import tempfile
import time
import http.client as http
import pty
import select
import struct
import uuid
import threading
import base64
from functools import wraps


def _parse_mem_limit(val):
    val = val.strip()
    m = re.match(r'^(\d+)([KMGTP]i?B?|B)?$', val, re.IGNORECASE)
    if not m:
        return None
    num = int(m.group(1))
    unit = (m.group(2) or '').upper()
    multipliers = {
        '': 1, 'B': 1,
        'K': 1024, 'KB': 1024, 'KIB': 1024,
        'M': 1024 ** 2, 'MB': 1024 ** 2, 'MIB': 1024 ** 2,
        'G': 1024 ** 3, 'GB': 1024 ** 3, 'GIB': 1024 ** 3,
        'T': 1024 ** 4, 'TB': 1024 ** 4, 'TIB': 1024 ** 4,
        'P': 1024 ** 5, 'PB': 1024 ** 5, 'PIB': 1024 ** 5,
    }
    mult = multipliers.get(unit)
    if mult is None:
        return None
    return num * mult


def ensure_deps():
    missing = []
    for mod, pkg in (('flask', 'flask'), ('psutil', 'psutil')):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[setup] Installing missing packages: {', '.join(missing)}")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q'] + missing)


ensure_deps()

from flask import Flask, request, jsonify, Response


def strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


app = Flask(__name__)

KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.node_api_key')
# The panel is given the token stored in this file by scripts/omega-node-connect.sh,
# so the agent MUST authenticate with the very same value, otherwise every
# authenticated call (VPS create/start/stop...) answers 401 Unauthorized.
TOKEN_FILE = os.environ.get('OMEGA_NODE_TOKEN_FILE', '/etc/omega-panel/node-token')
NODE_TYPE_FILE = os.environ.get('OMEGA_NODE_TYPE_FILE', '/etc/omega-panel/node-type')


def _load_api_key():
    env_key = os.environ.get('NODE_API_KEY', '').strip()
    if env_key:
        return env_key
    for path in (TOKEN_FILE, KEY_FILE):
        try:
            with open(path) as fh:
                value = fh.read().strip()
            if value:
                return value
        except OSError:
            continue
    generated = secrets.token_hex(32)
    try:
        with open(KEY_FILE, 'w') as fh:
            fh.write(generated)
    except Exception:
        pass
    return generated


API_KEY = _load_api_key()


def node_type():
    """lxc | kvm | incus (set by scripts/omega-node-install.sh --type=...)."""
    try:
        with open(NODE_TYPE_FILE) as fh:
            value = fh.read().strip().lower()
        if value in ('lxc', 'kvm', 'incus'):
            return value
    except OSError:
        pass
    return 'incus'


LISTEN_PORT = int(os.environ.get('NODE_PORT', 5001))

def _detect_socket():
    """Find the Incus (or LXD) unix socket instead of assuming one path."""
    candidates = [
        os.environ.get('OMEGA_INCUS_SOCKET', ''),
        '/var/lib/incus/unix.socket',
        '/var/lib/incus/unix.socket.user',
        '/var/snap/lxd/common/lxd/unix.socket',
        '/var/lib/lxd/unix.socket',
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return '/var/lib/incus/unix.socket'


LXD_SOCKET = _detect_socket()


def _lxd_request(method, path, data=None, timeout=30):
    """Send an HTTP request to the local Incus/LXD Unix socket.

    Returns ``(status_code, response_dict)``.  This deliberately uses
    ``http.client.HTTPConnection`` through the module alias imported above:
    ``import http.client as http`` means the correct class is
    ``http.HTTPConnection``.
    """
    import socket

    class _UnixSocketHTTPConnection(http.HTTPConnection):
        def __init__(self):
            super().__init__("localhost", timeout=timeout)

        def connect(self):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            try:
                sock.connect(LXD_SOCKET)
            except Exception:
                sock.close()
                raise
            self.sock = sock

    def _do(request_method, request_path, payload=None):
        conn = _UnixSocketHTTPConnection()
        try:
            headers = {}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            conn.request(
                request_method.upper(),
                request_path,
                body=payload,
                headers=headers,
            )
            response = conn.getresponse()
            raw = response.read()

            if not raw:
                parsed = {}
            else:
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parsed = {
                        "error": "Incus returned a non-JSON response",
                        "response": raw.decode("utf-8", errors="replace")[:1000],
                    }

            if not isinstance(parsed, dict):
                parsed = {"metadata": parsed}
            return response.status, parsed
        finally:
            conn.close()

    try:
        body = json.dumps(data).encode("utf-8") if data is not None else None
        status, response_data = _do(method, path, body)

        # Wait for asynchronous Incus operations and return their final result.
        if status == 202:
            operation_url = response_data.get("operation")
            if operation_url:
                deadline = time.monotonic() + min(max(timeout, 1), 600)
                while time.monotonic() < deadline:
                    time.sleep(0.25)
                    poll_status, operation = _do("GET", operation_url)
                    if poll_status >= 400:
                        return poll_status, operation

                    metadata = operation.get("metadata", {})
                    operation_state = metadata.get("status")

                    if operation_state == "Success":
                        return 200, operation
                    if operation_state == "Failure":
                        error = metadata.get("err") or "Incus operation failed"
                        return 500, {"error": error, "operation": operation}

                    # Some LXD-compatible APIs expose status_code instead.
                    result_code = metadata.get("status_code")
                    if result_code == 200:
                        return 200, operation
                    if isinstance(result_code, int) and result_code >= 400:
                        return 500, {
                            "error": metadata.get("err") or "Incus operation failed",
                            "operation": operation,
                        }

                return 408, {"error": "Incus operation timed out"}

        return status, response_data

    except (OSError, socket.error, http.HTTPException) as exc:
        app.logger.exception("Incus Unix-socket request failed: %s %s", method, path)
        return 500, {"error": str(exc)}
    except Exception as exc:
        app.logger.exception("Unexpected Incus request error: %s %s", method, path)
        return 500, {"error": str(exc)}


def _lxc_run(args, timeout=30):
    """Run an `incus` CLI command. Returns (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(['incus'] + args, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return '', 'Command timed out', 1
    except FileNotFoundError:
        return '', 'lxc command not found', 1
    except Exception as e:
        return '', str(e), 1


def lxc_status(name):
    code, resp = _lxd_request('GET', f'/1.0/instances/{name}')
    if code != 200 or resp.get('error_code', 0) != 0:
        return 'not_found'
    return resp.get('metadata', {}).get('status', '').lower()


def _read_stdout(meta):
    """Fetch the recorded stdout of a finished exec operation.
    Returns (return_code, stdout_bytes) or (None, None)."""
    output = meta.get('metadata', {}).get('output', {})
    if isinstance(output, dict):
        items = list(output.values())
    elif isinstance(output, list):
        items = output
    else:
        return None, None
    for path in items:
        if 'stdout' in path:
            import http.client as http
            import socket

            class _UC(http.HTTPConnection):
                def __init__(self):
                    super().__init__('localhost', timeout=10)

                def connect(self):
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.connect(LXD_SOCKET)

            c = _UC()
            c.request('GET', path)
            r = c.getresponse()
            rc = meta.get('metadata', {}).get('return-code', 0)
            return rc, r.read()
    return None, None


def lxc_attach(name, command, timeout=60):
    """Run a shell command inside a container via the Incus API.
    Returns (exit_code, stdout_bytes)."""
    code, resp = _lxd_request('POST', f'/1.0/instances/{name}/exec', data={
        'command': ['/bin/sh', '-c', command],
        'record-output': True,
        'environment': {'TERM': 'dumb'},
    }, timeout=timeout)
    if code not in (200, 201, 202):
        app.logger.warning('[lxc_attach] exec POST failed: code=%s resp=%s', code, str(resp)[:200])
        return 1, b''

    meta = resp.get('metadata', {})
    st = meta.get('status', '')
    if st == 'Success':
        rc, data = _read_stdout(meta)
        if rc is not None:
            return rc, data
        return meta.get('metadata', {}).get('return-code', 0), b''
    if st == 'Failure':
        app.logger.warning('[lxc_attach] immediate Failure: %s', str(meta)[:200])
        return 1, b''

    op_url = resp.get('operation', '')
    if not op_url:
        app.logger.warning('[lxc_attach] no operation URL')
        return 1, b''

    deadline = time.time() + timeout
    while time.time() < deadline:
        o_code, o_resp = _lxd_request('GET', op_url)
        if o_code == 200:
            meta = o_resp.get('metadata', {})
            st = meta.get('status', '')
            if st == 'Success':
                rc, data = _read_stdout(meta)
                if rc is not None:
                    return rc, data
                return meta.get('metadata', {}).get('return-code', 0), b''
            if st == 'Failure':
                return 1, b''
        time.sleep(0.3)
    app.logger.warning('[lxc_attach] timed out polling %s', op_url)
    return 1, b''


def lxc_fix_networking(name):
    """Alpine-style containers have no DHCP client config; set one up via busybox udhcpc."""
    try:
        import subprocess as _sp
        _sp.run(['incus', 'exec', name, '--', 'sh', '-c',
                 "cat > /opt/udhcpc.sh << 'SCRIPT'\n"
                 "#!/bin/sh\n"
                 'case "$1" in\n'
                 "  bound|renew)\n"
                 "    ip addr add $ip/$subnet dev $interface 2>/dev/null\n"
                 '    [ -n "$router" ] && ip route add default via $router dev $interface 2>/dev/null\n'
                 '    if [ -n "$dns" ]; then\n'
                 "      > /etc/resolv.conf\n"
                 "      for ns in $dns; do\n"
                 '        echo "nameserver $ns" >> /etc/resolv.conf\n'
                 "      done\n"
                 "    fi\n"
                 "    ;;\n"
                 "  deconfig)\n"
                 "    ip addr flush dev $interface 2>/dev/null\n"
                 "    ;;\n"
                 "esac\n"
                 "SCRIPT\n"
                 "chmod 755 /opt/udhcpc.sh"],
                timeout=30, capture_output=True)
        for _ in range(15):
            r = _sp.run(['incus', 'exec', name, '--', 'ip', 'addr', 'show', 'eth0'],
                        capture_output=True, timeout=10)
            if b'inet ' in r.stdout:
                break
            _sp.run(['incus', 'exec', name, '--', 'busybox', 'udhcpc', '-i', 'eth0', '-n',
                     '-s', '/opt/udhcpc.sh'], timeout=15, capture_output=True)
            time.sleep(2)
        _sp.run(['incus', 'exec', name, '--', 'sh', '-c',
                 "grep -q 'nameserver' /etc/resolv.conf 2>/dev/null || "
                 "echo 'nameserver 10.132.115.1' > /etc/resolv.conf"],
                timeout=10, capture_output=True)
    except Exception:
        pass


CLOUD_INIT = """#cloud-config
write_files:
  - path: /opt/udhcpc.sh
    content: |
      #!/bin/sh
      case "$1" in
        bound|renew)
          ip addr add $ip/$subnet dev $interface 2>/dev/null
          [ -n "$router" ] && ip route add default via $router dev $interface 2>/dev/null
          if [ -n "$dns" ]; then
            > /etc/resolv.conf
            for ns in $dns; do
              echo "nameserver $ns" >> /etc/resolv.conf
            done
          fi
          ;;
        deconfig)
          ip addr flush dev $interface 2>/dev/null
          ;;
      esac
    permissions: '0755'
bootcmd:
  - [sh, -c, "test -x /opt/udhcpc.sh && ! ip addr show eth0 | grep -q 'inet ' && busybox udhcpc -i eth0 -n -s /opt/udhcpc.sh >/dev/null 2>&1"]
  - [sh, -c, "grep -q 'nameserver' /etc/resolv.conf 2>/dev/null || echo 'nameserver 10.132.115.1' > /etc/resolv.conf"]
"""


def parse_ram_to_bytes(ram_str):
    ram_str = ram_str.strip().upper()
    if ram_str.endswith('GB') or ram_str.endswith('G'):
        return int(float(ram_str.replace('GB', '').replace('G', '')) * 1073741824)
    if ram_str.endswith('MB') or ram_str.endswith('M'):
        return int(float(ram_str.replace('MB', '').replace('M', '')) * 1048576)
    return int(float(ram_str) * 1073741824)


def parse_cpu_count(cpu_str):
    match = re.search(r'(\d+)', cpu_str)
    if match:
        return int(match.group(1))
    return 1


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if key != API_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


def nonkvm_state_dir(name):
    return os.path.join(os.environ.get('OMEGA_NONKVM_DIR', '/var/lib/omega-panel/nonkvm'), name)


def is_nonkvm(name):
    return os.path.isfile(os.path.join(nonkvm_state_dir(name), 'state.env'))


def nonkvm_action(name, action, extra=None, timeout=300):
    """Run the shared QEMU TCG helper for a non-KVM instance on this node."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'omega-nonkvm.sh')
    if not os.path.isfile(script):
        return 127, 'non-KVM helper script is missing on this node'
    try:
        proc = subprocess.run(['bash', script, action, '--name', name] + list(extra or []),
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout)
        return proc.returncode, (proc.stdout or '').strip()
    except subprocess.TimeoutExpired:
        return 124, 'non-KVM %s timed out' % action
    except Exception as exc:
        return 1, str(exc)


@app.before_request
def nonkvm_container_api():
    """Serve normal container API actions for software-emulated (non-KVM) VPS."""
    parts = request.path.strip('/').split('/')
    if len(parts) != 4 or parts[0] != 'api' or parts[1] != 'container':
        return None
    container_id, action = parts[2], parts[3]
    if action not in {'start', 'stop', 'restart', 'delete', 'status', 'nesting'} or not is_nonkvm(container_id):
        return None
    supplied = request.headers.get('X-API-Key') or request.args.get('api_key')
    if supplied != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    if action == 'nesting':
        data = request.get_json(silent=True) or {}
        enabled = str(data.get('nesting')).lower() in {'1', 'true', 'on', 'yes'}
        code, output = nonkvm_action(container_id, 'nesting', ['--state', 'on' if enabled else 'off'])
        if code != 0:
            return jsonify({'error': output[-600:] or 'nesting update failed'}), 500
        return jsonify({'status': 'ok', 'nesting': enabled})
    if action == 'status':
        code, output = nonkvm_action(container_id, 'status', timeout=60)
        state = 'running' if 'OMEGA_STATUS=running' in output else 'stopped'
        return jsonify({'status': 'ok', 'state': state, 'raw': output[-400:]})
    if action == 'restart':
        nonkvm_action(container_id, 'stop')
        action = 'start'
    code, output = nonkvm_action(container_id, action)
    if code != 0:
        return jsonify({'error': output[-600:] or ('%s failed' % action)}), 500
    if action == 'delete':
        return jsonify({'status': 'ok', 'state': 'deleted'})
    return jsonify({'status': 'ok', 'state': 'running' if action == 'start' else 'stopped'})



# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'node_type': node_type(),
        'incus_socket': os.path.exists(LXD_SOCKET),
        'kvm': os.path.exists('/dev/kvm'),
    })


@app.route('/api/debug/lxc_attach', methods=['POST'])
@require_api_key
def debug_lxc_attach():
    data = request.get_json()
    container_id = data.get('container_id', '')
    command = data.get('command', 'echo hello')

    code, resp = _lxd_request('POST', f'/1.0/instances/{container_id}/exec', data={
        'command': ['/bin/sh', '-c', command],
        'record-output': True,
        'environment': {'TERM': 'dumb'},
    }, timeout=30)

    result = {'exec_post_code': code, 'exec_post_resp': resp}

    if code == 200 and resp.get('type') == 'async':
        op_url = resp.get('operation', '')
        result['op_url'] = op_url
        import time as _t
        for _ in range(30):
            _t.sleep(1)
            o_code, o_resp = _lxd_request('GET', op_url)
            result['poll_code'] = o_code
            result['poll_resp'] = o_resp
            meta = o_resp.get('metadata', {})
            if meta.get('status') in ('Success', 'Failure'):
                result['op_status'] = meta.get('status')
                result['op_metadata'] = meta.get('metadata', {})
                output_raw = meta.get('metadata', {}).get('output', {})
                result['output_type'] = type(output_raw).__name__
                result['output_raw'] = output_raw
                if isinstance(output_raw, dict):
                    for fd, path in output_raw.items():
                        try:
                            import http.client as http
                            import socket

                            class _UC(http.HTTPConnection):
                                def __init__(self):
                                    super().__init__('localhost', timeout=10)

                                def connect(self):
                                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                                    self.sock.connect(LXD_SOCKET)

                            c = _UC()
                            c.request('GET', path)
                            r = c.getresponse()
                            body = r.read()
                            result[f'fd_{fd}_status'] = r.status
                            result[f'fd_{fd}_content'] = body.decode(errors='replace')[:500]
                        except Exception as e:
                            result[f'fd_{fd}_error'] = str(e)
                break
    return jsonify(result)


@app.route('/api/info')
@require_api_key
def node_info():
    import psutil
    disk = psutil.disk_usage('/')
    code, resp = _lxd_request('GET', '/1.0/instances')
    vps_count = 0
    if code == 200:
        paths = resp.get('metadata', [])
        for p in paths:
            name = p.rsplit('/', 1)[-1]
            c_code, c_resp = _lxd_request('GET', f'/1.0/instances/{name}')
            if c_code == 200 and c_resp.get('metadata', {}).get('status', '').lower() == 'running':
                vps_count += 1
    return jsonify({
        'status': 'ok',
        'cpu_percent': psutil.cpu_percent(interval=0.5),
        'ram_percent': psutil.virtual_memory().percent,
        'ram_total_gb': round(psutil.virtual_memory().total / 1073741824, 1),
        'disk_percent': round(disk.percent, 1),
        'disk_total_gb': round(disk.total / 1073741824, 1),
        'disk_used_gb': round(disk.used / 1073741824, 1),
        'vps_count': vps_count,
    })


@app.route('/api/containers')
@require_api_key
def list_containers():
    code, resp = _lxd_request('GET', '/1.0/instances')
    if code != 200:
        return jsonify({'error': 'Failed to list containers'}), 500
    paths = resp.get('metadata', [])
    result = []
    for p in paths:
        name = p.rsplit('/', 1)[-1]
        c_code, c_resp = _lxd_request('GET', f'/1.0/instances/{name}')
        status = c_resp.get('metadata', {}).get('status', '').lower() if c_code == 200 else 'unknown'
        result.append({'id': name, 'name': name, 'status': status})
    return jsonify({'containers': result})


@app.route('/api/container/create', methods=['POST'])
@require_api_key
def create_container():
    data = request.get_json()
    name = data.get('name')
    image = data.get('image', 'ubuntu-22.04')
    ram = data.get('ram')
    cpu = data.get('cpu')
    disk = data.get('disk', '10GB')
    vps_type = str(data.get('vps_type') or 'lxc').strip().lower()
    nesting = str(data.get('nesting', False)).strip().lower() in ('1', 'true', 'on', 'yes')
    if vps_type in ('vm', 'virtual-machine', 'virtualmachine', 'qemu'):
        vps_type = 'kvm'
    if vps_type not in ('lxc', 'kvm', 'nonkvm'):
        return jsonify({'error': 'Unsupported vps_type (lxc, kvm or nonkvm)'}), 400

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    if node_type() == 'lxc' and vps_type in ('kvm', 'nonkvm'):
        return jsonify({'error': "This node was installed as LXC-only. Re-run the node install with "
                                 "--type=kvm (or --type=incus) to create %s VPS." % vps_type}), 400

    if vps_type != 'nonkvm' and not os.path.exists(LXD_SOCKET):
        return jsonify({'error': 'Incus/LXD is not installed on this node (socket %s missing). '
                                 'Run: sudo bash scripts/omega-node-install.sh --type=%s' % (LXD_SOCKET, node_type())}), 500

    if vps_type == 'kvm' and not os.path.exists('/dev/kvm'):
        return jsonify({'error': 'KVM is not available on this node (/dev/kvm missing)'}), 400

    if vps_type == 'nonkvm':
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'omega-nonkvm.sh')
        if not os.path.isfile(script):
            return jsonify({'error': 'Non-KVM helper script is missing on this node'}), 500
        try:
            ram_mb = max(256, parse_ram_to_bytes(ram) // (1024 * 1024)) if ram else 2048
        except Exception:
            ram_mb = 2048
        try:
            disk_gb = str(int(float(str(disk).replace('GB', '').replace('gb', '').strip())))
        except Exception:
            disk_gb = '20'
        proc = subprocess.run(
            ['bash', script, 'create', '--name', name, '--alias', str(image),
             '--cpu', str(parse_cpu_count(cpu) if cpu else 2), '--ram-mb', str(ram_mb),
             '--disk-gb', disk_gb, '--nesting', 'on' if nesting else 'off'],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1200
        )
        output = proc.stdout or ''
        if proc.returncode != 0:
            return jsonify({'error': output[-900:] or 'Non-KVM creation failed'}), 500
        info = {}
        for line in output.splitlines():
            if '=' in line:
                key, _, value = line.partition('=')
                info[key.strip()] = value.strip()
        return jsonify({'status': 'ok', 'container_id': name, 'name': name,
                        'vps_type': 'nonkvm', 'nesting': nesting,
                        'ssh_port': info.get('OMEGA_SSH_PORT', ''),
                        'ssh_password': info.get('OMEGA_SSH_PASSWORD', '')})

    try:
        # Remove any stale instance with the same name
        _lxd_request('DELETE', f'/1.0/instances/{name}?force=1')

        disk_str = disk.strip().upper()
        instance_config = {
            'user.user-data': CLOUD_INIT,
            'security.nesting': 'true' if nesting else 'false',
        }
        if vps_type == 'lxc':
            instance_config['security.privileged'] = 'true'
        body = {
            'name': name,
            'source': _instance_source(image, vps_type),
            'config': instance_config,
            'devices': {
                'root': {'type': 'disk', 'path': '/', 'pool': 'default', 'size': disk_str},
            },
        }
        if vps_type == 'kvm':
            body['type'] = 'virtual-machine'
        if ram:
            body['config']['limits.memory'] = str(parse_ram_to_bytes(ram))
        if cpu:
            body['config']['limits.cpu'] = str(parse_cpu_count(cpu))

        code, resp = _lxd_request('POST', '/1.0/instances?wait=600', data=body, timeout=600)
        if code not in (200, 201, 202):
            return jsonify({'error': f"Failed to create: {resp.get('error', resp)}"}), 500

        if code in (201, 202) and isinstance(resp, dict) and resp.get('operation'):
            op_url = resp['operation']
            deadline = time.time() + 600
            while time.time() < deadline:
                o_code, o_resp = _lxd_request('GET', op_url)
                if o_code == 200 and isinstance(o_resp, dict):
                    meta = o_resp.get('metadata', {})
                    if meta.get('status') == 'Success':
                        break
                    if meta.get('status') == 'Failure':
                        return jsonify({'error': f'Create operation failed: {meta}'}), 500
                time.sleep(1)

        return jsonify({'status': 'ok', 'container_id': name, 'name': name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _instance_source(image, vps_type):
    """Image source for instance creation.

    Local aliases such as '22.04' point at cached container images, which cannot
    be used for virtual machines. For KVM we pull the VM variant from the
    public images remote instead.
    """
    image = str(image or '').strip()
    if vps_type != 'kvm':
        return {'type': 'image', 'alias': image}
    alias = image
    if ':' in alias:
        alias = alias.split(':', 1)[1]
    if re.fullmatch(r'\d{2}\.\d{2}', alias):
        alias = 'ubuntu/' + alias
    return {'type': 'image', 'mode': 'pull', 'protocol': 'simplestreams',
            'server': 'https://images.linuxcontainers.org', 'alias': alias}


@app.route('/api/container/<container_id>/nesting', methods=['POST'])
@require_api_key
def set_container_nesting(container_id):
    data = request.get_json(silent=True) or {}
    if 'nesting' not in data:
        return jsonify({'error': 'nesting (true/false) is required'}), 400
    enabled = str(data.get('nesting')).strip().lower() in ('1', 'true', 'on', 'yes')
    code, resp = _lxd_request('PATCH', f'/1.0/instances/{container_id}', data={
        'config': {'security.nesting': 'true' if enabled else 'false'}})
    if code not in (200, 201, 202):
        message = resp.get('error', resp) if isinstance(resp, dict) else resp
        return jsonify({'error': f'Failed to update nesting: {message}'}), 500
    return jsonify({'status': 'ok', 'nesting': enabled})


@app.route('/api/container/<container_id>/start', methods=['POST'])
@require_api_key
def start_container(container_id):
    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404
        _lxd_request('PUT', f'/1.0/instances/{container_id}/state', data={'action': 'start'})
        for _ in range(30):
            if lxc_status(container_id) == 'running':
                break
            time.sleep(2)
        lxc_fix_networking(container_id)
        return jsonify({'status': 'ok', 'state': 'running'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/stop', methods=['POST'])
@require_api_key
def stop_container(container_id):
    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404
        if status == 'stopped':
            return jsonify({'status': 'ok', 'state': 'stopped'})
        _lxd_request('PUT', f'/1.0/instances/{container_id}/state',
                     data={'action': 'stop', 'timeout': 30})
        return jsonify({'status': 'ok', 'state': 'stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/restart', methods=['POST'])
@require_api_key
def restart_container(container_id):
    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404
        _lxd_request('PUT', f'/1.0/instances/{container_id}/state', data={'action': 'restart'})
        time.sleep(2)
        lxc_fix_networking(container_id)
        return jsonify({'status': 'ok', 'state': lxc_status(container_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/delete', methods=['POST'])
@require_api_key
def delete_container(container_id):
    try:
        status = lxc_status(container_id)
        if status in ('running', 'frozen'):
            _lxd_request('PUT', f'/1.0/instances/{container_id}/state?wait=600',
                         data={'action': 'stop', 'timeout': 60})

        code, resp = _lxd_request('DELETE', f'/1.0/instances/{container_id}?wait=600', timeout=600)
        if code in (201, 202) and isinstance(resp, dict) and resp.get('operation'):
            op_url = resp['operation']
            import time as _time
            deadline = _time.time() + 600
            while _time.time() < deadline:
                o_code, o_resp = _lxd_request('GET', op_url, timeout=600)
                if o_code == 200 and isinstance(o_resp, dict):
                    meta = o_resp.get('metadata', {})
                    if meta.get('status') == 'Success':
                        break
                    if meta.get('status') == 'Failure':
                        raise Exception(f'LXD destroy failed: {meta}')
                _time.sleep(2)

        # Wait until the instance is really gone
        import time as _time
        for i in range(30):
            c_code, _ = _lxd_request('GET', f'/1.0/instances/{container_id}')
            if c_code == 404:
                break
            _time.sleep(1)

        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/status')
@require_api_key
def container_status(container_id):
    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404
        return jsonify({'status': 'ok', 'state': status, 'id': container_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/stats')
@require_api_key
def container_stats(container_id):
    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404

        stats = {
            'cpu_percent': 0.0,
            'memory_used': 0,
            'memory_limit': 0,
            'memory_percent': 0.0,
            'net_rx': 0,
            'net_tx': 0,
            'pids': 0,
        }
        if status != 'running':
            return jsonify(stats)

        code, resp = _lxd_request('GET', f'/1.0/instances/{container_id}/state')
        if code == 200 and resp.get('metadata'):
            meta = resp['metadata']
            mem = meta.get('memory', {})
            stats['memory_used'] = mem.get('usage', 0)
            stats['memory_limit'] = mem.get('total', 0)

            if stats['memory_limit'] == 0:
                c_code, c_resp = _lxd_request('GET', f'/1.0/instances/{container_id}')
                if c_code == 200 and isinstance(c_resp, dict):
                    c_meta = c_resp.get('metadata', c_resp)
                    ml_raw = c_meta.get('config', {}).get('limits.memory', '')
                    if ml_raw:
                        ml = _parse_mem_limit(ml_raw)
                        if ml:
                            stats['memory_limit'] = ml

            net = meta.get('network', {}).get('eth0', {}).get('counters', {})
            stats['net_rx'] = net.get('bytes_received', 0)
            stats['net_tx'] = net.get('bytes_sent', 0)

            # CPU % from `top`
            try:
                exit_code, top_out = lxc_attach(container_id, 'top -bn1 | head -5', timeout=5)
                if isinstance(top_out, bytes):
                    top_out = top_out.decode('utf-8', errors='ignore')
                for line in str(top_out).split('\n'):
                    if '%Cpu' in line or '%cpu' in line.lower():
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if 'us' in p and i > 0:
                                try:
                                    stats['cpu_percent'] = round(float(parts[i - 1]), 1)
                                except Exception:
                                    pass
                                break
                        break
            except Exception:
                pass

            # Process count
            try:
                _, ps_out = lxc_attach(container_id, 'ps aux | wc -l', timeout=5)
                if isinstance(ps_out, bytes):
                    ps_out = ps_out.decode('utf-8', errors='ignore')
                stats['pids'] = max(0, int(str(ps_out).strip()) - 1)
            except Exception:
                pass

        if stats['memory_limit'] <= 0:
            code2, resp2 = _lxd_request('GET', f'/1.0/instances/{container_id}')
            if code2 == 200:
                limit_str = resp2.get('metadata', {}).get('config', {}).get('limits.memory', '')
                if limit_str.isdigit():
                    stats['memory_limit'] = int(limit_str)

        if stats['memory_limit'] > 0:
            stats['memory_percent'] = round(stats['memory_used'] / stats['memory_limit'] * 100, 1)

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/regen-ssh', methods=['POST'])
@require_api_key
def regen_ssh(container_id):
    """(Re)start an sshx session inside the container and return its share URL."""
    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404
        if status != 'running':
            _lxd_request('PUT', f'/1.0/instances/{container_id}/state?wait=600',
                         data={'action': 'start'})
            lxc_fix_networking(container_id)
            time.sleep(2)

        lxc_attach(container_id,
                   'pkill sshx 2>/dev/null; killall sshx 2>/dev/null; rm -f /tmp/sshx_out.log; true')
        # Install sshx if it is missing
        lxc_attach(container_id,
                   'command -v sshx >/dev/null 2>&1 || '
                   '(command -v curl >/dev/null 2>&1 && curl -sSf https://sshx.io/get | sh || '
                   '(command -v wget >/dev/null 2>&1 && wget -qO- https://sshx.io/get | sh))',
                   timeout=300)
        rc, output = lxc_attach(container_id,
                                'pkill sshx 2>/dev/null; rm -f /tmp/sshx_out.log; '
                                'nohup sshx > /tmp/sshx_out.log 2>&1 & '
                                'sleep 10; cat /tmp/sshx_out.log 2>/dev/null')
        cleaned = strip_ansi(output.decode('utf-8', errors='ignore'))
        match = re.search(r'https://sshx\.io/s/[a-zA-Z0-9#]+', cleaned)
        if match:
            return jsonify({'status': 'ok', 'ssh_command': match.group(0), 'method': 'sshx'})
        return jsonify({'error': 'sshx failed to start'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/exec', methods=['POST'])
@require_api_key
def exec_in_container(container_id):
    data = request.get_json()
    command = data.get('command')
    if not command:
        return jsonify({'error': 'Command is required'}), 400
    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404
        exit_code, output = lxc_attach(container_id, command)
        return jsonify({
            'status': 'ok',
            'output': output.decode('utf-8', errors='replace'),
            'exit_code': exit_code,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/files', methods=['POST'])
@require_api_key
def container_files(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '/')
        exit_code, output = lxc_attach(container_id, f'ls -la {shlex.quote(path)}')
        files = []
        if exit_code == 0:
            for line in output.decode(errors='replace').strip().split('\n')[1:]:
                parts = line.split(None, 8)
                if len(parts) >= 9 and parts[8] not in ('.', '..'):
                    files.append({
                        'name': parts[8],
                        'is_dir': parts[0].startswith('d'),
                        'size': parts[4],
                        'permissions': parts[0],
                    })
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/file_read', methods=['POST'])
@require_api_key
def container_file_read(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '')
        exit_code, output = lxc_attach(container_id, f'cat {shlex.quote(path)}')
        return jsonify({'content': output.decode(errors='replace'), 'success': exit_code == 0})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/file_write', methods=['POST'])
@require_api_key
def container_file_write(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '')
        content = data.get('content', '')
        file_data = content.encode()

        import socket

        class _UC(http.HTTPConnection):
            def __init__(self):
                super().__init__('localhost', timeout=30)

            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(LXD_SOCKET)

        conn = _UC()
        try:
            conn.request('POST',
                         f'/1.0/instances/{container_id}/files?path={path}&uid=0&gid=0&mode=0644',
                         body=file_data,
                         headers={'Content-Type': 'application/octet-stream'})
            resp = conn.getresponse()
            resp.read()
            if resp.status in (200, 201, 204):
                return jsonify({'success': True})
            return jsonify({'error': f'LXD write failed with status {resp.status}'}), 500
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/top')
@require_api_key
def container_top(container_id):
    try:
        exit_code, output = lxc_attach(container_id, 'ps aux --sort=-%cpu')
        processes = []
        if exit_code == 0:
            for line in output.decode(errors='replace').strip().split('\n')[1:]:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({
                        'pid': parts[1],
                        'user': parts[0],
                        'cpu': parts[2],
                        'mem': parts[3],
                        'command': parts[10],
                    })
        return jsonify({'processes': processes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/upload', methods=['POST'])
@require_api_key
def container_upload(container_id):
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file'}), 400
        f = request.files['file']
        path = request.form.get('path', '/')
        file_data = f.read()
        dest = path if path.endswith(f.filename) else f"{path.rstrip('/')}/{f.filename}"

        import socket

        class _UC(http.HTTPConnection):
            def __init__(self):
                super().__init__('localhost', timeout=120)

            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(LXD_SOCKET)

        conn = _UC()
        try:
            conn.request('POST',
                         f'/1.0/instances/{container_id}/files?path={dest}&uid=0&gid=0&mode=0644',
                         body=file_data,
                         headers={'Content-Type': 'application/octet-stream'})
            resp = conn.getresponse()
            resp.read()
            if resp.status in (200, 201, 204):
                return jsonify({'success': True})
            return jsonify({'error': f'LXD upload failed with status {resp.status}'}), 500
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/backup', methods=['POST'])
@require_api_key
def container_backup(container_id):
    """Backups are implemented as Incus snapshots."""
    try:
        data = request.get_json()
        name = data.get('name', f'backup-{int(time.time())}')
        code, resp = _lxd_request('POST', f'/1.0/instances/{container_id}/snapshots',
                                  data={'name': name, 'stateful': False})
        if code not in (200, 201, 202):
            return jsonify({'error': resp.get('error', f'Snapshot failed: {code}')}), 500
        return jsonify({'success': True, 'image_tag': name, 'size_mb': 0})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/restore', methods=['POST'])
@require_api_key
def container_restore(container_id):
    try:
        data = request.get_json()
        snapshot = data.get('image', '')
        code, resp = _lxd_request('PUT', f'/1.0/instances/{container_id}',
                                  data={'restore': snapshot})
        if code not in (200, 202):
            return jsonify({'error': resp.get('error', f'Restore failed: {code}')}), 500
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/snapshots')
@require_api_key
def container_snapshots(container_id):
    try:
        code, resp = _lxd_request('GET', f'/1.0/instances/{container_id}/snapshots?recursion=1')
        snaps = []
        if code == 200:
            for s in resp.get('metadata', []):
                snaps.append({
                    'name': s.get('name', ''),
                    'created_at': s.get('created_at', ''),
                    'stateful': s.get('stateful', False),
                })
        return jsonify({'snapshots': snaps})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/snapshot/<snap_name>', methods=['DELETE'])
@require_api_key
def container_delete_snapshot(container_id, snap_name):
    try:
        code, resp = _lxd_request('DELETE', f'/1.0/instances/{container_id}/snapshots/{snap_name}')
        if code not in (200, 204):
            return jsonify({'error': resp.get('error', f'Delete failed: {code}')}), 500
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/update', methods=['POST'])
@require_api_key
def container_update(container_id):
    try:
        data = request.get_json() or {}
        ram = data.get('ram', '')
        cpu = data.get('cpu', '')
        disk = data.get('disk', '')
        import subprocess
        if ram:
            subprocess.run(['incus', 'config', 'set', container_id, 'limits.memory=' + ram],
                           timeout=30, capture_output=True)
        if cpu:
            subprocess.run(['incus', 'config', 'set', container_id, 'limits.cpu=' + cpu],
                           timeout=30, capture_output=True)
        if disk:
            subprocess.run(['incus', 'config', 'device', 'set', container_id, 'root', 'size=' + disk],
                           timeout=30, capture_output=True)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/download', methods=['POST'])
@require_api_key
def container_download(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '')
        import base64
        import http.client as http
        import socket

        class _UC(http.HTTPConnection):
            def __init__(self):
                super().__init__('localhost', timeout=30)

            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(LXD_SOCKET)

        c = _UC()
        c.request('GET', f'/1.0/instances/{container_id}/files?path={path}')
        r = c.getresponse()
        data = r.read()
        if r.status != 200:
            return jsonify({'error': f'Download failed: {r.status}'}), 500
        return jsonify({'data': base64.b64encode(data).decode()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Port forwarding (socat) and public tunnels (serveo)
# ---------------------------------------------------------------------------

@app.route('/api/socat/start', methods=['POST'])
@require_api_key
def socat_start():
    data = request.get_json()
    listen_ip = data.get('listen_ip')
    port = data.get('port')
    container_ip = data.get('container_ip')
    container_port = data.get('container_port', port)

    if not all([listen_ip, port, container_ip]):
        return jsonify({'error': 'listen_ip, port, and container_ip are required'}), 400

    try:
        import signal
        pidfile = f'/tmp/socat_{port}.pid'
        logfile = f'/tmp/socat_{port}.log'

        # Kill a previous forwarder on the same port
        if os.path.exists(pidfile):
            try:
                with open(pidfile) as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(0.5)
            except Exception:
                pass

        proc = subprocess.Popen(
            ['socat',
             f'TCP-LISTEN:{port},bind=0.0.0.0,reuseaddr,fork',
             f'TCP:{container_ip}:{container_port}'],
            stdout=open(logfile, 'w'),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        with open(pidfile, 'w') as f:
            f.write(str(proc.pid))
        return jsonify({'status': 'ok', 'pid': proc.pid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/socat/stop', methods=['POST'])
@require_api_key
def socat_stop():
    data = request.get_json()
    port = data.get('port')
    pid = data.get('pid')

    if not port:
        return jsonify({'error': 'port is required'}), 400

    try:
        import signal
        if pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
        pidfile = f'/tmp/socat_{port}.pid'
        if os.path.exists(pidfile):
            try:
                with open(pidfile) as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, signal.SIGTERM)
            except Exception:
                pass
            try:
                os.remove(pidfile)
            except Exception:
                pass
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/serveo/start', methods=['POST'])
@require_api_key
def serveo_start():
    data = request.get_json()
    container_id = data.get('container_id')
    local_port = data.get('local_port', 0)

    if not container_id or not isinstance(local_port, int) or not (1 <= local_port <= 65535):
        return jsonify({'error': 'container_id and local_port are required'}), 400

    try:
        status = lxc_status(container_id)
        if status == 'not_found':
            return jsonify({'error': 'Container not found'}), 404
        if status != 'running':
            return jsonify({'error': 'Container must be running'}), 400

        serveo_cmd = f'ssh -o StrictHostKeyChecking=no -R 80:localhost:{local_port} serveo.net'
        lxc_attach(container_id,
                   f'bash -c "nohup {serveo_cmd} > /tmp/serveo_{local_port}.log 2>&1 &"')

        serveo_url = None
        for _ in range(15):
            time.sleep(2)
            rc, raw = lxc_attach(container_id, f'cat /tmp/serveo_{local_port}.log')
            log_output = raw.decode('utf-8', errors='replace')
            for line in log_output.split('\n'):
                clean = strip_ansi(line.strip())
                if 'serveousercontent.com' in clean or 'serveo.net' in clean:
                    match = re.search(r'https?://\S+serveo\S+', clean)
                    if match:
                        serveo_url = match.group(0).rstrip('.')
                        break
            if serveo_url:
                break

        if not serveo_url:
            return jsonify({'error': 'Serveo did not return a URL. Tunnel may have failed to start.'}), 500
        return jsonify({'status': 'ok', 'serveo_url': serveo_url, 'port': local_port})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/serveo/stop', methods=['POST'])
@require_api_key
def serveo_stop():
    data = request.get_json()
    container_id = data.get('container_id')
    local_port = data.get('local_port', 0)

    if not container_id or not isinstance(local_port, int) or not (1 <= local_port <= 65535):
        return jsonify({'error': 'container_id and local_port are required'}), 400

    try:
        lxc_attach(container_id, f'pkill -f "ssh.*localhost:{local_port}.*serveo.net"', timeout=10)
        lxc_attach(container_id, f'rm -f /tmp/serveo_{local_port}.log', timeout=5)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/ip', methods=['GET'])
@require_api_key
def get_container_ip(container_id):
    try:
        code, resp = _lxd_request('GET', f'/1.0/instances/{container_id}/state')
        if code != 200 or not resp.get('metadata'):
            return jsonify({'error': 'Container not found'}), 404
        addrs = resp['metadata'].get('network', {}).get('eth0', {}).get('addresses', [])
        for a in addrs:
            if a.get('family') == 'inet' and a.get('scope') == 'global':
                return jsonify({'ip': a['address']})
        return jsonify({'ip': ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

@app.route('/api/image/<image_tag>/export')
@require_api_key
def export_image(image_tag):
    try:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix='.tar')
        temp.close()
        stdout, stderr, rc = _lxc_run(['image', 'export', image_tag, temp.name[:-4]], timeout=120)
        if rc != 0:
            os.unlink(temp.name)
            return jsonify({'error': stderr}), 500

        tar_path = temp.name
        if not os.path.exists(tar_path):
            tar_path = temp.name + '.tar'
            if not os.path.exists(tar_path):
                return jsonify({'error': 'Export failed'}), 500

        size = os.path.getsize(tar_path)

        def generate():
            with open(tar_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
            try:
                os.unlink(tar_path)
            except Exception:
                pass

        from flask import Response
        return Response(generate(), mimetype='application/x-tar', headers={
            'Content-Disposition': f'attachment; filename={image_tag}.tar',
            'Content-Length': str(size),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/image/import', methods=['POST'])
@require_api_key
def import_image():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        f = request.files['file']
        image_tag = request.form.get('tag', f'imported-{int(time.time())}')
        temp = tempfile.NamedTemporaryFile(delete=False, suffix='.tar')
        temp.write(f.read())
        temp.close()
        stdout, stderr, rc = _lxc_run(['image', 'import', temp.name, '--alias', image_tag],
                                      timeout=120)
        os.unlink(temp.name)
        if rc != 0:
            return jsonify({'error': stderr}), 500
        return jsonify({'status': 'ok', 'image_tag': image_tag})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/image/<image_tag>/delete', methods=['POST'])
@require_api_key
def delete_image(image_tag):
    try:
        stdout, stderr, rc = _lxc_run(['image', 'delete', image_tag], timeout=30)
        if rc != 0:
            return jsonify({'error': stderr}), 500
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Web terminal (PTY + Server-Sent Events)
# ---------------------------------------------------------------------------

terminal_sessions = {}


@app.route('/api/container/<container_id>/terminal/session', methods=['POST'])
@require_api_key
def node_terminal_create_session(container_id):
    cols = request.args.get('cols', 80, type=int)
    rows = request.args.get('rows', 24, type=int)
    try:
        master_fd, slave_fd = pty.openpty()
        try:
            import fcntl
            import termios
            win = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, win)
        except Exception:
            pass
        proc = subprocess.Popen(
            ['incus', 'exec', container_id, '--', '/bin/sh', '-c',
             'TERM=xterm-256color exec /bin/bash'],
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True,
        )
        os.close(slave_fd)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    session_id = str(uuid.uuid4())
    terminal_sessions[session_id] = {
        'master_fd': master_fd,
        'proc': proc,
        'container_id': container_id,
    }

    def _cleanup():
        proc.wait()
        time.sleep(0.3)
        try:
            os.close(master_fd)
        except Exception:
            pass
        terminal_sessions.pop(session_id, None)

    threading.Thread(target=_cleanup, daemon=True).start()
    return jsonify({'session_id': session_id})


@app.route('/api/container/<container_id>/terminal/input', methods=['POST'])
@require_api_key
def node_terminal_input(container_id):
    session_id = request.args.get('session')
    sess = terminal_sessions.get(session_id)
    if not sess:
        return jsonify({'error': 'session not found'}), 404
    data = request.get_data(as_text=True)
    try:
        os.write(sess['master_fd'], data.encode())
        return '', 204
    except OSError:
        return jsonify({'error': 'terminal closed'}), 410


@app.route('/api/container/<container_id>/terminal/resize', methods=['POST'])
@require_api_key
def node_terminal_resize(container_id):
    session_id = request.args.get('session')
    sess = terminal_sessions.get(session_id)
    if not sess:
        return jsonify({'error': 'session not found'}), 404
    cols = request.args.get('cols', 80, type=int)
    rows = request.args.get('rows', 24, type=int)
    try:
        import fcntl
        import termios
        win = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(sess['master_fd'], termios.TIOCSWINSZ, win)
    except Exception:
        pass
    return '', 204


@app.route('/api/container/<container_id>/terminal/stream')
@require_api_key
def node_terminal_stream(container_id):
    session_id = request.args.get('session')
    sess = terminal_sessions.get(session_id)
    if not sess:
        return jsonify({'error': 'session not found'}), 404

    def generate():
        mfd = sess['master_fd']
        proc = sess['proc']
        last_keepalive = time.time()
        while True:
            timeout = max(0, 15 - (time.time() - last_keepalive))
            r, _, _ = select.select([mfd], [], [], timeout)
            if r:
                try:
                    data = os.read(mfd, 4096)
                    if not data:
                        break
                    yield 'data: ' + base64.b64encode(data).decode() + '\n\n'
                except OSError:
                    break
            if proc.poll() is not None:
                try:
                    data = os.read(mfd, 4096)
                    if data:
                        yield 'data: ' + base64.b64encode(data).decode() + '\n\n'
                except OSError:
                    pass
                break
            if time.time() - last_keepalive >= 15:
                yield ': keepalive\n\n'
                last_keepalive = time.time()
        yield 'data: __TERMINAL_CLOSED__\n\n'

    resp = Response(generate(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Connection'] = 'keep-alive'
    return resp


if __name__ == '__main__':
    print('=== VPS Manager Node Agent (LXC) ===')
    print(f'API Key: {API_KEY}')
    print(f'Listening on port {LISTEN_PORT}')
    print("Save this key in your panel's node settings!")
    print('=====================================')
    app.run(host='0.0.0.0', port=LISTEN_PORT)
