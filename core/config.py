from __future__ import annotations
import os
from pathlib import Path
import secrets

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("OMEGA_DATA_DIR", "/var/lib/omega-panel"))
DB_PATH = Path(os.getenv("OMEGA_DB", str(DATA_DIR / "omega.db")))
SECRET_FILE = Path(os.getenv("OMEGA_SECRET_FILE", "/etc/omega-panel/secret"))
NODE_TOKEN_FILE = Path(os.getenv("OMEGA_NODE_TOKEN_FILE", "/etc/omega-panel/node-token"))
HOSTNAME = os.getenv("OMEGA_HOSTNAME", "rgnodes-vps")
BIND = os.getenv("OMEGA_BIND", "0.0.0.0")
PORT = int(os.getenv("OMEGA_PORT", "5000"))
NODE_BIND = os.getenv("OMEGA_NODE_BIND", "127.0.0.1")
NODE_PORT = int(os.getenv("OMEGA_NODE_PORT", "5001"))
NODE_NAME = os.getenv("OMEGA_NODE_NAME", HOSTNAME)
PANEL_URL = os.getenv("OMEGA_PANEL_URL", "http://127.0.0.1:5000")
DEFAULT_ENGINE = os.getenv("OMEGA_VPS_ENGINE", "incus")
DEFAULT_VCPUS = int(os.getenv("OMEGA_DEFAULT_VCPUS", "2"))
DEFAULT_MEMORY_MB = int(os.getenv("OMEGA_DEFAULT_MEMORY_MB", "8192"))
DEFAULT_DISK_GB = int(os.getenv("OMEGA_DEFAULT_DISK_GB", "25"))
MAX_VPS_PER_USER = int(os.getenv("OMEGA_MAX_VPS_PER_USER", "1"))
AUTO_UPDATE = os.getenv("OMEGA_AUTO_UPDATE", "true").lower() not in {"0", "false", "no"}
TIMEZONE = os.getenv("OMEGA_TIMEZONE", "Asia/Dhaka")


def _ensure_secret(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    path.write_text(value + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except PermissionError:
        pass
    return value


SECRET_KEY = _ensure_secret(SECRET_FILE)


def node_token() -> str:
    return _ensure_secret(NODE_TOKEN_FILE)
