from __future__ import annotations
import re, secrets
from pathlib import Path
from .engine import guest_file, guest_exec, EngineError
from .os_profiles import get_profile

SCRIPT=Path(__file__).resolve().parent.parent/'scripts'/'install_pterodactyl.sh'

def install_pterodactyl(instance_name: str, os_slug: str, domain: str, email: str):
    profile=get_profile(os_slug)
    if profile.family!='debian':
        raise EngineError('Pterodactyl helper currently targets Debian/Ubuntu guests only.')
    if not re.fullmatch(r"[A-Za-z0-9.-]{3,253}",domain) or '.' not in domain:
        raise ValueError('Invalid domain')
    guest_file(instance_name,'/root/omega-install-pterodactyl.sh',SCRIPT.read_text(encoding='utf-8'),'0700')
    cmd=f"DOMAIN={__import__('shlex').quote(domain)} EMAIL={__import__('shlex').quote(email)} bash /root/omega-install-pterodactyl.sh"
    return guest_exec(instance_name,cmd,timeout=1200)
