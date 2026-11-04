# Vizion Panel

> Credit: **sartahk34** · **SKa** V4 Stable latest

**Primary author:** MrZetrix  
**Original project/reference credit:** NafiGamer — `nafigamer0`

A clean-source rebuild of the uploaded Vizion Panel V3 Incus package. V4 keeps the same core product concept—web VPS dashboard, users, admin controls, Incus, SSH/SSHX and node status—but removes the fragile obfuscated runtime and destructive setup behavior.

## What is included

- Incus system containers (LXC/liblxc backend)
- Incus virtual machines with `--vm` (QEMU; KVM acceleration when the host exposes `/dev/kvm`)
- Host preparation for `cpu-checker`, `kvm-ok`, QEMU/KVM and libvirt
- Optional LXD snap compatibility install with `--with-lxd` without purging Incus/LXC packages
- Default VPS plan: **2 vCPU + 8 GiB RAM + 25 GiB disk**
- Default per-user quota: **1 VPS**, editable by admin
- Admin resource upgrades for existing VPS
- Node CPU policy shown as **UNL** by default (no panel-imposed node CPU quota; real hardware remains the physical limit)
- Live creation status in the dashboard with progress polling
- Dedicated provisioning worker + systemd restart + 60-second reconciliation watchdog
- Automatic OS update configuration for Debian/Ubuntu, RHEL-family, Alpine and Arch guests
- 20 UI languages with English as the default
- Configurable host name, default `rgnodes-vps`
- RGNODES™ SSHX bridge helper
- Optional Pterodactyl Panel installation helper for Debian/Ubuntu guests

## One line install (no clone)

```bash
bash <(curl -sL https://raw.githubusercontent.com/minecraft015662-svg/ska-sir-ne-kam-diya-ha/main/omega.sh)
```

The script downloads the repository into a temporary directory and shows the same menu;
nothing stays on the machine except what `setup.sh` installs. From a checkout use
`sudo bash omega.sh`. The menu clears the screen on every loop and after each action, so
old output never mixes with the next menu.

## Install

The fastest way is the single command menu (installs, uninstalls, connects nodes):

```bash
sudo bash omega.sh
```

```
  1) Install panel
  2) Uninstall panel
  3) Node install + connect
  4) Port forwarding
  5) Panel status
  6) Update panel
  7) Exit
```

Non-interactive: `sudo bash omega.sh --install`, `--uninstall`, `--node`, `--status`, `--update`, `--port-forward`.

Direct install on a supported systemd host as root:

```bash
sudo bash setup.sh
```

The default first login is **admin / admin**; change it right after signing in.

For LXD compatibility probing/installation too:

```bash
sudo bash setup.sh --with-lxd
```

The installer prefers the host distro Python, installs dependencies in `venv/`, creates the first admin as **admin / admin** (override with `OMEGA_ADMIN_USER` / `OMEGA_ADMIN_PASSWORD`), writes it to `/var/lib/omega-panel/first_admin_credentials.txt` with restrictive permissions, and registers a local node row. Change the password immediately after the first login.

## 24/7 services

`omega-panel.service`, `omega-node.service`, `omega-jobs.service`, `omega-watchdog.timer`, and `omega-image-refresh.timer` are enabled by setup. The VPS worker is persistent across panel process restarts and recovers unfinished jobs idempotently.

## Hardware truth

`kvm-ok` checks whether KVM acceleration is usable. A VM creation request fails cleanly when the host has no KVM support instead of reporting a false success. On nested VPS hosting, `/dev/kvm` may be unavailable even when the CPU supports virtualization on the physical server.

## Changing hostname and defaults

Use **Admin Panel → Panel settings**. The default host name is `rgnodes-vps`; the code does not hard-code a permanent node name.

## Pterodactyl

Admin users can open a ready Debian/Ubuntu VPS and start the Pterodactyl helper with a domain and email. The helper uses the current stable release archive, configures MariaDB/Redis/PHP-FPM/Nginx, and leaves TLS and first panel-admin creation to the operator.

## V3 compatibility note

The original V3 `app.py` and `node.py` were Py-Fuscate/bytecode-obfuscated and are stored under `legacy_v3/` for reference only. They are **not executed by V4**. Because the old runtime hid its database schema and operational behavior, V4 does not silently overwrite an existing V3 database; back up any live V3 data before switching.

## Hosting extension pack

### VPS types (Proxmox-style)

Admin → **VPS Types (LXC/KVM)** creates instances with an explicit type:

| Type | Backend | Nesting | Requirement |
| --- | --- | --- | --- |
| `lxc` | Incus system container | `security.nesting` | Incus/LXD |
| `kvm` | Incus VM (QEMU/KVM) | `security.nesting` (VT-x/AMD-V in guest) | `/dev/kvm` |
| `nonkvm` | QEMU software emulation (TCG) | emulated VMX/SVM where supported | `qemu-system-x86_64`, `qemu-img`, `cloud-localds` |

Nesting can be toggled later from the same page, from the VPS API
(`POST /vps/<id>/nesting`), from Discord (`/nesting`, `!nesting <id> on|off`) or
through the node agent (`POST /api/container/<id>/nesting`). Non-KVM VMs are
created by `scripts/omega-nonkvm.sh` from an Ubuntu cloud image with cloud-init
(root password + SSH) and a host-forwarded SSH port; the base image can be
overridden with the `nonkvm_image` panel setting or `OMEGA_NONKVM_BASE_IMAGE`.

### AI assistant (Grok + Gemini)

Admin → **AI Settings** stores per-provider API keys in the panel database:

* Google Gemini (default model `gemini-2.5-flash`)
* xAI Grok (default model `grok-4.7`)

One configured key powers the floating panel assistant, `POST /ai/chat`,
`POST /admin/ai/keys`, the Discord `/ask` slash command and the `!ai` prefix
command. The assistant receives the signed-in user's VPS list (and node summary
for admins) as context, and never receives the key itself. Test the saved key
from the same page; model names are configurable and fall back automatically
when a provider retires a model.

### Background image and hosting name

Admin → **Branding & Background** uploads a PNG/JPG/GIF/WebP background (max
8 MB, stored in `static/uploads/`), sets the dark overlay, and changes the
hosting name shown at the top of every page and in the browser title. The
default brand is **SK Hosting**.

### Discord bot commands

Slash commands: `/vps`, `/vps_action <id> <start|stop|restart>`,
`/nesting <id> <on|off>`, `/ask <question>`, `/uptime`, `/status`, `/add_admin`.
Prefix commands (default prefix `!`): `!help`, `!ping`, `!vps`, `!start <id>`,
`!stop <id>`, `!restart <id>`, `!nesting <id> on|off`, `!ai <question>`.

Prefix commands need the privileged **Message Content Intent** in the Discord
Developer Portal. If it is disabled the bot logs a warning, retries without the
intent and keeps answering slash commands. Set `OMEGA_BOT_PREFIX_COMMANDS=0` to
disable prefix commands explicitly. `discord.py` is now part of
`requirements.txt`, so `setup.sh` installs it.

### Connect a node by command

Admin → **Node Install / Uninstall** shows the
enrollment key and the exact command. On the node server run:

```bash
sudo bash scripts/omega-node-install.sh --bind=0.0.0.0   # remote panel must reach the agent
sudo bash scripts/omega-node-connect.sh \
  --panel http://PANEL_IP:5000 \
  --key ENROLLMENT_KEY \
  --name node-2 \
  --url http://NODE_IP:5001

# allow the agent port only from the panel
sudo ufw allow from PANEL_IP to any port 5001 proto tcp
```

Or run `sudo bash omega.sh` on the node and choose **3) Node install + connect**.
The panel stores the node with `is_local=0`, its agent URL and its token, so it can
create and manage VPS on that node immediately. Re-running the same command rotates
the stored token.

### Node install / uninstall commands

Admin → **Node Install / Uninstall** runs the agent scripts on this host, and the
same commands work from a terminal:

```bash
sudo bash scripts/omega-node-install.sh          # install / repair the node agent
sudo bash scripts/omega-node-install.sh --check  # service + health status
sudo bash scripts/omega-node-uninstall.sh        # stop, disable, remove the unit
sudo bash scripts/omega-node-uninstall.sh --purge
```

The uninstaller never deletes the shared panel directory in `/opt/omega-panel`.

### KVM and nesting switches

Every VPS has two switches on **VPS Switches** (`/features`, also linked in the sidebar)
and in the admin VPS Types table:

* **Nesting ON/OFF** - applied immediately with `security.nesting`, so Docker and nested
  VMs work inside the guest. No reinstall.
* **KVM ON/OFF** - moves a VM between the KVM backend and the non-KVM (QEMU TCG) backend.
  This reinstalls the VPS from its OS image, so the disk is wiped; the form requires the
  **wipe + reinstall** checkbox. LXC containers are not VMs and cannot be switched.
  The panel checks the host capability (`/dev/kvm`, QEMU) before touching the old VPS.

### Using the AI assistant

1. Admin -> **AI Settings**: paste the xAI Grok and/or Google Gemini key, choose the
   provider and model, then press **Send test request**.
2. The saved key is used everywhere: the floating **star** button at the bottom-right of
   every panel page, `POST /ai/chat`, Discord `/ask <question>` and `!ai <question>`.
3. The assistant receives the signed-in user's VPS list (type, status, nesting) and, for
   admins, node status, so it can answer questions about real servers. It never sees the
   API key.
4. Turn it off again with the **AI assistant enabled** checkbox; keys can be replaced or
   removed independently for each provider.

### Port forwarding

```bash
sudo bash scripts/omega-portforward.sh add --listen 8080 --to 10.0.0.5:80
sudo bash scripts/omega-portforward.sh list
sudo bash scripts/omega-portforward.sh remove --listen 8080
```

Each forward runs as `omega-forward-<port>.service` (socat), restarts automatically and
survives reboots. The same three actions are in the menu under **Port forwarding**.

### AI chats: member and admin

`/ai` is the AI chat page (sidebar: **AI Chat**). Members get the **Member chat**, which
only sees their own VPS. Admins get a second **Admin chat** tab that sees every VPS, node
status, user count and host capabilities, so it can answer fleet-level questions. Both use
the key saved in Admin -> AI Settings, and each tab keeps its own conversation. The
floating star widget stays a quick member chat.

### Converting an existing VPS

Open **VPS Switches** and pick a different backend for any VPS: `LXC container`,
`KVM ON (VM)` or `KVM OFF (Non-KVM)`. The switch is destructive by design - the VPS is
recreated from the same OS image, so the old disk is wiped and the **wipe + reinstall**
checkbox is mandatory. Nesting is a non-destructive ON/OFF switch. The same three backend
choices are available as radio switches on the create form, so a VPS can be born as LXC,
KVM or non-KVM.

### Node types and one-command node add (new)

Node install is now per type. Pick the type when you add the node:

| Type | Installs | Can create |
| --- | --- | --- |
| `lxc` | Incus (containers only) | LXC VPS |
| `kvm` | Incus + QEMU/KVM/libvirt (needs `/dev/kvm`) | LXC + KVM (+ non-KVM) |
| `incus` | everything | LXC + KVM + non-KVM |

**From the panel:** Nodes -> Add Node -> enter node name, the node VPS IP and the type ->
*Generate command* -> run the command as root on that VPS. It downloads the agent from the
panel, installs the chosen type, and connects the node. Example:

```bash
curl -fsSL 'http://PANEL_IP:5000/api/nodes/install.sh?key=KEY&name=node-1&ip=NODE_IP&type=kvm' | sudo bash
```

**By hand on the node:**

```bash
sudo bash scripts/omega-node-install.sh --type=kvm --bind=0.0.0.0
sudo bash scripts/omega-node-connect.sh --panel http://PANEL_IP:5000 --key KEY --name node-1 --url http://NODE_IP:5001
```

Fixed in this version: the node agent now authenticates with `/etc/omega-panel/node-token`
(the same token the panel stores). Before, the agent generated a different random key, so the
node was added fine (`/api/health` is open) but every VPS create returned `401 Unauthorized`.
An already-connected node is repaired by re-running the install command on it (same name).

## Verification

See `VERIFY.md` for the build checks. Host-level KVM, Incus daemon, storage quota behavior and guest-OS boot support must still be validated on the target server because those depend on the actual hardware, kernel and virtualization environment.
