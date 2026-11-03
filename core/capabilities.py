from __future__ import annotations
import os, platform, shutil, subprocess
import psutil

def cmd_version(cmd):
    path = shutil.which(cmd)
    if not path: return None
    try:
        p = subprocess.run([cmd,"--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
        return (p.stdout or "").strip().splitlines()[0][:180]
    except Exception: return None

def has_cmd(cmd): return shutil.which(cmd) is not None

def kvm_status():
    dev = os.path.exists('/dev/kvm')
    if has_cmd('kvm-ok'):
        try:
            p = subprocess.run(['kvm-ok'], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
            return {'device': dev, 'ok': p.returncode == 0, 'message': (p.stdout or '').strip()[:500]}
        except Exception as e:
            return {'device':dev,'ok':dev,'message':str(e)}
    return {'device':dev,'ok':dev,'message':'/dev/kvm present' if dev else 'kvm-ok not installed'}

def snapshot():
    vm = psutil.virtual_memory(); disk = psutil.disk_usage('/')
    return {
      'hostname': platform.node(), 'cpu_count': psutil.cpu_count(logical=True),
      'cpu_physical': psutil.cpu_count(logical=False), 'cpu_percent': psutil.cpu_percent(interval=0.1),
      'memory_total_mb': round(vm.total/1024/1024), 'memory_used_mb': round(vm.used/1024/1024), 'memory_available_mb': round(vm.available/1024/1024),
      'disk_total_gb': round(disk.total/1024/1024/1024,1), 'disk_used_gb': round(disk.used/1024/1024/1024,1), 'disk_free_gb': round(disk.free/1024/1024/1024,1),
      'incus': cmd_version('incus'), 'lxd': cmd_version('lxd'), 'qemu': cmd_version('qemu-system-x86_64') or cmd_version('qemu-system-x86_64'),
      'libvirtd': has_cmd('virsh') or has_cmd('libvirtd'), 'kvm': kvm_status(),
    }
