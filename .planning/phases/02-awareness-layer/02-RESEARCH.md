# Phase 2: Awareness Layer - Research

**Researched:** 2026-01-30
**Domain:** Docker API monitoring, Linux process detection, systemd scheduling
**Confidence:** HIGH

## Summary

Phase 2 requires detecting ALL GPU workloads regardless of how they were created: DS01-managed containers, unmanaged containers (docker-compose, devcontainers, raw docker run), and host GPU processes. The standard approach uses Docker Python SDK for container detection, nvidia-smi + /proc for host processes, and systemd timers for scheduling periodic scans.

Critical finding: Docker labels cannot be added to running containers via the API. Containers must be recreated to receive new labels. This fundamentally shapes the detection strategy - we can only apply cgroup slices to running containers, not add tracking labels until restart.

**Primary recommendation:** Use Docker Python SDK for comprehensive container inspection, psutil for robust process attribution, systemd timer (not daemon) for scheduled scanning, and docker update for applying restart policies to stopped containers.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Docker Python SDK (docker-py) | 7.1.0+ | Docker API access | Official Docker SDK, comprehensive container inspection |
| systemd timers | native | Scheduled scanning | Built-in, reliable, better than cron for services |
| nvidia-smi | native | GPU process detection | NVIDIA's official tool, universally available |
| jq | 1.6+ | JSON query/filtering | Standard for structured data filtering |
| psutil | 7.2.2+ | Process information | Cross-platform, robust process owner detection |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python subprocess | stdlib | Shell command integration | Wrapping nvidia-smi, docker CLI |
| /proc filesystem | kernel | Process metadata | Direct access to PID owner, cmdline |
| systemd-run | native | Transient unit creation | Launching new processes in cgroups |
| docker CLI | native | Fallback operations | When Python SDK doesn't expose feature |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| systemd timer | Long-running daemon | Timer is simpler, self-healing, lower resource use |
| Docker Python SDK | docker CLI + subprocess | SDK provides type safety, cleaner error handling |
| /proc filesystem | psutil library | psutil is cross-platform but adds dependency; /proc is universal on Linux |
| jq filtering | Python JSON parsing | jq is faster for command-line queries, Python better for complex logic |

**Installation:**
```bash
# Python dependencies
pip3 install docker psutil

# System dependencies (typically pre-installed)
sudo apt-get install jq

# Verify systemd timer support
systemctl --version  # Should show systemd 219+
```

## Architecture Patterns

### Recommended Project Structure
```
scripts/monitoring/
├── detect-workloads.py       # Main detection scanner
├── ds01-workloads            # Query command (bash wrapper)
└── workload-detector.service # Systemd service unit
    workload-detector.timer   # Systemd timer unit

/var/lib/ds01/
└── workload-inventory.json   # Persistent state file

/var/log/ds01/
└── events.jsonl              # Event log (Phase 1 integration)
```

### Pattern 1: Systemd Timer for Periodic Scanning
**What:** Timer triggers service every 30 seconds, service runs detection script once and exits
**When to use:** Periodic monitoring tasks that don't need to run continuously
**Example:**
```ini
# Source: systemd.timer official documentation
# /etc/systemd/system/workload-detector.timer
[Unit]
Description=DS01 Workload Detection Timer
Requires=workload-detector.service

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
AccuracySec=1s
Persistent=false

[Install]
WantedBy=timers.target
```

**Service unit:**
```ini
# /etc/systemd/system/workload-detector.service
[Unit]
Description=DS01 Workload Detection Scanner
After=docker.service

[Service]
Type=oneshot
ExecStart=/opt/ds01-infra/scripts/monitoring/detect-workloads.py
TimeoutSec=25s
```

**Key points:**
- `OnUnitActiveSec=30s` - Run 30s after last successful run
- `AccuracySec=1s` - High precision (default is 1min)
- `Type=oneshot` - Service exits after one run
- `Persistent=false` - Don't catch up missed runs on boot
- `TimeoutSec=25s` - Shorter than timer interval to prevent overlap

### Pattern 2: Docker Python SDK Container Inspection
**What:** List all containers (running and stopped), inspect labels and state
**When to use:** Need comprehensive container metadata including labels, env vars, config
**Example:**
```python
# Source: Docker SDK for Python official documentation
import docker

client = docker.from_env()

# List ALL containers (including stopped)
containers = client.containers.list(all=True)

for container in containers:
    # Access cached attributes
    name = container.name
    status = container.status  # 'running', 'exited', etc.
    labels = container.labels  # dict of labels

    # Reload from server if needed
    container.reload()

    # Check for specific labels
    is_managed = 'ds01.managed' in labels
    is_detected = 'ds01.detected' in labels
    has_gpu = labels.get('ds01.gpu.allocated')

    # Inspect full configuration
    config = container.attrs
    env_vars = config['Config']['Env']
    runtime = config['HostConfig'].get('Runtime')  # 'nvidia' for GPU
```

**Filter by label:**
```python
# Get only containers with specific label
gpu_containers = client.containers.list(
    all=True,
    filters={'label': 'ds01.gpu.allocated'}
)

# Multiple label filters (AND logic)
unmanaged = client.containers.list(
    all=True,
    filters={'label': ['!ds01.managed', '!ds01.detected']}
)
```

### Pattern 3: Container Origin Classification
**What:** Identify how container was created using label inspection
**When to use:** Need to categorize containers for different handling policies
**Example:**
```python
# Source: Docker label standards + devcontainer spec
def classify_container(container) -> str:
    """
    Classify container origin in priority order.

    Returns: 'ds01-managed', 'devcontainer', 'compose', 'raw-docker', 'unknown'
    """
    labels = container.labels

    # Priority 1: DS01 labels
    if 'ds01.managed' in labels:
        return 'ds01-managed'
    if 'ds01.detected' in labels:
        return 'ds01-detected'  # Already processed

    # Priority 2: Devcontainer labels
    if any(k.startswith('devcontainer.') for k in labels):
        return 'devcontainer'

    # Priority 3: Docker Compose labels
    if 'com.docker.compose.project' in labels:
        return 'compose'

    # Priority 4: Check name/image patterns
    if container.name.startswith('vsc-'):  # VS Code devcontainer naming
        return 'devcontainer'

    # Default: raw docker run or API-created
    return 'raw-docker'
```

**Common label patterns:**
- DS01: `ds01.managed=true`, `ds01.user=alice`, `ds01.gpu.allocated=0:1`
- Devcontainer: `devcontainer.metadata`, `devcontainer.local_folder`
- Compose: `com.docker.compose.project=myapp`, `com.docker.compose.service=web`

### Pattern 4: GPU Process Detection via nvidia-smi
**What:** Query GPU compute processes, match PIDs to users via /proc
**When to use:** Detecting host GPU processes outside containers
**Example:**
```python
# Source: nvidia-smi query documentation
import subprocess
import json

# Get GPU processes as CSV
result = subprocess.run(
    ['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'],
    capture_output=True,
    text=True,
    timeout=5
)

gpu_pids = []
for line in result.stdout.strip().split('\n'):
    if line:
        pid, mem = line.split(',')
        gpu_pids.append({
            'pid': int(pid.strip()),
            'gpu_memory_mb': int(mem.strip())
        })

# Attribute PIDs to users via /proc
for proc in gpu_pids:
    pid = proc['pid']

    # Read process owner UID from /proc/[pid]/status
    try:
        with open(f'/proc/{pid}/status', 'r') as f:
            for line in f:
                if line.startswith('Uid:'):
                    uid = int(line.split()[1])  # Real UID
                    proc['uid'] = uid
                    break

        # Read command line from /proc/[pid]/cmdline
        with open(f'/proc/{pid}/cmdline', 'rb') as f:
            cmdline_bytes = f.read()
            # Split on null bytes, filter empty strings
            cmdline = [s.decode('utf-8', errors='replace')
                      for s in cmdline_bytes.split(b'\0') if s]
            proc['cmdline'] = ' '.join(cmdline)

        # Resolve UID to username
        result = subprocess.run(
            ['getent', 'passwd', str(uid)],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0:
            proc['user'] = result.stdout.split(':')[0]

    except (FileNotFoundError, PermissionError, ProcessLookupError):
        # Process may have exited, or permission denied
        proc['user'] = 'unknown'
        proc['cmdline'] = ''
```

**Alternative using psutil:**
```python
# Source: psutil documentation
import psutil

try:
    process = psutil.Process(pid)
    user = process.username()
    cmdline = ' '.join(process.cmdline())
except (psutil.NoSuchProcess, psutil.AccessDenied):
    user = 'unknown'
    cmdline = ''
```

**Pitfall:** nvidia-smi PID information can be incomplete in containers due to namespace issues. Always handle missing PIDs gracefully.

### Pattern 5: Cgroup Slice Application
**What:** Apply systemd cgroup slices to already-running containers
**When to use:** Soft enforcement - apply resource limits without stopping containers
**Example:**
```bash
# Source: systemd cgroup documentation + Docker update command
# CRITICAL: Cannot change --cgroup-parent on running container
# Must use systemd scope wrapping or restart container

# Option 1: Create systemd scope for existing PID (complex)
# Get container's main PID
CONTAINER_PID=$(docker inspect -f '{{.State.Pid}}' container_name)

# Create transient scope in ds01.slice
systemd-run --scope --slice=ds01.slice --unit=ds01-container-${CONTAINER_PID} \
    --property=Delegate=yes \
    sleep infinity &

# Move container's cgroup into scope (complex, error-prone)
# This approach is fragile and not recommended

# Option 2: Update restart policy and wait for next restart (preferred)
docker update --restart=unless-stopped container_name

# Option 3: Force restart with new cgroup-parent (invasive)
# Get container config
CONFIG=$(docker inspect container_name)
# Stop container
docker stop container_name
# Remove container (keeping data)
docker rm container_name
# Recreate with --cgroup-parent=ds01.slice
docker run --cgroup-parent=ds01.slice [... restored config ...]
```

**CRITICAL FINDING:** Docker does not support changing cgroup-parent on running containers. Options:
1. **Defer enforcement** - Wait for container to restart naturally
2. **Update restart policy** - Ensure next boot applies slice
3. **Force restart** - Invasive but immediate (use sparingly)

### Pattern 6: State Persistence and Event Emission
**What:** Persist inventory to JSON file, emit events on state changes
**When to use:** Track workload lifecycle across scanner runs
**Example:**
```python
# Source: DS01 event logging pattern (Phase 1)
import json
from pathlib import Path

INVENTORY_FILE = Path('/var/lib/ds01/workload-inventory.json')

def load_inventory():
    """Load previous inventory state."""
    if INVENTORY_FILE.exists():
        return json.loads(INVENTORY_FILE.read_text())
    return {'containers': {}, 'host_processes': {}}

def save_inventory(inventory):
    """Persist current inventory state."""
    INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_FILE.write_text(json.dumps(inventory, indent=2))

def detect_changes(old_inventory, new_inventory):
    """Emit events for state transitions."""
    from ds01_events import log_event

    old_containers = set(old_inventory['containers'].keys())
    new_containers = set(new_inventory['containers'].keys())

    # New workloads detected
    for cid in new_containers - old_containers:
        container = new_inventory['containers'][cid]
        log_event(
            'detection.container_discovered',
            user=container.get('user', 'unknown'),
            details={
                'container': container['name'],
                'origin': container['origin'],
                'has_gpu': container.get('has_gpu', False)
            }
        )

    # Workloads exited
    for cid in old_containers - new_containers:
        container = old_inventory['containers'][cid]
        log_event(
            'detection.container_exited',
            user=container.get('user', 'unknown'),
            details={'container': container['name']}
        )
```

**State file format:**
```json
{
  "last_scan": "2026-01-30T14:30:00Z",
  "containers": {
    "abc123": {
      "id": "abc123",
      "name": "my-container",
      "origin": "devcontainer",
      "user": "alice",
      "has_gpu": true,
      "gpu_devices": ["0"],
      "status": "running",
      "detected_at": "2026-01-30T14:00:00Z"
    }
  },
  "host_processes": {
    "12345": {
      "pid": 12345,
      "user": "bob",
      "cmdline": "python train.py",
      "gpu_memory_mb": 2048
    }
  }
}
```

### Anti-Patterns to Avoid
- **Long-running daemon** - Use systemd timer instead. Daemons add complexity and don't auto-restart on crash.
- **Adding labels to running containers** - Not possible. Don't try to call `docker update --label`, it doesn't exist.
- **Blocking on Docker API** - Use timeouts on all docker/subprocess calls. API can hang.
- **Assuming PID stability** - Process PIDs can be reused. Always validate process still exists before acting.
- **Trusting nvidia-smi PIDs in containers** - Namespace issues can cause missing PIDs. Handle gracefully.
- **Direct cgroupfs manipulation** - On systemd systems, use systemd API. Don't write to /sys/fs/cgroup directly.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Process owner detection | Parse /etc/passwd manually | `getent passwd UID` or psutil | Handles LDAP, NIS, edge cases |
| JSON filtering in bash | Python loops | jq | Optimised, handles edge cases, standard tool |
| Process monitoring | Poll /proc in loop | systemd timer + oneshot service | Self-healing, resource efficient |
| Container API calls | Parse `docker ps` output | Docker Python SDK | Type-safe, handles API changes |
| Cgroup manipulation | Write to /sys/fs/cgroup | systemd-run, docker update | Avoids race conditions with systemd |
| GPU process detection | Parse nvidia-smi table output | `nvidia-smi --query-compute-apps=... --format=csv` | Structured output, forward compatible |
| Duration parsing | Custom regex | Reuse ds01_core.parse_duration | Already handles all edge cases |

**Key insight:** Process and container monitoring has many edge cases (PIDs reused, permissions denied, processes exit mid-query, namespace issues). Established tools handle these robustly.

## Common Pitfalls

### Pitfall 1: Docker Labels Cannot Be Modified on Running Containers
**What goes wrong:** Attempt to add `ds01.detected.*` labels to running containers fails
**Why it happens:** Docker API design - labels are immutable after creation (exception: Swarm services)
**How to avoid:** Use alternative tracking mechanisms:
- Persist detection state in separate JSON file
- Update restart policy so next boot includes labels
- Accept that labels only apply to future container restarts
**Warning signs:**
- `docker update --label` command doesn't exist
- Docker API update endpoint doesn't accept labels parameter
- GitHub issues dating back to 2015 requesting this feature

**Sources:**
- [Docker labels documentation](https://docs.docker.com/engine/manage-resources/labels/)
- [GitHub issue #15496 - Add labels to running containers](https://github.com/moby/moby/issues/15496)

### Pitfall 2: Cgroup Parent Cannot Be Changed on Running Containers
**What goes wrong:** Attempting to move container to ds01.slice fails while container is running
**Why it happens:** Docker sets cgroup-parent at container creation, cannot be changed at runtime
**How to avoid:**
- Apply cgroup slices only to new containers via docker wrapper
- For existing containers, update restart policy and wait for natural restart
- Document that unmanaged containers get slice on next boot, not immediately
**Warning signs:**
- `docker update --cgroup-parent` doesn't exist
- Systemd scope creation for existing PID is complex and fragile
- Direct cgroupfs manipulation conflicts with systemd

**Sources:**
- [Docker cgroup-parent documentation](https://docs.docker.com/engine/containers/runmetrics/)
- [Medium article on Docker cgroup management](https://baykara.medium.com/docker-resource-management-via-cgroups-and-systemd-633b093a835c)

### Pitfall 3: Transient GPU Processes Cause Detection Noise
**What goes wrong:** Short-lived GPU processes appear in one scan, gone by next scan, spam event log
**Why it happens:** ML workflows often spawn GPU processes for seconds (model loading, validation)
**How to avoid:**
- Track processes across scans before emitting events
- Emit events only for processes that persist across 2+ scans (60+ seconds)
- Exclude known system processes (nvidia-persistenced, Xorg, DCGM)
- Document that very brief GPU usage may not trigger events
**Warning signs:**
- Event log filled with process_discovered → process_exited within seconds
- Same PID numbers appearing repeatedly (PID reuse)
- System processes triggering alerts

**Sources:**
- [NVIDIA forums - GPU process handling](https://forums.developer.nvidia.com/t/nvidia-smi-no-running-processes-found/128926)

### Pitfall 4: /proc Files Use Null Byte Separators
**What goes wrong:** Reading `/proc/[pid]/cmdline` with normal file operations returns garbled text
**Why it happens:** Arguments separated by null bytes `\0`, not spaces or newlines
**How to avoid:**
```python
# Correct approach
with open(f'/proc/{pid}/cmdline', 'rb') as f:
    cmdline_bytes = f.read()
    args = [s.decode('utf-8', errors='replace') for s in cmdline_bytes.split(b'\0') if s]
    cmdline = ' '.join(args)

# Shell approach
cat /proc/12345/cmdline | tr '\0' ' '
```
**Warning signs:**
- Command line appears as single long string with no spaces
- Binary characters in output
- Python string operations fail on cmdline

**Sources:**
- [proc(5) man page - cmdline format](https://man7.org/linux/man-pages/man5/proc.5.html)
- [proc_pid_cmdline(5) man page](https://www.man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html)

### Pitfall 5: nvidia-smi PID Information Missing in Containers
**What goes wrong:** GPU memory is allocated but nvidia-smi shows no processes or wrong PIDs
**Why it happens:** Container namespace issues, especially pre-Linux 4.1 kernels lacking NSpid support
**How to avoid:**
- Always handle missing PIDs gracefully (don't crash)
- Cross-reference with Docker inspect for container GPU assignments
- For containers, use Docker labels as source of truth, not nvidia-smi
- Log warning when GPU memory allocated but no PID found
**Warning signs:**
- GPU memory shows usage in nvidia-smi but processes list is empty
- PID shown in nvidia-smi doesn't exist in /proc
- Containerised workloads missing from detection

**Sources:**
- [GitHub issue #1483 - nvidia-smi gets wrong PIDs](https://github.com/NVIDIA/nvidia-docker/issues/1483)
- [NVIDIA forums - processes missing from nvidia-smi](https://forums.developer.nvidia.com/t/11-gb-of-gpu-ram-used-and-no-process-listed-by-nvidia-smi/44459)

### Pitfall 6: Cgroup v1 vs v2 Path Differences
**What goes wrong:** Hardcoded cgroup paths break on systems using cgroup v2
**Why it happens:** Completely different filesystem layout between v1 and v2
**How to avoid:**
- Detect cgroup version: check for `/sys/fs/cgroup/cgroup.controllers` (v2) vs `/sys/fs/cgroup/memory/` (v1)
- Use systemd API instead of direct filesystem access
- Let Docker manage cgroup paths via `--cgroup-parent` flag
- Test on both Ubuntu 20.04 (v1) and Ubuntu 22.04+ (v2)
**Warning signs:**
- Cgroup paths like `/sys/fs/cgroup/memory/docker/` don't exist
- systemd slice application fails silently
- Resource limits not being applied

**Sources:**
- [Rootless containers cgroup v2 guide](https://rootlesscontaine.rs/getting-started/common/cgroup2/)
- [Docker forums - cgroup v2 issues](https://forums.docker.com/t/docker-container-fails-to-start-with-cgroup-v2-and-partition-other-than-member/141284)

### Pitfall 7: Systemd Timer Accuracy Defaults to 1 Minute
**What goes wrong:** Timer configured for 30s interval actually runs every ~30-90s randomly
**Why it happens:** systemd AccuracySec defaults to 1min for power management
**How to avoid:**
```ini
[Timer]
OnUnitActiveSec=30s
AccuracySec=1s  # CRITICAL: Set to 1s for precise timing
```
**Warning signs:**
- Detection delays vary wildly (30-90 seconds)
- Success criteria "within 60 seconds" barely met
- Timer appears to skip runs

**Sources:**
- [systemd.timer documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
- [ArchWiki systemd/Timers](https://wiki.archlinux.org/title/Systemd/Timers)

## Code Examples

Verified patterns from official sources:

### List All Containers with GPU Detection
```python
# Source: Docker SDK for Python documentation
import docker

client = docker.from_env()

def has_gpu_access(container):
    """Check if container has GPU access via runtime or devices."""
    config = container.attrs['HostConfig']

    # Method 1: nvidia runtime
    if config.get('Runtime') == 'nvidia':
        return True

    # Method 2: --gpus flag (creates DeviceRequests)
    if config.get('DeviceRequests'):
        for req in config['DeviceRequests']:
            if 'nvidia' in req.get('Capabilities', []):
                return True

    # Method 3: Manual device mapping (old approach)
    devices = config.get('Devices', [])
    for dev in devices:
        if 'nvidia' in dev.get('PathOnHost', ''):
            return True

    return False

# Scan all containers
all_containers = client.containers.list(all=True)
for container in all_containers:
    print(f"{container.name}: GPU={has_gpu_access(container)}, Status={container.status}")
```

### Detect Unmanaged Containers
```python
# Source: Docker label standards + DS01 patterns
def detect_unmanaged_containers(client):
    """Find containers not managed by DS01."""
    all_containers = client.containers.list(all=True)
    unmanaged = []

    for container in all_containers:
        labels = container.labels

        # Skip DS01-managed containers
        if 'ds01.managed' in labels:
            continue

        # Skip already-detected containers
        if 'ds01.detected' in labels:
            continue

        # This is an unmanaged container
        origin = classify_container(container)
        unmanaged.append({
            'id': container.id[:12],
            'name': container.name,
            'origin': origin,
            'has_gpu': has_gpu_access(container),
            'status': container.status,
            'labels': labels
        })

    return unmanaged
```

### Host GPU Process Detection
```python
# Source: nvidia-smi query documentation + /proc filesystem
import subprocess
from pathlib import Path

def detect_host_gpu_processes():
    """Detect GPU processes running on host (not in containers)."""
    # Get GPU processes
    result = subprocess.run(
        ['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'],
        capture_output=True,
        text=True,
        timeout=5
    )

    processes = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue

        pid_str, mem_str = line.split(',')
        pid = int(pid_str.strip())

        # Check if PID is in a container
        cgroup_path = Path(f'/proc/{pid}/cgroup')
        try:
            cgroup_content = cgroup_path.read_text()
            is_container = 'docker' in cgroup_content or 'containerd' in cgroup_content
        except (FileNotFoundError, PermissionError):
            continue  # Process exited or permission denied

        if is_container:
            continue  # Skip container processes

        # Get process owner
        try:
            status_path = Path(f'/proc/{pid}/status')
            for line in status_path.read_text().split('\n'):
                if line.startswith('Uid:'):
                    uid = int(line.split()[1])
                    break

            # Resolve username
            user_result = subprocess.run(
                ['getent', 'passwd', str(uid)],
                capture_output=True,
                text=True,
                timeout=1
            )
            user = user_result.stdout.split(':')[0] if user_result.returncode == 0 else 'unknown'

            # Get command line
            cmdline_path = Path(f'/proc/{pid}/cmdline')
            cmdline_bytes = cmdline_path.read_bytes()
            cmdline = ' '.join(s.decode('utf-8', errors='replace')
                             for s in cmdline_bytes.split(b'\0') if s)

            processes.append({
                'pid': pid,
                'user': user,
                'cmdline': cmdline,
                'gpu_memory_mb': int(mem_str.strip())
            })

        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue  # Process exited

    return processes
```

### Systemd Timer Management
```bash
# Source: systemd timer best practices
# Install timer and service
sudo cp workload-detector.timer /etc/systemd/system/
sudo cp workload-detector.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start timer
sudo systemctl enable workload-detector.timer
sudo systemctl start workload-detector.timer

# Check timer status
systemctl list-timers workload-detector.timer

# View service logs
journalctl -u workload-detector.service -f

# Test service manually
sudo systemctl start workload-detector.service

# Stop timer
sudo systemctl stop workload-detector.timer
```

### Query Inventory with jq
```bash
# Source: jq manual + DS01 patterns
INVENTORY=/var/lib/ds01/workload-inventory.json

# List all unmanaged containers with GPU
jq '.containers | to_entries[] | select(.value.origin != "ds01-managed" and .value.has_gpu) | .value' "$INVENTORY"

# Count containers by origin
jq '.containers | to_entries | group_by(.value.origin) | map({origin: .[0].value.origin, count: length})' "$INVENTORY"

# List host GPU processes by user
jq '.host_processes | to_entries[] | .value | select(.user != "unknown")' "$INVENTORY"

# Find containers detected in last hour
jq --arg since "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
   '.containers | to_entries[] | select(.value.detected_at >= $since) | .value' "$INVENTORY"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling `docker ps` output | Docker Python SDK | 2020+ | Type safety, better error handling, access to full metadata |
| Parse nvidia-smi table | `--query-compute-apps` CSV | nvidia-smi 367.38+ | Structured output, no regex parsing |
| Cron jobs | systemd timers | 2015+ (systemd adoption) | Self-healing, better logging, precise timing |
| Manual cgroup writes | systemd API | 2019+ (cgroup v2) | Avoids conflicts with systemd manager |
| `docker run --runtime=nvidia` | `docker run --gpus` | Docker 19.03+ | Simpler syntax, better GPU selection |

**Deprecated/outdated:**
- nvidia-docker v1: Replaced by NVIDIA Container Toolkit (2019)
- docker-py PyPI package naming: Now `docker` package (2020)
- `--runtime=nvidia`: Prefer `--gpus` flag (Docker 19.03+)
- libcgroup tools (cgset, cgcreate): Deprecated in favour of systemd on modern distros

## Open Questions

Things that couldn't be fully resolved:

1. **Cgroup slice application to running containers**
   - What we know: Cannot change --cgroup-parent on running containers via Docker API
   - What's unclear: Whether systemd transient scopes can reliably wrap existing container PIDs
   - Recommendation: Document limitation, apply slices on next restart only

2. **System GPU process filtering**
   - What we know: Need to exclude nvidia-persistenced, Xorg, DCGM from alerts
   - What's unclear: Complete list of system GPU processes across all configurations
   - Recommendation: Start with known list, make configurable for user additions

3. **Transient process threshold**
   - What we know: Brief GPU processes spam event log
   - What's unclear: What duration threshold balances detection speed vs noise (30s? 60s? 120s?)
   - Recommendation: Start with 2-scan threshold (60s), make configurable

4. **Devcontainer detection reliability**
   - What we know: `devcontainer.*` labels exist, `vsc-*` name prefix common
   - What's unclear: Whether all VS Code devcontainers set these labels consistently
   - Recommendation: Use multi-signal detection (labels + name prefix + env vars)

## Sources

### Primary (HIGH confidence)
- [Docker SDK for Python 7.1.0 docs](https://docker-py.readthedocs.io/en/stable/containers.html) - Container listing, inspection, filtering
- [systemd.timer man page](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html) - Timer configuration
- [proc(5) man page](https://man7.org/linux/man-pages/man5/proc.5.html) - /proc filesystem format
- [nvidia-smi documentation](https://nvidia.custhelp.com/app/answers/detail/a_id/3751/~/useful-nvidia-smi-queries) - Query compute apps
- [Docker labels documentation](https://docs.docker.com/engine/manage-resources/labels/) - Label immutability

### Secondary (MEDIUM confidence)
- [Docker Compose label patterns](https://docs.docker.com/reference/compose-file/) - com.docker.compose.* labels
- [Dev Container metadata reference](https://containers.dev/implementors/json_reference/) - devcontainer.* labels
- [ArchWiki systemd/Timers](https://wiki.archlinux.org/title/Systemd/Timers) - Timer best practices
- [psutil 7.2.2 documentation](https://psutil.readthedocs.io/) - Process owner detection

### Tertiary (LOW confidence - requires validation)
- [Medium article on Docker cgroup management](https://baykara.medium.com/docker-resource-management-via-cgroups-and-systemd-633b093a835c) - Cgroup patterns
- [NVIDIA forums discussions](https://forums.developer.nvidia.com/) - GPU process detection edge cases

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Docker SDK, systemd timers, nvidia-smi all officially documented and stable
- Architecture: HIGH - Patterns verified with official documentation
- Don't hand-roll: HIGH - All items have official alternatives with documented advantages
- Pitfalls: MEDIUM - Most verified via official docs, some based on community reports
- Code examples: HIGH - All sourced from official documentation or existing DS01 codebase

**Research date:** 2026-01-30
**Valid until:** 2026-03-01 (30 days - stable domain, slow-moving technologies)

**Key limitations:**
- Cgroup v2 testing needed on Ubuntu 22.04+ systems
- Devcontainer label patterns may vary by VS Code version
- GPU process namespace issues may vary by kernel version
- systemd transient scope reliability for existing PIDs not fully verified
