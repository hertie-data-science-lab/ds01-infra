"""
Runtime test fixtures for DS01 lifecycle testing.

These fixtures operate on the live system with real Docker containers and GPUs.
They back up and restore config, create real containers, and run lifecycle scripts.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

INFRA_ROOT = Path("/opt/ds01-infra")
CONFIG_FILE = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
DOCKER_BIN = "/usr/bin/docker"


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
# Fixtures
# =============================================================================


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
    config["policies"]["grace_period"] = "2m"
    config["policies"]["created_container_timeout"] = "2m"
    config["defaults"]["idle_timeout"] = "5m"
    config["defaults"]["container_hold_after_stop"] = "2m"

    # Also lower container_types docker idle to 5m
    if "container_types" in config and "docker" in config["container_types"]:
        config["container_types"]["docker"]["idle_timeout"] = "5m"

    with open(CONFIG_FILE, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    yield

    # Restore config FIRST, then re-enable cron. This ensures cron never
    # fires with lowered test values. (runtime_config_backup also restores,
    # but that runs after this teardown — too late for safe cron re-enable.)
    shutil.copy2(runtime_config_backup, CONFIG_FILE)
    if cron_was_disabled and CRON_DISABLED.exists():
        CRON_DISABLED.rename(CRON_FILE)
