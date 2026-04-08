#!/usr/bin/env python3
"""
DS01 Prometheus Exporter (Slim Version)
Exposes DS01-specific allocation and business metrics only.

GPU hardware metrics (utilization, memory, temperature) are provided by DCGM Exporter.
This exporter focuses on DS01-specific metrics that DCGM cannot provide:
- User → GPU allocation mapping
- Container interface tracking (orchestration, atomic, other)
- User-level MIG-equivalent counts
- Event log counts
- MIG slot mapping for DCGM metric joins

Metrics prefix: ds01_
Port: 9101
Endpoint: /metrics
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================================
# Configuration
# ============================================================================

EXPORTER_PORT = int(os.environ.get("DS01_EXPORTER_PORT", 9101))
BIND_ADDRESS = os.environ.get("DS01_EXPORTER_BIND", "127.0.0.1")

# DCGM Exporter URL for querying GPU_I_ID values (for MIG slot mapping)
# Default to localhost:9400 since DS01 exporter runs on host via systemd
DCGM_EXPORTER_URL = os.environ.get("DCGM_EXPORTER_URL", "http://127.0.0.1:9400/metrics")

INFRA_ROOT = Path("/opt/ds01-infra")
STATE_DIR = Path("/var/lib/ds01")
LOG_DIR = Path("/var/log/ds01")
GROUPS_DIR = INFRA_ROOT / "config/runtime/groups"

# Module paths for reuse
GPU_STATE_READER = INFRA_ROOT / "scripts/docker/gpu-state-reader.py"
USERNAME_UTILS = INFRA_ROOT / "scripts/lib/username_utils.py"

# ============================================================================
# Module Loading (reuse existing DS01 code)
# ============================================================================

_gpu_state_module = None


def _load_module(name: str, path: Path):
    """Dynamically load a Python module from file path."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_gpu_state_module():
    """Get cached gpu-state-reader module."""
    global _gpu_state_module
    if _gpu_state_module is None:
        _gpu_state_module = _load_module("gpu_state_reader", GPU_STATE_READER)
    return _gpu_state_module


_username_utils_module = None


def get_username_utils_module():
    """Get cached username_utils module."""
    global _username_utils_module
    if _username_utils_module is None:
        _username_utils_module = _load_module("username_utils", USERNAME_UTILS)
    return _username_utils_module


# ============================================================================
# Metric Collection
# ============================================================================
# NOTE: GPU hardware metrics (utilization, memory, temperature) removed.
# These are now provided by DCGM Exporter which has native driver access.
# This exporter focuses on DS01-specific allocation and business metrics.
# ============================================================================


def collect_allocation_metrics() -> List[str]:
    """Collect GPU allocation metrics from gpu-state-reader."""
    lines = []

    try:
        state_mod = get_gpu_state_module()
        reader = state_mod.get_reader()

        # Get all allocations
        allocations = reader.get_all_allocations()

        lines.append("# HELP ds01_gpu_allocated GPU/MIG slot allocation status (1=allocated)")
        lines.append("# TYPE ds01_gpu_allocated gauge")

        for slot, data in allocations.items():
            containers = data.get("containers", [])
            users = data.get("users", {})
            interfaces = data.get("interfaces", {})

            for container in containers:
                user = list(users.keys())[0] if users else "unknown"
                interface = list(interfaces.keys())[0] if interfaces else "unknown"
                lines.append(
                    f'ds01_gpu_allocated{{gpu_slot="{slot}",container="{container}",'
                    f'user="{user}",interface="{interface}"}} 1'
                )

        # Containers by interface
        by_interface = reader.get_all_containers_by_interface()

        lines.append("# HELP ds01_containers_total Total DS01 containers by status and interface")
        lines.append("# TYPE ds01_containers_total gauge")

        for interface, containers in by_interface.items():
            running = sum(1 for c in containers if c.get("running"))
            stopped = len(containers) - running
            lines.append(
                f'ds01_containers_total{{status="running",interface="{interface}"}} {running}'
            )
            lines.append(
                f'ds01_containers_total{{status="stopped",interface="{interface}"}} {stopped}'
            )

    except Exception as e:
        lines.append(f"# Error collecting allocation metrics: {e}")

    return lines


def collect_user_metrics() -> List[str]:
    """Collect per-user resource metrics."""
    lines = []

    try:
        state_mod = get_gpu_state_module()
        reader = state_mod.get_reader()

        # Get unique users from allocations
        by_interface = reader.get_all_containers_by_interface()
        users = set()
        for containers in by_interface.values():
            for c in containers:
                if c.get("user") and c["user"] != "unknown":
                    users.add(c["user"])

        lines.append("# HELP ds01_user_mig_allocated MIG-equivalents allocated to user")
        lines.append("# TYPE ds01_user_mig_allocated gauge")

        lines.append("# HELP ds01_user_containers_count Number of containers for user")
        lines.append("# TYPE ds01_user_containers_count gauge")

        for user in users:
            mig_total = reader.get_user_mig_total(user)
            user_allocs = reader.get_user_allocations(user)
            container_count = len(user_allocs)

            lines.append(f'ds01_user_mig_allocated{{user="{user}"}} {mig_total}')
            lines.append(f'ds01_user_containers_count{{user="{user}"}} {container_count}')

    except Exception as e:
        lines.append(f"# Error collecting user metrics: {e}")

    return lines


# Event log cache for efficient parsing
_event_cache: Dict[str, int] = {}
_event_cache_timestamp: float = 0
_event_cache_file_pos: int = 0
EVENT_CACHE_TTL = 60  # Refresh cache every 60 seconds


def collect_event_counts() -> List[str]:
    """Collect event counts from events.jsonl (last 24 hours).

    Uses incremental file reading with caching to avoid O(n) parsing on every scrape.
    """
    global _event_cache, _event_cache_timestamp, _event_cache_file_pos

    lines = []
    events_file = LOG_DIR / "events.jsonl"

    if not events_file.exists():
        return lines

    try:
        now = time.time()
        cutoff = now - 86400  # 24 hours ago

        # Check if we need to refresh the cache
        cache_age = now - _event_cache_timestamp
        if cache_age > EVENT_CACHE_TTL:
            # Full refresh: re-read file from stored position or start
            file_size = events_file.stat().st_size

            # If file is smaller than last position, it was truncated - start fresh
            if file_size < _event_cache_file_pos:
                _event_cache = {}
                _event_cache_file_pos = 0

            # Read only new content since last position
            with open(events_file, "r") as f:
                # If starting fresh, scan the whole file but only count recent events
                if _event_cache_file_pos == 0:
                    event_counts: Dict[str, int] = {}
                    for line in f:
                        try:
                            event = json.loads(line.strip())
                            ts_str = event.get("timestamp", "")
                            if ts_str:
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if ts.timestamp() > cutoff:
                                    event_type = event.get("event_type", "unknown")
                                    event_counts[event_type] = event_counts.get(event_type, 0) + 1
                        except (json.JSONDecodeError, ValueError):
                            continue
                    _event_cache = event_counts
                else:
                    # Seek to last known position and read new lines
                    f.seek(_event_cache_file_pos)
                    for line in f:
                        try:
                            event = json.loads(line.strip())
                            ts_str = event.get("timestamp", "")
                            if ts_str:
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if ts.timestamp() > cutoff:
                                    event_type = event.get("event_type", "unknown")
                                    _event_cache[event_type] = _event_cache.get(event_type, 0) + 1
                        except (json.JSONDecodeError, ValueError):
                            continue

                # Update position and timestamp
                _event_cache_file_pos = f.tell()

            _event_cache_timestamp = now

            # Prune old events every hour (approximate by reducing counts)
            # This is a simple approach - for exact counts, would need to track timestamps
            if cache_age > 3600:
                # Decay counts by ~4% per hour (rough approximation for 24h window)
                _event_cache = {k: max(0, int(v * 0.96)) for k, v in _event_cache.items()}
                _event_cache = {k: v for k, v in _event_cache.items() if v > 0}

        lines.append("# HELP ds01_events_24h_total Events in last 24 hours by type")
        lines.append("# TYPE ds01_events_24h_total gauge")

        for event_type, count in _event_cache.items():
            safe_type = event_type.replace('"', '\\"')
            lines.append(f'ds01_events_24h_total{{event_type="{safe_type}"}} {count}')

    except Exception as e:
        lines.append(f"# Error collecting event counts: {e}")

    return lines


LIFECYCLE_EVENT_MAP: Dict[str, Dict[str, str]] = {
    "maintenance.idle_kill": {"action": "idle_kill"},
    "maintenance.runtime_kill": {"action": "runtime_kill"},
    "resource.oom_kill": {"action": "oom_kill"},
    "alert.gpu_warning": {"action": "gpu_warning"},
    "alert.memory_warning": {"action": "memory_warning"},
    "alert.container_warning": {"action": "container_warning"},
    "bare_metal.warning": {"action": "bare_metal_warning"},
}


def collect_lifecycle_metrics() -> List[str]:
    """Emit lifecycle event counters from events.jsonl cache.

    Depends on collect_event_counts() having been called first to populate _event_cache.
    Always emits all label combinations (with 0 for missing) so dashboard panels don't break
    when an event type hasn't occurred yet.
    """
    lines = []
    lines.append("# HELP ds01_lifecycle_events_total Lifecycle enforcement events in last 24 hours")
    lines.append("# TYPE ds01_lifecycle_events_total gauge")

    for event_type, labels in LIFECYCLE_EVENT_MAP.items():
        count = _event_cache.get(event_type, 0)
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        lines.append(f"ds01_lifecycle_events_total{{{label_str}}} {count}")

    return lines


def collect_ssh_metrics() -> List[str]:
    """Collect active SSH session counts per user.

    Parses output of the `who` command (available on all Linux systems, no dependencies).
    Emits per-user gauge and a total aggregate gauge.
    """
    lines = []
    try:
        result = subprocess.run(["who"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return lines

        # Count sessions per user
        sessions: Dict[str, int] = {}
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            # who output format: "username  pts/0  2026-02-25 10:30 (192.168.1.1)"
            parts = line.split()
            if parts:
                user = parts[0]
                sessions[user] = sessions.get(user, 0) + 1

        lines.append("# HELP ds01_ssh_sessions_active Active SSH sessions per user")
        lines.append("# TYPE ds01_ssh_sessions_active gauge")
        for user, count in sorted(sessions.items()):
            safe_user = user.replace('"', '\\"')
            lines.append(f'ds01_ssh_sessions_active{{user="{safe_user}"}} {count}')

        lines.append("# HELP ds01_ssh_sessions_total Total active SSH sessions")
        lines.append("# TYPE ds01_ssh_sessions_total gauge")
        total = sum(sessions.values())
        lines.append(f"ds01_ssh_sessions_total {total}")

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        lines.append(f"# Error collecting SSH metrics: {e}")

    return lines


def collect_system_metrics() -> List[str]:
    """Collect basic system metrics."""
    lines = []

    try:
        # Disk usage for /var/lib/ds01
        if STATE_DIR.exists():
            stat = os.statvfs(STATE_DIR)
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bfree * stat.f_frsize
            used = total - free

            lines.append("# HELP ds01_state_disk_bytes Disk usage for DS01 state directory")
            lines.append("# TYPE ds01_state_disk_bytes gauge")
            lines.append(f'ds01_state_disk_bytes{{type="total"}} {total}')
            lines.append(f'ds01_state_disk_bytes{{type="used"}} {used}')
            lines.append(f'ds01_state_disk_bytes{{type="free"}} {free}')

    except Exception as e:
        lines.append(f"# Error collecting system metrics: {e}")

    return lines


def collect_unmanaged_metrics() -> List[str]:
    """Collect metrics for GPU containers outside DS01 tracking.

    Unmanaged containers bypass the docker wrapper (e.g., Docker Compose v2)
    and may have unrestricted GPU access.
    """
    lines = []

    try:
        state_mod = get_gpu_state_module()
        reader = state_mod.get_reader()
        unmanaged = reader.get_unmanaged_gpu_containers()

        lines.append("# HELP ds01_unmanaged_gpu_container Unmanaged container with GPU access")
        lines.append("# TYPE ds01_unmanaged_gpu_container gauge")

        for c in unmanaged:
            name = c.get("name", "unknown").replace('"', '\\"')
            user = c.get("user", "unknown").replace('"', '\\"')
            gpu_count = c.get("gpu_count", 0)
            access_type = c.get("access_type", "unknown")
            running = "true" if c.get("running") else "false"

            # Convert -1 to "ALL" for display
            gpu_display = "ALL" if gpu_count == -1 else str(gpu_count)

            lines.append(
                f"ds01_unmanaged_gpu_container{{"
                f'container="{name}",user="{user}",gpu_count="{gpu_display}",'
                f'access_type="{access_type}",running="{running}"}} 1'
            )

        # Summary metrics
        lines.append("")
        lines.append("# HELP ds01_unmanaged_gpu_count Total unmanaged GPU containers")
        lines.append("# TYPE ds01_unmanaged_gpu_count gauge")
        lines.append(f"ds01_unmanaged_gpu_count {len(unmanaged)}")

        running_count = sum(1 for c in unmanaged if c.get("running"))
        lines.append("")
        lines.append("# HELP ds01_unmanaged_gpu_running Running unmanaged GPU containers")
        lines.append("# TYPE ds01_unmanaged_gpu_running gauge")
        lines.append(f"ds01_unmanaged_gpu_running {running_count}")

    except Exception as e:
        lines.append(f"# Error collecting unmanaged metrics: {e}")

    return lines


# ============================================================================
# MIG Slot Mapping (for joining with DCGM metrics)
# ============================================================================

# Cache for MIG slot mapping (refreshed periodically)
_mig_mapping_cache: Dict[str, Dict] = {}
_mig_mapping_cache_timestamp: float = 0
MIG_MAPPING_CACHE_TTL = 60  # Refresh every 60 seconds


def _parse_nvidia_smi_mig_topology() -> Dict[int, List[Tuple[int, str]]]:
    """Parse nvidia-smi -L output to get MIG device indices and UUIDs.

    Returns:
        Dict mapping GPU index to list of (device_idx, mig_uuid) tuples
    """
    result: Dict[int, List[Tuple[int, str]]] = {}

    try:
        output = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10)
        if output.returncode != 0:
            return result

        current_gpu: Optional[int] = None

        for line in output.stdout.split("\n"):
            # Match GPU line: "GPU 2: NVIDIA A100-PCIE-40GB (UUID: GPU-xxx)"
            gpu_match = re.match(r"^GPU (\d+):", line)
            if gpu_match:
                current_gpu = int(gpu_match.group(1))
                continue

            # Match MIG line: "  MIG 1g.10gb Device 0: (UUID: MIG-xxx)"
            mig_match = re.match(r"^\s+MIG.*Device\s+(\d+):\s+\(UUID:\s+(MIG-[^)]+)\)", line)
            if mig_match and current_gpu is not None:
                device_idx = int(mig_match.group(1))
                mig_uuid = mig_match.group(2)
                if current_gpu not in result:
                    result[current_gpu] = []
                result[current_gpu].append((device_idx, mig_uuid))

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return result


def _query_dcgm_gpu_i_ids() -> Dict[int, List[int]]:
    """Query DCGM exporter to get GPU_I_ID values per GPU.

    Returns:
        Dict mapping GPU index to list of GPU_I_ID values (sorted)
    """
    result: Dict[int, List[int]] = {}

    try:
        req = urllib.request.Request(DCGM_EXPORTER_URL, method="GET")
        req.add_header("Accept", "text/plain")

        with urllib.request.urlopen(req, timeout=5) as response:
            content = response.read().decode("utf-8")

            # Parse metrics to extract gpu and GPU_I_ID labels
            # Example: DCGM_FI_DEV_SM_CLOCK{gpu="2",...,GPU_I_ID="3",...} 210
            for line in content.split("\n"):
                if 'GPU_I_ID="' not in line:
                    continue

                # Extract gpu label
                gpu_match = re.search(r'gpu="(\d+)"', line)
                gpu_i_id_match = re.search(r'GPU_I_ID="(\d+)"', line)

                if gpu_match and gpu_i_id_match:
                    gpu_idx = int(gpu_match.group(1))
                    gpu_i_id = int(gpu_i_id_match.group(1))

                    if gpu_idx not in result:
                        result[gpu_idx] = set()
                    result[gpu_idx].add(gpu_i_id)

    except (urllib.error.URLError, OSError, TimeoutError):
        pass

    # Convert sets to sorted lists
    return {gpu: sorted(list(ids)) for gpu, ids in result.items()}


def collect_mig_slot_mapping() -> List[str]:
    """Export MIG slot info for joining with DCGM metrics.

    This metric allows Prometheus to join DS01 allocation data (which uses
    gpu_slot format like "2.0") with DCGM metrics (which use GPU_I_ID labels).

    Correlation approach:
    1. Parse nvidia-smi -L to get MIG device indices (0,1,2,3) and UUIDs per GPU
    2. Query DCGM metrics to get GPU_I_ID values (3,4,5,6) per GPU
    3. Sort both lists - they're in the same relative order
    4. Map by position: sorted_nvidia_smi[i] ↔ sorted_dcgm_gpu_i_id[i]

    Exports:
        ds01_mig_slot_info{gpu="2", gpu_i_id="3", slot="2.0", mig_uuid="MIG-xxx"} 1
    """
    global _mig_mapping_cache, _mig_mapping_cache_timestamp

    lines = []

    try:
        now = time.time()

        # Check cache
        if now - _mig_mapping_cache_timestamp < MIG_MAPPING_CACHE_TTL and _mig_mapping_cache:
            # Use cached mapping
            pass
        else:
            # Refresh mapping
            nvidia_smi_topology = _parse_nvidia_smi_mig_topology()
            dcgm_gpu_i_ids = _query_dcgm_gpu_i_ids()

            new_cache: Dict[str, Dict] = {}

            for gpu_idx, mig_devices in nvidia_smi_topology.items():
                dcgm_ids = dcgm_gpu_i_ids.get(gpu_idx, [])

                # Sort nvidia-smi devices by device index
                sorted_mig = sorted(mig_devices, key=lambda x: x[0])

                # Warn if count mismatch (indicates topology change not yet reflected)
                if len(sorted_mig) != len(dcgm_ids):
                    print(
                        f"[ds01-exporter] WARNING: GPU {gpu_idx} MIG count mismatch: "
                        f"nvidia-smi={len(sorted_mig)}, DCGM={len(dcgm_ids)}. "
                        f"Consider restarting DCGM exporter.",
                        file=sys.stderr,
                    )

                # Map by position: nvidia-smi device[i] ↔ dcgm_ids[i]
                for i, (device_idx, mig_uuid) in enumerate(sorted_mig):
                    slot = f"{gpu_idx}.{device_idx}"
                    gpu_i_id = dcgm_ids[i] if i < len(dcgm_ids) else None

                    new_cache[slot] = {
                        "gpu": str(gpu_idx),
                        "gpu_i_id": str(gpu_i_id) if gpu_i_id is not None else "",
                        "slot": slot,
                        "mig_uuid": mig_uuid,
                        "device_idx": str(device_idx),
                    }

            _mig_mapping_cache = new_cache
            _mig_mapping_cache_timestamp = now

        # Generate metrics from cache
        lines.append("# HELP ds01_mig_slot_info MIG slot mapping for DCGM metric joins")
        lines.append("# TYPE ds01_mig_slot_info gauge")
        lines.append(
            "# Labels: gpu (parent GPU), gpu_i_id (DCGM instance ID), slot (DS01 format), mig_uuid"
        )

        mapped_count = 0
        unmapped_count = 0
        for slot, info in _mig_mapping_cache.items():
            if info["gpu_i_id"]:  # Only export if we have a GPU_I_ID mapping
                lines.append(
                    f'ds01_mig_slot_info{{gpu="{info["gpu"]}",gpu_i_id="{info["gpu_i_id"]}",'
                    f'slot="{info["slot"]}",mig_uuid="{info["mig_uuid"]}"}} 1'
                )
                mapped_count += 1
            else:
                unmapped_count += 1

        # Mapping health metric (for alerting on topology mismatches)
        lines.append("")
        lines.append("# HELP ds01_mig_mapping_status MIG slot mapping health (1=ok, 0=mismatch)")
        lines.append("# TYPE ds01_mig_mapping_status gauge")
        mapping_ok = 1 if unmapped_count == 0 else 0
        lines.append(
            f'ds01_mig_mapping_status{{mapped="{mapped_count}",unmapped="{unmapped_count}"}} {mapping_ok}'
        )

        # Also export full GPUs (non-MIG) for completeness
        lines.append("")
        lines.append("# HELP ds01_gpu_slot_info Full GPU slot mapping")
        lines.append("# TYPE ds01_gpu_slot_info gauge")

        try:
            output = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,uuid,mig.mode.current", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if output.returncode == 0:
                for line in output.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        gpu_idx, gpu_uuid, mig_mode = parts[0], parts[1], parts[2]
                        if mig_mode.lower() == "disabled":
                            lines.append(
                                f'ds01_gpu_slot_info{{gpu="{gpu_idx}",slot="{gpu_idx}",'
                                f'gpu_uuid="{gpu_uuid}",mig_enabled="false"}} 1'
                            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    except Exception as e:
        lines.append(f"# Error collecting MIG slot mapping: {e}")

    return lines


# ============================================================================
# Group Membership & Per-User Resource Metrics
# ============================================================================

# Cache for group membership (refreshed periodically)
_group_membership_cache: Dict[str, Dict[str, str]] = {}  # sanitized -> {user, group}
_group_counts_cache: Dict[str, int] = {}
_group_membership_cache_timestamp: float = 0
GROUP_MEMBERSHIP_CACHE_TTL = 300  # Refresh every 5 minutes


def _load_group_membership() -> Tuple[Dict[str, Dict[str, str]], Dict[str, int]]:
    """Load group membership from .members files.

    Discovers groups dynamically by globbing *.members (excludes archived.members).

    Returns:
        Tuple of:
        - sanitized_to_full: maps sanitized username -> {user: full_username, group: group_name}
        - group_counts: maps group_name -> member count
    """
    sanitized_to_full: Dict[str, Dict[str, str]] = {}
    group_counts: Dict[str, int] = {}

    try:
        utils = get_username_utils_module()
    except Exception:
        return sanitized_to_full, group_counts

    for members_file in sorted(GROUPS_DIR.glob("*.members")):
        group = members_file.stem
        if group == "archived":
            continue

        count = 0
        try:
            for line in members_file.read_text().splitlines():
                line = line.split("#")[0].strip()
                if not line:
                    continue
                count += 1
                sanitized = utils.sanitize_username_for_slice(line)
                sanitized_to_full[sanitized] = {"user": line, "group": group}
        except OSError:
            continue
        group_counts[group] = count

    return sanitized_to_full, group_counts


def _get_group_membership() -> Tuple[Dict[str, Dict[str, str]], Dict[str, int]]:
    """Get cached group membership data."""
    global _group_membership_cache, _group_counts_cache, _group_membership_cache_timestamp

    now = time.time()
    if now - _group_membership_cache_timestamp > GROUP_MEMBERSHIP_CACHE_TTL:
        mapping, counts = _load_group_membership()
        _group_membership_cache = mapping
        _group_counts_cache = counts
        _group_membership_cache_timestamp = now

    return _group_membership_cache, _group_counts_cache


def collect_user_group_info() -> List[str]:
    """Collect user-to-group mapping for Prometheus joins.

    Enables queries like:
        count by (group)(ds01_gpu_allocated * on(user) group_left(group) ds01_user_group_info)
    """
    lines = []
    mapping, counts = _get_group_membership()

    lines.append("# HELP ds01_user_group_info User group membership (1=member)")
    lines.append("# TYPE ds01_user_group_info gauge")

    for info in mapping.values():
        user = info["user"].replace('"', '\\"')
        group = info["group"]
        lines.append(f'ds01_user_group_info{{user="{user}",group="{group}"}} 1')

    lines.append("")
    lines.append("# HELP ds01_group_members_total Total members per group")
    lines.append("# TYPE ds01_group_members_total gauge")

    for group, count in sorted(counts.items()):
        lines.append(f'ds01_group_members_total{{group="{group}"}} {count}')

    return lines


def _detect_cgroup_root() -> Tuple[str, str]:
    """Detect cgroup hierarchy root for ds01.slice.

    Mirrors logic from collect-resource-stats.sh.

    Returns:
        Tuple of (root_path, version) where version is "v2" or "v1".
        Returns ("", "") if no cgroup hierarchy found.
    """
    # Pure v2: requires cgroup.controllers to distinguish from v1
    v2_path = Path("/sys/fs/cgroup/ds01.slice")
    if v2_path.is_dir() and Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        return str(v2_path), "v2"

    # v1 hybrid unified
    hybrid_path = Path("/sys/fs/cgroup/unified/ds01.slice")
    if hybrid_path.is_dir():
        return str(hybrid_path), "v1"

    # v1 memory controller (for memory.usage_in_bytes)
    memory_path = Path("/sys/fs/cgroup/memory/ds01.slice")
    if memory_path.is_dir():
        return str(memory_path), "v1"

    return "", ""


def collect_cgroup_per_user() -> List[str]:
    """Collect per-user CPU and memory usage from cgroup stats.

    Reads cpu.stat and memory.current from each user slice under ds01.slice.
    Reverse-maps sanitized slice names to full usernames via group membership files.
    """
    lines = []
    cgroup_root, cgroup_version = _detect_cgroup_root()
    if not cgroup_root:
        return lines

    mapping, _ = _get_group_membership()
    root_path = Path(cgroup_root)
    is_v1 = cgroup_version == "v1"

    lines.append(
        "# HELP ds01_user_cpu_usage_seconds_total Total CPU seconds consumed by user (from cgroup)"
    )
    lines.append("# TYPE ds01_user_cpu_usage_seconds_total counter")

    cpu_lines = []
    mem_lines = []

    # Iterate group slices
    for group_dir in sorted(root_path.iterdir()):
        if not group_dir.is_dir() or not group_dir.name.startswith("ds01-"):
            continue

        # Extract group name: ds01-student.slice -> student
        group_name = group_dir.name.replace(".slice", "").split("-", 1)[1]

        # Iterate user slices within group
        for user_dir in sorted(group_dir.iterdir()):
            if not user_dir.is_dir() or not user_dir.name.startswith("ds01-"):
                continue

            # Extract sanitized user: ds01-student-h_baker.slice -> h_baker
            slice_base = user_dir.name.replace(".slice", "")
            # Remove "ds01-{group}-" prefix
            prefix = f"ds01-{group_name}-"
            if not slice_base.startswith(prefix):
                continue
            sanitized_user = slice_base[len(prefix) :]

            # Reverse-map to full username
            info = mapping.get(sanitized_user)
            if info:
                full_user = info["user"]
                group = info["group"]
            else:
                full_user = sanitized_user
                group = group_name

            safe_user = full_user.replace('"', '\\"')

            # Read CPU usage
            if is_v1:
                cpu_stat_file = user_dir / "cpuacct.usage"
                try:
                    raw = cpu_stat_file.read_text().strip()
                    # v1 cpuacct.usage is in nanoseconds
                    cpu_seconds = int(raw) / 1_000_000_000
                except (OSError, ValueError):
                    cpu_seconds = None
            else:
                cpu_stat_file = user_dir / "cpu.stat"
                cpu_seconds = None
                try:
                    for line in cpu_stat_file.read_text().splitlines():
                        if line.startswith("usage_usec "):
                            cpu_seconds = int(line.split()[1]) / 1_000_000
                            break
                except (OSError, ValueError):
                    pass

            if cpu_seconds is not None:
                cpu_lines.append(
                    f"ds01_user_cpu_usage_seconds_total"
                    f'{{user="{safe_user}",group="{group}"}} {cpu_seconds:.3f}'
                )

            # Read memory usage
            if is_v1:
                mem_file = user_dir / "memory.usage_in_bytes"
            else:
                mem_file = user_dir / "memory.current"

            try:
                mem_bytes = int(mem_file.read_text().strip())
                mem_lines.append(
                    f"ds01_user_memory_current_bytes"
                    f'{{user="{safe_user}",group="{group}"}} {mem_bytes}'
                )
            except (OSError, ValueError):
                pass

    lines.extend(cpu_lines)
    lines.append("")
    lines.append("# HELP ds01_user_memory_current_bytes Current memory usage by user (from cgroup)")
    lines.append("# TYPE ds01_user_memory_current_bytes gauge")
    lines.extend(mem_lines)

    return lines


def collect_all_metrics() -> str:
    """Collect all metrics and return as Prometheus text format."""
    lines = []

    # Metadata
    lines.append("# DS01 Prometheus Exporter (Slim Version)")
    lines.append("# GPU hardware metrics provided by DCGM Exporter")
    lines.append(f"# Scrape time: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    # Exporter info
    lines.append("# HELP ds01_exporter_info DS01 exporter information")
    lines.append("# TYPE ds01_exporter_info gauge")
    lines.append('ds01_exporter_info{version="2.3.0",type="slim"} 1')
    lines.append("")

    # Collect DS01-specific metrics only (allocation, user, events, system)
    # GPU/MIG hardware metrics are now provided by DCGM Exporter
    lines.extend(collect_allocation_metrics())
    lines.append("")
    lines.extend(collect_user_metrics())
    lines.append("")
    lines.extend(collect_event_counts())
    lines.append("")
    lines.extend(collect_lifecycle_metrics())
    lines.append("")
    lines.extend(collect_system_metrics())
    lines.append("")
    lines.extend(collect_mig_slot_mapping())
    lines.append("")
    lines.extend(collect_unmanaged_metrics())
    lines.append("")
    lines.extend(collect_ssh_metrics())
    lines.append("")
    lines.extend(collect_user_group_info())
    lines.append("")
    lines.extend(collect_cgroup_per_user())

    return "\n".join(lines) + "\n"


# ============================================================================
# HTTP Server
# ============================================================================


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for /metrics endpoint."""

    def do_GET(self):
        if self.path == "/metrics":
            try:
                metrics = collect_all_metrics()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.end_headers()
                self.wfile.write(metrics.encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Error: {e}\n".encode("utf-8"))

        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK\n")

        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """<!DOCTYPE html>
<html><head><title>DS01 Exporter</title></head>
<body>
<h1>DS01 Prometheus Exporter (Slim)</h1>
<p>GPU hardware metrics: Use DCGM Exporter (:9400)</p>
<p><a href="/metrics">Metrics</a> | <a href="/health">Health</a></p>
</body></html>"""
            self.wfile.write(html.encode("utf-8"))

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found\n")

    def log_message(self, format, *args):
        """Override to use custom logging format."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {args[0]}", file=sys.stderr)


def main():
    """Start the exporter HTTP server."""
    print(f"DS01 Prometheus Exporter (Slim) starting on {BIND_ADDRESS}:{EXPORTER_PORT}")
    print(f"Metrics endpoint: http://{BIND_ADDRESS}:{EXPORTER_PORT}/metrics")
    print("Note: GPU hardware metrics provided by DCGM Exporter")

    server = HTTPServer((BIND_ADDRESS, EXPORTER_PORT), MetricsHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
