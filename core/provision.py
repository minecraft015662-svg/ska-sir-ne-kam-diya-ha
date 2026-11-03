from __future__ import annotations
import json, time
from . import db
from .engine import create_instance, install_guest_support, instance_status, action, remove, EngineError
from .os_profiles import get_profile
from .config import AUTO_UPDATE


def run_job(job_id):
    job=db.get_job(job_id)
    if not job: return
    vps=db.get_vps(job['vps_id']) if job['vps_id'] else None
    if not vps: db.update_job(job_id,status='error',progress=100,message='VPS record not found'); return
    attempts=job['attempts']+1; db.update_job(job_id,status='running',attempts=attempts)
    try:
        profile=get_profile(vps['os_slug'])
        db.update_job(job_id,progress=5,message='Checking virtualization backend',details={'step':'capabilities'})
        if vps['engine']=='vm':
            from .capabilities import kvm_status
            ks=kvm_status()
            if not ks['ok']:
                raise EngineError('KVM acceleration is not available on this node; choose container or enable hardware virtualization.')
        db.update_job(job_id,progress=15,message=f'Creating {profile.label}',details={'step':'create','engine':vps['engine']})
        create_instance(vps['name'], vps['os_slug'], vps['engine'], vps['vcpus'], vps['memory_mb'], vps['disk_gb'])
        db.update_job(job_id,progress=45,message='Waiting for guest agent / shell',details={'step':'ready'})
        ip=instance_status(vps['name']).get('ip')
        db.update_job(job_id,progress=55,message='Installing guest packages and SSH',details={'step':'guest-prep','ip':ip})
        install_guest_support(vps['name'], profile.family, auto_update=AUTO_UPDATE)
        db.update_vps(vps['id'], state='running', ip_address=instance_status(vps['name']).get('ip'))
        db.update_job(job_id,progress=90,message='Enabling 24/7 desired state',details={'step':'complete'})
        db.update_job(job_id,status='done',progress=100,message='VPS ready',details={'ip':db.get_vps(vps['id'])['ip_address'],'os':profile.label})
    except Exception as exc:
        db.update_vps(vps['id'], state='error')
        db.update_job(job_id,status='error',progress=100,message=str(exc),details={'attempt':attempts})

def reconcile_running():
    # Called by watchdog. Start managed instances whose desired state is running.
    for v in db.list_all_vps():
        if v['desired_state']!='running' or v['state'] not in ('running','stopped'): continue
        try:
            st=instance_status(v['name'])
            new_state='running' if st['state']=='running' else 'stopped' if st['state']=='stopped' else 'error'
            if new_state=='stopped':
                action(v['name'],'start'); new_state='running'
            db.update_vps(v['id'],state=new_state,ip_address=instance_status(v['name']).get('ip'))
        except Exception:
            db.update_vps(v['id'],state='offline')
