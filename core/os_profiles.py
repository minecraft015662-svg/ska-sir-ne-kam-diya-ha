from dataclasses import dataclass

@dataclass(frozen=True)
class OSProfile:
    slug: str
    label: str
    image: str
    family: str
    container: bool = True
    vm: bool = True

OS_PROFILES = [
    OSProfile("ubuntu-22.04", "Ubuntu 22.04 LTS", "images:ubuntu/22.04", "debian"),
    OSProfile("ubuntu-24.04", "Ubuntu 24.04 LTS", "images:ubuntu/24.04", "debian"),
    OSProfile("ubuntu-26.04", "Ubuntu 26.04", "images:ubuntu/26.04", "debian"),
    OSProfile("debian-11", "Debian 11", "images:debian/11", "debian"),
    OSProfile("debian-12", "Debian 12", "images:debian/12", "debian"),
    OSProfile("debian-13", "Debian 13", "images:debian/13", "debian"),
    OSProfile("almalinux-9", "AlmaLinux 9", "images:almalinux/9", "rhel"),
    OSProfile("rockylinux-9", "Rocky Linux 9", "images:rockylinux/9", "rhel"),
    OSProfile("fedora-42", "Fedora 42", "images:fedora/42", "rhel"),
    OSProfile("alpine-3.20", "Alpine 3.20", "images:alpine/3.20", "alpine"),
    OSProfile("alpine-3.21", "Alpine 3.21", "images:alpine/3.21", "alpine"),
    OSProfile("alpine-3.22", "Alpine 3.22", "images:alpine/3.22", "alpine"),
    OSProfile("archlinux", "Arch Linux (current)", "images:archlinux/current", "arch"),
]

BY_SLUG = {p.slug: p for p in OS_PROFILES}

def get_profile(slug: str) -> OSProfile:
    try:
        return BY_SLUG[slug]
    except KeyError as exc:
        raise ValueError(f"Unsupported OS profile: {slug}") from exc
