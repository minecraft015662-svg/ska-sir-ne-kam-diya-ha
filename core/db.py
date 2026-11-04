import os
import sqlite3
import hashlib
import secrets

DB_PATH = os.environ.get('OMEGA_DB_PATH', '/var/lib/omega-panel/omega.db')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def generate_api_key():
    return secrets.token_hex(32)

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            api_key TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hostname TEXT NOT NULL,
            node_url TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            is_local INTEGER DEFAULT 0,
            status TEXT DEFAULT 'online'
        )
    ''')
    conn.commit()
    conn.close()

def migrate_nodes():
    pass
