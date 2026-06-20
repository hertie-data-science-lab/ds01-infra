#!/usr/bin/env python3
"""
GPU Allocator Smart - Stateless GPU Allocation Manager
Uses Docker labels as single source of truth. No state files maintained.
Reads current state from Docker via gpu-state-reader.py.

Updated for DS01 Layered Architecture:
- Interface-specific state handling:
  - Orchestration: Binary state model (running/removed only)
  - Atomic/Docker/Other: Full state model (created/running/stopped/removed)
- GPU hold behavior varies by interface
"""

import fcntl
import importlib.util
import json
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Interface constants (from gpu-state-reader.py)
INTERFACE_ORCHESTRATION = "orchestration"
INTERFACE_ATOMIC = "atomic"
INTERFACE_API = "api"
INTERFACE_DOCKER = "docker"
INTERFACE_OTHER = "other"

# Import our helper modules (handle hyphenated filenames)
SCRIPT_DIR = Path(__file__).parent
LIB_DIR = SCRIPT_DIR.parent / "lib"

# Import username sanitization utility
sys.path.insert(0, str(LIB_DIR))
try:
    from username_utils import sanitize_username_for_slice
except ImportError:
    # Fallback if library not available
    import re as _re

    def sanitize_username_for_slice(username: str) -> str:
        if not username:
            return username
        sanitized = username.replace("@", "-at-").replace(".", "-")
        sanitized = _re.sub(r"[^a-zA-Z0-9_:-]", "-", sanitized)
        sanitized = _re.sub(r"-+", "-", sanitized).strip("-")
        return sanitized


# Import event logging (with safe fallback - allocator must work even if logging fails)
try:
    from ds01_events import log_event
except ImportError:
    # Fallback: no-op function if ds01_events not available
    def log_event(*args, **kwargs) -> bool:
        return False


# Dynamic import for gpu-state-reader.py
spec = importlib.util.spec_from_file_location(
    "gpu_state_reader", str(SCRIPT_DIR / "gpu-state-reader.py")
)
gpu_state_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpu_state_module)
GPUStateReader = gpu_state_module.GPUStateReader

# Dynamic import for gpu-availability-checker.py
spec = importlib.util.spec_from_file_location(
    "gpu_availability_checker", str(SCRIPT_DIR / "gpu-availability-checker.py")
)
gpu_avail_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpu_avail_module)
GPUAvailabilityChecker = gpu_avail_module.GPUAvailabilityChecker


class GPUAllocatorSmart:
    # Safe defaults for fail-open when config loading fails
    SAFE_DEFAULTS = {"max_gpu_equivalents": 1.0, "allow_full_gpu": False, "priority": 10}

    def __init__(self, config_path="/opt/ds01-infra/config/runtime/resource-limits.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.state_reader = GPUStateReader()
        self.availability_checker = GPUAvailabilityChecker()

        # Logging
        self.log_dir = Path("/var/log/ds01")
        self.log_file = self.log_dir / "gpu-allocations.log"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Lock file for preventing race conditions
        self.lock_file = self.log_dir / "gpu-allocator.lock"

        # Import resource limits parser for aggregate quota checking
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from get_resource_limits import ResourceLimitParser

            self.resource_parser = ResourceLimitParser(config_path)
        except ImportError:
            # Fail-open: if parser unavailable, disable aggregate checking
            print(
                "Warning: ResourceLimitParser unavailable, aggregate GPU quota disabled",
                file=sys.stderr,
            )
            self.resource_parser = None

    def _timeout_handler(self, signum, frame):
        """Signal handler for lock timeout"""
        raise TimeoutError("GPU allocator lock acquisition timeout")

    def _acquire_lock(self, timeout=5):
        """Acquire exclusive lock for GPU allocation operations with timeout.

        Args:
            timeout: Lock acquisition timeout in seconds (default: 5)

        Returns:
            bool: True if lock acquired, False if timeout (fail-open)
        """
        # Set up timeout signal handler
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(timeout)

        try:
            self._lock_fd = open(self.lock_file, "w")
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
            signal.alarm(0)  # Cancel alarm on success
            return True
        except TimeoutError:
            signal.alarm(0)  # Cancel alarm
            # Fail-open: log error but continue without lock
            log_event(
                "gpu.allocation.lock_timeout",
                source="gpu_allocator",
                error=f"{timeout}s timeout exceeded",
                severity="warning",
            )
            print(
                f"Warning: GPU allocator lock timeout ({timeout}s), continuing without lock",
                file=sys.stderr,
            )
            self._lock_fd = None
            return False

    def _release_lock(self):
        """Release the exclusive lock"""
        if hasattr(self, "_lock_fd") and self._lock_fd:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            self._lock_fd.close()
            self._lock_fd = None

    def _load_config(self) -> dict:
        """Load YAML configuration and merge external group membership files."""
        try:
            if not self.config_path.exists():
                return {}

            with open(self.config_path) as f:
                config = yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError) as e:
            print(f"Error: Config loading failed: {e}", file=sys.stderr)
            return {}

        # Load group members from config/runtime/groups/{group}.members files
        groups_dir = self.config_path.parent / "groups"
        for group_name in config.get("groups") or {}:
            member_file = groups_dir / f"{group_name}.members"
            try:
                if member_file.exists():
                    members = []
                    with open(member_file) as f:
                        for line in f:
                            line = line.split("#")[0].strip()
                            if line:
                                members.append(line)
                    if members:
                        inline = config["groups"][group_name].get("members", [])
                        config["groups"][group_name]["members"] = list(set(members + inline))
            except (OSError, PermissionError):
                pass  # Fall back to inline members if file unreadable

        return config

    def _get_user_limits(self, username: str) -> dict:
        """Get user's resource limits from config (merges defaults + group/override).

        Supports both original and sanitized usernames in config lookups.
        Tries original username first, then sanitized form.
        """
        defaults = self.config.get("defaults", {}) or {}
        groups = self.config.get("groups", {}) or {}
        sanitized = sanitize_username_for_slice(username)

        # Check user_overrides first (highest priority) - try original, then sanitized
        user_overrides = self.config.get("user_overrides", {}) or {}
        override_key = None
        if username in user_overrides:
            override_key = username
        elif sanitized != username and sanitized in user_overrides:
            override_key = sanitized

        if override_key:
            base_limits = defaults.copy()
            base_limits.update(user_overrides[override_key])
            base_limits["_group"] = "override"
            return base_limits

        # Check groups - try original, then sanitized
        for group_name, group_config in groups.items():
            if group_config:
                members = group_config.get("members", [])
                if username in members or (sanitized != username and sanitized in members):
                    base_limits = defaults.copy()
                    group_limits = {k: v for k, v in group_config.items() if k != "members"}
                    base_limits.update(group_limits)
                    base_limits["_group"] = group_name
                    return base_limits

        # Default group
        default_group = self.config.get("default_group", "student")
        if default_group in groups:
            base_limits = defaults.copy()
            group_config = groups[default_group]
            group_limits = {k: v for k, v in group_config.items() if k != "members"}
            base_limits.update(group_limits)
            base_limits["_group"] = default_group
            return base_limits

        # Fallback to defaults only
        base_limits = defaults.copy()
        base_limits["_group"] = "default"
        # Fail-open: if config failed to load or is empty, return safe defaults
        return base_limits if base_limits else self.SAFE_DEFAULTS.copy()

    def _can_use_full_gpu(self, username: str) -> bool:
        """Check if user is allowed to use full (non-MIG) GPUs"""
        limits = self._get_user_limits(username)
        # Default to False - students and default users cannot use full GPUs
        return limits.get("allow_full_gpu", False)

    def _is_full_gpu(self, gpu_slot: str) -> bool:
        """Check if a GPU slot is a full GPU (not MIG instance)"""
        # Full GPU slots don't have a decimal (e.g., "0", "1")
        # MIG slots have decimal (e.g., "1.0", "1.2")
        return "." not in str(gpu_slot)

    def _get_user_priority(self, username: str) -> int:
        """Get user's allocation priority"""
        limits = self._get_user_limits(username)
        return limits.get("priority", 10)

    def _check_aggregate_gpu_quota(
        self, username: str, requested_gpueq: float
    ) -> tuple[bool, str | None]:
        """Check if user is within aggregate GPU quota, in GPU-equivalents (gpueq).

        This is the first layer of GPU quota enforcement - it compares the user's
        currently-held gpueq (compute fractions summed across ALL containers) plus
        the gpueq weight of the requested allocation against their aggregate
        gpu_limit. For full GPUs every weight is 1.0, so this is numerically
        identical to the old integer slot-count check. The second layer
        (max_gpu_equivalents) is checked separately.

        Args:
            username: User requesting GPU allocation
            requested_gpueq: GPU-equivalents being requested (1.0 per full GPU)

        Returns:
            Tuple of (allowed: bool, error_message: Optional[str])
            - (True, None) if allocation allowed
            - (False, error_msg) if quota would be exceeded
        """
        # Fail-open: if parser unavailable, allow allocation
        if self.resource_parser is None:
            return True, None

        try:
            # Get aggregate limits for user
            aggregate = self.resource_parser.get_aggregate_limits(username)

            # No aggregate limits = unlimited (admin group or unconfigured)
            if aggregate is None:
                return True, None

            # No gpu_limit in aggregate section = unlimited
            gpu_limit = aggregate.get("gpu_limit")
            if gpu_limit is None or gpu_limit == "unlimited":
                return True, None

            # Current gpueq held by this user (full GPUs each count 1.0)
            current_gpueq = self.state_reader.get_user_gpu_equivalents(username)

            # Check if new allocation would exceed limit (small epsilon for float noise)
            if current_gpueq + requested_gpueq > float(gpu_limit) + 1e-9:
                error_msg = (
                    "AGGREGATE_GPU_QUOTA_EXCEEDED "
                    f"({current_gpueq:g}+{requested_gpueq:g}>{float(gpu_limit):g})"
                )
                return False, error_msg

            return True, None

        except Exception as e:
            # Fail-open: on any error, log and allow allocation
            print(f"Warning: Aggregate GPU quota check failed: {e}", file=sys.stderr)
            return True, None

    def _log_event(
        self,
        event_type: str,
        user: str,
        container: str,
        gpu_id: str | None = None,
        reason: str = "",
    ):
        """Log event to centralized event logger (events.jsonl)"""
        # Map legacy event types to new event types
        event_map = {
            "ALLOCATED": "gpu.allocated",
            "REJECTED": "gpu.rejected",
            "RELEASED": "gpu.released",
        }
        mapped_type = event_map.get(event_type, f"gpu.{event_type.lower()}")

        # Build event-logger.py command
        event_logger = str(SCRIPT_DIR / "event-logger.py")
        args = [
            "python3",
            event_logger,
            "log",
            mapped_type,
            f"user={user}",
            f"container={container}",
        ]

        if gpu_id:
            args.append(f"gpu={gpu_id}")
        if reason:
            args.append(f"reason={reason}")

        # Log to centralized event system (fail silently - logging should never block allocation)
        try:
            subprocess.run(args, capture_output=True, check=False, timeout=10)
        except (subprocess.SubprocessError, OSError) as e:
            # Log failures to stderr for debugging, but don't block
            print(f"Warning: event logging failed: {e}", file=sys.stderr)

        # Also write to legacy log file for backwards compatibility
        timestamp = datetime.now().isoformat()
        log_entry = f"{timestamp}|{event_type}|{user}|{container}|{gpu_id or 'N/A'}|{reason}\n"
        try:
            with open(self.log_file, "a") as f:
                f.write(log_entry)
        except OSError as e:
            # Log failures to stderr for debugging, but don't block
            print(f"Warning: legacy log write failed: {e}", file=sys.stderr)

    def _get_container_interface(self, container: str) -> str:
        """
        Get the interface a container was created with.
        Returns: INTERFACE_ORCHESTRATION, INTERFACE_ATOMIC, INTERFACE_API,
        INTERFACE_DOCKER, or INTERFACE_OTHER
        """
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "ds01.interface"}}|||'
                    '{{index .Config.Labels "ds01.managed"}}|||'
                    "{{.Name}}",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            output = result.stdout.strip()
            parts = output.split("|||")
            interface_label = parts[0] if len(parts) > 0 else ""
            managed_label = parts[1] if len(parts) > 1 else ""
            name = parts[2].lstrip("/") if len(parts) > 2 else ""

            # Explicit interface label
            if interface_label and interface_label != "<no value>":
                return interface_label

            # DS01 managed but no explicit interface -> atomic (backward compat)
            if managed_label == "true":
                return INTERFACE_ATOMIC

            # AIME naming convention
            if "._." in name:
                return INTERFACE_ATOMIC

            # Default: docker direct
            return INTERFACE_DOCKER

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return INTERFACE_DOCKER

    def allocate_gpu(
        self,
        username: str,
        container: str,
        max_gpus: float | None = None,
        require_full_gpu: bool = False,
    ) -> tuple[str | None, str]:
        """
        Allocate GPU for a container (stateless - reads from Docker).
        Uses file lock to prevent race conditions.

        Args:
            username: User requesting GPU
            container: Container name (full tag: name._.userid)
            max_gpus: User's max GPU-equivalents quota (max_gpu_equivalents, float)
            require_full_gpu: If True, only allocate full GPU (not MIG)

        Returns:
            Tuple of (gpu_id, status_message)
            gpu_id: Slot ID (e.g., "1.2") if successful, None if failed
            status_message: "SUCCESS", "ALREADY_ALLOCATED", or error reason
        """
        try:
            # Acquire exclusive lock to prevent race conditions
            self._acquire_lock()

            # Check if container already has GPU (read from Docker)
            container_gpu = self.state_reader.get_container_gpu(container)
            if container_gpu:
                gpu_slot = container_gpu["gpu_slot"]
                return gpu_slot, "ALREADY_ALLOCATED"

            # Get user's limits
            limits = self._get_user_limits(username)

            # Max GPU-equivalents quota (gpueq). One full GPU = 1.0 gpueq, so for
            # full-GPU users this is numerically the old slot count.
            max_gpueq = self._get_user_max_gpu_equivalents(username, limits)
            if max_gpus is not None:
                max_gpueq = float(max_gpus)

            # Check full GPU permission if requesting full GPU
            if require_full_gpu and not self._can_use_full_gpu(username):
                group = limits.get("_group", "default")
                reason = f"FULL_GPU_NOT_ALLOWED (group={group}, allow_full_gpu=false)"
                self._log_event("REJECTED", username, container, reason=reason)

                # Log to centralized event system (best-effort)
                log_event(
                    "gpu.reject",
                    user=username,
                    source="gpu_allocator",
                    container=container,
                    reason=reason,
                )

                return None, reason

            # FIRST LAYER: Check aggregate GPU quota (per-user total cap), in gpueq.
            # A single full-GPU request weighs 1.0 gpueq.
            allowed, agg_error = self._check_aggregate_gpu_quota(username, 1.0)
            if not allowed:
                self._log_event("REJECTED", username, container, reason=agg_error)

                # Log to centralized event system (best-effort)
                log_event(
                    "gpu.reject",
                    user=username,
                    source="gpu_allocator",
                    container=container,
                    reason=agg_error,
                )

                return None, agg_error

            # SECOND LAYER: Check per-user total quota (max_gpu_equivalents), in gpueq.
            current_gpueq = self.state_reader.get_user_gpu_equivalents(username)

            # Requested full GPU weighs 1.0 gpueq (epsilon guards float noise).
            if current_gpueq + 1.0 > max_gpueq + 1e-9:
                reason = f"USER_AT_LIMIT ({current_gpueq:g}/{max_gpueq:g})"
                self._log_event("REJECTED", username, container, reason=reason)

                # Log to centralized event system (best-effort)
                log_event(
                    "gpu.reject",
                    user=username,
                    source="gpu_allocator",
                    container=container,
                    reason=reason,
                )

                return None, reason

            # Find available GPU
            # Pass allow_full_gpu to availability checker so it can filter appropriately
            allow_full = self._can_use_full_gpu(username)
            suggestion = self.availability_checker.suggest_gpu_for_user(
                username,
                max_gpueq,
                self._get_user_priority(username),
                require_full_gpu=require_full_gpu,
                allow_full_gpu=allow_full,
            )

            if not suggestion["success"]:
                reason = suggestion["error"]
                self._log_event("REJECTED", username, container, reason=reason)

                # Log to centralized event system (best-effort)
                log_event(
                    "gpu.reject",
                    user=username,
                    source="gpu_allocator",
                    container=container,
                    reason=reason,
                )

                return None, reason

            gpu_slot = suggestion["gpu_slot"]

            # Double-check full GPU permission (belt and suspenders)
            if self._is_full_gpu(gpu_slot) and not allow_full:
                reason = f"FULL_GPU_NOT_ALLOWED (got slot {gpu_slot}, user cannot use full GPUs)"
                self._log_event("REJECTED", username, container, reason=reason)

                # Log to centralized event system (best-effort)
                log_event(
                    "gpu.reject",
                    user=username,
                    source="gpu_allocator",
                    container=container,
                    reason=reason,
                )

                return None, reason

            # Log allocation to legacy log
            reason = f"ALLOCATED (user has {current_gpueq + 1.0:g}/{max_gpueq:g} gpueq)"
            self._log_event("ALLOCATED", username, container, gpu_slot, reason)

            # Log to centralized event system (best-effort, never blocks)
            log_event(
                "gpu.allocate",
                user=username,
                source="gpu_allocator",
                container=container,
                gpu_uuid=gpu_slot,
                reason=reason,
            )

            return gpu_slot, "SUCCESS"

        except Exception as e:
            print(f"Error: GPU allocation failed: {e}", file=sys.stderr)
            return None, f"INTERNAL_ERROR: {e}"
        finally:
            # Always release the lock
            self._release_lock()

    def allocate_multi_gpu(
        self,
        username: str,
        container: str,
        container_type: str,
        num_gpus: int = 1,
        prefer_full_gpu: bool = False,
    ) -> tuple[list, int, float, str]:
        """
        Allocate multiple GPU slots for a container.
        Supports distributed containers across multiple GPU slots.

        Quota enforcement runs two layers (see _check_external_quotas): the
        per-container distinct-unit cap (integer slots) and the aggregate
        fair-share quota (gpueq). Each slot is a full GPU today (MIG off), so its
        weight is 1.0 gpueq and the total gpueq equals the slot count.

        Args:
            username: User requesting GPUs
            container: Container name (full tag: name._.userid)
            container_type: Interface/type (api, devcontainer, compose, docker, unknown)
            num_gpus: Number of GPU slots to allocate
            prefer_full_gpu: Accepted for CLI compatibility; with slots == full GPUs
                it is a no-op (every slot is already a full GPU).

        Returns:
            Tuple of (gpu_slots, slot_count, total_gpueq, status_message)
            gpu_slots: List of GPU slot IDs (e.g., ["0", "1"])
            slot_count: Number of slots allocated (== len(gpu_slots))
            total_gpueq: Sum of the allocated slots' gpueq weights (1.0 per full GPU)
            status_message: "SUCCESS", "ALREADY_ALLOCATED", or error reason
        """
        try:
            # Acquire exclusive lock
            self._acquire_lock()

            # Check if container already has GPU(s)
            container_gpu = self.state_reader.get_container_gpu(container)
            if container_gpu:
                gpu_slot = container_gpu["gpu_slot"]
                gpueq = self.state_reader.get_slot_compute_fraction(gpu_slot)
                return [gpu_slot], 1, gpueq, "ALREADY_ALLOCATED"

            # Per-container cap: distinct GPU/MIG units per container (integer).
            max_per_container = self._get_user_per_container_cap(username)

            if num_gpus > max_per_container:
                reason = f"EXCEEDS_CONTAINER_LIMIT ({num_gpus}>{max_per_container})"
                self._log_event("REJECTED", username, container, reason=reason)
                return [], 0, 0.0, reason

            # Quota check with one self-heal retry (see allocate_external).
            ok, err = self._check_external_quotas(username, max_per_container, num_gpus)
            if not ok:
                self.release_stale_allocations(username)
                ok, err = self._check_external_quotas(username, max_per_container, num_gpus)
            if not ok:
                # Rename QUOTA_EXCEEDED → EXCEEDS_TOTAL_LIMIT for wire-format continuity
                # with the old allocate-multi contract expected by the wrapper.
                if err and err.startswith("QUOTA_EXCEEDED:"):
                    current = err.split(":", 1)[1].split("/")[0]
                    err = f"EXCEEDS_TOTAL_LIMIT ({num_gpus}+{current}>{max_per_container})"
                self._log_event("REJECTED", username, container, reason=err)
                return [], 0, 0.0, err

            # Allocate slots one at a time (each slot is a full GPU today).
            can_use_full = self._can_use_full_gpu(username)
            allocated_slots = []
            for _ in range(num_gpus):
                suggestion = self.availability_checker.suggest_gpu_for_user(
                    username,
                    max_per_container,
                    self._get_user_priority(username),
                    require_full_gpu=False,
                    allow_full_gpu=can_use_full,
                    exclude_slots=allocated_slots,
                )
                if suggestion["success"]:
                    allocated_slots.append(suggestion["gpu_slot"])
                else:
                    reason = suggestion.get("error", "NO_GPU_AVAILABLE")
                    self._log_event("REJECTED", username, container, reason=reason)
                    return [], 0, 0.0, reason

            if not allocated_slots:
                reason = "NO_GPU_AVAILABLE"
                self._log_event("REJECTED", username, container, reason=reason)
                return [], 0, 0.0, reason

            # Log allocation
            slots_str = ",".join(allocated_slots)
            slot_count = len(allocated_slots)
            # Total gpueq = sum of each slot's compute fraction (1.0 per full GPU).
            total_gpueq = sum(
                self.state_reader.get_slot_compute_fraction(slot) for slot in allocated_slots
            )
            reason = f"ALLOCATED ({slot_count} slot(s), {total_gpueq:g} gpueq: {slots_str})"
            self._log_event("ALLOCATED", username, container, slots_str, reason)

            return allocated_slots, slot_count, total_gpueq, "SUCCESS"

        finally:
            self._release_lock()

    def get_docker_id(self, gpu_slot: str) -> str:
        """
        Get Docker-compatible device ID for a GPU slot.
        For MIG instances, returns MIG UUID. For full GPUs, returns GPU UUID.
        """
        # Device permissions are 0666 so all users can query nvidia-smi directly
        try:
            result = subprocess.run(
                ["/usr/bin/nvidia-smi", "-L"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            nvidia_output = result.stdout

            # Parse output to find UUID for this slot
            import re

            current_gpu = None
            current_gpu_uuid = None
            for line in nvidia_output.split("\n"):
                # Match full GPU line: "GPU 0: NVIDIA A100 (UUID: GPU-xxx)"
                gpu_match = re.match(r"GPU (\d+):\s+[^(]+\(UUID:\s+(GPU-[a-f0-9-]+)\)", line)
                if gpu_match:
                    current_gpu = gpu_match.group(1)
                    current_gpu_uuid = gpu_match.group(2)

                    # If this is a full GPU slot (no decimal), return GPU UUID
                    if gpu_slot == current_gpu:
                        return current_gpu_uuid
                    continue

                # Match MIG line: "  MIG 1g.10gb Device 0: (UUID: MIG-xxx)"
                mig_match = re.match(
                    r"\s+MIG\s+\S+\s+Device\s+(\d+):\s+\(UUID:\s+(MIG-[a-f0-9-]+)\)", line
                )
                if mig_match and current_gpu is not None:
                    device_id = mig_match.group(1)
                    uuid = mig_match.group(2)
                    slot_id = f"{current_gpu}.{device_id}"

                    if slot_id == gpu_slot:
                        return uuid

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Warning: nvidia-smi query failed: {e}", file=sys.stderr)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Warning: parsing nvidia-smi output failed: {e}", file=sys.stderr)

        # Fallback: return slot ID
        return gpu_slot

    def release_gpu(self, container: str) -> tuple[str | None, str]:
        """
        Release GPU from container (stateless - just logs event).
        Actual release happens when container is removed from Docker.

        Args:
            container: Container name

        Returns:
            Tuple of (gpu_id, status_message)
        """
        # Read GPU assignment from Docker
        container_gpu = self.state_reader.get_container_gpu(container)

        if not container_gpu:
            return None, "NOT_ALLOCATED"

        gpu_slot = container_gpu["gpu_slot"]
        username = container_gpu["user"]

        # Log release to legacy log
        reason = "RELEASED (container removed/stopped)"
        self._log_event("RELEASED", username, container, gpu_slot, reason)

        # Log to centralized event system (best-effort)
        log_event(
            "gpu.release",
            user=username,
            source="gpu_allocator",
            container=container,
            gpu_uuid=gpu_slot,
            reason=reason,
        )

        return gpu_slot, "SUCCESS"

    def get_status(self) -> dict:
        """
        Get current GPU allocation status (reads from Docker).

        Returns:
            Dict with GPU allocation information
        """
        allocations = self.state_reader.get_all_allocations()
        summary = self.availability_checker.get_allocation_summary()

        return {
            "total_gpus": summary["total_gpus"],
            "allocated": summary["allocated"],
            "available": summary["available"],
            "utilization_percent": summary["utilization_percent"],
            "allocations": allocations,
        }

    def get_user_gpu_count(self, username: str) -> int:
        """Count how many GPUs a user currently has allocated (reads from Docker)"""
        user_allocs = self.state_reader.get_user_allocations(username)
        return len(user_allocs)

    def _get_user_max_gpu_equivalents(self, username: str, limits: dict | None = None) -> float:
        """Max fair-share quota for a user in GPU-equivalents (gpueq, float).

        Resolves max_gpu_equivalents first, then the legacy aliases max_gpu_slots /
        max_gpus_per_user / max_mig_instances (read for one release). null/unlimited
        maps to 999.0; absence falls back to 1.0.
        """
        if limits is None:
            limits = self._get_user_limits(username)
        sentinel = object()
        value = sentinel
        for key in (
            "max_gpu_equivalents",
            "max_gpu_slots",
            "max_gpus_per_user",
            "max_mig_instances",
        ):
            if key in limits:
                value = limits[key]
                break
        if value is sentinel:
            return 1.0
        if value is None or value == "unlimited":
            return 999.0
        return float(value)

    def _get_user_per_container_cap(self, username: str) -> int:
        """
        Max GPU slots a single container may request for this user.

        Single source of truth: the user's group profile (`max_gpu_slots_per_container`),
        applied uniformly across all submission paths (api, devcontainer, compose,
        docker, unknown). A user's budget is their budget regardless of how they
        submitted the work — we don't want per-interface quota drift.

        Returns 999 for unlimited (admin).
        """
        limits = self._get_user_limits(username)
        # New key first, then legacy aliases (read for one release).
        # None (present-but-null) means unlimited; absence falls back to default 1.
        for key in (
            "max_gpu_slots_per_container",
            "max_gpus_per_container",
            "max_mig_per_container",
        ):
            if key in limits:
                cap = limits[key]
                break
        else:
            cap = 1
        if cap is None or cap == "unlimited":
            return 999
        return int(cap)

    def _check_external_quotas(
        self, username: str, max_per_container: int, requested_slots: int
    ) -> tuple[bool, str | None]:
        """Run both quota layers for a multi/external request.

        Layer 1 (aggregate, gpueq): the user's total fair-share quota. Each
        requested slot is a full GPU today, so its weight is 1.0 gpueq.
        Layer 2 (per-container, integer slots): a single container may pin at
        most ``max_per_container`` distinct GPU/MIG units.
        """
        # Layer 1: aggregate gpueq quota (full-GPU request → requested_slots gpueq).
        allowed, agg_err = self._check_aggregate_gpu_quota(username, float(requested_slots))
        if not allowed:
            return False, agg_err
        # Layer 2: per-container distinct-unit cap (integer slots).
        current_slots = self.get_user_gpu_count(username)
        if current_slots + requested_slots > max_per_container:
            return False, f"QUOTA_EXCEEDED:{current_slots}/{max_per_container}"
        return True, None

    def allocate_external(self, username: str, container_type: str) -> tuple[str | None, str]:
        """
        Allocate GPU for external container (devcontainer, compose, docker run, etc.).

        This is called by docker-wrapper.sh for non-ds01 containers requesting GPU.
        The wrapper handles the retry loop; this method does a single allocation attempt.

        Args:
            username: User requesting GPU
            container_type: devcontainer, compose, docker, unknown

        Returns:
            Tuple of (docker_id, status_message)
            docker_id: GPU/MIG UUID if successful, None if failed
            status_message: "SUCCESS", "QUOTA_EXCEEDED:current/max", or error reason
        """
        try:
            # Acquire exclusive lock
            self._acquire_lock()

            # Per-container cap: user profile, interface-agnostic.
            max_allowed = self._get_user_per_container_cap(username)

            # Quota check with one self-heal retry. If quota is exhausted, clear
            # stale api/orchestration containers (binary-state cleanup on demand)
            # and re-check before rejecting. Catches the case where a prior job's
            # container wasn't rm'd by its dispatcher.
            ok, err = self._check_external_quotas(username, max_allowed, 1)
            if not ok:
                self.release_stale_allocations(username)
                ok, err = self._check_external_quotas(username, max_allowed, 1)
            if not ok:
                self._log_event("REJECTED", username, f"external-{container_type}", reason=err)
                return None, err

            # Find available GPU using availability checker
            allow_full = self._can_use_full_gpu(username)
            suggestion = self.availability_checker.suggest_gpu_for_user(
                username,
                max_allowed,
                self._get_user_priority(username),
                require_full_gpu=False,
                allow_full_gpu=allow_full,
            )

            if not suggestion["success"]:
                reason = suggestion.get("error", "NO_GPU_AVAILABLE")
                # Don't log as REJECTED here - the wrapper will retry
                return None, reason

            gpu_slot = suggestion["gpu_slot"]

            # Double-check full GPU permission (belt and suspenders)
            if self._is_full_gpu(gpu_slot) and not allow_full:
                reason = f"FULL_GPU_NOT_ALLOWED (got slot {gpu_slot}, user cannot use full GPUs)"
                self._log_event("REJECTED", username, f"external-{container_type}", reason=reason)
                return None, reason

            # Get Docker-compatible device ID
            docker_id = self.get_docker_id(gpu_slot)

            # Log allocation
            self._log_event(
                "ALLOCATED",
                username,
                f"external-{container_type}",
                gpu_slot,
                f"External container allocation, slot={gpu_slot}",
            )

            return docker_id, "SUCCESS"

        except Exception as e:
            print(f"Error: External GPU allocation failed: {e}", file=sys.stderr)
            return None, f"INTERNAL_ERROR: {e}"
        finally:
            self._release_lock()

    def release_stale_allocations(self, username: str = None) -> list:
        """
        Remove stopped containers that exceeded GPU hold timeout.
        Container removal automatically releases GPU (Docker labels gone = GPU freed).

        Interface-specific behavior:
        - Orchestration / API: No hold timeout, stopped containers removed immediately
        - Atomic/Docker/Other: Respect gpu_hold_after_stop timeout

        Args:
            username: Optional - only check this user's containers (None = all users)

        Returns:
            List of (container, reason) tuples for removed containers
        """
        import re
        from datetime import timedelta

        def parse_duration(duration_str: str) -> timedelta | None:
            """Parse duration string like '24h', '0.5h', '1d' to timedelta"""
            if not duration_str or duration_str == "null" or duration_str == "indefinite":
                return None

            duration_str = str(duration_str).strip().lower()

            # Extract numeric value (supporting decimals)
            match = re.search(r"([\d.]+)", duration_str)
            if not match:
                return None
            value = float(match.group(1))

            if "h" in duration_str:
                return timedelta(hours=value)
            elif "d" in duration_str:
                return timedelta(days=value)
            elif "m" in duration_str:
                return timedelta(minutes=value)
            else:
                # Default to hours
                return timedelta(hours=value)

        removed = []
        now = datetime.now()

        # Get all containers with GPU allocations (from Docker labels)
        all_allocations = self.state_reader.get_all_allocations()

        for gpu_slot, gpu_info in all_allocations.items():
            for container in gpu_info["containers"]:
                # Get username from Docker label (not UID from container name)
                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "inspect",
                            "--format",
                            '{{index .Config.Labels "ds01.user"}}',
                            container,
                        ],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=10,
                    )
                    user = result.stdout.strip()
                    if not user or user == "<no value>":
                        user = None
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    user = None

                # Filter by username if specified
                if username and user != username:
                    continue

                # Get container interface
                interface = self._get_container_interface(container)

                # Check if container is stopped
                try:
                    result = subprocess.run(
                        ["docker", "inspect", "--format", "{{.State.Running}}", container],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=10,
                    )
                    is_running = result.stdout.strip() == "true"

                    if is_running:
                        continue  # Skip running containers

                    # Container is stopped - get FinishedAt timestamp from Docker state (automatic)
                    result = subprocess.run(
                        ["docker", "inspect", "--format", "{{.State.FinishedAt}}", container],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=10,
                    )
                    finished_at_str = result.stdout.strip()

                    if not finished_at_str or finished_at_str == "0001-01-01T00:00:00Z":
                        # Container never ran or invalid state - remove immediately (stale allocation)
                        subprocess.run(["docker", "rm", "-f", container], check=True, timeout=30)
                        removed.append((container, "Invalid FinishedAt - stale allocation"))
                        self._log_event(
                            "REMOVED_STALE",
                            user or "unknown",
                            container,
                            gpu_slot,
                            reason="Invalid FinishedAt",
                        )
                        continue

                    # Parse stopped timestamp (remove Z suffix and parse)
                    stopped_at = datetime.fromisoformat(
                        finished_at_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    elapsed = now - stopped_at

                    # INTERFACE-SPECIFIC STATE HANDLING
                    if interface in (INTERFACE_ORCHESTRATION, INTERFACE_API):
                        # Orchestration / API: Binary state model
                        # Stopped containers should be removed immediately (no limbo state).
                        # Both interfaces represent a higher-layer dispatcher (orchestration =
                        # CLI/scripted, api = ds01-jobs HTTP API) that already serialises
                        # access, so the wrapper's per-user GPU hold would just block back-
                        # to-back jobs without adding isolation.
                        subprocess.run(["docker", "rm", "-f", container], check=True, timeout=30)
                        reason = f"{interface} interface - binary state (stopped→removed)"
                        removed.append((container, reason))
                        self._log_event(
                            "REMOVED_STALE",
                            user or "unknown",
                            container,
                            gpu_slot,
                            reason=f"{interface} binary state: stopped→removed",
                        )
                        continue

                    # Atomic/Docker/Other: Full state model with hold timeout
                    if user:
                        limits = self._get_user_limits(user)
                        hold_timeout_str = limits.get("gpu_hold_after_stop_h")
                        hold_timeout = parse_duration(hold_timeout_str)

                        if hold_timeout is None:
                            # Indefinite hold - don't remove
                            continue

                        # Check if timeout exceeded
                        if elapsed > hold_timeout:
                            # Remove container (automatically releases GPU)
                            subprocess.run(
                                ["docker", "rm", "-f", container], check=True, timeout=30
                            )
                            removed.append(
                                (
                                    container,
                                    f"Timeout exceeded ({elapsed.total_seconds():.0f}s > {hold_timeout.total_seconds():.0f}s)",
                                )
                            )
                            self._log_event(
                                "REMOVED_STALE",
                                user,
                                container,
                                gpu_slot,
                                reason=f"Timeout exceeded: {elapsed.total_seconds():.0f}s",
                            )

                except subprocess.CalledProcessError:
                    # Container doesn't exist anymore - already removed
                    removed.append((container, "Container no longer exists"))
                except Exception as e:
                    # Log error but continue
                    print(f"Warning: Error checking container {container}: {e}", file=sys.stderr)
                    continue

        return removed


def main():
    """CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description="GPU Allocator Smart - Stateless GPU allocation")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # allocate command
    parser_allocate = subparsers.add_parser("allocate", help="Allocate GPU to container")
    parser_allocate.add_argument("user", help="Username")
    parser_allocate.add_argument("container", help="Container name (full tag)")
    parser_allocate.add_argument("max_gpus", type=int, help="Max GPUs for user")
    parser_allocate.add_argument("priority", type=int, help="User priority")

    # release command
    parser_release = subparsers.add_parser("release", help="Release GPU from container")
    parser_release.add_argument("container", help="Container name")

    # status command
    subparsers.add_parser("status", help="Show GPU allocation status")

    # user-count command
    parser_count = subparsers.add_parser("user-count", help="Show GPU count for user")
    parser_count.add_argument("user", help="Username")

    # release-stale command
    parser_stale = subparsers.add_parser(
        "release-stale", help="Release stale GPU allocations from stopped containers"
    )
    parser_stale.add_argument(
        "user", nargs="?", help="Optional: username to filter (default: all users)"
    )

    # allocate-multi command (multi-GPU allocation for distributed containers)
    parser_multi = subparsers.add_parser(
        "allocate-multi", help="Allocate multiple GPU slots to container"
    )
    parser_multi.add_argument("user", help="Username")
    parser_multi.add_argument("container", help="Container name (full tag)")
    parser_multi.add_argument(
        "container_type", help="Container type (api, devcontainer, compose, docker, unknown)"
    )
    parser_multi.add_argument("num_gpus", type=int, help="Number of GPU slots to allocate")
    parser_multi.add_argument(
        "--prefer-full", action="store_true", help="Deprecated no-op (slots are full GPUs)"
    )

    # allocate-external command (for docker-wrapper.sh - external containers like devcontainers, compose)
    parser_external = subparsers.add_parser(
        "allocate-external",
        help="Allocate GPU for external container (devcontainer, compose, docker run)",
    )
    parser_external.add_argument("user", help="Username")
    parser_external.add_argument(
        "container_type", help="Container type (devcontainer, compose, docker, unknown)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    allocator = GPUAllocatorSmart()

    if args.command == "allocate":
        gpu_id, reason = allocator.allocate_gpu(args.user, args.container, args.max_gpus)

        if gpu_id and reason not in ["ALREADY_ALLOCATED"]:
            docker_id = allocator.get_docker_id(gpu_id)
            print(f"✓ Allocated GPU/MIG {gpu_id} to {args.container}")
            print(f"DOCKER_ID={docker_id}")  # For mlc-create-wrapper parsing
        elif reason == "ALREADY_ALLOCATED":
            docker_id = allocator.get_docker_id(gpu_id)
            print(f"⚠ Container {args.container} already has GPU/MIG {gpu_id} allocated")
            print(f"DOCKER_ID={docker_id}")
        else:
            print(f"✗ Allocation failed: {reason}")
            sys.exit(1)

    elif args.command == "release":
        gpu_id, reason = allocator.release_gpu(args.container)
        if gpu_id:
            print(f"✓ Released GPU/MIG {gpu_id} from {args.container}")
        else:
            print(f"✗ No GPU allocated to {args.container}")

    elif args.command == "status":
        status = allocator.get_status()
        print(
            f"\nGPU Status: {status['allocated']}/{status['total_gpus']} allocated ({status['utilization_percent']:.1f}% utilization)\n"
        )

        for gpu_slot, info in sorted(status["allocations"].items()):
            containers = ", ".join(info["containers"]) if info["containers"] else "none"
            print(f"GPU/MIG {gpu_slot}:")
            print(f"  UUID: {info['uuid']}")
            print(f"  Containers: {containers}")
            print()

    elif args.command == "user-count":
        count = allocator.get_user_gpu_count(args.user)
        print(count)

    elif args.command == "release-stale":
        username = args.user if hasattr(args, "user") and args.user else None
        removed = allocator.release_stale_allocations(username)

        if removed:
            for container, reason in removed:
                print(f"✓ Removed {container}: {reason}")
            print(f"\n✓ Removed {len(removed)} stale container(s) (GPUs freed automatically)")
        else:
            print("✓ No stale containers found")

    elif args.command == "allocate-multi":
        gpu_slots, slot_count, total_gpueq, reason = allocator.allocate_multi_gpu(
            args.user,
            args.container,
            args.container_type,
            args.num_gpus,
            prefer_full_gpu=args.prefer_full,
        )

        if gpu_slots and reason == "SUCCESS":
            # Get Docker IDs for all slots
            docker_ids = [allocator.get_docker_id(slot) for slot in gpu_slots]
            slots_str = ",".join(gpu_slots)
            docker_ids_str = ",".join(docker_ids)
            print(f"✓ Allocated {len(gpu_slots)} GPU slot(s) to {args.container}")
            print(f"GPU_SLOTS={slots_str}")
            print(f"DOCKER_IDS={docker_ids_str}")  # For mlc-create-wrapper parsing
            print(f"SLOT_COUNT={slot_count}")
            print(f"GPU_EQUIV={total_gpueq:g}")  # Total GPU-equivalents (gpueq)
        elif reason == "ALREADY_ALLOCATED":
            slots_str = ",".join(gpu_slots)
            docker_ids = [allocator.get_docker_id(slot) for slot in gpu_slots]
            docker_ids_str = ",".join(docker_ids)
            print(f"⚠ Container {args.container} already has GPU(s) {slots_str} allocated")
            print(f"GPU_SLOTS={slots_str}")
            print(f"DOCKER_IDS={docker_ids_str}")
            print(f"SLOT_COUNT={slot_count}")
            print(f"GPU_EQUIV={total_gpueq:g}")
        else:
            print(f"✗ Allocation failed: {reason}")
            sys.exit(1)

    elif args.command == "allocate-external":
        # For docker-wrapper.sh - external containers (devcontainer, compose, docker run)
        docker_id, reason = allocator.allocate_external(args.user, args.container_type)

        if docker_id and reason == "SUCCESS":
            # Output format expected by docker-wrapper.sh
            print(f"DOCKER_ID={docker_id}")
            print("STATUS=SUCCESS")
        elif reason.startswith("QUOTA_EXCEEDED"):
            # Quota exceeded - wrapper should fail immediately (no retry)
            print("STATUS=QUOTA_EXCEEDED")
            print(f"REASON={reason}")
            sys.exit(1)
        else:
            # Other failure (e.g., no GPU available) - wrapper may retry
            print("STATUS=FAILED")
            print(f"REASON={reason}")
            sys.exit(1)


if __name__ == "__main__":
    main()
