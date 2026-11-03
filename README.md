# Omega Panel V4 Stable latest

**Primary author:** MrZetrix  
**Original project/reference credit:** NafiGamer — `nafigamer0`

A clean-source rebuild of the uploaded Omega Panel V3 Incus package. V4 keeps the same core product concept—web VPS dashboard, users, admin controls, Incus, SSH/SSHX and node status—but removes the fragile obfuscated runtime and destructive setup behavior.

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

## Install

Run on a supported systemd host as root:

```bash
sudo bash setup.sh
```

For LXD compatibility probing/installation too:

```bash
sudo bash setup.sh --with-lxd
```

The installer prefers the host distro Python, installs dependencies in `venv/`, creates a random first-admin password when no `OMEGA_ADMIN_PASSWORD` is supplied, and writes it to `/var/lib/omega-panel/first_admin_credentials.txt` with restrictive permissions.

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

## Verification

See `VERIFY.md` for the build checks. Host-level KVM, Incus daemon, storage quota behavior and guest-OS boot support must still be validated on the target server because those depend on the actual hardware, kernel and virtualization environment.
