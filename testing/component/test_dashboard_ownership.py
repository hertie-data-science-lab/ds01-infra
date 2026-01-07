#!/usr/bin/env python3
"""
Component Tests: Dashboard Ownership Integration

Tests for the dashboard's integration with the container ownership tracking file.
Focuses on the _load_ownership_file() method and extract_owner() fallback.
"""

import importlib.util
import importlib.machinery
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Module Loading
# =============================================================================


def load_dashboard_module(temp_ownership_file=None):
    """Load dashboard module (handles extensionless Python scripts)."""
    script_path = Path("/opt/ds01-infra/scripts/admin/dashboard")

    loader = importlib.machinery.SourceFileLoader("dashboard", str(script_path))
    spec = importlib.util.spec_from_loader("dashboard", loader, origin=str(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if temp_ownership_file:
        module.OWNERSHIP_FILE = temp_ownership_file

    return module


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_ownership_file(temp_dir):
    """Create temporary ownership file."""
    opa_dir = temp_dir / "opa"
    opa_dir.mkdir(parents=True)
    return opa_dir / "container-owners.json"


@pytest.fixture
def sample_ownership_data():
    """Sample container ownership data."""
    return {
        "containers": {
            "labeled-container": {
                "owner": "labeled-user",
                "owner_uid": 1001,
                "name": "labeled-container",
                "ds01_managed": True,
                "interface": "atomic",
                "detection_method": "ds01_label",
            },
            "mount-detected": {
                "owner": "mount-user",
                "owner_uid": 2002,
                "name": "mount-detected",
                "ds01_managed": False,
                "interface": "compose",
                "detection_method": "mount_path",
            },
            "devcontainer-proj": {
                "owner": "dev-user",
                "owner_uid": 3003,
                "name": "devcontainer-proj",
                "ds01_managed": False,
                "interface": "devcontainer",
                "detection_method": "devcontainer",
            },
        },
        "admins": ["admin1"],
        "service_users": ["ds01-dashboard"],
        "updated_at": "2025-01-07T12:00:00Z",
    }


# =============================================================================
# Test: Ownership File Loading
# =============================================================================


class TestOwnershipFileLoading:
    """Tests for _load_ownership_file() method."""

    @pytest.mark.component
    def test_loads_valid_ownership_file(self, temp_ownership_file, sample_ownership_data):
        """Successfully loads valid ownership JSON file."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData._load_ownership_file()

        assert "containers" in result
        assert "labeled-container" in result["containers"]
        assert result["containers"]["labeled-container"]["owner"] == "labeled-user"

    @pytest.mark.component
    def test_returns_empty_for_missing_file(self, temp_dir):
        """Returns empty structure when file doesn't exist."""
        missing_file = temp_dir / "nonexistent-ownership-file-12345.json"

        module = load_dashboard_module(missing_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData._load_ownership_file()

        assert result == {"containers": {}}

    @pytest.mark.component
    def test_returns_empty_for_corrupt_file(self, temp_ownership_file):
        """Returns empty structure for corrupt JSON file."""
        with open(temp_ownership_file, "w") as f:
            f.write("{ not valid json !!!")

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData._load_ownership_file()

        assert result == {"containers": {}}

    @pytest.mark.component
    def test_caches_ownership_data(self, temp_ownership_file, sample_ownership_data):
        """Caches ownership data to avoid repeated file reads."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        # First call
        result1 = module.DashboardData._load_ownership_file()
        cache_time = module.DashboardData._ownership_cache_time

        # Second call should use cache
        result2 = module.DashboardData._load_ownership_file()

        assert result1 == result2
        assert module.DashboardData._ownership_cache_time == cache_time
        assert module.DashboardData._ownership_cache is not None

    @pytest.mark.component
    def test_cache_expires_after_timeout(self, temp_ownership_file, sample_ownership_data):
        """Cache expires after 5 seconds."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        # First call
        module.DashboardData._load_ownership_file()

        # Simulate cache expiry
        module.DashboardData._ownership_cache_time = time.time() - 10  # 10 seconds ago

        # Update file with different data
        modified_data = {"containers": {"new-container": {"owner": "new-user"}}}
        with open(temp_ownership_file, "w") as f:
            json.dump(modified_data, f)

        # Should reload from file
        result = module.DashboardData._load_ownership_file()

        assert "new-container" in result["containers"]


# =============================================================================
# Test: Owner Extraction with Fallback
# =============================================================================


class TestExtractOwnerFallback:
    """Tests for extract_owner() ownership file fallback."""

    @pytest.mark.component
    def test_ds01_label_takes_priority(self, temp_ownership_file, sample_ownership_data):
        """ds01.user label takes priority over ownership file."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="explicit-ds01-user",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="labeled-container"
        )

        assert result == "explicit-ds01-user"

    @pytest.mark.component
    def test_aime_label_takes_priority(self, temp_ownership_file, sample_ownership_data):
        """aime.mlc.USER label takes priority over ownership file."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="aime-user",
            aime_username="",
            devcontainer_path="",
            container_name="labeled-container"
        )

        assert result == "aime-user"

    @pytest.mark.component
    def test_devcontainer_path_takes_priority(self, temp_ownership_file, sample_ownership_data):
        """devcontainer.local_folder path takes priority over ownership file."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="/home/devcontainer-user/project",
            container_name="labeled-container"
        )

        assert result == "devcontainer-user"

    @pytest.mark.component
    def test_falls_back_to_ownership_file(self, temp_ownership_file, sample_ownership_data):
        """Falls back to ownership file when no labels present."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="mount-detected"
        )

        assert result == "mount-user"

    @pytest.mark.component
    def test_returns_other_when_not_found(self, temp_ownership_file, sample_ownership_data):
        """Returns '(other)' when container not in ownership file."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="unknown-container"
        )

        assert result == "(other)"

    @pytest.mark.component
    def test_handles_empty_container_name(self, temp_ownership_file, sample_ownership_data):
        """Handles empty container name gracefully."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name=""
        )

        assert result == "(other)"


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestDashboardOwnershipEdgeCases:
    """Edge case tests for dashboard ownership integration."""

    @pytest.mark.component
    def test_handles_domain_username(self, temp_ownership_file):
        """Handles domain usernames with @ symbol."""
        data = {
            "containers": {
                "domain-container": {
                    "owner": "h.baker@hertie-school.lan",
                    "name": "domain-container",
                }
            }
        }

        with open(temp_ownership_file, "w") as f:
            json.dump(data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="domain-container"
        )

        assert result == "h.baker@hertie-school.lan"

    @pytest.mark.component
    def test_handles_unicode_in_container_name(self, temp_ownership_file):
        """Handles unicode characters in container names."""
        data = {
            "containers": {
                "projet-numero-1": {
                    "owner": "test-user",
                    "name": "projet-numero-1",
                }
            }
        }

        with open(temp_ownership_file, "w") as f:
            json.dump(data, f, ensure_ascii=False)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="projet-numero-1"
        )

        assert result == "test-user"

    @pytest.mark.component
    def test_handles_missing_owner_field(self, temp_ownership_file):
        """Handles container entry with missing owner field."""
        data = {
            "containers": {
                "incomplete-container": {
                    "name": "incomplete-container",
                    # owner field missing
                }
            }
        }

        with open(temp_ownership_file, "w") as f:
            json.dump(data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="incomplete-container"
        )

        # Should return (other) since owner is None/missing
        assert result == "(other)"

    @pytest.mark.component
    def test_handles_null_owner_value(self, temp_ownership_file):
        """Handles container entry with null owner value."""
        data = {
            "containers": {
                "null-owner-container": {
                    "owner": None,
                    "name": "null-owner-container",
                }
            }
        }

        with open(temp_ownership_file, "w") as f:
            json.dump(data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="null-owner-container"
        )

        # Should return (other) since owner is None
        assert result == "(other)"
