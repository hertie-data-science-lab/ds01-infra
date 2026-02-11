"""
Runtime lifecycle tests for DS01 Phase 5.

These tests create real Docker containers on the live system and run the actual
lifecycle scripts (idle detection, stale cleanup, GPU health) to validate
end-to-end behaviour.

Requirements:
  - Must run as root (sudo)
  - GPU 1 must be free
  - Takes ~15 minutes (monitoring loop with 60s intervals)

Run:
  sudo pytest runtime/ -m runtime -v
"""

import re
import time
from pathlib import Path

import pytest
import yaml

from .conftest import (
    CONFIG_FILE,
    DOCKER_BIN,
    INFRA_ROOT,
    container_exists,
    container_running,
    real_docker,
    run_lifecycle_script,
)

# All tests in this module are runtime tests; individual tests add
# requires_root/requires_gpu/requires_docker as needed.
pytestmark = [pytest.mark.runtime]

# Test container names (all prefixed ds01-e2e- for easy cleanup)
CONTAINERS = {
    "gpu_idle": "ds01-e2e-gpu-idle",
    "devcontainer": "ds01-e2e-devcontainer",
    "keepalive": "ds01-e2e-keepalive",
    "created": "ds01-e2e-created",
    "unlabelled": "ds01-e2e-unlabelled",
}

# How often to run lifecycle scripts during the monitoring loop
LOOP_INTERVAL_SECONDS = 60
# Maximum time to run the monitoring loop
MAX_LOOP_MINUTES = 15


def _force_cleanup_test_containers():
    """Force-remove all test containers (cleanup helper)."""
    for name in CONTAINERS.values():
        real_docker("rm", "-f", name, timeout=10)
    # Also catch any stragglers
    result = real_docker("ps", "-a", "--filter", "name=ds01-e2e-", "--format", "{{.Names}}")
    if result.returncode == 0 and result.stdout.strip():
        for name in result.stdout.strip().split("\n"):
            real_docker("rm", "-f", name, timeout=10)


@pytest.fixture(scope="module")
def lifecycle_scenario(lowered_timeouts):
    """
    Module-scoped fixture that creates test containers and runs the monitoring loop.

    Creates 5 containers with different characteristics, then repeatedly runs
    the lifecycle scripts until containers are acted upon or timeout.

    Yields a results dict consumed by individual test functions.
    """
    # Clean any leftover test containers from previous runs
    _force_cleanup_test_containers()

    # Also clean any stale state files for test containers
    state_dir = Path("/var/lib/ds01/container-states")
    for name in CONTAINERS.values():
        state_file = state_dir / f"{name}.state"
        if state_file.exists():
            state_file.unlink()

    runtime_state_dir = Path("/var/lib/ds01/container-runtime")
    for name in CONTAINERS.values():
        state_file = runtime_state_dir / f"{name}.state"
        if state_file.exists():
            state_file.unlink()

    # ── Create test containers ────────────────────────────────────────────

    # 1. GPU idle container: sleep with SIGTERM trap, docker labels
    real_docker(
        "run", "-d",
        "--name", CONTAINERS["gpu_idle"],
        "--gpus", '"device=1"',
        "--label", "ds01.user=e2e-test-user",
        "--label", "ds01.container_type=docker",
        "ubuntu:22.04",
        "bash", "-c",
        "trap 'echo SIGTERM received; exit 0' TERM; while true; do sleep 1; done",
    )

    # 2. Devcontainer: exempt from idle timeout
    real_docker(
        "run", "-d",
        "--name", CONTAINERS["devcontainer"],
        "--gpus", '"device=1"',
        "--label", "ds01.user=e2e-test-user",
        "--label", "ds01.container_type=devcontainer",
        "--label", "devcontainer.local_folder=/home/e2e-test-user/project",
        "ubuntu:22.04",
        "bash", "-c", "while true; do sleep 60; done",
    )

    # 3. Keep-alive container: has .keep-alive file
    real_docker(
        "run", "-d",
        "--name", CONTAINERS["keepalive"],
        "--gpus", '"device=1"',
        "--label", "ds01.user=e2e-test-user",
        "--label", "ds01.container_type=docker",
        "ubuntu:22.04",
        "bash", "-c", "mkdir -p /workspace && touch /workspace/.keep-alive && while true; do sleep 60; done",
    )

    # 4. Created-never-started container
    real_docker(
        "create",
        "--name", CONTAINERS["created"],
        "--gpus", '"device=1"',
        "--label", "ds01.user=e2e-test-user",
        "--label", "ds01.container_type=docker",
        "ubuntu:22.04",
        "echo", "never started",
    )

    # 5. Unlabelled container: no DS01 labels, exits immediately
    real_docker(
        "run",
        "--name", CONTAINERS["unlabelled"],
        "ubuntu:22.04",
        "echo", "done",
    )

    # ── Run monitoring loop ───────────────────────────────────────────────

    results = {
        "script_outputs": [],
        "loop_iterations": 0,
        "wall_time_seconds": 0,
    }

    start_time = time.time()
    max_seconds = MAX_LOOP_MINUTES * 60

    while (time.time() - start_time) < max_seconds:
        results["loop_iterations"] += 1

        # Run the three lifecycle scripts in sequence
        # IMPORTANT: Pass --name-filter to scope scripts to test containers only,
        # preventing interference with real running containers on the system.
        for script_name, extra_args in (
            ("check-idle-containers.sh", ["--name-filter", "ds01-e2e-"]),
            ("cleanup-stale-containers.sh", ["--name-filter", "ds01-e2e-"]),
            ("cleanup-stale-gpu-allocations.sh", []),
        ):
            try:
                out = run_lifecycle_script(script_name, *extra_args, timeout=120)
                results["script_outputs"].append({
                    "script": script_name,
                    "iteration": results["loop_iterations"],
                    "stdout": out.stdout,
                    "stderr": out.stderr,
                    "returncode": out.returncode,
                })
            except Exception as e:
                results["script_outputs"].append({
                    "script": script_name,
                    "iteration": results["loop_iterations"],
                    "error": str(e),
                })

        # Check if the gpu_idle container has been stopped/removed
        # (primary signal to end early)
        if not container_exists(CONTAINERS["gpu_idle"]):
            break

        # Also break if gpu_idle is stopped (even if not yet removed)
        if not container_running(CONTAINERS["gpu_idle"]):
            # Run cleanup once more to handle removal
            try:
                run_lifecycle_script("cleanup-stale-containers.sh", "--name-filter", "ds01-e2e-", timeout=120)
            except Exception:
                pass
            break

        time.sleep(LOOP_INTERVAL_SECONDS)

    results["wall_time_seconds"] = time.time() - start_time

    # ── Capture final state ───────────────────────────────────────────────

    results["final_state"] = {}
    for key, name in CONTAINERS.items():
        results["final_state"][key] = {
            "exists": container_exists(name),
            "running": container_running(name) if container_exists(name) else False,
        }

    yield results

    # ── Teardown: force-remove all test containers ────────────────────────
    _force_cleanup_test_containers()


# =============================================================================
# Test functions
# =============================================================================


@pytest.mark.requires_root
@pytest.mark.requires_gpu
@pytest.mark.requires_docker
def test_gpu_idle_container_stopped(lifecycle_scenario):
    """GPU idle container should be stopped and removed by idle detection."""
    state = lifecycle_scenario["final_state"]["gpu_idle"]
    assert not state["running"], "GPU idle container should not still be running"


@pytest.mark.requires_root
@pytest.mark.requires_gpu
@pytest.mark.requires_docker
def test_devcontainer_exempt_from_idle(lifecycle_scenario):
    """Devcontainer should survive the full test (exempt from idle timeout)."""
    state = lifecycle_scenario["final_state"]["devcontainer"]
    assert state["running"], "Devcontainer should still be running (idle-exempt)"


@pytest.mark.requires_root
@pytest.mark.requires_gpu
@pytest.mark.requires_docker
def test_keepalive_prevents_stop(lifecycle_scenario):
    """Container with .keep-alive file should survive idle detection."""
    state = lifecycle_scenario["final_state"]["keepalive"]
    assert state["running"], "Keep-alive container should still be running"


@pytest.mark.requires_root
@pytest.mark.requires_gpu
@pytest.mark.requires_docker
def test_created_state_cleanup(lifecycle_scenario):
    """Created-never-started container should be removed."""
    state = lifecycle_scenario["final_state"]["created"]
    assert not state["exists"], "Created-never-started container should be removed"


@pytest.mark.requires_root
@pytest.mark.requires_gpu
@pytest.mark.requires_docker
def test_unlabelled_stopped_cleanup(lifecycle_scenario):
    """Unlabelled stopped container should be removed by stale cleanup."""
    state = lifecycle_scenario["final_state"]["unlabelled"]
    assert not state["exists"], "Unlabelled stopped container should be removed"


@pytest.mark.requires_root
@pytest.mark.requires_gpu
@pytest.mark.requires_docker
def test_wall_notifications_sent(lifecycle_scenario):
    """Lifecycle scripts should use wall for notifications."""
    all_output = "\n".join(
        entry.get("stdout", "") + entry.get("stderr", "")
        for entry in lifecycle_scenario["script_outputs"]
    )
    # check-idle-containers.sh logs "Warning sent to" when wall is used
    # OR the container was stopped (which also sends wall)
    has_warning = "Warning sent to" in all_output or "CONTAINER AUTO-STOPPED" in all_output
    has_stop = "Stopped idle container" in all_output or "Removed" in all_output
    assert has_warning or has_stop, (
        "Expected wall notification evidence in script output"
    )


@pytest.mark.requires_root
@pytest.mark.requires_gpu
@pytest.mark.requires_docker
def test_sigterm_grace_respected(lifecycle_scenario):
    """If the idle container was stopped, it should have received SIGTERM (exit 0, not 137)."""
    # The container traps SIGTERM and exits 0. If killed (SIGKILL), exit code is 137.
    # If already removed, we check script output for evidence of graceful stop.
    if lifecycle_scenario["final_state"]["gpu_idle"]["exists"]:
        result = real_docker(
            "inspect", "-f", "{{.State.ExitCode}}", CONTAINERS["gpu_idle"]
        )
        if result.returncode == 0:
            exit_code = int(result.stdout.strip())
            assert exit_code == 0, (
                f"Container exit code {exit_code} suggests SIGKILL (137) or error, "
                "expected 0 from SIGTERM trap"
            )
    else:
        # Container already removed — check logs for graceful stop evidence
        all_output = "\n".join(
            entry.get("stdout", "") for entry in lifecycle_scenario["script_outputs"]
        )
        assert "Stopped idle container" in all_output or "Removed idle container" in all_output, (
            "Expected evidence of graceful stop in script output"
        )


# =============================================================================
# Static / config tests (don't need the lifecycle_scenario fixture)
# =============================================================================


def test_cron_schedule_no_collisions():
    """Deployed cron should have unique minute values for lifecycle jobs."""
    cron_file = INFRA_ROOT / "config" / "deploy" / "cron.d" / "ds01-maintenance"
    assert cron_file.exists(), f"Cron file not found: {cron_file}"

    content = cron_file.read_text()

    # Extract minute fields from lifecycle section
    # Lines look like: "5 * * * * root /opt/..."
    lifecycle_scripts = [
        "cleanup-stale-gpu-allocations",
        "check-idle-containers",
        "enforce-max-runtime",
        "cleanup-stale-containers",
    ]

    minutes = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("SHELL") or line.startswith("PATH") or line.startswith("INFRA"):
            continue
        if any(script in line for script in lifecycle_scripts):
            minute_field = line.split()[0]
            minutes.append(minute_field)

    assert len(minutes) == len(lifecycle_scripts), (
        f"Expected {len(lifecycle_scripts)} lifecycle cron entries, found {len(minutes)}"
    )
    assert len(set(minutes)) == len(minutes), (
        f"Lifecycle cron jobs have duplicate minute values: {minutes}"
    )


def test_cron_deployed_matches_repo():
    """Deployed /etc/cron.d/ds01-maintenance should match the repo version."""
    repo_cron = INFRA_ROOT / "config" / "deploy" / "cron.d" / "ds01-maintenance"
    deployed_cron = Path("/etc/cron.d/ds01-maintenance")

    if not deployed_cron.exists():
        pytest.skip("Cron file not deployed to /etc/cron.d/")

    repo_content = repo_cron.read_text()
    deployed_content = deployed_cron.read_text()
    assert repo_content == deployed_content, (
        "Deployed cron file differs from repo. Run: sudo deploy"
    )


@pytest.mark.requires_root
@pytest.mark.requires_gpu
def test_gpu_health_check_mode():
    """cleanup-stale-gpu-allocations.sh --health-check should produce output."""
    result = run_lifecycle_script(
        "cleanup-stale-gpu-allocations.sh", "--health-check", timeout=60
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0 or "health check" in combined.lower(), (
        f"--health-check failed with rc={result.returncode}: {combined[:500]}"
    )


def test_config_has_phase5_policies():
    """resource-limits.yaml should contain all Phase 5 policy keys."""
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    policies = config.get("policies", {})
    required_keys = [
        "grace_period",
        "keepalive_max_duration",
        "sigterm_grace_seconds",
        "gpu_hold_after_manual_stop",
        "created_container_timeout",
        "gpu_idle_threshold",
        "high_demand_threshold",
        "high_demand_idle_reduction",
    ]

    missing = [k for k in required_keys if k not in policies]
    assert not missing, f"Missing Phase 5 policy keys in resource-limits.yaml: {missing}"


def test_max_runtime_uses_targeted_notifications():
    """enforce-max-runtime.sh should use targeted user notifications, not broadcast or file-based."""
    script = INFRA_ROOT / "scripts" / "maintenance" / "enforce-max-runtime.sh"
    content = script.read_text()

    assert "notify_user" in content, "enforce-max-runtime.sh should use notify_user for targeted notifications"
    # Check it doesn't use broadcast wall or file-based notification
    assert "| wall" not in content, "enforce-max-runtime.sh should not broadcast via wall"
    assert "notify-send" not in content, (
        "enforce-max-runtime.sh should not use notify-send"
    )


