"""Instance backends for the three Proxmox-style VPS types.

* ``lxc``    – system container (Incus/LXD), nesting is ``security.nesting``.
* ``kvm``    – hardware accelerated virtual machine (Incus ``--vm``, needs /dev/kvm).
* ``nonkvm`` – software emulated QEMU (TCG) virtual machine for hosts without
  hardware virtualisation. Managed by ``scripts/omega-nonkvm.sh``.

Everything is name based, so the panel's existing start/stop/destroy helpers keep
working for containers and Incus VMs. Nesting is applied for all three types.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NONKVM_SCRIPT = BASE_DIR / "scripts" / "omega-nonkvm.sh"

TYPES: dict[str, dict] = {
    "lxc": {
        "label": "LXC container",
        "accel": "container",
        "description": "Lightweight system container. Fastest, shares the host kernel.",
        "nesting_hint": "Allows Docker/podman (nested containers) inside the VPS.",
    },
    "kvm": {
        "label": "KVM virtual machine",
        "accel": "kvm",
        "description": "Full hardware-accelerated VM (QEMU/KVM). Requires /dev/kvm.",
        "nesting_hint": "Exposes VT-x/AMD-V to the guest so it can run its own VMs.",
    },
    "nonkvm": {
        "label": "Non-KVM VM (QEMU TCG)",
        "accel": "tcg",
        "description": "Software-emulated VM for hosts without KVM. Slower, but a real VM.",
        "nesting_hint": "Emulates VMX/SVM where the QEMU build supports it (best effort).",
    },
}

DEFAULT_TYPE = "lxc"


class VpsTypeError(RuntimeError):
    pass


def normalise_type(vps_type: str | None) -> str:
    value = str(vps_type or "").strip().lower()
    if value in {"vm", "virtual-machine", "virtualmachine", "qemu", "kvm-vm"}:
        return "kvm"
    if value in {"non-kvm", "non_kvm", "tcg", "emulated"}:
        return "nonkvm"
    if value in {"container", "ct", "incus", "lxd"}:
        return "lxc"
    return value if value in TYPES else DEFAULT_TYPE


def type_meta(vps_type: str | None) -> dict:
    return TYPES[normalise_type(vps_type)]


def cli() -> str | None:
    return shutil.which("incus") or shutil.which("lxc")


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return proc.returncode, (proc.stdout or "").strip()
    except FileNotFoundError:
        return 127, f"Missing command: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"Command timed out after {timeout}s: {' '.join(cmd)}"


def capabilities() -> dict:
    """What this host can actually create right now."""
    binary = cli()
    kvm_device = os.path.exists("/dev/kvm")
    qemu = shutil.which("qemu-system-x86_64") or shutil.which("qemu-system-x86")
    cloud_localds = shutil.which("cloud-localds")
    qemu_img = shutil.which("qemu-img")
    nonkvm_ok = bool(qemu and qemu_img and cloud_localds)
    incus_version = ""
    if binary:
        rc, out = _run([binary, "--version"], timeout=15)
        if rc == 0:
            incus_version = out.splitlines()[0][:120] if out else ""
    return {
        "incus": bool(binary),
        "incus_binary": binary or "",
        "incus_version": incus_version,
        "kvm_device": kvm_device,
        "qemu": qemu or "",
        "qemu_img": qemu_img or "",
        "cloud_localds": cloud_localds or "",
        "lxc": bool(binary),
        "kvm": bool(binary and kvm_device),
        "nonkvm": bool(binary and nonkvm_ok),
        "types": {
            "lxc": bool(binary),
            "kvm": bool(binary and kvm_device),
            "nonkvm": bool(binary and nonkvm_ok),
        },
    }


def require_supported(vps_type: str) -> dict:
    vps_type = normalise_type(vps_type)
    caps = capabilities()
    if not caps["incus"]:
        raise VpsTypeError("Incus/LXD is not installed on this node. Run setup.sh first.")
    if vps_type == "kvm" and not caps["kvm"]:
        raise VpsTypeError(
            "/dev/kvm is not available on this node, so KVM virtual machines cannot start here. "
            "Use the LXC type, the Non-KVM (QEMU TCG) type, or enable nested hardware virtualisation."
        )
    if vps_type == "nonkvm" and not caps["nonkvm"]:
        missing = [name for name, key in (("qemu-system-x86_64", "qemu"),
                                          ("qemu-img", "qemu_img"),
                                          ("cloud-localds", "cloud_localds")) if not caps[key]]
        raise VpsTypeError(
            "Non-KVM VMs need " + ", ".join(missing) +
            ". Install them on the node (apt-get install qemu-system-x86 qemu-utils cloud-image-utils)."
        )
    return caps


def _run_nonkvm(actions: list[str], timeout: int = 900) -> tuple[int, str]:
    if not NONKVM_SCRIPT.exists():
        return 127, f"Missing helper script: {NONKVM_SCRIPT}"
    return _run(["bash", str(NONKVM_SCRIPT), *actions], timeout=timeout)


def parse_output(output: str) -> dict:
    values: dict[str, str] = {}
    for line in (output or "").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key.replace("_", "").isalnum():
                values[key] = value.strip()
    return values


def vm_image_ref(alias: str) -> str:
    """Return a VM-capable image reference.

    The panel's OS aliases (for example ``22.04`` or ``debian/13``) resolve to
    locally cached *container* images, and Incus refuses to launch those with
    ``--vm`` ("Asked for a VM but image is of type container"). For VMs we
    therefore always pull from the ``images:`` remote, which ships VM variants.
    """
    value = str(alias or "").strip()
    if not value:
        return "images:ubuntu/22.04"
    if ":" in value:
        return value
    if re.fullmatch(r"\d{2}\.\d{2}", value):
        return f"images:ubuntu/{value}"
    return f"images:{value}"


def create_instance(name: str, image_alias: str, vps_type: str = DEFAULT_TYPE,
                    nesting: bool = False, vcpus: int = 2, memory_mb: int = 2048,
                    disk_gb: int = 20, image_path: str = "") -> dict:
    """Create an instance and return {'name', 'vps_type', 'nesting', ...}."""
    vps_type = normalise_type(vps_type)
    require_supported(vps_type)
    nesting_value = "true" if nesting else "false"

    if vps_type == "nonkvm":
        args = ["create", "--name", name, "--alias", str(image_alias or "ubuntu-22.04"),
                "--cpu", str(int(vcpus)), "--ram-mb", str(int(memory_mb)),
                "--disk-gb", str(int(disk_gb)), "--nesting", ("on" if nesting else "off")]
        if image_path:
            args += ["--base-image", image_path]
        code, output = _run_nonkvm(args)
        if code != 0:
            raise VpsTypeError(f"Non-KVM VM creation failed: {output[-1200:]}")
        info = parse_output(output)
        ssh_password = info.get("OMEGA_SSH_PASSWORD", "")
        return {"name": name, "vps_type": vps_type, "nesting": bool(nesting),
                "ssh_host": info.get("OMEGA_SSH_HOST", "127.0.0.1"),
                "ssh_port": info.get("OMEGA_SSH_PORT", ""),
                "ssh_user": "root", "ssh_password": ssh_password,
                "raw": output[-2000:]}

    binary = cli()
    if not binary:
        raise VpsTypeError("Incus/LXD CLI is not installed on this node.")
    image_ref = vm_image_ref(image_alias) if vps_type == "kvm" else str(image_alias)
    args = [binary, "launch", image_ref, name]
    if vps_type == "kvm":
        args.append("--vm")
    args += [
        "-c", f"limits.cpu={int(vcpus)}",
        "-c", f"limits.memory={int(memory_mb)}MiB",
        "-c", f"security.nesting={nesting_value}",
    ]
    if vps_type == "lxc":
        # Matches the behaviour of the existing container creation path.
        args += ["-c", "security.privileged=true"]
    args += ["-d", f"root,size={int(disk_gb)}GiB"]
    code, output = _run(args, timeout=900)
    if code != 0 and vps_type == "kvm" and image_ref != str(image_alias) and "not found" in output.lower():
        # The translated remote image does not exist; fall back to the original alias.
        _run([binary, "delete", name, "--force"], timeout=60)
        args[2] = str(image_alias)
        code, output = _run(args, timeout=900)
    if code != 0:
        # A failed launch can leave a half-created instance behind.
        _run([binary, "delete", name, "--force"], timeout=60)
        raise VpsTypeError(f"Instance creation failed ({vps_type}): {output[-1200:]}")
    # Some images ignore the launch -c flag; make the nesting state explicit.
    set_nesting(name, vps_type, bool(nesting))
    return {"name": name, "vps_type": vps_type, "nesting": bool(nesting), "raw": output[-2000:]}


def set_nesting(name: str, vps_type: str, enabled: bool) -> tuple[bool, str]:
    vps_type = normalise_type(vps_type)
    value = "true" if enabled else "false"
    if vps_type == "nonkvm":
        code, output = _run_nonkvm(["nesting", "--name", name, "--state", ("on" if enabled else "off")])
        return code == 0, output[-800:]
    binary = cli()
    if not binary:
        return False, "Incus/LXD CLI is not installed on this node."
    code, output = _run([binary, "config", "set", name, "security.nesting", value], timeout=60)
    if code != 0:
        return False, output[-800:] or f"Could not set security.nesting={value}"
    rc, current = _run([binary, "config", "get", name, "security.nesting"], timeout=30)
    if rc == 0 and current:
        return current.strip().lower() == value, current.strip()
    return True, value


def get_nesting(name: str, vps_type: str) -> bool:
    vps_type = normalise_type(vps_type)
    if vps_type == "nonkvm":
        code, output = _run_nonkvm(["nesting", "--name", name, "--show"], timeout=30)
        return code == 0 and "on" in output.lower()
    binary = cli()
    if not binary:
        return False
    code, output = _run([binary, "config", "get", name, "security.nesting"], timeout=30)
    return code == 0 and output.strip().lower() == "true"


def exists(name: str, vps_type: str = DEFAULT_TYPE) -> bool:
    if normalise_type(vps_type) == "nonkvm":
        code, _ = _run_nonkvm(["status", "--name", name], timeout=30)
        return code == 0
    binary = cli()
    if not binary:
        return False
    code, _ = _run([binary, "info", name], timeout=30)
    return code == 0


def action(name: str, vps_type: str, operation: str) -> tuple[bool, str]:
    vps_type = normalise_type(vps_type)
    if operation not in {"start", "stop", "restart"}:
        raise ValueError("Unsupported action")
    if vps_type == "nonkvm":
        code, output = _run_nonkvm([operation, "--name", name])
        return code == 0, output[-800:]
    binary = cli()
    if not binary:
        return False, "Incus/LXD CLI is not installed on this node."
    args = [binary, operation, name]
    if operation in {"stop", "restart"}:
        args.append("--force")
    code, output = _run(args, timeout=300)
    return code == 0, output[-800:]


def remove(name: str, vps_type: str) -> tuple[bool, str]:
    if normalise_type(vps_type) == "nonkvm":
        code, output = _run_nonkvm(["destroy", "--name", name])
        return code == 0, output[-800:]
    binary = cli()
    if not binary:
        return False, "Incus/LXD CLI is not installed on this node."
    code, output = _run([binary, "delete", name, "--force"], timeout=300)
    return code == 0, output[-800:]


def instance_ip(name: str, vps_type: str) -> str:
    if normalise_type(vps_type) == "nonkvm":
        return "127.0.0.1"
    binary = cli()
    if not binary:
        return ""
    code, output = _run([binary, "list", name, "--format", "csv", "-c", "4"], timeout=30)
    if code != 0:
        return ""
    for token in (output.replace("(", "").replace(")", "")).split():
        if token.count(".") == 3 and all(part.isdigit() for part in token.split(".")):
            return token
    return ""
