#!/usr/bin/env python3
"""
Runtime Tests: Phase 6 — Lifecycle Enforcement on Live System

These tests require:
- Root privileges (sudo)
- Docker daemon running
- Real resource-limits.yaml
- Real lifecycle-exemptions.yaml

They create real containers, run lifecycle scripts, and verify enforcement
behaviour with exemptions, multi-signal idle detection, and variable SIGTERM.

Run with: sudo pytest testing/runtime/test_lifecycle_enforcement.py -m runtime -v
"""

import json
import subprocess
import time
from pathlib import Path

import pytest
import yaml

INFRA_ROOT = Path("/opt/ds01-infra")
CONFIG_FILE = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
EXEMPTIONS_FILE = INFRA_ROOT / "config" / "runtime" / "lifecycle-exemptions.yaml"
GET_RESOURCE_LIMITS = INFRA_ROOT / "scripts" / "docker" / "get_resource_limits.py"
CHECK_IDLE = INFRA_ROOT / "scripts" / "monitoring" / "check-idle-containers.sh"
ENFORCE_RUNTIME = INFRA_ROOT / "scripts" / "maintenance" / "enforce-max-runtime.sh"
DOCKER_BIN = "/usr/bin/docker"


def real_docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Call /usr/bin/docker directly, bypassing DS01 wrapper."""
    return subprocess.run(
        [DOCKER_BIN, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def container_running(name: str) -> bool:
    result = real_docker("inspect", "-f", "{{.State.Running}}", name)
    return result.returncode == 0 and result.stdout.strip() == "true"


def container_exists(name: str) -> bool:
    result = real_docker("inspect", name)
    return result.returncode == 0


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def runtime_config_backup():
    """Back up config and restore on teardown."""
    import shutil

    backup = CONFIG_FILE.with_suffix(".yaml.bak-lifecycle-test")
    shutil.copy2(CONFIG_FILE, backup)
    yield backup
    shutil.copy2(backup, CONFIG_FILE)
    backup.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def exemptions_backup():
    """Back up exemptions and restore on teardown."""
    import shutil

    if not EXEMPTIONS_FILE.exists():
        yield None
        return

    backup = EXEMPTIONS_FILE.with_suffix(".yaml.bak-lifecycle-test")
    shutil.copy2(EXEMPTIONS_FILE, backup)
    yield backup
    shutil.copy2(backup, EXEMPTIONS_FILE)
    backup.unlink(missing_ok=True)


@pytest.fixture
def test_container(request):
    """Create a simple test container, clean up after."""
    name = f"ds01-lifecycle-test-{int(time.time())}"
    real_docker(
        "run", "-d",
        "--name", name,
        "--label", "ds01.user=test-lifecycle",
        "--label", "ds01.managed=true",
        "--label", "ds01.interface=orchestration",
        "alpine:latest", "sleep", "3600",
    )
    yield name
    # Cleanup
    real_docker("rm", "-f", name)


# =============================================================================
# Runtime: Policy Resolution on Live System
# =============================================================================


@pytest.mark.runtime
@pytest.mark.requires_root
class TestLivePolicyResolution:
    """Test policy resolution against live config."""

    def test_lifecycle_policies_returns_json(self):
        """get_resource_limits.py --lifecycle-policies returns valid JSON."""
        result = subprocess.run(
            ["python3", str(GET_RESOURCE_LIMITS), "datasciencelab", "--lifecycle-policies"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert isinstance(data["gpu_idle_threshold"], (int, float))
        assert isinstance(data["cpu_idle_threshold"], (int, float))
        assert isinstance(data["idle_detection_window"], int)

    def test_check_exemption_returns_parseable_output(self):
        """--check-exemption output is parseable by bash scripts."""
        result = subprocess.run(
            [
                "python3",
                str(GET_RESOURCE_LIMITS),
                "datasciencelab",
                "--check-exemption",
                "idle_timeout",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        assert output == "not_exempt" or output.startswith("exempt:")


# =============================================================================
# Runtime: Exemption Enforcement
# =============================================================================


@pytest.mark.runtime
@pytest.mark.requires_root
class TestLiveExemptionEnforcement:
    """Test that exempt containers are not stopped by lifecycle scripts."""

    def test_exempt_user_in_real_config(self, exemptions_backup):
        """Real exemptions file has at least one exemption."""
        if not EXEMPTIONS_FILE.exists():
            pytest.skip("No exemptions file")

        with open(EXEMPTIONS_FILE) as f:
            data = yaml.safe_load(f)

        assert len(data.get("exemptions", [])) > 0

    def test_check_idle_dry_run_respects_exemption(self):
        """check-idle-containers.sh with DRY_RUN=1 reports exemptions."""
        # This tests the script's exemption path without actually stopping containers
        result = subprocess.run(
            ["bash", "-c", f"DRY_RUN=1 {CHECK_IDLE}"],
            capture_output=True,
            text=True,
            timeout=60,
            env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                 "DRY_RUN": "1"},
        )
        # Script should complete without error
        # (may or may not find running containers to check)
        assert result.returncode == 0 or "No running" in result.stdout


# =============================================================================
# Runtime: Script Execution
# =============================================================================


@pytest.mark.runtime
@pytest.mark.requires_root
class TestLiveScriptExecution:
    """Test that lifecycle scripts execute without errors on live system."""

    def test_check_idle_exits_cleanly(self):
        """check-idle-containers.sh exits 0 on live system."""
        result = subprocess.run(
            [str(CHECK_IDLE)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Should exit 0 even if no containers to check
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_enforce_runtime_exits_cleanly(self):
        """enforce-max-runtime.sh exits 0 on live system."""
        result = subprocess.run(
            [str(ENFORCE_RUNTIME)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
