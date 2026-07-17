"""
System test fixtures for DS01 lifecycle testing.

These fixtures operate on the live system with real Docker containers and GPUs.
They back up and restore config, create real containers, and run lifecycle scripts.
"""

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

INFRA_ROOT = Path("/opt/ds01-infra")
CONFIG_FILE = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
DOCKER_BIN = "/usr/bin/docker"
GPU_STATE_READER = INFRA_ROOT / "scripts" / "docker" / "gpu-state-reader.py"
NVIDIA_SMI = "/usr/bin/nvidia-smi"


# =============================================================================
# Helpers
# =============================================================================


def real_docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Call /usr/bin/docker directly, bypassing the DS01 wrapper."""
    return subprocess.run(
        [DOCKER_BIN, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_lifecycle_script(name: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a lifecycle script as root, returns CompletedProcess."""
    # Scripts live in monitoring/ or maintenance/
    for subdir in ("monitoring", "maintenance"):
        path = INFRA_ROOT / "scripts" / subdir / name
        if path.exists():
            return subprocess.run(
                [str(path), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    raise FileNotFoundError(f"Lifecycle script not found: {name}")


def container_running(name: str) -> bool:
    """Check if a container is running."""
    result = real_docker("inspect", "-f", "{{.State.Running}}", name)
    return result.returncode == 0 and result.stdout.strip() == "true"


def container_exists(name: str) -> bool:
    """Check if a container exists (any state)."""
    result = real_docker("inspect", name)
    return result.returncode == 0


# =============================================================================
# GPU safety: CI must never take a GPU a real user is on.
#
# free_gpu_indices() cross-checks two independent sources:
#   1. gpu-state-reader.py (Docker allocations — the DS01 SSOT): is a GPU handed
#      to any ds01-managed container right now?
#   2. nvidia-smi directly: is a compute process actually running on it, or does
#      it show nonzero utilization/memory? This catches GPU usage the Docker-side
#      view can't see (e.g. a process outside DS01 tracking entirely).
# A GPU only counts as free if BOTH sources say so. Any failure to read either
# source fails closed (treated as "not free"), never open.
# =============================================================================


def _all_gpu_indices() -> list[str]:
    """All physical GPU indices on the box, per nvidia-smi."""
    result = subprocess.run(
        [NVIDIA_SMI, "--query-gpu=index", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _ds01_allocated_gpu_indices() -> set[str]:
    """Full-GPU slot indices currently allocated to some ds01-managed container.

    Reads gpu-state-reader.py's `json` output — the Docker-derived SSOT for GPU
    allocations (HostConfig/labels on real containers). Slots with a "." are MIG
    slices, not full-GPU indices, and are ignored here since ds01-ci-bot's tests
    allocate full GPUs.

    Note: a read failure here returns an empty set (looks "unallocated"), which
    is NOT safe on its own — free_gpu_indices() always combines this with the
    nvidia-smi cross-check below, which fails closed independently.
    """
    try:
        result = subprocess.run(
            ["python3", str(GPU_STATE_READER), "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        allocations = json.loads(result.stdout) if result.returncode == 0 else {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        allocations = {}

    return {
        str(slot)
        for slot, data in allocations.items()
        if "." not in str(slot) and data.get("containers")
    }


def _nvidia_busy_gpu_indices() -> set[str]:
    """GPU indices with a running compute process, or nonzero util/memory.

    This is the independent-of-Docker check: it catches GPU usage that never
    went through a ds01-managed container (so gpu-state-reader wouldn't see it).
    Fails closed — if nvidia-smi can't be queried, every index is reported busy.
    """
    all_indices = set(_all_gpu_indices())
    if not all_indices:
        return set()

    try:
        apps = subprocess.run(
            [NVIDIA_SMI, "--query-compute-apps=gpu_uuid", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        query = subprocess.run(
            [
                NVIDIA_SMI,
                "--query-gpu=index,uuid,utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return all_indices  # fail closed: can't verify, assume busy

    if apps.returncode != 0 or query.returncode != 0:
        return all_indices  # fail closed

    busy_uuids = {line.strip() for line in apps.stdout.splitlines() if line.strip()}

    busy = set()
    for line in query.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            continue
        index, gpu_uuid, util, mem_used = parts
        if gpu_uuid in busy_uuids:
            busy.add(index)
            continue
        try:
            if int(util) > 0 or int(mem_used) > 0:
                busy.add(index)
        except ValueError:
            busy.add(index)  # unparseable reading — fail closed

    return busy


def free_gpu_indices() -> list[str]:
    """GPU indices that are genuinely free: no ds01 allocation AND no compute use.

    A GPU is free only if it has NO ds01 allocation (gpu-state-reader.py) AND no
    running compute process / nonzero utilization (nvidia-smi). This is the hard
    guarantee that CI never competes with real user workloads for GPU capacity.
    """
    all_indices = set(_all_gpu_indices())
    unavailable = _ds01_allocated_gpu_indices() | _nvidia_busy_gpu_indices()
    return sorted(all_indices - unavailable, key=int)


def free_gpu_count() -> int:
    """Number of GPUs that are genuinely free right now (see free_gpu_indices)."""
    return len(free_gpu_indices())


def retry_with_backoff(
    fn: Callable[[], subprocess.CompletedProcess], attempts: int = 3, base: float = 1.0
) -> subprocess.CompletedProcess:
    """Retry fn() with exponential backoff (base, 2*base, 4*base, ...) on transient failures.

    Only retries when the failure looks transient — exit 125 (Docker daemon
    hiccup) or "unavailable"/"temporarily" in the output (a brief allocation
    race clearing). Any other result — success, or a "real" failure — returns
    immediately without retrying.
    """
    result = fn()
    for attempt in range(attempts - 1):
        if result.returncode == 0 or not _is_transient_failure(result):
            return result
        time.sleep(base * (2**attempt))
        result = fn()
    return result


def _is_transient_failure(result: subprocess.CompletedProcess) -> bool:
    """Heuristic for "worth retrying": exit 125, or an unavailable/temporary error."""
    if result.returncode == 125:
        return True
    text = f"{result.stdout or ''}{result.stderr or ''}".lower()
    return "unavailable" in text or "temporarily" in text


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def require_free_gpus() -> Callable[[int], list[str]]:
    """Factory fixture: require_free_gpus(n) skips the test unless n GPUs are free.

    GPU-allocating tests depend on this fixture and call it with the number of
    GPUs they need, e.g. `require_free_gpus(2)`. This is the hard guarantee that
    CI never takes GPUs away from live user workloads: if there aren't enough
    genuinely-free GPUs (see free_gpu_indices), the test is skipped rather than
    racing real users for capacity. Returns the free indices on success, so
    tests that need specific GPUs can select from them dynamically.
    """

    def _require(n: int) -> list[str]:
        free = free_gpu_indices()
        if len(free) < n:
            pytest.skip(
                f"{n} GPUs required, only {len(free)} free — skipping to avoid "
                "competing with live user workloads"
            )
        return free

    return _require


@pytest.fixture(scope="module")
def runtime_config_backup():
    """Back up resource-limits.yaml and restore it on teardown."""
    backup = CONFIG_FILE.with_suffix(".yaml.bak-runtime-test")
    shutil.copy2(CONFIG_FILE, backup)
    yield backup
    # Restore original
    shutil.copy2(backup, CONFIG_FILE)
    backup.unlink(missing_ok=True)


CRON_FILE = Path("/etc/cron.d/ds01-maintenance")
CRON_DISABLED = Path("/etc/cron.d/ds01-maintenance.disabled-by-test")


@pytest.fixture(scope="module")
def lowered_timeouts(runtime_config_backup):
    """Modify resource-limits.yaml with short timeouts for testing, restore on teardown.

    Also disables the ds01-maintenance cron to prevent real cron jobs from running
    with lowered timeouts against non-test containers.
    """
    # Disable lifecycle cron BEFORE modifying config, so real cron jobs
    # cannot fire with lowered timeouts against production containers.
    cron_was_disabled = False
    if CRON_FILE.exists():
        CRON_FILE.rename(CRON_DISABLED)
        cron_was_disabled = True

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    # Lower timeouts for testing
    config["policies"]["grace_period_m"] = 2
    config["policies"]["created_container_timeout_m"] = 2
    config["defaults"]["idle_timeout_h"] = 0.083
    config["defaults"]["container_hold_after_stop_h"] = 0.033

    # Also lower container_types docker idle to ~5m
    if "container_types" in config and "docker" in config["container_types"]:
        config["container_types"]["docker"]["idle_timeout_h"] = 0.083

    with open(CONFIG_FILE, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    yield

    # Restore config FIRST, then re-enable cron. This ensures cron never
    # fires with lowered test values. (runtime_config_backup also restores,
    # but that runs after this teardown — too late for safe cron re-enable.)
    shutil.copy2(runtime_config_backup, CONFIG_FILE)
    if cron_was_disabled and CRON_DISABLED.exists():
        CRON_DISABLED.rename(CRON_FILE)
