# Omega Panel V4 Stable verification

This release was rebuilt from the uploaded V3 archive as clean, maintainable Python/Flask source.
The original V3 obfuscated `app.py` and `node.py` are preserved under `legacy_v3/` and are not executed.

## Static checks performed by the build environment
- Python bytecode compilation (`python -m compileall`)
- Import/startup checks with an isolated temporary SQLite database
- Flask route smoke tests for health, login, registration, dashboard, VM creation queue, and admin routes
- Bash syntax checks for all `.sh` files
- JSON/schema checks for translation and OS profile structures
- ZIP extraction + re-creation + integrity test

## Host-dependent checks
The build environment cannot expose your real server's `/dev/kvm`, Incus daemon, bridge, storage driver, or nested virtualization state. `setup.sh` therefore performs capability detection at install time and refuses VM provisioning when KVM is unavailable instead of falsely reporting success.

## Supported provisioning concepts
- Incus system containers (LXC/liblxc backend)
- Incus virtual machines (`--vm`, implemented by QEMU; KVM acceleration used when `/dev/kvm` is available)
- Host-side QEMU/KVM/libvirt package installation and checks
- Optional LXD snap compatibility detection without destructive Incus/LXD purges
- 2 vCPU / 8 GiB RAM / 25 GiB disk defaults per VPS
- Per-user VPS quota default 1, editable by admin
- Node CPU limit can be `UNL` (no panel-imposed CPU quota); physical hardware still remains the hard limit
- 24/7 systemd restart and periodic reconciliation
- Guest OS auto-update configuration during provisioning
- 20 UI languages, English default
- Dashboard live provisioning progress
- SSHX bridge helper
- Optional Pterodactyl panel installer helper (requires domain/email and final production configuration)
