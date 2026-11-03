from __future__ import annotations
import shutil
from .engine import run, EngineError

def open_sshx(instance_name: str):
    # This is a bridge helper only. The guest remains managed by Incus.
    if not shutil.which('sshx'):
        return {'ok':False,'message':'sshx command is not installed on the node','install':'curl -sSf https://sshx.io/get | sh'}
    try:
        # sshx can run a local shell; the actual command is isolated to this instance.
        p = __import__('subprocess').Popen(['sshx','sh','-lc',f'exec incus exec {instance_name} -- bash -l'], stdout=__import__('subprocess').PIPE, stderr=__import__('subprocess').STDOUT, text=True)
        # Give the client a short window for its URL; never block the web request.
        import time, re
        deadline=time.time()+6; buf=''
        while time.time()<deadline:
            line=p.stdout.readline() if p.stdout else ''
            if line:
                buf += line
                m=re.search(r'https?://\S+',line)
                if m: return {'ok':True,'url':m.group(0),'raw':buf[-2000:]}
            time.sleep(.1)
        return {'ok':False,'message':'SSHX started but did not return a URL yet','raw':buf[-2000:]}
    except Exception as exc:
        raise EngineError(str(exc)) from exc
