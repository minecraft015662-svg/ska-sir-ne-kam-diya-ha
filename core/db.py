from __future__ import annotations
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from .config import DB_PATH, DATA_DIR, DEFAULT_ENGINE, DEFAULT_VCPUS, DEFAULT_MEMORY_MB, DEFAULT_DISK_GB, MAX_VPS_PER_USER, HOSTNAME

_lock = threading.RLock()

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con

@contextmanager
def db():
    with _lock:
        con = connect()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
          max_vps INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          host TEXT NOT NULL DEFAULT '127.0.0.1',
          port INTEGER NOT NULL DEFAULT 5001,
          token TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          cpu_limit INTEGER,
          memory_limit_mb INTEGER,
          disk_limit_gb INTEGER,
          last_seen TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vps (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          node_id INTEGER NOT NULL,
          name TEXT UNIQUE NOT NULL,
          os_slug TEXT NOT NULL,
          engine TEXT NOT NULL,
          vcpus INTEGER NOT NULL DEFAULT 2,
          memory_mb INTEGER NOT NULL DEFAULT 8192,
          disk_gb INTEGER NOT NULL DEFAULT 25,
          state TEXT NOT NULL DEFAULT 'creating',
          hostname TEXT NOT NULL,
          ip_address TEXT,
          desired_state TEXT NOT NULL DEFAULT 'running',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(node_id) REFERENCES nodes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          vps_id INTEGER,
          kind TEXT NOT NULL,
          status TEXT NOT NULL,
          progress INTEGER NOT NULL DEFAULT 0,
          message TEXT NOT NULL DEFAULT '',
          details TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(vps_id) REFERENCES vps(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vps_user ON vps(user_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        ''')
        defaults = {
          "host_name": HOSTNAME,
          "default_engine": DEFAULT_ENGINE,
          "default_vcpus": str(DEFAULT_VCPUS),
          "default_memory_mb": str(DEFAULT_MEMORY_MB),
          "default_disk_gb": str(DEFAULT_DISK_GB),
          "max_vps_per_user": str(MAX_VPS_PER_USER),
          "auto_update": "true",
          "node_cpu_policy": "unlimited",
        }
        for key, value in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))

def get_setting(key: str, default=None):
    with db() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    with db() as con:
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

def create_user(username: str, password: str, role='user', max_vps=1):
    username = username.strip()
    if not 3 <= len(username) <= 32:
        raise ValueError("Username must be 3-32 characters")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    with db() as con:
        cur = con.execute("INSERT INTO users(username,password_hash,role,max_vps,created_at) VALUES(?,?,?,?,?)", (username, generate_password_hash(password), role, int(max_vps), utcnow()))
        return cur.lastrowid

def verify_user(username: str, password: str):
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
    return row if row and check_password_hash(row["password_hash"], password) else None

def get_user(user_id: int):
    with db() as con:
        return con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

def count_vps(user_id: int):
    with db() as con:
        return con.execute("SELECT COUNT(*) AS n FROM vps WHERE user_id=?", (user_id,)).fetchone()["n"]

def list_nodes():
    with db() as con:
        return con.execute("SELECT * FROM nodes ORDER BY id").fetchall()

def get_node(node_id: int):
    with db() as con:
        return con.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()

def ensure_local_node(token: str):
    with db() as con:
        row = con.execute("SELECT id FROM nodes WHERE name=?", (HOSTNAME,)).fetchone()
        if row:
            con.execute("UPDATE nodes SET token=?, host='127.0.0.1', port=5001, enabled=1 WHERE id=?", (token,row["id"]))
            return row["id"]
        cur = con.execute("INSERT INTO nodes(name,host,port,token,enabled,cpu_limit,last_seen,created_at) VALUES(?,?,?,?,?,?,?,?)", (HOSTNAME,'127.0.0.1',5001,token,1,None,utcnow(),utcnow()))
        return cur.lastrowid

def create_vps(user_id, node_id, name, os_slug, engine, vcpus, memory_mb, disk_gb, hostname=None):
    with db() as con:
        cur = con.execute("INSERT INTO vps(user_id,node_id,name,os_slug,engine,vcpus,memory_mb,disk_gb,state,hostname,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (user_id,node_id,name,os_slug,engine,vcpus,memory_mb,disk_gb,'creating',hostname or name,utcnow(),utcnow()))
        return cur.lastrowid

def get_vps(vps_id):
    with db() as con:
        return con.execute("SELECT v.*,u.username,n.name AS node_name,n.host AS node_host,n.port AS node_port,n.token AS node_token,n.enabled AS node_enabled FROM vps v JOIN users u ON u.id=v.user_id JOIN nodes n ON n.id=v.node_id WHERE v.id=?", (vps_id,)).fetchone()

def list_vps_for_user(user_id):
    with db() as con:
        return con.execute("SELECT v.*,n.name AS node_name FROM vps v JOIN nodes n ON n.id=v.node_id WHERE v.user_id=? ORDER BY v.id DESC", (user_id,)).fetchall()

def list_all_vps():
    with db() as con:
        return con.execute("SELECT v.*,u.username,n.name AS node_name FROM vps v JOIN users u ON u.id=v.user_id JOIN nodes n ON n.id=v.node_id ORDER BY v.id DESC").fetchall()

def update_vps(vps_id, **fields):
    allowed = {"state","ip_address","desired_state","updated_at","hostname","vcpus","memory_mb","disk_gb"}
    fields = {k:v for k,v in fields.items() if k in allowed}
    if not fields: return
    fields["updated_at"] = utcnow()
    sql = ",".join(f"{k}=?" for k in fields)
    with db() as con:
        con.execute(f"UPDATE vps SET {sql} WHERE id=?", (*fields.values(), vps_id))

def delete_vps(vps_id):
    with db() as con:
        con.execute("DELETE FROM vps WHERE id=?", (vps_id,))

def create_job(vps_id, kind, message='Queued'):
    with db() as con:
        cur = con.execute("INSERT INTO jobs(vps_id,kind,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (vps_id,kind,'queued',0,message,utcnow(),utcnow()))
        return cur.lastrowid

def get_job(job_id):
    with db() as con:
        return con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()

def list_active_jobs(limit=50):
    with db() as con:
        return con.execute("SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

def list_jobs_for_user(user_id, limit=25):
    with db() as con:
        return con.execute("SELECT j.* FROM jobs j JOIN vps v ON v.id=j.vps_id WHERE v.user_id=? ORDER BY j.id DESC LIMIT ?", (user_id,limit)).fetchall()

def update_job(job_id, **fields):
    allowed = {"status","progress","message","details","attempts"}
    fields = {k:(json.dumps(v, ensure_ascii=False) if k=="details" and not isinstance(v,str) else v) for k,v in fields.items() if k in allowed}
    fields["updated_at"] = utcnow()
    sql = ",".join(f"{k}=?" for k in fields)
    with db() as con:
        con.execute(f"UPDATE jobs SET {sql} WHERE id=?", (*fields.values(),job_id))

def reset_stale_jobs():
    with db() as con:
        con.execute("UPDATE jobs SET status='queued', message='Recovered after service restart', updated_at=? WHERE status='running'", (utcnow(),))

def all_users():
    with db() as con:
        return con.execute("SELECT id,username,role,max_vps,created_at FROM users ORDER BY id DESC").fetchall()

def set_user_quota(user_id: int, max_vps: int):
    with db() as con:
        con.execute("UPDATE users SET max_vps=? WHERE id=?", (max(1,int(max_vps)),user_id))

def set_node_quota(node_id: int, cpu_limit, memory_limit_mb, disk_limit_gb):
    with db() as con:
        con.execute("UPDATE nodes SET cpu_limit=?,memory_limit_mb=?,disk_limit_gb=? WHERE id=?", (None if cpu_limit in (None,"","UNL","unlimited") else int(cpu_limit), None if memory_limit_mb in (None,"","UNL","unlimited") else int(memory_limit_mb), None if disk_limit_gb in (None,"","UNL","unlimited") else int(disk_limit_gb), node_id))
