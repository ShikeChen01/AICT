"""VMManager — QEMU/KVM sub-VM lifecycle management via libvirt.

v4: Desktop agents run in QEMU/KVM virtual machines with full graphical
environments. Each sub-VM gets a dedicated vCPU, 1.5 GB RAM, and runs its
own Ubuntu kernel with Xvfb + x11vnc + openbox + chromium.

This manager handles:
  - QCOW2 image cloning from base image (copy-on-write overlay)
  - libvirt domain definition, start, stop, destroy
  - Bridge networking with static IP + iptables DNAT
  - QCOW2 snapshot / restore for persistent VMs
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Optional

import config

# libvirt is optional — pool manager still starts for Docker-only mode if
# libvirt is not installed.  All VMManager methods raise RuntimeError if
# libvirt is unavailable.
try:
    import libvirt

    _LIBVIRT_AVAILABLE = True
except ImportError:
    libvirt = None  # type: ignore[assignment]
    _LIBVIRT_AVAILABLE = False


def _require_libvirt() -> None:
    if not _LIBVIRT_AVAILABLE:
        raise RuntimeError(
            "libvirt-python is not installed. Desktop sub-VMs require "
            "QEMU/KVM + libvirt. Install with: pip install libvirt-python"
        )


class VMManager:
    """Thin wrapper around libvirt for QEMU/KVM sub-VM operations."""

    def __init__(self) -> None:
        self._conn: Optional["libvirt.virConnect"] = None

    # ── Connection ────────────────────────────────────────────────────────────

    def _get_conn(self) -> "libvirt.virConnect":
        _require_libvirt()
        if self._conn is None or not self._conn.isAlive():
            self._conn = libvirt.open("qemu:///system")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ── QCOW2 image management ───────────────────────────────────────────────

    @staticmethod
    def _vm_image_path(vm_id: str) -> str:
        return os.path.join(config.DESKTOP_IMAGE_DIR, f"vm-{vm_id}.qcow2")

    @staticmethod
    def _ensure_image_dir() -> None:
        Path(config.DESKTOP_IMAGE_DIR).mkdir(parents=True, exist_ok=True)

    def clone_base_image(self, vm_id: str) -> str:
        """Create a QCOW2 overlay backed by the base image (copy-on-write)."""
        self._ensure_image_dir()
        image_path = self._vm_image_path(vm_id)
        if os.path.exists(image_path):
            raise FileExistsError(f"VM image already exists: {image_path}")

        base = config.DESKTOP_BASE_IMAGE
        if not os.path.exists(base):
            raise FileNotFoundError(f"Base QCOW2 image not found: {base}")

        subprocess.run(
            [
                "qemu-img",
                "create",
                "-f", "qcow2",
                "-b", base,
                "-F", "qcow2",
                image_path,
                f"{config.DESKTOP_DISK_QUOTA_GB}G",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return image_path

    def remove_image(self, vm_id: str) -> None:
        image_path = self._vm_image_path(vm_id)
        if os.path.exists(image_path):
            os.remove(image_path)

    # ── Networking ────────────────────────────────────────────────────────────

    @staticmethod
    def _static_ip_for_port(host_port: int) -> str:
        """Derive a static IP from the host port number.

        Port 30051 → 192.168.100.10, 30052 → 192.168.100.11, etc.
        """
        offset = host_port - config.DESKTOP_PORT_START + config.VM_IP_START
        prefix = config.VM_SUBNET.rsplit(".", 1)[0]  # "192.168.100"
        return f"{prefix}.{offset}"

    @staticmethod
    def setup_port_forward(host_port: int, vm_ip: str) -> None:
        """Add iptables DNAT rule: host_port → vm_ip:8080."""
        subprocess.run(
            [
                "iptables", "-t", "nat", "-A", "PREROUTING",
                "-p", "tcp", "--dport", str(host_port),
                "-j", "DNAT", "--to-destination", f"{vm_ip}:{config.CONTAINER_INTERNAL_PORT}",
            ],
            check=True,
            capture_output=True,
        )
        # Also add for localhost access on the host itself
        subprocess.run(
            [
                "iptables", "-t", "nat", "-A", "OUTPUT",
                "-p", "tcp", "-d", "127.0.0.1", "--dport", str(host_port),
                "-j", "DNAT", "--to-destination", f"{vm_ip}:{config.CONTAINER_INTERNAL_PORT}",
            ],
            check=True,
            capture_output=True,
        )

    @staticmethod
    def remove_port_forward(host_port: int, vm_ip: str) -> None:
        """Remove iptables DNAT rules for a specific host port."""
        for chain in ("PREROUTING", "OUTPUT"):
            if chain == "OUTPUT":
                extra = ["-d", "127.0.0.1"]
            else:
                extra = []
            try:
                subprocess.run(
                    [
                        "iptables", "-t", "nat", "-D", chain,
                        *extra,
                        "-p", "tcp", "--dport", str(host_port),
                        "-j", "DNAT", "--to-destination",
                        f"{vm_ip}:{config.CONTAINER_INTERNAL_PORT}",
                    ],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                pass  # Rule may not exist

    # ── libvirt domain XML ────────────────────────────────────────────────────

    def _domain_xml(
        self,
        vm_id: str,
        image_path: str,
        vm_ip: str,
        auth_token: str,
    ) -> str:
        """Generate libvirt domain XML for a desktop sub-VM."""
        ram_kib = int(config.DESKTOP_RAM_GB * 1024 * 1024)
        name = f"aict-vm-{vm_id}"

        return textwrap.dedent(f"""\
            <domain type='kvm'>
              <name>{name}</name>
              <memory unit='KiB'>{ram_kib}</memory>
              <vcpu placement='static'>{config.DESKTOP_VCPUS}</vcpu>
              <os>
                <type arch='x86_64'>hvm</type>
                <boot dev='hd'/>
              </os>
              <features>
                <acpi/>
                <apic/>
              </features>
              <cpu mode='host-passthrough'/>
              <clock offset='utc'/>
              <on_poweroff>destroy</on_poweroff>
              <on_reboot>restart</on_reboot>
              <on_crash>destroy</on_crash>
              <devices>
                <emulator>/usr/bin/qemu-system-x86_64</emulator>
                <disk type='file' device='disk'>
                  <driver name='qemu' type='qcow2' cache='writeback'/>
                  <source file='{image_path}'/>
                  <target dev='vda' bus='virtio'/>
                </disk>
                <interface type='bridge'>
                  <source bridge='{config.VM_BRIDGE}'/>
                  <model type='virtio'/>
                </interface>
                <serial type='pty'>
                  <target port='0'/>
                </serial>
                <console type='pty'>
                  <target type='serial' port='0'/>
                </console>
                <graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'/>
                <video>
                  <model type='virtio' heads='1' primary='yes'/>
                </video>
                <channel type='unix'>
                  <target type='virtio' name='org.qemu.guest_agent.0'/>
                </channel>
              </devices>
              <metadata>
                <aict:vm xmlns:aict='http://aict.dev/libvirt/metadata/1.0'>
                  <aict:vm_id>{vm_id}</aict:vm_id>
                  <aict:auth_token>{auth_token}</aict:auth_token>
                  <aict:static_ip>{vm_ip}</aict:static_ip>
                </aict:vm>
              </metadata>
            </domain>
        """)

    # ── VM lifecycle ──────────────────────────────────────────────────────────

    def create_vm(
        self,
        vm_id: str,
        host_port: int,
        auth_token: str,
    ) -> str:
        """Create and start a desktop sub-VM.

        Returns the libvirt domain name.
        """
        _require_libvirt()

        # 1. Clone QCOW2 base image
        image_path = self.clone_base_image(vm_id)

        # 2. Compute static IP
        vm_ip = self._static_ip_for_port(host_port)

        # 3. Setup port forwarding
        try:
            self.setup_port_forward(host_port, vm_ip)
        except Exception:
            self.remove_image(vm_id)
            raise

        # 4. Define and start libvirt domain
        conn = self._get_conn()
        xml = self._domain_xml(vm_id, image_path, vm_ip, auth_token)
        try:
            dom = conn.defineXML(xml)
            dom.create()  # start the domain
        except Exception:
            self.remove_port_forward(host_port, vm_ip)
            self.remove_image(vm_id)
            raise

        return dom.name()

    def destroy_vm(self, vm_id: str, host_port: int) -> None:
        """Stop and undefine a sub-VM, remove its image and port forwarding."""
        domain_name = f"aict-vm-{vm_id}"
        vm_ip = self._static_ip_for_port(host_port)

        conn = self._get_conn()
        try:
            dom = conn.lookupByName(domain_name)
            if dom.isActive():
                dom.destroy()
            dom.undefineFlags(
                libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE
                | libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA
            )
        except Exception:
            pass  # Domain may already be gone

        self.remove_port_forward(host_port, vm_ip)
        self.remove_image(vm_id)

    def is_running(self, vm_id: str) -> bool:
        """Check if a sub-VM domain is active."""
        _require_libvirt()
        domain_name = f"aict-vm-{vm_id}"
        try:
            conn = self._get_conn()
            dom = conn.lookupByName(domain_name)
            return dom.isActive() == 1
        except Exception:
            return False

    def list_vms(self) -> list[str]:
        """List all AICT-managed VM domain names."""
        _require_libvirt()
        conn = self._get_conn()
        result = []
        for dom_id in conn.listDomainsID():
            dom = conn.lookupByID(dom_id)
            if dom.name().startswith("aict-vm-"):
                result.append(dom.name())
        # Also list defined-but-stopped domains
        for name in conn.listDefinedDomains():
            if name.startswith("aict-vm-") and name not in result:
                result.append(name)
        return result

    def stop_vm(self, vm_id: str) -> None:
        """Gracefully shut down a sub-VM."""
        _require_libvirt()
        domain_name = f"aict-vm-{vm_id}"
        conn = self._get_conn()
        try:
            dom = conn.lookupByName(domain_name)
            if dom.isActive():
                dom.shutdown()
        except Exception:
            pass

    def start_vm(self, vm_id: str) -> None:
        """Start a stopped sub-VM."""
        _require_libvirt()
        domain_name = f"aict-vm-{vm_id}"
        conn = self._get_conn()
        dom = conn.lookupByName(domain_name)
        if not dom.isActive():
            dom.create()

    # ── Snapshot / restore ────────────────────────────────────────────────────

    def create_snapshot(self, vm_id: str, label: str = "") -> str:
        """Create a QCOW2 internal snapshot of a sub-VM.

        Returns the snapshot name.
        """
        _require_libvirt()
        domain_name = f"aict-vm-{vm_id}"
        snap_name = label or f"snap-{int(time.time())}"
        conn = self._get_conn()
        dom = conn.lookupByName(domain_name)

        snap_xml = textwrap.dedent(f"""\
            <domainsnapshot>
              <name>{snap_name}</name>
              <description>AICT snapshot: {label}</description>
            </domainsnapshot>
        """)
        dom.snapshotCreateXML(snap_xml, 0)
        return snap_name

    def restore_snapshot(self, vm_id: str, snap_name: str) -> None:
        """Revert a sub-VM to a named snapshot."""
        _require_libvirt()
        domain_name = f"aict-vm-{vm_id}"
        conn = self._get_conn()
        dom = conn.lookupByName(domain_name)
        snap = dom.snapshotLookupByName(snap_name, 0)
        dom.revertToSnapshot(snap, 0)

    def list_snapshots(self, vm_id: str) -> list[str]:
        """List snapshot names for a sub-VM."""
        _require_libvirt()
        domain_name = f"aict-vm-{vm_id}"
        conn = self._get_conn()
        try:
            dom = conn.lookupByName(domain_name)
            return dom.snapshotListNames(0)
        except Exception:
            return []

    # ── File migration (promote/demote) ───────────────────────────────────────

    @staticmethod
    def migrate_files_to_vm(
        docker_volume: str,
        vm_id: str,
        vm_ip: str,
        auth_token: str,
        timeout: int = 30,
    ) -> bool:
        """Copy working directory from Docker volume to sub-VM via rsync.

        The sandbox server inside the VM exposes /workspace. We use rsync
        over SSH (cloud-init configures SSH key on VM) or fall back to
        tar + netcat for simplicity.
        """
        # Get Docker volume mountpoint
        try:
            result = subprocess.run(
                ["docker", "volume", "inspect", docker_volume, "--format", "{{.Mountpoint}}"],
                capture_output=True, text=True, check=True,
            )
            src_path = result.stdout.strip()
        except subprocess.CalledProcessError:
            return False

        if not src_path or not os.path.isdir(src_path):
            return False

        # rsync to VM workspace
        try:
            subprocess.run(
                [
                    "rsync", "-a", "--timeout", str(timeout),
                    f"{src_path}/",
                    f"root@{vm_ip}:/workspace/",
                ],
                check=True,
                capture_output=True,
                timeout=timeout + 10,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def migrate_files_from_vm(
        vm_ip: str,
        docker_volume: str,
        timeout: int = 30,
    ) -> bool:
        """Copy working directory from sub-VM back to Docker volume via rsync."""
        try:
            result = subprocess.run(
                ["docker", "volume", "inspect", docker_volume, "--format", "{{.Mountpoint}}"],
                capture_output=True, text=True, check=True,
            )
            dst_path = result.stdout.strip()
        except subprocess.CalledProcessError:
            return False

        if not dst_path:
            return False

        try:
            subprocess.run(
                [
                    "rsync", "-a", "--timeout", str(timeout),
                    f"root@{vm_ip}:/workspace/",
                    f"{dst_path}/",
                ],
                check=True,
                capture_output=True,
                timeout=timeout + 10,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
