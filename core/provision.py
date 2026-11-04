import subprocess
import time

def create_vps_container(container_name, image="ubuntu:22.04", cpu_cores=1, ram_mb=1024, root_password=""):
    """
    Creates an LXC VPS container and reliably sets the root password.
    """
    try:
        # 1. Create container if not exists
        create_cmd = f"lxc-create -n {container_name} -t download -- -d ubuntu -r jammy -a amd64"
        subprocess.run(create_cmd, shell=True, check=False)

        # 2. Start container
        subprocess.run(f"lxc-start -n {container_name}", shell=True, check=False)
        time.sleep(2) # Give container time to initialize init system

        # 3. Set root password reliably using multiple fallback methods
        if root_password:
            set_pwd_success = False

            # Method A: lxc-attach with chpasswd
            cmd_a = f"lxc-attach -n {container_name} -- bash -c 'echo root:{root_password} | chpasswd'"
            res_a = subprocess.run(cmd_a, shell=True, capture_output=True, text=True)
            if res_a.returncode == 0:
                set_pwd_success = True

            # Method B: Direct chroot inside host rootfs if attach fails
            if not set_pwd_success:
                rootfs_path = f"/var/lib/lxc/{container_name}/rootfs"
                cmd_b = f"echo 'root:{root_password}' | chroot {rootfs_path} chpasswd"
                res_b = subprocess.run(cmd_b, shell=True, capture_output=True, text=True)
                if res_b.returncode == 0:
                    set_pwd_success = True

            # Method C: Direct shadow file edit / passwd pipe fallback
            if not set_pwd_success:
                cmd_c = f"lxc-attach -n {container_name} -- passwd root <<EOF\n{root_password}\n{root_password}\nEOF"
                res_c = subprocess.run(cmd_c, shell=True, capture_output=True, text=True)
                if res_c.returncode == 0:
                    set_pwd_success = True

            if not set_pwd_success:
                raise Exception("Failed to update root password using all available provision methods.")

        return {"status": "success", "message": f"VPS {container_name} created successfully with root password configured."}

    except Exception as e:
        return {"status": "error", "message": str(e)}
