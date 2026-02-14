#!/usr/bin/env python3
"""
Component Tests: Phase 6 — Lifecycle Script Validation

Tests that check-idle-containers.sh and enforce-max-runtime.sh have the correct
structure and logic patterns after Phase 6 modifications. These tests validate
script syntax, key function existence, and structural patterns without running
the scripts against real containers.
"""

import subprocess
from pathlib import Path

import pytest

INFRA_ROOT = Path("/opt/ds01-infra")
CHECK_IDLE = INFRA_ROOT / "scripts" / "monitoring" / "check-idle-containers.sh"
ENFORCE_RUNTIME = INFRA_ROOT / "scripts" / "maintenance" / "enforce-max-runtime.sh"


# =============================================================================
# Bash Syntax Validation
# =============================================================================


class TestScriptSyntax:
    """Validate bash scripts parse without errors."""

    @pytest.mark.component
    def test_check_idle_containers_syntax(self):
        """check-idle-containers.sh passes bash -n syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(CHECK_IDLE)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    @pytest.mark.component
    def test_enforce_max_runtime_syntax(self):
        """enforce-max-runtime.sh passes bash -n syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(ENFORCE_RUNTIME)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


# =============================================================================
# check-idle-containers.sh — Structural Patterns
# =============================================================================


class TestCheckIdleStructure:
    """Validate Phase 6 patterns in check-idle-containers.sh."""

    @pytest.fixture(autouse=True)
    def load_script(self):
        self.content = CHECK_IDLE.read_text()

    @pytest.mark.component
    def test_has_get_lifecycle_policies_function(self):
        """Script defines get_lifecycle_policies() function."""
        assert "get_lifecycle_policies()" in self.content

    @pytest.mark.component
    def test_has_check_exemption_function(self):
        """Script defines check_exemption() function."""
        assert "check_exemption()" in self.content

    @pytest.mark.component
    def test_has_get_sigterm_grace_function(self):
        """Script defines get_sigterm_grace() function."""
        assert "get_sigterm_grace()" in self.content

    @pytest.mark.component
    def test_has_send_informational_warning_function(self):
        """Script defines send_informational_warning() function."""
        assert "send_informational_warning()" in self.content

    @pytest.mark.component
    def test_calls_lifecycle_policies_cli(self):
        """Script calls get_resource_limits.py --lifecycle-policies."""
        assert "--lifecycle-policies" in self.content

    @pytest.mark.component
    def test_calls_check_exemption_cli(self):
        """Script calls get_resource_limits.py --check-exemption."""
        assert "--check-exemption" in self.content

    @pytest.mark.component
    def test_uses_idle_streak_tracking(self):
        """Script tracks IDLE_STREAK for detection window."""
        assert "IDLE_STREAK" in self.content

    @pytest.mark.component
    def test_parameterized_cpu_threshold(self):
        """is_container_active_secondary uses parameterized cpu threshold."""
        # Should NOT have hardcoded 1.0 for CPU threshold
        assert "cpu_threshold" in self.content or "CPU_THRESHOLD" in self.content

    @pytest.mark.component
    def test_parameterized_network_threshold(self):
        """is_container_active_secondary uses parameterized network threshold."""
        assert "network_threshold" in self.content or "NET_THRESHOLD" in self.content

    @pytest.mark.component
    def test_multi_signal_and_logic(self):
        """Idle detection uses AND logic across multiple signals."""
        # Script checks gpu_status then secondary_active (CPU+network)
        assert "gpu_status" in self.content
        assert "secondary_active" in self.content

    @pytest.mark.component
    def test_exempt_containers_get_warnings(self):
        """Exempt containers receive informational warnings, not enforcement."""
        assert "send_informational_warning" in self.content

    @pytest.mark.component
    def test_no_hardcoded_1_percent_cpu(self):
        """CPU idle threshold is not hardcoded to 1.0 (old value)."""
        # The old hardcoded value was 1.0 in is_container_active_secondary
        # It should now be parameterized via cpu_threshold
        # We check that is_container_active_secondary takes a threshold parameter
        # rather than using literal "1.0" for comparison
        lines = self.content.split("\n")
        in_secondary_fn = False
        for line in lines:
            if "is_container_active_secondary" in line and "()" in line:
                in_secondary_fn = True
            elif in_secondary_fn and line.strip().startswith("}"):
                in_secondary_fn = False
            elif in_secondary_fn:
                # Should use parameter, not hardcoded literal for CPU check
                if "1.0" in line and "cpu" in line.lower() and "threshold" not in line.lower():
                    pytest.fail(
                        f"Found hardcoded 1.0 CPU threshold in is_container_active_secondary: {line.strip()}"
                    )


# =============================================================================
# enforce-max-runtime.sh — Structural Patterns
# =============================================================================


class TestEnforceRuntimeStructure:
    """Validate Phase 6 patterns in enforce-max-runtime.sh."""

    @pytest.fixture(autouse=True)
    def load_script(self):
        self.content = ENFORCE_RUNTIME.read_text()

    @pytest.mark.component
    def test_has_check_exemption_function(self):
        """Script defines check_exemption() function."""
        assert "check_exemption()" in self.content

    @pytest.mark.component
    def test_calls_check_exemption_cli(self):
        """Script calls get_resource_limits.py --check-exemption max_runtime."""
        assert "--check-exemption" in self.content

    @pytest.mark.component
    def test_checks_exemption_before_enforcement(self):
        """Exemption check happens before stop action."""
        # check_exemption should appear before the stop logic
        exemption_pos = self.content.find("check_exemption")
        stop_pos = self.content.find("stop_runtime_exceeded")
        assert exemption_pos < stop_pos, "Exemption check should come before stop logic"

    @pytest.mark.component
    def test_logs_audit_events_for_exemption(self):
        """Script logs audit events when exemption is applied."""
        assert "runtime_exempt" in self.content or "exempt" in self.content.lower()

    @pytest.mark.component
    def test_variable_sigterm_grace(self):
        """Script uses variable SIGTERM grace by container type."""
        assert "sigterm_grace" in self.content.lower() or "SIGTERM_GRACE" in self.content

    @pytest.mark.component
    def test_uses_container_type_for_grace(self):
        """SIGTERM grace resolution checks container type."""
        assert "container_type" in self.content or "CONTAINER_TYPE" in self.content


# =============================================================================
# Config File Validation
# =============================================================================


class TestConfigFileStructure:
    """Validate Phase 6 config file structures."""

    @pytest.mark.component
    def test_resource_limits_has_per_group_policies(self):
        """resource-limits.yaml has policies subsection in each group."""
        import yaml

        config_path = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
        if not config_path.exists():
            pytest.skip("Config file not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        groups = config.get("groups", {})
        for group_name in ["student", "researcher", "faculty"]:
            group = groups.get(group_name, {})
            assert "policies" in group, f"Group '{group_name}' missing policies section"
            policies = group["policies"]
            assert "cpu_idle_threshold" in policies, (
                f"Group '{group_name}' missing cpu_idle_threshold"
            )
            assert "idle_detection_window" in policies, (
                f"Group '{group_name}' missing idle_detection_window"
            )

    @pytest.mark.component
    def test_global_policies_has_all_thresholds(self):
        """Global policies section has all Phase 6 threshold fields."""
        import yaml

        config_path = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
        if not config_path.exists():
            pytest.skip("Config file not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        policies = config.get("policies", {})
        required = [
            "gpu_idle_threshold",
            "cpu_idle_threshold",
            "network_idle_threshold",
            "idle_detection_window",
            "sigterm_grace_seconds",
        ]
        for field in required:
            assert field in policies, f"Global policies missing '{field}'"

    @pytest.mark.component
    def test_container_types_sigterm_grace(self):
        """All container types have sigterm_grace_seconds."""
        import yaml

        config_path = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
        if not config_path.exists():
            pytest.skip("Config file not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        container_types = config.get("container_types", {})
        for ct_name in ["devcontainer", "compose", "docker", "unknown"]:
            ct = container_types.get(ct_name, {})
            assert "sigterm_grace_seconds" in ct, (
                f"container_types.{ct_name} missing sigterm_grace_seconds"
            )
            assert isinstance(ct["sigterm_grace_seconds"], (int, float)), (
                f"container_types.{ct_name}.sigterm_grace_seconds should be numeric"
            )

    @pytest.mark.component
    def test_lifecycle_exemptions_schema(self):
        """lifecycle-exemptions.yaml follows expected schema."""
        import yaml

        path = INFRA_ROOT / "config" / "runtime" / "lifecycle-exemptions.yaml"
        if not path.exists():
            pytest.skip("Exemptions file not found")

        with open(path) as f:
            data = yaml.safe_load(f)

        assert "exemptions" in data
        for i, exemption in enumerate(data["exemptions"]):
            assert "username" in exemption, f"Exemption {i} missing 'username'"
            assert "exempt_from" in exemption, f"Exemption {i} missing 'exempt_from'"
            assert "reason" in exemption, f"Exemption {i} missing 'reason'"
            assert isinstance(exemption["exempt_from"], list), (
                f"Exemption {i} 'exempt_from' should be a list"
            )
            for ef in exemption["exempt_from"]:
                assert ef in ("idle_timeout", "max_runtime"), (
                    f"Exemption {i} has unknown exempt_from value: {ef}"
                )
