"""Hosting extension pack for the Omega panel.

Adds, without rewriting the rest of the monolith:

* AI assistant with admin-managed Grok / Gemini keys (web widget, API, bot).
* Background image upload and panel branding (name shown at the top).
* Proxmox-style VPS types: LXC, KVM and non-KVM (QEMU TCG), each with nesting.
* Node agent install / uninstall / status commands in the admin panel.

app.py calls :func:`register_hosting_extensions` once at import time.
"""
from __future__ import annotations

import hmac
import html as html_module
import io
import json
import re
import secrets
import subprocess
import uuid
from pathlib import Path

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from . import ai, vps_types

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_MAGIC = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".gif": b"GIF8",
    ".webp": b"RIFF",
}

SETTINGS_COLUMNS = [
    ("ai_enabled", "INTEGER DEFAULT 1"),
    ("ai_provider", "TEXT DEFAULT 'gemini'"),
    ("ai_api_key", "TEXT DEFAULT ''"),
    ("ai_model", "TEXT DEFAULT ''"),
    ("ai_system_prompt", "TEXT DEFAULT ''"),
    ("ai_max_tokens", "INTEGER DEFAULT 900"),
    ("gemini_api_key", "TEXT DEFAULT ''"),
    ("gemini_model", "TEXT DEFAULT ''"),
    ("grok_api_key", "TEXT DEFAULT ''"),
    ("grok_model", "TEXT DEFAULT ''"),
    ("brand_name", "TEXT DEFAULT 'SK Hosting'"),
    ("background_path", "TEXT DEFAULT ''"),
    ("background_dim", "INTEGER DEFAULT 55"),
    ("nonkvm_image", "TEXT DEFAULT ''"),
    ("node_enroll_key", "TEXT DEFAULT ''"),
]

VPS_COLUMNS = [
    ("vps_type", "TEXT DEFAULT 'lxc'"),
    ("nesting", "INTEGER DEFAULT 0"),
    ("ssh_port", "TEXT DEFAULT ''"),
]

IMAGE_CHOICES = [
    ("ubuntu-22.04", "Ubuntu 22.04 LTS"),
    ("ubuntu-24.04", "Ubuntu 24.04 LTS"),
    ("debian-12", "Debian 12"),
    ("debian-13", "Debian 13"),
    ("almalinux-9", "AlmaLinux 9"),
    ("rockylinux-9", "Rocky Linux 9"),
    ("alpine-3.22", "Alpine 3.22"),
]

EXTRA_CSS = """
.ext-page{padding:24px}
.x-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:20px;flex-wrap:wrap}
.x-head h1{font-size:22px;font-weight:700;letter-spacing:-.4px;margin:0}
.x-head p{color:var(--text-dim);font-size:13px;margin:6px 0 0}
.x-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:16px}
.x-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:16px}
.x-card h2{font-size:14px;font-weight:600;margin:0 0 14px;display:flex;align-items:center;gap:8px}
.x-field{margin-bottom:12px}
.x-field label{display:block;font-size:12px;font-weight:500;color:var(--text-muted);margin-bottom:6px}
.x-input,.x-select,.x-textarea{width:100%;padding:9px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:10px;color:var(--text);font:13px inherit;outline:none}
.x-input:focus,.x-select:focus,.x-textarea:focus{border-color:rgba(255,255,255,.2)}
.x-textarea{min-height:90px;resize:vertical;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.x-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border:1px solid rgba(255,255,255,.12);border-radius:10px;background:rgba(255,255,255,.08);color:var(--text);font-size:13px;font-weight:500;cursor:pointer;text-decoration:none}
.x-btn:hover{background:rgba(255,255,255,.16)}
.x-btn.x-danger{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.3);color:#fca5a5}
.x-btn.x-ghost{background:transparent}
.x-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:100px;font-size:11px;font-weight:600;border:1px solid var(--border)}
.x-badge.ok{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.3);color:#86efac}
.x-badge.off{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.3);color:#fca5a5}
.x-badge.warn{background:rgba(234,179,8,.12);border-color:rgba(234,179,8,.3);color:#fde68a}
.x-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px dashed var(--border);font-size:13px}
.x-row:last-child{border-bottom:none}
.x-row span:last-child{color:var(--text-muted);font-size:12px;text-align:right;overflow-wrap:anywhere}
.x-note{font-size:12px;color:var(--text-dim);line-height:1.6}
.x-tablewrap{overflow-x:auto;border:1px solid var(--border);border-radius:10px}
.x-table{width:100%;border-collapse:collapse;font-size:13px}
.x-table th{text-align:left;padding:10px 12px;background:var(--bg-elevated);color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border)}
.x-table td{padding:10px 12px;border-bottom:1px solid var(--border);color:var(--text-muted);vertical-align:middle}
.x-table tr:last-child td{border-bottom:none}
.x-pre{background:#05080f;border:1px solid var(--border);border-radius:10px;padding:14px;font-size:12px;line-height:1.5;color:#cbd5e1;white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto}
.x-check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-muted)}
.x-check input{width:16px;height:16px;accent-color:#22c55e}
.x-bg-preview{width:100%;max-width:360px;border-radius:12px;border:1px solid var(--border);display:block}
.x-flash{padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:14px;border:1px solid var(--border)}
.x-flash.success{background:rgba(34,197,94,.1);border-color:rgba(34,197,94,.3);color:#86efac}
.x-flash.error{background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.3);color:#fca5a5}
.omega-topbar-brand{font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--text-muted);margin-right:8px}
.omega-topbar-sep{color:var(--text-dim);margin-right:8px}
.omega-ai{position:fixed;right:22px;bottom:22px;z-index:9000;font-family:inherit}
.omega-ai-toggle{width:52px;height:52px;border-radius:50%;border:1px solid rgba(255,255,255,.16);background:linear-gradient(145deg,#1c2a44,#0d1626);color:#dbeafe;font-size:22px;cursor:pointer;box-shadow:0 12px 34px rgba(0,0,0,.45)}
.omega-ai-panel{position:absolute;right:0;bottom:64px;width:min(360px,calc(100vw - 40px));background:#0b1220;border:1px solid rgba(255,255,255,.12);border-radius:16px;box-shadow:0 24px 60px rgba(0,0,0,.55);overflow:hidden}
.omega-ai-panel header{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.08);font-size:13px;color:#e2e8f0}
.omega-ai-panel header small{margin-left:auto;color:#7c8ba1;font-size:10px;text-transform:uppercase;letter-spacing:.5px}
.omega-ai-close{background:none;border:none;color:#7c8ba1;font-size:18px;cursor:pointer;line-height:1}
.omega-ai-log{max-height:300px;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px}
.omega-ai-msg{font-size:12.5px;line-height:1.55;padding:9px 11px;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere}
.omega-ai-msg.user{background:rgba(59,130,246,.16);border:1px solid rgba(59,130,246,.28);color:#dbeafe;align-self:flex-end;max-width:88%}
.omega-ai-msg.bot{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#cbd5e1;max-width:92%}
.omega-ai-form{display:flex;gap:8px;padding:10px;border-top:1px solid rgba(255,255,255,.08)}
.omega-ai-form textarea{flex:1;background:#070d18;border:1px solid rgba(255,255,255,.12);border-radius:10px;color:#e2e8f0;font:12.5px inherit;padding:8px;resize:none;min-height:38px;max-height:110px}
.omega-ai-form button{background:#1d4ed8;border:none;border-radius:10px;color:#fff;padding:0 14px;font-size:12.5px;font-weight:600;cursor:pointer}
"""


GLOBAL_CSS = """
.omega-topbar-brand{font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--text-muted,#8ea2bc);margin-right:8px}
.omega-topbar-sep{color:var(--text-dim,#63738d);margin-right:8px}
.omega-ai{position:fixed;right:22px;bottom:22px;z-index:9000;font-family:inherit}
.omega-ai-toggle{width:52px;height:52px;border-radius:50%;border:1px solid rgba(255,255,255,.16);background:linear-gradient(145deg,#1c2a44,#0d1626);color:#dbeafe;font-size:22px;cursor:pointer;box-shadow:0 12px 34px rgba(0,0,0,.45)}
.omega-ai-panel{position:absolute;right:0;bottom:64px;width:min(360px,calc(100vw - 40px));background:#0b1220;border:1px solid rgba(255,255,255,.12);border-radius:16px;box-shadow:0 24px 60px rgba(0,0,0,.55);overflow:hidden}
.omega-ai-panel header{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.08);font-size:13px;color:#e2e8f0}
.omega-ai-panel header small{margin-left:auto;color:#7c8ba1;font-size:10px;text-transform:uppercase;letter-spacing:.5px}
.omega-ai-close{background:none;border:none;color:#7c8ba1;font-size:18px;cursor:pointer;line-height:1}
.omega-ai-log{max-height:300px;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px}
.omega-ai-msg{font-size:12.5px;line-height:1.55;padding:9px 11px;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere}
.omega-ai-msg.user{background:rgba(59,130,246,.16);border:1px solid rgba(59,130,246,.28);color:#dbeafe;align-self:flex-end;max-width:88%}
.omega-ai-msg.bot{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#cbd5e1;max-width:92%}
.omega-ai-form{display:flex;gap:8px;padding:10px;border-top:1px solid rgba(255,255,255,.08)}
.omega-ai-form textarea{flex:1;background:#070d18;border:1px solid rgba(255,255,255,.12);border-radius:10px;color:#e2e8f0;font:12.5px inherit;padding:8px;resize:none;min-height:38px;max-height:110px}
.omega-ai-form button{background:#1d4ed8;border:none;border-radius:10px;color:#fff;padding:0 14px;font-size:12.5px;font-weight:600;cursor:pointer}
"""


def _esc(value) -> str:
    return html_module.escape(str(value or ""), quote=True)


def _page(title: str, heading: str, active: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>" + title + "</title>"
        "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='css/style.css') }}\">"
        "<style>" + EXTRA_CSS + "</style></head><body class=\"page-advanced\">"
        "{% include 'icons.html' %}"
        "{% from 'components.html' import sidebar, topbar, overlay %}"
        "<div class=\"app-layout\">{{ sidebar('" + active + "', settings, custom_icon) }}"
        "<div class=\"main-content\">{{ topbar('" + heading + "', '" + active + "') }}"
        "<div class=\"page ext-page\">" + body + "</div></div></div>{{ overlay() }}"
        "<script src=\"{{ url_for('static', filename='js/main.js') }}\"></script></body></html>"
    )


ADMIN_AI_BODY = """
{% with messages = get_flashed_messages(with_categories=true) %}{% for cat, msg in messages %}
<div class="x-flash {{ 'success' if cat == 'success' else 'error' }}">{{ msg }}</div>{% endfor %}{% endwith %}
<div class="x-head">
  <div><h1>AI assistant</h1>
    <p>Set the Grok and Gemini keys here. The saved key is used by the panel assistant, the Discord <code>/ask</code> command and the <code>!ai</code> prefix command.</p>
  </div>
  <span class="x-badge {{ 'ok' if settings['ai_enabled'] else 'off' }}">{{ 'Enabled' if settings['ai_enabled'] else 'Disabled' }}</span>
</div>
<div class="x-grid">
  <div class="x-card">
    <h2>Provider status</h2>
    <div class="x-row"><span>Active provider</span><span>{{ config.provider_label }}</span></div>
    <div class="x-row"><span>Model</span><span>{{ config.model }}</span></div>
    <div class="x-row"><span>API key</span><span>{% if config.has_key %}<span class="x-badge ok">configured</span>{% else %}<span class="x-badge off">missing</span>{% endif %}</span></div>
    <div class="x-row"><span>Gemini key</span><span>{{ 'saved' if gemini_saved else 'not set' }}</span></div>
    <div class="x-row"><span>Grok key</span><span>{{ 'saved' if grok_saved else 'not set' }}</span></div>
    <p class="x-note">Keys are stored in the panel database and never printed back. Leave a key field empty to keep the saved value; use the clear checkbox to remove it.</p>
  </div>
  <div class="x-card">
    <h2>Assistant settings</h2>
    <form method="post" action="{{ url_for('ext_admin_ai') }}">
      <div class="x-field"><label>Provider</label>
        <select class="x-select" name="ai_provider">
          <option value="gemini" {{ 'selected' if settings['ai_provider'] == 'gemini' }}>Google Gemini</option>
          <option value="grok" {{ 'selected' if settings['ai_provider'] == 'grok' }}>xAI Grok</option>
        </select>
      </div>
      <div class="x-field"><label>Gemini model</label>
        <input class="x-input" name="gemini_model" value="{{ settings['gemini_model'] }}" placeholder="gemini-2.5-flash"></div>
      <div class="x-field"><label>Grok model</label>
        <input class="x-input" name="grok_model" value="{{ settings['grok_model'] }}" placeholder="grok-4.7"></div>
      <div class="x-field"><label>Max answer tokens</label>
        <input class="x-input" type="number" min="120" max="4000" name="ai_max_tokens" value="{{ settings['ai_max_tokens'] or 900 }}"></div>
      <div class="x-field"><label class="x-check"><input type="checkbox" name="ai_enabled" {{ 'checked' if settings['ai_enabled'] }}> AI assistant enabled</label></div>
      <div class="x-field"><label>System prompt (optional)</label>
        <textarea class="x-textarea" name="ai_system_prompt" placeholder="Leave empty to use the built-in hosting assistant prompt.">{{ settings['ai_system_prompt'] }}</textarea></div>
      <button class="x-btn" type="submit">Save settings</button>
    </form>
  </div>
</div>
<div class="x-card">
  <h2>API keys</h2>
  <form method="post" action="{{ url_for('ext_admin_ai_keys') }}">
    <div class="x-grid">
      <div class="x-field"><label>Google Gemini API key</label>
        <input class="x-input" type="password" name="gemini_api_key" autocomplete="off" placeholder="{{ 'saved - leave empty to keep' if gemini_saved else 'AIza...' }}">
        <label class="x-check" style="margin-top:8px"><input type="checkbox" name="clear_gemini"> Remove saved Gemini key</label>
        <p class="x-note">Create a key at <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener">Google AI Studio</a>.</p>
      </div>
      <div class="x-field"><label>xAI Grok API key</label>
        <input class="x-input" type="password" name="grok_api_key" autocomplete="off" placeholder="{{ 'saved - leave empty to keep' if grok_saved else 'xai-...' }}">
        <label class="x-check" style="margin-top:8px"><input type="checkbox" name="clear_grok"> Remove saved Grok key</label>
        <p class="x-note">Create a key at <a href="https://console.x.ai/" target="_blank" rel="noopener">xAI Console</a>.</p>
      </div>
    </div>
    <button class="x-btn" type="submit">Save keys</button>
  </form>
</div>
<div class="x-card">
  <h2>Test the configured provider</h2>
  <form method="post" action="{{ url_for('ext_admin_ai_test') }}">
    <div class="x-field"><label>Test prompt</label>
      <input class="x-input" name="prompt" value="Say hello and name the panel you are running inside."></div>
    <button class="x-btn" type="submit">Send test request</button>
  </form>
  {% if test_result %}
  <div class="x-flash {{ 'success' if test_result.ok else 'error' }}" style="margin-top:14px">
    {% if test_result.ok %}<strong>{{ test_result.provider }} · {{ test_result.model }}</strong><br>{% endif %}
    {{ test_result.text }}
  </div>
  {% endif %}
</div>
"""

ADMIN_BRANDING_BODY = """
{% with messages = get_flashed_messages(with_categories=true) %}{% for cat, msg in messages %}
<div class="x-flash {{ 'success' if cat == 'success' else 'error' }}">{{ msg }}</div>{% endfor %}{% endwith %}
<div class="x-head">
  <div><h1>Branding &amp; background</h1>
    <p>The hosting name is shown at the top of every panel page and in the browser title.</p>
  </div>
  <span class="x-badge {{ 'ok' if settings['background_path'] else 'off' }}">{{ 'Background set' if settings['background_path'] else 'No background' }}</span>
</div>
<div class="x-grid">
  <div class="x-card">
    <h2>Hosting name</h2>
    <form method="post" action="{{ url_for('ext_admin_branding') }}" enctype="multipart/form-data">
      <div class="x-field"><label>Panel / hosting name</label>
        <input class="x-input" name="site_name" value="{{ settings['site_name'] }}" placeholder="SK Hosting"></div>
      <div class="x-field"><label>Short brand shown in the top bar</label>
        <input class="x-input" name="brand_name" value="{{ settings['brand_name'] }}" placeholder="SK Hosting"></div>
      <div class="x-field"><label>Footer text</label>
        <input class="x-input" name="footer_text" value="{{ settings['footer_text'] }}"></div>
      <button class="x-btn" type="submit">Save name</button>
    </form>
  </div>
  <div class="x-card">
    <h2>Background image</h2>
    {% if settings['background_path'] %}
      <img class="x-bg-preview" src="{{ settings['background_path'] }}" alt="Current background">
    {% endif %}
    <form method="post" action="{{ url_for('ext_admin_branding') }}" enctype="multipart/form-data" style="margin-top:14px">
      <div class="x-field"><label>Upload image (PNG, JPG, GIF or WebP, max 8 MB)</label>
        <input class="x-input" type="file" name="background_file" accept="image/png,image/jpeg,image/gif,image/webp"></div>
      <div class="x-field"><label>Dark overlay: {{ settings['background_dim'] or 55 }}%</label>
        <input class="x-input" type="range" min="0" max="90" step="5" name="background_dim" value="{{ settings['background_dim'] or 55 }}"></div>
      {% if settings['background_path'] %}
      <div class="x-field"><label class="x-check"><input type="checkbox" name="remove_background"> Remove the current background</label></div>
      {% endif %}
      <button class="x-btn" type="submit">Upload / apply</button>
    </form>
    <p class="x-note">The image is applied behind every panel page and is stored in <code>static/uploads/</code>.</p>
  </div>
</div>
"""

ADMIN_NODE_TOOLS_BODY = """
{% with messages = get_flashed_messages(with_categories=true) %}{% for cat, msg in messages %}
<div class="x-flash {{ 'success' if cat == 'success' else 'error' }}">{{ msg }}</div>{% endfor %}{% endwith %}
<div class="x-head">
  <div><h1>Node install / uninstall</h1>
    <p>These buttons run the node agent scripts on this host. They need the panel service to run as root (or use sudo in a terminal).</p>
  </div>
  <span class="x-badge {{ 'ok' if agent.active else 'off' }}">{{ agent.state }}</span>
</div>
<div class="x-grid">
  <div class="x-card">
    <h2>Agent status</h2>
    <div class="x-row"><span>systemd unit</span><span>{{ agent.unit_state }}</span></div>
    <div class="x-row"><span>Health endpoint</span><span>{{ agent.health }}</span></div>
    <div class="x-row"><span>Node token file</span><span>{{ agent.token }}</span></div>
    <div class="x-row"><span>Port</span><span>{{ agent.port }}</span></div>
    <div class="x-row"><span>Privileges</span><span>{{ agent.privileges }}</span></div>
    <p class="x-note">A healthy agent answers <code>http://127.0.0.1:{{ agent.port }}/api/health</code> and is used for every container/VM action the panel performs locally.</p>
  </div>
  <div class="x-card">
    <h2>Commands</h2>
    <form method="post" action="{{ url_for('ext_admin_node_tools') }}" style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="x-btn" name="action" value="check" type="submit">Check status</button>
      <button class="x-btn" name="action" value="install" type="submit">Install / repair node</button>
      <button class="x-btn x-danger" name="action" value="uninstall" type="submit">Uninstall node</button>
    </form>
    <p class="x-note" style="margin-top:12px">Equivalent terminal commands:</p>
    <pre class="x-pre">sudo bash scripts/omega-node-install.sh
sudo bash scripts/omega-node-install.sh --check
sudo bash scripts/omega-node-uninstall.sh
sudo bash scripts/omega-node-uninstall.sh --purge</pre>
  </div>
</div>
<div class="x-card">
  <h2>Connect a node by command</h2>
  <div class="x-row"><span>Enrollment key</span><span><code>{{ enroll_key or 'not generated yet' }}</code></span></div>
  <div class="x-row"><span>Panel URL</span><span>{{ panel_url }}</span></div>
  <p class="x-note">Run these on the node server (the second command connects it to this panel):</p>
  <pre class="x-pre">sudo bash scripts/omega-node-install.sh
sudo bash scripts/omega-node-connect.sh --panel {{ panel_url }} --key {{ enroll_key }} --name NODE-NAME --url http://NODE_IP:5001</pre>
  <p class="x-note">Or on the node run <code>sudo bash omega.sh</code> and choose option 3 (Node install + connect).</p>
</div>
{% if output %}
<div class="x-card">
  <h2>Output · {{ action }}</h2>
  <pre class="x-pre">{{ output }}</pre>
</div>
{% endif %}
"""

ADMIN_VPS_TYPES_BODY = """
{% with messages = get_flashed_messages(with_categories=true) %}{% for cat, msg in messages %}
<div class="x-flash {{ 'success' if cat == 'success' else 'error' }}">{{ msg }}</div>{% endfor %}{% endwith %}
<div class="x-head">
  <div><h1>VPS types</h1>
    <p>Create Proxmox-style LXC containers, KVM virtual machines or non-KVM (QEMU TCG) virtual machines, with nesting on or off.</p>
  </div>
</div>
<div class="x-grid">
  <div class="x-card">
    <h2>Host capabilities</h2>
    <div class="x-row"><span>Incus / LXD</span><span>{{ caps.incus_version if caps.incus else 'not installed' }}</span></div>
    <div class="x-row"><span>/dev/kvm</span><span>{{ 'available' if caps.kvm_device else 'not available' }}</span></div>
    <div class="x-row"><span>QEMU</span><span>{{ caps.qemu or 'not installed' }}</span></div>
    <div class="x-row"><span>cloud-localds</span><span>{{ caps.cloud_localds or 'not installed' }}</span></div>
    <div class="x-row"><span>LXC type</span><span><span class="x-badge {{ 'ok' if caps.types.lxc else 'off' }}">{{ 'ready' if caps.types.lxc else 'unavailable' }}</span></span></div>
    <div class="x-row"><span>KVM type</span><span><span class="x-badge {{ 'ok' if caps.types.kvm else 'off' }}">{{ 'ready' if caps.types.kvm else 'needs /dev/kvm' }}</span></span></div>
    <div class="x-row"><span>Non-KVM type</span><span><span class="x-badge {{ 'ok' if caps.types.nonkvm else 'off' }}">{{ 'ready' if caps.types.nonkvm else 'needs qemu + cloud-localds' }}</span></span></div>
  </div>
  <div class="x-card">
    <h2>Create VPS</h2>
    <form method="post" action="{{ url_for('ext_admin_create_typed_vps') }}">
      <div class="x-field"><label>Owner</label>
        <select class="x-select" name="user_id" required>
          {% for u in users %}<option value="{{ u['id'] }}">{{ u['username'] }}</option>{% endfor %}
        </select></div>
      <div class="x-field"><label>Node</label>
        <select class="x-select" name="node_id" required>
          {% for n in nodes %}<option value="{{ n['id'] }}">{{ n['name'] }}{{ ' (local)' if n['is_local'] else '' }}</option>{% endfor %}
        </select></div>
      <div class="x-field"><label>Type</label>
        <select class="x-select" name="vps_type">
          <option value="lxc">LXC container</option>
          <option value="kvm">KVM virtual machine</option>
          <option value="nonkvm">Non-KVM VM (QEMU TCG)</option>
        </select></div>
      <div class="x-field"><label>Operating system</label>
        <select class="x-select" name="os_type">
          {% for value, label in images %}<option value="{{ value }}">{{ label }}</option>{% endfor %}
        </select></div>
      <div class="x-grid" style="grid-template-columns:repeat(3,1fr);gap:10px">
        <div class="x-field"><label>vCPU</label><input class="x-input" type="number" name="cpu" min="1" max="64" value="2"></div>
        <div class="x-field"><label>RAM (MB)</label><input class="x-input" type="number" name="ram" min="256" max="131072" step="256" value="2048"></div>
        <div class="x-field"><label>Disk (GB)</label><input class="x-input" type="number" name="disk" min="5" max="2000" value="25"></div>
      </div>
      <div class="x-field"><label class="x-check"><input type="checkbox" name="nesting"> Nesting enabled (Docker / nested VMs inside this VPS)</label></div>
      <button class="x-btn" type="submit">Create VPS</button>
      <p class="x-note">KVM creation needs <code>/dev/kvm</code> on the node; non-KVM creation needs qemu-system-x86_64, qemu-img and cloud-localds. Creation can take a few minutes.</p>
    </form>
  </div>
</div>
<div class="x-card">
  <h2>All VPS · type and nesting</h2>
  <div class="x-tablewrap"><table class="x-table">
    <thead><tr><th>ID</th><th>Name</th><th>Owner</th><th>Type</th><th>OS</th><th>Status</th><th>Nesting</th><th></th></tr></thead>
    <tbody>
    {% for v in vps_list %}
      <tr>
        <td>#{{ v['id'] }}</td>
        <td>{{ v['container_name'] }}</td>
        <td>{{ v['username'] }}</td>
        <td>{{ v['vps_type'] or 'lxc' }}</td>
        <td>{{ v['os_type'] }}</td>
        <td>{{ v['status'] }}</td>
        <td><span class="x-badge {{ 'ok' if v['nesting'] else 'off' }}">{{ 'ON' if v['nesting'] else 'OFF' }}</span></td>
        <td>
          <form method="post" action="{{ url_for('ext_vps_nesting', vps_id=v['id']) }}" style="margin:0">
            <input type="hidden" name="enabled" value="{{ 0 if v['nesting'] else 1 }}">
            <button class="x-btn x-ghost" type="submit">{{ 'Disable' if v['nesting'] else 'Enable' }}</button>
          </form>
        </td>
      </tr>
    {% else %}
      <tr><td colspan="8">No VPS yet.</td></tr>
    {% endfor %}
    </tbody>
  </table></div>
</div>
"""


def _panel_context(get_db, user_id: int, is_admin: bool) -> str:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, container_name, status, os_type, ram, cpu, disk,
                      COALESCE(vps_type,'lxc') AS vps_type, COALESCE(nesting,0) AS nesting
               FROM vps WHERE user_id=? ORDER BY id DESC LIMIT 20""",
            (int(user_id),),
        ).fetchall()
        lines = ["Live panel context (never invent values that are not listed here):"]
        if not rows:
            lines.append("- The user has no VPS yet.")
        for row in rows:
            lines.append(
                f"- VPS #{row['id']} {row['container_name']}: type={row['vps_type']}, "
                f"status={row['status']}, os={row['os_type']}, cpu={row['cpu']}, "
                f"ram={row['ram']}, disk={row['disk']}, nesting={'on' if row['nesting'] else 'off'}"
            )
        if is_admin:
            nodes = conn.execute(
                "SELECT name, status, COALESCE(is_local,0) AS is_local FROM nodes ORDER BY id LIMIT 30"
            ).fetchall()
            for node in nodes:
                lines.append(f"- Node {node['name']}: status={node['status']}, local={'yes' if node['is_local'] else 'no'}")
            totals = conn.execute(
                "SELECT COUNT(*) AS total, SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running FROM vps"
            ).fetchone()
            if totals:
                lines.append(f"- Panel totals: {totals['total'] or 0} VPS, {totals['running'] or 0} running.")
        return "\n".join(lines)
    finally:
        conn.close()


def _read_image(upload) -> tuple[bytes, str, str]:
    filename = str(getattr(upload, "filename", "") or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_MAGIC:
        return b"", "", "Background must be a PNG, JPG, JPEG, GIF or WebP image."
    data = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        return b"", "", "The image is empty or larger than 8 MB."
    if not data.startswith(IMAGE_MAGIC[suffix]):
        return b"", "", "The uploaded file is not a valid image."
    if suffix == ".webp" and data[8:12] != b"WEBP":
        return b"", "", "The uploaded file is not a valid WebP image."
    try:
        from PIL import Image  # optional full decode
        Image.open(io.BytesIO(data)).verify()
    except ImportError:
        pass
    except Exception:
        return b"", "", "The uploaded file is not a valid image."
    return data, suffix, ""


def _agent_status(port: str) -> dict:
    state = {"active": False, "state": "unknown", "unit_state": "unknown",
             "health": "unreachable", "token": "missing", "port": port,
             "privileges": "non-root"}
    try:
        proc = subprocess.run(["systemctl", "is-active", "omega-node.service"],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=6, check=False)
        unit_state = (proc.stdout or "").strip() or "unknown"
        state["unit_state"] = unit_state
        state["active"] = unit_state == "active"
        state["state"] = "running" if state["active"] else unit_state
    except Exception:
        state["unit_state"] = "systemctl unavailable"
    try:
        import requests
        response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=3)
        if response.ok:
            state["health"] = json.dumps(response.json())[:200]
            state["active"] = True
            state["state"] = "healthy"
        else:
            state["health"] = f"HTTP {response.status_code}"
    except Exception as exc:
        state["health"] = f"unreachable ({type(exc).__name__})"
    if Path("/etc/omega-panel/node-token").is_file():
        state["token"] = "present"
    import os as _os
    state["privileges"] = "root" if hasattr(_os, "geteuid") and _os.geteuid() == 0 else "non-root (scripts need sudo)"
    return state


def register_hosting_extensions(app, deps) -> None:
    get_db = deps["get_db"]
    get_settings = deps["get_settings"]
    login_required = deps["login_required"]
    admin_required = deps["admin_required"]
    limiter = deps["limiter"]
    get_rate_limit = deps["get_rate_limit"]
    add_log = deps["add_log"]
    templates = deps["EMBEDDED_TEMPLATES"]
    call_node_api = deps["call_node_api"]
    get_node_for_vps = deps["get_node_for_vps"]
    os_image_alias = deps["os_image_alias"]
    generate_container_name = deps["generate_container_name"]

    upload_dir = Path(app.root_path) / "static" / "uploads"
    scripts_dir = Path(app.root_path) / "scripts"
    state = {"ready": False}

    def settings_row():
        return get_settings()

    def settings_dict() -> dict:
        row = settings_row()
        return dict(row) if row else {}

    def ensure_schema() -> None:
        if state["ready"]:
            return
        conn = get_db()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(settings)").fetchall()}
            if not columns:
                conn.close()
                deps["init_db"]()
                conn = get_db()
                columns = {row[1] for row in conn.execute("PRAGMA table_info(settings)").fetchall()}
            for name, definition in SETTINGS_COLUMNS:
                if name not in columns:
                    conn.execute(f"ALTER TABLE settings ADD COLUMN {name} {definition}")
            vps_columns = {row[1] for row in conn.execute("PRAGMA table_info(vps)").fetchall()}
            for name, definition in VPS_COLUMNS:
                if name not in vps_columns:
                    conn.execute(f"ALTER TABLE vps ADD COLUMN {name} {definition}")
            conn.execute("UPDATE settings SET ai_provider='gemini' WHERE COALESCE(ai_provider,'')=''")
            conn.execute("UPDATE settings SET gemini_model=? WHERE COALESCE(gemini_model,'')=''",
                         (ai.default_model("gemini"),))
            conn.execute("UPDATE settings SET grok_model=? WHERE COALESCE(grok_model,'')=''",
                         (ai.default_model("grok"),))
            conn.execute("UPDATE settings SET ai_system_prompt=? WHERE COALESCE(ai_system_prompt,'')=''",
                         (ai.DEFAULT_SYSTEM_PROMPT,))
            conn.execute("UPDATE settings SET brand_name='SK Hosting' WHERE COALESCE(brand_name,'')=''")
            conn.execute("UPDATE settings SET site_name='SK Hosting' WHERE COALESCE(site_name,'') IN ('','Omega Panel')")
            conn.execute("UPDATE vps SET vps_type='lxc' WHERE COALESCE(vps_type,'')=''")
            conn.commit()
            state["ready"] = True
        finally:
            try:
                conn.close()
            except Exception:
                pass

    try:
        ensure_schema()
    except Exception:
        app.logger.exception("Hosting extension schema could not be prepared yet")

    @app.before_request
    def _hosting_ext_ready():
        try:
            ensure_schema()
        except Exception:
            app.logger.exception("Hosting extension schema check failed")

    templates["admin_ai.html"] = _page("AI settings — {{ settings['site_name'] }}", "AI Settings", "admin", ADMIN_AI_BODY)
    templates["admin_branding.html"] = _page("Branding — {{ settings['site_name'] }}", "Branding", "admin", ADMIN_BRANDING_BODY)
    templates["admin_node_tools.html"] = _page("Node commands — {{ settings['site_name'] }}", "Node Commands", "admin", ADMIN_NODE_TOOLS_BODY)
    templates["admin_vps_types.html"] = _page("VPS types — {{ settings['site_name'] }}", "VPS Types", "admin", ADMIN_VPS_TYPES_BODY)

    # ------------------------------------------------------------------ AI
    @app.route("/admin/ai", methods=["GET", "POST"])
    @admin_required
    def ext_admin_ai():
        ensure_schema()
        if request.method == "POST":
            provider = ai.provider_slug(request.form.get("ai_provider"))
            try:
                max_tokens = max(120, min(4000, int(request.form.get("ai_max_tokens") or 900)))
            except (TypeError, ValueError):
                max_tokens = 900
            conn = get_db()
            try:
                row = conn.execute("SELECT id FROM settings LIMIT 1").fetchone()
                settings_id = row["id"] if row else 1
                conn.execute(
                    """UPDATE settings SET ai_enabled=?, ai_provider=?, ai_system_prompt=?,
                              ai_max_tokens=?, gemini_model=?, grok_model=? WHERE id=?""",
                    (1 if request.form.get("ai_enabled") else 0, provider,
                     (request.form.get("ai_system_prompt") or "").strip()[:4000],
                     max_tokens,
                     (request.form.get("gemini_model") or "").strip()[:120],
                     (request.form.get("grok_model") or "").strip()[:120],
                     settings_id),
                )
                conn.commit()
            finally:
                conn.close()
            add_log("info", "AI settings updated by administrator", "ai")
            flash("AI settings saved.", "success")
            return redirect(url_for("ext_admin_ai"))
        config = ai.configured(settings_dict())
        saved = settings_dict()
        return render_template("admin_ai.html", config=config, test_result=None,
                               gemini_saved=bool(saved.get("gemini_api_key")),
                               grok_saved=bool(saved.get("grok_api_key")))

    @app.route("/admin/ai/keys", methods=["POST"])
    @admin_required
    def ext_admin_ai_keys():
        ensure_schema()
        conn = get_db()
        try:
            row = conn.execute("SELECT id FROM settings LIMIT 1").fetchone()
            settings_id = row["id"] if row else 1
            for column, clear_field in (("gemini_api_key", "clear_gemini"),
                                        ("grok_api_key", "clear_grok")):
                if request.form.get(clear_field):
                    conn.execute(f"UPDATE settings SET {column}='' WHERE id=?", (settings_id,))
                value = (request.form.get(column) or "").strip()
                if value:
                    conn.execute(f"UPDATE settings SET {column}=? WHERE id=?", (value[:400], settings_id))
            conn.commit()
        finally:
            conn.close()
        add_log("info", "AI API keys updated by administrator", "ai")
        flash("API keys saved.", "success")
        return redirect(url_for("ext_admin_ai"))

    @app.route("/admin/ai/test", methods=["POST"])
    @admin_required
    def ext_admin_ai_test():
        ensure_schema()
        prompt = (request.form.get("prompt") or "Say hello and name the panel you are running inside.").strip()[:1000]
        current = settings_dict()
        try:
            result = ai.answer_with_settings(current, prompt)
            test_result = {"ok": True, "text": result["reply"],
                           "model": result["model"], "provider": ai.provider_meta(result["provider"])["label"]}
        except ai.AIError as exc:
            test_result = {"ok": False, "text": str(exc)}
        except Exception as exc:
            app.logger.exception("AI test request failed")
            test_result = {"ok": False, "text": f"Unexpected error: {exc}"}
        return render_template("admin_ai.html", config=ai.configured(current), test_result=test_result,
                               gemini_saved=bool(current.get("gemini_api_key")),
                               grok_saved=bool(current.get("grok_api_key")))

    @app.route("/ai/status")
    @login_required
    def ext_ai_status():
        ensure_schema()
        return jsonify(ai.configured(settings_dict()))

    @app.route("/ai/chat", methods=["POST"])
    @login_required
    @limiter.limit(lambda: get_rate_limit("api"))
    def ext_ai_chat():
        ensure_schema()
        body = request.get_json(silent=True) or {}
        message = str(body.get("message") or "").strip()
        history = body.get("history") if isinstance(body.get("history"), list) else []
        if not message:
            return jsonify({"error": "Message is required."}), 400
        try:
            context = _panel_context(get_db, session["user_id"], bool(session.get("is_admin")))
            result = ai.answer_with_settings(settings_dict(), message, history=history, context=context)
        except ai.AIError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            app.logger.exception("AI assistant request failed")
            return jsonify({"error": "AI request failed. Check the server log."}), 500
        add_log("info", f"AI assistant answered a {len(message)}-character question", "ai")
        return jsonify(result)

    # ------------------------------------------------------------ branding
    @app.route("/admin/branding", methods=["GET", "POST"])
    @admin_required
    def ext_admin_branding():
        ensure_schema()
        if request.method == "POST":
            conn = get_db()
            try:
                row = conn.execute("SELECT id, background_path FROM settings LIMIT 1").fetchone()
                if not row:
                    flash("Settings row is missing.", "error")
                    return redirect(url_for("ext_admin_branding"))
                settings_id = row["id"]
                current_background = row["background_path"] or ""
                try:
                    dim = max(0, min(90, int(request.form.get("background_dim") or 55)))
                except (TypeError, ValueError):
                    dim = 55
                site_name = (request.form.get("site_name") or "").strip()[:120]
                brand_name = (request.form.get("brand_name") or "").strip()[:60]
                footer_text = (request.form.get("footer_text") or "").strip()[:200]
                if site_name or brand_name or footer_text:
                    conn.execute(
                        """UPDATE settings SET site_name=COALESCE(NULLIF(?,''),site_name),
                                  brand_name=COALESCE(NULLIF(?,''),brand_name),
                                  footer_text=COALESCE(NULLIF(?,''),footer_text) WHERE id=?""",
                        (site_name, brand_name, footer_text, settings_id),
                    )
                conn.execute("UPDATE settings SET background_dim=? WHERE id=?", (dim, settings_id))
                upload = request.files.get("background_file")
                if upload and upload.filename:
                    data, suffix, error = _read_image(upload)
                    if error:
                        conn.commit()
                        flash(error, "error")
                        return redirect(url_for("ext_admin_branding"))
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    filename = f"bg_{uuid.uuid4().hex[:12]}{suffix}"
                    (upload_dir / filename).write_bytes(data)
                    if current_background.startswith("/static/uploads/"):
                        try:
                            (Path(app.root_path) / current_background.lstrip("/")).unlink()
                        except OSError:
                            pass
                    current_background = f"/static/uploads/{filename}"
                    conn.execute("UPDATE settings SET background_path=? WHERE id=?",
                                 (current_background, settings_id))
                if request.form.get("remove_background") and current_background:
                    if current_background.startswith("/static/uploads/"):
                        try:
                            (Path(app.root_path) / current_background.lstrip("/")).unlink()
                        except OSError:
                            pass
                    conn.execute("UPDATE settings SET background_path='' WHERE id=?", (settings_id,))
                conn.commit()
            finally:
                conn.close()
            add_log("info", "Panel branding updated", "settings")
            flash("Branding saved.", "success")
            return redirect(url_for("ext_admin_branding"))
        return render_template("admin_branding.html")

    # ----------------------------------------------------------- node tools
    @app.route("/admin/node-tools", methods=["GET", "POST"])
    @admin_required
    def ext_admin_node_tools():
        port = str(__import__("os").environ.get("OMEGA_NODE_PORT", "5001"))
        output = ""
        action = ""
        if request.method == "POST":
            action = (request.form.get("action") or "check").strip()
            commands = {
                "check": (scripts_dir / "omega-node-install.sh", ["--check"]),
                "install": (scripts_dir / "omega-node-install.sh", []),
                "uninstall": (scripts_dir / "omega-node-uninstall.sh", []),
            }
            if action not in commands:
                flash("Unknown action.", "error")
                return redirect(url_for("ext_admin_node_tools"))
            script, extra = commands[action]
            if not script.is_file():
                flash(f"Missing script: {script.name}", "error")
                return redirect(url_for("ext_admin_node_tools"))
            try:
                proc = subprocess.run(["bash", str(script), *extra], text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      timeout=420, check=False)
                output = ((proc.stdout or "") + (f"\n[exit status {proc.returncode}]" if proc.returncode else ""))[-12000:]
                flash(f"{action.title()} command finished with exit status {proc.returncode}.",
                      "success" if proc.returncode == 0 else "error")
            except subprocess.TimeoutExpired:
                output = "The command timed out after 420 seconds."
                flash("Command timed out.", "error")
            except Exception as exc:
                output = f"Could not run the command: {exc}"
                flash("Command could not be started.", "error")
            add_log("warning", f"Node command '{action}' executed from the admin panel", "node")
        return render_template("admin_node_tools.html", output=output, action=action,
                               agent=_agent_status(port), enroll_key=_node_enroll_key(),
                               panel_url=_panel_url())

    # ----------------------------------------------------------- VPS types
    @app.route("/admin/vps-types")
    @admin_required
    def ext_admin_vps_types():
        ensure_schema()
        conn = get_db()
        try:
            users = conn.execute("SELECT id, username FROM users ORDER BY username").fetchall()
            nodes = conn.execute("SELECT id, name, is_local FROM nodes ORDER BY id").fetchall()
            vps_list = conn.execute(
                """SELECT v.id, v.container_name, v.os_type, v.status, v.user_id,
                          COALESCE(v.vps_type,'lxc') AS vps_type, COALESCE(v.nesting,0) AS nesting,
                          u.username
                   FROM vps v LEFT JOIN users u ON u.id=v.user_id ORDER BY v.id DESC LIMIT 200"""
            ).fetchall()
        finally:
            conn.close()
        return render_template("admin_vps_types.html", caps=vps_types.capabilities(),
                               users=users, nodes=nodes, vps_list=vps_list, images=IMAGE_CHOICES)

    @app.route("/admin/vps-types/create", methods=["POST"])
    @admin_required
    def ext_admin_create_typed_vps():
        ensure_schema()
        try:
            user_id = int(request.form.get("user_id") or 0)
            node_id = int(request.form.get("node_id") or 0)
            vps_type = vps_types.normalise_type(request.form.get("vps_type"))
            nesting = bool(request.form.get("nesting"))
            cpu = max(1, min(64, int(request.form.get("cpu") or 2)))
            ram_mb = max(256, min(131072, int(request.form.get("ram") or 2048)))
            disk_gb = max(5, min(2000, int(request.form.get("disk") or 25)))
            os_type = (request.form.get("os_type") or "ubuntu-22.04").strip()
        except (TypeError, ValueError):
            flash("CPU, RAM, disk and node values must be numbers.", "error")
            return redirect(url_for("ext_admin_vps_types"))

        conn = get_db()
        try:
            user = conn.execute("SELECT id, username FROM users WHERE id=?", (user_id,)).fetchone()
            node = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        finally:
            conn.close()
        if not user or not node:
            flash("Select an existing user and node.", "error")
            return redirect(url_for("ext_admin_vps_types"))

        settings_now = settings_dict()
        name = generate_container_name()
        image_alias = os_image_alias(os_type)
        ssh_password = ""
        ssh_port = ""
        try:
            if node["is_local"]:
                result = vps_types.create_instance(
                    name, image_alias, vps_type, nesting, cpu, ram_mb, disk_gb,
                    image_path=str(settings_now.get("nonkvm_image") or ""),
                )
                container_id = name
                ssh_password = result.get("ssh_password") or ""
                ssh_port = result.get("ssh_port") or ""
            else:
                payload = {"name": name, "image": image_alias,
                           "ram": f"{ram_mb}MB", "cpu": f"{cpu} vCPU", "disk": f"{disk_gb}GB",
                           "vps_type": vps_type, "nesting": nesting}
                response, code = call_node_api(node["node_url"], node["api_key"],
                                               "/api/container/create", method="POST",
                                               data=payload, timeout=900)
                if code not in (200, 201) or not isinstance(response, dict) or response.get("error"):
                    message = response.get("error") if isinstance(response, dict) else str(response)
                    raise RuntimeError(message or f"Remote node returned HTTP {code}")
                container_id = response.get("container_id") or name
                ssh_password = response.get("ssh_password") or ""
                ssh_port = str(response.get("ssh_port") or "")
        except Exception as exc:
            app.logger.exception("Typed VPS creation failed")
            add_log("error", f"VPS creation failed ({vps_type}): {exc}", "vps")
            flash(f"VPS creation failed: {exc}", "error")
            return redirect(url_for("ext_admin_vps_types"))

        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO vps (user_id, node_id, container_id, container_name, os_type,
                                    ram, cpu, disk, status, vps_type, nesting, ssh_password, ssh_port)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, node_id, container_id, name, os_type, f"{ram_mb}MB",
                 f"{cpu} vCPU", f"{disk_gb}GB", "running", vps_type, 1 if nesting else 0,
                 ssh_password or None, ssh_port or None),
            )
            conn.commit()
        finally:
            conn.close()
        add_log("info", f"{vps_types.type_meta(vps_type)['label']} created: {name} for {user['username']}", "vps")
        flash(f"{vps_types.type_meta(vps_type)['label']} {name} created "
              f"(nesting {'on' if nesting else 'off'}).", "success")
        return redirect(url_for("ext_admin_vps_types"))

    @app.route("/vps/<int:vps_id>/nesting", methods=["POST"])
    @login_required
    def ext_vps_nesting(vps_id):
        ensure_schema()
        vps_row, node = get_node_for_vps(vps_id)
        if not vps_row:
            if request.is_json:
                return jsonify({"error": "VPS not found"}), 404
            flash("VPS not found.", "error")
            return redirect(url_for("dashboard"))
        conn = get_db()
        try:
            shared = conn.execute("SELECT 1 FROM vps_shares WHERE vps_id=? AND shared_with=?",
                                  (vps_id, session["user_id"])).fetchone()
        finally:
            conn.close()
        if int(vps_row["user_id"]) != int(session["user_id"]) and not session.get("is_admin") and not shared:
            if request.is_json:
                return jsonify({"error": "Not allowed"}), 403
            flash("You do not have access to this VPS.", "error")
            return redirect(url_for("dashboard"))

        raw = request.form.get("enabled")
        if raw is None and request.is_json:
            raw = (request.get_json(silent=True) or {}).get("enabled")
        current = bool(vps_row["nesting"]) if "nesting" in vps_row.keys() else False
        enabled = current if raw is None else str(raw).strip().lower() in {"1", "true", "on", "yes"}

        vps_type = vps_row["vps_type"] if "vps_type" in vps_row.keys() else "lxc"
        container_id = vps_row["container_id"] or vps_row["container_name"]
        try:
            if node and not node["is_local"]:
                response, code = call_node_api(node["node_url"], node["api_key"],
                                               f"/api/container/{container_id}/nesting",
                                               method="POST", data={"nesting": enabled}, timeout=120)
                ok = code in (200, 201) and isinstance(response, dict) and not response.get("error")
                message = (response.get("error") if isinstance(response, dict) else "") or (
                    "Nesting updated" if ok else f"Node returned HTTP {code}")
            else:
                ok, message = vps_types.set_nesting(container_id, vps_type, enabled)
        except Exception as exc:
            ok, message = False, str(exc)

        if ok:
            conn = get_db()
            try:
                conn.execute("UPDATE vps SET nesting=? WHERE id=?", (1 if enabled else 0, vps_id))
                conn.commit()
            finally:
                conn.close()
            add_log("info", f"Nesting {'enabled' if enabled else 'disabled'} on {vps_row['container_name']}", "vps")
        if request.is_json or request.args.get("format") == "json":
            return jsonify({"ok": ok, "nesting": enabled, "message": message})
        flash(("Nesting " + ("enabled" if enabled else "disabled") + " on " + str(vps_row["container_name"])
               + ("" if ok else f": {message}")), "success" if ok else "error")
        target = request.referrer or url_for("ext_admin_vps_types")
        return redirect(target)

    # ------------------------------------------------------ node enrollment
    def _node_enroll_key() -> str:
        conn = get_db()
        try:
            row = conn.execute("SELECT id, node_enroll_key FROM settings LIMIT 1").fetchone()
            if not row:
                return ""
            key = str(row["node_enroll_key"] or "").strip()
            if not key:
                key = secrets.token_hex(20)
                conn.execute("UPDATE settings SET node_enroll_key=? WHERE id=?", (key, row["id"]))
                conn.commit()
            return key
        finally:
            conn.close()

    def _panel_url() -> str:
        configured = str(settings_dict().get("panel_public_url") or "").strip().rstrip("/")
        return configured or request.url_root.rstrip("/")

    @app.route("/api/nodes/enroll", methods=["POST"])
    @limiter.limit("30/minute")
    def ext_node_enroll():
        ensure_schema()
        body = request.get_json(silent=True) or {}
        supplied = str(request.headers.get("X-Omega-Enroll") or body.get("enroll_key") or "").strip()
        expected = _node_enroll_key()
        if not expected or not hmac.compare_digest(supplied, expected):
            return jsonify({"error": "Invalid enrollment key"}), 403
        name = str(body.get("name") or "").strip()[:64]
        node_url = str(body.get("node_url") or "").strip().rstrip("/")[:300]
        token = str(body.get("token") or "").strip()[:200]
        hostname = str(body.get("hostname") or name).strip()[:200] or name
        if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", name):
            return jsonify({"error": "Invalid node name"}), 400
        if not re.match(r"^https?://", node_url):
            return jsonify({"error": "node_url must start with http:// or https://"}), 400
        if not token:
            return jsonify({"error": "token is required"}), 400
        conn = get_db()
        try:
            existing = conn.execute("SELECT id FROM nodes WHERE name=?", (name,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE nodes SET hostname=?, node_url=?, api_key=?, status='online', is_local=0 WHERE id=?",
                    (hostname, node_url, token, existing["id"]),
                )
                node_id = existing["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO nodes(name,hostname,node_url,api_key,status,is_local) VALUES(?,?,?,?,'online',0)",
                    (name, hostname, node_url, token),
                )
                node_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        add_log("info", f"Node connected by command: {name} ({node_url})", "node")
        return jsonify({"ok": True, "node_id": node_id, "name": name, "node_url": node_url})

    @app.route("/api/nodes/enroll/key")
    @admin_required
    def ext_node_enroll_key():
        ensure_schema()
        return jsonify({"enroll_key": _node_enroll_key(), "panel_url": _panel_url()})

    # ------------------------------------------- global branding / AI widget
    @app.after_request
    def _hosting_ext_inject(response):
        try:
            if response.direct_passthrough or response.is_streamed or response.mimetype != "text/html":
                return response
            if request.endpoint in {"embedded_css", "embedded_js"}:
                return response
            raw = response.get_data()
            if len(raw) > 3_500_000:
                return response
            html = raw.decode("utf-8", "ignore")
            if "<!--omega-host-ext-->" in html:
                return response
            current = settings_dict()
            brand = _esc(current.get("brand_name") or current.get("site_name") or "SK Hosting")
            background = str(current.get("background_path") or "").strip()
            try:
                dim = max(0, min(90, int(current.get("background_dim") or 55))) / 100.0
            except (TypeError, ValueError):
                dim = 0.55
            css = ""
            if background.startswith("/static/"):
                css += (
                    "body{background-image:linear-gradient(rgba(3,7,18,%.2f),rgba(3,7,18,%.2f)),"
                    "url('%s') !important;background-size:cover !important;background-position:center !important;"
                    "background-attachment:fixed !important;background-repeat:no-repeat !important;}"
                    % (dim, dim, _esc(background))
                )
            widget = ""
            config = ai.configured(current)
            if session.get("user_id") and config["enabled"] and config["has_key"]:
                widget = (
                    '<div id="omega-ai" class="omega-ai">'
                    '<button type="button" id="omega-ai-toggle" class="omega-ai-toggle" aria-label="AI assistant">&#10022;</button>'
                    '<section id="omega-ai-panel" class="omega-ai-panel" hidden>'
                    "<header><strong>AI assistant</strong><small>" + _esc(config["model"]) + "</small>"
                    '<button type="button" class="omega-ai-close" id="omega-ai-close" aria-label="Close">&times;</button></header>'
                    '<div class="omega-ai-log" id="omega-ai-log"></div>'
                    '<form class="omega-ai-form" id="omega-ai-form">'
                    '<textarea id="omega-ai-input" rows="2" placeholder="Ask about your VPS, nesting, SSH, backups..."></textarea>'
                    "<button type=\"submit\">Send</button></form></section></div>"
                    "<script>(function(){var root=document.getElementById('omega-ai');if(!root)return;"
                    "var panel=document.getElementById('omega-ai-panel'),logEl=document.getElementById('omega-ai-log'),"
                    "form=document.getElementById('omega-ai-form'),input=document.getElementById('omega-ai-input'),history=[];"
                    "function add(role,text){var el=document.createElement('div');el.className='omega-ai-msg '+role;"
                    "el.textContent=text;logEl.appendChild(el);logEl.scrollTop=logEl.scrollHeight;return el;}"
                    "document.getElementById('omega-ai-toggle').addEventListener('click',function(){panel.hidden=!panel.hidden;"
                    "if(!panel.hidden&&!logEl.childElementCount){add('bot','Hi! Ask me about your VPS, nesting, SSH or panel settings.');}});"
                    "document.getElementById('omega-ai-close').addEventListener('click',function(){panel.hidden=true;});"
                    "form.addEventListener('submit',async function(event){event.preventDefault();var text=input.value.trim();"
                    "if(!text)return;input.value='';add('user',text);var pending=add('bot','Thinking...');"
                    "try{var res=await fetch('/ai/chat',{method:'POST',headers:{'Content-Type':'application/json'},"
                    "body:JSON.stringify({message:text,history:history.slice(-10)})});var data=await res.json();"
                    "pending.textContent=data.reply||data.error||'No answer.';if(data.reply){history.push({role:'user',content:text});"
                    "history.push({role:'assistant',content:data.reply});}}catch(err){pending.textContent='AI request failed: '+err;}});"
                    "})();</script>"
                )
            if brand and '<span class="topbar-title">' in html:
                html = html.replace(
                    '<span class="topbar-title">',
                    '<span class="topbar-title"><span class="omega-topbar-brand">' + brand +
                    '</span><span class="omega-topbar-sep">&bull;</span>', 1)
            style_block = '<style id="omega-host-ext-style">' + GLOBAL_CSS + css + "</style>"
            if "</head>" in html:
                html = html.replace("</head>", style_block + "</head>", 1)
            else:
                html = style_block + html
            if widget:
                if "</body>" in html:
                    html = html.replace("</body>", widget + "</body>", 1)
                else:
                    html += widget
            if "</body>" in html:
                html = html.replace("</body>", "<!--omega-host-ext--></body>", 1)
            else:
                html += "<!--omega-host-ext-->"
            response.set_data(html)
        except Exception:
            app.logger.exception("Could not inject hosting extras into the page")
        return response
