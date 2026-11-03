import os
import pty
import random
import select
import shlex
import string
import struct
import subprocess
import sqlite3
import hashlib
import secrets
import uuid
import time
import json
import io
import tempfile
import uuid
import threading
import base64
import psutil
import zoneinfo
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import http.client
import socket as _socket
import re
LXC_IMAGE_MAP = {'ubuntu-22.04': '22.04', 'ubuntu-24.04': '24.04', 'ubuntu-26.04': '26.04', 'ubuntu:22.04': '22.04', 'ubuntu:24.04': '24.04', 'ubuntu:26.04': '26.04'}
def _lxd_request(method, path, data=None, timeout=30):
    class _UnixConn(http.client.HTTPConnection):
        def __init__(self):
            super().__init__('localhost')
        def connect(self):
            self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self.sock.connect('/var/lib/incus/unix.socket')
    conn = _UnixConn()
    body = json.dumps(data).encode() if data else None
    headers = {'Content-Type': 'application/json'} if body else {}
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        resp_body = resp.read()
        try:
            return (resp.status, json.loads(resp_body))
        except:
            return (resp.status, resp_body)
    except Exception as e:
        return (500, {'error': str(e)})
    finally:
        try:
            conn.close()
        except:
            pass
def _lxc_fix_networking(name):
    try:
        import subprocess as _sp
        _sp.run(['incus', 'exec', name, '--', 'sh', '-c', """cat > /opt/udhcpc.sh << 'SCRIPT'
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
SCRIPT
chmod 755 /opt/udhcpc.sh"""], timeout=30, capture_output=True)
        for _ in range(15):
            r = _sp.run(['incus', 'exec', name, '--', 'ip', 'addr', 'show', 'eth0'], capture_output=True, timeout=10)
            if b'inet ' in r.stdout:
                break
            _sp.run(['incus', 'exec', name, '--', 'busybox', 'udhcpc', '-i', 'eth0', '-n', '-s', '/opt/udhcpc.sh'], timeout=15, capture_output=True)
            time.sleep(2)
        _sp.run(['incus', 'exec', name, '--', 'sh', '-c', "grep -q 'nameserver' /etc/resolv.conf 2>/dev/null || echo 'nameserver 10.132.115.1' > /etc/resolv.conf"], timeout=10, capture_output=True)
    except:
        pass
def _parse_ram_to_bytes(ram_str):
    if not ram_str:
        return 2147483648
    ram_str = str(ram_str).strip().upper()
    if 'GB' in ram_str:
        return int(float(ram_str.replace('GB', '').strip()) * 1073741824)
    if 'MB' in ram_str:
        return int(float(ram_str.replace('MB', '').strip()) * 1048576)
    return 2147483648
def _parse_cpu_count(cpu_str):
    if not cpu_str:
        return 1
    m = re.search('(\\d+)', str(cpu_str))
    if m:
        return int(m.group(1))
    return 1
def lxc_create(name, os_type='ubuntu-22.04', ram='2GB', cpu='1 vCPU', disk='20GB'):
    ram_bytes = _parse_ram_to_bytes(ram)
    cpu_count = _parse_cpu_count(cpu)
    try:
        disk_bytes = int(float(str(disk).replace('GB', '').strip()) * 1073741824)
    except:
        disk_bytes = 21474836480
    if os_type.startswith('backup-'):
        source = {'type': 'image', 'alias': os_type}
    else:
        alias = LXC_IMAGE_MAP.get(os_type, LXC_IMAGE_MAP.get('vps-' + os_type, None))
        if not alias:
            alias = '22.04' if ':' not in os_type else os_type
        source = {'type': 'image', 'alias': alias}
    config = {'source': source, 'profiles': ['default'], 'name': name, 'config': {'limits.memory': str(ram_bytes), 'limits.cpu': str(cpu_count), 'security.privileged': 'true'}, 'devices': {'root': {'type': 'disk', 'path': '/', 'pool': 'default', 'size': str(disk_bytes)}}}
    code, resp = _lxd_request('POST', '/1.0/instances?wait=600', data=config)
    if code not in (200, 201, 202):
        raise Exception(f"Failed to create LXC container: {resp.get('error', '') if isinstance(resp, dict) else resp}")
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
                    raise Exception(f"LXD create operation failed: {meta}")
            time.sleep(1)
    _lxc_fix_networking(name)
    return name
def lxc_start(name):
    _lxd_request('PUT', f"/1.0/instances/{name}/state?wait=600", data={'action': 'start'})
    time.sleep(2)
    _lxc_fix_networking(name)
def lxc_stop(name, timeout=60):
    code, resp = _lxd_request('PUT', f"/1.0/instances/{name}/state?wait=600", data={'action': 'stop', 'timeout': timeout})
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
                    err = str(meta.get('err', ''))
                    if 'already stopped' in err.lower():
                        break
                    raise Exception(f"LXD stop failed: {meta}")
            time.sleep(2)
    time.sleep(1)
def lxc_restart(name):
    _lxd_request('PUT', f"/1.0/instances/{name}/state?wait=600", data={'action': 'restart', 'timeout': 60})
    time.sleep(3)
    _lxc_fix_networking(name)
def lxc_destroy(name):
    code, resp = _lxd_request('DELETE', f"/1.0/instances/{name}?wait=600")
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
                    raise Exception(f"LXD destroy failed: {meta}")
            time.sleep(2)
    for i in range(30):
        c_code, _ = _lxd_request('GET', f"/1.0/instances/{name}")
        if c_code == 404:
            return
        time.sleep(1)
def lxc_status(name):
    code, resp = _lxd_request('GET', f"/1.0/instances/{name}/state?recursion=1")
    if code == 200 and isinstance(resp, dict):
        meta = resp.get('metadata', resp)
        return meta.get('status', 'unknown').lower()
    return 'unknown'
def lxc_get_ip(name):
    code, resp = _lxd_request('GET', f"/1.0/instances/{name}/state?recursion=1")
    if code == 200 and isinstance(resp, dict):
        meta = resp.get('metadata', resp)
        net = meta.get('network', {})
        for iface, data in net.items():
            if iface != 'lo':
                addrs = data.get('addresses', [])
                for a in addrs:
                    if a.get('family') == 'inet':
                        return a.get('address', '')
    return ''
def _parse_mem_limit(val):
    val = val.strip()
    m = re.match('^(\\d+)([KMGTP]i?B?|B)?$', val, re.IGNORECASE)
    if not m:
        return
    num = int(m.group(1))
    unit = (m.group(2) or '').upper()
    multipliers = {'': 1, 'B': 1, 'K': 1024, 'KB': 1024, 'KIB': 1024, 'M': 1048576, 'MB': 1048576, 'MIB': 1048576, 'G': 1073741824, 'GB': 1073741824, 'GIB': 1073741824, 'T': 1099511627776, 'TB': 1099511627776, 'TIB': 1099511627776, 'P': 1125899906842624, 'PB': 1125899906842624, 'PIB': 1125899906842624}
    mult = multipliers.get(unit)
    if mult is None:
        return
    return num * mult
def lxc_get_stats(name):
    code, resp = _lxd_request('GET', f"/1.0/instances/{name}/state?recursion=1")
    stats = {'cpu_percent': 0.0, 'memory_used': 0, 'memory_limit': 0, 'memory_percent': 0.0, 'net_rx': 0, 'net_tx': 0, 'pids': 0}
    if code != 200 or not isinstance(resp, dict):
        return stats
    meta = resp.get('metadata', resp)
    mem = meta.get('memory', {})
    stats['memory_used'] = mem.get('usage', 0)
    c_code, c_resp = _lxd_request('GET', f"/1.0/instances/{name}")
    if c_code == 200 and isinstance(c_resp, dict):
        c_meta = c_resp.get('metadata', c_resp)
        mem_limit = c_meta.get('config', {}).get('limits.memory', '')
        if mem_limit:
            ml = _parse_mem_limit(mem_limit)
            if ml:
                stats['memory_limit'] = ml
    if stats['memory_limit'] == 0:
        stats['memory_limit'] = mem.get('total', 0)
    if stats['memory_limit'] == 0:
        stats['memory_limit'] = mem.get('usage_in_bytes', 0)
    if stats['memory_limit'] > 0:
        stats['memory_percent'] = round(stats['memory_used'] / stats['memory_limit'] * 100, 2)
    try:
        exit_code, top_out = lxc_attach(name, 'top -bn1 | head -5', timeout=5)
        if isinstance(top_out, bytes):
            top_out = top_out.decode('utf-8', errors='ignore')
        for line in str(top_out).split('\n'):
            if '%Cpu' in line or '%cpu' in line.lower():
                parts = line.split()
                for i, p in enumerate(parts):
                    if 'us' in p and i > 0:
                        try:
                            stats['cpu_percent'] = round(float(parts[i - 1]), 1)
                        except:
                            pass
                        break
                break
        _, ps_out = lxc_attach(name, 'ps aux | wc -l', timeout=5)
        if isinstance(ps_out, bytes):
            ps_out = ps_out.decode('utf-8', errors='ignore')
        try:
            stats['pids'] = int(str(ps_out).strip()) - 1
        except:
            pass
    except:
        pass
    net = meta.get('network', {})
    for iface, data in net.items():
        if iface != 'lo':
            stats['net_rx'] += data.get('counters', {}).get('bytes_received', 0)
            stats['net_tx'] += data.get('counters', {}).get('bytes_sent', 0)
    return stats
def lxc_info(name):
    code, resp = _lxd_request('GET', f"/1.0/instances/{name}/state")
    if code != 200:
        return
    if isinstance(resp, dict):
        return resp
def lxc_snapshot_create(name, snap_name):
    code, resp = _lxd_request('POST', f"/1.0/instances/{name}/snapshots", data={'name': snap_name, 'stateful': False})
    if code not in (200, 201, 202):
        raise Exception(f"Failed to create snapshot: {resp.get('error', '') if isinstance(resp, dict) else resp}")
    return snap_name
def lxc_snapshot_list(name):
    code, resp = _lxd_request('GET', f"/1.0/instances/{name}/snapshots")
    if code == 200 and isinstance(resp, dict):
        return [p.split('/')[-1] for p in resp.get('metadata', [])]
    return []
def lxc_snapshot_restore(name, snap_name):
    _lxd_request('PUT', f"/1.0/instances/{name}/state", data={'action': 'stop'})
    time.sleep(2)
    code, resp = _lxd_request('PUT', f"/1.0/instances/{name}", data={'restore': f"/1.0/instances/{name}/snapshots/{snap_name}"})
    if code not in (200, 202):
        raise Exception(f"Failed to restore snapshot: {resp.get('error', '') if isinstance(resp, dict) else resp}")
def lxc_snapshot_delete(name, snap_name):
    _lxd_request('DELETE', f"/1.0/instances/{name}/snapshots/{snap_name}")
def lxc_get_version():
    code, resp = _lxd_request('GET', '/1.0')
    if code == 200 and isinstance(resp, dict):
        return resp.get('metadata', {}).get('environment', {}).get('server_version', 'unknown')
    return 'unknown'
def lxc_is_available():
    try:
        code, _ = _lxd_request('GET', '/1.0')
        return code == 200
    except:
        return False
def lxc_copy_file_to_container(name, container_path, file_data):
    class _UC(http.client.HTTPConnection):
        def __init__(self):
            super().__init__('localhost', timeout=60)
        def connect(self):
            self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self.sock.connect('/var/lib/incus/unix.socket')
    conn = _UC()
    try:
        conn.request('POST', f"/1.0/instances/{name}/files?path={container_path}&uid=0&gid=0&mode=0644", body=file_data, headers={'Content-Type': 'application/octet-stream'})
        conn.getresponse()
    finally:
        conn.close()
def lxc_copy_file_from_container(name, container_path):
    code, resp = _lxd_request('GET', f"/1.0/instances/{name}/files?path={container_path}")
    if code == 200:
        if isinstance(resp, bytes):
            return resp
        if isinstance(resp, str):
            return resp.encode()
        return b''
    raise Exception(f"Failed to read file: {resp}")
def lxc_put_archive(name, path, data):
    class _UC(http.client.HTTPConnection):
        def __init__(self):
            super().__init__('localhost', timeout=120)
        def connect(self):
            self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self.sock.connect('/var/lib/incus/unix.socket')
    conn = _UC()
    try:
        conn.request('POST', f"/1.0/instances/{name}/files?path={path}&uid=0&gid=0&mode=0644", body=data, headers={'Content-Type': 'application/octet-stream'})
        conn.getresponse()
    finally:
        conn.close()
def lxc_get_archive(name, path):
    code, resp = _lxd_request('GET', f"/1.0/instances/{name}/files?path={path}")
    if code == 200:
        if isinstance(resp, bytes):
            return resp
        if isinstance(resp, str):
            return resp.encode()
        return b''
    raise Exception(f"Failed to get archive: {resp}")
def lxc_list():
    code, resp = _lxd_request('GET', '/1.0/instances')
    if code == 200 and isinstance(resp, dict):
        return [p.split('/')[-1] for p in resp.get('metadata', [])]
    return []
def lxc_list_all():
    code, resp = _lxd_request('GET', '/1.0/instances?recursion=1')
    if code == 200 and isinstance(resp, dict):
        return resp.get('metadata', [])
    return []
def lxc_attach(name, command, timeout=60, **kwargs):
    code, resp = _lxd_request('POST', f"/1.0/instances/{name}/exec", data={'command': ['/bin/sh', '-c', command], 'record-output': True, 'environment': {'TERM': 'dumb'}}, timeout=timeout)
    if code not in (200, 201, 202) or resp.get('type') != 'async':
        return (1, b'')
    op_url = resp.get('operation', '')
    if not op_url:
        return (1, b'')
    deadline = time.time() + timeout
    while time.time() < deadline:
        o_code, o_resp = _lxd_request('GET', op_url)
        if o_code == 200:
            meta = o_resp.get('metadata', {})
            if meta.get('status') == 'Success':
                output = meta.get('metadata', {}).get('output', {})
                paths_to_check = []
                if isinstance(output, dict):
                    paths_to_check = list(output.values())
                elif isinstance(output, list):
                    paths_to_check = output
                for p in paths_to_check:
                    if isinstance(p, str) and 'stdout' in p:
                        class _UC(http.client.HTTPConnection):
                            def __init__(self):
                                super().__init__('localhost', timeout=10)
                            def connect(self):
                                self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
                                self.sock.connect('/var/lib/incus/unix.socket')
                        c = _UC()
                        c.request('GET', p)
                        r = c.getresponse()
                        return (meta.get('metadata', {}).get('return-code', 0), r.read())
                return (meta.get('metadata', {}).get('return-code', 0), b'')
            if meta.get('status') == 'Failure':
                return (1, b'')
        time.sleep(0.3)
    return (1, b'')
def strip_ansi(text):
    return re.sub('\\x1b\\[[0-9;]*m', '', text)
app = Flask(__name__)
EMBEDDED_TEMPLATES = {'icons.html': """<svg xmlns="http://www.w3.org/2000/svg" style="display:none">
    <symbol id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </symbol>
    <symbol id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </symbol>
    <symbol id="icon-bolt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </symbol>
    <symbol id="icon-dashboard" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>
    </symbol>
    <symbol id="icon-server" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>
    </symbol>
    <symbol id="icon-terminal" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
    </symbol>
    <symbol id="icon-user" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
    </symbol>
    <symbol id="icon-users" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </symbol>
    <symbol id="icon-bell" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </symbol>
    <symbol id="icon-settings" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </symbol>
    <symbol id="icon-play" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="5 3 19 12 5 21 5 3"/>
    </symbol>
    <symbol id="icon-stop" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
    </symbol>
    <symbol id="icon-pause" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
    </symbol>
    <symbol id="icon-ban" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
    </symbol>
    <symbol id="icon-copy" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </symbol>
    <symbol id="icon-trash" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </symbol>
    <symbol id="icon-refresh" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </symbol>
    <symbol id="icon-restart" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </symbol>
    <symbol id="icon-chevron-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6"/>
    </symbol>
    <symbol id="icon-plus" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </symbol>
    <symbol id="icon-key" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
    </symbol>
    <symbol id="icon-cpu" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>
    </symbol>
    <symbol id="icon-shield" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </symbol>
    <symbol id="icon-dot" viewBox="0 0 8 8">
        <circle cx="4" cy="4" r="4" fill="currentColor"/>
    </symbol>
    <symbol id="icon-sliders" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>
    </symbol>
    <symbol id="icon-check-circle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
    </symbol>
    <symbol id="icon-menu" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>
    </symbol>
    <symbol id="icon-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </symbol>
    <symbol id="icon-clock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </symbol>
    <symbol id="icon-info" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </symbol>
    <symbol id="icon-hard-drive" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="22" y1="12" x2="2" y2="12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" y1="16" x2="6.01" y2="16"/><line x1="10" y1="16" x2="10.01" y2="16"/>
    </symbol>

    <symbol id="icon-activity" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </symbol>
    <symbol id="icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12"/>
    </symbol>
    <symbol id="icon-globe" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </symbol>
    <symbol id="icon-rocket" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
    </symbol>
    <symbol id="icon-arrow-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
    </symbol>
    <symbol id="icon-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </symbol>
    <symbol id="icon-mail" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
    </symbol>
    <symbol id="icon-edit" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </symbol></svg>
""", 'components.html': """{% macro sidebar(active_page, settings=None, icon=None) %}
<aside class="sidebar">
    <a href="/dashboard" class="sidebar-logo">
        {% if icon %}
        <img src="{{ icon }}" alt="Icon" style="width:24px;height:24px;border-radius:6px;object-fit:contain;">
        {% else %}
        <img src="https://files.catbox.moe/wni5n4.png" alt="Icon" style="width:24px;height:24px;border-radius:6px;object-fit:contain;">
        {% endif %}
        {{ settings.site_name if settings else 'Omega Panel' }}
    </a>

    <div class="sidebar-section">
        <div class="sidebar-section-label">Main</div>
        <a href="/dashboard" class="sidebar-link {{ 'active' if active_page == 'dashboard' }}">
            <svg width="18" height="18"><use href="#icon-dashboard"/></svg>
            Dashboard
        </a>
        <a href="/ports" class="sidebar-link {{ 'active' if active_page == 'ports' }}">
            <svg width="18" height="18"><use href="#icon-key"/></svg>
            Port Forwarding
        </a>
        <a href="/tickets" class="sidebar-link {{ 'active' if active_page == 'tickets' }}">
            <svg width="18" height="18"><use href="#icon-bell"/></svg>
            Support Tickets
        </a>
        <a href="/schedules" class="sidebar-link {{ 'active' if active_page == 'schedules' }}">
            <svg width="18" height="18"><use href="#icon-clock"/></svg>
            Schedules
        </a>
        <a href="/notifications" class="sidebar-link {{ 'active' if active_page == 'notifications' }}">
            <svg width="18" height="18"><use href="#icon-bell"/></svg>
            Notifications
        </a>
    </div>

    <div class="sidebar-section">
        <div class="sidebar-section-label">Management</div>
        <a href="/profile" class="sidebar-link {{ 'active' if active_page == 'profile' }}">
            <svg width="18" height="18"><use href="#icon-user"/></svg>
            Profile
        </a>
        <a href="/logs" class="sidebar-link {{ 'active' if active_page == 'logs' }}">
            <svg width="18" height="18"><use href="#icon-terminal"/></svg>
            Logs
        </a>
    </div>

    {% if session.get('is_admin') %}
    <div class="sidebar-section">
        <div class="sidebar-section-label">Administration</div>
        <a href="/admin" class="sidebar-link {{ 'active' if active_page == 'admin' }}">
            <svg width="18" height="18"><use href="#icon-settings"/></svg>
            Admin Dashboard
        </a>
        <a href="/admin/users" class="sidebar-link {{ 'active' if active_page == 'users' }}">
            <svg width="18" height="18"><use href="#icon-users"/></svg>
            Users
        </a>
        <a href="/admin/all-vps" class="sidebar-link {{ 'active' if active_page == 'allvps' }}">
            <svg width="18" height="18"><use href="#icon-server"/></svg>
            All VPS
        </a>
        <a href="/admin/expiring" class="sidebar-link {{ 'active' if active_page == 'expiring' }}">
            <svg width="18" height="18"><use href="#icon-clock"/></svg>
            Expiring VPS
        </a>
        <a href="/admin/usage" class="sidebar-link {{ 'active' if active_page == 'usage' }}">
            <svg width="18" height="18"><use href="#icon-users"/></svg>
            Usage Report
        </a>
        <a href="/nodes" class="sidebar-link {{ 'active' if active_page == 'nodes' }}">
            <svg width="18" height="18"><use href="#icon-cpu"/></svg>
            Nodes
        </a>
    </div>
    <div class="sidebar-section">
        <div class="sidebar-section-label">System</div>
        <a href="/system-info" class="sidebar-link {{ 'active' if active_page == 'sysinfo' }}">
            <svg width="18" height="18"><use href="#icon-info"/></svg>
            System Info
        </a>
        <a href="/os-icons" class="sidebar-link {{ 'active' if active_page == 'osicons' }}">
            <svg width="18" height="18"><use href="#icon-server"/></svg>
            OS Icons
        </a>
        <a href="/settings" class="sidebar-link {{ 'active' if active_page == 'settings' }}">
            <svg width="18" height="18"><use href="#icon-settings"/></svg>
            Settings
        </a>
        <a href="/api-docs" class="sidebar-link {{ 'active' if active_page == 'apidocs' }}">
            <svg width="18" height="18"><use href="#icon-terminal"/></svg>
            API Docs
        </a>
    </div>
    {% endif %}

    <div class="sidebar-footer">
        <div style="margin-bottom:4px;">{{ settings.footer_text if settings else 'Powered by Omega Panel' }}</div>
        <div style="font-size:10px;color:var(--text-dim);margin-bottom:6px;">Created by <strong>NafiGamer</strong> &amp; <strong>Aman</strong></div>
        <a href="/logout" style="color:var(--text-dim);text-decoration:none;font-size:11px;display:flex;align-items:center;gap:4px;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            Sign out
        </a>
    </div>
</aside>
{% endmacro %}

{% macro topbar(title, active_page) %}
<div class="topbar">
    <div class="topbar-left">
        <button class="hamburger" onclick="document.querySelector('.sidebar').classList.toggle('open'); document.querySelector('.sidebar-overlay').classList.toggle('active')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <span class="topbar-title">{{ title }}</span>
    </div>
    <div class="topbar-right">
        <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">
            <svg width="16" height="16"><use href="#icon-sun"/></svg>
        </button>
        <a href="/logout" class="theme-toggle" title="Sign out" style="text-decoration:none;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        </a>
        <button class="topbar-bell">
            <svg width="18" height="18"><use href="#icon-bell"/></svg>
            <span class="badge"></span>
        </button>
        <a href="/profile" class="topbar-user">
            <div class="topbar-avatar">{{ session.get('username', 'U')[0].upper() }}</div>
            <div class="topbar-user-info">
                <span class="topbar-user-name">{{ session.get('username') }}</span>
                <span class="topbar-user-role">{% if session.get('is_admin') %}Admin{% else %}User{% endif %}</span>
            </div>
        </a>
    </div>
</div>
{% endmacro %}

{% macro overlay() %}
<div class="sidebar-overlay" onclick="document.querySelector('.sidebar').classList.remove('open'); this.classList.remove('active')"></div>
{% endmacro %}
""", 'index.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ settings.site_name if settings else 'Omega Panel' }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        @keyframes fadeUp { from { opacity: 0; transform: translateY(24px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
        @keyframes gradientShift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        @keyframes slideIn { from { opacity: 0; transform: scale(.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 20px rgba(255,255,255,.08); } 50% { box-shadow: 0 0 40px rgba(255,255,255,.15); } }

        .hero-bg {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: -1;
            background: radial-gradient(ellipse 80% 60% at 50% -20%, rgba(255,255,255,.05) 0%, transparent 70%),
                        radial-gradient(ellipse 60% 40% at 80% 50%, rgba(255,255,255,.03) 0%, transparent 60%),
                        var(--bg-elevated);
        }
        .hero-grid {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: -1;
            background-image:
                linear-gradient(rgba(255,255,255,.02) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,.02) 1px, transparent 1px);
            background-size: 60px 60px;
            mask-image: radial-gradient(ellipse 70% 50% at 50% 30%, black 20%, transparent 70%);
        }

        .landing-page {
            min-height: 100vh; display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            padding: 40px 20px; gap: 0;
        }
        .hero-section { text-align: center; max-width: 640px; width: 100%; }
        .hero-section h1 {
            font-size: clamp(32px, 5vw, 52px); font-weight: 800; letter-spacing: -2px;
            line-height: 1.1; margin-bottom: 20px; animation: fadeUp .6s ease both;
        }
        .hero-section h1 .gradient-text {
            background: linear-gradient(135deg, #ffffff, #a1a1aa, #ffffff);
            background-size: 200% 200%;
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            animation: gradientShift 4s ease infinite;
        }
        .hero-sub {
            font-size: 16px; color: var(--text-muted); line-height: 1.7;
            max-width: 480px; margin: 0 auto 32px; animation: fadeUp .6s ease .1s both;
        }
        .hero-actions {
            display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;
            animation: fadeUp .6s ease .2s both;
        }
        .hero-actions .btn { padding: 12px 28px; font-size: 14px; font-weight: 600; border-radius: 10px; }
        .hero-actions .btn-primary { animation: glow 3s ease infinite; }

        .stats-row {
            display: flex; gap: 32px; justify-content: center; flex-wrap: wrap;
            margin-top: 48px; animation: fadeUp .6s ease .3s both;
        }
        .stat-item { text-align: center; }
        .stat-num { font-size: 28px; font-weight: 800; color: var(--accent); line-height: 1; }
        .stat-label { font-size: 12px; color: var(--text-dim); margin-top: 6px; }

        .features-section {
            margin-top: 64px; width: 100%; max-width: 900px;
            animation: fadeUp .6s ease .4s both;
        }
        .features-section h2 {
            text-align: center; font-size: 20px; font-weight: 700; margin-bottom: 32px;
            letter-spacing: -.5px;
        }
        .features-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px;
        }
        .feature-card {
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px;
            padding: 24px; text-align: center; transition: all .25s ease; position: relative; overflow: hidden;
        }
        .feature-card:hover {
            border-color: rgba(255,255,255,.15); transform: translateY(-3px);
            box-shadow: 0 8px 32px rgba(255,255,255,.05);
        }
        .feature-card::before {
            content: ''; position: absolute; top: 0; left: 50%; transform: translateX(-50%);
            width: 60%; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.2), transparent);
            opacity: 0; transition: opacity .25s;
        }
        .feature-card:hover::before { opacity: 1; }
        .feature-icon {
            width: 44px; height: 44px; border-radius: 12px; display: inline-flex;
            align-items: center; justify-content: center; margin-bottom: 16px;
            background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.08);
        }
        .feature-card h3 { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
        .feature-card p { font-size: 13px; color: var(--text-dim); line-height: 1.6; margin: 0; }

        .trust-section {
            margin-top: 56px; text-align: center; animation: fadeUp .6s ease .5s both;
        }
        .trust-row {
            display: flex; gap: 24px; justify-content: center; flex-wrap: wrap; margin-top: 16px;
        }
        .trust-item {
            display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-dim);
        }
        .trust-item svg { color: var(--green); flex-shrink: 0; }

        .cta-section {
            margin-top: 56px; width: 100%; max-width: 640px; text-align: center;
            animation: fadeUp .6s ease .6s both;
        }
        .cta-card {
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
            padding: 40px 32px; position: relative; overflow: hidden;
        }
        .cta-card::before {
            content: ''; position: absolute; top: -1px; left: 0; right: 0; height: 2px;
            background: linear-gradient(90deg, transparent, var(--accent), transparent);
        }
        .cta-card h2 { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
        .cta-card p { font-size: 14px; color: var(--text-dim); margin-bottom: 24px; }

        .footer-bar {
            margin-top: 56px; padding: 20px; text-align: center; font-size: 12px;
            color: var(--text-dim); border-top: 1px solid var(--border); width: 100%;
            max-width: 900px; display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; gap: 12px; animation: fadeIn .6s ease .7s both;
        }

        @media (max-width: 640px) {
            .features-grid { grid-template-columns: 1fr; }
            .stats-row { gap: 20px; }
            .footer-bar { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="hero-bg"></div>
    <div class="hero-grid"></div>

    <svg xmlns="http://www.w3.org/2000/svg" style="display:none">
        <symbol id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </symbol>
        <symbol id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </symbol>
        <symbol id="icon-bolt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </symbol>
        <symbol id="icon-key" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
        </symbol>
        <symbol id="icon-sliders" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>
        </symbol>
        <symbol id="icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
        </symbol>
        <symbol id="icon-globe" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
        </symbol>
        <symbol id="icon-shield" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </symbol>
        <symbol id="icon-server" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>
        </symbol>
        <symbol id="icon-rocket" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
        </symbol>
    </svg>

    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme" style="position: fixed; top: 16px; right: 16px; z-index: 10;">
        <svg width="16" height="16"><use href="#icon-sun"/></svg>
    </button>

    <div class="landing-page">
        <div class="hero-section">
            <div style="display: flex; justify-content: center; align-items: center; gap: 10px; margin-bottom: 8px;">
                {% if custom_icon %}
                <img src="{{ custom_icon }}" alt="Icon" style="width:32px;height:32px;border-radius:8px;object-fit:contain;animation:float 3s ease-in-out infinite;">
                {% else %}
                <img src="https://files.catbox.moe/wni5n4.png" alt="Icon" style="width:32px;height:32px;border-radius:8px;object-fit:contain;animation:float 3s ease-in-out infinite;">
                {% endif %}
                <span style="font-size: 20px; font-weight: 700;">{{ settings.site_name if settings else 'Omega Panel' }}</span>
            </div>
            <div style="display: flex; justify-content: center; margin-bottom: 32px;">
                <div style="display: inline-flex; align-items: center; gap: 6px; padding: 5px 14px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 100px; font-size: 12px; color: var(--text-muted);">
                    <span style="width: 6px; height: 6px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite;"></span>
                    Available now
                </div>
            </div>

            <h1>Deploy VPS in <span class="gradient-text">seconds</span></h1>
            <p class="hero-sub">{{ settings.site_description if settings else 'Lightweight virtual private servers. Full root access, instant provisioning, and a clean dashboard to manage everything.' }}</p>

            <div class="hero-actions">
                <a href="/register" class="btn btn-primary">Create account</a>
                <a href="/login" class="btn btn-ghost">Sign in</a>
            </div>

            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-num">99.9%</div>
                    <div class="stat-label">Uptime</div>
                </div>
                <div class="stat-item">
                    <div class="stat-num">&lt;3s</div>
                    <div class="stat-label">Boot time</div>
                </div>
                <div class="stat-item">
                    <div class="stat-num">1Gbps</div>
                    <div class="stat-label">Network</div>
                </div>
                <div class="stat-item">
                    <div class="stat-num">Root</div>
                    <div class="stat-label">Full access</div>
                </div>
            </div>
        </div>

        <div class="features-section">
            <h2>Everything you need</h2>
            <div class="features-grid">
                <div class="feature-card">
                    <div class="feature-icon"><svg width="20" height="20" style="color: var(--accent);"><use href="#icon-rocket"/></svg></div>
                    <h3>Instant provisioning</h3>
                    <p>Your instance is live in seconds. No waiting, no queues.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon"><svg width="20" height="20" style="color: var(--accent);"><use href="#icon-key"/></svg></div>
                    <h3>SSH &amp; SSHx</h3>
                    <p>Connect via sshx. Browser or terminal.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon"><svg width="20" height="20" style="color: var(--accent);"><use href="#icon-sliders"/></svg></div>
                    <h3>Full control</h3>
                    <p>Start, stop, restart, or destroy. One click.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon"><svg width="20" height="20" style="color: var(--accent);"><use href="#icon-shield"/></svg></div>
                    <h3>Secure by default</h3>
                    <p>Isolated containers with dedicated resources.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon"><svg width="20" height="20" style="color: var(--accent);"><use href="#icon-globe"/></svg></div>
                    <h3>Multi-node</h3>
                    <p>Deploy across multiple servers from one panel.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon"><svg width="20" height="20" style="color: var(--accent);"><use href="#icon-server"/></svg></div>
                    <h3>Port forwarding</h3>
                    <p>Expose services to the internet with ease.</p>
                </div>
            </div>
        </div>

        <div class="trust-section">
            <div class="trust-row">
                <div class="trust-item">
                    <svg width="16" height="16"><use href="#icon-check"/></svg>
                    <span>No credit card required</span>
                </div>
                <div class="trust-item">
                    <svg width="16" height="16"><use href="#icon-check"/></svg>
                    <span>Free tier available</span>
                </div>
                <div class="trust-item">
                    <svg width="16" height="16"><use href="#icon-check"/></svg>
                    <span>Cancel anytime</span>
                </div>
            </div>
        </div>

        <div class="cta-section">
            <div class="cta-card">
                <h2>Ready to get started?</h2>
                <p>Create an account and deploy your first VPS in under a minute.</p>
                <div style="display: flex; gap: 10px; justify-content: center;">
                    <a href="/register" class="btn btn-primary">Get started free</a>
                    <a href="/login" class="btn btn-ghost">Sign in</a>
                </div>
            </div>
        </div>

        <div class="footer-bar">
            <span>{{ settings.footer_text if settings else 'Omega Panel' }} &mdash; Created by <strong>NafiGamer</strong> &amp; <strong>Aman</strong></span>
            <span style="display: flex; gap: 16px;">
                <a href="/login" style="color: var(--text-dim); text-decoration: none;">Login</a>
                <a href="/register" style="color: var(--text-dim); text-decoration: none;">Register</a>
            </span>
        </div>
    </div>

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'login.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign in — {{ settings.site_name if settings else 'Omega Panel' }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        @keyframes fadeUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 20px rgba(255,255,255,.1); } 50% { box-shadow: 0 0 40px rgba(255,255,255,.2); } }

        .auth-bg {
            position: fixed; inset: 0; z-index: -2;
            background: radial-gradient(ellipse 60% 50% at 50% 0%, rgba(255,255,255,.05) 0%, transparent 60%),
                        var(--bg-elevated);
        }
        .auth-grid {
            position: fixed; inset: 0; z-index: -1;
            background-image:
                linear-gradient(rgba(255,255,255,.015) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,.015) 1px, transparent 1px);
            background-size: 50px 50px;
            mask-image: radial-gradient(ellipse 60% 50% at 50% 30%, black 10%, transparent 70%);
        }

        .auth-page {
            min-height: 100vh; min-height: 100dvh; display: flex; align-items: center; justify-content: center;
            padding: 20px; position: relative; z-index: 1;
        }

        .auth-wrapper {
            width: 100%; max-width: 420px; animation: fadeUp .5s ease both;
            margin: 0 auto; position: relative; z-index: 2;
        }

        .auth-header {
            text-align: center; margin-bottom: 32px;
        }

        .auth-logo {
            display: inline-flex; align-items: center; gap: 10px; margin-bottom: 16px;
        }

        .auth-logo-icon {
            width: 48px; height: 48px; border-radius: 14px; display: flex;
            align-items: center; justify-content: center;
            background: var(--bg-card); border: 1px solid var(--border);
            animation: float 3s ease-in-out infinite;
        }

        .auth-logo-icon svg { width: 24px; height: 24px; color: var(--text); }

        .auth-header h1 {
            font-size: 22px; font-weight: 700; margin-bottom: 6px; letter-spacing: -.5px;
        }

        .auth-header p {
            font-size: 14px; color: var(--text-dim);
        }

        .auth-card {
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
            padding: 28px; position: relative; overflow: hidden;
        }

        .auth-card::before {
            content: ''; position: absolute; top: -1px; left: 0; right: 0; height: 2px;
            background: linear-gradient(90deg, transparent, var(--text), transparent);
        }

        .form-group { margin-bottom: 18px; }

        .form-group label {
            display: block; font-size: 13px; font-weight: 500;
            color: var(--text-muted); margin-bottom: 6px;
        }

        .input-wrap {
            position: relative;
        }

        .input-wrap svg {
            position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
            width: 16px; height: 16px; color: var(--text-dim); pointer-events: none;
            transition: color .15s;
        }

        .input-wrap input:focus ~ svg,
        .input-wrap input:focus + svg { color: var(--text-muted); }

        .form-control {
            width: 100%; padding: 11px 12px 11px 38px; font-size: 14px;
            font-family: inherit; color: var(--text); background: var(--bg-input);
            border: 1px solid var(--border); border-radius: 10px; outline: none;
            transition: all .15s ease;
        }

        .form-control::placeholder { color: var(--text-dim); }
        .form-control:focus { border-color: rgba(255,255,255,.2); box-shadow: 0 0 0 3px rgba(255,255,255,.05); }

        .btn-submit {
            width: 100%; padding: 12px; font-size: 14px; font-weight: 600;
            font-family: inherit; border: none; border-radius: 10px;
            background: var(--text); color: var(--bg); cursor: pointer;
            transition: all .15s; margin-top: 4px;
            animation: glow 3s ease infinite;
        }

        .btn-submit:hover { opacity: .9; transform: translateY(-1px); }
        .btn-submit:active { transform: translateY(0); }

        .auth-divider {
            display: flex; align-items: center; gap: 12px; margin: 20px 0;
            font-size: 12px; color: var(--text-dim);
        }

        .auth-divider::before, .auth-divider::after {
            content: ''; flex: 1; height: 1px; background: var(--border);
        }

        .auth-footer {
            text-align: center; font-size: 13px; color: var(--text-dim); margin-top: 20px;
        }

        .auth-footer a { color: var(--text); text-decoration: none; font-weight: 600; }
        .auth-footer a:hover { text-decoration: underline; }

        .back-link {
            display: flex; align-items: center; gap: 6px; font-size: 13px;
            color: var(--text-dim); text-decoration: none; margin-bottom: 24px;
            transition: color .15s;
        }

        .back-link:hover { color: var(--text-muted); }
        .back-link svg { width: 14px; height: 14px; }

        .theme-toggle {
            position: fixed; top: 16px; right: 16px; z-index: 10;
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 8px; width: 36px; height: 36px;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; color: var(--text-muted); transition: all .15s;
        }

        .theme-toggle:hover { background: var(--bg-hover); color: var(--text); border-color: rgba(255,255,255,.15); }

        .flash-msg {
            padding: 10px 14px; border-radius: 10px; font-size: 13px; margin-bottom: 18px;
            display: flex; align-items: center; gap: 8px;
        }

        .flash-success { background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.15); color: var(--green); }
        .flash-error { background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.15); color: var(--red); }

        @media (max-width: 480px) {
            .auth-page { padding: 20px 16px; }
            .auth-header { margin-bottom: 24px; }
            .auth-header h1 { font-size: 20px; }
            .auth-card { padding: 20px; border-radius: 14px; }
            .auth-logo-icon { width: 44px; height: 44px; }
        }
    </style>
</head>
<body>
    <div class="auth-bg"></div>
    <div class="auth-grid"></div>

    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">
        <svg width="16" height="16"><use href="#icon-sun"/></svg>
    </button>

    <svg xmlns="http://www.w3.org/2000/svg" style="display:none">
        <symbol id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </symbol>
        <symbol id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </symbol>
        <symbol id="icon-bolt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </symbol>
        <symbol id="icon-user" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
        </symbol>
        <symbol id="icon-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </symbol>
        <symbol id="icon-arrow-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
        </symbol>
    </svg>

    <div class="auth-page">
        <div class="auth-wrapper">
            <a href="/" class="back-link">
                <svg width="14" height="14"><use href="#icon-arrow-left"/></svg>
                Back to home
            </a>

            <div class="auth-header">
                <div class="auth-logo">
                    <div class="auth-logo-icon">
                        {% if custom_icon %}
                        <img src="{{ custom_icon }}" alt="Icon" style="width:24px;height:24px;border-radius:6px;object-fit:contain;">
                        {% else %}
                        <img src="https://files.catbox.moe/wni5n4.png" alt="Icon" style="width:24px;height:24px;border-radius:6px;object-fit:contain;">
                        {% endif %}
                    </div>
                </div>
                <h1>Welcome back</h1>
                <p>Sign in to your {{ settings.site_name if settings else 'Omega Panel' }} account</p>
            </div>

            <div class="auth-card">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="flash-msg flash-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <form method="POST" action="/login">
                    <div class="form-group">
                        <label for="username">Username</label>
                        <div class="input-wrap">
                            <input type="text" id="username" name="username" class="form-control" placeholder="Enter your username" required autofocus>
                            <svg width="16" height="16"><use href="#icon-user"/></svg>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="password">Password</label>
                        <div class="input-wrap">
                            <input type="password" id="password" name="password" class="form-control" placeholder="Enter your password" required>
                            <svg width="16" height="16"><use href="#icon-lock"/></svg>
                        </div>
                    </div>

                    <button type="submit" class="btn-submit">Sign in</button>
                </form>
            </div>

            <div class="auth-footer">
                Don't have an account? <a href="/register">Create one</a>
            </div>
            <div style="text-align:center;font-size:10px;color:var(--text-dim);margin-top:12px;">Created by <strong>NafiGamer</strong> &amp; <strong>Aman</strong></div>
        </div>
    </div>

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'register.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create account — {{ settings.site_name if settings else 'Omega Panel' }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        @keyframes fadeUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 20px rgba(255,255,255,.1); } 50% { box-shadow: 0 0 40px rgba(255,255,255,.2); } }

        .auth-bg {
            position: fixed; inset: 0; z-index: -2;
            background: radial-gradient(ellipse 60% 50% at 50% 0%, rgba(255,255,255,.05) 0%, transparent 60%),
                        var(--bg-elevated);
        }
        .auth-grid {
            position: fixed; inset: 0; z-index: -1;
            background-image:
                linear-gradient(rgba(255,255,255,.015) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,.015) 1px, transparent 1px);
            background-size: 50px 50px;
            mask-image: radial-gradient(ellipse 60% 50% at 50% 30%, black 10%, transparent 70%);
        }

        .auth-page {
            min-height: 100vh; min-height: 100dvh; display: flex; align-items: center; justify-content: center;
            padding: 20px; position: relative; z-index: 1;
        }

        .auth-wrapper {
            width: 100%; max-width: 420px; animation: fadeUp .5s ease both;
            margin: 0 auto; position: relative; z-index: 2;
        }

        .auth-header {
            text-align: center; margin-bottom: 32px;
        }

        .auth-logo {
            display: inline-flex; align-items: center; gap: 10px; margin-bottom: 16px;
        }

        .auth-logo-icon {
            width: 48px; height: 48px; border-radius: 14px; display: flex;
            align-items: center; justify-content: center;
            background: var(--bg-card); border: 1px solid var(--border);
            animation: float 3s ease-in-out infinite;
        }

        .auth-logo-icon svg { width: 24px; height: 24px; color: var(--text); }

        .auth-header h1 {
            font-size: 22px; font-weight: 700; margin-bottom: 6px; letter-spacing: -.5px;
        }

        .auth-header p {
            font-size: 14px; color: var(--text-dim);
        }

        .auth-card {
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
            padding: 28px; position: relative; overflow: hidden;
        }

        .auth-card::before {
            content: ''; position: absolute; top: -1px; left: 0; right: 0; height: 2px;
            background: linear-gradient(90deg, transparent, var(--text), transparent);
        }

        .form-group { margin-bottom: 16px; }

        .form-group label {
            display: block; font-size: 13px; font-weight: 500;
            color: var(--text-muted); margin-bottom: 6px;
        }

        .input-wrap {
            position: relative;
        }

        .input-wrap svg {
            position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
            width: 16px; height: 16px; color: var(--text-dim); pointer-events: none;
            transition: color .15s;
        }

        .input-wrap input:focus ~ svg,
        .input-wrap input:focus + svg { color: var(--text-muted); }

        .form-control {
            width: 100%; padding: 11px 12px 11px 38px; font-size: 14px;
            font-family: inherit; color: var(--text); background: var(--bg-input);
            border: 1px solid var(--border); border-radius: 10px; outline: none;
            transition: all .15s ease;
        }

        .form-control::placeholder { color: var(--text-dim); }
        .form-control:focus { border-color: rgba(255,255,255,.2); box-shadow: 0 0 0 3px rgba(255,255,255,.05); }

        .btn-submit {
            width: 100%; padding: 12px; font-size: 14px; font-weight: 600;
            font-family: inherit; border: none; border-radius: 10px;
            background: var(--text); color: var(--bg); cursor: pointer;
            transition: all .15s; margin-top: 4px;
            animation: glow 3s ease infinite;
        }

        .btn-submit:hover { opacity: .9; transform: translateY(-1px); }
        .btn-submit:active { transform: translateY(0); }

        .auth-footer {
            text-align: center; font-size: 13px; color: var(--text-dim); margin-top: 20px;
        }

        .auth-footer a { color: var(--text); text-decoration: none; font-weight: 600; }
        .auth-footer a:hover { text-decoration: underline; }

        .back-link {
            display: flex; align-items: center; gap: 6px; font-size: 13px;
            color: var(--text-dim); text-decoration: none; margin-bottom: 24px;
            transition: color .15s;
        }

        .back-link:hover { color: var(--text-muted); }
        .back-link svg { width: 14px; height: 14px; }

        .theme-toggle {
            position: fixed; top: 16px; right: 16px; z-index: 10;
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 8px; width: 36px; height: 36px;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; color: var(--text-muted); transition: all .15s;
        }

        .theme-toggle:hover { background: var(--bg-hover); color: var(--text); border-color: rgba(255,255,255,.15); }

        .flash-msg {
            padding: 10px 14px; border-radius: 10px; font-size: 13px; margin-bottom: 18px;
            display: flex; align-items: center; gap: 8px;
        }

        .flash-success { background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.15); color: var(--green); }
        .flash-error { background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.15); color: var(--red); }

        .form-hint {
            font-size: 11px; color: var(--text-dim); margin-top: 4px;
        }

        .form-row {
            display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
        }

        @media (max-width: 480px) {
            .auth-page { padding: 20px 16px; }
            .auth-header { margin-bottom: 24px; }
            .auth-header h1 { font-size: 20px; }
            .auth-card { padding: 20px; border-radius: 14px; }
            .form-row { grid-template-columns: 1fr; }
            .auth-logo-icon { width: 44px; height: 44px; }
        }
    </style>
</head>
<body>
    <div class="auth-bg"></div>
    <div class="auth-grid"></div>

    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">
        <svg width="16" height="16"><use href="#icon-sun"/></svg>
    </button>

    <svg xmlns="http://www.w3.org/2000/svg" style="display:none">
        <symbol id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </symbol>
        <symbol id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </symbol>
        <symbol id="icon-bolt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </symbol>
        <symbol id="icon-user" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
        </symbol>
        <symbol id="icon-mail" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
        </symbol>
        <symbol id="icon-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </symbol>
        <symbol id="icon-arrow-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
        </symbol>
        <symbol id="icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
        </symbol>
    </svg>

    <div class="auth-page">
        <div class="auth-wrapper">
            <a href="/" class="back-link">
                <svg width="14" height="14"><use href="#icon-arrow-left"/></svg>
                Back to home
            </a>

            <div class="auth-header">
                <div class="auth-logo">
                    <div class="auth-logo-icon">
                        {% if custom_icon %}
                        <img src="{{ custom_icon }}" alt="Icon" style="width:24px;height:24px;border-radius:6px;object-fit:contain;">
                        {% else %}
                        <img src="https://files.catbox.moe/wni5n4.png" alt="Icon" style="width:24px;height:24px;border-radius:6px;object-fit:contain;">
                        {% endif %}
                    </div>
                </div>
                <h1>Create account</h1>
                <p>Get started with {{ settings.site_name if settings else 'Omega Panel' }}</p>
            </div>

            <div class="auth-card">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="flash-msg flash-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <form method="POST" action="/register">
                    <div class="form-group">
                        <label for="username">Username</label>
                        <div class="input-wrap">
                            <input type="text" id="username" name="username" class="form-control" placeholder="Choose a username" required autofocus>
                            <svg width="16" height="16"><use href="#icon-user"/></svg>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="email">Email</label>
                        <div class="input-wrap">
                            <input type="email" id="email" name="email" class="form-control" placeholder="you@example.com" required>
                            <svg width="16" height="16"><use href="#icon-mail"/></svg>
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label for="password">Password</label>
                            <div class="input-wrap">
                                <input type="password" id="password" name="password" class="form-control" placeholder="Min 6 characters" required minlength="6">
                                <svg width="16" height="16"><use href="#icon-lock"/></svg>
                            </div>
                        </div>

                        <div class="form-group">
                            <label for="confirm_password">Confirm</label>
                            <div class="input-wrap">
                                <input type="password" id="confirm_password" name="confirm_password" class="form-control" placeholder="Repeat password" required>
                                <svg width="16" height="16"><use href="#icon-lock"/></svg>
                            </div>
                        </div>
                    </div>

                    <button type="submit" class="btn-submit">Create account</button>
                </form>
            </div>

            <div class="auth-footer">
                Already have an account? <a href="/login">Sign in</a>
            </div>
            <div style="text-align:center;font-size:10px;color:var(--text-dim);margin-top:12px;">Created by <strong>NafiGamer</strong> &amp; <strong>Aman</strong></div>
        </div>
    </div>

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'dashboard.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard — {{ settings.site_name if settings else 'Omega Panel' }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        @keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }

        .welcome-banner {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 28px 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
            animation: fadeUp .4s ease both;
        }

        .welcome-banner::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.1), transparent);
        }

        .welcome-banner::after {
            content: '';
            position: absolute;
            top: -60%; right: -10%;
            width: 300px; height: 300px;
            background: radial-gradient(circle, rgba(255,255,255,.04) 0%, transparent 70%);
            pointer-events: none;
        }

        .welcome-banner h1 {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -.5px;
            margin-bottom: 4px;
        }

        .welcome-banner p {
            font-size: 13px;
            color: var(--text-dim);
        }

        .stat-cards {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px;
            display: flex;
            align-items: center;
            gap: 14px;
            transition: all .2s ease;
            animation: fadeUp .4s ease both;
        }

        .stat-card:nth-child(1) { animation-delay: .05s; }
        .stat-card:nth-child(2) { animation-delay: .1s; }
        .stat-card:nth-child(3) { animation-delay: .15s; }
        .stat-card:nth-child(4) { animation-delay: .2s; }

        .stat-card:hover {
            border-color: rgba(255,255,255,.1);
            transform: translateY(-2px);
        }

        .stat-icon {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .stat-icon svg { width: 20px; height: 20px; }

        .stat-icon.s-white { background: rgba(255,255,255,.06); color: var(--text); border: 1px solid rgba(255,255,255,.08); }
        .stat-icon.s-green { background: var(--green-bg); color: var(--green); border: 1px solid rgba(34,197,94,.12); }
        .stat-icon.s-yellow { background: var(--yellow-bg); color: var(--yellow); border: 1px solid rgba(234,179,8,.12); }
        .stat-icon.s-red { background: var(--red-bg); color: var(--red); border: 1px solid rgba(239,68,68,.12); }

        .stat-info .stat-label {
            font-size: 11px;
            font-weight: 500;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: .5px;
        }

        .stat-info .stat-value {
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -.5px;
            line-height: 1.2;
        }

        .stat-sub {
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 2px;
        }

        .overview-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 20px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.08), transparent);
        }

        .card-title {
            font-size: 14px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 16px;
        }

        .card-title svg { width: 18px; height: 18px; color: var(--text-dim); }

        .resource-bars { display: flex; flex-direction: column; gap: 14px; }

        .resource-bar-item { display: flex; flex-direction: column; gap: 6px; }

        .resource-bar-header {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .resource-bar-track {
            height: 6px;
            background: var(--bg);
            border-radius: 3px;
            overflow: hidden;
        }

        .resource-bar-fill {
            height: 100%;
            border-radius: 3px;
            transition: width .5s ease;
        }

        .resource-bar-fill.green { background: var(--green); }
        .resource-bar-fill.white { background: var(--text); }
        .resource-bar-fill.yellow { background: var(--yellow); }

        .vps-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 12px;
        }

        .vps-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px;
            transition: all .2s ease;
            position: relative;
            overflow: hidden;
        }

        .vps-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.06), transparent);
        }

        .vps-card:hover {
            border-color: rgba(255,255,255,.1);
            transform: translateY(-2px);
        }

        .vps-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }

        .vps-name {
            font-size: 14px;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }

        .vps-specs {
            display: flex;
            gap: 12px;
            margin-bottom: 12px;
        }

        .vps-spec { display: flex; flex-direction: column; gap: 2px; }

        .vps-spec-label {
            font-size: 10px;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: .5px;
        }

        .vps-spec-value {
            font-size: 13px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .vps-actions { display: flex; gap: 8px; }

        .search-bar {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }

        .search-input {
            flex: 1;
            padding: 10px 14px;
            font-size: 13px;
            font-family: inherit;
            color: var(--text);
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 10px;
            outline: none;
            transition: border-color .15s;
        }

        .search-input::placeholder { color: var(--text-dim); }
        .search-input:focus { border-color: rgba(255,255,255,.2); }

        .search-select {
            padding: 10px 32px 10px 12px;
            font-size: 13px;
            font-family: inherit;
            color: var(--text-muted);
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 10px;
            outline: none;
            cursor: pointer;
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%2371717a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 10px center;
        }

        .ssh-box {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            overflow-x: auto;
            white-space: nowrap;
        }

        .status {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 500;
            padding: 3px 8px;
            border-radius: 100px;
        }

        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }

        .status-running { background: var(--green-bg); color: var(--green); border: 1px solid rgba(34,197,94,.2); }
        .status-running .status-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
        .status-stopped { background: var(--red-bg); color: var(--red); border: 1px solid rgba(239,68,68,.2); }
        .status-stopped .status-dot { background: var(--red); }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
        }

        .empty-icon {
            width: 64px;
            height: 64px;
            margin: 0 auto 16px;
            background: var(--bg-hover);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-dim);
        }

        .empty-state h3 {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 6px;
        }

        .empty-state p {
            font-size: 13px;
            color: var(--text-dim);
            margin-bottom: 20px;
        }

        .chart-legend {
            display: flex;
            gap: 16px;
            justify-content: center;
            font-size: 12px;
            color: var(--text-dim);
        }

        .chart-legend .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 4px;
            vertical-align: middle;
        }

        .chart-legend .dot.green { background: var(--green); }
        .chart-legend .dot.gray { background: var(--text-dim); }

        @media (max-width: 1024px) {
            .stat-cards { grid-template-columns: repeat(2, 1fr); }
        }

        @media (max-width: 768px) {
            .overview-grid { grid-template-columns: 1fr; }
            .vps-grid { grid-template-columns: 1fr; }
            .welcome-banner { flex-direction: column; gap: 16px; text-align: center; }
        }
    </style>
</head>
<body>
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('dashboard', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Dashboard', 'dashboard') }}

            <div class="page page-advanced">

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="welcome-banner">
                    <div>
                        <h1>Welcome back, {{ session.get('username') }}!</h1>
                        <p>Manage your virtual private servers from one central dashboard.</p>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <a href="/dashboard" class="btn btn-ghost">
                            <svg width="14" height="14"><use href="#icon-server"/></svg>
                            Manage VPS
                        </a>
                        {% if session.get('is_admin') %}
                        <a href="/admin" class="btn btn-primary">
                            <svg width="14" height="14"><use href="#icon-plus"/></svg>
                            New VPS
                        </a>
                        {% endif %}
                    </div>
                </div>

                <div class="stat-cards">
                    <div class="stat-card">
                        <div class="stat-icon s-white">
                            <svg width="20" height="20"><use href="#icon-server"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total VPS</div>
                            <div class="stat-value">{{ vps_list|length }}</div>
                            <div class="stat-sub">
                                <span class="text-green">{{ vps_list|selectattr('status', 'equalto', 'running')|list|length }} running</span>
                                &middot;
                                <span class="text-red">{{ vps_list|selectattr('status', 'equalto', 'stopped')|list|length }} stopped</span>
                            </div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon s-green">
                            <svg width="20" height="20"><use href="#icon-cpu"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total CPU</div>
                            <div class="stat-value">{{ total_cpu }}</div>
                            <div class="stat-sub">Cores allocated</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon s-yellow">
                            <svg width="20" height="20"><use href="#icon-bolt"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total RAM</div>
                            <div class="stat-value">{{ total_ram }} GB</div>
                            <div class="stat-sub">Memory allocated</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon s-red">
                            <svg width="20" height="20"><use href="#icon-server"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Storage</div>
                            <div class="stat-value">{{ total_storage }} GB</div>
                            <div class="stat-sub">Disk allocated</div>
                        </div>
                    </div>
                </div>

                <div class="overview-grid">
                    <div class="card">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-server"/></svg>
                            VPS Status
                        </div>
                        <div class="chart-legend">
                            <span><span class="dot green"></span> Running: {{ vps_list|selectattr('status', 'equalto', 'running')|list|length }}</span>
                            <span><span class="dot gray"></span> Stopped: {{ vps_list|selectattr('status', 'equalto', 'stopped')|list|length }}</span>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-bolt"/></svg>
                            Resources
                        </div>
                        <div class="resource-bars">
                            <div class="resource-bar-item">
                                <div class="resource-bar-header">
                                    <span>CPU</span>
                                    <span>{{ total_cpu }} cores</span>
                                </div>
                            </div>
                            <div class="resource-bar-item">
                                <div class="resource-bar-header">
                                    <span>RAM</span>
                                    <span>{{ total_ram }} GB</span>
                                </div>
                            </div>
                            <div class="resource-bar-item">
                                <div class="resource-bar-header">
                                    <span>Storage</span>
                                    <span>{{ total_storage }} GB</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {% if vps_list %}
                <div class="search-bar">
                    <input type="text" class="search-input" placeholder="Search by name or IP..." id="searchInput">
                    <select class="search-select" id="statusFilter">
                        <option value="">All Status</option>
                        <option value="running">Running</option>
                        <option value="stopped">Stopped</option>
                    </select>
                </div>

                <div class="vps-grid" id="vpsGrid">
                    {% for vps in vps_list %}
                    <div class="vps-card" data-name="{{ vps['container_name'] }}" data-status="{{ vps['status'] }}" data-id="{{ vps['id'] }}">
                        <div class="vps-card-header">
                            <span class="vps-name">{{ vps['container_name'] }}</span>
                            <div style="display:flex;align-items:center;gap:6px;">
                                {% if vps['shared_by'] %}
                                <span style="background:var(--accent);color:#000;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:500;">Shared</span>
                                {% endif %}
                                <span class="status status-{{ vps['status'] }}">
                                    <span class="status-dot"></span>
                                    {{ vps['status'] }}
                                </span>
                            </div>
                        </div>

                        {% if vps['expires_at'] %}
                        <div style="background:rgba(248,113,113,.1);border:1px solid rgba(248,113,113,.2);border-radius:8px;padding:6px 10px;margin-bottom:8px;font-size:11px;color:var(--red);">
                            Expires: {{ vps['expires_at'][:10] }}
                        </div>
                        {% endif %}

                        <div class="vps-specs">
                            <div class="vps-spec">
                                <span class="vps-spec-label">OS</span>
                                <span class="vps-spec-value">{{ vps['os_type'] }}</span>
                            </div>
                            <div class="vps-spec">
                                <span class="vps-spec-label">RAM</span>
                                <span class="vps-spec-value">{{ vps['ram'] }}</span>
                            </div>
                            <div class="vps-spec">
                                <span class="vps-spec-label">CPU</span>
                                <span class="vps-spec-value">{{ vps['cpu'] }}</span>
                            </div>
                        </div>

                        {% if vps['status'] == 'running' %}
                        <div class="vps-stats" data-vps-id="{{ vps['id'] }}" style="margin-bottom: 12px;">
                            <div class="resource-bars">
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>CPU</span>
                                        <span class="stat-value" id="vps-cpu-{{ vps['id'] }}">Loading...</span>
                                    </div>
                                    <div class="resource-bar-track">
                                        <div class="resource-bar-fill white" id="vps-cpu-bar-{{ vps['id'] }}" style="width: 0%"></div>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>RAM</span>
                                        <span class="stat-value" id="vps-ram-{{ vps['id'] }}">Loading...</span>
                                    </div>
                                    <div class="resource-bar-track">
                                        <div class="resource-bar-fill green" id="vps-ram-bar-{{ vps['id'] }}" style="width: 0%"></div>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>Network</span>
                                        <span class="stat-value" id="vps-net-{{ vps['id'] }}">Loading...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        {% endif %}

                        {% if vps['ssh_command'] %}
                        {% set is_sshx = 'sshx.io' in vps['ssh_command'] %}
                        <div class="ssh-box">
                            <code>{{ vps['ssh_command'] }}</code>
                        </div>
                        <button class="btn btn-ghost btn-sm mb-3" onclick='copyToClipboard({{ vps['ssh_command']|tojson }})' style="width: 100%;">
                            <svg width="14" height="14"><use href="#icon-copy"/></svg>
                            {% if is_sshx %}Copy URL{% else %}Copy SSH command{% endif %}
                        </button>
                        {% endif %}

                        <div class="vps-actions">
                            <a href="/vps/{{ vps['id'] }}" class="btn btn-ghost btn-sm">
                                <svg width="14" height="14"><use href="#icon-terminal"/></svg>
                                Details
                            </a>
                            {% if vps['status'] == 'running' %}
                            <form method="POST" action="/vps/{{ vps['id'] }}/stop" style="flex: 1;">
                                <button type="submit" class="btn btn-yellow btn-sm" style="width: 100%;">
                                    <svg width="14" height="14"><use href="#icon-stop"/></svg>
                                    Stop
                                </button>
                            </form>
                            {% elif vps['status'] == 'stopped' or vps['status'] == 'created' %}
                            <form method="POST" action="/vps/{{ vps['id'] }}/start" style="flex: 1;">
                                <button type="submit" class="btn btn-green btn-sm" style="width: 100%;">
                                    <svg width="14" height="14"><use href="#icon-play"/></svg>
                                    Start
                                </button>
                            </form>
                            {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <div class="card empty-state">
                    <div class="empty-icon">
                        <svg width="28" height="28"><use href="#icon-server"/></svg>
                    </div>
                    <h3>No Virtual Private Servers</h3>
                    <p>You haven't created any VPS instances yet.</p>
                    {% if session.get('is_admin') %}
                    <a href="/admin" class="btn btn-primary btn-lg">
                        <svg width="14" height="14"><use href="#icon-plus"/></svg>
                        Create Your First VPS
                    </a>
                    {% endif %}
                </div>
                {% endif %}
            </div>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    <script>
        document.getElementById('searchInput')?.addEventListener('input', filterVPS);
        document.getElementById('statusFilter')?.addEventListener('change', filterVPS);

        function filterVPS() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            const status = document.getElementById('statusFilter').value;
            document.querySelectorAll('.vps-card').forEach(card => {
                const name = card.dataset.name.toLowerCase();
                const s = card.dataset.status;
                const matchName = !query || name.includes(query);
                const matchStatus = !status || s === status;
                card.style.display = (matchName && matchStatus) ? '' : 'none';
            });
        }

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        function loadVPSStats() {
            document.querySelectorAll('.vps-stats').forEach(el => {
                const vpsId = el.dataset.vpsId;
                fetch('/api/vps/' + vpsId + '/stats')
                    .then(r => r.json())
                    .then(data => {
                        if (data.error) return;
                        const cpuEl = document.getElementById('vps-cpu-' + vpsId);
                        const cpuBar = document.getElementById('vps-cpu-bar-' + vpsId);
                        const ramEl = document.getElementById('vps-ram-' + vpsId);
                        const ramBar = document.getElementById('vps-ram-bar-' + vpsId);
                        const netEl = document.getElementById('vps-net-' + vpsId);
                        if (cpuEl) cpuEl.textContent = data.cpu_percent + '%';
                        if (cpuBar) cpuBar.style.width = Math.min(data.cpu_percent, 100) + '%';
                        if (ramEl) ramEl.textContent = data.memory_used + ' / ' + data.memory_total + ' MB';
                        if (ramBar) ramBar.style.width = Math.min(data.memory_percent, 100) + '%';
                        if (netEl) netEl.textContent = '↓' + formatBytes(data.net_rx) + ' ↑' + formatBytes(data.net_tx);
                    })
                    .catch(() => {});
            });
        }

        loadVPSStats();
        setInterval(loadVPSStats, 5000);
    </script>
</body>
</html>
""", 'admin.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin — {{ settings.site_name if settings else 'Omega Panel' }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        @keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

        .page-advanced { position: relative; }
        .page-advanced::before {
            content: ''; position: fixed; top: 0; left: var(--sidebar-w); right: 0; bottom: 0;
            background: radial-gradient(ellipse 60% 40% at 50% 0%, rgba(255,255,255,.03) 0%, transparent 60%);
            pointer-events: none; z-index: 0;
        }
        .page-advanced > * { position: relative; z-index: 1; }

        .page-header {
            display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px;
        }
        .page-header h1 { font-size: 22px; font-weight: 700; letter-spacing: -.5px; }
        .page-header-sub { font-size: 13px; color: var(--text-dim); margin-top: 2px; }

        .stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
        .stat-card {
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
            padding: 18px; display: flex; align-items: center; gap: 14px;
            transition: all .2s; animation: fadeUp .4s ease both;
        }
        .stat-card:nth-child(1) { animation-delay: .05s; }
        .stat-card:nth-child(2) { animation-delay: .1s; }
        .stat-card:nth-child(3) { animation-delay: .15s; }
        .stat-card:nth-child(4) { animation-delay: .2s; }
        .stat-card:hover { border-color: rgba(255,255,255,.1); transform: translateY(-2px); }

        .stat-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .stat-icon svg { width: 20px; height: 20px; }
        .stat-icon.s-white { background: rgba(255,255,255,.06); color: var(--text); border: 1px solid rgba(255,255,255,.08); }
        .stat-icon.s-green { background: var(--green-bg); color: var(--green); border: 1px solid rgba(34,197,94,.12); }
        .stat-icon.s-yellow { background: var(--yellow-bg); color: var(--yellow); border: 1px solid rgba(234,179,8,.12); }
        .stat-icon.s-red { background: var(--red-bg); color: var(--red); border: 1px solid rgba(239,68,68,.12); }

        .stat-info .stat-label { font-size: 11px; font-weight: 500; color: var(--text-dim); text-transform: uppercase; letter-spacing: .5px; }
        .stat-info .stat-value { font-size: 24px; font-weight: 700; letter-spacing: -.5px; line-height: 1.2; }

        .card {
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
            padding: 20px; position: relative; overflow: hidden;
        }
        .card::before {
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.08), transparent);
        }
        .card-title { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
        .card-title svg { width: 18px; height: 18px; color: var(--text-dim); }

        .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        thead { background: var(--bg-elevated); }
        th { text-align: left; padding: 10px 14px; font-weight: 500; color: var(--text-dim); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; border-bottom: 1px solid var(--border); }
        td { padding: 10px 14px; color: var(--text-muted); border-bottom: 1px solid var(--border); }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: rgba(255,255,255,.03); }

        .status { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 500; padding: 3px 8px; border-radius: 100px; }
        .status-dot { width: 6px; height: 6px; border-radius: 50%; }
        .status-running { background: var(--green-bg); color: var(--green); border: 1px solid rgba(34,197,94,.2); }
        .status-running .status-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
        .status-stopped { background: var(--red-bg); color: var(--red); border: 1px solid rgba(239,68,68,.2); }
        .status-stopped .status-dot { background: var(--red); }

        .empty-state { text-align: center; padding: 60px 20px; }
        .empty-icon { width: 64px; height: 64px; margin: 0 auto 16px; background: var(--bg-hover); border-radius: 16px; display: flex; align-items: center; justify-content: center; color: var(--text-dim); }
        .empty-state h3 { font-size: 15px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
        .empty-state p { font-size: 13px; color: var(--text-dim); margin-bottom: 20px; }

        .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.7); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 200; padding: 20px; }
        .modal-bg.active { display: flex; }
        .modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; width: 100%; max-width: 420px; padding: 24px; box-shadow: 0 4px 24px rgba(0,0,0,.5); }
        .modal-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
        .modal-top h2 { font-size: 15px; font-weight: 600; }
        .modal-x { background: none; border: none; color: var(--text-dim); font-size: 18px; cursor: pointer; padding: 4px; line-height: 1; border-radius: 4px; }
        .modal-x:hover { color: var(--text-muted); background: var(--bg-hover); }

        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; }
        .form-control { width: 100%; padding: 10px 12px; font-size: 14px; font-family: inherit; color: var(--text); background: var(--bg-input); border: 1px solid var(--border); border-radius: 10px; outline: none; transition: all .15s; }
        .form-control:focus { border-color: rgba(255,255,255,.2); }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

        .mb-4 { margin-bottom: 16px; }

        .vps-os-col,.vps-specs-col{display:table-cell}
        .user-email-col,.user-joined-col{display:table-cell}
        @media (max-width: 768px) {
            .stat-cards { grid-template-columns: repeat(2, 1fr); gap: 6px; }
            .page-header { flex-direction: column; gap: 10px; }
            .form-row { grid-template-columns: 1fr; }
            .stat-card { padding: 8px; gap: 6px; }
            .stat-icon { width: 28px; height: 28px; border-radius: 6px; }
            .stat-icon svg { width: 14px; height: 14px; }
            .stat-info .stat-value { font-size: 14px; }
            .stat-info .stat-label { font-size: 9px; }
            .card { padding: 10px; }
            .card-title { font-size: 12px; margin-bottom: 6px; }
            table { font-size: 11px; }
            th, td { padding: 5px 6px; }
            .page-header h1 { font-size: 15px; }
            .page-header-sub { font-size: 10px; }
            .status { padding: 2px 6px; font-size: 9px; }
            .modal { padding: 14px; }
            .form-group { margin-bottom: 8px; }
            .form-control { padding: 7px 9px; font-size: 11px; }
            .vps-os-col,.vps-specs-col{display:none}
            .vps-name{font-size:10px;font-weight:500}
            .vps-detail-mobile{display:block;font-size:9px;color:var(--text-dim);margin-top:1px}
            .user-email-col,.user-joined-col{display:none}
            .user-detail-mobile{display:block;font-size:9px;color:var(--text-dim);margin-top:1px}
            .btn-sm{padding:2px 4px !important;font-size:9px !important;min-width:0 !important;width:auto !important}\\n            .action-btns{flex-direction:column;gap:2px !important;align-items:flex-end}
        }
    </style>
</head>
<body>
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('admin', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Admin Panel', 'admin') }}

            <div class="page page-advanced">

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="page-header">
                    <div>
                        <h1>Administration</h1>
                        <p class="page-header-sub">Manage users, VPS instances, and system settings.</p>
                    </div>
                    <button class="btn btn-primary" onclick="openModal('createModal')">
                        <svg width="14" height="14"><use href="#icon-plus"/></svg>
                        New VPS
                    </button>
                </div>

                <div class="stat-cards">
                    <div class="stat-card">
                        <div class="stat-icon s-white"><svg width="20" height="20"><use href="#icon-users"/></svg></div>
                        <div class="stat-info">
                            <div class="stat-label">Users</div>
                            <div class="stat-value">{{ total_users }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon s-green"><svg width="20" height="20"><use href="#icon-server"/></svg></div>
                        <div class="stat-info">
                            <div class="stat-label">Instances</div>
                            <div class="stat-value">{{ total_vps }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon s-yellow"><svg width="20" height="20"><use href="#icon-play"/></svg></div>
                        <div class="stat-info">
                            <div class="stat-label">Active</div>
                            <div class="stat-value">{{ active_vps }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon s-red"><svg width="20" height="20"><use href="#icon-clock"/></svg></div>
                        <div class="stat-info">
                            <div class="stat-label">Expiring Soon</div>
                            <div class="stat-value">{{ expiring_count }}</div>
                        </div>
                    </div>
                </div>

                <div class="card mb-4">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-server"/></svg>
                        All Instances
                    </div>
                    {% if vps_list %}
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>Name</th>
                                    <th class="vps-os-col">OS</th>
                                    <th class="vps-specs-col">Specs</th>
                                    <th>Status</th>
                                    <th style="text-align: right;">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for vps in vps_list %}
                                <tr>
                                    <td>{{ vps['username'] }}</td>
                                    <td>
                                        <span class="vps-name">{{ vps['container_name'] }}</span>
                                        <span class="vps-detail-mobile">{{ vps['os_type'] }} · {{ vps['ram'] }}/{{ vps['cpu'] }}</span>
                                    </td>
                                    <td class="vps-os-col">{{ vps['os_type'] }}</td>
                                    <td class="vps-specs-col" style="font-size: 12px;">{{ vps['ram'] }} / {{ vps['cpu'] }}</td>
                                    <td>
                                        <span class="status status-{{ vps['status'] }}">
                                            <span class="status-dot"></span>
                                            {{ vps['status'] }}
                                        </span>
                                    </td>
                                    <td style="text-align: right;">
                                        <div class="action-btns">
                                            <a href="/admin/vps/{{ vps['id'] }}" class="btn btn-ghost btn-sm" title="Details">
                                                <svg width="12" height="12"><use href="#icon-terminal"/></svg>
                                            </a>
                                            {% if vps['status'] == 'running' %}
                                            <form method="POST" action="/admin/stop-vps/{{ vps['id'] }}" style="display: inline;">
                                                <button type="submit" class="btn btn-yellow btn-sm" title="Stop">
                                                    <svg width="12" height="12"><use href="#icon-stop"/></svg>
                                                </button>
                                            </form>
                                            {% elif vps['status'] == 'stopped' or vps['status'] == 'created' %}
                                            <form method="POST" action="/admin/start-vps/{{ vps['id'] }}" style="display: inline;">
                                                <button type="submit" class="btn btn-green btn-sm" title="Start">
                                                    <svg width="12" height="12"><use href="#icon-play"/></svg>
                                                </button>
                                            </form>
                                            {% endif %}
                                            <button type="button" class="btn btn-ghost btn-sm" onclick="openEditModal({{ vps['id'] }}, '{{ vps['container_name'] }}' , '{{ vps['ram'] }}' , '{{ vps['cpu'] }}' , '{{ vps['disk'] }}' , {{ vps['max_backups'] }})" title="Edit">
                                                    <svg width="12" height="12"><use href="#icon-edit"/></svg>
                                                </button>
                                            <form method="POST" action="/admin/delete-vps/{{ vps['id'] }}" style="display: inline;">
                                                <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Delete this VPS?')" title="Delete">
                                                    <svg width="12" height="12"><use href="#icon-trash"/></svg>
                                                </button>
                                            </form>
                                        </div>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="empty-state">
                        <div class="empty-icon"><svg width="28" height="28"><use href="#icon-server"/></svg></div>
                        <h3>No instances yet</h3>
                        <p>Create a VPS for a user to get started.</p>
                    </div>
                    {% endif %}
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-users"/></svg>
                        Users
                    </div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th class="user-email-col">Email</th>
                                    <th>Role</th>
                                    <th class="user-joined-col">Joined</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for user in users %}
                                <tr>
                                    <td>
                                        {{ user['username'] }}
                                        <span class="user-detail-mobile">{{ user['email'] }}</span>
                                    </td>
                                    <td class="user-email-col text-dim">{{ user['email'] }}</td>
                                    <td>
                                        {% if user['role'] == 'owner' %}
                                        <span class="status" style="background:rgba(251,191,36,.12);color:var(--yellow);">Owner</span>
                                        {% elif user['is_admin'] %}
                                        <span class="status status-running">Admin</span>
                                        {% else %}
                                        <span class="status status-stopped">User</span>
                                        {% endif %}
                                    </td>
                                    <td class="user-joined-col text-dim">{{ user['created_at'] }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div id="createModal" class="modal-bg">
        <div class="modal">
            <div class="modal-top">
                <h2>New VPS</h2>
                <button class="modal-x" onclick="closeModal('createModal')">&times;</button>
            </div>
            <form method="POST" action="/admin/create-vps">
                <div class="form-group">
                    <label>Assign to</label>
                    <select name="user_id" class="form-control" required>
                        <option value="">Select user</option>
                        {% for user in users %}
                        <option value="{{ user['id'] }}">{{ user['username'] }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>OS</label>
                    <select name="os_type" class="form-control">
                        <option value="ubuntu-22.04">Ubuntu 22.04</option>
                        <option value="ubuntu-24.04">Ubuntu 24.04 (Noble Numbat)</option>
                        <option value="ubuntu-26.04">Ubuntu 26.04 (Resolute Raccoon)</option>
                                                                    </select>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>RAM (MB)</label>
                        <input type="number" name="ram" id="ram-input" class="form-control" value="2048" min="256" placeholder="e.g. 2048" oninput="document.getElementById('ram-hint').textContent = this.value + ' MB = ' + (this.value / 1024).toFixed(1) + ' GB'">
                        <p id="ram-hint" class="text-dim" style="font-size:10px;margin-top:4px;">2048 MB = 2 GB</p>
                    </div>
                    <div class="form-group">
                        <label>CPU (cores)</label>
                        <input type="number" name="cpu" class="form-control" value="1" min="1" max="32" placeholder="e.g. 2">
                    </div>
                </div>
                <div class="form-group">
                    <label>Disk (GB)</label>
                    <input type="number" name="disk" class="form-control" value="20" min="5" placeholder="e.g. 20">
                </div>
                <div class="form-group">
                    <label>Max Backups (0 = disabled)</label>
                    <input type="number" name="max_backups" class="form-control" value="0" min="0" max="10">
                    <p class="text-dim" style="font-size:10px;margin-top:4px;">How many backups the user can create for this VPS</p>
                </div>
                <div class="form-group">
                    <label>Node</label>
                    <select name="node_id" class="form-control">
                        {% for node in nodes %}
                        <option value="{{ node['id'] }}">{{ node['name'] }} ({{ node['hostname'] }}) — {{ node['vps_count'] }}/{{ node['max_vps'] }} VPS</option>
                        {% endfor %}
                    </select>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Deploy VPS</button>
            </form>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>

    <div id="editModal" class="modal-bg">
        <div class="modal">
            <div class="modal-top">
                <h2>Edit VPS — <span id="editModalName"></span></h2>
                <button class="modal-x" onclick="closeEditModal()">&times;</button>
            </div>
            <form method="POST" id="editForm">
                <div class="form-group">
                    <label>RAM (MB)</label>
                    <input type="number" name="ram" id="editRam" class="form-control" min="256" placeholder="e.g. 2048" oninput="document.getElementById('editRamHint').textContent = this.value + ' MB = ' + (this.value / 1024).toFixed(1) + ' GB'">
                        <p id="editRamHint" class="text-dim" style="font-size:10px;margin-top:4px;"></p>
                    </div>
                <div class="form-group">
                    <label>CPU (cores)</label>
                    <input type="number" name="cpu" id="editCpu" class="form-control" min="1" max="32" placeholder="e.g. 2">
                </div>
                <div class="form-group">
                    <label>Disk (GB)</label>
                    <input type="number" name="disk" id="editDisk" class="form-control" min="5" placeholder="e.g. 20">
                </div>
                <div class="form-group">
                    <label>Max Backups</label>
                    <input type="number" name="max_backups" id="editMaxBackups" class="form-control">
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%;">Save Changes</button>
            </form>
        </div>
    </div>
    <script>
    function openEditModal(id, name, ram, cpu, disk, maxb) {
        document.getElementById("editModal").classList.add("active");
        document.getElementById("editModalName").textContent = name;
        document.getElementById("editForm").action = "/admin/vps/" + id + "/update";
        var ramVal = ram && ram.includes('GB') ? (parseFloat(ram) * 1024) : (parseInt(ram) || 0);
        document.getElementById("editRam").value = ramVal;
        document.getElementById("editRamHint").textContent = ramVal + ' MB = ' + (ramVal / 1024).toFixed(1) + ' GB';
        document.getElementById("editCpu").value = parseInt(cpu) || cpu.replace(/[^0-9]/g, '');
        document.getElementById("editDisk").value = parseInt(disk) || disk.replace(/[^0-9]/g, '');
        document.getElementById("editMaxBackups").value = maxb;
    }
    function closeEditModal() {
        document.getElementById("editModal").classList.remove("active");
    }
    </script></body>
</html>
""", 'admin_vps_detail.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ vps['container_name'] }} — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .info-list{display:flex;flex-direction:column;gap:12px}
        .info-item{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}
        .info-item:last-child{border-bottom:none}
        .info-label{font-size:12px;color:var(--text-dim)}
        .info-value{font-size:13px;color:var(--text);font-weight:500}
        .vps-specs{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
        .vps-spec{text-align:center;padding:12px;background:var(--bg-input);border-radius:10px;border:1px solid var(--border);transition:border-color .2s}
        .vps-spec:hover{border-color:rgba(255,255,255,.1)}
        .vps-spec-label{font-size:11px;color:var(--text-dim);display:block;margin-bottom:4px}
        .vps-spec-value{font-size:16px;font-weight:700;color:var(--text)}
        .resource-bars{display:flex;flex-direction:column;gap:14px}
        .resource-bar-header{display:flex;justify-content:space-between;font-size:12px;color:var(--text-muted);margin-bottom:6px}
        .resource-bar-track{height:6px;background:var(--bg-input);border-radius:10px;overflow:hidden}
        .resource-bar-fill{height:100%;border-radius:10px;transition:width .6s ease}
        .resource-bar-fill.blue{background:linear-gradient(90deg,#60a5fa,#3b82f6)}
        .resource-bar-fill.green{background:linear-gradient(90deg,#34d399,#10b981)}
        .resource-bar-fill.yellow{background:linear-gradient(90deg,#fbbf24,#f59e0b)}
        .resource-bar-fill.red{background:linear-gradient(90deg,#f87171,#ef4444)}
        .ssh-box{background:var(--bg-input);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:10px;font-size:12px;color:var(--text);overflow-x:auto;white-space:nowrap;font-family:monospace}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;border:none;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;text-decoration:none}
        .btn-green{background:rgba(52,211,153,.15);color:var(--green);border:1px solid rgba(52,211,153,.2)}
        .btn-green:hover{background:rgba(52,211,153,.25)}
        .btn-yellow{background:rgba(251,191,36,.15);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
        .btn-yellow:hover{background:rgba(251,191,36,.25)}
        .btn-red{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn-red:hover{background:rgba(248,113,113,.25)}
        .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)}
        .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
        .btn-sm{padding:6px 10px;font-size:12px}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .status-creating{background:rgba(251,191,36,.12);color:var(--yellow)}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .alert{padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:16px;border:1px solid}
        .alert-success{background:rgba(52,211,153,.08);border-color:rgba(52,211,153,.2);color:var(--green)}
        .alert-error{background:rgba(248,113,113,.08);border-color:rgba(248,113,113,.2);color:var(--red)}
        .alert-info{background:rgba(255,255,255,.04);border-color:var(--border);color:var(--text-muted)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @media (max-width: 768px) {
            .info-item { flex-direction: column; align-items: flex-start; gap: 4px; }
        }
        @media (max-width: 480px) {
            .vps-specs { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('allvps', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar(vps['container_name'], 'allvps') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin/all-vps">All VPS</a>
                    <span class="sep">></span>
                    <span class="current">{{ vps['container_name'] }}</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>{{ vps['container_name'] }}</h1>
                        <p class="page-header-sub">
                            Owned by <strong style="color:var(--text)">{{ vps['username'] }}</strong> &middot;
                            <span id="status-badge" class="status status-{{ container_status }}">
                                <span class="status-dot"></span>
                                {{ container_status }}
                            </span>
                        </p>
                    </div>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="detail-grid">
                    <div style="display:flex;flex-direction:column;gap:12px;">
                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-server"/></svg>
                                Instance Info
                            </div>
                            <div class="info-list">
                                <div class="info-item">
                                    <span class="info-label">Container ID</span>
                                    <span class="info-value">{{ vps['container_id'][:12] if vps['container_id'] else '—' }}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Container name</span>
                                    <span class="info-value">{{ vps['container_name'] }}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Operating system</span>
                                    <span class="info-value">{{ vps['os_type'] }}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Owner</span>
                                    <span class="info-value">{{ vps['username'] }}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Created</span>
                                    <span class="info-value">{{ vps['created_at'] }}</span>
                                </div>
                            </div>
                        </div>

                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-cpu"/></svg>
                                Specs
                            </div>
                            <div class="vps-specs">
                                <div class="vps-spec">
                                    <span class="vps-spec-label">RAM</span>
                                    <span class="vps-spec-value">{{ vps['ram'] }}</span>
                                </div>
                                <div class="vps-spec">
                                    <span class="vps-spec-label">CPU</span>
                                    <span class="vps-spec-value">{{ vps['cpu'] }}</span>
                                </div>
                                <div class="vps-spec">
                                    <span class="vps-spec-label">Disk</span>
                                    <span class="vps-spec-value">{{ vps['disk'] }}</span>
                                </div>
                            </div>
                        </div>

                        {% if container_status == 'running' %}
                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-cpu"/></svg>
                                Live Container Stats
                            </div>
                            <div class="resource-bars" id="liveStats">
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>CPU Usage</span>
                                        <span id="live-cpu">Loading...</span>
                                    </div>
                                    <div class="resource-bar-track">
                                        <div class="resource-bar-fill blue" id="live-cpu-bar" style="width:0%"></div>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>Memory Usage</span>
                                        <span id="live-ram">Loading...</span>
                                    </div>
                                    <div class="resource-bar-track">
                                        <div class="resource-bar-fill green" id="live-ram-bar" style="width:0%"></div>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>Network I/O</span>
                                        <span id="live-net">Loading...</span>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>Processes</span>
                                        <span id="live-pids">Loading...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        {% endif %}

                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-key"/></svg>
                                SSHx Access
                            </div>
                            {% if vps['ssh_command'] %}
                            {% if vps['ssh_password'] %}
                            <p class="text-dim" style="font-size:12px;margin-bottom:6px;">SSH command:</p>
                            <div class="ssh-box">
                                <code>{{ vps['ssh_command'] }}</code>
                            </div>
                            <p class="text-dim" style="font-size:12px;margin-bottom:6px;margin-top:6px;">Password: <strong>{{ vps['ssh_password'] }}</strong></p>
                            {% else %}
                            <p class="text-dim" style="font-size:12px;margin-bottom:10px;">Open this link to connect:</p>
                            <div class="ssh-box">
                                <code>{{ vps['ssh_command'] }}</code>
                            </div>
                            <button class="btn btn-ghost btn-sm" onclick='copyToClipboard({{ vps['ssh_command']|tojson }})' style="width:100%;">
                                <svg width="14" height="14"><use href="#icon-copy"/></svg>
                                Copy URL
                            </button>
                            {% endif %}
                            {% else %}
                            <p class="text-dim" style="font-size:13px;">Start the instance to get SSH credentials.</p>
                            {% endif %}
                        </div>

                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-shield"/></svg>
                                Credentials
                            </div>
                            <div class="info-list">
                                <div class="info-item">
                                    <span class="info-label">User</span>
                                    <span class="info-value">root</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Password</span>
                                    <span class="info-value">root</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">SSH port</span>
                                    <span class="info-value">22</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div>
                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-settings"/></svg>
                                Admin Actions
                            </div>
                            <div style="display:flex;flex-direction:column;gap:8px;">
                                {% if container_status == 'running' %}
                                <form method="POST" action="/admin/stop-vps/{{ vps['id'] }}">
                                    <button type="submit" class="btn btn-yellow" style="width:100%;">
                                        <svg width="14" height="14"><use href="#icon-stop"/></svg>
                                        Stop instance
                                    </button>
                                </form>
                                <form method="POST" action="/admin/restart-vps/{{ vps['id'] }}">
                                    <button type="submit" class="btn btn-ghost" style="width:100%;">
                                        <svg width="14" height="14"><use href="#icon-restart"/></svg>
                                        Restart instance
                                    </button>
                                </form>
                                {% elif container_status == 'stopped' or container_status == 'exited' or container_status == 'created' or container_status == 'not_found' %}
                                <form method="POST" action="/admin/start-vps/{{ vps['id'] }}">
                                    <button type="submit" class="btn btn-green" style="width:100%;">
                                        <svg width="14" height="14"><use href="#icon-play"/></svg>
                                        Start instance
                                    </button>
                                </form>
                                {% endif %}

                                {% if container_status == 'running' %}
                                <form method="POST" action="/admin/vps/{{ vps['id'] }}/regen-ssh">
                                    <button type="submit" class="btn btn-ghost btn-sm" style="width:100%;">
                                        <svg width="12" height="12"><use href="#icon-key"/></svg>
                                        Regenerate SSH
                                    </button>
                                </form>
                                {% endif %}

                                {% if container_status == 'running' %}
                                <a href="/vps/{{ vps['id'] }}/files" class="btn btn-ghost btn-sm" style="width:100%;text-align:center;">
                                    <svg width="12" height="12"><use href="#icon-server"/></svg>
                                    File Manager
                                </a>
                                <a href="/vps/{{ vps['id'] }}/processes" class="btn btn-ghost btn-sm" style="width:100%;text-align:center;">
                                    <svg width="12" height="12"><use href="#icon-cpu"/></svg>
                                    Process Manager
                                </a>
                                <a href="/vps/{{ vps['id'] }}/terminal" class="btn btn-ghost btn-sm" style="width:100%;text-align:center;">
                                    <svg width="12" height="12"><use href="#icon-terminal"/></svg>
                                    Terminal
                                </a>
                                {% endif %}

                                <form method="POST" action="/admin/delete-vps/{{ vps['id'] }}">
                                    <button type="submit" class="btn btn-red" style="width:100%;" onclick="return confirm('Delete this VPS?')">
                                        <svg width="14" height="14"><use href="#icon-trash"/></svg>
                                        Delete instance
                                    </button>
                                </form>
                            </div>
                        </div>

                        <div class="card fade-in" style="margin-top:12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-users"/></svg>
                                Transfer VPS
                            </div>
                            <p style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">Transfer this VPS to another user.</p>
                            <form method="POST" action="/admin/vps/{{ vps['id'] }}/transfer">
                                <div style="display:flex;gap:6px;">
                                    <input type="text" name="target_username" class="form-control" placeholder="Username" required style="flex:1;padding:6px 8px;font-size:12px;">
                                    <button type="submit" class="btn btn-ghost btn-sm" onclick="return confirm('Transfer this VPS?')">Transfer</button>
                                </div>
                            </form>
                        </div>

                        <div class="card fade-in" style="margin-top:12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-users"/></svg>
                                Share VPS
                            </div>
                            <p style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">Share this VPS with another user. Both can access it.</p>
                            <form method="POST" action="/admin/vps/{{ vps['id'] }}/share">
                                <div style="display:flex;gap:6px;">
                                    <input type="text" name="target_username" class="form-control" placeholder="Username" required style="flex:1;padding:6px 8px;font-size:12px;">
                                    <button type="submit" class="btn btn-ghost btn-sm">Share</button>
                                </div>
                            </form>
                            {% if shares %}
                            <div style="margin-top:10px;">
                                <div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">Shared with:</div>
                                {% for s in shares %}
                                <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);">
                                    <span style="font-size:12px;">{{ s['username'] }}</span>
                                    <form method="POST" action="/admin/vps/{{ vps['id'] }}/unshare/{{ s['id'] }}">
                                        <button type="submit" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px;" onclick="return confirm('Remove share?')">Remove</button>
                                    </form>
                                </div>
                                {% endfor %}
                            </div>
                            {% endif %}
                        </div>

                        <div class="card fade-in" style="margin-top:12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-restart"/></svg>
                                Reinstall OS
                            </div>
                            <p style="font-size:11px;color:var(--red);margin-bottom:10px;">⚠ This will erase all data on this VPS.</p>
                            <form method="POST" action="/admin/vps/{{ vps['id'] }}/reinstall">
                                <div style="margin-bottom:10px;">
                                    <select name="os_type" class="form-control" style="width:100%;padding:8px 10px;font-size:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);">
                                        <option value="ubuntu-22.04" {{ 'selected' if vps['os_type'] == 'ubuntu-22.04' }}>Ubuntu 22.04</option>
                                        <option value="ubuntu-24.04" {{ 'selected' if vps['os_type'] == 'ubuntu-24.04' }}>Ubuntu 24.04 (Noble Numbat)</option>
                                        <option value="ubuntu-26.04" {{ 'selected' if vps['os_type'] == 'ubuntu-26.04' }}>Ubuntu 26.04 (Resolute Raccoon)</option>
                                                                                                                    </select>
                                </div>
                                <button type="submit" class="btn btn-red" style="width:100%;" onclick="return confirm('Reinstall this VPS? All data will be lost.')">
                                    <svg width="14" height="14"><use href="#icon-restart"/></svg>
                                    Reinstall OS
                                </button>
                            </form>
                        </div>

                        <div class="card fade-in" style="margin-top:12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-clock"/></svg>
                                Expiration
                            </div>
                            {% if vps['expires_at'] %}
                            <div style="margin-bottom:10px;">
                                <p style="font-size:12px;color:var(--text);">Expires: <strong>{{ vps['expires_at'] }}</strong></p>
                            </div>
                            {% else %}
                            <p style="font-size:12px;color:var(--text-dim);margin-bottom:10px;">No expiration set (runs forever)</p>
                            {% endif %}
                            <form method="POST" action="/admin/vps/{{ vps['id'] }}/set-expiry" style="margin-bottom:8px;">
                                <div style="display:flex;gap:6px;">
                                    <input type="datetime-local" name="expires_at" class="form-control" style="flex:1;padding:6px 8px;font-size:12px;" value="{{ vps['expires_at'][:16] if vps['expires_at'] else '' }}">
                                    <button type="submit" class="btn btn-ghost btn-sm">Set</button>
                                </div>
                            </form>
                            {% if vps['expires_at'] %}
                            <form method="POST" action="/admin/vps/{{ vps['id'] }}/clear-expiry">
                                <button type="submit" class="btn btn-ghost btn-sm" style="width:100%;">Clear Expiration</button>
                            </form>
                            {% endif %}
                        </div>

                        <div class="card fade-in" style="margin-top:12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-key"/></svg>
                                Snapshots
                            </div>
                            {% if vps['max_backups'] != 0 %}<form method="POST" action="/admin/vps/{{ vps['id'] }}/backup" style="margin-bottom:10px;">
                                <div style="display:flex;gap:6px;">
                                <input type="text" name="name" class="form-control" placeholder="Snapshot name" style="flex:1;padding:6px 8px;font-size:12px;">
                                <button type="submit" class="btn btn-ghost btn-sm">Create</button>
                                </div>
                            </form>{% else %}
                            <p class="text-dim" style="font-size:12px;">Backups are disabled for this VPS.</p>
                            {% endif %}
{% if snapshots %}
                            <div style="display:flex;flex-direction:column;gap:6px;">
{% for s in snapshots %}
                                <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:var(--bg-input);border-radius:8px;font-size:12px;">
                                <div>
                                <div style="font-weight:500;">{{ s['name'] }}</div>
                                <div style="color:var(--text-dim);font-size:11px;">{{ s['created_at'][:16] }}</div>
                                </div>
                                <div style="display:flex;gap:4px;">
                                <form method="POST" action="/admin/vps/{{ vps['id'] }}/backup/{{ s['name'] }}/restore" style="display:inline;">
                                <button type="submit" class="btn btn-ghost btn-sm" onclick="return confirm('Restore this snapshot? Current data will be replaced.')" title="Restore">Restore</button>
                                </form>
                                <form method="POST" action="/admin/vps/{{ vps['id'] }}/backup/{{ s['name'] }}/delete" style="display:inline;">
                                <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Delete this snapshot?')" title="Delete">
                                <svg width="12" height="12"><use href="#icon-trash"/></svg>
                                </button>
                                </form>
                                </div>
                                </div>
{% endfor %}
                            </div>
{% else %}
                            <p style="font-size:12px;color:var(--text-dim);text-align:center;padding:10px;">No snapshots yet</p>
{% endif %}
                            </div>             </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    <script>
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        function refreshStatus() {
            fetch('/api/vps/{{ vps["id"] }}/status')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('status-badge');
                    const s = data.status === 'running' ? 'running' : 'stopped';
                    badge.className = `status status-${s}`;
                    badge.innerHTML = `<span class="status-dot"></span>${data.status}`;
                });
        }

        function loadContainerStats() {
            fetch('/api/vps/{{ vps["id"] }}/stats')
                .then(r => r.json())
                .then(data => {
                    if (data.error) return;
                    
                    const cpuEl = document.getElementById('live-cpu');
                    const cpuBar = document.getElementById('live-cpu-bar');
                    const ramEl = document.getElementById('live-ram');
                    const ramBar = document.getElementById('live-ram-bar');
                    const netEl = document.getElementById('live-net');
                    const pidsEl = document.getElementById('live-pids');

                    if (cpuEl) cpuEl.textContent = data.cpu_percent + '%';
                    if (cpuBar) cpuBar.style.width = Math.min(data.cpu_percent, 100) + '%';
                    if (ramEl) ramEl.textContent = data.memory_used + ' / ' + data.memory_total + ' MB (' + data.memory_percent + '%)';
                    if (ramBar) ramBar.style.width = Math.min(data.memory_percent, 100) + '%';
                    if (netEl) netEl.textContent = '↓' + formatBytes(data.net_rx) + ' ↑' + formatBytes(data.net_tx);
                    if (pidsEl) pidsEl.textContent = data.pids + ' processes';
                })
                .catch(() => {});
        }

        refreshStatus();
        loadContainerStats();
        setInterval(refreshStatus, 5000);
        setInterval(loadContainerStats, 5000);
    </script>
</body>
</html>
""", 'vps_detail.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ vps['container_name'] }} — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced {
            background: var(--bg);
            background-image:
                radial-gradient(ellipse 80% 50% at 50% -20%, rgba(255,255,255,0.03), transparent);
            min-height: 100vh;
        }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            position: relative;
            transition: transform .2s, box-shadow .2s, border-color .2s;
        }
        .card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 2px;
            border-radius: 12px 12px 0 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.08), transparent);
        }
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            border-color: var(--border-focus);
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            transition: transform .2s, box-shadow .2s;
        }
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(0,0,0,0.25);
        }
        .card-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card-title svg { color: var(--text-muted); }
        .info-list { display: flex; flex-direction: column; gap: 12px; }
        .info-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
        }
        .info-item:last-child { border-bottom: none; }
        .info-label { font-size: 12px; color: var(--text-dim); }
        .info-value { font-size: 13px; color: var(--text); font-weight: 500; }
        .vps-specs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
        .vps-spec {
            text-align: center;
            padding: 12px;
            background: var(--bg-input);
            border-radius: 10px;
            border: 1px solid var(--border);
            transition: border-color .2s;
        }
        .vps-spec:hover { border-color: rgba(255,255,255,0.1); }
        .vps-spec-label { font-size: 11px; color: var(--text-dim); display: block; margin-bottom: 4px; }
        .vps-spec-value { font-size: 16px; font-weight: 700; color: var(--text); }
        .resource-bars { display: flex; flex-direction: column; gap: 14px; }
        .resource-bar-header {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 6px;
        }
        .resource-bar-track {
            height: 6px;
            background: var(--bg-input);
            border-radius: 10px;
            overflow: hidden;
        }
        .resource-bar-fill {
            height: 100%;
            border-radius: 10px;
            transition: width .6s ease;
        }
        .resource-bar-fill.blue { background: linear-gradient(90deg, #60a5fa, #3b82f6); }
        .resource-bar-fill.green { background: linear-gradient(90deg, #34d399, #10b981); }
        .resource-bar-fill.yellow { background: linear-gradient(90deg, #fbbf24, #f59e0b); }
        .resource-bar-fill.red { background: linear-gradient(90deg, #f87171, #ef4444); }
        .ssh-box {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
            font-size: 12px;
            color: var(--text);
            overflow-x: auto;
            white-space: nowrap;
            font-family: monospace;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 8px 16px;
            border: none;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all .15s;
            text-decoration: none;
        }
        .btn-green { background: rgba(52,211,153,0.15); color: var(--green); border: 1px solid rgba(52,211,153,0.2); }
        .btn-green:hover { background: rgba(52,211,153,0.25); }
        .btn-yellow { background: rgba(251,191,36,0.15); color: var(--yellow); border: 1px solid rgba(251,191,36,0.2); }
        .btn-yellow:hover { background: rgba(251,191,36,0.25); }
        .btn-red { background: rgba(248,113,113,0.15); color: var(--red); border: 1px solid rgba(248,113,113,0.2); }
        .btn-red:hover { background: rgba(248,113,113,0.25); }
        .btn-ghost { background: rgba(255,255,255,0.04); color: var(--text-muted); border: 1px solid var(--border); }
        .btn-ghost:hover { background: rgba(255,255,255,0.08); color: var(--text); }
        .btn-sm { padding: 6px 10px; font-size: 12px; }
        .status {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: currentColor;
        }
        .status-running { background: rgba(52,211,153,0.12); color: var(--green); }
        .status-stopped { background: rgba(248,113,113,0.12); color: var(--red); }
        .status-creating { background: rgba(251,191,36,0.12); color: var(--yellow); }
        .page-header h1 { font-size: 22px; font-weight: 700; color: var(--text); }
        .page-header-sub { font-size: 13px; color: var(--text-dim); margin-top: 4px; }
        .breadcrumbs { font-size: 12px; color: var(--text-dim); margin-bottom: 16px; }
        .breadcrumbs a { color: var(--text-muted); text-decoration: none; transition: color .15s; }
        .breadcrumbs a:hover { color: var(--text); }
        .breadcrumbs .sep { margin: 0 6px; }
        .breadcrumbs .current { color: var(--text); }
        .alert {
            padding: 12px 16px;
            border-radius: 10px;
            font-size: 13px;
            margin-bottom: 16px;
            border: 1px solid;
        }
        .alert-success { background: rgba(52,211,153,0.08); border-color: rgba(52,211,153,0.2); color: var(--green); }
        .alert-error { background: rgba(248,113,113,0.08); border-color: rgba(248,113,113,0.2); color: var(--red); }
        .alert-info { background: rgba(255,255,255,0.04); border-color: var(--border); color: var(--text-muted); }
        .text-dim { color: var(--text-dim); }
        .fade-in { animation: fadeIn .4s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @media (max-width: 768px) {
            .info-item { flex-direction: column; align-items: flex-start; gap: 4px; }
        }
        @media (max-width: 480px) {
            .vps-specs { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('myvps', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar(vps['container_name'], 'myvps') }}

            <div class="page" style="padding: 24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/dashboard">My VPS</a>
                    <span class="sep">></span>
                    <span class="current">{{ vps['container_name'] }}</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>{{ vps['container_name'] }}</h1>
                        <p class="page-header-sub">
                            <span id="status-badge" class="status status-{{ container_status }}">
                                <span class="status-dot"></span>
                                {{ container_status }}
                            </span>
                            {% if shared_by %}
                            <span style="background:var(--accent);color:#000;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;">Shared by {{ shared_by }}</span>
                            {% endif %}
                            {% if not is_owner %}
                            <span style="background:var(--accent);color:#000;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;">Shared with you</span>
                            {% endif %}
                        </p>
                    </div>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="detail-grid">
                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-server"/></svg>
                                Instance Info
                            </div>
                            <div class="info-list">
                                <div class="info-item">
                                    <span class="info-label">Container ID</span>
                                    <span class="info-value">{{ vps['container_id'][:12] if vps['container_id'] else '—' }}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Container name</span>
                                    <span class="info-value">{{ vps['container_name'] }}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Operating system</span>
                                    <span class="info-value">{{ vps['os_type'] }}</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Created</span>
                                    <span class="info-value">{{ vps['created_at'] }}</span>
                                </div>
                            </div>
                        </div>

                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-cpu"/></svg>
                                Specs
                            </div>
                            <div class="vps-specs">
                                <div class="vps-spec">
                                    <span class="vps-spec-label">RAM</span>
                                    <span class="vps-spec-value">{{ vps['ram'] }}</span>
                                </div>
                                <div class="vps-spec">
                                    <span class="vps-spec-label">CPU</span>
                                    <span class="vps-spec-value">{{ vps['cpu'] }}</span>
                                </div>
                                <div class="vps-spec">
                                    <span class="vps-spec-label">Disk</span>
                                    <span class="vps-spec-value">{{ vps['disk'] }}</span>
                                </div>
                            </div>
                        </div>

                        {% if container_status == 'running' %}
                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-activity"/></svg>
                                Live Container Stats
                            </div>
                            <div class="resource-bars" id="liveStats">
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>CPU Usage</span>
                                        <span id="live-cpu">Loading...</span>
                                    </div>
                                    <div class="resource-bar-track">
                                        <div class="resource-bar-fill blue" id="live-cpu-bar" style="width: 0%"></div>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>Memory Usage</span>
                                        <span id="live-ram">Loading...</span>
                                    </div>
                                    <div class="resource-bar-track">
                                        <div class="resource-bar-fill green" id="live-ram-bar" style="width: 0%"></div>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>Network I/O</span>
                                        <span id="live-net">Loading...</span>
                                    </div>
                                </div>
                                <div class="resource-bar-item">
                                    <div class="resource-bar-header">
                                        <span>Processes</span>
                                        <span id="live-pids">Loading...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        {% endif %}

                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-key"/></svg>
                                SSHx Access
                            </div>
                            {% if vps['ssh_command'] %}
                            {% if vps['ssh_password'] %}
                            <p class="text-dim" style="font-size:12px;margin-bottom:6px;">SSH command:</p>
                            <div class="ssh-box">
                                <code>{{ vps['ssh_command'] }}</code>
                            </div>
                            <p class="text-dim" style="font-size:12px;margin-bottom:6px;margin-top:6px;">Password: <strong>{{ vps['ssh_password'] }}</strong></p>
                            {% else %}
                            <p class="text-dim" style="font-size:12px;margin-bottom:10px;">Open this link to connect:</p>
                            <div class="ssh-box">
                                <code>{{ vps['ssh_command'] }}</code>
                            </div>
                            <button class="btn btn-ghost btn-sm" onclick='copyToClipboard({{ vps['ssh_command']|tojson }})' style="width:100%;">
                                <svg width="14" height="14"><use href="#icon-copy"/></svg>
                                Copy URL
                            </button>
                            {% endif %}
                            {% else %}
                            <p class="text-dim" style="font-size:13px;">Start the instance to get SSH credentials.</p>
                            {% endif %}
                        </div>

                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-shield"/></svg>
                                Credentials
                            </div>
                            <div class="info-list">
                                <div class="info-item">
                                    <span class="info-label">User</span>
                                    <span class="info-value">root</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">Password</span>
                                    <span class="info-value">root</span>
                                </div>
                                <div class="info-item">
                                    <span class="info-label">SSH port</span>
                                    <span class="info-value">22</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div>
                        <div class="card fade-in">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-settings"/></svg>
                                Actions
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 8px;">
                                {% if container_status == 'running' %}
                                <form method="POST" action="/vps/{{ vps['id'] }}/stop">
                                    <button type="submit" class="btn btn-yellow" style="width: 100%;">
                                        <svg width="14" height="14"><use href="#icon-stop"/></svg>
                                        Stop instance
                                    </button>
                                </form>
                                <form method="POST" action="/vps/{{ vps['id'] }}/restart">
                                    <button type="submit" class="btn btn-ghost" style="width: 100%;">
                                        <svg width="14" height="14"><use href="#icon-restart"/></svg>
                                        Restart instance
                                    </button>
                                </form>
                                {% elif container_status == 'stopped' or container_status == 'exited' or container_status == 'created' or container_status == 'not_found' %}
                                <form method="POST" action="/vps/{{ vps['id'] }}/start">
                                    <button type="submit" class="btn btn-green" style="width: 100%;">
                                        <svg width="14" height="14"><use href="#icon-play"/></svg>
                                        Start instance
                                    </button>
                                </form>
                                {% endif %}

                                {% if container_status == 'running' %}
                                <form method="POST" action="/vps/{{ vps['id'] }}/regen-ssh">
                                    <button type="submit" class="btn btn-ghost btn-sm" style="width: 100%;">
                                        <svg width="12" height="12"><use href="#icon-key"/></svg>
                                        Regenerate SSH
                                    </button>
                                </form>
                                {% endif %}

                                {% if container_status == 'running' %}
                                <a href="/vps/{{ vps['id'] }}/files" class="btn btn-ghost btn-sm" style="width:100%;text-align:center;">
                                    <svg width="12" height="12"><use href="#icon-server"/></svg>
                                    File Manager
                                </a>
                                <a href="/vps/{{ vps['id'] }}/processes" class="btn btn-ghost btn-sm" style="width:100%;text-align:center;">
                                    <svg width="12" height="12"><use href="#icon-cpu"/></svg>
                                    Process Manager
                                </a>
                                <a href="/vps/{{ vps['id'] }}/terminal" class="btn btn-ghost btn-sm" style="width:100%;text-align:center;">
                                    <svg width="12" height="12"><use href="#icon-terminal"/></svg>
                                    Terminal
                                </a>
                                {% endif %}
                            </div>
                        </div>

                        {% if is_owner %}
                        <div class="card fade-in" style="margin-top: 12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-restart"/></svg>
                                Reinstall OS
                            </div>
                            <p style="font-size: 11px; color: var(--red); margin-bottom: 10px;">⚠ This will erase all data on this VPS.</p>
                            <form method="POST" action="/vps/{{ vps['id'] }}/reinstall">
                                <div style="margin-bottom: 10px;">
                                    <select name="os_type" style="width: 100%; padding: 8px 10px; font-size: 12px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; color: var(--text);">
                                        <option value="ubuntu-22.04" {{ 'selected' if vps['os_type'] == 'ubuntu-22.04' }}>Ubuntu 22.04</option>
                                        <option value="ubuntu-24.04" {{ 'selected' if vps['os_type'] == 'ubuntu-24.04' }}>Ubuntu 24.04 (Noble Numbat)</option>
                                        <option value="ubuntu-26.04" {{ 'selected' if vps['os_type'] == 'ubuntu-26.04' }}>Ubuntu 26.04 (Resolute Raccoon)</option>
                                                                                                                    </select>
                                </div>
                                <button type="submit" class="btn btn-red" style="width: 100%;" onclick="return confirm('Reinstall this VPS? All data will be lost.')">
                                    <svg width="14" height="14"><use href="#icon-restart"/></svg>
                                    Reinstall OS
                                </button>
                            </form>
                        </div>
                        {% endif %}

                        {% if is_owner %}
                        <div class="card fade-in" style="margin-top: 12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-users"/></svg>
                                Transfer VPS
                            </div>
                            <p style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">Transfer this VPS to another user. You will lose access.</p>
                            <form method="POST" action="/vps/{{ vps['id'] }}/transfer">
                                <div style="display:flex;gap:6px;">
                                    <input type="text" name="target_username" class="form-control" placeholder="Username" required style="flex:1;padding:6px 8px;font-size:12px;">
                                    <button type="submit" class="btn btn-ghost btn-sm" onclick="return confirm('Transfer this VPS? You will lose access.')">Transfer</button>
                                </div>
                            </form>
                        </div>

                        <div class="card fade-in" style="margin-top: 12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-users"/></svg>
                                Share VPS
                            </div>
                            <p style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">Share this VPS with another user. Both can access it.</p>
                            <form method="POST" action="/vps/{{ vps['id'] }}/share">
                                <div style="display:flex;gap:6px;">
                                    <input type="text" name="target_username" class="form-control" placeholder="Username" required style="flex:1;padding:6px 8px;font-size:12px;">
                                    <button type="submit" class="btn btn-ghost btn-sm">Share</button>
                                </div>
                            </form>
                            {% if shares %}
                            <div style="margin-top:10px;">
                                <div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">Shared with:</div>
                                {% for s in shares %}
                                <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);">
                                    <span style="font-size:12px;">{{ s['username'] }}</span>
                                    <form method="POST" action="/vps/{{ vps['id'] }}/unshare/{{ s['id'] }}">
                                        <button type="submit" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px;" onclick="return confirm('Remove share?')">Remove</button>
                                    </form>
                                </div>
                                {% endfor %}
                            </div>
                            {% endif %}
                        </div>
                        {% endif %}

                        {% if snapshots or True %}
                        <div class="card fade-in" style="margin-top:12px;">
                            <div class="card-title">
                                <svg width="18" height="18"><use href="#icon-key"/></svg>
                                Snapshots
                            </div>
                            {% if vps['max_backups'] != 0 %}<form method="POST" action="/vps/{{ vps['id'] }}/backup" style="margin-bottom:10px;">
                                <div style="display:flex;gap:6px;">
                                <input type="text" name="name" class="form-control" placeholder="Snapshot name" style="flex:1;padding:6px 8px;font-size:12px;">
                                <button type="submit" class="btn btn-ghost btn-sm">Create</button>
                                </div>
                            </form>{% else %}
                            <p class="text-dim" style="font-size:12px;">Backups are disabled for this VPS.</p>
                            {% endif %}
{% if snapshots %}
                            <div style="display:flex;flex-direction:column;gap:6px;">
{% for s in snapshots %}
                                <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:var(--bg-input);border-radius:8px;font-size:12px;">
                                <div>
                                <div style="font-weight:500;">{{ s['name'] }}</div>
                                <div style="color:var(--text-dim);font-size:11px;">{{ s['created_at'][:16] }}</div>
                                </div>
                                <div style="display:flex;gap:4px;">
                                <form method="POST" action="/vps/{{ vps['id'] }}/backup/{{ s['name'] }}/restore" style="display:inline;">
                                <button type="submit" class="btn btn-ghost btn-sm" onclick="return confirm('Restore this snapshot? Current data will be replaced.')" title="Restore">Restore</button>
                                </form>
                                <form method="POST" action="/vps/{{ vps['id'] }}/backup/{{ s['name'] }}/delete" style="display:inline;">
                                <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Delete this snapshot?')" title="Delete">
                                <svg width="12" height="12"><use href="#icon-trash"/></svg>
                                </button>
                                </form>
                                </div>
                                </div>
{% endfor %}
                            </div>
{% else %}
                            <p style="font-size:12px;color:var(--text-dim);text-align:center;padding:10px;">No snapshots yet</p>
{% endif %}
                        </div>
{% endif %}
                        {% if vps['expires_at'] %}
                        <div class="card fade-in" style="margin-top: 12px;">
                            <div class="card-title" style="color:var(--red);">
                                <svg width="18" height="18"><use href="#icon-clock"/></svg>
                                Expiration Warning
                            </div>
                            <p style="font-size:12px;color:var(--text);">This VPS expires on: <strong>{{ vps['expires_at'] }}</strong></p>
                            <p style="font-size:11px;color:var(--text-dim);margin-top:4px;">After expiration, you can still control the VPS for 24 hours, then it will be auto-deleted.</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    <script>
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        function refreshStatus() {
            fetch('/api/vps/{{ vps["id"] }}/status')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('status-badge');
                    const s = data.status === 'running' ? 'running' : 'stopped';
                    badge.className = `status status-${s}`;
                    badge.innerHTML = `<span class="status-dot"></span>${data.status}`;
                });
        }

        function loadContainerStats() {
            fetch('/api/vps/{{ vps["id"] }}/stats')
                .then(r => r.json())
                .then(data => {
                    if (data.error) return;
                    
                    const cpuEl = document.getElementById('live-cpu');
                    const cpuBar = document.getElementById('live-cpu-bar');
                    const ramEl = document.getElementById('live-ram');
                    const ramBar = document.getElementById('live-ram-bar');
                    const netEl = document.getElementById('live-net');
                    const pidsEl = document.getElementById('live-pids');

                    if (cpuEl) cpuEl.textContent = data.cpu_percent + '%';
                    if (cpuBar) cpuBar.style.width = Math.min(data.cpu_percent, 100) + '%';
                    if (ramEl) ramEl.textContent = data.memory_used + ' / ' + data.memory_total + ' MB (' + data.memory_percent + '%)';
                    if (ramBar) ramBar.style.width = Math.min(data.memory_percent, 100) + '%';
                    if (netEl) netEl.textContent = '↓' + formatBytes(data.net_rx) + ' ↑' + formatBytes(data.net_tx);
                    if (pidsEl) pidsEl.textContent = data.pids + ' processes';
                })
                .catch(() => {});
        }

        refreshStatus();
        loadContainerStats();
        setInterval(refreshStatus, 5000);
        setInterval(loadContainerStats, 5000);
    </script>
</body>
</html>
""", 'all_vps.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>All VPS — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .stat-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:16px;display:flex;align-items:center;gap:12px;transition:transform .2s,box-shadow .2s}
        .stat-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.25)}
        .stat-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}
        .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .stat-icon.blue{background:rgba(96,165,250,.12);color:#60a5fa}
        .stat-icon.green{background:rgba(52,211,153,.12);color:#34d399}
        .stat-icon.red{background:rgba(248,113,113,.12);color:#f87171}
        .stat-info{display:flex;flex-direction:column}
        .stat-label{font-size:12px;color:var(--text-dim)}
        .stat-value{font-size:20px;font-weight:700;color:var(--text)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
        table{width:100%;border-collapse:collapse}
        thead{background:var(--bg-input)}
        th{padding:10px 14px;font-size:12px;font-weight:600;color:var(--text-muted);text-align:left;border-bottom:1px solid var(--border)}
        td{padding:10px 14px;font-size:13px;color:var(--text);border-bottom:1px solid var(--border)}
        tr:last-child td{border-bottom:none}
        tr:hover td{background:rgba(255,255,255,.02)}
        .mono{font-family:monospace}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .status-creating{background:rgba(251,191,36,.12);color:var(--yellow)}
        .empty-state{text-align:center;padding:40px 20px;color:var(--text-dim)}
        .empty-icon{width:64px;height:64px;border-radius:12px;background:var(--bg-input);display:flex;align-items:center;justify-content:center;margin:0 auto 12px;color:var(--text-muted)}
        .empty-state h3{font-size:15px;color:var(--text);margin-bottom:4px}
        .empty-state p{font-size:13px}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;border:none;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;text-decoration:none}
        .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)}
        .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
        .btn-yellow{background:rgba(251,191,36,.15);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
        .btn-yellow:hover{background:rgba(251,191,36,.25)}
        .btn-green{background:rgba(52,211,153,.15);color:var(--green);border:1px solid rgba(52,211,153,.2)}
        .btn-green:hover{background:rgba(52,211,153,.25)}
        .btn-red{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn-red:hover{background:rgba(248,113,113,.25)}
        .btn-sm{padding:6px 10px;font-size:12px}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @media (max-width: 768px) {
            .stat-cards { grid-template-columns: repeat(2, 1fr); gap: 4px; }
            .page-header { flex-direction: column; gap: 8px; }
            .stat-card { padding: 6px; gap: 5px; }
            .stat-icon { width: 24px; height: 24px; border-radius: 5px; }
            .stat-icon svg { width: 12px; height: 12px; }
            .stat-value { font-size: 13px; }
            .stat-label { font-size: 8px; }
            .card { padding: 10px; }
            .card-title { font-size: 11px; margin-bottom: 6px; }
            table { font-size: 10px; }
            th { padding: 5px 6px; font-size: 9px; }
            td { padding: 5px 6px; }
            .page-header h1 { font-size: 14px; }
            .page-header-sub { font-size: 10px; }
            .status { padding: 1px 5px; font-size: 9px; }
            .breadcrumbs { font-size: 10px; margin-bottom: 8px; }
        }
        @media (max-width: 480px) {
            .stat-cards { grid-template-columns: 1fr; gap: 3px; }
            .stat-card { padding: 5px; gap: 4px; }
            .stat-icon { width: 20px; height: 20px; border-radius: 4px; }
            .stat-icon svg { width: 10px; height: 10px; }
            .stat-value { font-size: 12px; }
            .card { padding: 8px; }
            table { font-size: 9px; }
            th { padding: 4px 5px; }
            td { padding: 4px 5px; }
            .page-header h1 { font-size: 13px; }
            .btn-sm { padding: 3px 5px; font-size: 9px; }
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('allvps', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('All VPS', 'allvps') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin">Admin</a>
                    <span class="sep">></span>
                    <span class="current">All VPS</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>All VPS Instances</h1>
                        <p class="page-header-sub">Manage all virtual private servers across all users.</p>
                    </div>
                </div>

                <div class="stat-cards fade-in">
                    <div class="stat-card">
                        <div class="stat-icon blue">
                            <svg width="20" height="20"><use href="#icon-server"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total VPS</div>
                            <div class="stat-value">{{ vps_list|length }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <svg width="20" height="20"><use href="#icon-play"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Running</div>
                            <div class="stat-value">{{ vps_list|selectattr('status', 'equalto', 'running')|list|length }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon red">
                            <svg width="20" height="20"><use href="#icon-stop"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Stopped</div>
                            <div class="stat-value">{{ vps_list|selectattr('status', 'equalto', 'stopped')|list|length }}</div>
                        </div>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-server"/></svg>
                        All Instances
                    </div>
                    {% if vps_list %}
                    <div class="table-wrap" style="margin-top:12px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>Name</th>
                                    <th>OS</th>
                                    <th>Specs</th>
                                    <th>Status</th>
                                    <th style="text-align:right;">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for vps in vps_list %}
                                <tr>
                                    <td>{{ vps['username'] }}</td>
                                    <td class="mono" style="font-size:12px;">{{ vps['container_name'] }}</td>
                                    <td>{{ vps['os_type'] }}</td>
                                    <td style="font-size:12px;">{{ vps['ram'] }} / {{ vps['cpu'] }}</td>
                                    <td>
                                        <span class="status status-{{ vps['status'] }}">
                                            <span class="status-dot"></span>
                                            {{ vps['status'] }}
                                        </span>
                                    </td>
                                    <td style="text-align:right;">
                                        <div style="display:flex;gap:4px;justify-content:flex-end;">
                                            <a href="/admin/vps/{{ vps['id'] }}" class="btn btn-ghost btn-sm" title="Details">
                                                <svg width="12" height="12"><use href="#icon-info"/></svg>
                                            </a>
                                            {% if vps['status'] == 'running' %}
                                            <form method="POST" action="/admin/stop-vps/{{ vps['id'] }}" style="display:inline;">
                                                <button type="submit" class="btn btn-yellow btn-sm" title="Stop">
                                                    <svg width="12" height="12"><use href="#icon-stop"/></svg>
                                                </button>
                                            </form>
                                            {% elif vps['status'] == 'stopped' or vps['status'] == 'created' %}
                                            <form method="POST" action="/admin/start-vps/{{ vps['id'] }}" style="display:inline;">
                                                <button type="submit" class="btn btn-green btn-sm" title="Start">
                                                    <svg width="12" height="12"><use href="#icon-play"/></svg>
                                                </button>
                                            </form>
                                            {% endif %}
                                            <form method="POST" action="/admin/delete-vps/{{ vps['id'] }}" style="display:inline;">
                                                <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Delete this VPS?')" title="Delete">
                                                    <svg width="12" height="12"><use href="#icon-trash"/></svg>
                                                </button>
                                            </form>
                                        </div>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="empty-state">
                        <div class="empty-icon">
                            <svg width="28" height="28"><use href="#icon-server"/></svg>
                        </div>
                        <h3>No instances yet</h3>
                        <p>Create a VPS for a user to get started.</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'profile.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Profile — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        .profile-grid{display:grid;grid-template-columns:1fr 1.5fr;gap:16px;margin-bottom:20px}
        .activity-ip-col,.activity-time-col{display:table-cell}
        .activity-detail{display:none}
        @media(max-width:768px){
            .profile-grid{grid-template-columns:1fr;gap:10px}
            .card{padding:10px}
            .card-title{font-size:12px;margin-bottom:6px}
            .page-header h1{font-size:15px}
            .breadcrumbs{font-size:10px;margin-bottom:8px}
            .profile-avatar-lg{width:50px;height:50px;font-size:22px}
            table{font-size:11px}
            th{padding:5px 6px;font-size:9px}
            td{padding:5px 6px}
            .status{padding:2px 6px;font-size:9px}
            .info-item{padding:5px 0}
            .info-label{font-size:10px}
            .info-value{font-size:11px}
            .form-row{grid-template-columns:1fr}
            .form-control{padding:7px 9px;font-size:12px}
            .btn-primary{padding:6px 12px;font-size:12px}
            .activity-ip-col,.activity-time-col{display:none}
            .activity-detail{display:block;font-size:9px;color:var(--text-dim);margin-top:1px}
        }
    </style>
</head>
<body>
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('profile', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('My Profile', 'profile') }}

            <div class="page">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <span class="current">Profile</span>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="profile-grid fade-in">
                    <div class="card fade-in">
                        <div style="text-align: center; padding: 20px 0;">
                            <div class="profile-avatar-lg">{{ session.get('username', 'U')[0].upper() }}</div>
                            <h2 style="margin-top: 12px; font-size: 18px;">{{ user['username'] }}</h2>
                            <p class="text-dim" style="font-size: 13px;">{{ user['email'] }}</p>
                            <div style="display: flex; gap: 8px; justify-content: center; margin-top: 12px;">
                                {% if user['is_admin'] %}
                                <span class="status" style="background:rgba(251,191,36,.12);color:var(--yellow);">Owner</span>
                                {% elif user['is_admin'] %}
                                <span class="status status-running">Admin</span>
                                {% else %}
                                <span class="status status-stopped">User</span>
                                {% endif %}
                                <span class="status status-creating">Member since {{ user['created_at'][:10] }}</span>
                            </div>
                        </div>
                        <div class="info-list" style="margin-top: 16px;">
                            {% if user['is_admin'] %}
                            <div class="info-item">
                                <span class="info-label">
                                    <svg width="14" height="14" style="display: inline;"><use href="#icon-key"/></svg>
                                    API Key
                                </span>
                                <span class="info-value" style="display: flex; align-items: center; gap: 6px;">
                                    <span id="api-key-val">{{ user['api_key'][:16] }}...</span>
                                    <button class="btn btn-ghost btn-sm" onclick='copyToClipboard({{ user['api_key']|tojson }})' style="padding: 3px 6px;">
                                        <svg width="12" height="12"><use href="#icon-copy"/></svg>
                                    </button>
                                    <form method="POST" action="/profile/regen-api" style="display: inline;">
                                        <button type="submit" class="btn btn-ghost btn-sm" style="padding: 3px 6px;">
                                            <svg width="12" height="12"><use href="#icon-refresh"/></svg>
                                        </button>
                                    </form>
                                </span>
                            </div>
                            {% endif %}
                            <div class="info-item">
                                <span class="info-label">
                                    <svg width="14" height="14" style="display: inline;"><use href="#icon-dot"/></svg>
                                    Last Login
                                </span>
                                <span class="info-value">{{ user['created_at'][:16] }}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">
                                    <svg width="14" height="14" style="display: inline;"><use href="#icon-dot"/></svg>
                                    Last Active
                                </span>
                                <span class="info-value">4 minutes ago</span>
                            </div>
                        </div>
                    </div>

                    <div class="card fade-in">
                        <div class="card-title" style="margin-bottom: 16px;">
                            <svg width="18" height="18"><use href="#icon-user"/></svg>
                            Edit Profile
                        </div>
                        <form method="POST" action="/profile">
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Username</label>
                                    <input type="text" name="username" class="form-control" value="{{ user['username'] }}" required>
                                </div>
                                <div class="form-group">
                                    <label>Email Address</label>
                                    <input type="email" name="email" class="form-control" value="{{ user['email'] }}" required>
                                </div>
                            </div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Current Password</label>
                                    <input type="password" name="current_password" class="form-control" placeholder="Enter current password" required>
                                </div>
                                <div class="form-group">
                                    <label>New Password</label>
                                    <input type="password" name="new_password" class="form-control" placeholder="Leave blank to keep current">
                                </div>
                            </div>
                            <div class="form-group">
                                <label>Confirm New Password</label>
                                <input type="password" name="confirm_password" class="form-control" placeholder="Confirm new password">
                            </div>
                            <div style="display: flex; gap: 8px; justify-content: flex-end;">
                                <button type="submit" class="btn btn-primary">
                                    <svg width="14" height="14"><use href="#icon-check-circle"/></svg>
                                    Save Changes
                                </button>
                            </div>
                        </form>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-terminal"/></svg>
                        Recent Activity
                    </div>
                    <div class="table-wrap" style="margin-top: 12px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Action</th>
                                    <th>Resource</th>
                                    <th class="activity-detail">Details</th>
                                    <th class="activity-ip-col">IP Address</th>
                                    <th class="activity-time-col">Time</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for log in activity %}
                                <tr>
                                    <td>
                                        <span class="status status-{{ 'running' if log['action'] == 'login' else 'stopped' if log['action'] == 'logout' else 'creating' }}">{{ log['action'] }}</span>
                                        <span class="activity-detail">{{ log['details'] or '' }}</span>
                                    </td>
                                    <td class="text-dim">{{ log['resource'] or '—' }}</td>
                                    <td class="activity-detail text-dim" style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;">{{ log['details'] or '—' }}</td>
                                    <td class="activity-ip-col mono" style="font-size:12px;">{{ log['ip_address'] or '—' }}</td>
                                    <td class="activity-time-col text-dim">{{ log['created_at'][:16] }}</td>
                                </tr>
                                {% endfor %}
                                {% if not activity %}
                                <tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 20px;">No recent activity</td></tr>
                                {% endif %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'ports.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Port Forwarding — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .stat-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:16px;transition:transform .2s,box-shadow .2s}
        .stat-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.25)}
        .stat-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}
        .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .stat-icon.blue{background:rgba(96,165,250,.12);color:#60a5fa}
        .stat-icon.green{background:rgba(52,211,153,.12);color:#34d399}
        .stat-icon.yellow{background:rgba(251,191,36,.12);color:#fbbf24}
        .stat-icon.red{background:rgba(248,113,113,.12);color:#f87171}
        .stat-icon.orange{background:rgba(251,146,60,.12);color:#fb923c}
        .stat-info{display:flex;flex-direction:column}
        .stat-label{font-size:12px;color:var(--text-dim)}
        .stat-value{font-size:20px;font-weight:700;color:var(--text)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
        table{width:100%;border-collapse:collapse}
        thead{background:var(--bg-input)}
        th{padding:10px 14px;font-size:12px;font-weight:600;color:var(--text-muted);text-align:left;border-bottom:1px solid var(--border)}
        td{padding:10px 14px;font-size:13px;color:var(--text);border-bottom:1px solid var(--border)}
        tr:last-child td{border-bottom:none}
        tr:hover td{background:rgba(255,255,255,.02)}
        .mono{font-family:monospace}
        .text-green{color:var(--green)}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .empty-state{text-align:center;padding:40px 20px;color:var(--text-dim)}
        .empty-icon{width:64px;height:64px;border-radius:12px;background:var(--bg-input);display:flex;align-items:center;justify-content:center;margin:0 auto 12px;color:var(--text-muted)}
        .empty-state h3{font-size:15px;color:var(--text);margin-bottom:4px}
        .empty-state p{font-size:13px}
        .form-group{margin-bottom:14px}
        .form-group label{display:block;font-size:12px;font-weight:500;color:var(--text-muted);margin-bottom:6px}
        .form-control{width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:13px;transition:border-color .15s;outline:none}
        .form-control:focus{border-color:rgba(255,255,255,.15)}
        .form-control::placeholder{color:var(--text-dim)}
        select.form-control{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%238888a0'%3E%3Cpath d='M6 8L1 3h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
        .form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;border:none;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;text-decoration:none}
        .btn-primary{background:rgba(255,255,255,.1);color:var(--text);border:1px solid rgba(255,255,255,.12)}
        .btn-primary:hover{background:rgba(255,255,255,.18)}
        .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)}
        .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
        .btn-red{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn-red:hover{background:rgba(248,113,113,.25)}
        .btn-sm{padding:6px 10px;font-size:12px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .alert{padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:16px;border:1px solid}
        .alert-success{background:rgba(52,211,153,.08);border-color:rgba(52,211,153,.2);color:var(--green)}
        .alert-error{background:rgba(248,113,113,.08);border-color:rgba(248,113,113,.2);color:var(--red)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @media(max-width:768px){
            .stat-cards{grid-template-columns:1fr 1fr 1fr;gap:6px}
            .stat-card{padding:10px 8px}
            .stat-icon{width:28px;height:28px;border-radius:8px}
            .stat-icon svg{width:14px;height:14px}
            .stat-label{font-size:10px}
            .stat-value{font-size:14px}
            .form-row{grid-template-columns:1fr}
            .card{padding:14px}
            table{font-size:12px}
            th{padding:8px 8px;font-size:10px}
            td{padding:8px 8px;font-size:11px}
            .mono{font-size:11px!important}
            .btn{padding:8px 12px;font-size:12px}
            .status{padding:2px 6px!important;font-size:10px!important;gap:3px!important}
            td,th{padding:6px 6px!important}
            td .btn-sm{padding:2px 4px!important;font-size:9px!important}
            .mono{font-size:10px!important}
            .table-wrap{margin-top:6px!important}
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('ports', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Port Forwarding', 'ports') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <span class="current">Port Forwarding</span>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                {% if settings['port_forwarding_method'] == 'ipv4' %}
                <div class="stat-cards fade-in">
                    <div class="stat-card">
                        <div class="stat-icon blue">
                            <svg width="20" height="20"><use href="#icon-key"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Allocated Ports</div>
                            <div class="stat-value">{{ allocated }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <svg width="20" height="20"><use href="#icon-check-circle"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Used Ports</div>
                            <div class="stat-value">{{ used }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon yellow">
                            <svg width="20" height="20"><use href="#icon-bolt"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Available Ports</div>
                            <div class="stat-value">{{ available }}</div>
                        </div>
                    </div>
                </div>
                {% endif %}

                <div class="card fade-in" style="margin-bottom:20px;">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-key"/></svg>
                        Active Port Forwards
                        <span class="status status-running" style="margin-left:auto; font-size:11px;">
                            {{ 'IPv4 Direct' if settings['port_forwarding_method'] == 'ipv4' else 'Serveo Tunnel' }}
                        </span>
                    </div>
                    {% if forwards %}
                    <div class="table-wrap" style="margin-top:12px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>VPS</th>
                                    <th>Port (VPS)</th>
                                    <th>{{ 'External Port' if settings['port_forwarding_method'] == 'ipv4' else 'Serveo URL' }}</th>
                                    <th>Method</th>
                                    <th>Status</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for fwd in forwards %}
                                <tr>
                                    <td>{{ fwd['container_name'] }}</td>
                                    <td class="mono" style="font-size:12px;">{{ fwd['local_port'] }}</td>
                                    <td class="mono text-green" style="font-size:12px;">
                                        {% if fwd['serveo_url'] and fwd['serveo_url'].startswith('http') %}
                                        <a href="{{ fwd['serveo_url'] }}" target="_blank" style="color:var(--green);text-decoration:none;">{{ fwd['serveo_url'] }}</a>
                                        {% elif fwd['serveo_url'] %}
                                        <span>{{ fwd['serveo_url'] }}</span>
                                        {% else %}
                                        <span>Pending...</span>
                                        {% endif %}
                                    </td>
                                    <td><span class="status {{ 'status-running' if (fwd['method'] if 'method' in fwd.keys() else 'serveo') == 'ipv4' else 'status-creating' }}" style="font-size:11px;">{{ (fwd['method'] if 'method' in fwd.keys() else 'serveo') }}</span></td>
                                    <td><span class="status status-{{ 'running' if fwd['status'] == 'active' else 'stopped' }}">{{ fwd['status'] }}</span></td>
                                    <td style="text-align:right;">
                                        <form method="POST" action="/ports/{{ fwd['id'] }}/delete" style="display:inline;">
                                            <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Delete?')">
                                                <svg width="12" height="12"><use href="#icon-trash"/></svg>
                                            </button>
                                        </form>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="empty-state">
                        <div class="empty-icon">
                            <svg width="28" height="28"><use href="#icon-key"/></svg>
                        </div>
                        <h3>No Port Forwards</h3>
                        <p>You haven't set up any port forwarding rules yet.</p>
                        <p class="text-dim" style="font-size:12px;">Create a VPS first to add port forwards.</p>
                    </div>
                    {% endif %}
                </div>

                {% if user_vps %}
                <div class="card fade-in">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-plus"/></svg>
                        New Port Forward
                        <span class="status {{ 'status-running' if settings['port_forwarding_method'] == 'ipv4' else 'status-creating' }}" style="margin-left:auto; font-size:11px;">
                            {{ 'IPv4 Direct' if settings['port_forwarding_method'] == 'ipv4' else 'Serveo Tunnel' }}
                        </span>
                    </div>
                    <form method="POST" action="/ports/create" style="margin-top:12px;">
                        <div class="form-row">
                            <div class="form-group">
                                <label>VPS</label>
                                <select name="vps_id" class="form-control" required>
                                    <option value="">Select VPS</option>
                                    {% for vps in user_vps %}
                                    <option value="{{ vps['id'] }}">{{ vps['container_name'] }} ({{ vps['status'] }})</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Port (inside VPS)</label>
                                <input type="number" name="local_port" class="form-control" placeholder="e.g. 8181" min="1" max="65535" required>
                                <p class="text-dim" style="font-size:10px;margin-top:4px;">The port your app runs on inside the VPS</p>
                            </div>
                        </div>
                        <button type="submit" class="btn btn-primary" style="width:100%;">
                            <svg width="14" height="14"><use href="#icon-plus"/></svg>
                            {{ 'Create Forward via IPv4' if settings['port_forwarding_method'] == 'ipv4' else 'Create Forward via Serveo' }}
                        </button>
                    </form>
                    <p class="text-dim" style="font-size:11px;margin-top:8px;">
                        {% if settings['port_forwarding_method'] == 'ipv4' %}
                        Binds port on your server's public IP and forwards traffic directly to the VPS container.
                        {% else %}
                        Runs: <code style="background:var(--bg-input);padding:2px 6px;border-radius:4px;">ssh -R 80:localhost:{port} serveo.net</code> inside the VPS. A public URL will be generated automatically.
                        {% endif %}
                    </p>
                </div>
                {% endif %}
            </div>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'settings.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel Settings — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .form-group{margin-bottom:14px}
        .form-group label{display:block;font-size:12px;font-weight:500;color:var(--text-muted);margin-bottom:6px}
        .form-control{width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:13px;transition:border-color .15s;outline:none}
        .form-control:focus{border-color:rgba(255,255,255,.15)}
        .form-control::placeholder{color:var(--text-dim)}
        select.form-control{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%238888a0'%3E%3Cpath d='M6 8L1 3h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
        .form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
        .checkbox-row{display:flex;align-items:center;gap:8px;margin-top:12px;padding:10px 14px;background:var(--bg-input);border:1px solid var(--border);border-radius:10px}
        .checkbox-row input[type="checkbox"]{width:16px;height:16px;accent-color:var(--green)}
        .checkbox-row label{font-size:13px;color:var(--text);cursor:pointer}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;border:none;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;text-decoration:none}
        .btn-primary{background:rgba(255,255,255,.1);color:var(--text);border:1px solid rgba(255,255,255,.12)}
        .btn-primary:hover{background:rgba(255,255,255,.18)}
        .btn-lg{padding:10px 24px;font-size:14px}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .alert{padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:16px;border:1px solid}
        .alert-success{background:rgba(52,211,153,.08);border-color:rgba(52,211,153,.2);color:var(--green)}
        .alert-error{background:rgba(248,113,113,.08);border-color:rgba(248,113,113,.2);color:var(--red)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('settings', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Panel Settings', 'settings') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin">Admin</a>
                    <span class="sep">></span>
                    <span class="current">Settings</span>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <form method="POST" action="/settings" enctype="multipart/form-data">
                    <div class="card fade-in" style="margin-bottom:20px;">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-settings"/></svg>
                            General Settings
                        </div>
                        <div style="margin-top:16px;">
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Site Name</label>
                                    <input type="text" name="site_name" class="form-control" value="{{ settings['site_name'] }}">
                                </div>
                                <div class="form-group">
                                    <label>Site Description</label>
                                    <input type="text" name="site_description" class="form-control" value="{{ settings['site_description'] }}">
                                </div>
                            </div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Footer Text</label>
                                    <input type="text" name="footer_text" class="form-control" value="{{ settings['footer_text'] }}">
                                </div>
                                <div class="form-group">
                                    <label>Timezone</label>
                                    <select name="timezone" class="form-control">
                                        {% for tz in timezones %}
                                        <option value="{{ tz }}" {% if settings['timezone'] == tz %}selected{% endif %}>{{ tz }}</option>{% endfor %}
                                    </select>
                                </div>
                            </div>
                            <div class="checkbox-row">
                                <input type="checkbox" name="registration_enabled" id="registration_enabled" {{ 'checked' if settings['registration_enabled'] }}>
                                <label for="registration_enabled">Enable user registration</label>
                            </div>
                            <div class="form-group" style="margin-top:12px;">
                                <label>VPS Hostname Prefix</label>
                                <input type="text" name="hostname_prefix" class="form-control" value="{{ settings['hostname_prefix'] }}" placeholder="vps">
                                <div class="text-dim" style="font-size:11px;margin-top:4px;">Prefix for auto-generated VPS hostnames (e.g. <code>vps-</code> becomes <code>prefix-</code>)</div>
                            </div>
                        </div>
                    </div>

                    <div class="card fade-in" style="margin-bottom:20px;">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-settings"/></svg>
                            Branding
                        </div>
                        <div style="margin-top:16px;">
                            <div class="form-group">
                                <label>Site Icon (PNG or GIF only)</label>
                                <div style="display:flex;gap:12px;align-items:flex-start;">
                                    <div style="flex:1;">
                                        <input type="file" name="icon_file" id="iconFile" accept=".png,.gif,image/png,image/gif" 
                                               style="display:none;" onchange="previewIcon(this)">
                                        <button type="button" class="btn btn-ghost" onclick="document.getElementById('iconFile').click()" 
                                                style="width:100%;padding:20px;border:2px dashed var(--border);border-radius:10px;background:var(--bg-input);cursor:pointer;">
                                            <svg width="20" height="20" style="margin-bottom:8px;color:var(--text-dim);"><use href="#icon-plus"/></svg>
                                            <div style="font-size:13px;color:var(--text-muted);">Click to upload icon</div>
                                            <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">PNG or GIF, max 2MB</div>
                                        </button>
                                    </div>
                                    <div id="iconPreview" style="width:64px;height:64px;border-radius:12px;background:var(--bg-input);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0;">
                                        {% if settings['icon_path'] %}
                                        <img src="{{ settings['icon_path'] }}" alt="Current icon" style="width:100%;height:100%;object-fit:contain;">
                                        {% else %}
                                        <svg width="24" height="24" style="color:var(--text-dim);"><use href="#icon-settings"/></svg>
                                        {% endif %}
                                    </div>
                                </div>
                                {% if settings['icon_path'] %}
                                <div style="margin-top:8px;display:flex;align-items:center;gap:8px;">
                                    <span style="font-size:11px;color:var(--text-dim);">Current: {{ settings['icon_path'].split('/')[-1] }}</span>
                                    <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--red);cursor:pointer;">
                                        <input type="checkbox" name="remove_icon" value="1" style="accent-color:var(--red);">
                                        Remove icon
                                    </label>
                                </div>
                                {% endif %}
                            </div>
                        </div>
                    </div>

                                        <div class="card fade-in" style="margin-bottom:20px;">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-key"/></svg>
                            Port Forwarding
                        </div>
                        <div style="margin-top:16px;">
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Forwarding Method</label>
                                    <select name="port_forwarding_method" class="form-control">
                                        <option value="serveo" {% if settings['port_forwarding_method'] == 'serveo' %}selected{% endif %}>Serveo (Tunnel)</option>
                                        <option value="ipv4" {% if settings['port_forwarding_method'] == 'ipv4' %}selected{% endif %}>IPv4 (Direct)</option>
                                    </select>
                                    <p class="text-dim" style="font-size:11px;margin-top:4px;">Serveo uses tunnels, IPv4 exposes ports directly on your server IP</p>
                                </div>
                                <div class="form-group">
                                    <label>Public IPv4 Address</label>
                                    <input type="text" name="public_ipv4" class="form-control" value="{{ settings['public_ipv4'] if 'public_ipv4' in settings.keys() else '' }}" placeholder="e.g. 1.2.3.4">
                                    <p class="text-dim" style="font-size:11px;margin-top:4px;">Required when using IPv4 method. Your server's public IP.</p>
                                </div>
                                <div class="form-group">
                                    <label>Max Ports Per User</label>
                                    <input type="number" name="max_ports_per_user" class="form-control" value="{{ settings['max_ports_per_user'] if 'max_ports_per_user' in settings.keys() else 20 }}" min="1" max="1000">
                                    <p class="text-dim" style="font-size:11px;margin-top:4px;">Maximum port forwards per user (IPv4 method only)</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card fade-in" style="margin-bottom:20px;">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-clock"/></svg>
                            VPS Expiration
                        </div>
                        <div style="margin-top:16px;">
                            <div class="form-group">
                                <label>Default VPS Lifetime (days)</label>
                                <input type="number" name="default_vps_days" class="form-control" value="{{ settings['default_vps_days'] if 'default_vps_days' in settings.keys() else 0 }}" min="0">
                                <p class="text-dim" style="font-size:11px;margin-top:4px;">0 = no expiration (VPS runs forever). When set, new VPS will expire after N days. Expired VPS is stopped for 24h then deleted.</p>
                            </div>
                        </div>
                    </div>

                    <div class="card fade-in" style="margin-bottom:20px;">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-shield"/></svg>
                            Rate Limiting
                        </div>
                        <div style="margin-top:16px;">
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Auth Endpoints (per minute)</label>
                                    <input type="number" name="rate_limit_auth" class="form-control" value="{{ settings['rate_limit_auth'] if 'rate_limit_auth' in settings.keys() else 10 }}">
                                    <p class="text-dim" style="font-size:11px;margin-top:4px;">Login, register, password changes</p>
                                </div>
                                <div class="form-group">
                                    <label>API Endpoints (per minute)</label>
                                    <input type="number" name="rate_limit_api" class="form-control" value="{{ settings['rate_limit_api'] if 'rate_limit_api' in settings.keys() else 60 }}">
                                    <p class="text-dim" style="font-size:11px;margin-top:4px;">Status checks, stats, system info</p>
                                </div>
                            </div>
                            <div class="form-group">
                                <label>Heavy Operations (per minute)</label>
                                <input type="number" name="rate_limit_heavy" class="form-control" value="{{ settings['rate_limit_heavy'] if 'rate_limit_heavy' in settings.keys() else 5 }}">
                                <p class="text-dim" style="font-size:11px;margin-top:4px;">Create, delete, restart VPS instances</p>
                            </div>
                        </div>
                    </div>

                    <div style="display:flex;justify-content:flex-end;">
                        <button type="submit" class="btn btn-primary btn-lg">
                            <svg width="14" height="14"><use href="#icon-check-circle"/></svg>
                            Save Settings
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    <script>
        function previewIcon(input) {
            const preview = document.getElementById('iconPreview');
            if (input.files && input.files[0]) {
                const file = input.files[0];
                const ext = file.name.split('.').pop().toLowerCase();
                if (!['png', 'gif'].includes(ext)) {
                    alert('Only PNG and GIF files are allowed');
                    input.value = '';
                    return;
                }
                if (file.size > 2 * 1024 * 1024) {
                    alert('File size must be under 2MB');
                    input.value = '';
                    return;
                }
                const reader = new FileReader();
                reader.onload = function(e) {
                    preview.innerHTML = '<img src="' + e.target.result + '" style="width:100%;height:100%;object-fit:contain;">';
                };
                reader.readAsDataURL(file);
            }
        }
    </script>
</body>
</html>
""", 'nodes.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Node Management — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .stat-icon.blue{background:rgba(96,165,250,.12);color:#60a5fa}
        .stat-icon.green{background:rgba(52,211,153,.12);color:#34d399}
        .stat-icon.yellow{background:rgba(251,191,36,.12);color:#fbbf24}
        .stat-icon.red{background:rgba(248,113,113,.12);color:#f87171}
        .stat-icon.orange{background:rgba(251,146,60,.12);color:#fb923c}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .resource-bars{display:flex;flex-direction:column;gap:14px}
        .resource-bar-header{display:flex;justify-content:space-between;font-size:12px;color:var(--text-muted);margin-bottom:6px}
        .resource-bar-track{height:6px;background:var(--bg-input);border-radius:10px;overflow:hidden}
        .resource-bar-fill{height:100%;border-radius:10px;transition:width .6s ease}
        .resource-bar-fill.blue{background:linear-gradient(90deg,#60a5fa,#3b82f6)}
        .resource-bar-fill.green{background:linear-gradient(90deg,#34d399,#10b981)}
        .resource-bar-fill.yellow{background:linear-gradient(90deg,#fbbf24,#f59e0b)}
        .resource-bar-fill.red{background:linear-gradient(90deg,#f87171,#ef4444)}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .status-creating{background:rgba(251,191,36,.12);color:var(--yellow)}
        .empty-state{text-align:center;padding:40px 20px;color:var(--text-dim)}
        .empty-icon{width:64px;height:64px;border-radius:12px;background:var(--bg-input);display:flex;align-items:center;justify-content:center;margin:0 auto 12px;color:var(--text-muted)}
        .empty-state h3{font-size:15px;color:var(--text);margin-bottom:4px}
        .empty-state p{font-size:13px}
        .form-group{margin-bottom:14px}
        .form-group label{display:block;font-size:12px;font-weight:500;color:var(--text-muted);margin-bottom:6px}
        .form-control{width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:13px;transition:border-color .15s;outline:none}
        .form-control:focus{border-color:rgba(255,255,255,.15)}
        .form-control::placeholder{color:var(--text-dim)}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;border:none;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;text-decoration:none}
        .btn-primary{background:rgba(255,255,255,.1);color:var(--text);border:1px solid rgba(255,255,255,.12)}
        .btn-primary:hover{background:rgba(255,255,255,.18)}
        .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)}
        .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
        .btn-red{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn-red:hover{background:rgba(248,113,113,.25)}
        .btn-sm{padding:6px 10px;font-size:12px}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .alert{padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:16px;border:1px solid}
        .alert-success{background:rgba(52,211,153,.08);border-color:rgba(52,211,153,.2);color:var(--green)}
        .alert-error{background:rgba(248,113,113,.08);border-color:rgba(248,113,113,.2);color:var(--red)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(4px);z-index:1000;align-items:center;justify-content:center}
        .modal-bg.active{display:flex}
        .modal{background:var(--bg-card);border:1px solid var(--border);border-radius:16px;padding:24px;width:100%;max-width:480px;max-height:80vh;overflow-y:auto}
        .modal-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
        .modal-top h2{font-size:16px;font-weight:600;color:var(--text)}
        .modal-x{background:none;border:none;color:var(--text-dim);font-size:20px;cursor:pointer;padding:4px 8px;border-radius:6px;transition:background .15s}
        .modal-x:hover{background:rgba(255,255,255,.06)}
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('nodes', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Node Management', 'nodes') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin">Admin</a>
                    <span class="sep">></span>
                    <span class="current">Nodes</span>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="page-header fade-in" style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div>
                        <h1>Cluster Nodes</h1>
                        <p class="page-header-sub">Manage your VPS hosting nodes. Add remote servers by IP and API key.</p>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <form method="POST" action="/nodes/add-local" style="display:inline;">
                            <button type="submit" class="btn btn-ghost">
                                <svg width="14" height="14"><use href="#icon-plus"/></svg>
                                Add Local Node
                            </button>
                        </form>
                        <button class="btn btn-primary" onclick="openModal('addNodeModal')">
                            <svg width="14" height="14"><use href="#icon-plus"/></svg>
                            Add Remote Node
                        </button>
                    </div>
                </div>

                {% if not nodes %}
                <div class="card fade-in">
                    <div class="empty-state">
                        <div class="empty-icon">
                            <svg width="28" height="28"><use href="#icon-server"/></svg>
                        </div>
                        <h3>No Nodes Yet</h3>
                        <p>Add a node to start deploying VPS instances.</p>
                    </div>
                </div>
                {% endif %}

                {% for node in nodes %}
                <div class="card fade-in" style="margin-bottom:16px;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
                        <div style="display:flex;align-items:center;gap:12px;">
                            <div class="stat-icon {{ 'green' if node['status'] == 'online' else 'red' }}">
                                <svg width="20" height="20"><use href="#icon-server"/></svg>
                            </div>
                            <div>
                                <h3 style="font-size:16px;font-weight:600;color:var(--text);">{{ node['name'] }}</h3>
                                <p class="text-dim" style="font-size:12px;">{{ node['hostname'] }}{% if node['node_url'] %} &middot; {{ node['node_url'] }}{% endif %}</p>
                            </div>
                        </div>
                        <div style="display:flex;gap:8px;align-items:center;">
                            <span class="status status-{{ 'running' if node['status'] == 'online' else 'stopped' }}">
                                <span class="status-dot"></span>
                                {{ node['status']|capitalize }}
                            </span>
                            {% if node['is_local'] %}
                            <span class="status status-creating">Local</span>
                            {% endif %}
                        </div>
                    </div>

                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:16px;">
                        <div>
                            <div class="text-dim" style="font-size:12px;margin-bottom:4px;">VPS Usage</div>
                            <div style="font-size:20px;font-weight:700;color:var(--text);">{{ node['vps_count'] }} / {{ node['max_vps'] }}</div>
                        </div>
                        <div>
                            <div class="text-dim" style="font-size:12px;margin-bottom:4px;">Last Seen</div>
                            <div style="font-size:20px;font-weight:700;color:var(--text);">{{ 'Now' if node['status'] == 'online' else node['created_at'][:10] }}</div>
                        </div>
                    </div>

                    <div class="resource-bars">
                        <div class="resource-bar-item">
                            <div class="resource-bar-header">
                                <span>CPU</span>
                                <span>{{ "%.1f"|format(node['cpu_usage']) }}%</span>
                            </div>
                            <div class="resource-bar-track">
                                <div class="resource-bar-fill {{ 'green' if node['cpu_usage'] < 50 else 'yellow' if node['cpu_usage'] < 80 else 'red' }}" style="width:{{ node['cpu_usage'] }}%"></div>
                            </div>
                        </div>
                        <div class="resource-bar-item">
                            <div class="resource-bar-header">
                                <span>RAM</span>
                                <span>{{ "%.1f"|format(node['ram_usage']) }}%</span>
                            </div>
                            <div class="resource-bar-track">
                                <div class="resource-bar-fill {{ 'green' if node['ram_usage'] < 50 else 'yellow' if node['ram_usage'] < 80 else 'red' }}" style="width:{{ node['ram_usage'] }}%"></div>
                            </div>
                        </div>
                    </div>

                    <div style="margin-top:16px;display:flex;gap:8px;">
                        <button class="btn btn-ghost btn-sm" onclick="populateEditModal({{ node['id'] }}, '{{ node['name'] }}', '{{ node['hostname'] }}', '{{ node['node_url'] }}', '{{ node['api_key'] }}', {{ node['max_vps'] }}, {{ node['is_local']|lower }})">
                            <svg width="14" height="14"><use href="#icon-edit"/></svg>
                            Edit Node
                        </button>
                        <form method="POST" action="/nodes/delete/{{ node['id'] }}">
                            <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Delete this node?')">
                                <svg width="14" height="14"><use href="#icon-trash"/></svg>
                                Delete Node
                            </button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <div id="addNodeModal" class="modal-bg">
        <div class="modal">
            <div class="modal-top">
                <h2>Add Node</h2>
                <button class="modal-x" onclick="closeModal('addNodeModal')">&times;</button>
            </div>
            <form method="POST" action="/nodes/add">
                <div class="form-group">
                    <label>Node Name</label>
                    <input type="text" name="name" class="form-control" placeholder="e.g. US-1" required>
                </div>
                <div class="form-group">
                    <label>Hostname / IP</label>
                    <input type="text" name="hostname" class="form-control" placeholder="e.g. us1.example.com or 203.0.113.5" required>
                </div>
                <div class="form-group">
                    <label>Node URL (for remote nodes)</label>
                    <input type="text" name="node_url" class="form-control" placeholder="e.g. http://203.0.113.5:5001">
                    <small class="text-dim" style="font-size:11px;">Leave empty for local node. Remote nodes need the agent running.</small>
                </div>
                <div class="form-group">
                    <label>API Key (for remote nodes)</label>
                    <input type="text" name="api_key" class="form-control" placeholder="Paste the node agent's API key">
                    <small class="text-dim" style="font-size:11px;">Shown in the node agent's startup output.</small>
                </div>
                <div class="form-group">
                    <label>Max VPS</label>
                    <input type="number" name="max_vps" class="form-control" value="500">
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%;">Add Node</button>
            </form>
        </div>
    </div>

        <div id="editNodeModal" class="modal-bg">
        <div class="modal">
            <div class="modal-top">
                <h2>Edit Node</h2>
                <button class="modal-x" onclick="closeModal('editNodeModal')">&times;</button>
            </div>
            <form method="POST" action="/nodes/edit">
                <input type="hidden" name="node_id" id="editNodeId">
                <div class="form-group">
                    <label>Node Name</label>
                    <input type="text" name="name" id="editNodeName" class="form-control" required>
                </div>
                <div class="form-group">
                    <label>Hostname / IP</label>
                    <input type="text" name="hostname" id="editNodeHostname" class="form-control" required>
                </div>
                <div id="editNodeExtraFields">
                <div class="form-group">
                    <label>Node URL</label>
                    <input type="text" name="node_url" id="editNodeUrl" class="form-control">
                </div>
                <div class="form-group">
                    <label>API Key</label>
                    <input type="text" name="api_key" id="editNodeApiKey" class="form-control">
                </div>
                </div>
                <div class="form-group">
                    <label>Max VPS</label>
                    <input type="number" name="max_vps" id="editNodeMaxVps" class="form-control" value="500">
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%;">Save Changes</button>
            </form>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'logs.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>System Logs — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        .stat-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
        .stat-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:16px;display:flex;align-items:center;gap:12px;transition:transform .2s,box-shadow .2s}
        .stat-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.25)}
        .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .stat-icon.blue{background:rgba(96,165,250,.12);color:#60a5fa}
        .stat-icon.green{background:rgba(52,211,153,.12);color:#34d399}
        .stat-icon.yellow{background:rgba(251,191,36,.12);color:#fbbf24}
        .stat-icon.red{background:rgba(248,113,113,.12);color:#f87171}
        .stat-info{display:flex;flex-direction:column}
        .stat-label{font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px}
        .stat-value{font-size:18px;font-weight:700;color:var(--text)}
        .log-output{max-height:500px;overflow-y:auto;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:12px;font-family:monospace;font-size:12px;line-height:1.6}
        .log-line{padding:3px 0;border-bottom:1px solid rgba(255,255,255,.03);display:flex;gap:8px;flex-wrap:wrap;align-items:baseline}
        .log-line:last-child{border-bottom:none}
        .log-time{color:var(--text-dim);font-size:11px;flex-shrink:0}
        .log-source{color:var(--text-muted);font-size:11px}
        .log-level{font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;flex-shrink:0}
        .level-info{background:rgba(52,211,153,.12);color:var(--green)}
        .level-warning{background:rgba(251,191,36,.12);color:var(--yellow)}
        .level-error{background:rgba(248,113,113,.12);color:var(--red)}
        .log-message{color:var(--text);font-size:12px;word-break:break-word}
        .search-bar{display:flex;gap:8px;margin-bottom:12px}
        .search-input{flex:1;padding:8px 12px;font-size:13px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);outline:none}
        .search-input:focus{border-color:rgba(255,255,255,.2)}
        .search-select{padding:8px 12px;font-size:13px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);outline:none}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:4px;padding:6px 10px;border:none;border-radius:8px;font-size:11px;font-weight:500;cursor:pointer;transition:all .15s;text-decoration:none}
        .btn-sm{padding:4px 8px;font-size:10px}
        .btn-red{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn-red:hover{background:rgba(248,113,113,.25)}
        .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)}
        .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:12px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .page-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .text-dim{color:var(--text-dim)}
        .mb-4{margin-bottom:16px}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @media(max-width:768px){
            .stat-cards{grid-template-columns:1fr 1fr;gap:6px}
            .stat-card{padding:8px;gap:6px}
            .stat-icon{width:28px;height:28px;border-radius:6px}
            .stat-icon svg{width:14px;height:14px}
            .stat-value{font-size:13px}
            .stat-label{font-size:9px}
            .card{padding:10px}
            .card-title{font-size:12px;margin-bottom:6px}
            .page-header{flex-direction:column;gap:8px}
            .page-header h1{font-size:15px}
            .page-header-sub{font-size:10px}
            .breadcrumbs{font-size:10px;margin-bottom:8px}
            .search-bar{flex-direction:column;gap:4px}
            .search-input,.search-select{padding:7px 9px;font-size:12px}
            .log-output{max-height:350px;padding:8px;font-size:10px;line-height:1.4}
            .log-line{gap:4px}
            .log-time{font-size:9px}
            .log-source{font-size:9px}
            .log-level{font-size:8px;padding:1px 4px}
            .log-message{font-size:10px}
            .btn-sm{padding:3px 6px;font-size:9px}
        }
    </style>
</head>
<body>
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('logs', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('System Logs', 'logs') }}

            <div class="page">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin">Admin</a>
                    <span class="sep">></span>
                    <span class="current">Logs</span>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="page-header fade-in">
                    <div>
                        <h1>Log Viewer</h1>
                        <p class="page-header-sub">System logs and activity monitoring.</p>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <select class="search-select" id="logLines" onchange="filterLogs()">
                            <option value="100">100 lines</option>
                            <option value="200">200 lines</option>
                            <option value="500" selected>500 lines</option>
                        </select>
                        {% if session.get('is_admin') %}
                        <form method="POST" action="/logs/clear" style="display: inline;">
                            <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Clear all logs?')">
                                <svg width="14" height="14"><use href="#icon-trash"/></svg>
                                Clear
                            </button>
                        </form>
                        {% endif %}
                    </div>
                </div>

                <div class="stat-cards fade-in" style="grid-template-columns: repeat(4, 1fr);">
                    <div class="stat-card">
                        <div class="stat-icon blue">
                            <svg width="20" height="20"><use href="#icon-terminal"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Log File</div>
                            <div class="stat-value" style="font-size: 14px;">activity_log</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <svg width="20" height="20"><use href="#icon-server"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total Entries</div>
                            <div class="stat-value">{{ logs|length }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon yellow">
                            <svg width="20" height="20"><use href="#icon-check-circle"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Lines Shown</div>
                            <div class="stat-value" id="linesShown">{{ logs|length }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon red">
                            <svg width="20" height="20"><use href="#icon-bolt"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Last Updated</div>
                            <div class="stat-value" style="font-size: 14px;">Now</div>
                        </div>
                    </div>
                </div>

                <div class="card fade-in mb-4">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-terminal"/></svg>
                        Filter Logs
                    </div>
                    <div class="search-bar" style="margin-top: 12px; margin-bottom: 0;">
                        <input type="text" class="search-input" placeholder="Search logs..." id="logSearch" oninput="filterLogs()">
                        <select class="search-select" id="logLevel" onchange="filterLogs()">
                            <option value="">All Levels</option>
                            <option value="info">Info</option>
                            <option value="warning">Warning</option>
                            <option value="error">Error</option>
                        </select>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-terminal"/></svg>
                        Log Output
                        <span class="text-dim" style="font-size: 12px; font-weight: 400; margin-left: auto;">Real-time log viewer</span>
                    </div>
                    <div class="log-output" id="logOutput">
                        {% for log in logs %}
                        <div class="log-line" data-level="{{ log['action'] }}" data-message="{{ log['action'] }} {{ log['resource'] or '' }} {{ log['details'] or '' }}" data-username="{{ log['username'] }}">
                            <span class="log-time">{{ log['created_at'][:19] }}</span>
                            {% if is_admin %}
                            <span class="log-source">[{{ log['username'] }}]</span>
                            {% endif %}
                            <span class="log-level level-{{ 'info' if log['action'] in ['login', 'register', 'start_vps', 'create_vps', 'regen_api_key', 'update_profile'] else 'warning' if log['action'] in ['stop_vps', 'delete_vps', 'logout'] else 'error' }}">{{ log['action']|upper }}</span>
                            <span class="log-source">[{{ log['resource'] or 'system' }}]</span>
                            <span class="log-message">{{ log['details'] or '' }}</span>
                        </div>
                        {% endfor %}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid var(--border); margin-top: 12px;">
                        <span class="text-dim" style="font-size: 12px;">Ready</span>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-ghost btn-sm" onclick="document.getElementById('logOutput').scrollTop = 0">
                                <svg width="12" height="12"><use href="#icon-chevron-left"/></svg>
                                Top
                            </button>
                            <button class="btn btn-ghost btn-sm" onclick="document.getElementById('logOutput').scrollTop = document.getElementById('logOutput').scrollHeight">
                                Bottom
                                <svg width="12" height="12" style="transform: rotate(90deg);"><use href="#icon-chevron-left"/></svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    <script>
        function filterLogs() {
            const query = document.getElementById('logSearch').value.toLowerCase();
            const level = document.getElementById('logLevel').value;
            let visible = 0;
            document.querySelectorAll('.log-line').forEach(line => {
                const msg = line.dataset.message.toLowerCase();
                const username = (line.dataset.username || '').toLowerCase();
                const action = line.dataset.level;
                const matchQuery = !query || msg.includes(query) || username.includes(query);
                const matchLevel = !level || action === level;
                const show = matchQuery && matchLevel;
                line.style.display = show ? '' : 'none';
                if (show) visible++;
            });
            document.getElementById('linesShown').textContent = visible;
        }
    </script>
</body>
</html>
""", 'users.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Users — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .stat-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:16px;display:flex;align-items:center;gap:12px;transition:transform .2s,box-shadow .2s}
        .stat-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.25)}
        .stat-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:20px}
        .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .stat-icon.blue{background:rgba(96,165,250,.12);color:#60a5fa}
        .stat-icon.green{background:rgba(52,211,153,.12);color:#34d399}
        .stat-info{display:flex;flex-direction:column}
        .stat-label{font-size:12px;color:var(--text-dim)}
        .stat-value{font-size:20px;font-weight:700;color:var(--text)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
        table{width:100%;border-collapse:collapse}
        thead{background:var(--bg-input)}
        th{padding:10px 14px;font-size:12px;font-weight:600;color:var(--text-muted);text-align:left;border-bottom:1px solid var(--border)}
        td{padding:10px 14px;font-size:13px;color:var(--text);border-bottom:1px solid var(--border)}
        tr:last-child td{border-bottom:none}
        tr:hover td{background:rgba(255,255,255,.02)}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .status-banned{background:rgba(248,113,113,.12);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:4px;padding:6px 10px;border:none;border-radius:8px;font-size:11px;font-weight:500;cursor:pointer;transition:all .15s;text-decoration:none}
        .btn-sm{padding:4px 8px;font-size:10px}
        .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)}
        .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
        .btn-green{background:rgba(52,211,153,.15);color:var(--green);border:1px solid rgba(52,211,153,.2)}
        .btn-green:hover{background:rgba(52,211,153,.25)}
        .btn-yellow{background:rgba(251,191,36,.15);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
        .btn-yellow:hover{background:rgba(251,191,36,.25)}
        .btn-red{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn-red:hover{background:rgba(248,113,113,.25)}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .user-name { font-weight: 500; }
        .user-email { color: var(--text-dim); }
        .user-meta { display: none; }
        @media (max-width: 768px) {
            .stat-cards { grid-template-columns: 1fr 1fr; gap: 6px; }
            .page-header { flex-direction: column; gap: 6px; }
            .stat-card { padding: 8px; gap: 6px; }
            .stat-icon { width: 28px; height: 28px; border-radius: 6px; }
            .stat-icon svg { width: 14px; height: 14px; }
            .stat-value { font-size: 15px; }
            .stat-label { font-size: 9px; }
            .card { padding: 8px; }
            .card-title { font-size: 12px; margin-bottom: 4px; }
            .page-header h1 { font-size: 15px; }
            .page-header-sub { font-size: 10px; }
            .status { padding: 2px 6px; font-size: 9px; }
            .breadcrumbs { font-size: 10px; margin-bottom: 8px; }
            table { font-size: 11px; }
            th { padding: 6px 6px; font-size: 10px; }
            td { padding: 6px 6px; }
            th.email-col, td.email-col { display: none; }
            th.joined-col, td.joined-col { display: none; }
            .user-name { display: block; font-size: 11px; }
            .user-email { display: block; font-size: 9px; }
            .user-meta { display: block; font-size: 9px; color: var(--text-dim); margin-top: 1px; }
            .action-btns { flex-direction: column; gap: 2px !important; }
            .action-btns .btn { padding: 3px 6px; font-size: 9px; }
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('users', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Users', 'users') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin">Admin</a>
                    <span class="sep">></span>
                    <span class="current">Users</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>User Management</h1>
                        <p class="page-header-sub">All registered users on the platform.</p>
                    </div>
                </div>

                <div class="stat-cards fade-in">
                    <div class="stat-card">
                        <div class="stat-icon blue">
                            <svg width="20" height="20"><use href="#icon-users"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total Users</div>
                            <div class="stat-value">{{ users|length }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <svg width="20" height="20"><use href="#icon-user"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Admins</div>
                            <div class="stat-value">{{ users|selectattr('is_admin', 'equalto', 1)|list|length }}</div>
                        </div>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-users"/></svg>
                        All Users
                    </div>
                    <div class="table-wrap" style="margin-top:12px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th class="email-col">Email</th>
                                    <th>Role</th>
                                    <th>Status</th>
                                    <th class="joined-col">Joined</th>
                                    <th style="text-align:right;">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for user in users %}
                                <tr>
                                    <td>
                                        <span class="user-name">{{ user['username'] }}</span>
                                        <span class="user-email">{{ user['email'] }}</span>
                                        <span class="user-meta">{{ user['created_at'][:10] }}</span>
                                    </td>
                                    <td class="email-col text-dim">{{ user['email'] }}</td>
                                    <td>
                                        {% if user['role'] == 'owner' %}
                                        <span class="status" style="background:rgba(251,191,36,.12);color:var(--yellow);">Owner</span>
                                        {% elif user['is_admin'] %}
                                        <span class="status status-running">Admin</span>
                                        {% else %}
                                        <span class="status status-stopped">User</span>
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if user['is_banned'] %}
                                        <span class="status status-banned">Banned</span>
                                        {% else %}
                                        <span style="font-size:10px;color:var(--text-dim);">Active</span>
                                        {% endif %}
                                    </td>
                                    <td class="joined-col text-dim">{{ user['created_at'][:10] }}</td>
                                    <td style="text-align:right;">
                                        <div class="action-btns" style="display:flex;gap:4px;justify-content:flex-end;">
                                            {% if not user['is_admin'] %}
                                            <form method="POST" action="/admin/promote/{{ user['id'] }}" style="display:inline;">
                                                <button type="submit" class="btn btn-green btn-sm" title="Make Admin">
                                                    <svg width="10" height="10"><use href="#icon-users"/></svg>
                                                    Admin
                                                </button>
                                            </form>
                                            {% else %}
                                            {% if user['id'] != session['user_id'] and user['role'] != 'owner' %}
                                            <form method="POST" action="/admin/demote/{{ user['id'] }}" style="display:inline;">
                                                <button type="submit" class="btn btn-yellow btn-sm" onclick="return confirm('Demote this user?')" title="Remove Admin">
                                                    Demote
                                                </button>
                                            </form>
                                            {% endif %}
                                            {% endif %}

                                            {% if not user['is_admin'] %}
                                            {% if user['is_banned'] %}
                                            <form method="POST" action="/admin/unban/{{ user['id'] }}" style="display:inline;">
                                                <button type="submit" class="btn btn-ghost btn-sm" title="Unban">
                                                    Unban
                                                </button>
                                            </form>
                                            {% else %}
                                            <form method="POST" action="/admin/ban/{{ user['id'] }}" style="display:inline;">
                                                <button type="submit" class="btn btn-red btn-sm" onclick="return confirm('Ban this user?')" title="Ban User">
                                                    <svg width="10" height="10"><use href="#icon-ban"/></svg>
                                                    Ban
                                                </button>
                                            </form>
                                            {% endif %}
                                            {% endif %}
                                        </div>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'file_manager.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Manager — {{ vps['container_name'] }}</title>
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        .file-path { display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-bottom:12px;font-size:12px; }
        .file-path a { color:var(--accent);text-decoration:none; }
        .file-path span { color:var(--text-dim); }
        .file-icon { width:16px;height:16px;margin-right:6px; }
        .file-row { display:flex;align-items:center;padding:8px 10px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .15s; }
        .file-row:hover { background:var(--bg-secondary); }
        .file-row:last-child { border-bottom:none; }
        .file-actions { margin-left:auto;display:flex;gap:4px; }
        .file-size { font-size:11px;color:var(--text-dim);min-width:60px;text-align:right; }
        .file-perms { font-size:11px;color:var(--text-dim);font-family:monospace;margin-left:12px; }
        @media(max-width:640px){
            .file-perms { display:none; }
            .file-size { display:none; }
            .file-actions { gap:2px; }
        }
    </style>
</head>
<body>
    {% include 'icons.html' %}
    <div class="layout">
        {% from 'components.html' import sidebar, topbar, overlay with context %}
        {{ sidebar('myvps', settings, custom_icon) }}
        <main class="main-content">
            {{ topbar(vps['container_name'] ~ ' — File Manager', 'myvps') }}
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="page-header fade-in">
                    <div>
                        <div class="file-path">
                            {% set parts = current_path.strip('/').split('/') %}
                            <a href="/vps/{{ vps['id'] }}/files?path=/">/</a>
                            {% set ns = namespace(full='') %}
                            {% for p in parts %}
                                {% if p %}
                                {% set ns.full = ns.full ~ '/' ~ p %}
                                <span>/</span><a href="/vps/{{ vps['id'] }}/files?path={{ ns.full }}">{{ p }}</a>
                                {% endif %}
                            {% endfor %}
                        </div>
                    </div>
                    <div style="display:flex;gap:6px;">
                        <a href="/vps/{{ vps['id'] }}" class="btn btn-ghost btn-sm">Back</a>
                    </div>
                </div>

                <div class="card fade-in">
                    <div style="padding:12px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                        <span style="font-size:13px;font-weight:600;">{{ current_path }}</span>
                        <div style="display:flex;gap:6px;">
                            <button onclick="uploadFile()" class="btn btn-ghost btn-sm">Upload</button>
                            <button onclick="newFile()" class="btn btn-ghost btn-sm">New File</button>
                            <button onclick="newFolder()" class="btn btn-ghost btn-sm">New Folder</button>
                        </div>
                    </div>

                    {% if current_path != '/' %}
                    <a href="/vps/{{ vps['id'] }}/files?path={{ '/'.join(current_path.strip('/').split('/')[:-1]) or '/' }}" class="file-row" style="text-decoration:none;color:var(--text);">
                        <svg width="16" height="16" style="margin-right:6px;"><use href="#icon-server"/></svg>
                        <span style="font-size:13px;">.. (Back)</span>
                    </a>
                    {% endif %}

                    {% for f in files %}
                    {% if f['is_dir'] %}
                    <a href="/vps/{{ vps['id'] }}/files?path={{ current_path.rstrip('/') }}/{{ f['name'] }}" class="file-row" style="text-decoration:none;color:var(--text);">
                        <svg width="16" height="16" style="margin-right:6px;color:var(--accent);"><use href="#icon-server"/></svg>
                        <span style="font-size:13px;">{{ f['name'] }}</span>
                        <span class="file-perms">{{ f.get('permissions', '') }}</span>
                        <span class="file-size">{{ f.get('size', '') }}</span>
                        <div class="file-actions">
                            <button onclick="event.preventDefault();deleteFile('{{ current_path.rstrip('/') }}/{{ f['name'] }}')" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px;color:var(--red);">Delete</button>
                        </div>
                    </a>
                    {% endif %}
                    {% endfor %}

                    {% for f in files %}
                    {% if not f['is_dir'] %}
                    <div class="file-row" onclick="editFile('{{ current_path.rstrip('/') }}/{{ f['name'] }}')">
                        <svg width="16" height="16" style="margin-right:6px;color:var(--text-dim);"><use href="#icon-terminal"/></svg>
                        <span style="font-size:13px;">{{ f['name'] }}</span>
                        <span class="file-perms">{{ f.get('permissions', '') }}</span>
                        <span class="file-size">{{ f.get('size', '') }}</span>
                        <div class="file-actions">
                            <button onclick="event.stopPropagation();downloadFile('{{ current_path.rstrip('/') }}/{{ f['name'] }}')" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px;">Download</button>
                            <button onclick="event.stopPropagation();deleteFile('{{ current_path.rstrip('/') }}/{{ f['name'] }}')" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px;color:var(--red);">Delete</button>
                        </div>
                    </div>
                    {% endif %}
                    {% endfor %}

                    {% if not files %}
                    <div style="padding:24px;text-align:center;color:var(--text-dim);font-size:13px;">This folder is empty.</div>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>

    <div id="editor-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;display:none;align-items:center;justify-content:center;">
        <div style="background:var(--bg);border:1px solid var(--border);border-radius:12px;width:90%;max-width:800px;max-height:90vh;display:flex;flex-direction:column;">
            <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
                <span id="editor-filename" style="font-size:13px;font-weight:600;"></span>
                <div style="display:flex;gap:6px;">
                    <button onclick="saveFile()" class="btn btn-primary btn-sm">Save</button>
                    <button onclick="closeEditor()" class="btn btn-ghost btn-sm">Cancel</button>
                </div>
            </div>
            <textarea id="editor-content" style="flex:1;min-height:400px;padding:12px;font-family:monospace;font-size:12px;background:var(--bg-secondary);border:none;color:var(--text);resize:none;outline:none;"></textarea>
        </div>
    </div>

    <input type="file" id="file-input" style="display:none;" onchange="doUpload(this)">

    {{ overlay() }}
    <script src="/static/js/main.js"></script>
    <script>
    let currentEditPath = '';
    const vpsId = {{ vps['id'] }};
    const currentDir = '{{ current_path }}';

    function editFile(path) {
        currentEditPath = path;
        document.getElementById('editor-filename').textContent = path;
        document.getElementById('editor-modal').style.display = 'flex';
        fetch(`/vps/${vpsId}/files/read?path=${encodeURIComponent(path)}`)
            .then(r => r.json())
            .then(d => {
                document.getElementById('editor-content').value = d.content || '';
            })
            .catch(() => {
                document.getElementById('editor-content').value = 'Error loading file';
            });
    }

    function saveFile() {
        const content = document.getElementById('editor-content').value;
        fetch(`/vps/${vpsId}/files/write`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path: currentEditPath, content: content})
        })
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                closeEditor();
                location.reload();
            }
        });
    }

    function closeEditor() {
        document.getElementById('editor-modal').style.display = 'none';
    }

    function uploadFile() {
        document.getElementById('file-input').click();
    }

    function doUpload(input) {
        if (!input.files[0]) return;
        const fd = new FormData();
        fd.append('file', input.files[0]);
        fd.append('path', currentDir);
        fetch(`/vps/${vpsId}/files/upload`, {method: 'POST', body: fd})
            .then(() => location.reload());
    }

    function newFolder() {
        const name = prompt('Folder name:');
        if (!name) return;
        fetch(`/vps/${vpsId}/files/mkdir`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path: currentDir + '/' + name})
        })
        .then(r => r.json())
        .then(d => { if (d.success) location.reload(); });
    }

    function newFile() {
        const name = prompt('File name:');
        if (!name) return;
        fetch(`/vps/${vpsId}/files/write`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path: currentDir + '/' + name, content: ''})
        })
        .then(r => r.json())
        .then(d => { if (d.success) location.reload(); });
    }

    function deleteFile(path) {
        if (!confirm('Delete ' + path.split('/').pop() + '?')) return;
        fetch(`/vps/${vpsId}/files/delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path: path})
        })
        .then(r => r.json())
        .then(d => { if (d.success) location.reload(); });
    }

    function downloadFile(path) {
        window.location.href = `/vps/${vpsId}/files/download?path=${encodeURIComponent(path)}`;
    }
    </script>
</body>
</html>
""", **{'process_manager.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Process Manager — {{ vps['container_name'] }}</title>
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        .proc-bar { height:4px;border-radius:2px;background:var(--border);overflow:hidden; }
        .proc-bar-fill { height:100%;border-radius:2px;transition:width .3s; }
        .proc-cpu { background:var(--accent); }
        .proc-mem { background:#a78bfa; }
        .proc-row { display:grid;grid-template-columns:70px 80px 60px 60px 1fr 50px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border);font-size:12px;gap:8px; }
        .proc-header { font-weight:600;color:var(--text-dim);font-size:11px;text-transform:uppercase; }
        .proc-cmd { font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text); }
        @media(max-width:640px){
            .proc-row { grid-template-columns:50px 50px 1fr 40px; }
            .proc-header { font-size:10px; }
            .proc-mem-col, .proc-user-col { display:none; }
        }
    </style>
</head>
<body>
    {% include 'icons.html' %}
    <div class="layout">
        {% from 'components.html' import sidebar, topbar, overlay with context %}
        {{ sidebar('myvps', settings, custom_icon) }}
        <main class="main-content">
            {{ topbar(vps['container_name'] ~ ' — Processes', 'myvps') }}
            <div class="content">
                <div class="page-header fade-in">
                    <div style="display:flex;gap:6px;">
                        <button onclick="location.reload()" class="btn btn-ghost btn-sm">Refresh</button>
                        <a href="/vps/{{ vps['id'] }}" class="btn btn-ghost btn-sm">Back</a>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="proc-row proc-header">
                        <div>PID</div>
                        <div class="proc-user-col">User</div>
                        <div>CPU%</div>
                        <div class="proc-mem-col">MEM%</div>
                        <div>Command</div>
                        <div></div>
                    </div>

                    {% if processes %}
                    {% for p in processes %}
                    <div class="proc-row">
                        <div class="mono" style="color:var(--accent);">{{ p['pid'] }}</div>
                        <div class="proc-user-col" style="color:var(--text-dim);">{{ p['user'] }}</div>
                        <div>
                            <div style="display:flex;align-items:center;gap:6px;">
                                <span>{{ p['cpu'] }}%</span>
                                <div class="proc-bar" style="flex:1;"><div class="proc-bar-fill proc-cpu" style="width:{{ [p['cpu']|float, 100]|min }}%;"></div></div>
                            </div>
                        </div>
                        <div class="proc-mem-col">
                            <div style="display:flex;align-items:center;gap:6px;">
                                <span>{{ p['mem'] }}%</span>
                                <div class="proc-bar" style="flex:1;"><div class="proc-bar-fill proc-mem" style="width:{{ [p['mem']|float, 100]|min }}%;"></div></div>
                            </div>
                        </div>
                        <div class="proc-cmd" title="{{ p['command'] }}">{{ p['command'] }}</div>
                        <div>
                            <button onclick="killProcess('{{ p['pid'] }}')" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px;color:var(--red);">Kill</button>
                        </div>
                    </div>
                    {% endfor %}
                    {% else %}
                    <div style="padding:24px;text-align:center;color:var(--text-dim);font-size:13px;">No processes found.</div>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>
    {{ overlay() }}
    <script src="/static/js/main.js"></script>
    <script>
    const vpsId = {{ vps['id'] }};

    function killProcess(pid) {
        if (!confirm('Kill process ' + pid + '?')) return;
        fetch(`/vps/${vpsId}/processes/kill`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pid: pid})
        })
        .then(r => r.json())
        .then(d => { location.reload(); });
    }
    </script>
</body>
</html>
""", 'notifications.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Notifications — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
        table{width:100%;border-collapse:collapse}
        thead{background:var(--bg-input)}
        th{padding:10px 14px;font-size:12px;font-weight:600;color:var(--text-muted);text-align:left;border-bottom:1px solid var(--border)}
        td{padding:10px 14px;font-size:13px;color:var(--text);border-bottom:1px solid var(--border)}
        tr:last-child td{border-bottom:none}
        tr:hover td{background:rgba(255,255,255,.02)}
        .mono{font-family:monospace}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .status-creating{background:rgba(251,191,36,.12);color:var(--yellow)}
        .empty-state{text-align:center;padding:40px 20px;color:var(--text-dim)}
        .empty-icon{width:64px;height:64px;border-radius:12px;background:var(--bg-input);display:flex;align-items:center;justify-content:center;margin:0 auto 12px;color:var(--text-muted)}
        .empty-state h3{font-size:15px;color:var(--text);margin-bottom:4px}
        .empty-state p{font-size:13px}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .ip-col,.time-col{display:table-cell}
        .log-detail{display:none}
        @media(max-width:768px){
            .card{padding:10px}
            .card-title{font-size:12px;margin-bottom:6px}
            .page-header h1{font-size:15px}
            .page-header-sub{font-size:10px}
            .breadcrumbs{font-size:10px;margin-bottom:8px}
            table{font-size:11px}
            th{padding:5px 6px;font-size:9px}
            td{padding:5px 6px}
            .status{padding:2px 6px;font-size:9px}
            .ip-col,.time-col{display:none}
            .log-detail{display:block;font-size:9px;color:var(--text-dim);margin-top:1px}
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('notifications', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Notifications', 'notifications') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <span class="current">Notifications</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>Notifications</h1>
                        <p class="page-header-sub">Your recent activity and alerts.</p>
                    </div>
                </div>

                <div class="card fade-in">
                    {% if logs %}
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Action</th>
                                    <th>Resource</th>
                                    <th class="log-detail">Details</th>
                                    <th class="ip-col">IP</th>
                                    <th class="time-col">Time</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for log in logs %}
                                <tr>
                                    <td>
                                        <span class="status status-{{ 'running' if log['action'] in ['login', 'register', 'start_vps', 'create_vps'] else 'stopped' if log['action'] in ['logout', 'delete_vps'] else 'creating' }}">
                                            {{ log['action']|replace('_', ' ')|title }}
                                        </span>
                                        <span class="log-detail">{{ log['details'] or '' }}</span>
                                    </td>
                                    <td class="text-dim">{{ log['resource'] or '—' }}</td>
                                    <td class="log-detail text-dim" style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;">{{ log['details'] or '—' }}</td>
                                    <td class="ip-col mono" style="font-size:12px;">{{ log['ip_address'] or '—' }}</td>
                                    <td class="time-col text-dim">{{ log['created_at'][:16] }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="empty-state">
                        <div class="empty-icon">
                            <svg width="28" height="28"><use href="#icon-bell"/></svg>
                        </div>
                        <h3>No Notifications</h3>
                        <p>You're all caught up!</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'tickets.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omega Panel</title>
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    {% include 'icons.html' %}
    <div class="layout">
        {% from 'components.html' import sidebar, topbar, overlay with context %}
        {{ sidebar('tickets', settings, custom_icon) }}
        <main class="main-content">
            {{ topbar('Support Tickets', 'tickets') }}
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                {% if not session.get('is_admin') %}
                <div class="card fade-in" style="margin-bottom:16px;">
                    <div class="card-title">New Ticket</div>
                    <form method="POST" action="/tickets/create">
                        <div style="margin-bottom:10px;">
                            <input type="text" name="subject" class="form-control" placeholder="Subject" required style="width:100%;padding:8px 12px;font-size:13px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);">
                        </div>
                        <div style="margin-bottom:10px;">
                            <textarea name="message" class="form-control" placeholder="Describe your issue..." required rows="3" style="width:100%;padding:8px 12px;font-size:13px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);resize:vertical;"></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary">Submit Ticket</button>
                    </form>
                </div>
                {% endif %}

                <div class="card fade-in">
                    <div class="card-title">
                        {% if session.get('is_admin') %}All Tickets{% else %}My Tickets{% endif %}
                    </div>
                    {% if tickets %}
                    <div style="overflow-x:auto;">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Subject</th>
                                    <th>User</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for t in tickets %}
                                <tr>
                                    <td>#{{ t['id'] }}</td>
                                    <td>{{ t['subject'] }}</td>
                                    <td>{{ t['username'] }}</td>
                                    <td>
                                        <span class="status status-{{ 'running' if t['status'] == 'open' else 'stopped' }}">
                                            <span class="status-dot"></span>
                                            {{ t['status']|capitalize }}
                                        </span>
                                    </td>
                                    <td style="font-size:12px;color:var(--text-dim);">{{ t['created_at'][:16] }}</td>
                                    <td>
                                        <a href="/tickets/{{ t['id'] }}" class="btn btn-ghost btn-sm">View</a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <p style="color:var(--text-dim);font-size:13px;">No tickets yet.</p>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>
    {{ overlay() }}
    <script src="/static/js/main.js"></script>
</body>
</html>
""", 'ticket_detail.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omega Panel</title>
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    {% include 'icons.html' %}
    <div class="layout">
        {% from 'components.html' import sidebar, topbar, overlay with context %}
        {{ sidebar('tickets', settings, custom_icon) }}
        <main class="main-content">
            {{ topbar('Ticket #' ~ ticket['id'], 'tickets') }}
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="page-header fade-in">
                    <div style="display:flex;gap:6px;">
                        {% if ticket['status'] == 'open' %}
                        <form method="POST" action="/tickets/{{ ticket['id'] }}/close">
                            <button type="submit" class="btn btn-ghost btn-sm">Close Ticket</button>
                        </form>
                        {% else %}
                        <form method="POST" action="/tickets/{{ ticket['id'] }}/reopen">
                            <button type="submit" class="btn btn-ghost btn-sm">Reopen</button>
                        </form>
                        {% endif %}
                        <form method="POST" action="/tickets/{{ ticket['id'] }}/delete">
                            <button type="submit" class="btn btn-ghost btn-sm" style="color:var(--red);" onclick="return confirm('Delete this ticket?')">Delete</button>
                        </form>
                        <a href="/tickets" class="btn btn-ghost btn-sm">Back</a>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="card-title">
                        <span class="status status-{{ 'running' if ticket['status'] == 'open' else 'stopped' }}">
                            <span class="status-dot"></span>
                            {{ ticket['status']|capitalize }}
                        </span>
                    </div>

                    <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:16px;">
                        {% for r in replies %}
                        <div style="padding:12px;border-radius:8px;border:1px solid var(--border);background:{{ 'rgba(139,92,246,.05)' if r['is_admin'] else 'var(--bg-secondary)' }};">
                            <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                                <span style="font-size:12px;font-weight:600;color:{{ 'var(--accent)' if r['is_admin'] else 'var(--text)' }};">
                                    {{ r['username'] }} {% if r['is_admin'] %}<span style="font-size:10px;background:var(--accent);color:#000;padding:1px 6px;border-radius:8px;margin-left:4px;">Admin</span>{% endif %}
                                </span>
                                <span style="font-size:11px;color:var(--text-dim);">{{ r['created_at'][:16] }}</span>
                            </div>
                            <p style="font-size:13px;color:var(--text);white-space:pre-wrap;">{{ r['message'] }}</p>
                        </div>
                        {% endfor %}
                    </div>

                    {% if ticket['status'] == 'open' %}
                    <form method="POST" action="/tickets/{{ ticket['id'] }}/reply">
                        <div style="margin-bottom:10px;">
                            <textarea name="message" class="form-control" placeholder="Type your reply..." required rows="3" style="width:100%;padding:8px 12px;font-size:13px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);resize:vertical;"></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary">Reply</button>
                    </form>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>
    {{ overlay() }}
    <script src="/static/js/main.js"></script>
</body>
</html>
""", 'schedules.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omega Panel</title>
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    {% include 'icons.html' %}
    <div class="layout">
        {% from 'components.html' import sidebar, topbar, overlay with context %}
        {{ sidebar('schedules', settings, custom_icon) }}
        <main class="main-content">
            {{ topbar('VPS Schedules', 'schedules') }}
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="card fade-in" style="margin-bottom:16px;">
                    <div class="card-title">Create Schedule</div>
                    <form method="POST" action="/schedules/create">
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
                            <div>
                                <label style="font-size:11px;color:var(--text-dim);display:block;margin-bottom:4px;">VPS</label>
                                <select name="vps_id" class="form-control" required style="width:100%;padding:8px;font-size:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);">
                                    {% for v in user_vps %}
                                    <option value="{{ v['id'] }}">{{ v['container_name'] }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div>
                                <label style="font-size:11px;color:var(--text-dim);display:block;margin-bottom:4px;">Action</label>
                                <select name="action" class="form-control" required style="width:100%;padding:8px;font-size:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);">
                                    <option value="start">Start</option>
                                    <option value="stop">Stop</option>
                                    <option value="restart">Restart</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size:11px;color:var(--text-dim);display:block;margin-bottom:4px;">Time (HH:MM)</label>
                                <input type="time" name="time" class="form-control" required style="width:100%;padding:8px;font-size:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);">
                            </div>
                            <div>
                                <label style="font-size:11px;color:var(--text-dim);display:block;margin-bottom:4px;">Days</label>
                                <select name="days" class="form-control" style="width:100%;padding:8px;font-size:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;color:var(--text);">
                                    <option value="everyday">Every Day</option>
                                    <option value="monday,tuesday,wednesday,thursday,friday">Weekdays</option>
                                    <option value="saturday,sunday">Weekends</option>
                                </select>
                            </div>
                        </div>
                        <button type="submit" class="btn btn-primary">Create Schedule</button>
                    </form>
                </div>

                <div class="card fade-in">
                    <div class="card-title">Active Schedules</div>
                    {% if schedules %}
                    <div style="overflow-x:auto;">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>VPS</th>
                                    <th>Action</th>
                                    <th>Time</th>
                                    <th>Days</th>
                                    <th>Status</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for s in schedules %}
                                <tr>
                                    <td>{{ s['container_name'] }}</td>
                                    <td><span style="text-transform:capitalize;">{{ s['action'] }}</span></td>
                                    <td class="mono">{{ s['time'] }}</td>
                                    <td style="font-size:12px;">{{ s['days'] }}</td>
                                    <td>
                                        <span class="status status-{{ 'running' if s['enabled'] else 'stopped' }}">
                                            <span class="status-dot"></span>
                                            {{ 'Enabled' if s['enabled'] else 'Disabled' }}
                                        </span>
                                    </td>
                                    <td style="display:flex;gap:4px;">
                                        <form method="POST" action="/schedules/{{ s['id'] }}/toggle">
                                            <button type="submit" class="btn btn-ghost btn-sm" style="font-size:11px;">{{ 'Disable' if s['enabled'] else 'Enable' }}</button>
                                        </form>
                                        <form method="POST" action="/schedules/{{ s['id'] }}/delete">
                                            <button type="submit" class="btn btn-ghost btn-sm" style="font-size:11px;color:var(--red);" onclick="return confirm('Delete this schedule?')">Delete</button>
                                        </form>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <p style="color:var(--text-dim);font-size:13px;">No schedules yet.</p>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>
    {{ overlay() }}
    <script src="/static/js/main.js"></script>
</body>
</html>
""", 'system_info.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>System Info — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
.page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;transition:transform .2s,box-shadow .2s,border-color .2s}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .card:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.3);border-color:var(--border-focus)}
        .stat-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:16px;transition:transform .2s,box-shadow .2s}
        .stat-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.25)}
        .stat-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
        .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .stat-icon.blue{background:rgba(96,165,250,.12);color:#60a5fa}
        .stat-icon.green{background:rgba(52,211,153,.12);color:#34d399}
        .stat-icon.yellow{background:rgba(251,191,36,.12);color:#fbbf24}
        .stat-icon.orange{background:rgba(251,146,60,.12);color:#fb923c}
        .stat-info{display:flex;flex-direction:column}
        .stat-label{font-size:12px;color:var(--text-dim)}
        .stat-value{font-size:20px;font-weight:700;color:var(--text)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .card-title svg{color:var(--text-muted)}
        .info-list{display:flex;flex-direction:column;gap:12px}
        .info-item{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}
        .info-item:last-child{border-bottom:none}
        .info-label{font-size:12px;color:var(--text-dim)}
        .info-value{font-size:13px;color:var(--text);font-weight:500}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none;transition:color .15s}
        .breadcrumbs a:hover{color:var(--text)}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .info-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
        @media(max-width:768px){
            .stat-cards{grid-template-columns:1fr 1fr;gap:6px}
            .stat-card{padding:8px;gap:6px}
            .stat-icon{width:28px;height:28px;border-radius:6px}
            .stat-icon svg{width:14px;height:14px}
            .stat-value{font-size:13px}
            .stat-label{font-size:9px}
            .card{padding:10px}
            .card-title{font-size:12px;margin-bottom:6px}
            .info-grid{grid-template-columns:1fr;gap:8px}
            .info-item{padding:6px 0}
            .info-label{font-size:10px}
            .info-value{font-size:11px}
            .page-header h1{font-size:15px}
            .page-header-sub{font-size:10px}
            .breadcrumbs{font-size:10px;margin-bottom:8px}
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('sysinfo', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('System Info', 'sysinfo') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <span class="current">System Info</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>System Information</h1>
                        <p class="page-header-sub">Server status and resource details.</p>
                    </div>
                </div>

                <div class="stat-cards fade-in">
                    <div class="stat-card">
                        <div class="stat-icon blue">
                            <svg width="20" height="20"><use href="#icon-cpu"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">CPU Usage</div>
                            <div class="stat-value">{{ info['cpu_percent'] }}%</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <svg width="20" height="20"><use href="#icon-bolt"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">RAM Usage</div>
                            <div class="stat-value">{{ info['ram_used'] }} / {{ info['ram_total'] }} GB</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon yellow">
                            <svg width="20" height="20"><use href="#icon-hard-drive"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Disk Usage</div>
                            <div class="stat-value">{{ info['disk_used'] }} / {{ info['disk_total'] }} GB</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon orange">
                            <svg width="20" height="20"><use href="#icon-server"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">LXC</div>
                            <div class="stat-value">v{{ info['lxd_version'] }}</div>
                        </div>
                    </div>
                </div>

                <div class="info-grid fade-in">
                    <div class="card fade-in">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-cpu"/></svg>
                            CPU
                        </div>
                        <div class="info-list">
                            <div class="info-item">
                                <span class="info-label">Cores</span>
                                <span class="info-value">{{ info['cpu_count'] }}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Usage</span>
                                <span class="info-value">{{ info['cpu_percent'] }}%</span>
                            </div>
                        </div>
                    </div>

                    <div class="card fade-in">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-bolt"/></svg>
                            Memory
                        </div>
                        <div class="info-list">
                            <div class="info-item">
                                <span class="info-label">Total</span>
                                <span class="info-value">{{ info['ram_total'] }} GB</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Used</span>
                                <span class="info-value">{{ info['ram_used'] }} GB ({{ info['ram_percent'] }}%)</span>
                            </div>
                        </div>
                    </div>

                    <div class="card fade-in">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-hard-drive"/></svg>
                            Disk
                        </div>
                        <div class="info-list">
                            <div class="info-item">
                                <span class="info-label">Total</span>
                                <span class="info-value">{{ info['disk_total'] }} GB</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Used</span>
                                <span class="info-value">{{ info['disk_used'] }} GB ({{ info['disk_percent'] }}%)</span>
                            </div>
                        </div>
                    </div>

                    <div class="card fade-in">
                        <div class="card-title">
                            <svg width="18" height="18"><use href="#icon-info"/></svg>
                            System
                        </div>
                        <div class="info-list">
                            <div class="info-item">
                                <span class="info-label">Platform</span>
                                <span class="info-value" style="font-size:11px;">{{ info['platform'][:30] }}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Python</span>
                                <span class="info-value">{{ info['python_version'] }}</span>
                            </div>
                            <div class="info-item">
                                <span class="info-label">Hostname</span>
                                <span class="info-value">{{ info['hostname'] }}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'os_icons.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OS Icons — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
</head>
<body>
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('osicons', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('OS Icons', 'osicons') }}

            <div class="page">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <span class="current">OS Icons</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>Operating System Icons</h1>
                        <p class="page-header-sub">Available operating systems for VPS deployment.</p>
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px;">
                    <div class="card fade-in" style="text-align: center; padding: 24px;">
                        <img src="https://img.icons8.com/?size=160&id=jboFV8ZOXgZR&format=png" alt="Ubuntu 22.04" style="width: 64px; height: 64px; margin: 0 auto 16px; display: block; object-fit: contain;">
                        <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 4px;">Ubuntu 22.04 (Jammy Jellyfish)</h3>
                        <p class="text-dim" style="font-size: 13px;">LTS Jammy Jellyfish</p>
                        <span class="status status-running" style="margin-top: 12px; display: inline-block;">Available</span>
                    </div>

                    <div class="card fade-in" style="text-align: center; padding: 24px;">
                        <img src="https://img.icons8.com/?size=160&id=jboFV8ZOXgZR&format=png" alt="Ubuntu 24.04" style="width: 64px; height: 64px; margin: 0 auto 16px; display: block; object-fit: contain;">
                        <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 4px;">Ubuntu 24.04 (Noble Numbat)</h3>
                        <p class="text-dim" style="font-size: 13px;">LTS Noble Numbat</p>
                        <span class="status status-running" style="margin-top: 12px; display: inline-block;">Available</span>
                    </div>

                    <div class="card fade-in" style="text-align: center; padding: 24px;">
                        <img src="https://img.icons8.com/?size=160&id=jboFV8ZOXgZR&format=png" alt="Ubuntu 26.04" style="width: 64px; height: 64px; margin: 0 auto 16px; display: block; object-fit: contain;">
                        <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 4px;">Ubuntu 26.04 (Resolute Raccoon)</h3>
                        <p class="text-dim" style="font-size: 13px;">Resolute Raccoon</p>
                        <span class="status status-running" style="margin-top: 12px; display: inline-block;">Available</span>
                    </div>

                    

                    
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'api_docs.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Docs — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        .page-advanced{background:var(--bg);background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(255,255,255,.03),transparent);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .endpoint{margin-bottom:16px;border:1px solid var(--border);border-radius:10px;overflow:hidden}
        .endpoint-header{display:flex;align-items:center;gap:8px;padding:10px 14px;background:var(--bg-input);cursor:pointer;transition:background .15s}
        .endpoint-header:hover{background:rgba(255,255,255,.04)}
        .method{font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;font-family:monospace;text-transform:uppercase}
        .method-get{background:rgba(52,211,153,.12);color:var(--green)}
        .method-post{background:rgba(96,165,250,.12);color:#60a5fa}
        .method-delete{background:rgba(248,113,113,.12);color:var(--red)}
        .endpoint-path{font-size:13px;font-family:monospace;color:var(--text);font-weight:500}
        .endpoint-desc{font-size:12px;color:var(--text-dim);margin-left:auto}
        .endpoint-body{padding:14px;display:none;font-size:12px;color:var(--text-muted)}
        .endpoint-body.open{display:block}
        .endpoint-body p{margin-bottom:8px;line-height:1.5}
        .endpoint-body strong{color:var(--text)}
        .code-block{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-family:monospace;font-size:11px;line-height:1.5;overflow-x:auto;margin:8px 0;color:var(--text-muted);white-space:pre}
        .param-table{width:100%;border-collapse:collapse;margin:8px 0}
        .param-table th{text-align:left;padding:6px 10px;font-size:11px;color:var(--text-dim);border-bottom:1px solid var(--border);font-weight:500}
        .param-table td{padding:6px 10px;font-size:11px;border-bottom:1px solid var(--border)}
        .param-name{font-family:monospace;color:var(--text);font-weight:500}
        .param-required{color:var(--red);font-size:10px}
        .param-optional{color:var(--text-dim);font-size:10px}
        .section-title{font-size:16px;font-weight:600;color:var(--text);margin:20px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
        .section-title svg{color:var(--text-dim)}
        .auth-badge{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-size:10px;font-weight:500;background:rgba(251,191,36,.1);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
        .rate-badge{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-size:10px;font-weight:500;background:rgba(96,165,250,.08);color:#60a5fa;border:1px solid rgba(96,165,250,.15)}
        .tag{display:inline-flex;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:500}
        .tag-admin{background:rgba(248,113,113,.12);color:var(--red)}
        .tag-user{background:rgba(52,211,153,.12);color:var(--green)}
        .tag-public{background:rgba(255,255,255,.06);color:var(--text-dim)}
        @media(max-width:768px){
            .card{padding:10px}
            .card-title{font-size:12px;margin-bottom:8px}
            .page-header h1{font-size:15px}
            .page-header-sub{font-size:10px}
            .breadcrumbs{font-size:10px;margin-bottom:8px}
            .endpoint-header{padding:8px 10px;flex-wrap:wrap}
            .endpoint-path{font-size:11px}
            .endpoint-desc{margin-left:0;margin-top:4px;font-size:10px}
            .endpoint-body{padding:10px}
            .section-title{font-size:14px}
            .code-block{font-size:10px;padding:8px}
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('apidocs', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('API Docs', 'apidocs') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <span class="current">API Docs</span>
                </div>

                <div class="page-header fade-in">
                    <div>
                        <h1>API Documentation</h1>
                        <p class="page-header-sub">REST API endpoints for Omega Panel. All endpoints require session auth (login) except public ones.</p>
                    </div>
                </div>

                <div class="card fade-in" style="margin-bottom:20px;">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-info"/></svg>
                        Authentication
                    </div>
                    <p style="font-size:12px;color:var(--text-muted);line-height:1.6;">
                        All API endpoints require a valid session (user must be logged in via the web interface). Admin-only endpoints require <code>is_admin</code> session flag.
                        Rate limits are configurable from <a href="/settings" style="color:var(--text);text-decoration:underline;">Settings</a>.
                    </p>
                    <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">
                        <span class="tag tag-public">Public — No auth</span>
                        <span class="tag tag-user">User — Login required</span>
                        <span class="tag tag-admin">Admin — Admin required</span>
                        <span class="auth-badge">Session-based auth</span>
                        <span class="rate-badge">Rate limited</span>
                    </div>
                </div>

                <!-- Panel API -->
                <div class="section-title fade-in">
                    <svg width="18" height="18"><use href="#icon-server"/></svg>
                    Panel API
                    <span class="text-dim" style="font-size:11px;font-weight:400;">(works for both local &amp; remote VPS)</span>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/vps/{id}/status</span>
                        <span class="tag tag-user" style="margin-left:4px;">User</span>
                        <span class="endpoint-desc">Get VPS container status</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns the LXD instance status for a VPS. Users can only access their own VPS; admins can access any.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "status": "running" | "stopped" | "not_found",
  "id": "container_id",
  "name": "container_name"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/vps/{id}/stats</span>
                        <span class="tag tag-user" style="margin-left:4px;">User</span>
                        <span class="endpoint-desc">Get live VPS resource usage</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns real-time CPU, RAM, network, and PID stats from the LXD instance.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "cpu_percent": 2.5,
  "memory_used": 134217728,
  "memory_limit": 2147483648,
  "memory_percent": 6.25,
  "network_rx": 123456,
  "network_tx": 654321,
  "pids": 5
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/system-stats</span>
                        <span class="tag tag-user" style="margin-left:4px;">User</span>
                        <span class="endpoint-desc">Get host machine stats</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns host server CPU, RAM, and disk usage.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "cpu_percent": 15.3,
  "ram_percent": 45.2,
  "ram_used": 3.6,
  "ram_total": 8.0,
  "disk_percent": 62.1,
  "disk_used": 49.7,
  "disk_total": 80.0
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/favicon</span>
                        <span class="tag tag-public" style="margin-left:4px;">Public</span>
                        <span class="endpoint-desc">Get custom favicon path</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns the custom favicon/icon path if set.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "icon": "/static/uploads/icon_xxx.png"
}</div>
                    </div>
                </div>

              

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/vps/{id}/set-expiry</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Set VPS expiration date</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Sets or clears the expiration date for a VPS. Authenticate with <code>X-API-Key</code> header using an admin's API key. When the expiration passes, the VPS enters a <strong>24-hour grace period</strong> (<code>status=expired</code>) during which the owner can still start/stop/restart it. After 24h, the VPS is automatically destroyed and deleted from the database.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{"expires_at": "2026-12-31 23:59"}</div>
                        <p>If <code>expires_at</code> is an empty string or omitted, the expiration is cleared.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"success": true, "expires_at": "2026-12-31 23:59"}</div>
                    </div>
                </div>
  <!-- Local Node API -->
                <div class="section-title fade-in">
                    <svg width="18" height="18"><use href="#icon-server"/></svg>
                    Local Node API
                    <span class="text-dim" style="font-size:11px;font-weight:400;">(direct LXD management, admin API key required)</span>
                </div>

                <div class="card fade-in" style="margin-bottom:16px;">
                    <p style="font-size:12px;color:var(--text-muted);line-height:1.6;">
                        These endpoints run on the panel itself and manage the local LXD host directly.
                        Authenticate with <code>X-API-Key</code> header using an admin's API key.
                    </p>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/local/api/health</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">LXD health check</span>
                    </div>
                    <div class="endpoint-body">
                        <div class="code-block">{
  "status": "ok",
  "LXD": "running"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/local/api/info</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Host system info</span>
                    </div>
                    <div class="endpoint-body">
                        <div class="code-block">{
  "cpu_percent": 12.5,
  "ram_used": 2.1,
  "ram_total": 8.0,
  "disk_used": 25.3,
  "disk_total": 80.0,
  "lxd_version": "24.0.7",
  "hostname": "panel-1",
  "platform": "Linux-5.15.0"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/local/api/containers</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">List all local containers</span>
                    </div>
                    <div class="endpoint-body">
                        <div class="code-block">{
  "containers": [
    {
      "id": "abc123...",
      "name": "vps-user-1234",
      "status": "running",
      "image": "ubuntu-22.04"
    }
  ]
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/create</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Create container</span>
                    </div>
                    <div class="endpoint-body">
                        <strong>Request:</strong>
                        <div class="code-block">{
  "name": "vps-user-1234",
  "image": "ubuntu-22.04",
  "ram": "2GB",
  "cpu": "1 vCPU"
}</div>
                        <strong>Available images:</strong>
                        <div class="code-block">ubuntu-22.04    # Ubuntu 22.04
ubuntu-24.04    # Ubuntu 24.04
ubuntu-26.04    # Ubuntu 26.04</div>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "status": "ok",
  "container_id": "abc123...",
  "name": "vps-user-1234"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/start</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Start container</span>
                    </div>
                    <div class="endpoint-body"><div class="code-block">{"status": "ok"}</div></div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/stop</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Stop container</span>
                    </div>
                    <div class="endpoint-body"><div class="code-block">{"status": "ok"}</div></div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/restart</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Restart container</span>
                    </div>
                    <div class="endpoint-body"><div class="code-block">{"status": "ok"}</div></div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/delete</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Delete container</span>
                    </div>
                    <div class="endpoint-body"><div class="code-block">{"status": "ok"}</div></div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/local/api/container/{id}/status</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Get container status</span>
                    </div>
                    <div class="endpoint-body">
                        <div class="code-block">{
  "state": "running",
  "id": "abc123...",
  "name": "vps-user-1234"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/local/api/container/{id}/stats</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Container resource stats</span>
                    </div>
                    <div class="endpoint-body">
                        <div class="code-block">{
  "cpu_percent": 3.2,
  "memory_used": 134217728,
  "memory_limit": 2147483648,
  "memory_percent": 6.25,
  "net_rx": 123456,
  "net_tx": 654321,
  "pids": 5
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/regen-ssh</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Regenerate SSH link</span>
                    </div>
                    <div class="endpoint-body">
                        <div class="code-block">{
  "status": "ok",
  "link": "https://sshx.io/s/abc123"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/exec</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Execute command</span>
                    </div>
                    <div class="endpoint-body">
                        <strong>Request:</strong>
                        <div class="code-block">{"command": "ls -la /"}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "output": "total 64\\ndrwxr-xr-x ...",
  "exit_code": 0
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/local/api/container/{id}/ip</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Get container IP</span>
                    </div>
                    <div class="endpoint-body">
                        <div class="code-block">{"ip": "10.132.115.x"}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/update</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Update container resources</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Updates RAM, CPU, and/or disk size for a container. Resources are applied via LXD config changes (RAM/CPU take effect immediately, disk on next start).</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{
  "ram": "4GB",
  "cpu": "2 vCPU",
  "disk": "40GB"
}</div>
                        <p>All fields are optional; only provided fields are updated.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>

                <div class="endpoint

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/socat/start</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Start IPv4 port forward</span>
                    </div>
                    <div class="endpoint-body">
                        <strong>Request:</strong>
                        <div class="code-block">{
  "container_ip": "10.132.115.x",
  "local_port": 22,
  "external_port": 30000
}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "status": "ok",
  "socat_pid": 12345
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/socat/stop</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Stop port forward</span>
                    </div>
                    <div class="endpoint-body">
                        <strong>Request:</strong>
                        <div class="code-block">{"socat_pid": 12345}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>

                

                
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/local/api/container/{id}/top</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">List running processes</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns running processes sorted by CPU usage.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "processes": [
    {"pid": "1", "user": "root", "cpu": "0.0", "mem": "0.1", "command": "/sbin/init"}
  ]
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/local/api/container/{id}/processes/kill</span>
                        <span class="auth-badge" style="margin-left:4px;">Admin API Key</span>
                        <span class="endpoint-desc">Kill a process</span>
                    </div>
                    <div class="endpoint-body">
                        <strong>Request:</strong>
                        <div class="code-block">{"pid": "1234"}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{"success": true}</div>
                    </div>
                </div>

                <!-- Node Agent API -->
                <div class="section-title fade-in">
                    <svg width="18" height="18"><use href="#icon-cpu"/></svg>
                    Node Agent API
                    <span class="text-dim" style="font-size:11px;font-weight:400;">(remote nodes only, panel calls these internally)</span>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/health</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Health check</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns node agent health status. Requires <code>X-API-Key</code> header.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "status": "ok",
  "LXD": "running"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/info</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Node system info</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns system info for the remote node.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "cpu_percent": 12.5,
  "ram_used": 2.1,
  "ram_total": 8.0,
  "disk_used": 25.3,
  "disk_total": 80.0,
  "lxd_version": "24.0.7",
  "hostname": "node-1",
  "platform": "Linux-5.15.0"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/containers</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">List all containers</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns list of all LXD instances on the node.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "containers": [
    {
      "id": "abc123...",
      "name": "vps-user-1234",
      "status": "running",
      "image": "ubuntu-22.04"
    }
  ]
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/create</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Create a new container</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Creates and starts a new LXD instance.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{
  "name": "vps-user-1234",
  "image": "ubuntu-22.04",
  "ram": "2GB",
  "cpu": "1 vCPU"
}</div>
                        <strong>Available images:</strong>
                        <div class="code-block">ubuntu-22.04    # Ubuntu 22.04
ubuntu-24.04    # Ubuntu 24.04

ubuntu-26.04    # Ubuntu 26.04</div>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "status": "ok",
  "container_id": "abc123...",
  "name": "vps-user-1234"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/start</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Start a container</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Starts a stopped container.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/stop</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Stop a container</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Stops a running container.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/restart</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Restart a container</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Restarts a container (stop + start).</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/delete</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Delete a container</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Stops and removes a container.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/container/{id}/status</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Get container status</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns the status and state of a container.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "state": "running",
  "id": "abc123...",
  "name": "vps-user-1234"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/container/{id}/stats</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Get container resource stats</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns real-time CPU, RAM, network, and PID stats.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "cpu_percent": 3.2,
  "memory_used": 134217728,
  "memory_limit": 2147483648,
  "memory_percent": 6.25,
  "network_rx": 123456,
  "network_tx": 654321,
  "pids": 5
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/regen-ssh</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Regenerate SSH session</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Restarts the container and returns a new sshx connection link.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "status": "ok",
  "link": "https://sshx.io/s/abc123"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/exec</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Execute a command</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Runs a command inside the container.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{
  "command": "ls -la /"
}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "output": "total 64\\ndrwxr-xr-x ...",
  "exit_code": 0
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/container/{id}/ip</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Get container IP address</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns the container's internal IP address.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "ip": "10.132.115.x"
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/socat/start</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Start IPv4 port forward</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Starts a socat process to forward traffic from a port to a container.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{
  "container_ip": "10.132.115.x",
  "local_port": 22,
  "external_port": 30000
}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "status": "ok",
  "socat_pid": 12345
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/socat/stop</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Stop IPv4 port forward</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Kills the socat process for a port forward.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{
  "socat_pid": 12345
}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>


                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/container/{id}/top</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">List running processes</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns running processes sorted by CPU usage.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{
  "processes": [
    {"pid": "1", "user": "root", "cpu": "0.0", "mem": "0.1", "command": "/sbin/init"}
  ]
}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/backup</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Create container snapshot</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Creates a snapshot/backup of the container.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{"name": "backup-1719400000"}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{"success": true, "image_tag": "backup-1719400000", "size_mb": 0}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/restore</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Restore from snapshot</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Restores container from a named snapshot.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{"snapshot": "backup-1719400000"}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{"success": true}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-get">GET</span>
                        <span class="endpoint-path">/api/container/{id}/snapshots</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">List all snapshots</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Returns all available snapshots for a container.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"snapshots": [{"name": "backup-1719400000"}]}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-delete">DELETE</span>
                        <span class="endpoint-path">/api/container/{id}/snapshot/{name}</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Delete a snapshot</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Deletes a named snapshot from the container.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"success": true}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/serveo/start</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Start SSH tunnel</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Starts a serveo.net SSH tunnel to expose a container port publicly.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{"container_id": "vps-user-1234", "local_port": 8080}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok", "serveo_url": "https://abc.serveo.net", "port": 8080}</div>
                    </div>
                </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/serveo/stop</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Stop SSH tunnel</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Stops the serveo.net SSH tunnel for a container port.</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{"container_id": "vps-user-1234", "local_port": 8080}</div>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
            </div>

                <div class="endpoint fade-in" onclick="this.querySelector('.endpoint-body').classList.toggle('open')">
                    <div class="endpoint-header">
                        <span class="method method-post">POST</span>
                        <span class="endpoint-path">/api/container/{id}/update</span>
                        <span class="tag tag-public" style="margin-left:4px;">API Key</span>
                        <span class="endpoint-desc">Update container resources</span>
                    </div>
                    <div class="endpoint-body">
                        <p>Updates RAM, CPU, and/or disk size for a container. Resources are applied via LXD config changes (RAM/CPU take effect immediately, disk on next start).</p>
                        <strong>Request Body:</strong>
                        <div class="code-block">{
  "ram": "4GB",
  "cpu": "2 vCPU",
  "disk": "40GB"
}</div>
                        <p>All fields are optional; only provided fields are updated.</p>
                        <strong>Response:</strong>
                        <div class="code-block">{"status": "ok"}</div>
                    </div>
                </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'usage.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>User Usage Report — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        .page-advanced{background:var(--bg);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative}
        .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:12px 12px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}
        .stat-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:16px;transition:transform .2s,box-shadow .2s}
        .stat-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.25)}
        .stat-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
        .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .stat-icon.blue{background:rgba(96,165,250,.12);color:#60a5fa}
        .stat-icon.green{background:rgba(52,211,153,.12);color:#34d399}
        .stat-icon.yellow{background:rgba(251,191,36,.12);color:#fbbf24}
        .stat-icon.red{background:rgba(248,113,113,.12);color:#f87171}
        .stat-info{display:flex;flex-direction:column}
        .stat-label{font-size:12px;color:var(--text-dim)}
        .stat-value{font-size:20px;font-weight:700;color:var(--text)}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
        table{width:100%;border-collapse:collapse}
        thead{background:var(--bg-input)}
        th{padding:10px 14px;font-size:12px;font-weight:600;color:var(--text-muted);text-align:left;border-bottom:1px solid var(--border)}
        td{padding:10px 14px;font-size:13px;color:var(--text);border-bottom:1px solid var(--border)}
        tr:last-child td{border-bottom:none}
        tr:hover td{background:rgba(255,255,255,.02)}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .alert{padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:16px;border:1px solid}
        .alert-success{background:rgba(52,211,153,.08);border-color:rgba(52,211,153,.2);color:var(--green)}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .cpu-col,.ram-col,.disk-col,.joined-col{display:table-cell}
        @media(max-width:768px){
            .stat-cards{grid-template-columns:1fr 1fr;gap:6px}
            .stat-card{padding:8px;gap:6px}
            .stat-icon{width:28px;height:28px;border-radius:6px}
            .stat-icon svg{width:14px;height:14px}
            .stat-value{font-size:13px}
            .stat-label{font-size:9px}
            .card{padding:10px}
            .card-title{font-size:12px;margin-bottom:6px}
            .page-header h1{font-size:15px}
            .page-header-sub{font-size:10px}
            .breadcrumbs{font-size:10px;margin-bottom:8px}
            table{font-size:11px}
            th{padding:5px 6px;font-size:9px}
            td{padding:5px 6px}
            .status{padding:2px 6px;font-size:9px}
            .cpu-col,.disk-col,.joined-col{display:none}
            .user-detail{display:block;font-size:9px;color:var(--text-dim);margin-top:1px}
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('usage', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Usage Report', 'usage') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin">Admin</a>
                    <span class="sep">></span>
                    <span class="current">Usage Report</span>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="page-header fade-in">
                    <div>
                        <h1>User Usage Report</h1>
                        <p class="page-header-sub">Resource allocation per user, sorted by most RAM used.</p>
                    </div>
                </div>

                <div class="stat-cards fade-in">
                    <div class="stat-card">
                        <div class="stat-icon blue">
                            <svg width="20" height="20"><use href="#icon-users"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total Users</div>
                            <div class="stat-value">{{ usage|length }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <svg width="20" height="20"><use href="#icon-server"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total VPS</div>
                            <div class="stat-value">{{ totals['total_vps'] }}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon yellow">
                            <svg width="20" height="20"><use href="#icon-cpu"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total RAM</div>
                            <div class="stat-value">{{ totals['total_ram']|int }}GB</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon red">
                            <svg width="20" height="20"><use href="#icon-hard-drive"/></svg>
                        </div>
                        <div class="stat-info">
                            <div class="stat-label">Total Disk</div>
                            <div class="stat-value">{{ totals['total_disk']|int }}GB</div>
                        </div>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-users"/></svg>
                        Per-User Breakdown
                    </div>
                    {% if usage %}
                    <div class="table-wrap" style="margin-top:12px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>VPS</th>
                                    <th>Running</th>
                                    <th class="cpu-col">Live CPU</th>
                                    <th class="ram-col">Live RAM</th>
                                    <th>Alloc RAM</th>
                                    <th class="cpu-col">Alloc CPU</th>
                                    <th class="disk-col">Alloc Disk</th>
                                    <th class="joined-col">Joined</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for u in usage %}
                                {% set ls = live_stats.get(u['id'], {}) %}
                                <tr>
                                    <td>
                                        <div style="font-weight:500;">{{ u['username'] }}</div>
                                        <span class="user-detail">{{ u['user_created'][:10] if u['user_created'] else '—' }} · {{ u['total_disk']|int }}GB disk · {{ u['total_cpu'] }} cores</span>
                                    </td>
                                    <td><span class="status status-running">{{ u['vps_count'] }}</span></td>
                                    <td>{{ u['running_count'] or 0 }}</td>
                                    <td class="cpu-col">
                                        {% if ls.get('live_cpu', 0) > 0 %}
                                        <span style="color:{{ 'var(--red)' if ls['live_cpu'] > 80 else 'var(--yellow)' if ls['live_cpu'] > 50 else 'var(--green)' }};font-weight:600;">{{ ls['live_cpu'] }}%</span>
                                        {% else %}
                                        <span class="text-dim">—</span>
                                        {% endif %}
                                    </td>
                                    <td class="ram-col">
                                        {% if ls.get('live_ram_mb', 0) > 0 %}
                                        <span style="font-weight:500;">{{ (ls['live_ram_mb'] / 1024)|round(1) }}GB</span>
                                        {% else %}
                                        <span class="text-dim">—</span>
                                        {% endif %}
                                    </td>
                                    <td><strong>{{ u['total_ram']|int }}GB</strong></td>
                                    <td class="cpu-col">{{ u['total_cpu'] }} cores</td>
                                    <td class="disk-col">{{ u['total_disk']|int }}GB</td>
                                    <td class="joined-col text-dim" style="font-size:12px;">{{ u['user_created'][:10] if u['user_created'] else '—' }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="empty-state" style="padding:40px 20px;text-align:center;color:var(--text-dim);">
                        <h3>No Data</h3>
                        <p>No users or VPS found.</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'expiring_vps.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Expiring VPS — Omega Panel</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <style>
        .page-advanced{background:var(--bg);min-height:100vh}
        .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative}
        .card-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
        table{width:100%;border-collapse:collapse}
        thead{background:var(--bg-input)}
        th{padding:10px 14px;font-size:12px;font-weight:600;color:var(--text-muted);text-align:left;border-bottom:1px solid var(--border)}
        td{padding:10px 14px;font-size:13px;color:var(--text);border-bottom:1px solid var(--border)}
        tr:last-child td{border-bottom:none}
        .status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500}
        .status-running{background:rgba(52,211,153,.12);color:var(--green)}
        .status-stopped{background:rgba(248,113,113,.12);color:var(--red)}
        .status-expired{background:rgba(251,191,36,.12);color:var(--yellow)}
        .status-creating{background:rgba(96,165,250,.12);color:#60a5fa}
        .empty-state{text-align:center;padding:40px 20px;color:var(--text-dim)}
        .empty-icon{width:64px;height:64px;border-radius:12px;background:var(--bg-input);display:flex;align-items:center;justify-content:center;margin:0 auto 12px;color:var(--text-muted)}
        .breadcrumbs{font-size:12px;color:var(--text-dim);margin-bottom:16px}
        .breadcrumbs a{color:var(--text-muted);text-decoration:none}
        .breadcrumbs .sep{margin:0 6px}
        .breadcrumbs .current{color:var(--text)}
        .page-header h1{font-size:22px;font-weight:700;color:var(--text)}
        .page-header-sub{font-size:13px;color:var(--text-dim);margin-top:4px}
        .alert{padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:16px;border:1px solid}
        .alert-success{background:rgba(52,211,153,.08);border-color:rgba(52,211,153,.2);color:var(--green)}
        .alert-error{background:rgba(248,113,113,.08);border-color:rgba(248,113,113,.2);color:var(--red)}
        .btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;border:none;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s}
        .btn-red{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.2)}
        .btn-red:hover{background:rgba(248,113,113,.25)}
        .btn-ghost{background:rgba(255,255,255,.04);color:var(--text-muted);border:1px solid var(--border)}
        .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
        .btn-sm{padding:6px 10px;font-size:12px}
        .text-dim{color:var(--text-dim)}
        .fade-in{animation:fadeIn .4s ease}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        .vps-os,.vps-specs,.vps-expires{display:table-cell}
        @media(max-width:768px){
            .card{padding:10px}
            .card-title{font-size:12px;margin-bottom:8px}
            .page-header h1{font-size:15px}
            .page-header-sub{font-size:10px}
            table{font-size:11px}
            th{padding:5px 6px;font-size:9px}
            td{padding:5px 6px}
            .status{padding:2px 6px;font-size:9px}
            .vps-os,.vps-specs,.vps-expires{display:none}
            .vps-user{font-size:10px}
            .vps-name{font-size:10px;font-weight:500}
            .vps-days{font-size:9px}
            .vps-detail-mobile{display:block;font-size:9px;color:var(--text-dim);margin-top:1px}
            .btn-sm{padding:3px 6px;font-size:9px}
        }
    </style>
</head>
<body class="page-advanced">
    {% include 'icons.html' %}
    {% from 'components.html' import sidebar, topbar, overlay %}

    <div class="app-layout">
        {{ sidebar('expiring', settings, custom_icon) }}

        <div class="main-content">
            {{ topbar('Expiring VPS', 'expiring') }}

            <div class="page" style="padding:24px;">
                <div class="breadcrumbs">
                    <a href="/dashboard">Dashboard</a>
                    <span class="sep">></span>
                    <a href="/admin">Admin</a>
                    <span class="sep">></span>
                    <span class="current">Expiring VPS</span>
                </div>

                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="page-header fade-in">
                    <div>
                        <h1>Expiring VPS</h1>
                        <p class="page-header-sub">VPS instances sorted by expiration date (soonest first).</p>
                    </div>
                </div>

                <div class="card fade-in">
                    <div class="card-title">
                        <svg width="18" height="18"><use href="#icon-clock"/></svg>
                        Expiring / Expired Instances
                    </div>
                    {% if vps_list %}
                    <div class="table-wrap" style="margin-top: 12px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>Name</th>
                                    <th class="vps-os">OS</th>
                                    <th class="vps-specs">Specs</th>
                                    <th class="vps-expires">Expires</th>
                                    <th>Days Left</th>
                                    <th>Status</th>
                                    <th style="text-align: right;">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for vps in vps_list %}
                                <tr>
                                    <td class="vps-user">{{ vps['username'] }}</td>
                                    <td>
                                        <span class="vps-name">{{ vps['container_name'] }}</span>
                                        <span class="vps-detail-mobile">{{ vps['os_type'] }} · {{ vps['ram'] }}/{{ vps['cpu'] }}</span>
                                        <span class="vps-detail-mobile">Exp: {{ vps['expires_at'][:16] if vps['expires_at'] else '—' }}</span>
                                    </td>
                                    <td class="vps-os">{{ vps['os_type'] }}</td>
                                    <td class="vps-specs">{{ vps['ram'] }} / {{ vps['cpu'] }}</td>
                                    <td class="vps-expires text-dim">{{ vps['expires_at'][:16] if vps['expires_at'] else '—' }}</td>
                                    <td>
                                        {% if vps['days_left'] is not none %}
                                            {% if vps['days_left'] <= 0 %}
                                                <span class="vps-days" style="color:var(--red);font-weight:600;">Expired</span>
                                            {% elif vps['days_left'] <= 1 %}
                                                <span class="vps-days" style="color:var(--red);font-weight:600;">{{ vps['days_left'] }}d</span>
                                            {% elif vps['days_left'] <= 7 %}
                                                <span class="vps-days" style="color:var(--yellow);font-weight:600;">{{ vps['days_left'] }}d</span>
                                            {% else %}
                                                <span class="vps-days" style="color:var(--green);">{{ vps['days_left'] }}d</span>
                                            {% endif %}
                                        {% else %}
                                            —
                                        {% endif %}
                                    </td>
                                    <td><span class="status status-{{ vps['status'] }}">{{ vps['status'] }}</span></td>
                                    <td style="text-align: right;">
                                        <a href="/admin/vps/{{ vps['id'] }}" class="btn btn-ghost btn-sm" style="text-decoration:none;">Details</a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="empty-state">
                        <div class="empty-icon">
                            <svg width="28" height="28"><use href="#icon-clock"/></svg>
                        </div>
                        <h3>No Expiring VPS</h3>
                        <p>No VPS with expiration dates set.</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    {{ overlay() }}
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
""", 'terminal.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ vps['container_name'] }} &mdash; Terminal</title>
    <link rel="icon" href="{{ custom_icon if custom_icon else 'https://files.catbox.moe/wni5n4.png' }}">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; background: #000; overflow: hidden; }
        #terminal-container { height: 100vh; padding: 8px; }
    </style>
</head>
<body>
    <div id="terminal-container"></div>
    <script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.min.js"></script>
    <script>
        (function() {
            var term = new Terminal({ cursorBlink: true, fontSize: 14, fontFamily: 'Menlo, Monaco, "Courier New", monospace', theme: { background: '#000', foreground: '#f0f0f0' } });
            var fitAddon = new FitAddon.FitAddon();
            term.loadAddon(fitAddon);
            term.open(document.getElementById('terminal-container'));
            fitAddon.fit();
            var sessionId = null;
            function sendResize() {
                if (!sessionId) return;
                var dims = fitAddon.proposeDimensions();
                if (!dims) return;
                fetch('/api/vps/{{ vps['id'] }}/terminal/resize?session=' + sessionId + '&cols=' + dims.cols + '&rows=' + dims.rows, { method: 'POST' });
            }
            function createSession() {
                var dims = fitAddon.proposeDimensions();
                var cols = dims ? dims.cols : 80;
                var rows = dims ? dims.rows : 24;
                fetch('/api/vps/{{ vps['id'] }}/terminal/session?cols=' + cols + '&rows=' + rows, { method: 'POST' })
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        sessionId = data.session_id;
                        connectStream();
                        setTimeout(function() { sendResize(); }, 100);
                    })
                    .catch(function(err) {
                        term.writeln('Failed to create terminal session');
                    });
            }
            function connectStream() {
                var evtSource = new EventSource('/api/vps/{{ vps['id'] }}/terminal/stream?session=' + sessionId);
                evtSource.onmessage = function(event) {
                    if (event.data === '__TERMINAL_CLOSED__') {
                        evtSource.close();
                        return;
                    }
                    try {
                        var bytes = Uint8Array.from(atob(event.data), function(c) { return c.charCodeAt(0); });
                        term.write(bytes);
                    } catch(e) {
                        term.write(event.data);
                    }
                };
                evtSource.onerror = function() { evtSource.close(); };
            }
            term.onData(function(data) {
                if (sessionId) {
                    fetch('/api/vps/{{ vps['id'] }}/terminal/input?session=' + sessionId, {
                        method: 'POST',
                        body: data
                    });
                }
            });
            function onResize() {
                fitAddon.fit();
                sendResize();
            }
            window.addEventListener('resize', onResize);
            createSession();
        })();
    </script>
</body>
</html>"""}}
EMBEDDED_CSS = """@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg: #09090b;
    --bg-elevated: #18181b;
    --bg-card: #1c1c21;
    --bg-hover: #27272a;
    --bg-input: #0f0f12;
    --border: #27272a;
    --border-focus: #3f3f46;
    --text: #fafafa;
    --text-muted: #a1a1aa;
    --text-dim: #71717a;
    --accent: #ffffff;
    --accent-hover: #e4e4e7;
    --accent-glow: rgba(255, 255, 255, 0.15);
    --green: #22c55e;
    --green-bg: rgba(34, 197, 94, 0.12);
    --red: #ef4444;
    --red-bg: rgba(239, 68, 68, 0.12);
    --yellow: #eab308;
    --yellow-bg: rgba(234, 179, 8, 0.12);
    --orange: #f97316;
    --orange-bg: rgba(249, 115, 22, 0.12);
    --radius: 8px;
    --radius-lg: 12px;
    --sidebar-w: 220px;
}

html { scroll-behavior: smooth; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
}

/* ===== LAYOUT ===== */
.app-layout {
    display: flex;
    min-height: 100vh;
}

/* ===== SIDEBAR ===== */
.sidebar {
    width: var(--sidebar-w);
    background: var(--bg-elevated);
    border-right: 1px solid var(--border);
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    z-index: 50;
    overflow-y: auto;
}

.sidebar-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px 18px;
    border-bottom: 1px solid var(--border);
    text-decoration: none;
    color: var(--text);
    font-size: 15px;
    font-weight: 700;
}

.sidebar-logo svg {
    width: 24px;
    height: 24px;
    color: var(--text);
}

.sidebar-section {
    padding: 16px 0 4px;
}

.sidebar-section-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 0 18px;
    margin-bottom: 4px;
}

.sidebar-link {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-muted);
    text-decoration: none;
    transition: all 0.12s ease;
    position: relative;
}

.sidebar-link:hover {
    color: var(--text);
    background: var(--bg-hover);
}

.sidebar-link.active {
    color: #09090b;
    background: var(--accent);
    border-radius: 0;
}

.sidebar-link.active svg {
    color: #09090b;
}

.sidebar-link svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
    color: var(--text-dim);
}

.sidebar-link.active ~ .sidebar-link svg,
.sidebar-link:hover svg {
    color: inherit;
}

.sidebar-badge {
    margin-left: auto;
    background: var(--red);
    color: white;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 10px;
    min-width: 18px;
    text-align: center;
}

.sidebar-footer {
    margin-top: auto;
    padding: 12px 18px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    color: var(--text-dim);
}

/* ===== MAIN ===== */
.main-content {
    flex: 1;
    margin-left: var(--sidebar-w);
    display: flex;
    flex-direction: column;
    min-height: 100vh;
}

/* ===== TOPBAR ===== */
.topbar {
    height: 52px;
    background: rgba(9, 9, 11, 0.85);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    position: sticky;
    top: 0;
    z-index: 40;
}

.topbar-title {
    font-size: 14px;
    font-weight: 600;
}

.topbar-right {
    display: flex;
    align-items: center;
    gap: 12px;
}

.topbar-bell {
    position: relative;
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.topbar-bell:hover {
    background: var(--bg-hover);
    color: var(--text);
}

.topbar-bell svg { width: 18px; height: 18px; }

.topbar-bell .badge {
    position: absolute;
    top: 0;
    right: 0;
    width: 8px;
    height: 8px;
    background: var(--red);
    border-radius: 50%;
    border: 2px solid var(--bg);
}

.topbar-user {
    display: flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    color: var(--text);
}

.topbar-avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 600;
    color: #09090b;
}

.topbar-user-info {
    line-height: 1.3;
}

.topbar-user-name {
    font-size: 13px;
    font-weight: 500;
    display: block;
}

.topbar-user-role {
    font-size: 11px;
    color: var(--text-dim);
    display: block;
}

/* ===== PAGE ===== */
.page {
    flex: 1;
    padding: 24px;
    position: relative;
}

.page-bg {
    position: fixed;
    top: 0;
    left: var(--sidebar-w);
    right: 0;
    bottom: 0;
    background-size: cover;
    background-position: center;
    opacity: 0.12;
    pointer-events: none;
    z-index: 0;
}

.page > * { position: relative; z-index: 1; }

/* ===== BREADCRUMBS ===== */
.breadcrumbs {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 8px;
}

.breadcrumbs a {
    color: var(--text-dim);
    text-decoration: none;
}

.breadcrumbs a:hover { color: var(--text-muted); }
.breadcrumbs .sep { color: var(--text-dim); }
.breadcrumbs .current { color: var(--text-muted); }

/* ===== PAGE HEADER ===== */
.page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 24px;
}

.page-header h1 {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.5px;
}

.page-header-sub {
    font-size: 13px;
    color: var(--text-dim);
    margin-top: 2px;
}

/* ===== STAT CARDS ===== */
.stat-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 20px;
}

.stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 14px;
}

.stat-icon {
    width: 42px;
    height: 42px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.stat-icon svg { width: 20px; height: 20px; }

.stat-icon.blue { background: rgba(255, 255, 255, 0.08); color: var(--text); }
.stat-icon.green { background: var(--green-bg); color: var(--green); }
.stat-icon.yellow { background: var(--yellow-bg); color: var(--yellow); }
.stat-icon.red { background: var(--red-bg); color: var(--red); }
.stat-icon.orange { background: var(--orange-bg); color: var(--orange); }

.stat-info .stat-label {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.stat-info .stat-value {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1.2;
}

/* ===== SEARCH BAR ===== */
.search-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
}

.search-input {
    flex: 1;
    padding: 9px 14px;
    font-size: 13px;
    font-family: inherit;
    color: var(--text);
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    outline: none;
    transition: border-color 0.15s;
}

.search-input::placeholder { color: var(--text-dim); }
.search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(255,255,255,0.1); }

.search-select {
    padding: 9px 32px 9px 12px;
    font-size: 13px;
    font-family: inherit;
    color: var(--text-muted);
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    outline: none;
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%2371717a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
}

.search-select:focus { border-color: var(--accent); }

/* ===== BUTTONS ===== */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    font-family: inherit;
    border: none;
    border-radius: var(--radius);
    cursor: pointer;
    transition: all 0.15s ease;
    text-decoration: none;
    white-space: nowrap;
    line-height: 1.4;
}

.btn svg { flex-shrink: 0; }

.btn-primary { background: var(--accent); color: #09090b; }
.btn-primary:hover { background: var(--accent-hover); box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.3), 0 2px 8px rgba(255, 255, 255, 0.25); }
body.light .btn-primary { color: #ffffff; }

.btn-green { background: var(--green); color: white; }
.btn-green:hover { background: #16a34a; }

.btn-red { background: var(--red); color: white; }
.btn-red:hover { background: #dc2626; }

.btn-yellow { background: var(--yellow); color: #000; }
.btn-yellow:hover { background: #ca8a04; }

.btn-ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
.btn-ghost:hover { background: var(--bg-hover); color: var(--text); border-color: var(--border-focus); }

.btn-sm { padding: 5px 10px; font-size: 12px; border-radius: 6px; }
.btn-lg { padding: 10px 20px; font-size: 14px; }

/* ===== CARDS ===== */
.card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 20px;
}

.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
}

.card-title {
    font-size: 14px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
}

.card-title svg { width: 18px; height: 18px; color: var(--text); }

/* ===== FORMS ===== */
.form-group { margin-bottom: 16px; }

.form-group label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-muted);
    margin-bottom: 6px;
}

.form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}

.form-control {
    width: 100%;
    padding: 9px 12px;
    font-size: 14px;
    font-family: inherit;
    color: var(--text);
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    outline: none;
    transition: all 0.15s ease;
}

.form-control::placeholder { color: var(--text-dim); }
.form-control:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(255,255,255,0.08); }

select.form-control {
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%2371717a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    padding-right: 36px;
}

.checkbox-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-muted);
}

.checkbox-row input[type="checkbox"] {
    width: 16px;
    height: 16px;
    accent-color: var(--accent);
}

/* ===== ALERTS ===== */
.alert {
    padding: 10px 14px;
    border-radius: var(--radius);
    font-size: 13px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.alert-success { background: var(--green-bg); border: 1px solid rgba(34, 197, 94, 0.2); color: var(--green); }
.alert-error { background: var(--red-bg); border: 1px solid rgba(239, 68, 68, 0.2); color: var(--red); }

/* ===== TABLE ===== */
.table-wrap {
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
}

table { width: 100%; border-collapse: collapse; font-size: 13px; }

thead { background: var(--bg-elevated); }

th {
    text-align: left;
    padding: 10px 14px;
    font-weight: 500;
    color: var(--text-dim);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid var(--border);
}

td { padding: 10px 14px; color: var(--text-muted); border-bottom: 1px solid var(--border); }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,0.02); }

/* ===== STATUS ===== */
.status {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 500;
    padding: 3px 8px;
    border-radius: 100px;
}

.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
}

.status-running { background: var(--green-bg); color: var(--green); border: 1px solid rgba(34, 197, 94, 0.2); }
.status-running .status-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
.status-stopped { background: var(--red-bg); color: var(--red); border: 1px solid rgba(239, 68, 68, 0.2); }
.status-stopped .status-dot { background: var(--red); }
.status-creating { background: var(--yellow-bg); color: var(--yellow); border: 1px solid rgba(234, 179, 8, 0.2); }
.status-creating .status-dot { background: var(--yellow); animation: pulse 1.5s ease infinite; }
.status-online { background: var(--green-bg); color: var(--green); border: 1px solid rgba(34, 197, 94, 0.2); }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

/* ===== MODAL ===== */
.modal-bg {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    backdrop-filter: blur(4px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 200;
    padding: 20px;
}

.modal-bg.active { display: flex; }

.modal {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    width: 100%;
    max-width: 420px;
    padding: 24px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.5);
}

.modal-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
}

.modal-top h2 { font-size: 15px; font-weight: 600; }

.modal-x {
    background: none;
    border: none;
    color: var(--text-dim);
    font-size: 18px;
    cursor: pointer;
    padding: 4px;
    line-height: 1;
    border-radius: 4px;
}

.modal-x:hover { color: var(--text-muted); background: var(--bg-hover); }

/* ===== AUTH ===== */
.auth-page {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 20px;
}

.auth-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 32px;
    width: 100%;
    max-width: 380px;
}

.auth-card h2 { font-size: 18px; font-weight: 700; margin-bottom: 4px; }

.auth-sub {
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 24px;
}

.auth-footer {
    text-align: center;
    font-size: 13px;
    color: var(--text-dim);
    margin-top: 16px;
}

.auth-footer a { color: var(--text); text-decoration: none; font-weight: 500; }
.auth-footer a:hover { text-decoration: underline; }

/* ===== EMPTY STATE ===== */
.empty-state {
    text-align: center;
    padding: 60px 20px;
}

.empty-icon {
    width: 64px;
    height: 64px;
    margin: 0 auto 16px;
    background: var(--bg-hover);
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-dim);
}

.empty-icon svg { width: 28px; height: 28px; }

.empty-state h3 {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 6px;
}

.empty-state p {
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 20px;
}

/* ===== INFO LIST ===== */
.info-list { display: flex; flex-direction: column; }

.info-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
}

.info-item:last-child { border-bottom: none; }
.info-label { color: var(--text-dim); }
.info-value { color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 12px; }

/* ===== VPS SPEC BAR ===== */
.spec-bars { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }

.spec-bar-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
}

.spec-bar-label { color: var(--text-dim); font-weight: 500; }
.spec-bar-value { color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }

.spec-bar-track {
    height: 4px;
    background: var(--bg);
    border-radius: 2px;
    margin-top: 4px;
    overflow: hidden;
}

.spec-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
}

.spec-bar-fill.green { background: var(--green); }
.spec-bar-fill.blue { background: var(--text); }
.spec-bar-fill.yellow { background: var(--yellow); }
.spec-bar-fill.red { background: var(--red); }

/* ===== THEME TOGGLE ===== */
.theme-toggle {
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    width: 32px;
    height: 32px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    color: var(--text-muted);
    transition: all 0.15s ease;
    flex-shrink: 0;
    padding: 0;
}

.theme-toggle:hover { background: var(--bg-hover); color: var(--text); border-color: var(--border-focus); }
.theme-toggle svg { display: block; }

/* ===== LIGHT THEME ===== */
body.light {
    --bg: #ffffff;
    --bg-elevated: #f9fafb;
    --bg-card: #ffffff;
    --bg-hover: #f3f4f6;
    --bg-input: #f9fafb;
    --border: #e5e7eb;
    --border-focus: #d1d5db;
    --text: #111827;
    --text-muted: #4b5563;
    --text-dim: #9ca3af;
    --accent: #18181b;
    --accent-hover: #27272a;
    --accent-glow: rgba(24, 24, 27, 0.1);
    --green: #16a34a;
    --green-bg: rgba(22, 163, 74, 0.08);
    --red: #dc2626;
    --red-bg: rgba(220, 38, 38, 0.06);
    --yellow: #ca8a04;
    --yellow-bg: rgba(202, 138, 4, 0.08);
    --orange: #ea580c;
    --orange-bg: rgba(234, 88, 12, 0.08);
}

body.light .sidebar { background: #1c1c21; border-right-color: #27272a; }
body.light .sidebar-link { color: #a1a1aa; }
body.light .sidebar-link:hover { color: #fafafa; background: #27272a; }
body.light .sidebar-link.active { color: #09090b; background: #ffffff; }
body.light .sidebar-link.active svg { color: #09090b; }
body.light .sidebar-link svg { color: #71717a; }
body.light .sidebar-section-label { color: #71717a; }
body.light .sidebar-logo { color: #fafafa; }
body.light .topbar { background: rgba(255,255,255,0.85); }
body.light .page-bg { opacity: 0.06; }
body.light .spec-bar-track { background: #f3f4f6; }
body.light .status-running .status-dot { box-shadow: 0 0 6px var(--green); }

/* ===== HAMBURGER ===== */
.hamburger {
    display: none;
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    border-radius: 6px;
    align-items: center;
    justify-content: center;
}
.hamburger:hover { background: var(--bg-hover); color: var(--text); }

/* ===== SIDEBAR OVERLAY ===== */
.sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 45;
}
.sidebar-overlay.active { display: block; }

/* ===== TOPBAR LEFT ===== */
.topbar-left {
    display: flex;
    align-items: center;
    gap: 10px;
}

/* ===== RESPONSIVE ===== */
@media (max-width: 1024px) {
    .stat-cards { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
    .sidebar {
        transform: translateX(-100%);
        transition: transform 0.2s ease;
    }
    .sidebar.open {
        transform: translateX(0);
    }
    .main-content { margin-left: 0; }
    .page-bg { left: 0; }
    .stat-cards { grid-template-columns: 1fr; }
    .form-row { grid-template-columns: 1fr; }
    .topbar-user-info { display: none; }
    .topbar-left { display: flex; align-items: center; gap: 10px; }
    .hamburger { display: flex !important; }
    .vps-grid { grid-template-columns: 1fr; }
    .page { padding: 16px; }
    .page-header { flex-direction: column; gap: 12px; }
    .topbar { padding: 0 12px; }
    .info-item { flex-direction: column; align-items: flex-start; gap: 4px; }
    .detail-grid { grid-template-columns: 1fr !important; }
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-focus); }

/* ===== ANIMATION ===== */
.fade-in { animation: fadeIn 0.2s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ===== MISC ===== */
.mono { font-family: 'JetBrains Mono', monospace; }
.text-dim { color: var(--text-dim); }
.text-muted { color: var(--text-muted); }
.text-green { color: var(--green); }
.text-red { color: var(--red); }
.mb-2 { margin-bottom: 8px; }
.mb-3 { margin-bottom: 12px; }
.mb-4 { margin-bottom: 16px; }
.mt-3 { margin-top: 12px; }

/* ===== WELCOME BANNER ===== */
.welcome-banner {
    background: linear-gradient(135deg, var(--bg-card), var(--bg-elevated));
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 24px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
}

.welcome-banner h1 {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 4px;
}

.welcome-banner p {
    font-size: 13px;
    color: var(--text-dim);
}

/* ===== STAT SUB ===== */
.stat-sub {
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 2px;
}

/* ===== RESOURCE BARS ===== */
.resource-bars {
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.resource-bar-item {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.resource-bar-header {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--text-muted);
    font-weight: 500;
}

.resource-bar-track {
    height: 6px;
    background: var(--bg);
    border-radius: 3px;
    overflow: hidden;
}

.resource-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
}

.resource-bar-fill.green { background: var(--green); }
.resource-bar-fill.blue { background: var(--text); }
.resource-bar-fill.yellow { background: var(--yellow); }
.resource-bar-fill.red { background: var(--red); }

/* ===== CHART LEGEND ===== */
.chart-legend {
    display: flex;
    gap: 16px;
    justify-content: center;
    margin-top: 16px;
    font-size: 12px;
    color: var(--text-dim);
}

.chart-legend .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 4px;
    vertical-align: middle;
}

.chart-legend .dot.green { background: var(--green); }
.chart-legend .dot.gray { background: var(--text-dim); }
.chart-legend .dot.red { background: var(--red); }

/* ===== PROFILE AVATAR ===== */
.profile-avatar-lg {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    background: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    font-weight: 700;
    color: #09090b;
    margin: 0 auto;
}

/* ===== LOG OUTPUT ===== */
.log-output {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px;
    max-height: 400px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    margin-top: 12px;
}

.log-line {
    display: flex;
    gap: 10px;
    padding: 3px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    line-height: 1.6;
}

.log-line:hover {
    background: rgba(255,255,255,0.02);
}

.log-time {
    color: var(--text-dim);
    white-space: nowrap;
}

.log-level {
    font-weight: 600;
    white-space: nowrap;
    min-width: 50px;
}

.log-level.level-info { color: var(--text); }
.log-level.level-warning { color: var(--yellow); }
.log-level.level-error { color: var(--red); }

.log-source {
    color: var(--text-dim);
}

.log-message {
    color: var(--text-muted);
    word-break: break-word;
}

/* ===== VPS CARD GRID ===== */
.vps-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 16px;
    transition: border-color 0.15s;
}

.vps-card:hover {
    border-color: var(--border-focus);
}

.vps-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}

.vps-name {
    font-size: 14px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
}

.vps-specs {
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
}

.vps-spec {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.vps-spec-label {
    font-size: 10px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.vps-spec-value {
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 500;
}

.vps-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
}

.ssh-box {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 8px 12px;
    margin-bottom: 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
    overflow-x: auto;
    white-space: nowrap;
}

.ssh-box code {
    color: inherit;
}

.vps-actions {
    display: flex;
    gap: 8px;
}

/* ===== ADVANCED PAGE STYLES ===== */
.page-advanced {
    position: relative;
}

.page-advanced::before {
    content: '';
    position: fixed;
    top: 0; left: var(--sidebar-w); right: 0; bottom: 0;
    background: radial-gradient(ellipse 60% 40% at 50% 0%, rgba(255,255,255,.03) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}

.page-advanced > * { position: relative; z-index: 1; }

/* Gradient border cards */
.card-glow {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 20px;
    overflow: hidden;
}

.card-glow::before {
    content: '';
    position: absolute;
    top: -1px; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.15), transparent);
    opacity: 0;
    transition: opacity .3s;
}

.card-glow:hover::before { opacity: 1; }

/* Stat card glow */
.stat-card {
    transition: all .2s ease;
}

.stat-card:hover {
    border-color: rgba(255,255,255,.1);
    transform: translateY(-1px);
}

/* Welcome banner advanced */
.welcome-banner {
    position: relative;
    overflow: hidden;
}

.welcome-banner::before {
    content: '';
    position: absolute;
    top: -50%; right: -20%;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(255,255,255,.03) 0%, transparent 70%);
    pointer-events: none;
}

/* VPS card hover */
.vps-card {
    transition: all .2s ease;
}

.vps-card:hover {
    border-color: rgba(255,255,255,.1);
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(0,0,0,.2);
}

/* Table row hover */
tr:hover td {
    background: rgba(255,255,255,.03);
}

/* Button transitions */
.btn {
    transition: all .15s ease;
}

.btn:active {
    transform: scale(.98);
}

/* Smooth scrolling */
.page {
    scroll-behavior: smooth;
}

/* Card title with gradient underline */
.card-title-gradient {
    font-size: 14px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    padding-bottom: 12px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(90deg, var(--text), var(--text-dim));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* Detail grid */
.detail-grid {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: 16px;
    align-items: start;
}

@media (max-width: 768px) {
    .detail-grid { grid-template-columns: 1fr !important; }
}
"""
EMBEDDED_JS = """function getTheme() {
    return localStorage.getItem('theme') || 'dark';
}

function setTheme(theme) {
    localStorage.setItem('theme', theme);
    document.body.className = theme === 'light' ? 'light' : '';
    updateThemeIcon();
}

function toggleTheme() {
    setTheme(getTheme() === 'dark' ? 'light' : 'dark');
}

function updateThemeIcon() {
    const btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    const isDark = getTheme() === 'dark';
    btn.innerHTML = isDark
        ? '<svg width="16" height="16"><use href="#icon-sun"/></svg>'
        : '<svg width="16" height="16"><use href="#icon-moon"/></svg>';
}

function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
            showToast('Copied to clipboard');
        }).catch(function() {
            fallbackCopy(text);
        });
    } else {
        fallbackCopy(text);
    }
}
function fallbackCopy(text) {
    var el = document.createElement('textarea');
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    showToast('Copied to clipboard');
}

function showToast(msg) {
    const t = document.createElement('div');
    t.textContent = msg;
    const isLight = getTheme() === 'light';
    Object.assign(t.style, {
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        background: isLight ? '#ffffff' : '#18181b',
        color: isLight ? '#111827' : '#fafafa',
        border: `1px solid ${isLight ? '#e5e7eb' : '#27272a'}`,
        padding: '8px 14px',
        borderRadius: '8px',
        fontSize: '13px',
        fontFamily: 'Inter, sans-serif',
        zIndex: '9999',
        boxShadow: isLight ? '0 4px 12px rgba(0,0,0,0.1)' : '0 4px 12px rgba(0,0,0,0.4)',
        animation: 'fadeIn 0.2s ease'
    });
    document.body.appendChild(t);
    setTimeout(() => {
        t.style.opacity = '0';
        t.style.transition = 'opacity 0.2s';
        setTimeout(() => t.remove(), 200);
    }, 2000);
}

function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

function confirmAction(msg, cb) {
    if (confirm(msg)) cb();
}

document.addEventListener('DOMContentLoaded', () => {
    setTheme(getTheme());

    document.querySelectorAll('.modal-bg').forEach(m => {
        m.addEventListener('click', e => {
            if (e.target === m) m.classList.remove('active');
        });
    });

    document.querySelectorAll('.alert').forEach(a => {
        setTimeout(() => {
            a.style.opacity = '0';
            a.style.transition = 'opacity 0.3s';
            setTimeout(() => a.remove(), 300);
        }, 4000);
    });

    document.querySelectorAll('form').forEach(f => {
        f.addEventListener('submit', function() {
            const b = this.querySelector('button[type="submit"]');
            if (b && !b.dataset.noDisable) {
                b.disabled = true;
                b.style.opacity = '0.6';
            }
        });
    });
});

function populateEditModal(id, name, hostname, nodeUrl, apiKey, maxVps, isLocal) {
    document.getElementById('editNodeId').value = id;
    document.getElementById('editNodeName').value = name;
    document.getElementById('editNodeHostname').value = hostname;
    document.getElementById('editNodeUrl').value = nodeUrl;
    document.getElementById('editNodeApiKey').value = apiKey;
    document.getElementById('editNodeMaxVps').value = maxVps;
    var extraFields = document.getElementById('editNodeExtraFields');
    if (extraFields) { extraFields.style.display = isLocal ? 'none' : ''; }
    openModal('editNodeModal');
}
"""
from jinja2 import DictLoader
app.jinja_loader = DictLoader(EMBEDDED_TEMPLATES)
@app.route('/static/css/style.css')
def embedded_css():
    return Response(EMBEDDED_CSS, mimetype='text/css')
@app.route('/static/js/main.js')
def embedded_js():
    return Response(EMBEDDED_JS, mimetype='application/javascript')
secret_key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secret_key')
if os.path.exists(secret_key_file):
    with open(secret_key_file, 'r') as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    with open(secret_key_file, 'w') as f:
        f.write(app.secret_key)
app.config['MAX_CONTENT_LENGTH'] = 2147483648
app.config['PERMANENT_SESSION_LIFETIME'] = 2592000
app.config['SESSION_COOKIE_NAME'] = 'omega_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
@app.before_request
def make_session_permanent():
    session.permanent = True
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[], storage_uri='memory://')
DATABASE = 'database.db'
SERVER_LIMIT = 5
def get_db():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=10000')
    return conn
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            api_key TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            node_id INTEGER DEFAULT NULL,
            container_id TEXT,
            container_name TEXT,
            ssh_command TEXT,
            status TEXT DEFAULT 'creating',
            os_type TEXT DEFAULT 'ubuntu-22.04',
            ram TEXT DEFAULT '2GB',
            cpu TEXT DEFAULT '1 vCPU',
            disk TEXT DEFAULT '20GB',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS port_forwards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vps_id INTEGER NOT NULL,
            local_port INTEGER NOT NULL,
            remote_port INTEGER NOT NULL,
            serveo_url TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (vps_id) REFERENCES vps(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            resource TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT DEFAULT 'Omega Panel',
            site_description TEXT DEFAULT 'High-Performance VPS Management Panel',
            footer_text TEXT DEFAULT 'Powered by Omega Panel',
            timezone TEXT DEFAULT 'Asia/Kolkata',
            registration_enabled INTEGER DEFAULT 1,
            logo_url TEXT DEFAULT '/static/img/logo.png',
            favicon_url TEXT DEFAULT '/static/img/favicon.ico',
            cpu_threshold INTEGER DEFAULT 90,
            ram_threshold INTEGER DEFAULT 90,
            max_ports_per_user INTEGER DEFAULT 20,
            hostname_prefix TEXT DEFAULT 'vps'
        )
    """)
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN hostname_prefix TEXT DEFAULT 'vps'")
    except:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hostname TEXT NOT NULL,
            node_url TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            status TEXT DEFAULT 'online',
            vps_count INTEGER DEFAULT 0,
            max_vps INTEGER DEFAULT 500,
            cpu_usage REAL DEFAULT 0,
            ram_usage REAL DEFAULT 0,
            is_local INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT DEFAULT 'info',
            message TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vps_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            image_name TEXT NOT NULL,
            size_mb REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vps_id) REFERENCES vps(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vps_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vps_id INTEGER NOT NULL,
            shared_with INTEGER NOT NULL,
            shared_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vps_id) REFERENCES vps(id),
            FOREIGN KEY (shared_with) REFERENCES users(id),
            FOREIGN KEY (shared_by) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vps_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vps_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            time TEXT NOT NULL,
            days TEXT DEFAULT 'everyday',
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vps_id) REFERENCES vps(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    migrations = [("ALTER TABLE settings ADD COLUMN port_forwarding_method TEXT DEFAULT 'serveo'", []), ("ALTER TABLE settings ADD COLUMN public_ipv4 TEXT DEFAULT ''", []), ("ALTER TABLE port_forwards ADD COLUMN method TEXT DEFAULT 'serveo'", []), ('ALTER TABLE port_forwards ADD COLUMN socat_pid INTEGER DEFAULT NULL', []), ('ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0', []), ("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'", []), ("ALTER TABLE settings ADD COLUMN icon_path TEXT DEFAULT ''", []), ('ALTER TABLE settings ADD COLUMN rate_limit_auth INTEGER DEFAULT 10', []), ('ALTER TABLE settings ADD COLUMN rate_limit_api INTEGER DEFAULT 60', []), ('ALTER TABLE settings ADD COLUMN rate_limit_heavy INTEGER DEFAULT 5', []), ('ALTER TABLE vps ADD COLUMN max_backups INTEGER DEFAULT 0', []), ('ALTER TABLE vps ADD COLUMN expires_at TIMESTAMP DEFAULT NULL', []), ('ALTER TABLE settings ADD COLUMN default_vps_days INTEGER DEFAULT 0', []), ('ALTER TABLE vps ADD COLUMN ssh_password TEXT DEFAULT NULL', [])]
    for sql, params in migrations:
        try:
            conn.execute(sql, params)
        except:
            continue
    conn.commit()
    conn.close()
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
def generate_api_key():
    return 'fwa-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))
def log_activity(user_id, action, resource=None, details=None, ip_address=None):
    conn = get_db()
    conn.execute('INSERT INTO activity_log (user_id, action, resource, details, ip_address) VALUES (?, ?, ?, ?, ?)', (user_id, action, resource, details, ip_address))
    conn.commit()
    conn.close()
def add_log(level, message, source='system'):
    conn = get_db()
    conn.execute('INSERT INTO system_logs (level, message, source) VALUES (?, ?, ?)', (level, message, source))
    conn.commit()
    conn.close()
def migrate_nodes():
    conn = get_db()
    try:
        conn.execute('ALTER TABLE nodes ADD COLUMN node_url TEXT DEFAULT ""')
    except:
        pass
    try:
        conn.execute('ALTER TABLE nodes ADD COLUMN api_key TEXT DEFAULT ""')
    except:
        pass
    try:
        conn.execute('ALTER TABLE vps ADD COLUMN node_id INTEGER DEFAULT NULL')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN max_ports_per_user INTEGER DEFAULT 20')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN icon_path TEXT DEFAULT ""')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN rate_limit_auth INTEGER DEFAULT 10')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN rate_limit_api INTEGER DEFAULT 60')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN rate_limit_heavy INTEGER DEFAULT 5')
    except:
        pass
    try:
        conn.execute('ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0')
    except:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    except:
        pass
    try:
        conn.execute("UPDATE users SET role = 'owner' WHERE is_admin = 1 AND id = (SELECT MIN(id) FROM users WHERE is_admin = 1)")
    except:
        pass
    conn.commit()
    conn.close()
def call_node_api(node_url, api_key, endpoint, method='GET', data=None, files=None, stream=False):
    import requests as req
    url = f"{node_url.rstrip('/')}{endpoint}"
    try:
        if files:
            headers = {'X-API-Key': api_key}
            if method == 'POST':
                r = req.post(url, headers=headers, data=data, files=files, timeout=300, stream=stream)
            else:
                return ({'error': 'Files only supported with POST'}, 400)
        else:
            headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}
            if method == 'GET':
                r = req.get(url, headers=headers, timeout=300, stream=stream)
            elif method == 'POST':
                r = req.post(url, headers=headers, json=data, timeout=300, stream=stream)
            elif method == 'DELETE':
                r = req.delete(url, headers=headers, timeout=300)
            else:
                return ({'error': 'Invalid method'}, 400)
        if stream:
            return (r, r.status_code)
        return (r.json(), r.status_code)
    except req.exceptions.ConnectionError:
        return ({'error': 'Node unreachable'}, 502)
    except req.exceptions.Timeout:
        return ({'error': 'Node timeout'}, 504)
    except Exception as e:
        return ({'error': str(e)}, 500)
def get_node_for_vps(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        conn.close()
        return (None, None)
    node = conn.execute('SELECT * FROM nodes WHERE id = ?', (vps['node_id'],)).fetchone() if vps['node_id'] else None
    if not node:
        node = conn.execute('SELECT * FROM nodes WHERE is_local = 1 LIMIT 1').fetchone()
    conn.close()
    return (vps, node)
def get_settings():
    conn = get_db()
    settings = conn.execute('SELECT * FROM settings LIMIT 1').fetchone()
    if not settings:
        conn.execute('INSERT INTO settings DEFAULT VALUES')
        conn.commit()
        settings = conn.execute('SELECT * FROM settings LIMIT 1').fetchone()
    conn.close()
    return settings
def get_rate_limit(tier='api'):
    settings = get_settings()
    defaults = {'auth': '10/minute', 'api': '60/minute', 'heavy': '5/minute'}
    col = f"rate_limit_{tier}"
    if col in settings.keys():
        val = settings[col]
        if val and int(val) > 0:
            return f"{val}/minute"
    return defaults.get(tier, '60/minute')
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        conn = get_db()
        user = conn.execute('SELECT is_banned FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        if user and user['is_banned']:
            session.clear()
            flash('Your account has been banned', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        if not user or not user['is_admin']:
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function
def get_container_ip(container_id):
    try:
        return lxc_get_ip(container_id)
    except:
        pass
def start_socat_local(listen_ip, port, container_ip, container_port=None):
    import subprocess
    import os
    import signal
    import time
    if not container_port:
        container_port = port
    pidfile = f"/tmp/socat_{port}.pid"
    logfile = f"/tmp/socat_{port}.log"
    if os.path.exists(pidfile):
        try:
            with open(pidfile) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(0.5)
        except:
            pass
    proc = subprocess.Popen(['socat', f"TCP-LISTEN:{port},bind=0.0.0.0,reuseaddr,fork", f"TCP:{container_ip}:{container_port}"], stdout=open(logfile, 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    with open(pidfile, 'w') as f:
        f.write(str(proc.pid))
    return proc.pid
def stop_socat_local(port, pid=None):
    import os
    import signal
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except:
            pass
    pidfile = f"/tmp/socat_{port}.pid"
    if os.path.exists(pidfile):
        try:
            with open(pidfile) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
        except:
            pass
        try:
            os.remove(pidfile)
        except:
            pass
def get_random_free_port():
    import socket
    for _ in range(20):
        port = random.randint(30000, 60000)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    raise Exception('No free ports available')
def generate_container_name():
    s = get_settings()
    prefix = s['hostname_prefix'] if 'hostname_prefix' in s.keys() else 'vps'
    if not prefix:
        prefix = 'vps'
    return prefix + '-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')
@app.route('/register', methods=['GET', 'POST'])
@limiter.limit(lambda: get_rate_limit('auth'))
def register():
    settings = get_settings()
    if not settings['registration_enabled']:
        flash('Registration is currently disabled', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect(url_for('register'))
        conn = get_db()
        try:
            try:
                existing = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
                if existing:
                    flash('Username or email already exists', 'error')
                    return redirect(url_for('register'))
                conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, hash_password(password)))
                conn.commit()
                user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
                log_activity(user['id'], 'register', 'auth', json.dumps({'username': username}), request.remote_addr)
                add_log('info', f"New user registered: {username}", 'auth')
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            except sqlite3.Error as e:
                flash(f"Registration failed: {str(e)}", 'error')
        finally:
            conn.close()
        return render_template('register.html')
    return render_template('register.html')
@app.context_processor
def inject_settings():
    settings = get_settings()
    icon_path = settings['icon_path'] if 'icon_path' in settings.keys() else ''
    return dict(settings=settings, custom_icon=icon_path)
@app.route('/tickets')
@login_required
def tickets():
    conn = get_db()
    if session.get('is_admin'):
        ticket_list = conn.execute("""
            SELECT t.*, u.username FROM tickets t
            JOIN users u ON t.user_id = u.id
            ORDER BY t.updated_at DESC
        """).fetchall()
    else:
        ticket_list = conn.execute("""
            SELECT t.*, u.username FROM tickets t
            JOIN users u ON t.user_id = u.id
            WHERE t.user_id = ?
            ORDER BY t.updated_at DESC
        """, (session['user_id'],)).fetchall()
    conn.close()
    return render_template('tickets.html', tickets=ticket_list)
@app.route('/tickets/create', methods=['POST'])
@login_required
def create_ticket():
    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()
    if not subject or not message:
        flash('Subject and message required', 'error')
        return redirect(url_for('tickets'))
    conn = get_db()
    cursor = conn.execute('INSERT INTO tickets (user_id, subject) VALUES (?, ?)', (session['user_id'], subject))
    ticket_id = cursor.lastrowid
    conn.execute('INSERT INTO ticket_replies (ticket_id, user_id, message, is_admin) VALUES (?, ?, ?, 0)', (ticket_id, session['user_id'], message))
    conn.commit()
    conn.close()
    flash('Ticket created', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))
@app.route('/tickets/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    conn = get_db()
    ticket = conn.execute('SELECT t.*, u.username FROM tickets t JOIN users u ON t.user_id = u.id WHERE t.id = ?', (ticket_id,)).fetchone()
    if not ticket:
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    if ticket['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    replies = conn.execute("""
        SELECT r.*, u.username FROM ticket_replies r
        JOIN users u ON r.user_id = u.id
        WHERE r.ticket_id = ?
        ORDER BY r.created_at ASC
    """, (ticket_id,)).fetchall()
    conn.close()
    return render_template('ticket_detail.html', ticket=ticket, replies=replies)
@app.route('/tickets/<int:ticket_id>/reply', methods=['POST'])
@login_required
def reply_ticket(ticket_id):
    message = request.form.get('message', '').strip()
    if not message:
        flash('Message required', 'error')
        return redirect(url_for('ticket_detail', ticket_id=ticket_id))
    conn = get_db()
    ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    if not ticket:
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    if ticket['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    is_admin = 1 if session.get('is_admin') else 0
    conn.execute('INSERT INTO ticket_replies (ticket_id, user_id, message, is_admin) VALUES (?, ?, ?, ?)', (ticket_id, session['user_id'], message, is_admin))
    conn.execute('UPDATE tickets SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))
@app.route('/tickets/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    conn = get_db()
    ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    if not ticket:
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    if ticket['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    conn.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    flash('Ticket closed', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))
@app.route('/tickets/<int:ticket_id>/reopen', methods=['POST'])
@login_required
def reopen_ticket(ticket_id):
    conn = get_db()
    ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    if not ticket:
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    if ticket['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    conn.execute("UPDATE tickets SET status = 'open' WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    flash('Ticket reopened', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))
@app.route('/tickets/<int:ticket_id>/delete', methods=['POST'])
@login_required
def delete_ticket(ticket_id):
    conn = get_db()
    ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    if not ticket:
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    if ticket['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('Ticket not found', 'error')
        conn.close()
        return redirect(url_for('tickets'))
    conn.execute('DELETE FROM ticket_replies WHERE ticket_id = ?', (ticket_id,))
    conn.execute('DELETE FROM tickets WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()
    flash('Ticket deleted', 'success')
    return redirect(url_for('tickets'))
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: get_rate_limit('auth'))
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, hash_password(password))).fetchone()
        conn.close()
        if user:
            if user['is_banned']:
                flash('Your account has been banned', 'error')
                return redirect(url_for('login'))
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            log_activity(user['id'], 'login', 'auth', json.dumps({'ip': request.remote_addr}), request.remote_addr)
            add_log('info', f"User logged in: {username}", 'auth')
            flash('Login successful!', 'success')
            if user['is_admin']:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')
@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_activity(session['user_id'], 'logout', 'auth', None, request.remote_addr)
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    user_vps = conn.execute('SELECT *, NULL as shared_by FROM vps WHERE user_id = ?', (session['user_id'],)).fetchall()
    shared_vps = conn.execute("""
        SELECT v.*, u.username as shared_by
        FROM vps v
        JOIN vps_shares s ON v.id = s.vps_id
        JOIN users u ON s.shared_by = u.id
        WHERE s.shared_with = ?
    """, (session['user_id'],)).fetchall()
    vps_list = list(user_vps) + list(shared_vps)
    settings = get_settings()
    total_cpu = 0
    total_ram = 0
    total_storage = 0
    for vps in vps_list:
        cpu_str = vps['cpu'].replace(' vCPU', '').replace(' core', '')
        total_cpu += int(cpu_str) if cpu_str.isdigit() else 1
        ram_str = vps['ram'].replace('GB', '')
        total_ram += int(ram_str) if ram_str.isdigit() else 2
        disk_str = vps['disk'].replace('GB', '')
        total_storage += int(disk_str) if disk_str.isdigit() else 20
    conn.close()
    return render_template('dashboard.html', vps_list=vps_list, settings=settings, total_cpu=total_cpu, total_ram=total_ram, total_storage=total_storage)
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    activity = conn.execute('SELECT * FROM activity_log WHERE user_id = ? ORDER BY created_at DESC LIMIT 10', (session['user_id'],)).fetchall()
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if hash_password(current_password) != user['password']:
            flash('Current password is incorrect', 'error')
        elif new_password and new_password != confirm_password:
            flash('New passwords do not match', 'error')
        elif new_password and len(new_password) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            if new_password:
                conn.execute('UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?', (username, email, hash_password(new_password), session['user_id']))
            else:
                conn.execute('UPDATE users SET username = ?, email = ? WHERE id = ?', (username, email, session['user_id']))
            conn.commit()
            session['username'] = username
            log_activity(session['user_id'], 'update_profile', 'settings', None, request.remote_addr)
            flash('Profile updated successfully', 'success')
    conn.close()
    return render_template('profile.html', user=user, activity=activity)
@app.route('/profile/regen-api', methods=['POST'])
@admin_required
def regen_api_key():
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user['is_admin']:
        flash('Only admins can manage API keys', 'error')
        conn.close()
        return redirect(url_for('profile'))
    new_key = generate_api_key()
    conn.execute('UPDATE users SET api_key = ? WHERE id = ?', (new_key, session['user_id']))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'regen_api_key', 'security', None, request.remote_addr)
    flash('API key regenerated', 'success')
    return redirect(url_for('profile'))
@app.route('/vps/<int:vps_id>')
@login_required
def vps_detail(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    conn = get_db()
    is_owner = vps['user_id'] == session['user_id']
    is_shared = conn.execute('SELECT * FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    if not is_owner and not is_shared and not session.get('is_admin'):
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    snapshots = _get_snapshots(vps['container_id'] if vps['container_id'] else None, node)
    shares = conn.execute("""
        SELECT s.*, u.username FROM vps_shares s
        JOIN users u ON s.shared_with = u.id
        WHERE s.vps_id = ?
    """, (vps_id,)).fetchall()
    shared_by = None
    if not is_owner:
        row = conn.execute('SELECT s.*, u.username FROM vps_shares s JOIN users u ON s.shared_by = u.id WHERE s.vps_id = ? AND s.shared_with = ?', (vps_id, session['user_id'])).fetchone()
        if row:
            shared_by = row['username']
    conn.close()
    container_status = 'unknown'
    if vps['container_id']:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/status")
            if code == 200:
                container_status = resp.get('state', 'unknown')
            else:
                container_status = 'not_found'
        else:
            try:
                container_status = lxc_status(vps['container_id'])
            except:
                container_status = 'not_found'
    return render_template('vps_detail.html', vps=vps, container_status=container_status, snapshots=snapshots, shares=shares, shared_by=shared_by, is_owner=is_owner)
terminal_sessions = {}
@app.route('/vps/<int:vps_id>/terminal')
@login_required
def vps_terminal(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    conn = get_db()
    is_owner = vps['user_id'] == session['user_id']
    is_shared = conn.execute('SELECT * FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    conn.close()
    if not is_owner and not is_shared and not session.get('is_admin'):
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    return render_template('terminal.html', vps=vps)
@app.route('/api/vps/<int:vps_id>/terminal/session', methods=['POST'])
@login_required
def terminal_create_session(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'VPS not found'}), 404)
    cid = vps['container_id']
    if not cid:
        return (jsonify({'error': 'Container not created yet'}), 400)
    if node and not node['is_local']:
        endpoint = f"/api/container/{cid}/terminal/session?cols={request.args.get('cols', 80)}&rows={request.args.get('rows', 24)}"
        resp, code = call_node_api(node['node_url'], node['api_key'], endpoint, method='POST')
        if code != 200:
            return (jsonify(resp), code)
        return jsonify(resp)
    cols = request.args.get('cols', 80, type=int)
    rows = request.args.get('rows', 24, type=int)
    master_fd, slave_fd = pty.openpty()
    try:
        import fcntl
        import termios
        win = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, win)
    except:
        pass
    proc = subprocess.Popen(['incus', 'exec', cid, '--', '/bin/sh', '-c', 'TERM=xterm-256color exec /bin/bash'], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True)
    os.close(slave_fd)
    session_id = str(uuid.uuid4())
    terminal_sessions[session_id] = {'master_fd': master_fd, 'proc': proc, 'vps_id': vps_id}
    def _cleanup():
        proc.wait()
        time.sleep(0.3)
        try:
            os.close(master_fd)
        except:
            pass
        terminal_sessions.pop(session_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()
    return jsonify({'session_id': session_id})
@app.route('/api/vps/<int:vps_id>/terminal/input', methods=['POST'])
@login_required
def terminal_input(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'VPS not found'}), 404)
    cid = vps['container_id']
    if node and not node['is_local']:
        import requests as req
        url = f"{node['node_url'].rstrip('/')}/api/container/{cid}/terminal/input?session={request.args.get('session', '')}"
        r = req.post(url, headers={'X-API-Key': node['api_key'], 'Content-Type': 'text/plain'}, data=request.get_data(), timeout=30)
        if r.status_code != 204:
            try:
                return (jsonify(r.json()), r.status_code)
            except:
                return (jsonify({'error': 'request failed'}), r.status_code)
        return ('', 204)
    session_id = request.args.get('session')
    sess = terminal_sessions.get(session_id)
    if not sess:
        return (jsonify({'error': 'session not found'}), 404)
    data = request.get_data(as_text=True)
    try:
        os.write(sess['master_fd'], data.encode())
    except OSError:
        return (jsonify({'error': 'terminal closed'}), 410)
    return ('', 204)
@app.route('/api/vps/<int:vps_id>/terminal/resize', methods=['POST'])
@login_required
def terminal_resize(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'VPS not found'}), 404)
    cid = vps['container_id']
    if node and not node['is_local']:
        endpoint = f"/api/container/{cid}/terminal/resize?session={request.args.get('session', '')}&cols={request.args.get('cols', 80)}&rows={request.args.get('rows', 24)}"
        resp, code = call_node_api(node['node_url'], node['api_key'], endpoint, method='POST')
        if code != 204:
            return (jsonify(resp), code)
        return ('', 204)
    session_id = request.args.get('session')
    sess = terminal_sessions.get(session_id)
    if not sess:
        return (jsonify({'error': 'session not found'}), 404)
    cols = request.args.get('cols', 80, type=int)
    rows = request.args.get('rows', 24, type=int)
    try:
        import fcntl
        import termios
        win = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(sess['master_fd'], termios.TIOCSWINSZ, win)
    except:
        return ('', 204)
    return ('', 204)
@app.route('/api/vps/<int:vps_id>/terminal/stream')
@login_required
def terminal_stream(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'VPS not found'}), 404)
    cid = vps['container_id']
    if node and not node['is_local']:
        import requests as req
        url = f"{node['node_url'].rstrip('/')}/api/container/{cid}/terminal/stream?session={request.args.get('session', '')}"
        headers = {'X-API-Key': node['api_key']}
        r = req.get(url, headers=headers, stream=True, timeout=300)
        if r.status_code != 200:
            return (jsonify(r.json()), r.status_code)
        def proxy_stream():
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk.decode(errors='replace')
            r.close()
        resp = Response(proxy_stream(), mimetype='text/event-stream')
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['X-Accel-Buffering'] = 'no'
        return resp
    session_id = request.args.get('session')
    sess = terminal_sessions.get(session_id)
    if not sess:
        return (jsonify({'error': 'session not found'}), 404)
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
    return Response(generate(), mimetype='text/event-stream')
@app.route('/schedules')
@login_required
def schedules():
    conn = get_db()
    schedule_list = conn.execute("""
        SELECT s.*, v.container_name FROM vps_schedules s
        JOIN vps v ON s.vps_id = v.id
        WHERE s.user_id = ?
        ORDER BY s.created_at DESC
    """, (session['user_id'],)).fetchall()
    user_vps = conn.execute('SELECT * FROM vps WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('schedules.html', schedules=schedule_list, user_vps=user_vps)
@app.route('/schedules/create', methods=['POST'])
@login_required
def create_schedule():
    vps_id = request.form.get('vps_id')
    action = request.form.get('action')
    time_val = request.form.get('time')
    days = request.form.get('days', 'everyday')
    if not all([vps_id, action, time_val]):
        flash('All fields required', 'error')
        return redirect(url_for('schedules'))
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ? AND user_id = ?', (vps_id, session['user_id'])).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('schedules'))
    conn.execute('INSERT INTO vps_schedules (vps_id, user_id, action, time, days) VALUES (?, ?, ?, ?, ?)', (vps_id, session['user_id'], action, time_val, days))
    conn.commit()
    conn.close()
    flash('Schedule created', 'success')
    return redirect(url_for('schedules'))
@app.route('/schedules/<int:schedule_id>/toggle', methods=['POST'])
@login_required
def toggle_schedule(schedule_id):
    conn = get_db()
    schedule = conn.execute('SELECT * FROM vps_schedules WHERE id = ? AND user_id = ?', (schedule_id, session['user_id'])).fetchone()
    if not schedule:
        flash('Schedule not found', 'error')
        conn.close()
        return redirect(url_for('schedules'))
    new_val = 0 if schedule['enabled'] else 1
    conn.execute('UPDATE vps_schedules SET enabled = ? WHERE id = ?', (new_val, schedule_id))
    conn.commit()
    conn.close()
    flash('Schedule updated', 'success')
    return redirect(url_for('schedules'))
@app.route('/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    conn = get_db()
    schedule = conn.execute('SELECT * FROM vps_schedules WHERE id = ? AND user_id = ?', (schedule_id, session['user_id'])).fetchone()
    if not schedule:
        flash('Schedule not found', 'error')
        conn.close()
        return redirect(url_for('schedules'))
    conn.execute('DELETE FROM vps_schedules WHERE id = ?', (schedule_id,))
    conn.commit()
    conn.close()
    flash('Schedule deleted', 'success')
    return redirect(url_for('schedules'))
def check_schedules():
    try:
        from datetime import datetime
        now = datetime.now()
        current_time = now.strftime('%H:%M')
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        current_day = day_names[now.weekday()]
        conn = get_db()
        schedules = conn.execute("""
            SELECT s.*, v.container_id, v.container_name, v.status
            FROM vps_schedules s
            JOIN vps v ON s.vps_id = v.id
            WHERE s.enabled = 1 AND s.time = ?
        """, (current_time,)).fetchall()
        for schedule in schedules:
            days = schedule['days']
            if days == 'everyday' or current_day in days.split(','):
                try:
                    if schedule['action'] == 'start' and schedule['status'] != 'running':
                        lxc_start(vps['container_id'])
                        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('running', schedule['vps_id']))
                    elif schedule['action'] == 'stop' and schedule['status'] != 'stopped':
                        lxc_stop(vps['container_id'])
                        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('stopped', schedule['vps_id']))
                    elif schedule['action'] == 'restart':
                        lxc_restart(vps['container_id'])
                        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('running', schedule['vps_id']))
                except:
                    continue
        conn.commit()
        conn.close()
    except:
        pass
def user_has_vps_access(vps_id, user_id, is_admin=False):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        conn.close()
        return (None, None)
    if vps['user_id'] == user_id or is_admin:
        conn.close()
        return (vps, None)
    shared = conn.execute('SELECT 1 FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, user_id)).fetchone()
    conn.close()
    if shared:
        return (vps, None)
    return (None, None)
@app.route('/vps/<int:vps_id>/files')
@login_required
def file_manager(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    path = request.args.get('path', '/')
    if not path.startswith('/'):
        path = '/' + path
    files = []
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/files", method='POST', data={'path': path})
            if code == 200:
                files = resp.get('files', [])
        else:
            exit_code, output = lxc_attach(vps['container_id'], f"ls -la {shlex.quote(path)}", user='root')
            output = output.decode() if isinstance(output, bytes) else str(output)
            if exit_code == 0:
                for line in output.strip().split('\n')[1:]:
                    parts = line.split(None, 8)
                    if len(parts) >= 9 and parts[8] not in ('.', '..'):
                        files.append({'name': parts[8], 'is_dir': parts[0].startswith('d'), 'size': parts[4], 'permissions': parts[0]})
    except:
        flash('Error reading directory', 'error')
    return render_template('file_manager.html', vps=vps, files=files, current_path=path)
@app.route('/vps/<int:vps_id>/files/read')
@login_required
def file_read(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'Not found'}), 404)
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        return (jsonify({'error': 'Not found'}), 404)
    path = request.args.get('path', '')
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/file_read", method='POST', data={'path': path})
            if code == 200:
                return jsonify(resp)
            return
        exit_code, output = lxc_attach(vps['container_id'], f"cat {shlex.quote(path)}", user='root')
        output = output.decode() if isinstance(output, bytes) else str(output)
        return jsonify({'content': output, 'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/vps/<int:vps_id>/files/write', methods=['POST'])
@login_required
def file_write(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'Not found'}), 404)
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        return (jsonify({'error': 'Not found'}), 404)
    data = request.get_json()
    path = data.get('path', '')
    content = data.get('content', '')
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/file_write", method='POST', data={'path': path, 'content': content})
            return jsonify({'success': code == 200 and resp.get('success', False)})
        safe_path = shlex.quote(path)
        cmd = f"cat > {safe_path} << 'VPSMANAGER_EOF'\n{content}\nVPSMANAGER_EOF"
        exit_code, output = lxc_attach(vps['container_id'], cmd, user='root')
        output = output.decode() if isinstance(output, bytes) else str(output)
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/vps/<int:vps_id>/files/mkdir', methods=['POST'])
@login_required
def file_mkdir(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'Not found'}), 404)
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        return (jsonify({'error': 'Not found'}), 404)
    data = request.get_json()
    path = data.get('path', '')
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/exec", method='POST', data={'command': f"mkdir -p {shlex.quote(path)}"})
            return jsonify({'success': code == 200 and resp.get('status') == 'ok'})
        exit_code, output = lxc_attach(vps['container_id'], f"mkdir -p {shlex.quote(path)}", user='root')
        output = output.decode() if isinstance(output, bytes) else str(output)
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/vps/<int:vps_id>/files/delete', methods=['POST'])
@login_required
def file_delete(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'Not found'}), 404)
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        return (jsonify({'error': 'Not found'}), 404)
    data = request.get_json()
    path = data.get('path', '')
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/exec", method='POST', data={'command': f"rm -rf {shlex.quote(path)}"})
            return jsonify({'success': code == 200 and resp.get('status') == 'ok'})
        exit_code, output = lxc_attach(vps['container_id'], f"rm -rf {shlex.quote(path)}", user='root')
        output = output.decode() if isinstance(output, bytes) else str(output)
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/vps/<int:vps_id>/files/upload', methods=['POST'])
@login_required
def file_upload(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('file_manager', vps_id=vps_id))
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        flash('VPS not found', 'error')
        return redirect(url_for('file_manager', vps_id=vps_id))
    path = request.form.get('path', '/')
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        flash('No file selected', 'error')
        return redirect(url_for('file_manager', vps_id=vps_id, path=path))
    filename = uploaded_file.filename
    safe_temp = f"/tmp/omega-upload-{uuid.uuid4().hex}"
    uploaded_file.save(safe_temp)
    try:
        if node and not node['is_local']:
            with open(safe_temp, 'rb') as f:
                resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/upload", method='POST', data={'path': path}, files={'file': (filename, f)})
        else:
            with open(safe_temp, 'rb') as f:
                file_data = f.read()
            class _UCHttp(http.client.HTTPConnection):
                def __init__(self):
                    super().__init__('localhost', timeout=120)
                def connect(self):
                    import socket as _sk
                    self.sock = _sk.socket(_sk.AF_UNIX, _sk.SOCK_STREAM)
                    self.sock.connect('/var/lib/incus/unix.socket')
            conn = _UCHttp()
            try:
                dest = f"{path.rstrip('/')}/{filename}"
                conn.request('POST', f"/1.0/instances/{vps['container_id']}/files?path={dest}&uid=0&gid=0&mode=0644", body=file_data, headers={'Content-Type': 'application/octet-stream'})
                resp = conn.getresponse()
                resp.read()
                if resp.status not in (200, 201, 204):
                    raise Exception(f"LXD upload failed with status {resp.status}")
            finally:
                conn.close()
        os.remove(safe_temp)
        flash('File uploaded', 'success')
    except Exception as e:
        flash(f"Upload failed: {str(e)}", 'error')
        if os.path.exists(safe_temp):
            os.remove(safe_temp)
    return redirect(url_for('file_manager', vps_id=vps_id, path=path))
@app.route('/vps/<int:vps_id>/files/download')
@login_required
def file_download(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('file_manager', vps_id=vps_id))
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        flash('VPS not found', 'error')
        return redirect(url_for('file_manager', vps_id=vps_id))
    path = request.args.get('path', '')
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/download", method='POST', data={'path': path})
            if code == 200 and 'data' in resp:
                import base64
                data = base64.b64decode(resp['data'])
                return Response(data, headers={'Content-Disposition': f"attachment; filename={os.path.basename(path)}", 'Content-Type': 'application/octet-stream'})
        else:
            archive_data = lxc_get_archive(vps['container_id'], path)
            return Response(bits, headers={'Content-Disposition': f"attachment; filename={os.path.basename(path)}.tar", 'Content-Type': 'application/gzip'})
    except Exception as e:
        flash(f"Download failed: {str(e)}", 'error')
    return redirect(url_for('file_manager', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/processes')
@login_required
def process_manager(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    processes = []
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/top")
            if code == 200:
                processes = resp.get('processes', [])
        else:
            exit_code, output = lxc_attach(vps['container_id'], 'ps aux --sort=-%cpu', user='root')
            if isinstance(output, bytes):
                output = output.decode('utf-8', errors='ignore')
            if exit_code == 0:
                lines = output.strip().split('\n')
                for line in lines[1:]:
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        processes.append({'pid': parts[1], 'user': parts[0], 'cpu': parts[2], 'mem': parts[3], 'command': parts[10]})
    except:
        pass
    return render_template('process_manager.html', vps=vps, processes=processes)
@app.route('/vps/<int:vps_id>/processes/kill', methods=['POST'])
@login_required
def kill_process(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'Not found'}), 404)
    access, _ = user_has_vps_access(vps_id, session['user_id'], session.get('is_admin'))
    if not access:
        return (jsonify({'error': 'Not found'}), 404)
    data = request.get_json()
    pid = data.get('pid', '')
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/exec", method='POST', data={'command': f"kill -9 {pid}"})
            return jsonify(resp)
        _, output = lxc_attach(vps['container_id'], f"kill -9 {pid}", user='root')
        output = output.decode() if isinstance(output, bytes) else str(output)
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/admin')
@admin_required
def admin_panel():
    conn = get_db()
    users = conn.execute('SELECT * FROM users').fetchall()
    all_vps = conn.execute('SELECT v.*, u.username FROM vps v JOIN users u ON v.user_id = u.id').fetchall()
    nodes = conn.execute('SELECT * FROM nodes ORDER BY is_local DESC, name ASC').fetchall()
    total_users = len(users)
    total_vps = len(all_vps)
    active_vps = len([v for v in all_vps if v['status'] == 'running'])
    expiring_count = conn.execute("SELECT COUNT(*) as c FROM vps WHERE expires_at IS NOT NULL AND expires_at > datetime('now') AND expires_at < datetime('now', '+7 days')").fetchone()['c']
    settings = get_settings()
    conn.close()
    return render_template('admin.html', users=users, vps_list=all_vps, nodes=nodes, total_users=total_users, total_vps=total_vps, active_vps=active_vps, expiring_count=expiring_count, settings=settings)
@app.route('/admin/create-vps', methods=['POST'])
@admin_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def admin_create_vps():
    user_id = request.form.get('user_id')
    os_type = request.form.get('os_type', 'ubuntu-22.04')
    ram_mb = request.form.get('ram', '2048')
    ram = f"{ram_mb}MB"
    cpu_cores = request.form.get('cpu', '1')
    cpu = f"{cpu_cores} vCPU"
    disk_gb = request.form.get('disk', '20')
    disk = f"{disk_gb}GB"
    node_id = request.form.get('node_id')
    max_backups = request.form.get('max_backups', 0)
    if not user_id:
        flash('Please select a user', 'error')
        return redirect(url_for('admin_panel'))
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('admin_panel'))
    if node_id:
        node = conn.execute('SELECT * FROM nodes WHERE id = ?', (node_id,)).fetchone()
    else:
        node = conn.execute('SELECT * FROM nodes WHERE is_local = 1 LIMIT 1').fetchone()
    if not node:
        flash('No node available', 'error')
        conn.close()
        return redirect(url_for('admin_panel'))
    container_name = generate_container_name()
    image_map = {'ubuntu-22.04': '22.04', 'ubuntu-24.04': '24.04', 'ubuntu-26.04': '26.04'}
    image = image_map.get(os_type, '22.04')
    try:
        try:
            if node['is_local']:
                container_id = lxc_create(container_name, os_type, ram, cpu, disk)
            else:
                resp, code = call_node_api(node['node_url'], node['api_key'], '/api/container/create', method='POST', data={'name': container_name, 'image': image, 'ram': ram, 'cpu': cpu, 'disk': disk})
                if code != 200 or resp.get('error'):
                    raise Exception(resp.get('error', 'Failed to create on remote node'))
                container_id = resp['container_id']
            settings = get_settings()
            default_days = settings['default_vps_days'] if 'default_vps_days' in settings.keys() else 0
            expires_at = None
            if default_days > 0:
                from datetime import timedelta
                expires_at = (datetime.now() + timedelta(days=default_days)).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute('INSERT INTO vps (user_id, node_id, container_id, container_name, os_type, ram, cpu, disk, status, max_backups, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (user_id, node['id'], container_id, container_name, os_type, ram, cpu, disk, 'created', max_backups, expires_at))
            conn.commit()
            log_activity(user['id'], 'create_vps', 'vps', json.dumps({'name': container_name}), request.remote_addr)
            add_log('info', f"VPS created: {container_name} for {user['username']} on node {node['name']}", 'vps')
            flash(f"VPS created successfully for {user['username']} on node {node['name']}", 'success')
        except Exception as e:
            flash(f"Error creating VPS: {str(e)}", 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_panel'))
@app.route('/vps/<int:vps_id>/transfer', methods=['POST'])
@login_required
def transfer_vps(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    if vps['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    target_username = request.form.get('target_username', '').strip()
    if not target_username:
        flash('Enter a username', 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    target = conn.execute('SELECT * FROM users WHERE username = ?', (target_username,)).fetchone()
    if not target:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    if target['id'] == vps['user_id']:
        flash('VPS already belongs to this user', 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    old_owner = conn.execute('SELECT username FROM users WHERE id = ?', (vps['user_id'],)).fetchone()
    conn.execute('UPDATE vps SET user_id = ? WHERE id = ?', (target['id'], vps_id))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'transfer_vps', 'vps', json.dumps({'vps': vps['container_name'], 'from': old_owner['username'] if old_owner else '?', 'to': target['username']}), request.remote_addr)
    flash(f"VPS transferred to {target['username']}", 'success')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/transfer', methods=['POST'])
@admin_required
def admin_transfer_vps(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('admin_all_vps'))
    target_username = request.form.get('target_username', '').strip()
    if not target_username:
        flash('Enter a username', 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    target = conn.execute('SELECT * FROM users WHERE username = ?', (target_username,)).fetchone()
    if not target:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    if target['id'] == vps['user_id']:
        flash('VPS already belongs to this user', 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    old_owner = conn.execute('SELECT username FROM users WHERE id = ?', (vps['user_id'],)).fetchone()
    conn.execute('UPDATE vps SET user_id = ? WHERE id = ?', (target['id'], vps_id))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'transfer_vps', 'vps', json.dumps({'vps': vps['container_name'], 'from': old_owner['username'] if old_owner else '?', 'to': target['username']}), request.remote_addr)
    flash(f"VPS transferred to {target['username']}", 'success')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/share', methods=['POST'])
@login_required
def share_vps(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    if vps['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    target_username = request.form.get('target_username', '').strip()
    if not target_username:
        flash('Enter a username', 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    target = conn.execute('SELECT * FROM users WHERE username = ?', (target_username,)).fetchone()
    if not target:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    if target['id'] == vps['user_id']:
        flash('Cannot share with yourself', 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    existing = conn.execute('SELECT * FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, target['id'])).fetchone()
    if existing:
        flash(f"Already shared with {target['username']}", 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    conn.execute('INSERT INTO vps_shares (vps_id, shared_with, shared_by) VALUES (?, ?, ?)', (vps_id, target['id'], session['user_id']))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'share_vps', 'vps', json.dumps({'vps': vps['container_name'], 'shared_with': target['username']}), request.remote_addr)
    flash(f"VPS shared with {target['username']}", 'success')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/unshare/<int:share_id>', methods=['POST'])
@login_required
def unshare_vps(vps_id, share_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    if vps['user_id'] != session['user_id'] and not session.get('is_admin'):
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    share = conn.execute('SELECT * FROM vps_shares WHERE id = ? AND vps_id = ?', (share_id, vps_id)).fetchone()
    if not share:
        flash('Share not found', 'error')
        conn.close()
        return redirect(url_for('vps_detail', vps_id=vps_id))
    conn.execute('DELETE FROM vps_shares WHERE id = ?', (share_id,))
    conn.commit()
    conn.close()
    flash('Share removed', 'success')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/share', methods=['POST'])
@admin_required
def admin_share_vps(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('admin_all_vps'))
    target_username = request.form.get('target_username', '').strip()
    if not target_username:
        flash('Enter a username', 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    target = conn.execute('SELECT * FROM users WHERE username = ?', (target_username,)).fetchone()
    if not target:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    if target['id'] == vps['user_id']:
        flash('Cannot share with yourself', 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    existing = conn.execute('SELECT * FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, target['id'])).fetchone()
    if existing:
        flash(f"Already shared with {target['username']}", 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    conn.execute('INSERT INTO vps_shares (vps_id, shared_with, shared_by) VALUES (?, ?, ?)', (vps_id, target['id'], session['user_id']))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'share_vps', 'vps', json.dumps({'vps': vps['container_name'], 'shared_with': target['username']}), request.remote_addr)
    flash(f"VPS shared with {target['username']}", 'success')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/unshare/<int:share_id>', methods=['POST'])
@admin_required
def admin_unshare_vps(vps_id, share_id):
    conn = get_db()
    share = conn.execute('SELECT * FROM vps_shares WHERE id = ? AND vps_id = ?', (share_id, vps_id)).fetchone()
    if not share:
        flash('Share not found', 'error')
        conn.close()
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    conn.execute('DELETE FROM vps_shares WHERE id = ?', (share_id,))
    conn.commit()
    conn.close()
    flash('Share removed', 'success')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/start', methods=['POST'])
@login_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def start_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    conn = get_db()
    is_shared = conn.execute('SELECT 1 FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    conn.close()
    if vps['user_id'] != session['user_id'] and not is_shared and not session.get('is_admin'):
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    try:
        if node['is_local']:
            lxc_start(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/start", method='POST')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('running', vps_id))
        conn.commit()
        conn.close()
        log_activity(session['user_id'], 'start_vps', 'vps', json.dumps({'name': vps['container_name']}), request.remote_addr)
        add_log('info', f"VPS started: {vps['container_name']}", 'vps')
        flash('VPS started successfully', 'success')
    except Exception as e:
        flash(f"Error starting VPS: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/stop', methods=['POST'])
@login_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def stop_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    conn = get_db()
    is_shared = conn.execute('SELECT 1 FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    conn.close()
    if vps['user_id'] != session['user_id'] and not is_shared and not session.get('is_admin'):
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    try:
        if node['is_local']:
            lxc_stop(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/stop", method='POST')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('stopped', vps_id))
        conn.commit()
        conn.close()
        log_activity(session['user_id'], 'stop_vps', 'vps', json.dumps({'name': vps['container_name']}), request.remote_addr)
        add_log('info', f"VPS stopped: {vps['container_name']}", 'vps')
        flash('VPS stopped successfully', 'success')
    except Exception as e:
        flash(f"Error stopping VPS: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/restart', methods=['POST'])
@login_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def restart_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    conn = get_db()
    is_shared = conn.execute('SELECT 1 FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    conn.close()
    if vps['user_id'] != session['user_id'] and not is_shared and not session.get('is_admin'):
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    try:
        if node['is_local']:
            lxc_restart(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/restart", method='POST')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('running', vps_id))
        conn.commit()
        conn.close()
        log_activity(session['user_id'], 'restart_vps', 'vps', json.dumps({'name': vps['container_name']}), request.remote_addr)
        add_log('info', f"VPS restarted: {vps['container_name']}", 'vps')
        flash('VPS restarted successfully', 'success')
    except Exception as e:
        flash(f"Error restarting VPS: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/regen-ssh', methods=['POST'])
@login_required
def regen_ssh(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    conn = get_db()
    is_shared = conn.execute('SELECT 1 FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    conn.close()
    if vps['user_id'] != session['user_id'] and not is_shared and not session.get('is_admin'):
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    ssh_session_line = None
    ssh_password_val = None
    try:
        if node['is_local']:
            if lxc_status(vps['container_id']) != 'running':
                lxc_start(vps['container_id'])
                time.sleep(2)
            try:
                lxc_attach(vps['container_id'], 'pkill sshx')
                time.sleep(1)
            except:
                pass
            lxc_attach(vps['container_id'], 'command -v sshx >/dev/null 2>&1 || curl -sSf https://sshx.io/get | sh', timeout=60)
            exit_code, output = lxc_attach(vps['container_id'], 'nohup sshx > /tmp/sshx_output.log 2>&1 & sleep 10; cat /tmp/sshx_output.log 2>/dev/null')
            if isinstance(output, bytes):
                output = output.decode('utf-8', errors='ignore')
            for line in str(output).split('\n'):
                decoded = strip_ansi(line.strip())
                if 'sshx.io' in decoded:
                    match = re.search('https://sshx\\.io/s/[a-zA-Z0-9#]+', decoded)
                    if match:
                        ssh_session_line = match.group(0)
                        break
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/regen-ssh", method='POST', data={'method': 'sshx'})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
            ssh_session_line = resp.get('ssh_command')
            ssh_password_val = resp.get('password')
        if ssh_session_line:
            conn = get_db()
            conn.execute('UPDATE vps SET ssh_command = ?, ssh_password = ? WHERE id = ?', (ssh_session_line, ssh_password_val, vps_id))
            conn.commit()
            conn.close()
            flash('SSH credentials regenerated', 'success')
        else:
            flash('Failed to regenerate SSH credentials', 'error')
    except Exception as e:
        flash(f"Error regenerating SSH: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/regen-ssh', methods=['POST'])
@admin_required
def admin_regen_ssh(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_all_vps'))
    ssh_session_line = None
    ssh_password_val = None
    try:
        if node['is_local']:
            if lxc_status(vps['container_id']) != 'running':
                lxc_start(vps['container_id'])
                time.sleep(2)
            try:
                lxc_attach(vps['container_id'], 'pkill sshx')
                time.sleep(1)
            except:
                pass
            lxc_attach(vps['container_id'], 'command -v sshx >/dev/null 2>&1 || curl -sSf https://sshx.io/get | sh', timeout=60)
            exit_code, output = lxc_attach(vps['container_id'], 'nohup sshx > /tmp/sshx_output.log 2>&1 & sleep 10; cat /tmp/sshx_output.log 2>/dev/null')
            if isinstance(output, bytes):
                output = output.decode('utf-8', errors='ignore')
            for line in str(output).split('\n'):
                decoded = strip_ansi(line.strip())
                if 'sshx.io' in decoded:
                    match = re.search('https://sshx\\.io/s/[a-zA-Z0-9#]+', decoded)
                    if match:
                        ssh_session_line = match.group(0)
                        break
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/regen-ssh", method='POST', data={'method': 'sshx'})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
            ssh_session_line = resp.get('ssh_command')
            ssh_password_val = resp.get('password')
        if ssh_session_line:
            conn = get_db()
            conn.execute('UPDATE vps SET ssh_command = ?, ssh_password = ? WHERE id = ?', (ssh_session_line, ssh_password_val, vps_id))
            conn.commit()
            conn.close()
            flash('SSH credentials regenerated', 'success')
        else:
            flash('Failed to regenerate SSH credentials', 'error')
    except Exception as e:
        flash(f"Error regenerating SSH: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/delete', methods=['POST'])
@login_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def delete_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps or vps['user_id'] != session['user_id']:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    try:
        if node['is_local']:
            lxc_stop(vps['container_id'])
            lxc_destroy(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/delete", method='POST')
    except:
        pass
    conn = get_db()
    conn.execute('DELETE FROM port_forwards WHERE vps_id = ?', (vps_id,))
    conn.execute('DELETE FROM backups WHERE vps_id = ?', (vps_id,))
    conn.execute('DELETE FROM vps WHERE id = ?', (vps_id,))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'delete_vps', 'vps', json.dumps({'name': vps['container_name']}), request.remote_addr)
    add_log('warning', f"VPS deleted: {vps['container_name']}", 'vps')
    flash('VPS deleted successfully', 'success')
    return redirect(url_for('dashboard'))
@app.route('/admin/vps/<int:vps_id>/update', methods=['POST'])
@admin_required
def admin_update_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_all_vps'))
    ram_raw = request.form.get('ram', '').strip()
    cpu_raw = request.form.get('cpu', '').strip()
    disk_raw = request.form.get('disk', '').strip()
    max_backups = request.form.get('max_backups', '').strip()
    ram = f"{ram_raw}MB" if ram_raw else ''
    cpu = cpu_raw if cpu_raw else ''
    disk = f"{disk_raw}GB" if disk_raw else ''
    try:
        has_spec_change = bool(ram or cpu or disk)
        if has_spec_change:
            import subprocess
            cid = vps['container_id']
            if node['is_local']:
                if ram:
                    subprocess.run(['incus', 'config', 'set', cid, 'limits.memory=' + ram], timeout=30, capture_output=True)
                if cpu:
                    subprocess.run(['incus', 'config', 'set', cid, 'limits.cpu=' + cpu], timeout=30, capture_output=True)
                if disk:
                    subprocess.run(['incus', 'config', 'device', 'set', cid, 'root', 'size=' + disk], timeout=30, capture_output=True)
            else:
                resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{cid}/update", method='POST', data={'ram': ram, 'cpu': cpu, 'disk': disk})
                if code != 200 or resp.get('error'):
                    raise Exception(resp.get('error', 'Update failed on remote node'))
            if vps['status'] == 'running':
                if node['is_local']:
                    lxc_stop(cid)
                else:
                    call_node_api(node['node_url'], node['api_key'], f"/api/container/{cid}/stop", method='POST')
        conn = get_db()
        updates = []
        vals = []
        if ram:
            updates.append('ram = ?')
            vals.append(ram)
        if cpu:
            updates.append('cpu = ?')
            vals.append(cpu)
        if disk:
            updates.append('disk = ?')
            vals.append(disk)
        if max_backups != '':
            updates.append('max_backups = ?')
            vals.append(int(max_backups))
        if updates:
            vals.append(vps_id)
            conn.execute(f"UPDATE vps SET {', '.join(updates)} WHERE id = ?", vals)
            conn.commit()
        conn.close()
        flash('VPS updated successfully', 'success')
    except Exception as e:
        flash(f"Error updating VPS: {str(e)}", 'error')
    return redirect(url_for('admin_all_vps'))
@app.route('/admin/delete-vps/<int:vps_id>', methods=['POST'])
@admin_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def admin_delete_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_all_vps'))
    try:
        if node['is_local']:
            lxc_stop(vps['container_id'])
            lxc_destroy(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/delete", method='POST')
    except:
        pass
    conn = get_db()
    conn.execute('DELETE FROM port_forwards WHERE vps_id = ?', (vps_id,))
    conn.execute('DELETE FROM backups WHERE vps_id = ?', (vps_id,))
    conn.execute('DELETE FROM vps WHERE id = ?', (vps_id,))
    conn.commit()
    conn.close()
    add_log('warning', f"VPS deleted by admin: {vps['container_name']}", 'vps')
    flash('VPS deleted successfully', 'success')
    return redirect(url_for('admin_all_vps'))
@app.route('/admin/start-vps/<int:vps_id>', methods=['POST'])
@admin_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def admin_start_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_panel'))
    try:
        if node['is_local']:
            lxc_start(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/start", method='POST')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('running', vps_id))
        conn.commit()
        conn.close()
        add_log('info', f"VPS started by admin: {vps['container_name']}", 'vps')
        flash('VPS started successfully', 'success')
    except Exception as e:
        flash(f"Error starting VPS: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/stop-vps/<int:vps_id>', methods=['POST'])
@admin_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def admin_stop_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_panel'))
    try:
        if node['is_local']:
            lxc_stop(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/stop", method='POST')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('stopped', vps_id))
        conn.commit()
        conn.close()
        add_log('info', f"VPS stopped by admin: {vps['container_name']}", 'vps')
        flash('VPS stopped successfully', 'success')
    except Exception as e:
        flash(f"Error stopping VPS: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/restart-vps/<int:vps_id>', methods=['POST'])
@admin_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def admin_restart_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_panel'))
    try:
        if node['is_local']:
            lxc_restart(vps['container_id'])
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/restart", method='POST')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET status = ? WHERE id = ?', ('running', vps_id))
        conn.commit()
        conn.close()
        add_log('info', f"VPS restarted by admin: {vps['container_name']}", 'vps')
        flash('VPS restarted successfully', 'success')
    except Exception as e:
        flash(f"Error restarting VPS: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/reinstall', methods=['POST'])
@admin_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def admin_reinstall_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_all_vps'))
    os_type = request.form.get('os_type', vps['os_type'])
    image_map = {'ubuntu-22.04': '22.04', 'ubuntu-24.04': '24.04', 'ubuntu-26.04': '26.04'}
    image = image_map.get(os_type, '22.04')
    try:
        if node['is_local']:
            try:
                lxc_stop(vps['container_id'])
                lxc_destroy(vps['container_id'])
            except:
                pass
            container_id = lxc_create(vps['container_name'], os_type, vps['ram'], vps['cpu'], vps['disk'])
        else:
            try:
                call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/delete", method='POST')
            except:
                pass
            resp, code = call_node_api(node['node_url'], node['api_key'], '/api/container/create', method='POST', data={'name': vps['container_name'], 'image': image, 'ram': vps['ram'], 'cpu': vps['cpu'], 'disk': vps['disk']})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed to create new container'))
            container_id = resp['container_id']
        conn = get_db()
        conn.execute("""UPDATE vps SET container_id = ?, os_type = ?,
                       status = ?, ssh_command = NULL WHERE id = ?""", (container_id, os_type, 'created', vps_id))
        conn.commit()
        conn.close()
        add_log('warning', f"VPS reinstalled by admin: {vps['container_name']} → {os_type}", 'vps')
        flash(f"VPS reinstalled with {os_type}", 'success')
    except Exception as e:
        flash(f"Error reinstalling VPS: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/reinstall', methods=['POST'])
@login_required
@limiter.limit(lambda: get_rate_limit('heavy'))
def reinstall_vps(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps or vps['user_id'] != session['user_id']:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    os_type = request.form.get('os_type', vps['os_type'])
    image_map = {'ubuntu-22.04': '22.04', 'ubuntu-24.04': '24.04', 'ubuntu-26.04': '26.04'}
    image = image_map.get(os_type, '22.04')
    try:
        if node['is_local']:
            try:
                lxc_stop(vps['container_id'])
                lxc_destroy(vps['container_id'])
            except:
                pass
            container_id = lxc_create(vps['container_name'], os_type, vps['ram'], vps['cpu'], vps['disk'])
        else:
            try:
                call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/delete", method='POST')
            except:
                pass
            resp, code = call_node_api(node['node_url'], node['api_key'], '/api/container/create', method='POST', data={'name': vps['container_name'], 'image': image, 'ram': vps['ram'], 'cpu': vps['cpu'], 'disk': vps['disk']})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed to create new container'))
            container_id = resp['container_id']
        conn = get_db()
        conn.execute("""UPDATE vps SET container_id = ?, os_type = ?,
                       status = ?, ssh_command = NULL WHERE id = ?""", (container_id, os_type, 'created', vps_id))
        conn.commit()
        conn.close()
        log_activity(session['user_id'], 'reinstall_vps', 'vps', json.dumps({'name': vps['container_name'], 'os': os_type}), request.remote_addr)
        add_log('warning', f"VPS reinstalled: {vps['container_name']} → {os_type}", 'vps')
        flash(f"VPS reinstalled with {os_type}", 'success')
    except Exception as e:
        flash(f"Error reinstalling VPS: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>')
@admin_required
def admin_vps_detail(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT v.*, u.username FROM vps v JOIN users u ON v.user_id = u.id WHERE v.id = ?', (vps_id,)).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('admin_all_vps'))
    shares = conn.execute("""
        SELECT s.*, u.username FROM vps_shares s
        JOIN users u ON s.shared_with = u.id
        WHERE s.vps_id = ?
    """, (vps_id,)).fetchall()
    conn.close()
    snapshots = []
    container_status = 'unknown'
    if vps['container_id']:
        vps_data, node = get_node_for_vps(vps_id)
        snapshots = _get_snapshots(vps['container_id'], node)
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/status")
            if code == 200:
                container_status = resp.get('state', 'unknown')
            else:
                container_status = 'not_found'
        else:
            try:
                container_status = lxc_status(vps['container_id'])
            except:
                container_status = 'not_found'
    return render_template('admin_vps_detail.html', vps=vps, container_status=container_status, snapshots=snapshots, shares=shares)
@app.route('/api/vps/<int:vps_id>/status')
@login_required
@limiter.limit(lambda: get_rate_limit('api'))
def api_vps_status(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'VPS not found'}), 404)
    conn = get_db()
    is_shared = conn.execute('SELECT 1 FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    conn.close()
    if vps['user_id'] != session['user_id'] and not is_shared and not session.get('is_admin'):
        return (jsonify({'error': 'VPS not found'}), 404)
    if node and not node['is_local']:
        resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/status")
        if code == 200:
            return jsonify({'status': resp.get('state', 'unknown'), 'id': resp.get('id', ''), 'name': vps['container_name']})
        return jsonify({'status': 'not_found', 'name': vps['container_name']})
    try:
        return jsonify({'status': lxc_status(vps['container_id']), 'id': vps['container_id'], 'name': vps['container_name']})
    except:
        return jsonify({'status': 'not_found'})
@app.route('/ports')
@login_required
def port_forwarding():
    conn = get_db()
    forwards = conn.execute("""
        SELECT pf.*, v.container_name, v.status as vps_status
        FROM port_forwards pf
        JOIN vps v ON pf.vps_id = v.id
        WHERE pf.user_id = ?
        ORDER BY pf.created_at DESC
    """, (session['user_id'],)).fetchall()
    user_vps = conn.execute('SELECT * FROM vps WHERE user_id = ? AND status = "running"', (session['user_id'],)).fetchall()
    shared_vps = conn.execute("""
        SELECT v.* FROM vps v
        JOIN vps_shares s ON v.id = s.vps_id
        WHERE s.shared_with = ? AND v.status = 'running'
    """, (session['user_id'],)).fetchall()
    user_vps = list(user_vps) + list(shared_vps)
    settings = get_settings()
    conn.close()
    allocated = settings['max_ports_per_user']
    used = len(forwards)
    available = allocated - used
    return render_template('ports.html', forwards=forwards, user_vps=user_vps, allocated=allocated, used=used, available=available)
@app.route('/ports/create', methods=['POST'])
@login_required
def create_port_forward():
    vps_id = request.form.get('vps_id')
    local_port = request.form.get('local_port', '')
    if not vps_id or not local_port.isdigit() or not 1 <= int(local_port) <= 65535:
        flash('All fields are required', 'error')
        return redirect(url_for('port_forwarding'))
    local_port = int(local_port)
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ? AND (user_id = ? OR id IN (SELECT vps_id FROM vps_shares WHERE shared_with = ?))', (vps_id, session['user_id'], session['user_id'])).fetchone()
    if not vps or vps['status'] != 'running':
        flash('VPS must be running', 'error')
        conn.close()
        return redirect(url_for('port_forwarding'))
    settings = get_settings()
    method = settings['port_forwarding_method'] if 'port_forwarding_method' in settings.keys() else 'serveo'
    if method == 'ipv4':
        user_port_count = conn.execute('SELECT COUNT(*) as c FROM port_forwards WHERE user_id = ?', (session['user_id'],)).fetchone()['c']
        if user_port_count >= settings['max_ports_per_user']:
            flash(f"Port quota reached ({settings['max_ports_per_user']}). Delete some ports first.", 'error')
            conn.close()
            return redirect(url_for('port_forwarding'))
    try:
        try:
            vps_data, node = get_node_for_vps(vps_id)
            if method == 'ipv4':
                public_ipv4 = settings['public_ipv4'] if 'public_ipv4' in settings.keys() else ''
                if not public_ipv4:
                    raise Exception('Public IPv4 address not configured in settings')
                external_port = get_random_free_port()
                if node['is_local']:
                    container_ip = get_container_ip(vps['container_id'])
                    if not container_ip:
                        raise Exception('Could not determine container IP')
                    pid = start_socat_local(public_ipv4, external_port, container_ip, local_port)
                    public_url = f"http://{public_ipv4}:{external_port}"
                    conn.execute('INSERT INTO port_forwards (user_id, vps_id, local_port, remote_port, serveo_url, method, socat_pid) VALUES (?, ?, ?, ?, ?, ?, ?)', (session['user_id'], vps_id, local_port, external_port, public_url, 'ipv4', pid))
                else:
                    container_ip_resp, _ = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/ip")
                    container_ip = container_ip_resp.get('ip', '') if container_ip_resp else ''
                    if not container_ip:
                        raise Exception('Could not determine container IP on remote node')
                    resp, code = call_node_api(node['node_url'], node['api_key'], '/api/socat/start', method='POST', data={'listen_ip': public_ipv4, 'port': external_port, 'container_ip': container_ip, 'container_port': int(local_port)})
                    if code != 200 or resp.get('error'):
                        raise Exception(resp.get('error', 'Failed to start socat on remote node'))
                    public_url = f"http://{public_ipv4}:{external_port}"
                    conn.execute('INSERT INTO port_forwards (user_id, vps_id, local_port, remote_port, serveo_url, method, socat_pid) VALUES (?, ?, ?, ?, ?, ?, ?)', (session['user_id'], vps_id, local_port, external_port, public_url, 'ipv4', resp.get('pid')))
                conn.commit()
                log_activity(session['user_id'], 'create_port_forward', 'port', json.dumps({'vps': vps['container_name'], 'local': local_port, 'url': public_url, 'method': 'ipv4'}), request.remote_addr)
                flash(f"Port forwarding created: {public_url}", 'success')
            else:
                serveo_cmd = f"ssh -o StrictHostKeyChecking=no -R 80:localhost:{local_port} serveo.net"
                if node['is_local']:
                    lxc_attach(vps['container_id'], f"bash -c \"nohup {serveo_cmd} > /tmp/serveo_{local_port}.log 2>&1 &\"", detach=True)
                    import time
                    log_output = ''
                    for _ in range(10):
                        time.sleep(2)
                        _, output = lxc_attach(vps['container_id'], f"cat /tmp/serveo_{local_port}.log")
                        log_output = output.decode() if isinstance(output, bytes) else str(output)
                        if 'serveousercontent.com' in log_output or 'https://' in log_output:
                            break
                else:
                    resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/exec", method='POST', data={'command': f"bash -c \"nohup {serveo_cmd} > /tmp/serveo_{local_port}.log 2>&1 &\"", 'detach': True})
                    if code != 200 or resp.get('error'):
                        raise Exception(resp.get('error', 'Failed on remote node'))
                    import time
                    log_output = ''
                    for _ in range(10):
                        time.sleep(2)
                        resp2, code2 = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/exec", method='POST', data={'command': f"cat /tmp/serveo_{local_port}.log"})
                        if code2 == 200:
                            log_output = resp2.get('output', '')
                        if 'serveousercontent.com' in log_output or 'https://' in log_output:
                            break
                serveo_url = None
                for line in log_output.split('\n'):
                    clean = strip_ansi(line.strip())
                    if 'serveousercontent.com' in clean or 'serveo.net' in clean:
                        import re
                        match = re.search('https?://\\S+serveo\\S+', clean)
                        if match:
                            serveo_url = match.group(0).rstrip('.')
                            break
                if not serveo_url:
                    raise Exception('Serveo did not return a URL. The tunnel may have failed to start.')
                conn.execute('INSERT INTO port_forwards (user_id, vps_id, local_port, remote_port, serveo_url, method) VALUES (?, ?, ?, ?, ?, ?)', (session['user_id'], vps_id, local_port, 80, serveo_url, 'serveo'))
                conn.commit()
                log_activity(session['user_id'], 'create_port_forward', 'port', json.dumps({'vps': vps['container_name'], 'local': local_port, 'url': serveo_url, 'method': 'serveo'}), request.remote_addr)
                flash(f"Port forwarding created: {serveo_url}", 'success')
        except Exception as e:
            flash(f"Error creating port forward: {str(e)}", 'error')
    finally:
        conn.close()
    return redirect(url_for('port_forwarding'))
@app.route('/ports/<int:port_id>/delete', methods=['POST'])
@login_required
def delete_port_forward(port_id):
    conn = get_db()
    forward = conn.execute('SELECT * FROM port_forwards WHERE id = ? AND (user_id = ? OR vps_id IN (SELECT vps_id FROM vps_shares WHERE shared_with = ?))', (port_id, session['user_id'], session['user_id'])).fetchone()
    if forward:
        method = forward['method'] if 'method' in forward.keys() else 'serveo'
        if method == 'ipv4':
            socat_pid = forward['socat_pid'] if 'socat_pid' in forward.keys() else None
            external_port = forward['remote_port']
            vps_data, node = get_node_for_vps(forward['vps_id'])
            if node['is_local']:
                stop_socat_local(external_port, socat_pid)
            else:
                try:
                    call_node_api(node['node_url'], node['api_key'], '/api/socat/stop', method='POST', data={'port': external_port, 'pid': socat_pid})
                except:
                    pass
        conn.execute('DELETE FROM port_forwards WHERE id = ?', (port_id,))
        conn.commit()
        flash('Port forwarding rule deleted', 'success')
    conn.close()
    return redirect(url_for('port_forwarding'))
@app.route('/logs')
@login_required
def system_logs():
    conn = get_db()
    if session.get('is_admin'):
        logs = conn.execute("""
            SELECT al.*, u.username FROM activity_log al
            JOIN users u ON al.user_id = u.id
            ORDER BY al.created_at DESC LIMIT 500
        """).fetchall()
    else:
        logs = conn.execute("""
            SELECT al.*, u.username FROM activity_log al
            JOIN users u ON al.user_id = u.id
            WHERE al.user_id = ?
            ORDER BY al.created_at DESC LIMIT 500
        """, (session['user_id'],)).fetchall()
    conn.close()
    return render_template('logs.html', logs=logs, is_admin=session.get('is_admin', 0))
@app.route('/logs/clear', methods=['POST'])
@admin_required
def clear_logs():
    conn = get_db()
    conn.execute('DELETE FROM system_logs')
    conn.commit()
    conn.close()
    add_log('info', 'System logs cleared', 'system')
    flash('Logs cleared', 'success')
    return redirect(url_for('system_logs'))
@app.route('/notifications')
@login_required
def notifications():
    conn = get_db()
    logs = conn.execute("""
        SELECT al.*, u.username FROM activity_log al
        JOIN users u ON al.user_id = u.id
        WHERE al.user_id = ?
        ORDER BY al.created_at DESC LIMIT 50
    """, (session['user_id'],)).fetchall()
    conn.close()
    return render_template('notifications.html', logs=logs)
@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('users.html', users=users)
@app.route('/admin/promote/<int:user_id>', methods=['POST'])
@admin_required
def promote_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    if user['is_admin']:
        flash('User is already an admin', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    conn.execute('UPDATE users SET is_admin = 1, role = ? WHERE id = ?', ('admin', user_id))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'promote_user', 'admin', json.dumps({'user': user['username']}), request.remote_addr)
    add_log('info', f"User promoted to admin: {user['username']}", 'admin')
    flash(f"{user['username']} is now an admin", 'success')
    return redirect(url_for('admin_users'))
@app.route('/admin/demote/<int:user_id>', methods=['POST'])
@admin_required
def demote_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    if user['id'] == session['user_id']:
        flash('Cannot demote yourself', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    if user['role'] == 'owner':
        flash('Cannot demote the owner', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    conn.execute('UPDATE users SET is_admin = 0, role = ? WHERE id = ?', ('user', user_id))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'demote_user', 'admin', json.dumps({'user': user['username']}), request.remote_addr)
    add_log('info', f"Admin demoted: {user['username']}", 'admin')
    flash(f"{user['username']} is no longer an admin", 'success')
    return redirect(url_for('admin_users'))
@app.route('/admin/ban/<int:user_id>', methods=['POST'])
@admin_required
def ban_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    if user['is_admin']:
        flash('Cannot ban an admin', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    if user['id'] == session['user_id']:
        flash('Cannot ban yourself', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    conn.execute('UPDATE users SET is_banned = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'ban_user', 'admin', json.dumps({'user': user['username']}), request.remote_addr)
    add_log('warning', f"User banned: {user['username']}", 'admin')
    flash(f"{user['username']} has been banned", 'success')
    return redirect(url_for('admin_users'))
@app.route('/admin/unban/<int:user_id>', methods=['POST'])
@admin_required
def unban_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found', 'error')
        conn.close()
        return redirect(url_for('admin_users'))
    conn.execute('UPDATE users SET is_banned = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    log_activity(session['user_id'], 'unban_user', 'admin', json.dumps({'user': user['username']}), request.remote_addr)
    add_log('info', f"User unbanned: {user['username']}", 'admin')
    flash(f"{user['username']} has been unbanned", 'success')
    return redirect(url_for('admin_users'))
@app.route('/admin/all-vps')
@admin_required
def admin_all_vps():
    conn = get_db()
    all_vps = conn.execute('SELECT v.*, u.username FROM vps v JOIN users u ON v.user_id = u.id ORDER BY v.created_at DESC').fetchall()
    conn.close()
    return render_template('all_vps.html', vps_list=all_vps)
@app.route('/os-icons')
@login_required
def os_icons():
    return render_template('os_icons.html')
@app.route('/api-docs')
@login_required
@admin_required
def api_docs():
    return render_template('api_docs.html')
@app.route('/system-info')
@login_required
def system_info():
    import platform
    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    info = {'platform': platform.platform(), 'python_version': platform.python_version(), 'hostname': platform.node(), 'cpu_count': psutil.cpu_count(), 'cpu_percent': cpu_percent, 'ram_total': round(ram.total / 1073741824, 1), 'ram_used': round(ram.used / 1073741824, 1), 'ram_percent': ram.percent, 'disk_total': round(disk.total / 1073741824, 1), 'disk_used': round(disk.used / 1073741824, 1), 'disk_percent': disk.percent, 'lxd_version': lxc_get_version()}
    return render_template('system_info.html', info=info)
@app.route('/nodes')
@admin_required
def node_management():
    conn = get_db()
    nodes = conn.execute('SELECT * FROM nodes ORDER BY is_local DESC, name ASC').fetchall()
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    local_node = conn.execute('SELECT * FROM nodes WHERE is_local = 1').fetchone()
    if local_node:
        conn.execute('UPDATE nodes SET cpu_usage = ?, ram_usage = ? WHERE is_local = 1', (cpu, ram))
        total_vps = conn.execute('SELECT COUNT(*) as c FROM vps').fetchone()['c']
        conn.execute('UPDATE nodes SET vps_count = ? WHERE is_local = 1', (total_vps,))
        conn.commit()
    nodes = conn.execute('SELECT * FROM nodes ORDER BY is_local DESC, name ASC').fetchall()
    conn.close()
    return render_template('nodes.html', nodes=nodes, cpu=cpu, ram=ram)
@app.route('/nodes/add-local', methods=['POST'])
@admin_required
def add_local_node():
    conn = get_db()
    existing = conn.execute('SELECT * FROM nodes WHERE is_local = 1').fetchone()
    if existing:
        flash('Local node already exists', 'error')
        conn.close()
        return redirect(url_for('node_management'))
    import platform
    hostname = platform.node()
    conn.execute('INSERT INTO nodes (name, hostname, node_url, api_key, max_vps, is_local, status) VALUES (?, ?, ?, ?, ?, ?, ?)', ('Local', hostname, '', '', 500, 1, 'online'))
    conn.commit()
    conn.close()
    flash('Local node added', 'success')
    return redirect(url_for('node_management'))
@app.route('/nodes/add', methods=['POST'])
@admin_required
def add_node():
    name = request.form.get('name')
    hostname = request.form.get('hostname')
    node_url = request.form.get('node_url', '')
    api_key = request.form.get('api_key', '')
    max_vps = request.form.get('max_vps', 500)
    if not name or not hostname:
        flash('Name and hostname are required', 'error')
        return redirect(url_for('node_management'))
    if node_url:
        resp, code = call_node_api(node_url, api_key, '/api/health')
        if code != 200 or resp.get('error'):
            flash(f"Cannot connect to node: {resp.get('error', 'Connection failed')}", 'error')
            return redirect(url_for('node_management'))
    conn = get_db()
    conn.execute('INSERT INTO nodes (name, hostname, node_url, api_key, max_vps, is_local) VALUES (?, ?, ?, ?, ?, 0)', (name, hostname, node_url, api_key, max_vps))
    conn.commit()
    conn.close()
    flash('Node added successfully', 'success')
    return redirect(url_for('node_management'))
@app.route('/nodes/edit', methods=['POST'])
@admin_required
def edit_node():
    node_id = request.form.get('node_id')
    name = request.form.get('name')
    hostname = request.form.get('hostname')
    node_url = request.form.get('node_url', '')
    api_key = request.form.get('api_key', '')
    max_vps = request.form.get('max_vps', 500)
    if not node_id or not name or not hostname:
        flash('Name and hostname are required', 'error')
        return redirect(url_for('node_management'))
    conn = get_db()
    node = conn.execute('SELECT * FROM nodes WHERE id = ?', (node_id,)).fetchone()
    if not node:
        flash('Node not found', 'error')
        conn.close()
        return redirect(url_for('node_management'))
    conn.execute('UPDATE nodes SET name = ?, hostname = ?, node_url = ?, api_key = ?, max_vps = ? WHERE id = ?', (name, hostname, node_url, api_key, max_vps, node_id))
    conn.commit()
    conn.close()
    flash('Node updated successfully', 'success')
    return redirect(url_for('node_management'))
@app.route('/nodes/delete/<int:node_id>', methods=['POST'])
@admin_required
def delete_node(node_id):
    conn = get_db()
    node = conn.execute('SELECT * FROM nodes WHERE id = ?', (node_id,)).fetchone()
    if not node:
        flash('Node not found', 'error')
        conn.close()
        return redirect(url_for('node_management'))
    if node['is_local']:
        flash('Cannot delete local node', 'error')
        conn.close()
        return redirect(url_for('node_management'))
    vps_count = conn.execute('SELECT COUNT(*) as c FROM vps WHERE node_id = ?', (node_id,)).fetchone()['c']
    if vps_count > 0:
        flash('Node still has VPS. Delete them first.', 'error')
        conn.close()
        return redirect(url_for('node_management'))
    conn.execute('DELETE FROM nodes WHERE id = ?', (node_id,))
    conn.commit()
    conn.close()
    flash('Node deleted', 'success')
    return redirect(url_for('node_management'))
@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def panel_settings():
    conn = get_db()
    settings = get_settings()
    if request.method == 'POST':
        site_name = request.form.get('site_name', settings['site_name'])
        site_description = request.form.get('site_description', settings['site_description'])
        footer_text = request.form.get('footer_text', settings['footer_text'])
        timezone = request.form.get('timezone', settings['timezone'])
        registration_enabled = 1 if request.form.get('registration_enabled') else 0
        cpu_threshold = request.form.get('cpu_threshold', 90)
        ram_threshold = request.form.get('ram_threshold', 90)
        max_ports = request.form.get('max_ports_per_user', 20)
        rate_limit_auth = request.form.get('rate_limit_auth', 10)
        rate_limit_api = request.form.get('rate_limit_api', 60)
        rate_limit_heavy = request.form.get('rate_limit_heavy', 5)
        port_forwarding_method = request.form.get('port_forwarding_method', 'serveo')
        public_ipv4 = request.form.get('public_ipv4', '')
        default_vps_days = request.form.get('default_vps_days', 0)
        hostname_prefix = request.form.get('hostname_prefix', 'vps')
        icon_path = settings['icon_path'] if 'icon_path' in settings.keys() else ''
        if request.form.get('remove_icon'):
            if icon_path and icon_path.startswith('/static/uploads/'):
                import os
                old_file = os.path.join(app.root_path, icon_path.lstrip('/'))
                if os.path.exists(old_file):
                    try:
                        os.remove(old_file)
                    except:
                        pass
            icon_path = ''
        icon_file = request.files.get('icon_file')
        if icon_file and icon_file.filename:
            import os
            allowed_exts = {'.png', '.gif'}
            ext = os.path.splitext(icon_file.filename.lower())[1]
            if ext not in allowed_exts:
                flash('Only PNG and GIF files are allowed', 'error')
                conn.close()
                return redirect(url_for('panel_settings'))
            import uuid
            filename = f"icon_{uuid.uuid4().hex[:12]}{ext}"
            filepath = os.path.join(app.root_path, 'static', 'uploads', filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            icon_file.save(filepath)
            if icon_path and icon_path.startswith('/static/uploads/'):
                old_file = os.path.join(app.root_path, icon_path.lstrip('/'))
                if os.path.exists(old_file):
                    try:
                        os.remove(old_file)
                    except:
                        pass
            icon_path = f"/static/uploads/{filename}"
        conn.execute("""UPDATE settings SET site_name = ?, site_description = ?, footer_text = ?,
                       timezone = ?, registration_enabled = ?, cpu_threshold = ?, ram_threshold = ?,
                       max_ports_per_user = ?, icon_path = ?,
                       rate_limit_auth = ?, rate_limit_api = ?, rate_limit_heavy = ?,
                       port_forwarding_method = ?, public_ipv4 = ?, default_vps_days = ?,
                       hostname_prefix = ? WHERE id = ?""", (site_name, site_description, footer_text, timezone, registration_enabled, cpu_threshold, ram_threshold, max_ports, icon_path, rate_limit_auth, rate_limit_api, rate_limit_heavy, port_forwarding_method, public_ipv4, default_vps_days, hostname_prefix, settings['id']))
        conn.commit()
        add_log('info', 'Panel settings updated', 'settings')
        flash('Settings saved successfully', 'success')
    conn.close()
    return render_template('settings.html', settings=get_settings(), timezones=sorted(zoneinfo.available_timezones()))
@app.route('/api/favicon')
def get_favicon():
    settings = get_settings()
    icon_path = settings['icon_path'] if 'icon_path' in settings.keys() else ''
    if icon_path:
        return jsonify({'icon': icon_path})
    return jsonify({'icon': ''})
@app.route('/api/system-stats')
@login_required
@limiter.limit(lambda: get_rate_limit('api'))
def system_stats():
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return jsonify({'cpu_percent': cpu, 'ram_percent': ram.percent, 'ram_used': round(ram.used / 1073741824, 1), 'ram_total': round(ram.total / 1073741824, 1), 'disk_percent': disk.percent, 'disk_used': round(disk.used / 1073741824, 1), 'disk_total': round(disk.total / 1073741824, 1)})
@app.route('/api/vps/<int:vps_id>/stats')
@login_required
@limiter.limit(lambda: get_rate_limit('api'))
def vps_stats(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps:
        return (jsonify({'error': 'VPS not found'}), 404)
    conn = get_db()
    is_shared = conn.execute('SELECT 1 FROM vps_shares WHERE vps_id = ? AND shared_with = ?', (vps_id, session['user_id'])).fetchone()
    conn.close()
    if vps['user_id'] != session['user_id'] and not is_shared and not session.get('is_admin'):
        return (jsonify({'error': 'VPS not found'}), 404)
    if node and not node['is_local']:
        resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/stats")
        if code == 200:
            return jsonify({'cpu_percent': resp.get('cpu_percent', 0), 'memory_percent': resp.get('memory_percent', 0), 'memory_used': round(resp.get('memory_used', 0) / 1048576, 1), 'memory_total': round(resp.get('memory_limit', 0) / 1048576, 1), 'net_rx': resp.get('net_rx', 0), 'net_tx': resp.get('net_tx', 0), 'pids': resp.get('pids', 0)})
        return (jsonify({'error': resp.get('error', 'Failed to get stats')}), 500)
    try:
        stats = lxc_get_stats(vps['container_id'])
        return jsonify({'cpu_percent': stats.get('cpu_percent', 0), 'memory_percent': stats.get('memory_percent', 0), 'memory_used': round(stats.get('memory_used', 0) / 1048576, 1), 'memory_total': round(stats.get('memory_limit', 0) / 1048576, 1), 'net_rx': stats.get('net_rx', 0), 'net_tx': stats.get('net_tx', 0), 'pids': stats.get('pids', 0)})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
def admin_api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return (jsonify({'error': 'Missing API key'}), 401)
        conn = get_db()
        admin = conn.execute('SELECT * FROM users WHERE is_admin = 1 AND api_key = ?', (api_key,)).fetchone()
        conn.close()
        if not admin:
            return (jsonify({'error': 'Invalid API key'}), 401)
        return f(*args, **kwargs)
    return decorated
@app.route('/local/api/health')
@admin_api_required
def local_api_health():
    try:
        lxc_is_available()
        return jsonify({'status': 'ok', 'docker': 'running'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/info')
@admin_api_required
def local_api_info():
    import platform
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return jsonify({'cpu_percent': cpu, 'ram_used': round(ram.used / 1073741824, 1), 'ram_total': round(ram.total / 1073741824, 1), 'disk_used': round(disk.used / 1073741824, 1), 'disk_total': round(disk.total / 1073741824, 1), 'lxd_version': lxc_get_version(), 'hostname': platform.node(), 'platform': platform.platform()})
@app.route('/local/api/containers')
@admin_api_required
def local_api_containers():
    containers = lxc_list_all()
    result = []
    for c in containers:
        result.append({'id': c.id, 'name': c.name, 'status': c.status, 'image': c.image.tags[0] if c.image.tags else str(c.image.id)[:12]})
    return jsonify({'containers': result})
@app.route('/local/api/container/create', methods=['POST'])
@admin_api_required
def local_api_container_create():
    data = request.get_json()
    name = data.get('name', '')
    image = data.get('image', 'ubuntu:22.04')
    ram = data.get('ram', '2GB')
    cpu = data.get('cpu', '1 vCPU')
    disk = data.get('disk', '20GB')
    if not name:
        return (jsonify({'error': 'Name required'}), 400)
    try:
        container_id = lxc_create(name, image, ram, cpu, disk)
        return jsonify({'status': 'ok', 'container_id': container_id, 'name': name})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/start', methods=['POST'])
@admin_api_required
def local_api_container_start(container_id):
    try:
        lxc_start(container_id)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/stop', methods=['POST'])
@admin_api_required
def local_api_container_stop(container_id):
    try:
        lxc_stop(container_id)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/restart', methods=['POST'])
@admin_api_required
def local_api_container_restart(container_id):
    try:
        lxc_restart(container_id)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/delete', methods=['POST'])
@admin_api_required
def local_api_container_delete(container_id):
    try:
        lxc_stop(container_id)
        lxc_destroy(container_id)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/update', methods=['POST'])
@admin_api_required
def local_api_container_update(container_id):
    try:
        data = request.get_json() or {}
        ram = data.get('ram', '')
        cpu = data.get('cpu', '')
        disk = data.get('disk', '')
        import subprocess
        if ram:
            subprocess.run(['incus', 'config', 'set', container_id, 'limits.memory=' + ram], timeout=30, capture_output=True)
        if cpu:
            subprocess.run(['incus', 'config', 'set', container_id, 'limits.cpu=' + cpu], timeout=30, capture_output=True)
        if disk:
            subprocess.run(['incus', 'config', 'device', 'set', container_id, 'root', 'size=' + disk], timeout=30, capture_output=True)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/status')
@admin_api_required
def local_api_container_status(container_id):
    try:
        st = lxc_status(container_id)
        return jsonify({'state': st, 'id': container_id, 'name': container_id})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/stats')
@admin_api_required
def local_api_container_stats(container_id):
    try:
        stats = lxc_get_stats(container_id)
        return jsonify(stats)
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/regen-ssh', methods=['POST'])
@admin_api_required
def local_api_container_regen_ssh(container_id):
    try:
        lxc_restart(container_id)
        link = None
        import time as _time
        for _ in range(20):
            _time.sleep(1)
            exit_code, output = lxc_attach(container_id, 'cat /var/log/sshx.log 2>/dev/null || journalctl -u sshx --no-pager -n 20 2>/dev/null || ps aux | grep sshx')
            if isinstance(output, bytes):
                output = output.decode('utf-8', errors='ignore')
            cleaned = strip_ansi(str(output))
            for line in cleaned.splitlines():
                if 'sshx.io' in line:
                    match = re.search('https://sshx\\.io/s/[a-zA-Z0-9#]+', line)
                    if match:
                        link = match.group(0)
                        break
            if link:
                break
        return jsonify({'status': 'ok', 'link': link or ''})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/exec', methods=['POST'])
@admin_api_required
def local_api_container_exec(container_id):
    data = request.get_json()
    command = data.get('command', 'echo hello')
    try:
        exit_code, output = lxc_attach(container_id, command)
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='ignore')
        return jsonify({'output': str(output), 'exit_code': exit_code})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/ip')
@admin_api_required
def local_api_container_ip(container_id):
    try:
        ip = lxc_get_ip(container_id)
        return jsonify({'ip': ip or ''})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/vps/<int:vps_id>/set-expiry', methods=['POST'])
@admin_api_required
def local_api_vps_set_expiry(vps_id):
    try:
        data = request.get_json() or {}
        expires_at = data.get('expires_at', '')
        conn = get_db()
        vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
        if not vps:
            conn.close()
            return (jsonify({'error': 'VPS not found'}), 404)
        if expires_at:
            conn.execute('UPDATE vps SET expires_at = ? WHERE id = ?', (expires_at, vps_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'expires_at': expires_at})
        conn.execute('UPDATE vps SET expires_at = NULL WHERE id = ?', (vps_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'expires_at': None})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/socat/start', methods=['POST'])
@admin_api_required
def local_api_socat_start():
    data = request.get_json()
    container_ip = data.get('container_ip')
    local_port = data.get('local_port')
    external_port = data.get('external_port')
    if not all([container_ip, local_port, external_port]):
        return (jsonify({'error': 'Missing parameters'}), 400)
    try:
        import subprocess
        proc = subprocess.Popen(['socat', f"TCP-LISTEN:{external_port},bind=0.0.0.0,reuseaddr,fork", f"TCP:{container_ip}:{local_port}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({'status': 'ok', 'socat_pid': proc.pid})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/socat/stop', methods=['POST'])
@admin_api_required
def local_api_socat_stop():
    data = request.get_json()
    socat_pid = data.get('socat_pid')
    if not socat_pid:
        return (jsonify({'error': 'Missing socat_pid'}), 400)
    try:
        os.kill(int(socat_pid), 9)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/image/<image_tag>/export')
@admin_api_required
def local_api_image_export(image_tag):
    try:
        return (jsonify({'error': 'LXD snapshot export not supported yet'}), 501)
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/image/import', methods=['POST'])
@admin_api_required
def local_api_image_import():
    try:
        if 'file' not in request.files:
            return (jsonify({'error': 'No file uploaded'}), 400)
        f = request.files['file']
        image_tag = request.form.get('tag', f"imported-{int(time.time())}")
        return jsonify({'status': 'ok', 'image_tag': image_tag})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/files', methods=['POST'])
@admin_api_required
def local_api_files(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '/')
        exit_code, output = lxc_attach(container_id, f"ls -la {shlex.quote(path)}")
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='ignore')
        files = []
        if exit_code == 0:
            for line in output.strip().split('\n')[1:]:
                parts = line.split(None, 8)
                if len(parts) >= 9:
                    files.append({'name': parts[8], 'is_dir': parts[0].startswith('d'), 'size': parts[4], 'permissions': parts[0]})
        return jsonify({'files': files})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/file_read', methods=['POST'])
@admin_api_required
def local_api_file_read(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '')
        exit_code, output = lxc_attach(container_id, f"cat {shlex.quote(path)}")
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='replace')
        return jsonify({'content': output, 'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/file_write', methods=['POST'])
@admin_api_required
def local_api_file_write(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '')
        content = data.get('content', '')
        safe_path = shlex.quote(path)
        cmd = f"cat > {safe_path} << 'VPSMANAGER_EOF'\n{content}\nVPSMANAGER_EOF"
        exit_code, output = lxc_attach(container_id, cmd)
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/files/delete', methods=['POST'])
@admin_api_required
def local_api_file_delete(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '')
        exit_code, output = lxc_attach(container_id, f"rm -rf {shlex.quote(path)}")
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/files/mkdir', methods=['POST'])
@admin_api_required
def local_api_file_mkdir(container_id):
    try:
        data = request.get_json()
        path = data.get('path', '')
        exit_code, output = lxc_attach(container_id, f"mkdir -p {shlex.quote(path)}")
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/top')
@admin_api_required
def local_api_top(container_id):
    try:
        exit_code, output = lxc_attach(container_id, 'ps aux --sort=-%cpu')
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='ignore')
        processes = []
        if exit_code == 0:
            for line in output.strip().split('\n')[1:]:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({'pid': parts[1], 'user': parts[0], 'cpu': parts[2], 'mem': parts[3], 'command': parts[10]})
        return jsonify({'processes': processes})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
@app.route('/local/api/container/<container_id>/processes/kill', methods=['POST'])
@admin_api_required
def local_api_kill_process(container_id):
    try:
        data = request.get_json()
        pid = data.get('pid', '')
        exit_code, output = lxc_attach(container_id, f"kill -9 {pid}")
        return jsonify({'success': exit_code == 0})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
def check_expirations():
    import threading
    while True:
        time.sleep(60)
        try:
            from datetime import timedelta
            with app.app_context():
                settings = get_settings()
                tz_key = settings['timezone'] if 'timezone' in settings.keys() else 'UTC'
                try:
                    tz = zoneinfo.ZoneInfo(tz_key)
                except:
                    tz = zoneinfo.ZoneInfo('UTC')
                conn = get_db()
                now = datetime.now(tz)
                print(f"[EXPIRATION CHECK] Running at {now.strftime('%Y-%m-%d %H:%M:%S')} (tz={tz_key})")
                expired = conn.execute('SELECT * FROM vps WHERE expires_at IS NOT NULL').fetchall()
                print(f"[EXPIRATION CHECK] Found {len(expired)} VPS with expires_at set")
                for v in expired:
                    try:
                        expires = datetime.strptime(v['expires_at'], '%Y-%m-%dT%H:%M').replace(tzinfo=tz)
                    except:
                        try:
                            expires = datetime.strptime(v['expires_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)
                        except:
                            print(f"[EXPIRATION CHECK] Skipping VPS {v['id']} ({v['container_name']}) — bad format '{v['expires_at']}'")
                            continue
                    grace_end = expires + timedelta(hours=24)
                    print(f"[EXPIRATION CHECK] VPS {v['id']} ({v['container_name']}): expires={expires}, grace_end={grace_end}, now={now}, delete={now >= grace_end}")
                    if now >= grace_end:
                        print(f"[EXPIRATION CHECK] DELETING VPS {v['id']} ({v['container_name']})")
                        node = conn.execute('SELECT * FROM nodes WHERE id = ?', (v['node_id'],)).fetchone() if v['node_id'] else None
                        if not node:
                            node = conn.execute('SELECT * FROM nodes WHERE is_local = 1 LIMIT 1').fetchone()
                        if node and node['is_local']:
                            try:
                                lxc_stop(v['container_id'])
                            except:
                                pass
                            try:
                                lxc_destroy(v['container_id'])
                            except:
                                pass
                        elif node:
                            try:
                                call_node_api(node['node_url'], node['api_key'], f"/api/container/{v['container_id']}/delete", method='POST')
                            except:
                                pass
                        conn.execute('DELETE FROM port_forwards WHERE vps_id = ?', (v['id'],))
                        conn.execute('DELETE FROM backups WHERE vps_id = ?', (v['id'],))
                        conn.execute('DELETE FROM vps WHERE id = ?', (v['id'],))
                        conn.execute('INSERT INTO system_logs (level, message, source) VALUES (?, ?, ?)', ('warning', f"VPS deleted after expiration + 24h: {v['container_name']}", 'vps'))
                        print(f"[EXPIRATION CHECK] Deleted VPS {v['id']} ({v['container_name']}) from DB")
                conn.commit()
                conn.close()
                print(f"[EXPIRATION CHECK] Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"[EXPIRATION CHECK] Error: {e}")
def _get_snapshots(container_id, node):
    snapshots = []
    try:
        if node and not node['is_local']:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{container_id}/snapshots")
            if code == 200:
                snapshots = resp.get('snapshots', [])
        else:
            code, resp = _lxd_request('GET', f"/1.0/instances/{container_id}/snapshots?recursion=1")
            if code == 200:
                for s in resp.get('metadata', []):
                    snapshots.append({'name': s.get('name', ''), 'created_at': s.get('created_at', ''), 'stateful': s.get('stateful', False)})
    except:
        pass
    return snapshots
@app.route('/vps/<int:vps_id>/backup', methods=['POST'])
@login_required
def create_backup(vps_id):
    vps, node = get_node_for_vps(vps_id)
    if not vps or vps['user_id'] != session['user_id']:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    if vps['max_backups'] == 0:
        flash('Backups are disabled for this VPS', 'error')
        return redirect(url_for('vps_detail', vps_id=vps_id))
    if vps['max_backups'] > 0:
        current = _get_snapshots(vps['container_id'], node)
        if len(current) >= vps['max_backups']:
            flash(f"Backup limit reached ({vps['max_backups']}). Delete an existing snapshot first.", 'error')
            return redirect(url_for('vps_detail', vps_id=vps_id))
    snap_name = request.form.get('name', f"snap-{int(time.time())}")
    try:
        if node['is_local']:
            code, resp = _lxd_request('POST', f"/1.0/instances/{vps['container_id']}/snapshots", data={'name': snap_name, 'stateful': False})
            if code not in (200, 201, 202):
                raise Exception(resp.get('error', f"Snapshot failed: {code}"))
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/backup", method='POST', data={'name': snap_name})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        log_activity(session['user_id'], 'create_backup', 'vps', json.dumps({'vps': vps['container_name'], 'backup': snap_name}), request.remote_addr)
        flash(f"Backup created: {snap_name}", 'success')
    except Exception as e:
        flash(f"Error creating backup: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/backup/<snap_name>/restore', methods=['POST'])
@login_required
def restore_backup(vps_id, snap_name):
    vps, node = get_node_for_vps(vps_id)
    if not vps or vps['user_id'] != session['user_id']:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    container_id = vps['container_id']
    container_name = vps['container_name']
    try:
        if node['is_local']:
            code, resp = _lxd_request('PUT', f"/1.0/instances/{container_id}", data={'restore': snap_name})
            if code not in (200, 202):
                raise Exception(resp.get('error', f"Restore failed: {code}"))
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{container_id}/restore", method='POST', data={'image': snap_name})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET ssh_command = NULL, ssh_password = NULL WHERE id = ?', (vps_id,))
        conn.commit()
        conn.close()
        log_activity(session['user_id'], 'restore_backup', 'vps', json.dumps({'vps': container_name, 'backup': snap_name}), request.remote_addr)
        flash(f"VPS restored from: {snap_name}. SSH credentials cleared — regenerate them.", 'success')
    except Exception as e:
        flash(f"Error restoring backup: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/vps/<int:vps_id>/backup/<snap_name>/delete', methods=['POST'])
@login_required
def delete_backup(vps_id, snap_name):
    vps, node = get_node_for_vps(vps_id)
    if not vps or vps['user_id'] != session['user_id']:
        flash('VPS not found', 'error')
        return redirect(url_for('dashboard'))
    try:
        if node['is_local']:
            code, resp = _lxd_request('DELETE', f"/1.0/instances/{vps['container_id']}/snapshots/{snap_name}")
            if code not in (200, 204):
                raise Exception(resp.get('error', f"Delete failed: {code}"))
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps['container_id']}/snapshot/{snap_name}", method='DELETE')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        flash(f"Backup deleted: {snap_name}", 'success')
    except Exception as e:
        flash(f"Error deleting backup: {str(e)}", 'error')
    return redirect(url_for('vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/backup', methods=['POST'])
@admin_required
def admin_create_backup(vps_id):
    vps_data, node = get_node_for_vps(vps_id)
    if not vps_data:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_all_vps'))
    if vps_data['max_backups'] == 0:
        flash('Backups are disabled for this VPS', 'error')
        return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    if vps_data['max_backups'] > 0:
        current = _get_snapshots(vps_data['container_id'], node)
        if len(current) >= vps_data['max_backups']:
            flash(f"Backup limit reached ({vps_data['max_backups']}). Delete an existing snapshot first.", 'error')
            return redirect(url_for('admin_vps_detail', vps_id=vps_id))
    snap_name = request.form.get('name', f"snap-{int(time.time())}")
    try:
        if node['is_local']:
            code, resp = _lxd_request('POST', f"/1.0/instances/{vps_data['container_id']}/snapshots", data={'name': snap_name, 'stateful': False})
            if code not in (200, 201, 202):
                raise Exception(resp.get('error', f"Snapshot failed: {code}"))
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps_data['container_id']}/backup", method='POST', data={'name': snap_name})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        flash(f"Backup created: {snap_name}", 'success')
    except Exception as e:
        flash(f"Error creating backup: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/backup/<snap_name>/restore', methods=['POST'])
@admin_required
def admin_restore_backup(vps_id, snap_name):
    vps_data, node = get_node_for_vps(vps_id)
    if not vps_data:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_all_vps'))
    container_id = vps_data['container_id']
    container_name = vps_data['container_name']
    try:
        if node['is_local']:
            code, resp = _lxd_request('PUT', f"/1.0/instances/{container_id}", data={'restore': snap_name})
            if code not in (200, 202):
                raise Exception(resp.get('error', f"Restore failed: {code}"))
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{container_id}/restore", method='POST', data={'image': snap_name})
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        conn = get_db()
        conn.execute('UPDATE vps SET ssh_command = NULL, ssh_password = NULL WHERE id = ?', (vps_id,))
        conn.commit()
        conn.close()
        flash(f"VPS restored from: {snap_name}. SSH credentials cleared — regenerate them.", 'success')
    except Exception as e:
        flash(f"Error restoring backup: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/backup/<snap_name>/delete', methods=['POST'])
@admin_required
def admin_delete_backup(vps_id, snap_name):
    vps_data, node = get_node_for_vps(vps_id)
    if not vps_data:
        flash('VPS not found', 'error')
        return redirect(url_for('admin_all_vps'))
    try:
        if node['is_local']:
            code, resp = _lxd_request('DELETE', f"/1.0/instances/{vps_data['container_id']}/snapshots/{snap_name}")
            if code not in (200, 204):
                raise Exception(resp.get('error', f"Delete failed: {code}"))
        else:
            resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{vps_data['container_id']}/snapshot/{snap_name}", method='DELETE')
            if code != 200 or resp.get('error'):
                raise Exception(resp.get('error', 'Failed on remote node'))
        flash(f"Backup deleted: {snap_name}", 'success')
    except Exception as e:
        flash(f"Error deleting backup: {str(e)}", 'error')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/set-expiry', methods=['POST'])
@admin_required
def set_vps_expiry(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        flash('VPS not found', 'error')
        conn.close()
        return redirect(url_for('admin_all_vps'))
    expires_at = request.form.get('expires_at', '')
    if expires_at:
        conn.execute('UPDATE vps SET expires_at = ? WHERE id = ?', (expires_at, vps_id))
        flash(f"Expiration set to {expires_at}", 'success')
    else:
        conn.execute('UPDATE vps SET expires_at = NULL WHERE id = ?', (vps_id,))
        flash('Expiration cleared', 'success')
    conn.commit()
    conn.close()
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/vps/<int:vps_id>/clear-expiry', methods=['POST'])
@admin_required
def clear_vps_expiry(vps_id):
    conn = get_db()
    conn.execute('UPDATE vps SET expires_at = NULL WHERE id = ?', (vps_id,))
    conn.commit()
    conn.close()
    flash('Expiration cleared', 'success')
    return redirect(url_for('admin_vps_detail', vps_id=vps_id))
@app.route('/admin/usage')
@admin_required
def admin_usage():
    conn = get_db()
    usage = conn.execute("""
        SELECT u.id, u.username, u.created_at as user_created,
            COUNT(v.id) as vps_count,
            SUM(CASE WHEN v.status = 'running' THEN 1 ELSE 0 END) as running_count,
            SUM(CASE WHEN v.status != 'running' THEN 1 ELSE 0 END) as stopped_count,
            COALESCE(SUM(CAST(REPLACE(REPLACE(v.ram, 'GB', ''), 'MB', '') AS REAL)), 0) as total_ram,
            COALESCE(SUM(CAST(REPLACE(v.cpu, ' vCPU', '') AS INTEGER)), 0) as total_cpu,
            COALESCE(SUM(CAST(REPLACE(v.disk, 'GB', '') AS REAL)), 0) as total_disk
        FROM users u
        LEFT JOIN vps v ON u.id = v.user_id
        GROUP BY u.id
        ORDER BY total_ram DESC
    """).fetchall()
    user_live_stats = {}
    for u in usage:
        uid = u['id']
        user_vps = conn.execute('SELECT id, container_id, node_id, status FROM vps WHERE user_id = ?', (uid,)).fetchall()
        live_cpu = 0.0
        live_ram_mb = 0
        live_disk_gb = 0.0
        for v in user_vps:
            if v['status'] != 'running' or not v['container_id']:
                pass
            else:
                try:
                    vps_data, node = get_node_for_vps(v['id'])
                    if node['is_local']:
                        stats = lxc_get_stats(v['container_id'])
                        live_cpu += stats.get('cpu_percent', 0.0)
                        live_ram_mb += stats.get('memory_used', 0) // 1048576
                    else:
                        resp, code = call_node_api(node['node_url'], node['api_key'], f"/api/container/{v['container_id']}/stats")
                        if code == 200 and not resp.get('error'):
                            live_cpu += resp.get('cpu_percent', 0)
                            live_ram_mb += resp.get('memory_used', 0) // 1048576
                except:
                    continue
        user_live_stats[uid] = {'live_cpu': round(live_cpu, 1), 'live_ram_mb': live_ram_mb}
    totals = conn.execute("""
        SELECT
            COUNT(*) as total_vps,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
            COALESCE(SUM(CAST(REPLACE(REPLACE(ram, 'GB', ''), 'MB', '') AS REAL)), 0) as total_ram,
            COALESCE(SUM(CAST(REPLACE(cpu, ' vCPU', '') AS INTEGER)), 0) as total_cpu,
            COALESCE(SUM(CAST(REPLACE(disk, 'GB', '') AS REAL)), 0) as total_disk
        FROM vps
    """).fetchone()
    conn.close()
    return render_template('usage.html', usage=usage, totals=totals, live_stats=user_live_stats)
@app.route('/admin/expiring')
@admin_required
def admin_expiring():
    conn = get_db()
    expiring = conn.execute("""
        SELECT v.*, u.username,
            CAST(julianday(v.expires_at) - julianday('now') AS INTEGER) as days_left
        FROM vps v
        JOIN users u ON v.user_id = u.id
        WHERE v.expires_at IS NOT NULL
        ORDER BY v.expires_at ASC
    """).fetchall()
    conn.close()
    return render_template('expiring_vps.html', vps_list=expiring)
if __name__ == '__main__':
    init_db()
    migrate_nodes()
    conn = get_db()
    admin = conn.execute('SELECT * FROM users WHERE is_admin = 1').fetchone()
    if not admin:
        api_key = generate_api_key()
        conn.execute('INSERT INTO users (username, email, password, is_admin, api_key) VALUES (?, ?, ?, ?, ?)', ('admin', 'admin@vps.com', hash_password('admin123'), 1, api_key))
        conn.commit()
        print('Default admin created: admin / admin123')
    conn.close()
    import threading
    t = threading.Thread(target=check_expirations, daemon=True)
    t.start()
    import time as _time
    def schedule_loop():
        last_minute = None
        while True:
            now = datetime.now()
            current_minute = now.strftime('%H:%M')
            if current_minute != last_minute:
                check_schedules()
                last_minute = current_minute
            _time.sleep(30)
    st = threading.Thread(target=schedule_loop, daemon=True)
    st.start()
    app.run(host='0.0.0.0', port=5000, debug=True)
