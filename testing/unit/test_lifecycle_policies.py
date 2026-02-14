#!/usr/bin/env python3
"""
Unit Tests: Phase 6 - Lifecycle Enhancements

Tests for:
- get_lifecycle_policies() — per-group policy inheritance
- check_exemption() — time-bounded exemption checking
- CLI flags: --lifecycle-policies, --check-exemption
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, "/opt/ds01-infra/scripts/docker")

INFRA_ROOT = Path("/opt/ds01-infra")
GET_RESOURCE_LIMITS = INFRA_ROOT / "scripts" / "docker" / "get_resource_limits.py"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def lifecycle_config(temp_dir):
    """Config with per-group lifecycle policies."""
    config = {
        "defaults": {
            "max_mig_instances": 1,
            "max_cpus": 8,
            "memory": "32g",
            "priority": 50,
            "idle_timeout": "48h",
            "max_runtime": "168h",
        },
        "default_group": "student",
        "groups": {
            "student": {
                "members": ["alice", "bob"],
                "policies": {
                    "gpu_idle_threshold": 5,
                    "cpu_idle_threshold": 2.0,
                    "network_idle_threshold": 1048576,
                    "idle_detection_window": 3,
                },
            },
            "researcher": {
                "members": ["carol"],
                "max_mig_instances": 2,
                "policies": {
                    "gpu_idle_threshold": 5,
                    "cpu_idle_threshold": 3.0,
                    "network_idle_threshold": 1048576,
                    "idle_detection_window": 4,
                },
            },
            "faculty": {
                "members": ["dave"],
                "policies": {
                    "cpu_idle_threshold": 3.0,
                    "idle_detection_window": 4,
                },
            },
            "admin": {
                "members": ["root_user"],
                # No policies section
            },
        },
        "user_overrides": {
            "special": {
                "max_mig_instances": 4,
                "policies": {
                    "cpu_idle_threshold": 5.0,
                    "idle_detection_window": 6,
                },
            }
        },
        "policies": {
            "gpu_idle_threshold": 5,
            "cpu_idle_threshold": 2.0,
            "network_idle_threshold": 1048576,
            "idle_detection_window": 3,
            "sigterm_grace_seconds": 60,
            "high_demand_threshold": 0.8,
        },
        "container_types": {
            "devcontainer": {"sigterm_grace_seconds": 30},
            "compose": {"sigterm_grace_seconds": 45},
            "docker": {"sigterm_grace_seconds": 60},
            "unknown": {"sigterm_grace_seconds": 30},
        },
    }

    config_file = temp_dir / "resource-limits.yaml"
    with open(config_file, "w") as f:
        yaml.safe_dump(config, f)

    return config_file


@pytest.fixture
def parser(lifecycle_config):
    """Create ResourceLimitParser with lifecycle config."""
    from get_resource_limits import ResourceLimitParser

    return ResourceLimitParser(config_path=str(lifecycle_config))


@pytest.fixture
def exemptions_file(temp_dir):
    """Create a lifecycle-exemptions.yaml with test exemptions."""
    future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    past = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    exemptions = {
        "exemptions": [
            {
                "username": "permanent_user",
                "category": "waiver",
                "exempt_from": ["idle_timeout", "max_runtime"],
                "reason": "Permanent research workflow",
                "approved_by": "admin",
                "approved_on": "2026-01-01",
                "expires_on": None,
            },
            {
                "username": "temp_user",
                "category": "research_grant",
                "exempt_from": ["idle_timeout"],
                "reason": "PhD thesis deadline",
                "approved_by": "faculty",
                "approved_on": "2026-01-01",
                "expires_on": future,
            },
            {
                "username": "expired_user",
                "category": "research_grant",
                "exempt_from": ["idle_timeout", "max_runtime"],
                "reason": "Old grant",
                "approved_by": "faculty",
                "approved_on": "2025-01-01",
                "expires_on": past,
            },
            {
                "username": "idle_only_user",
                "category": "waiver",
                "exempt_from": ["idle_timeout"],
                "reason": "Idle only exemption",
                "approved_by": "admin",
                "approved_on": "2026-01-01",
                "expires_on": None,
            },
        ]
    }

    exemption_file = temp_dir / "lifecycle-exemptions.yaml"
    with open(exemption_file, "w") as f:
        yaml.safe_dump(exemptions, f)

    return exemption_file


@pytest.fixture
def parser_with_exemptions(lifecycle_config, exemptions_file):
    """Parser whose config_dir contains exemptions file."""
    from get_resource_limits import ResourceLimitParser

    return ResourceLimitParser(config_path=str(lifecycle_config))


# =============================================================================
# get_lifecycle_policies() — Inheritance Tests
# =============================================================================


class TestGetLifecyclePolicies:
    """Tests for per-group lifecycle policy resolution."""

    @pytest.mark.unit
    def test_student_gets_student_policies(self, parser):
        """Student group member gets student-tier policies."""
        policies = parser.get_lifecycle_policies("alice")
        assert policies["cpu_idle_threshold"] == 2.0
        assert policies["idle_detection_window"] == 3
        assert policies["gpu_idle_threshold"] == 5
        assert policies["network_idle_threshold"] == 1048576

    @pytest.mark.unit
    def test_researcher_gets_researcher_policies(self, parser):
        """Researcher group member gets researcher-tier policies."""
        policies = parser.get_lifecycle_policies("carol")
        assert policies["cpu_idle_threshold"] == 3.0
        assert policies["idle_detection_window"] == 4

    @pytest.mark.unit
    def test_faculty_partial_policies_inherit_global(self, parser):
        """Faculty with partial policies inherits unset values from global."""
        policies = parser.get_lifecycle_policies("dave")
        # Explicitly set in faculty group
        assert policies["cpu_idle_threshold"] == 3.0
        assert policies["idle_detection_window"] == 4
        # Inherited from global policies
        assert policies["gpu_idle_threshold"] == 5
        assert policies["network_idle_threshold"] == 1048576

    @pytest.mark.unit
    def test_admin_no_policies_gets_global(self, parser):
        """Admin group with no policies section gets global defaults."""
        policies = parser.get_lifecycle_policies("root_user")
        assert policies["gpu_idle_threshold"] == 5
        assert policies["cpu_idle_threshold"] == 2.0
        assert policies["idle_detection_window"] == 3

    @pytest.mark.unit
    def test_unknown_user_gets_default_group_or_global(self, parser):
        """Unknown user resolves to default_group policies."""
        policies = parser.get_lifecycle_policies("unknown_person")
        # default_group is 'student', which has policies
        assert policies["cpu_idle_threshold"] == 2.0
        assert policies["idle_detection_window"] == 3

    @pytest.mark.unit
    def test_user_override_takes_precedence(self, parser):
        """User override policies override group and global."""
        policies = parser.get_lifecycle_policies("special")
        assert policies["cpu_idle_threshold"] == 5.0
        assert policies["idle_detection_window"] == 6
        # Non-overridden values come from global
        assert policies["gpu_idle_threshold"] == 5

    @pytest.mark.unit
    def test_returns_all_required_keys(self, parser):
        """Returned dict contains all required policy keys."""
        policies = parser.get_lifecycle_policies("alice")
        required = {
            "gpu_idle_threshold",
            "cpu_idle_threshold",
            "network_idle_threshold",
            "idle_detection_window",
            "sigterm_grace_seconds",
        }
        assert required.issubset(policies.keys())

    @pytest.mark.unit
    def test_sigterm_grace_from_global(self, parser):
        """sigterm_grace_seconds inherited from global policies."""
        policies = parser.get_lifecycle_policies("alice")
        assert policies["sigterm_grace_seconds"] == 60

    @pytest.mark.unit
    def test_empty_config_raises(self, temp_dir):
        """Empty config raises during init or get_lifecycle_policies."""
        from get_resource_limits import ResourceLimitParser

        empty_config = temp_dir / "empty.yaml"
        empty_config.write_text("")

        with pytest.raises((ValueError, TypeError, AttributeError)):
            p = ResourceLimitParser(str(empty_config))
            p.get_lifecycle_policies("anyone")

    @pytest.mark.unit
    def test_no_policies_section_uses_hardcoded_defaults(self, temp_dir):
        """Config without any policies section uses hardcoded defaults."""
        config = {
            "defaults": {"max_mig_instances": 1, "max_cpus": 8, "memory": "32g"},
            "groups": {},
        }
        config_file = temp_dir / "no-policies.yaml"
        with open(config_file, "w") as f:
            yaml.safe_dump(config, f)

        from get_resource_limits import ResourceLimitParser

        p = ResourceLimitParser(str(config_file))
        policies = p.get_lifecycle_policies("anyone")

        # Hardcoded defaults
        assert policies["gpu_idle_threshold"] == 5
        assert policies["cpu_idle_threshold"] == 2.0
        assert policies["network_idle_threshold"] == 1048576
        assert policies["idle_detection_window"] == 3
        assert policies["sigterm_grace_seconds"] == 60


# =============================================================================
# check_exemption() — Exemption Resolution Tests
# =============================================================================


class TestCheckExemption:
    """Tests for lifecycle exemption checking."""

    @pytest.mark.unit
    def test_permanent_exemption_idle(self, parser_with_exemptions):
        """Permanent exemption for idle_timeout returns exempt."""
        exempt, reason = parser_with_exemptions.check_exemption(
            "permanent_user", "idle_timeout"
        )
        assert exempt is True
        assert "Permanent exemption" in reason

    @pytest.mark.unit
    def test_permanent_exemption_runtime(self, parser_with_exemptions):
        """Permanent exemption for max_runtime returns exempt."""
        exempt, reason = parser_with_exemptions.check_exemption(
            "permanent_user", "max_runtime"
        )
        assert exempt is True
        assert "Permanent exemption" in reason

    @pytest.mark.unit
    def test_temporary_exemption_active(self, parser_with_exemptions):
        """Active (non-expired) temporary exemption returns exempt."""
        exempt, reason = parser_with_exemptions.check_exemption(
            "temp_user", "idle_timeout"
        )
        assert exempt is True
        assert "Temporary exemption" in reason

    @pytest.mark.unit
    def test_temporary_exemption_wrong_type(self, parser_with_exemptions):
        """Temporary exemption for different enforcement type returns not exempt."""
        exempt, reason = parser_with_exemptions.check_exemption(
            "temp_user", "max_runtime"
        )
        assert exempt is False
        assert reason is None

    @pytest.mark.unit
    def test_expired_exemption(self, parser_with_exemptions):
        """Expired exemption returns not exempt."""
        exempt, reason = parser_with_exemptions.check_exemption(
            "expired_user", "idle_timeout"
        )
        assert exempt is False
        assert reason is None

    @pytest.mark.unit
    def test_no_exemption(self, parser_with_exemptions):
        """User with no exemption returns not exempt."""
        exempt, reason = parser_with_exemptions.check_exemption(
            "nonexistent_user", "idle_timeout"
        )
        assert exempt is False
        assert reason is None

    @pytest.mark.unit
    def test_partial_exemption_idle_only(self, parser_with_exemptions):
        """User exempt only from idle_timeout, not max_runtime."""
        # idle_only_user is exempt from idle_timeout only
        exempt, reason = parser_with_exemptions.check_exemption(
            "idle_only_user", "idle_timeout"
        )
        assert exempt is True

        exempt, reason = parser_with_exemptions.check_exemption(
            "idle_only_user", "max_runtime"
        )
        assert exempt is False

    @pytest.mark.unit
    def test_missing_exemption_file(self, parser):
        """Missing exemptions file returns not exempt (fail-open)."""
        # parser fixture's config_dir doesn't have lifecycle-exemptions.yaml
        exempt, reason = parser.check_exemption("anyone", "idle_timeout")
        assert exempt is False
        assert reason is None

    @pytest.mark.unit
    def test_empty_exemption_file(self, temp_dir, lifecycle_config):
        """Empty exemptions file returns not exempt."""
        exemption_file = temp_dir / "lifecycle-exemptions.yaml"
        exemption_file.write_text("")

        from get_resource_limits import ResourceLimitParser

        p = ResourceLimitParser(str(lifecycle_config))
        exempt, reason = p.check_exemption("anyone", "idle_timeout")
        assert exempt is False

    @pytest.mark.unit
    def test_malformed_exemption_file(self, temp_dir, lifecycle_config):
        """Malformed YAML exemptions file returns not exempt (fail-open)."""
        exemption_file = temp_dir / "lifecycle-exemptions.yaml"
        exemption_file.write_text("this: is: not: valid: yaml: [")

        from get_resource_limits import ResourceLimitParser

        p = ResourceLimitParser(str(lifecycle_config))
        exempt, reason = p.check_exemption("anyone", "idle_timeout")
        assert exempt is False

    @pytest.mark.unit
    def test_z_suffix_iso_date(self, temp_dir, lifecycle_config):
        """Handles ISO 8601 dates with Z suffix correctly."""
        future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        exemptions = {
            "exemptions": [
                {
                    "username": "z_user",
                    "exempt_from": ["idle_timeout"],
                    "reason": "Z suffix test",
                    "expires_on": future,
                }
            ]
        }
        exemption_file = temp_dir / "lifecycle-exemptions.yaml"
        with open(exemption_file, "w") as f:
            yaml.safe_dump(exemptions, f)

        from get_resource_limits import ResourceLimitParser

        p = ResourceLimitParser(str(lifecycle_config))
        exempt, reason = p.check_exemption("z_user", "idle_timeout")
        assert exempt is True

    @pytest.mark.unit
    def test_invalid_date_format_skipped(self, temp_dir, lifecycle_config):
        """Invalid date format in expires_on is skipped gracefully."""
        exemptions = {
            "exemptions": [
                {
                    "username": "bad_date_user",
                    "exempt_from": ["idle_timeout"],
                    "reason": "Bad date",
                    "expires_on": "not-a-date",
                }
            ]
        }
        exemption_file = temp_dir / "lifecycle-exemptions.yaml"
        with open(exemption_file, "w") as f:
            yaml.safe_dump(exemptions, f)

        from get_resource_limits import ResourceLimitParser

        p = ResourceLimitParser(str(lifecycle_config))
        exempt, reason = p.check_exemption("bad_date_user", "idle_timeout")
        assert exempt is False

    @pytest.mark.unit
    def test_exemption_without_exempt_from_field(self, temp_dir, lifecycle_config):
        """Exemption record without exempt_from field doesn't match."""
        exemptions = {
            "exemptions": [
                {
                    "username": "no_field_user",
                    "reason": "Missing exempt_from",
                    "expires_on": None,
                }
            ]
        }
        exemption_file = temp_dir / "lifecycle-exemptions.yaml"
        with open(exemption_file, "w") as f:
            yaml.safe_dump(exemptions, f)

        from get_resource_limits import ResourceLimitParser

        p = ResourceLimitParser(str(lifecycle_config))
        exempt, reason = p.check_exemption("no_field_user", "idle_timeout")
        assert exempt is False


# =============================================================================
# CLI Flag Tests
# =============================================================================


class TestCLIFlags:
    """Tests for CLI --lifecycle-policies and --check-exemption flags."""

    @pytest.mark.unit
    def test_lifecycle_policies_flag_outputs_json(self):
        """--lifecycle-policies outputs valid JSON."""
        result = subprocess.run(
            ["python3", str(GET_RESOURCE_LIMITS), "datasciencelab", "--lifecycle-policies"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert "gpu_idle_threshold" in data
        assert "cpu_idle_threshold" in data
        assert "network_idle_threshold" in data
        assert "idle_detection_window" in data
        assert "sigterm_grace_seconds" in data

    @pytest.mark.unit
    def test_check_exemption_flag_not_exempt(self):
        """--check-exemption for non-exempt user outputs not_exempt."""
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
        assert "not_exempt" in result.stdout.strip()

    @pytest.mark.unit
    def test_check_exemption_flag_exempt_user(self):
        """--check-exemption for exempt user outputs exempt: reason."""
        result = subprocess.run(
            [
                "python3",
                str(GET_RESOURCE_LIMITS),
                "204214@hertie-school.lan",
                "--check-exemption",
                "idle_timeout",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip().startswith("exempt:")

    @pytest.mark.unit
    def test_check_exemption_missing_type_errors(self):
        """--check-exemption without type argument exits with error."""
        result = subprocess.run(
            [
                "python3",
                str(GET_RESOURCE_LIMITS),
                "datasciencelab",
                "--check-exemption",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0


# =============================================================================
# Real Config Integration Tests
# =============================================================================


class TestRealConfigLifecyclePolicies:
    """Integration tests using the real resource-limits.yaml."""

    @pytest.fixture
    def real_parser(self):
        """Parser using the real production config."""
        config_path = INFRA_ROOT / "config" / "runtime" / "resource-limits.yaml"
        if not config_path.exists():
            pytest.skip("Real config not found")

        from get_resource_limits import ResourceLimitParser

        return ResourceLimitParser(str(config_path))

    @pytest.mark.unit
    def test_real_config_has_global_policies(self, real_parser):
        """Real config has global policies section with all required fields."""
        policies = real_parser.config.get("policies", {})
        assert "cpu_idle_threshold" in policies
        assert "network_idle_threshold" in policies
        assert "idle_detection_window" in policies
        assert "sigterm_grace_seconds" in policies

    @pytest.mark.unit
    def test_real_config_student_has_policies(self, real_parser):
        """Real config student group has per-group policies."""
        student = real_parser.config.get("groups", {}).get("student", {})
        assert "policies" in student
        assert "cpu_idle_threshold" in student["policies"]

    @pytest.mark.unit
    def test_real_config_researcher_has_policies(self, real_parser):
        """Real config researcher group has per-group policies."""
        researcher = real_parser.config.get("groups", {}).get("researcher", {})
        assert "policies" in researcher
        assert "idle_detection_window" in researcher["policies"]

    @pytest.mark.unit
    def test_real_config_container_types_have_sigterm(self, real_parser):
        """All container types in real config have sigterm_grace_seconds."""
        container_types = real_parser.config.get("container_types", {})
        for ct_name, ct_config in container_types.items():
            assert "sigterm_grace_seconds" in ct_config, (
                f"container_types.{ct_name} missing sigterm_grace_seconds"
            )

    @pytest.mark.unit
    def test_real_exemptions_file_valid_yaml(self):
        """Real lifecycle-exemptions.yaml is valid YAML."""
        path = INFRA_ROOT / "config" / "runtime" / "lifecycle-exemptions.yaml"
        if not path.exists():
            pytest.skip("Exemptions file not found")

        with open(path) as f:
            data = yaml.safe_load(f)

        assert "exemptions" in data
        assert isinstance(data["exemptions"], list)

    @pytest.mark.unit
    def test_real_exemptions_have_required_fields(self):
        """Real exemptions have required fields."""
        path = INFRA_ROOT / "config" / "runtime" / "lifecycle-exemptions.yaml"
        if not path.exists():
            pytest.skip("Exemptions file not found")

        with open(path) as f:
            data = yaml.safe_load(f)

        for exemption in data["exemptions"]:
            assert "username" in exemption
            assert "exempt_from" in exemption
            assert "reason" in exemption
            assert isinstance(exemption["exempt_from"], list)
