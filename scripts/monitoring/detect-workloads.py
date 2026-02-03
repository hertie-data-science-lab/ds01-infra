#!/usr/bin/env python3
"""
DS01 Workload Detection Scanner

Discovers all GPU workloads on the system and builds a unified inventory.

Core functionality:
- Detects ALL containers (running/stopped) and classifies by origin
- Detects host GPU processes via nvidia-smi + /proc attribution
- Persists state to /var/lib/ds01/workload-inventory.json
- Emits events on state transitions (new workload, exited workload)
- Transient filtering: GPU processes must persist for 2 scans before events emitted

Design:
- Runs as oneshot script (invoked by systemd timer every 30s)
- Near-real-time inventory (max 30s lag from polling interval)
- System GPU processes excluded from user-facing inventory
- Safe import fallback for event logging (scanner must work even if logging fails)

Usage:
    python3 detect-workloads.py              # Full scan, save inventory, emit events
    python3 detect-workloads.py --dry-run    # Scan only, print to stdout
    python3 detect-workloads.py --verbose    # Enable debug logging
"""

from __future__ import annotations

import sys
import json
import logging
import subprocess
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add lib directory to path for ds01_events import
SCRIPT_DIR = Path(__file__).parent
LIB_DIR = SCRIPT_DIR.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

# Safe import of event logging (with fallback to no-op)
try:
    from ds01_events import log_event
except ImportError:
    def log_event(*args, **kwargs) -> bool:
        return False

# Lazy import docker (only when needed)
docker = None


# Constants
INVENTORY_FILE = Path("/var/lib/ds01/workload-inventory.json")
SYSTEM_GPU_PROCESSES = {
    "nvidia-persistenced",
    "nv-hostengine",
    "dcgm",
    "dcgmi",
    "nvidia-smi",
    "Xorg",
    "X",
}
SCAN_TIMEOUT = 25  # Must be shorter than 30s timer interval

# Logging setup
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def classify_container(container) -> str:
    """
    Classify container by origin/creation method.

    Priority order:
    1. ds01.managed label -> "ds01-managed"
    2. devcontainer.* labels -> "devcontainer"
    3. com.docker.compose.project label -> "compose"
    4. Container name starts with "vsc-" -> "devcontainer"
    5. Default -> "raw-docker"

    Args:
        container: Docker container object

    Returns:
        Classification string
    """
    labels = container.labels or {}

    # Priority 1: DS01-managed containers
    if labels.get("ds01.managed") == "true":
        return "ds01-managed"

    # Priority 2: Devcontainer labels
    if any(key.startswith("devcontainer.") for key in labels.keys()):
        return "devcontainer"

    # Priority 3: Docker Compose
    if "com.docker.compose.project" in labels:
        return "compose"

    # Priority 4: VSCode devcontainer name pattern
    if container.name.startswith("vsc-"):
        return "devcontainer"

    # Default
    return "raw-docker"


def has_gpu_access(container) -> bool:
    """
    Check if container has GPU access via any mechanism.

    Checks:
    - HostConfig.Runtime == "nvidia"
    - HostConfig.DeviceRequests with nvidia capabilities
    - HostConfig.Devices with nvidia paths

    Args:
        container: Docker container object

    Returns:
        True if container has GPU access
    """
    try:
        # Reload to get full HostConfig
        container.reload()
        host_config = container.attrs.get("HostConfig", {})

        # Check 1: nvidia runtime
        if host_config.get("Runtime") == "nvidia":
            return True

        # Check 2: DeviceRequests (modern --gpus flag)
        device_requests = host_config.get("DeviceRequests", [])
        for request in device_requests:
            # Capabilities is a list of lists of strings
            capabilities = request.get("Capabilities", [])
            for cap_list in capabilities:
                if "gpu" in cap_list or "nvidia" in cap_list:
                    return True

        # Check 3: Legacy device mapping
        devices = host_config.get("Devices", [])
        for device in devices:
            path = device.get("PathOnHost", "")
            if "nvidia" in path:
                return True

        return False

    except Exception as e:
        logger.warning(f"Error checking GPU access for {container.name}: {e}")
        return False


def get_container_user(container) -> str:
    """
    Determine the user who owns this container.

    Priority order:
    1. ds01.user label
    2. aime.mlc.USER label
    3. devcontainer.local_folder label (extract username from path)
    4. Process owner from /proc (if container is running)
    5. "unknown"

    Args:
        container: Docker container object

    Returns:
        Username string
    """
    labels = container.labels or {}

    # Priority 1: ds01.user label
    if "ds01.user" in labels:
        return labels["ds01.user"]

    # Priority 2: AIME MLC label
    if "aime.mlc.USER" in labels:
        return labels["aime.mlc.USER"]

    # Priority 3: Devcontainer path
    if "devcontainer.local_folder" in labels:
        # Extract username from path like /home/alice/project
        folder = labels["devcontainer.local_folder"]
        parts = Path(folder).parts
        if len(parts) >= 3 and parts[1] == "home":
            return parts[2]

    # Priority 4: Process owner (if running)
    if container.status == "running":
        try:
            # Get container PID
            pid = container.attrs.get("State", {}).get("Pid")
            if pid and pid > 0:
                # Read /proc/{pid}/status for Uid
                status_file = Path(f"/proc/{pid}/status")
                if status_file.exists():
                    for line in status_file.read_text().splitlines():
                        if line.startswith("Uid:"):
                            uid = line.split()[1]  # Real UID is first field
                            # Resolve UID to username
                            result = subprocess.run(
                                ["getent", "passwd", uid],
                                capture_output=True,
                                text=True,
                                timeout=1,
                            )
                            if result.returncode == 0:
                                username = result.stdout.split(":")[0]
                                return username
        except Exception as e:
            logger.debug(f"Could not get process owner for {container.name}: {e}")

    # Fallback
    return "unknown"


def get_container_gpu_devices(container) -> list[str]:
    """
    Extract GPU device IDs allocated to this container.

    Checks:
    1. ds01.gpu.allocated label (format: "0:1" or "0")
    2. DeviceRequests device IDs

    Args:
        container: Docker container object

    Returns:
        List of GPU device strings, empty if no GPU
    """
    labels = container.labels or {}

    # Check ds01.gpu.allocated label
    if "ds01.gpu.allocated" in labels:
        return [labels["ds01.gpu.allocated"]]

    # Check DeviceRequests
    try:
        container.reload()
        host_config = container.attrs.get("HostConfig", {})
        device_requests = host_config.get("DeviceRequests", [])
        for request in device_requests:
            device_ids = request.get("DeviceIDs", [])
            if device_ids:
                return device_ids
    except Exception as e:
        logger.debug(f"Could not get GPU devices for {container.name}: {e}")

    return []


def scan_containers(client) -> dict[str, dict[str, Any]]:
    """
    Scan all containers and build inventory.

    Returns dict keyed by container ID (first 12 chars) with:
    - id: Container ID (short)
    - name: Container name
    - origin: Classification (ds01-managed, devcontainer, compose, raw-docker)
    - user: Owner username
    - has_gpu: Boolean GPU access flag
    - gpu_devices: List of GPU device IDs
    - status: Container status (running, exited, created, etc.)
    - image: Image name or ID

    Args:
        client: Docker client

    Returns:
        Dict of container entries keyed by container ID
    """
    try:
        containers = client.containers.list(all=True)
        inventory = {}

        for container in containers:
            container_id = container.id[:12]

            # Get image name
            image_name = "unknown"
            try:
                if container.image.tags:
                    image_name = container.image.tags[0]
                else:
                    image_name = container.image.id[:12]
            except Exception:
                pass

            inventory[container_id] = {
                "id": container_id,
                "name": container.name,
                "origin": classify_container(container),
                "user": get_container_user(container),
                "has_gpu": has_gpu_access(container),
                "gpu_devices": get_container_gpu_devices(container),
                "status": container.status,
                "image": image_name,
            }

        logger.info(f"Scanned {len(inventory)} containers")
        return inventory

    except Exception as e:
        logger.warning(f"Error scanning containers: {e}")
        return {}


def is_container_process(pid: int) -> bool:
    """
    Check if process is running inside a container.

    Reads /proc/{pid}/cgroup and checks for docker/containerd.

    Args:
        pid: Process ID

    Returns:
        True if containerised, False if host process
    """
    try:
        cgroup_file = Path(f"/proc/{pid}/cgroup")
        if not cgroup_file.exists():
            return False

        content = cgroup_file.read_text()
        return "docker" in content or "containerd" in content

    except (FileNotFoundError, PermissionError):
        return False


def get_process_user(pid: int) -> str:
    """
    Get username of process owner.

    Reads /proc/{pid}/status for UID, then resolves via getent.

    Args:
        pid: Process ID

    Returns:
        Username or "unknown"
    """
    try:
        status_file = Path(f"/proc/{pid}/status")
        if not status_file.exists():
            return "unknown"

        for line in status_file.read_text().splitlines():
            if line.startswith("Uid:"):
                uid = line.split()[1]  # Real UID

                # Resolve UID to username
                result = subprocess.run(
                    ["getent", "passwd", uid],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )

                if result.returncode == 0:
                    username = result.stdout.split(":")[0]
                    return username

        return "unknown"

    except Exception:
        return "unknown"


def get_process_cmdline(pid: int) -> str:
    """
    Get process command line.

    Reads /proc/{pid}/cmdline (null-byte separated).

    Args:
        pid: Process ID

    Returns:
        Command line string or empty string
    """
    try:
        cmdline_file = Path(f"/proc/{pid}/cmdline")
        if not cmdline_file.exists():
            return ""

        # Read as bytes (null-byte separators)
        cmdline_bytes = cmdline_file.read_bytes()

        # Split on null bytes and decode
        parts = cmdline_bytes.split(b"\0")
        parts = [p.decode("utf-8", errors="replace") for p in parts if p]

        return " ".join(parts)

    except Exception:
        return ""


def scan_host_gpu_processes() -> dict[str, dict[str, Any]]:
    """
    Scan host GPU processes via nvidia-smi.

    Returns dict keyed by PID (as string) with:
    - pid: Process ID
    - user: Owner username
    - cmdline: Command line
    - gpu_memory_mb: GPU memory usage in MB
    - gpu_uuid: GPU UUID

    Excludes:
    - Container processes
    - System GPU processes (nvidia-persistenced, DCGM, Xorg, etc.)

    Returns:
        Dict of process entries keyed by PID string
    """
    try:
        # Run nvidia-smi with timeout
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory,gpu_uuid",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            logger.warning(f"nvidia-smi failed: {result.stderr}")
            return {}

        processes = {}

        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue

            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 3:
                continue

            pid = int(parts[0])
            gpu_memory_mb = int(parts[1])
            gpu_uuid = parts[2]

            # Skip container processes
            if is_container_process(pid):
                continue

            # Get process details
            user = get_process_user(pid)
            cmdline = get_process_cmdline(pid)

            # Get process name (first element of cmdline)
            process_name = ""
            if cmdline:
                process_name = Path(cmdline.split()[0]).name

            # Skip system GPU processes
            if process_name in SYSTEM_GPU_PROCESSES:
                logger.debug(f"Skipping system process: {process_name} (PID {pid})")
                continue

            processes[str(pid)] = {
                "pid": pid,
                "user": user,
                "cmdline": cmdline,
                "gpu_memory_mb": gpu_memory_mb,
                "gpu_uuid": gpu_uuid,
            }

        logger.info(f"Scanned {len(processes)} host GPU processes")
        return processes

    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi timed out")
        return {}
    except Exception as e:
        logger.warning(f"Error scanning host GPU processes: {e}")
        return {}


def load_inventory() -> dict[str, Any]:
    """
    Load previous inventory from disk.

    Returns:
        Previous inventory dict or default structure
    """
    try:
        if INVENTORY_FILE.exists():
            with open(INVENTORY_FILE) as f:
                inventory = json.load(f)
                logger.debug("Loaded existing inventory")
                return inventory
        else:
            logger.debug("No existing inventory found")
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in inventory file: {e}")
    except Exception as e:
        logger.warning(f"Error loading inventory: {e}")

    # Return default structure
    return {
        "last_scan": None,
        "containers": {},
        "host_processes": {},
        "_pending_processes": {},
    }


def save_inventory(inventory: dict[str, Any]) -> None:
    """
    Save inventory to disk atomically.

    Writes to temporary file first, then renames to avoid corruption.

    Args:
        inventory: Inventory dict to save
    """
    try:
        # Ensure parent directory exists
        INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file
        tmp_file = INVENTORY_FILE.parent / f"{INVENTORY_FILE.name}.tmp"
        with open(tmp_file, "w") as f:
            json.dump(inventory, f, indent=2)

        # Atomic rename
        os.rename(tmp_file, INVENTORY_FILE)
        logger.debug(f"Saved inventory to {INVENTORY_FILE}")

    except OSError as e:
        logger.warning(f"Failed to save inventory: {e}")


def detect_transitions(old: dict[str, Any], new: dict[str, Any]) -> None:
    """
    Detect state transitions and emit events.

    Compares old and new inventories to find:
    - New containers
    - Exited containers
    - Container status changes
    - New host GPU processes
    - Exited host GPU processes

    Args:
        old: Previous inventory dict
        new: Current inventory dict
    """
    old_containers = old.get("containers", {})
    new_containers = new.get("containers", {})
    old_processes = old.get("host_processes", {})
    new_processes = new.get("host_processes", {})

    # Container transitions
    for container_id, container in new_containers.items():
        if container_id not in old_containers:
            # New container discovered
            log_event(
                "detection.container_discovered",
                user=container.get("user"),
                source="detect-workloads",
                container_id=container_id,
                name=container.get("name"),
                origin=container.get("origin"),
                has_gpu=container.get("has_gpu"),
                image=container.get("image"),
            )
        else:
            # Check for status changes
            old_status = old_containers[container_id].get("status")
            new_status = container.get("status")
            if old_status != new_status:
                log_event(
                    "detection.container_status_changed",
                    user=container.get("user"),
                    source="detect-workloads",
                    container_id=container_id,
                    name=container.get("name"),
                    old_status=old_status,
                    new_status=new_status,
                )

    # Exited containers
    for container_id, container in old_containers.items():
        if container_id not in new_containers:
            log_event(
                "detection.container_exited",
                user=container.get("user"),
                source="detect-workloads",
                container_id=container_id,
                name=container.get("name"),
                origin=container.get("origin"),
            )

    # Host process transitions (confirmed processes only)
    for pid, process in new_processes.items():
        if pid not in old_processes:
            # New process (already confirmed via transient filter)
            log_event(
                "detection.host_gpu_process_discovered",
                user=process.get("user"),
                source="detect-workloads",
                pid=process.get("pid"),
                cmdline=process.get("cmdline"),
                gpu_memory_mb=process.get("gpu_memory_mb"),
                gpu_uuid=process.get("gpu_uuid"),
            )

    # Exited processes
    for pid, process in old_processes.items():
        if pid not in new_processes:
            log_event(
                "detection.host_gpu_process_exited",
                user=process.get("user"),
                source="detect-workloads",
                pid=process.get("pid"),
                cmdline=process.get("cmdline"),
            )


def apply_transient_filter(
    old_inventory: dict[str, Any],
    scanned_processes: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """
    Apply 2-scan persistence filter for host GPU processes.

    Transient processes (< 2 scans) are not included in the main inventory
    and do not generate events. This avoids noise from short-lived processes.

    Process lifecycle:
    1. First scan: Add to _pending_processes (not host_processes, no event)
    2. Second scan: Still present? Move to host_processes, emit discovered event
    3. Second scan: Gone? Remove from _pending_processes silently (no event)

    Args:
        old_inventory: Previous inventory with _pending_processes
        scanned_processes: Current scan results (all processes)

    Returns:
        Filtered process dict (confirmed processes only)
    """
    old_processes = old_inventory.get("host_processes", {})
    pending_processes = old_inventory.get("_pending_processes", {})

    confirmed_processes = {}

    for pid, process in scanned_processes.items():
        if pid in old_processes:
            # Already confirmed - keep it
            confirmed_processes[pid] = process
        elif pid in pending_processes:
            # Was pending, now confirmed (2nd scan) - promote to confirmed
            confirmed_processes[pid] = process
            logger.debug(f"Process {pid} confirmed (2 scans)")
        else:
            # First time seeing this process - will be added to pending by caller
            logger.debug(f"Process {pid} pending (1 scan)")

    return confirmed_processes


def merge_timestamps(old_inventory: dict[str, Any], new_inventory: dict[str, Any]) -> None:
    """
    Merge detected_at timestamps from old inventory into new.

    Preserves timestamps for entries that existed in previous scan.
    Adds new timestamps for new entries.

    Args:
        old_inventory: Previous inventory
        new_inventory: Current inventory (modified in place)
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Merge container timestamps
    old_containers = old_inventory.get("containers", {})
    new_containers = new_inventory.get("containers", {})
    for container_id, container in new_containers.items():
        if container_id in old_containers and "detected_at" in old_containers[container_id]:
            # Preserve existing timestamp
            container["detected_at"] = old_containers[container_id]["detected_at"]
        else:
            # New container - add timestamp
            container["detected_at"] = now

    # Merge process timestamps
    old_processes = old_inventory.get("host_processes", {})
    new_processes = new_inventory.get("host_processes", {})
    for pid, process in new_processes.items():
        if pid in old_processes and "detected_at" in old_processes[pid]:
            # Preserve existing timestamp
            process["detected_at"] = old_processes[pid]["detected_at"]
        else:
            # New process - add timestamp
            process["detected_at"] = now


def run_scan() -> dict[str, Any]:
    """
    Execute complete scan cycle.

    Returns inventory dict with:
    - last_scan: UTC ISO timestamp
    - containers: Dict of container entries
    - host_processes: Dict of host process entries

    Returns:
        Inventory dict
    """
    global docker

    # Lazy import docker
    if docker is None:
        import docker as docker_module
        docker = docker_module

    # Create docker client
    try:
        client = docker.from_env()
    except Exception as e:
        logger.error(f"Failed to create Docker client: {e}")
        return {
            "last_scan": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "containers": {},
            "host_processes": {},
        }

    # Scan containers
    containers = scan_containers(client)

    # Scan host GPU processes
    host_processes = scan_host_gpu_processes()

    # Build inventory
    inventory = {
        "last_scan": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "containers": containers,
        "host_processes": host_processes,
    }

    return inventory


def main() -> int:
    """
    Main entry point.

    Returns:
        0 on success, 1 on error
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="DS01 Workload Detection Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  detect-workloads.py              # Full scan, save inventory, emit events
  detect-workloads.py --dry-run    # Scan only, print to stdout
  detect-workloads.py --verbose    # Enable debug logging
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print inventory to stdout without saving or emitting events",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    try:
        # Load previous inventory
        old_inventory = load_inventory()

        # Run scan
        logger.info("Starting workload scan")
        scanned_inventory = run_scan()

        # Apply transient filter for host processes
        scanned_processes = scanned_inventory.get("host_processes", {})
        confirmed_processes = apply_transient_filter(old_inventory, scanned_processes)

        # Update pending processes list
        old_processes = old_inventory.get("host_processes", {})
        old_pending = old_inventory.get("_pending_processes", {})
        new_pending = {}

        for pid, process in scanned_processes.items():
            if pid not in old_processes and pid not in old_pending:
                # First time seeing this process - add to pending
                new_pending[pid] = process

        # Build new inventory with confirmed processes
        new_inventory = {
            "last_scan": scanned_inventory["last_scan"],
            "containers": scanned_inventory["containers"],
            "host_processes": confirmed_processes,
            "_pending_processes": new_pending,
        }

        # Detect transitions and emit events (skip if dry-run)
        if not args.dry_run:
            detect_transitions(old_inventory, new_inventory)

        # Merge timestamps from old inventory
        merge_timestamps(old_inventory, new_inventory)

        # Save or print
        if args.dry_run:
            # Print to stdout
            print(json.dumps(new_inventory, indent=2))
        else:
            # Save to disk
            save_inventory(new_inventory)

        # Summary
        num_containers = len(new_inventory.get("containers", {}))
        num_gpu_containers = sum(
            1 for c in new_inventory.get("containers", {}).values() if c.get("has_gpu")
        )
        num_host_processes = len(new_inventory.get("host_processes", {}))
        num_pending = len(new_inventory.get("_pending_processes", {}))

        logger.info(
            f"Scan complete: {num_containers} containers ({num_gpu_containers} with GPU), "
            f"{num_host_processes} host GPU processes ({num_pending} pending)"
        )

        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
