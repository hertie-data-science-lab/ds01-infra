#!/usr/bin/env python3
"""
Integration Tests: Phase 6 — Cross-Component Lifecycle Integration

Tests that the Python config parser, YAML config files, and bash scripts
work together correctly. Validates the full resolution chain:

  resource-limits.yaml → get_resource_limits.py → bash scripts

These tests use real files but don't start containers.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

INFRA_ROOT = Path("/opt/ds01-infra")
GET_RESOURCE_LIMITS = INFRA_ROOT / "scripts" / "docker" / "get_resource_limits.py"
sys.path.insert(0, str(INFRA_ROOT / "scripts" / "docker"))


# =============================================================================
# Python → YAML Config Integration
# =============================================================================


class TestConfigResolverIntegration:
    """Test Python parser resolves real YAML config correctly."""

    @pytest.fixture
    def real_parser(self):
        config_path = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
        if not config_path.exists():
            pytest.skip("Real config not found")
        from get_resource_limits import ResourceLimitParser

        return ResourceLimitParser(str(config_path))

    @pytest.mark.integration
    def test_student_lifecycle_policies_match_config(self, real_parser):
        """Student lifecycle policies match YAML config values."""
        # Read expected values directly from YAML
        with open(real_parser.config_path) as f:
            raw = yaml.safe_load(f)

        student_policies = raw["groups"]["student"]["policies"]

        # Get resolved policies for a student (using default group)
        policies = real_parser.get_lifecycle_policies("unknown_student_user")

        # Student group is default_group, so unknown users get student policies
        assert policies["cpu_idle_threshold"] == student_policies["cpu_idle_threshold"]
        assert policies["idle_detection_window"] == student_policies["idle_detection_window"]

    @pytest.mark.integration
    def test_global_policies_set_sigterm_defaults(self, real_parser):
        """Global sigterm_grace_seconds is resolved from policies section."""
        with open(real_parser.config_path) as f:
            raw = yaml.safe_load(f)

        expected_sigterm = raw["policies"]["sigterm_grace_seconds"]
        policies = real_parser.get_lifecycle_policies("unknown_user")
        assert policies["sigterm_grace_seconds"] == expected_sigterm

    @pytest.mark.integration
    def test_researcher_policies_differ_from_student(self, real_parser):
        """Researcher group has different policies than student."""
        with open(real_parser.config_path) as f:
            raw = yaml.safe_load(f)

        # Load member files to find a real researcher
        researcher_members_file = (
            INFRA_ROOT / "config" / "runtime" / "groups" / "researcher.members"
        )
        if not researcher_members_file.exists():
            pytest.skip("No researcher.members file")

        members = [
            line.split("#")[0].strip()
            for line in researcher_members_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not members:
            pytest.skip("No researcher members")

        researcher_policies = real_parser.get_lifecycle_policies(members[0])
        student_policies = real_parser.get_lifecycle_policies("unknown_default_student")

        # Researcher should have different idle_detection_window
        researcher_yaml = raw["groups"]["researcher"]["policies"]
        assert researcher_policies["idle_detection_window"] == researcher_yaml["idle_detection_window"]

        # If student and researcher differ in config, they should differ in resolution
        student_yaml = raw["groups"]["student"]["policies"]
        if student_yaml["idle_detection_window"] != researcher_yaml["idle_detection_window"]:
            assert student_policies["idle_detection_window"] != researcher_policies["idle_detection_window"]


# =============================================================================
# CLI → Python → YAML End-to-End
# =============================================================================


class TestCLIIntegration:
    """Test CLI flags produce consistent output with Python API."""

    @pytest.mark.integration
    def test_cli_lifecycle_policies_matches_api(self):
        """CLI --lifecycle-policies output matches Python API result."""
        # CLI output
        result = subprocess.run(
            ["python3", str(GET_RESOURCE_LIMITS), "datasciencelab", "--lifecycle-policies"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        cli_data = json.loads(result.stdout.strip())

        # Python API output
        from get_resource_limits import ResourceLimitParser

        parser = ResourceLimitParser()
        api_data = parser.get_lifecycle_policies("datasciencelab")

        assert cli_data == api_data

    @pytest.mark.integration
    def test_cli_check_exemption_matches_api(self):
        """CLI --check-exemption output matches Python API result."""
        username = "204214@hertie-school.lan"

        # CLI output
        result = subprocess.run(
            [
                "python3",
                str(GET_RESOURCE_LIMITS),
                username,
                "--check-exemption",
                "idle_timeout",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        cli_output = result.stdout.strip()

        # Python API
        from get_resource_limits import ResourceLimitParser

        parser = ResourceLimitParser()
        is_exempt, reason = parser.check_exemption(username, "idle_timeout")

        if is_exempt:
            assert cli_output.startswith("exempt:")
        else:
            assert cli_output == "not_exempt"


# =============================================================================
# Bash Script → Python Script Integration
# =============================================================================


class TestBashPythonIntegration:
    """Test that bash scripts call Python correctly."""

    @pytest.mark.integration
    def test_check_idle_lifecycle_policies_call(self):
        """check-idle-containers.sh's get_lifecycle_policies function calls Python correctly."""
        # Source the relevant function and test it
        script = INFRA_ROOT / "scripts" / "monitoring" / "check-idle-containers.sh"
        content = script.read_text()

        # Verify the function calls get_resource_limits.py --lifecycle-policies
        assert "get_resource_limits.py" in content
        assert "--lifecycle-policies" in content

        # Test that the Python CLI produces valid JSON that bash can parse
        result = subprocess.run(
            ["python3", str(GET_RESOURCE_LIMITS), "datasciencelab", "--lifecycle-policies"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout.strip())

        # These are the keys the bash script extracts via jq/python
        assert "gpu_idle_threshold" in data
        assert "cpu_idle_threshold" in data
        assert "network_idle_threshold" in data
        assert "idle_detection_window" in data

    @pytest.mark.integration
    def test_enforce_runtime_exemption_call(self):
        """enforce-max-runtime.sh's check_exemption function calls Python correctly."""
        script = INFRA_ROOT / "scripts" / "maintenance" / "enforce-max-runtime.sh"
        content = script.read_text()

        # Verify it calls the right Python flag
        assert "--check-exemption" in content

        # Test that CLI output is parseable by bash (starts with "exempt:" or "not_exempt")
        result = subprocess.run(
            [
                "python3",
                str(GET_RESOURCE_LIMITS),
                "datasciencelab",
                "--check-exemption",
                "max_runtime",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        assert output == "not_exempt" or output.startswith("exempt:")


# =============================================================================
# Container Type SIGTERM Grace Integration
# =============================================================================


class TestSigtermGraceIntegration:
    """Test SIGTERM grace period resolution across components."""

    @pytest.mark.integration
    def test_container_types_sigterm_values_are_positive(self):
        """All container type SIGTERM values are positive integers."""
        config_path = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
        if not config_path.exists():
            pytest.skip("Config not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        for ct_name, ct_config in config.get("container_types", {}).items():
            grace = ct_config.get("sigterm_grace_seconds")
            assert grace is not None, f"{ct_name} missing sigterm_grace_seconds"
            assert isinstance(grace, (int, float)) and grace > 0, (
                f"{ct_name} sigterm_grace_seconds should be positive, got {grace}"
            )

    @pytest.mark.integration
    def test_sigterm_grace_hierarchy(self):
        """SIGTERM grace values follow expected hierarchy."""
        config_path = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
        if not config_path.exists():
            pytest.skip("Config not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        ct = config.get("container_types", {})
        # devcontainer should be shortest (K8s default), docker longest
        devcontainer_grace = ct.get("devcontainer", {}).get("sigterm_grace_seconds", 30)
        compose_grace = ct.get("compose", {}).get("sigterm_grace_seconds", 45)
        docker_grace = ct.get("docker", {}).get("sigterm_grace_seconds", 60)

        assert devcontainer_grace <= compose_grace <= docker_grace


# =============================================================================
# Exemption + Policy Interaction
# =============================================================================


class TestExemptionPolicyInteraction:
    """Test that exemptions and policies work together correctly."""

    @pytest.mark.integration
    def test_exempt_user_still_has_policies(self):
        """Exempt user still gets lifecycle policies (used for informational warnings)."""
        from get_resource_limits import ResourceLimitParser

        parser = ResourceLimitParser()

        # 204214 is exempt in the real config
        username = "204214@hertie-school.lan"
        is_exempt, _ = parser.check_exemption(username, "idle_timeout")

        # Regardless of exemption, policies should resolve
        policies = parser.get_lifecycle_policies(username)
        assert "gpu_idle_threshold" in policies
        assert "cpu_idle_threshold" in policies

    @pytest.mark.integration
    def test_non_exempt_user_not_exempt_all_types(self):
        """Non-exempt user is not exempt from any enforcement type."""
        from get_resource_limits import ResourceLimitParser

        parser = ResourceLimitParser()

        exempt_idle, _ = parser.check_exemption("datasciencelab", "idle_timeout")
        exempt_runtime, _ = parser.check_exemption("datasciencelab", "max_runtime")

        assert not exempt_idle
        assert not exempt_runtime
