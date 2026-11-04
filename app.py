import os
import sqlite3
import hashlib
import secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for
from core.provision import create_vps_container

app = Flask(__name__)
DB_PATH = '/var/lib/omega-panel/omega.db'

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key():
    return secrets.token_hex(32)

def init_db():
    conn = get_db()
    # Users table
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
    # Nodes table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hostname TEXT NOT NULL,
            node_url TEXT,
            api_key TEXT,
            is_local INTEGER DEFAULT 0,
            status TEXT DEFAULT 'offline'
        )
    ''')
    conn.commit()
    conn.close()

def migrate_nodes():
    # Placeholder for future schema migrations
    pass

@app.route('/')
def index():
    return render_template('vps.html')

@app.route('/vps/create', methods=['POST'])
def create_vps():
    vps_name = request.form.get('vps_name')
    root_password = request.form.get('root_password')
    result = create_vps_container(vps_name, root_password=root_password)
    return jsonify(result)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
