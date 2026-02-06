#!/usr/bin/env python3
"""
GPU State Reader - Docker-First GPU Allocation State
Reads GPU allocation state directly from Docker containers (HostConfig + Labels)
This is the SINGLE SOURCE OF TRUTH for GPU allocations.

Updated for DS01 Layered Architecture:
- Tracks ALL containers in ds01.slice (not just AIME naming convention)
- Supports 4 interfaces: Orchestration, Atomic, Docker, Other
- Interface detection via ds01.interface label and naming patterns
"""

import subprocess
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict

# Real Docker binary - bypasses the wrapper at /usr/local/bin/docker
# The wrapper filters 'docker ps' for non-admin users, which would cause
# the GPU state reader to miss allocations from other users, leading to
# incorrect "available" GPU status and double-allocations.
DOCKER_BIN = "/usr/bin/docker"


# Interface detection constants
INTERFACE_ORCHESTRATION = "orchestration"
INTERFACE_ATOMIC = "atomic"
INTERFACE_DOCKER = "docker"
INTERFACE_OTHER = "other"
INTERFACE_UNMANAGED = "unmanaged"  # Containers outside DS01 tracking (bypass wrapper)

# Infrastructure containers - excluded from monitoring
INFRASTRUCTURE_CONTAINER_PATTERNS = [
    "ds01-prometheus",
    "ds01-grafana",
    "ds01-alertmanager",
    "ds01-dcgm-exporter",
    "ds01-node-exporter",
]
INFRASTRUCTURE_LABEL = "ds01.protected"


class GPUStateReader:
    def __init__(self, config_path="/opt/ds01-infra/config/runtime/resource-limits.yaml"):
        self._mig_uuid_to_slot_cache = None
        self.config_path = config_path
        self._config = None

    def _load_config(self):
        """Load resource-limits.yaml if not already loaded"""
        if self._config is None:
            try:
                import yaml
                with open(self.config_path) as f:
                    self._config = yaml.safe_load(f)
            except FileNotFoundError:
                self._config = {}
            except (IOError, OSError) as e:
                print(f"Warning: could not read config file: {e}", file=sys.stderr)
                self._config = {}
            except yaml.YAMLError as e:
                print(f"Warning: could not parse config file: {e}", file=sys.stderr)
                self._config = {}
        return self._config

    def _get_mig_instances_per_gpu(self) -> int:
        """Get mig_instances_per_gpu from config (default: 4)"""
        config = self._load_config()
        gpu_config = config.get('gpu_allocation', {})
        return gpu_config.get('mig_instances_per_gpu', 4)

    def _is_full_gpu(self, gpu_slot: str) -> bool:
        """Check if a GPU slot is a full GPU (not MIG instance)"""
        slot_str = str(gpu_slot)
        # MIG UUIDs start with "MIG-" and don't contain dots
        if slot_str.startswith('MIG-'):
            return False
        return '.' not in slot_str

    def _get_mig_uuid_to_slot_mapping(self) -> Dict[str, str]:
        """
        Get mapping of GPU/MIG UUIDs to slot IDs.
        Maps both physical GPU UUIDs (GPU-xxx → "0") and MIG UUIDs (MIG-xxx → "1.0").
        Caches result for performance.
        """
        if self._mig_uuid_to_slot_cache is not None:
            return self._mig_uuid_to_slot_cache

        mapping = {}

        # Device permissions are 0666 so all users can query nvidia-smi directly
        try:
            result = subprocess.run(
                ["/usr/bin/nvidia-smi", "-L"],
                capture_output=True,
                text=True,
                check=True
            )
            nvidia_output = result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._mig_uuid_to_slot_cache = mapping
            return mapping

        # Parse output like:
        # GPU 0: NVIDIA A100-PCIE-40GB (UUID: GPU-14d7e768-...)
        # GPU 1: NVIDIA A100-PCIE-40GB (UUID: GPU-86021f6f-...)
        #   MIG 1g.10gb Device 0: (UUID: MIG-abc-123)
        #   MIG 1g.10gb Device 1: (UUID: MIG-def-456)

        try:
            current_gpu = None
            for line in nvidia_output.split('\n'):
                # Match GPU line: "GPU 0: NVIDIA A100 (UUID: GPU-xxx)"
                gpu_match = re.match(r'GPU (\d+):\s+[^(]+\(UUID:\s+(GPU-[a-f0-9-]+)\)', line)
                if gpu_match:
                    current_gpu = gpu_match.group(1)
                    gpu_uuid = gpu_match.group(2)
                    mapping[gpu_uuid] = current_gpu
                    continue

                # Match MIG line: "  MIG 1g.10gb Device 0: (UUID: MIG-xxx)"
                mig_match = re.match(r'\s+MIG\s+\S+\s+Device\s+(\d+):\s+\(UUID:\s+(MIG-[a-f0-9-]+)\)', line)
                if mig_match and current_gpu is not None:
                    device_id = mig_match.group(1)
                    uuid = mig_match.group(2)
                    slot_id = f"{current_gpu}.{device_id}"
                    mapping[uuid] = slot_id
        except Exception:
            pass

        self._mig_uuid_to_slot_cache = mapping
        return mapping

    def _get_container_inspect(self, container_name: str) -> Optional[Dict]:
        """Get docker inspect output for a container."""
        try:
            result = subprocess.run(
                [DOCKER_BIN, "inspect", container_name],
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)
            return data[0] if data else None
        except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
            return None

    def _detect_interface(self, container_data: Dict) -> str:
        """
        Detect which interface created this container.

        Detection order:
        1. ds01.interface label (explicit)
        2. AIME naming convention (name._.uid) -> Atomic or Orchestration
        3. Tool-specific labels/naming -> Other
        4. Default -> Docker

        Returns: INTERFACE_ORCHESTRATION, INTERFACE_ATOMIC, INTERFACE_DOCKER, or INTERFACE_OTHER
        """
        labels = container_data.get('Config', {}).get('Labels', {}) or {}
        name = container_data.get('Name', '').lstrip('/')

        # 1. Explicit ds01.interface label
        interface_label = labels.get('ds01.interface', '')
        if interface_label:
            if interface_label == 'orchestration':
                return INTERFACE_ORCHESTRATION
            elif interface_label == 'atomic':
                return INTERFACE_ATOMIC
            # Other explicit values fall through

        # 2. DS01 managed label (from mlc-create-wrapper)
        if labels.get('ds01.managed') == 'true':
            # Has DS01 label but no explicit interface -> atomic (backward compat)
            return INTERFACE_ATOMIC

        # 3. AIME naming convention (name._.uid)
        if '._.' in name:
            return INTERFACE_ATOMIC

        # 4. Tool-specific detection for "Other" interface
        # VS Code Dev Containers
        if (name.startswith('vscode-') or
            'devcontainer' in labels or
            labels.get('devcontainer.metadata')):
            return INTERFACE_OTHER

        # Docker Compose
        if (labels.get('com.docker.compose.project') or
            labels.get('com.docker.compose.service') or
            '_' in name and name.endswith(('_1', '_2', '_3'))):
            return INTERFACE_OTHER

        # JupyterHub
        if (name.startswith('jupyterhub-') or
            name.startswith('jupyter-') or
            labels.get('hub.jupyter.org/username')):
            return INTERFACE_OTHER

        # 5. Default: Docker direct
        return INTERFACE_DOCKER

    def _extract_user_from_cgroup(self, cgroup_parent: str) -> Optional[str]:
        """
        Extract (sanitized) username from cgroup path.
        Example: ds01-student-alice.slice -> alice
        Example: ds01-student-h-baker-at-hertie-school-lan.slice -> h-baker-at-hertie-school-lan

        Note: Returns the sanitized form of the username. For original username,
        use Docker labels (ds01.user or aime.mlc.USER) which preserve the original.
        """
        if not cgroup_parent:
            return None

        # Pattern: ds01-{group}-{sanitized_username}.slice
        # Sanitized usernames can contain hyphens, so use .+ for the username part
        match = re.match(r'ds01-(\w+)-(.+)\.slice', cgroup_parent)
        if match:
            return match.group(2)  # Return sanitized username
        return None

    def _extract_gpu_from_container(self, container_data: Dict) -> Optional[Dict]:
        """
        Extract GPU assignment from Docker container inspect data.
        Returns dict with gpu_uuid, gpu_slot, interface, etc. or None if no GPU.
        Now supports multiple GPU devices per container.

        GPU info sources (in order of preference):
        1. HostConfig.DeviceRequests (from --gpus flag) - single MIG
        2. DS01 labels (ds01.gpu.uuids, ds01.gpu.slots) - multi-MIG with --runtime=nvidia
        """
        try:
            # Get HostConfig.DeviceRequests (used for single MIG with --gpus)
            device_requests = container_data.get('HostConfig', {}).get('DeviceRequests', [])
            device_ids = []

            if device_requests:
                # Look for GPU device IDs in first DeviceRequest
                first_request = device_requests[0]
                device_ids = first_request.get('DeviceIDs', [])

            # If no DeviceRequests, check DS01 labels (used for multi-MIG with --runtime=nvidia)
            labels = container_data.get('Config', {}).get('Labels', {}) or {}
            if not device_ids and labels.get('ds01.gpu.uuids'):
                # Multi-MIG: read from labels
                device_ids = labels.get('ds01.gpu.uuids', '').split(',')
                device_ids = [uid.strip() for uid in device_ids if uid.strip()]

            if not device_ids:
                return None

            # Map all UUIDs to slot IDs
            uuid_to_slot = self._get_mig_uuid_to_slot_mapping()
            mig_per_gpu = self._get_mig_instances_per_gpu()

            gpu_slots = []
            gpu_uuids = []
            mig_equiv = 0

            for uuid in device_ids:
                slot = uuid_to_slot.get(uuid, uuid)  # Fallback to UUID if not found
                gpu_slots.append(slot)
                gpu_uuids.append(uuid)
                # Full GPU counts as mig_per_gpu equivalents
                if self._is_full_gpu(slot):
                    mig_equiv += mig_per_gpu
                else:
                    mig_equiv += 1

            # Primary GPU info (for backward compatibility)
            gpu_uuid = device_ids[0]
            gpu_slot = gpu_slots[0] if gpu_slots else gpu_uuid

            # Extract additional info from Docker labels (labels already loaded above)
            allocated_at = labels.get('ds01.gpu.allocated_at', '')
            priority = labels.get('ds01.gpu.priority', '')
            user = labels.get('ds01.user') or labels.get('aime.mlc.USER', '')
            container_name = container_data.get('Name', '').lstrip('/')

            # Detect interface
            interface = self._detect_interface(container_data)

            # Fall back to cgroup-based user detection if label not set
            if not user:
                cgroup_parent = container_data.get('HostConfig', {}).get('CgroupParent', '')
                user = self._extract_user_from_cgroup(cgroup_parent) or ''

            return {
                'container_name': container_name,
                'gpu_uuid': gpu_uuid,           # Primary GPU UUID (backward compat)
                'gpu_slot': gpu_slot,           # Primary GPU slot (backward compat)
                'gpu_uuids': gpu_uuids,         # All GPU UUIDs
                'gpu_slots': gpu_slots,         # All GPU slots
                'mig_equiv': mig_equiv,         # Total MIG-equivalents
                'allocated_at': allocated_at,
                'priority': priority,
                'user': user,
                'interface': interface
            }

        except (KeyError, IndexError, TypeError) as e:
            # Malformed container data - return None
            return None
        except subprocess.CalledProcessError:
            # nvidia-smi query failed - GPU extraction failed
            return None

    def _is_infrastructure_container(self, name: str, labels: dict) -> bool:
        """Check if container is DS01 infrastructure (monitoring stack).

        Infrastructure containers are excluded from unmanaged container detection
        because they are intentionally created outside DS01 tracking.
        """
        # Check for explicit protected label
        if labels.get(INFRASTRUCTURE_LABEL) == 'true':
            return True

        # Check against known infrastructure patterns
        for pattern in INFRASTRUCTURE_CONTAINER_PATTERNS:
            if name.startswith(pattern) or name == pattern:
                return True

        return False

    def _extract_owner_from_compose(self, labels: dict) -> Optional[str]:
        """Extract owner from compose project path or devcontainer.local_folder.

        For containers created via docker compose or dev containers, the owner
        can often be inferred from the working directory path.

        Priority:
        1. devcontainer.local_folder (most reliable)
        2. com.docker.compose.project.working_dir (compose projects)

        Returns username if extractable from /home/<username>/..., else None.
        """
        # Priority 1: devcontainer.local_folder
        path = labels.get('devcontainer.local_folder', '')

        # Priority 2: com.docker.compose.project.working_dir
        if not path:
            path = labels.get('com.docker.compose.project.working_dir', '')

        # Extract username from path like /home/h.baker@hertie-school.lan/...
        if path and path.startswith('/home/'):
            parts = path.split('/')
            if len(parts) >= 3:
                return parts[2]  # The username part after /home/

        return None

    def _get_gpu_access_info(self, container_data: Dict) -> Optional[Dict]:
        """Get GPU access information for a container.

        Returns dict with:
        - gpu_count: Number of GPUs requested (-1 means all GPUs)
        - gpu_uuids: List of specific GPU UUIDs if pinned
        - access_type: 'all', 'count', 'specific', or None

        Returns None if container has no GPU access.
        """
        try:
            device_requests = container_data.get('HostConfig', {}).get('DeviceRequests', [])

            if not device_requests:
                return None

            for request in device_requests:
                driver = request.get('Driver', '')
                caps = request.get('Capabilities', [])

                # Check if this is an NVIDIA GPU request
                is_nvidia = driver == 'nvidia' or any('gpu' in cap for cap in caps)

                if is_nvidia:
                    device_ids = request.get('DeviceIDs', [])
                    count = request.get('Count', 0)

                    if device_ids:
                        return {
                            'gpu_count': len(device_ids),
                            'gpu_uuids': device_ids,
                            'access_type': 'specific'
                        }
                    elif count == -1:
                        return {
                            'gpu_count': -1,  # All GPUs
                            'gpu_uuids': [],
                            'access_type': 'all'
                        }
                    elif count > 0:
                        return {
                            'gpu_count': count,
                            'gpu_uuids': [],
                            'access_type': 'count'
                        }

            return None

        except (KeyError, TypeError):
            return None

    def get_unmanaged_gpu_containers(self) -> List[Dict]:
        """Get ALL containers with GPU access that are NOT tracked by DS01.

        Unmanaged containers are:
        - Not in ds01.slice hierarchy (empty cgroup-parent or different slice)
        - Not DS01 infrastructure (prometheus, grafana, etc.)
        - Have DeviceRequests for nvidia/gpu

        Returns list of dicts with:
        - name: Container name
        - user: Detected owner (from compose path, or 'unknown')
        - gpu_count: Number of GPUs (-1 = all)
        - gpu_uuids: List of pinned GPU UUIDs (if specific)
        - access_type: 'all', 'count', or 'specific'
        - labels: Relevant labels for debugging
        """
        unmanaged = []

        try:
            # Get ALL containers (using real docker binary)
            result = subprocess.run(
                [DOCKER_BIN, "ps", "-a", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True
            )

            for name in result.stdout.split('\n'):
                name = name.strip()
                if not name:
                    continue

                container_data = self._get_container_inspect(name)
                if not container_data:
                    continue

                labels = container_data.get('Config', {}).get('Labels', {}) or {}
                cgroup_parent = container_data.get('HostConfig', {}).get('CgroupParent', '')

                # Skip if it's tracked by DS01
                in_ds01_slice = cgroup_parent.startswith('ds01')
                has_ds01_labels = any(k.startswith('ds01.') for k in labels.keys())
                has_aime_naming = '._.' in name

                if in_ds01_slice or has_ds01_labels or has_aime_naming:
                    continue

                # Skip infrastructure containers
                if self._is_infrastructure_container(name, labels):
                    continue

                # Check for GPU access
                gpu_info = self._get_gpu_access_info(container_data)
                if not gpu_info:
                    continue

                # Get container state
                state = container_data.get('State', {})
                is_running = state.get('Running', False)
                status = state.get('Status', 'unknown')

                # Try to detect owner
                user = self._extract_owner_from_compose(labels) or 'unknown'

                unmanaged.append({
                    'name': name,
                    'user': user,
                    'gpu_count': gpu_info['gpu_count'],
                    'gpu_uuids': gpu_info['gpu_uuids'],
                    'access_type': gpu_info['access_type'],
                    'running': is_running,
                    'status': status,
                    'cgroup_parent': cgroup_parent,
                    'labels': {
                        'compose_project': labels.get('com.docker.compose.project', ''),
                        'compose_service': labels.get('com.docker.compose.service', ''),
                        'devcontainer': labels.get('devcontainer.local_folder', ''),
                    }
                })

        except subprocess.CalledProcessError:
            pass

        return unmanaged

    def get_all_allocations(self) -> Dict:
        """
        Get all GPU allocations by reading Docker containers.
        Now tracks ALL containers in ds01.slice (all interfaces).
        Returns dict structured like old gpu-state.json for compatibility.
        """
        allocations = defaultdict(lambda: {
            'type': 'mig_instance',
            'containers': [],
            'users': defaultdict(int),
            'uuid': '',
            'profile': '',
            'docker_id': '',
            'interfaces': defaultdict(int)  # Track containers by interface
        })

        # Get ALL containers (not just AIME naming convention)
        container_names = self._get_all_ds01_containers()

        for container_name in container_names:
            if not container_name:
                continue

            container_data = self._get_container_inspect(container_name)
            if not container_data:
                continue

            gpu_info = self._extract_gpu_from_container(container_data)

            if not gpu_info:
                continue  # Container has no GPU

            user = gpu_info['user']
            interface = gpu_info.get('interface', INTERFACE_DOCKER)

            # Process ALL gpu_slots for multi-MIG containers
            all_gpu_slots = gpu_info.get('gpu_slots', [gpu_info['gpu_slot']])
            all_gpu_uuids = gpu_info.get('gpu_uuids', [gpu_info['gpu_uuid']])

            for i, gpu_slot in enumerate(all_gpu_slots):
                gpu_uuid = all_gpu_uuids[i] if i < len(all_gpu_uuids) else ''

                # Add to allocations
                allocations[gpu_slot]['containers'].append(container_name)
                allocations[gpu_slot]['users'][user] += 1
                allocations[gpu_slot]['uuid'] = gpu_uuid
                allocations[gpu_slot]['docker_id'] = gpu_uuid
                allocations[gpu_slot]['interfaces'][interface] += 1

                # Try to determine profile from UUID or slot
                if 'MIG' in gpu_uuid:
                    allocations[gpu_slot]['profile'] = '1g.10gb'  # Default, could parse from nvidia-smi

        # Convert defaultdict to regular dict
        result = {}
        for k, v in allocations.items():
            v['users'] = dict(v['users'])
            v['interfaces'] = dict(v['interfaces'])
            result[k] = v

        return result

    def _get_all_ds01_containers(self) -> List[str]:
        """
        Get ALL containers that should be tracked by DS01.
        Includes containers from all interfaces:
        - DS01 Orchestration (ds01.interface=orchestration)
        - DS01 Atomic (ds01.interface=atomic or name._.uid pattern)
        - Docker (direct docker run, in ds01.slice)
        - Other (VS Code, Compose, etc., in ds01.slice)
        """
        container_names = []

        try:
            # Get all containers (using real docker binary to see all users' containers)
            result = subprocess.run(
                [DOCKER_BIN, "ps", "-a", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True
            )

            for name in result.stdout.split('\n'):
                name = name.strip()
                if not name:
                    continue

                # Check if container is in ds01 slice hierarchy
                container_data = self._get_container_inspect(name)
                if container_data:
                    cgroup_parent = container_data.get('HostConfig', {}).get('CgroupParent', '')

                    # Include if:
                    # 1. In ds01.slice hierarchy
                    # 2. Has ds01.* labels
                    # 3. Has AIME naming convention (legacy support)
                    labels = container_data.get('Config', {}).get('Labels', {}) or {}

                    in_ds01_slice = cgroup_parent.startswith('ds01')
                    has_ds01_labels = any(k.startswith('ds01.') for k in labels.keys())
                    has_aime_naming = '._.' in name

                    if in_ds01_slice or has_ds01_labels or has_aime_naming:
                        container_names.append(name)

        except subprocess.CalledProcessError:
            pass

        return container_names

    def get_all_containers_by_interface(self) -> Dict[str, List[Dict]]:
        """
        Get all containers grouped by interface.
        Returns dict with interface names as keys and container info lists as values.
        """
        by_interface = {
            INTERFACE_ORCHESTRATION: [],
            INTERFACE_ATOMIC: [],
            INTERFACE_DOCKER: [],
            INTERFACE_OTHER: []
        }

        container_names = self._get_all_ds01_containers()

        for container_name in container_names:
            if not container_name:
                continue

            container_data = self._get_container_inspect(container_name)
            if not container_data:
                continue

            interface = self._detect_interface(container_data)
            gpu_info = self._extract_gpu_from_container(container_data)

            # Get container state
            state = container_data.get('State', {})
            is_running = state.get('Running', False)
            status = state.get('Status', 'unknown')

            # Get user
            labels = container_data.get('Config', {}).get('Labels', {}) or {}
            user = labels.get('ds01.user') or labels.get('aime.mlc.USER', '')
            if not user:
                cgroup_parent = container_data.get('HostConfig', {}).get('CgroupParent', '')
                user = self._extract_user_from_cgroup(cgroup_parent) or 'unknown'

            container_info = {
                'name': container_name,
                'user': user,
                'status': status,
                'running': is_running,
                'gpu': gpu_info['gpu_slot'] if gpu_info else None,
                'gpu_uuid': gpu_info['gpu_uuid'] if gpu_info else None,
                'interface': interface
            }

            by_interface[interface].append(container_info)

        return by_interface

    def get_container_gpu(self, container_name: str) -> Optional[Dict]:
        """Get GPU assignment for a specific container."""
        container_data = self._get_container_inspect(container_name)
        if not container_data:
            return None
        return self._extract_gpu_from_container(container_data)

    def get_user_allocations(self, username: str) -> List[Dict]:
        """
        Get all GPU allocations for a specific user.
        Now tracks all containers from all interfaces.
        Includes MIG-equivalent count for multi-GPU containers.
        """
        user_allocations = []

        # Get all DS01 containers (all interfaces)
        container_names = self._get_all_ds01_containers()

        for container_name in container_names:
            if not container_name:
                continue

            container_data = self._get_container_inspect(container_name)
            if not container_data:
                continue

            gpu_info = self._extract_gpu_from_container(container_data)

            if not gpu_info:
                continue

            # Get user from labels or cgroup
            container_user = gpu_info['user']
            if not container_user:
                continue

            if container_user != username:
                continue

            # Get status
            state = container_data.get('State', {})
            is_running = state.get('Running', False)
            status = state.get('Status', 'unknown')
            interface = gpu_info.get('interface', INTERFACE_DOCKER)

            user_allocations.append({
                'container': container_name,
                'gpu_slot': gpu_info['gpu_slot'],           # Primary slot (backward compat)
                'gpu_uuid': gpu_info['gpu_uuid'],           # Primary UUID (backward compat)
                'gpu_slots': gpu_info.get('gpu_slots', [gpu_info['gpu_slot']]),  # All slots
                'gpu_uuids': gpu_info.get('gpu_uuids', [gpu_info['gpu_uuid']]),  # All UUIDs
                'mig_equiv': gpu_info.get('mig_equiv', 1),  # MIG-equivalents
                'status': status,
                'running': is_running,
                'interface': interface
            })

        return user_allocations

    def get_user_mig_total(self, username: str) -> int:
        """
        Get total MIG-equivalents allocated to a user across all containers.
        """
        allocations = self.get_user_allocations(username)
        return sum(alloc.get('mig_equiv', 1) for alloc in allocations)

    def get_user_gpu_count(self, username: str) -> int:
        """
        Get count of GPU slots allocated to a user (for display purposes).

        Unlike user-mig-total which returns MIG-equivalents (1 full GPU = N mig-equiv),
        this returns the actual count of GPU/MIG slots:
        - In non-MIG mode: count of full GPUs (e.g., 1 full GPU = 1)
        - In MIG mode: count of MIG instances (e.g., 2 MIG instances = 2)

        This is appropriate for user-facing display where users expect to see
        "1 GPU" when they have 1 GPU, not "4 MIG-equivalents".
        """
        allocations = self.get_user_allocations(username)
        # Count distinct GPU slots across all containers
        all_slots = set()
        for alloc in allocations:
            for slot in alloc.get('gpu_slots', [alloc.get('gpu_slot')]):
                if slot:
                    all_slots.add(slot)
        return len(all_slots)


# ============================================================================
# MODULE-LEVEL API FUNCTIONS (for importing by other scripts)
# These provide a simple interface for other DS01 scripts to get GPU state.
# gpu-state-reader.py is the SINGLE SOURCE OF TRUTH for GPU allocations.
# ============================================================================

_reader_instance = None

def get_reader() -> GPUStateReader:
    """Get singleton GPUStateReader instance."""
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = GPUStateReader()
    return _reader_instance


def get_mig_allocations() -> List[Dict]:
    """
    Get all MIG allocations in a format compatible with monitors.
    Returns list of dicts with: container, user, mig_slot, mig_uuid
    """
    reader = get_reader()
    allocations = reader.get_all_allocations()

    result = []
    for slot, data in allocations.items():
        # Only include MIG slots (format: X.Y)
        if '.' in str(slot):
            for container in data.get('containers', []):
                # Find user for this container
                users = data.get('users', {})
                user = list(users.keys())[0] if users else 'unknown'
                result.append({
                    'container': container,
                    'user': user,
                    'mig_slot': slot,
                    'mig_uuid': data.get('uuid', '')
                })
    return result


def get_gpu_allocations() -> List[Dict]:
    """
    Get all full GPU allocations (non-MIG) in a format compatible with monitors.
    Returns list of dicts with: container, user, gpu_slot, gpu_uuid
    """
    reader = get_reader()
    allocations = reader.get_all_allocations()

    result = []
    for slot, data in allocations.items():
        # Only include full GPU slots (no decimal point)
        if '.' not in str(slot):
            for container in data.get('containers', []):
                users = data.get('users', {})
                user = list(users.keys())[0] if users else 'unknown'
                result.append({
                    'container': container,
                    'user': user,
                    'gpu_slot': slot,
                    'gpu_uuid': data.get('uuid', '')
                })
    return result


def get_all_gpu_allocations_by_slot() -> Dict:
    """
    Get all GPU/MIG allocations indexed by slot.
    Returns the raw allocation dict from GPUStateReader.
    """
    return get_reader().get_all_allocations()


def get_all_allocations_flat() -> List[Dict]:
    """
    Get ALL allocations (both MIG and full GPU) as a flat list.
    Returns list of dicts with: container, user, gpu_slot, gpu_uuid

    This is the primary API for monitors that need to track all GPU usage.
    """
    reader = get_reader()
    allocations = reader.get_all_allocations()

    result = []
    for slot, data in allocations.items():
        for container in data.get('containers', []):
            users = data.get('users', {})
            user = list(users.keys())[0] if users else 'unknown'
            result.append({
                'container': container,
                'user': user,
                'gpu_slot': str(slot),
                'gpu_uuid': data.get('uuid', '')
            })
    return result


def get_unmanaged_gpu_containers() -> List[Dict]:
    """
    Get containers with GPU access that bypass DS01 tracking.

    These are containers that:
    - Are NOT in ds01.slice hierarchy
    - Are NOT DS01 infrastructure (prometheus, grafana, etc.)
    - Have GPU DeviceRequests (--gpus flag)

    This is used for monitoring compliance and detecting resource leaks.
    """
    return get_reader().get_unmanaged_gpu_containers()


def main():
    """CLI interface"""
    reader = GPUStateReader()

    if len(sys.argv) < 2:
        print("Usage: gpu-state-reader.py <command> [args]")
        print("\nCommands:")
        print("  all                    - Show all GPU allocations")
        print("  by-interface           - Show containers grouped by interface")
        print("  container <name>       - Show GPU for specific container")
        print("  user <username>        - Show user's GPU allocations (with MIG-equiv)")
        print("  user-mig-total <user>  - Get total MIG-equivalents for user")
        print("  user-gpu-count <user>  - Get GPU/MIG slot count for display")
        print("  unmanaged              - Show containers with GPU access outside DS01 tracking")
        print("  json                   - Output all allocations as JSON")
        print("  json-by-interface      - Output containers by interface as JSON")
        print("  json-unmanaged         - Output unmanaged GPU containers as JSON")
        sys.exit(1)

    command = sys.argv[1]

    if command == "all":
        allocations = reader.get_all_allocations()
        for gpu_slot, data in sorted(allocations.items()):
            print(f"\nGPU/MIG {gpu_slot}:")
            print(f"  UUID: {data['uuid']}")
            print(f"  Containers: {', '.join(data['containers']) if data['containers'] else 'none'}")
            print(f"  Users: {dict(data['users'])}")
            if data.get('interfaces'):
                print(f"  Interfaces: {dict(data['interfaces'])}")

    elif command == "by-interface":
        by_interface = reader.get_all_containers_by_interface()

        interface_names = {
            INTERFACE_ORCHESTRATION: "DS01 ORCHESTRATION",
            INTERFACE_ATOMIC: "DS01 ATOMIC",
            INTERFACE_DOCKER: "DOCKER DIRECT",
            INTERFACE_OTHER: "OTHER (VS Code, Compose, etc.)"
        }

        for interface, containers in by_interface.items():
            print(f"\n{interface_names.get(interface, interface)} ({len(containers)}):")
            if not containers:
                print("  (none)")
            for c in containers:
                status = "🟢" if c['running'] else "○"
                gpu = f"GPU:{c['gpu']}" if c['gpu'] else "no GPU"
                print(f"  {status} {c['name']} [{c['user']}] {gpu}")

    elif command == "json":
        allocations = reader.get_all_allocations()
        print(json.dumps(allocations, indent=2, default=str))

    elif command == "json-by-interface":
        by_interface = reader.get_all_containers_by_interface()
        print(json.dumps(by_interface, indent=2, default=str))

    elif command == "container" and len(sys.argv) > 2:
        container_name = sys.argv[2]
        gpu_info = reader.get_container_gpu(container_name)
        if gpu_info:
            print(json.dumps(gpu_info, indent=2))
        else:
            print(f"Container {container_name} has no GPU or not found")
            sys.exit(1)

    elif command == "user" and len(sys.argv) > 2:
        username = sys.argv[2]
        allocations = reader.get_user_allocations(username)
        total_mig = reader.get_user_mig_total(username)
        print(f"GPU allocations for {username} (total: {total_mig} MIG-equiv):")
        for alloc in allocations:
            status = "🟢" if alloc['running'] else "○"
            interface = f"[{alloc.get('interface', '?')}]"
            mig_equiv = alloc.get('mig_equiv', 1)
            gpu_slots = alloc.get('gpu_slots', [alloc['gpu_slot']])
            slots_str = ','.join(gpu_slots) if len(gpu_slots) > 1 else alloc['gpu_slot']
            mig_info = f"({mig_equiv} MIG-equiv)" if mig_equiv > 1 else ""
            print(f"  {status} {alloc['container']}: GPU {slots_str} {mig_info} {interface}")

    elif command == "user-mig-total" and len(sys.argv) > 2:
        username = sys.argv[2]
        total = reader.get_user_mig_total(username)
        print(total)

    elif command == "user-gpu-count" and len(sys.argv) > 2:
        username = sys.argv[2]
        count = reader.get_user_gpu_count(username)
        print(count)

    elif command == "unmanaged":
        unmanaged = reader.get_unmanaged_gpu_containers()
        if not unmanaged:
            print("No unmanaged GPU containers detected.")
        else:
            print(f"\n⚠️  UNMANAGED GPU CONTAINERS ({len(unmanaged)}):")
            print("   (These containers bypass DS01 tracking and resource limits)\n")
            for c in unmanaged:
                status = "🟢" if c['running'] else "○"
                gpu_str = "all GPUs" if c['gpu_count'] == -1 else f"{c['gpu_count']} GPU(s)"
                access_warning = " ⚠️ UNRESTRICTED" if c['access_type'] == 'all' else ""
                print(f"  {status} {c['name']}")
                print(f"      User: {c['user']}")
                print(f"      GPUs: {gpu_str}{access_warning}")
                if c['labels']['compose_project']:
                    print(f"      Compose: {c['labels']['compose_project']}/{c['labels']['compose_service']}")
                if c['labels']['devcontainer']:
                    print(f"      DevContainer: {c['labels']['devcontainer']}")
                print()

    elif command == "json-unmanaged":
        unmanaged = reader.get_unmanaged_gpu_containers()
        print(json.dumps(unmanaged, indent=2, default=str))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
