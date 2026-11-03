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

## Verification

See `VERIFY.md` for the build checks. Host-level KVM, Incus daemon, storage quota behavior and guest-OS boot support must still be validated on the target server because those depend on the actual hardware, kernel and virtualization environment.
