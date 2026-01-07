#!/usr/bin/env python3
"""
Unit Tests: Sync Container Owners

Tests for sync-container-owners.py periodic sync script that maintains
container ownership data while preserving tracker-detected owners.
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# =============================================================================
# Module Loading (handles hyphenated filenames)
# =============================================================================


def load_sync_module(temp_output_file=None, temp_lock_file=None, temp_output_dir=None):
    """
    Load sync-container-owners.py module with optional path overrides.

    Python can't import filenames with hyphens, so we use importlib.util.
    """
    script_path = Path("/opt/ds01-infra/scripts/docker/sync-container-owners.py")

    spec = importlib.util.spec_from_file_location("sync_container_owners", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Override paths after loading
    if temp_output_file:
        module.OUTPUT_FILE = temp_output_file
    if temp_lock_file:
        module.LOCK_FILE = temp_lock_file
    if temp_output_dir:
        module.OUTPUT_DIR = temp_output_dir

    return module


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_ownership_dir(temp_dir):
    """Create temporary ownership directory."""
    opa_dir = temp_dir / "opa"
    opa_dir.mkdir(parents=True)
    return opa_dir


@pytest.fixture
def temp_ownership_file(temp_ownership_dir):
    """Create temporary ownership file path."""
    return temp_ownership_dir / "container-owners.json"


@pytest.fixture
def temp_lock_file(temp_ownership_dir):
    """Create temporary lock file path."""
    return temp_ownership_dir / "container-owners.lock"


@pytest.fixture
def sync_module(temp_ownership_file, temp_lock_file, temp_ownership_dir):
    """Load sync module with temp paths."""
    return load_sync_module(temp_ownership_file, temp_lock_file, temp_ownership_dir)


@pytest.fixture
def sample_container_inspect_data():
    """Sample data from docker inspect."""
    return [
        {
            "Id": "abc123def456789abc123def456789abc123def456789abc123def456789abcd",
            "Name": "/project-a",
            "Config": {
                "Labels": {
                    "ds01.user": "testuser",
                    "ds01.managed": "true",
                }
            },
        },
        {
            "Id": "def789abc012def789abc012def789abc012def789abc012def789abc012defg",
            "Name": "/project-b",
            "Config": {
                "Labels": {
                    "aime.mlc.USER": "student1",
                }
            },
        },
    ]


@pytest.fixture
def existing_tracker_data():
    """Existing ownership data from tracker daemon."""
    return {
        "containers": {
            "ghi456jkl789": {
                "owner": "tracker-detected-user",
                "owner_uid": 2000,
                "name": "unlabeled-container",
                "ds01_managed": False,
                "interface": "docker",
                "created_at": "2025-01-01T00:00:00+00:00",
                "detection_method": "mount_path",
            },
            "unlabeled-container": {
                "owner": "tracker-detected-user",
                "owner_uid": 2000,
                "name": "unlabeled-container",
                "ds01_managed": False,
                "interface": "docker",
                "created_at": "2025-01-01T00:00:00+00:00",
                "detection_method": "mount_path",
            },
        },
        "admins": ["admin1"],
        "service_users": ["ds01-dashboard"],
        "updated_at": "2025-01-01T00:00:00+00:00",
    }


# =============================================================================
# Test: Owner Extraction from Labels
# =============================================================================


class TestGetContainerOwner:
    """Tests for get_container_owner function."""

    @pytest.mark.unit
    def test_ds01_label_priority(self, sync_module):
        """ds01.user label takes priority."""
        labels = {
            "ds01.user": "ds01user",
            "aime.mlc.USER": "aimeuser",
            "devcontainer.local_folder": "/home/devuser/project",
        }

        result = sync_module.get_container_owner(labels)
        assert result == "ds01user"

    @pytest.mark.unit
    def test_aime_label_second_priority(self, sync_module):
        """aime.mlc.USER is second priority."""
        labels = {
            "aime.mlc.USER": "aimeuser",
            "devcontainer.local_folder": "/home/devuser/project",
        }

        result = sync_module.get_container_owner(labels)
        assert result == "aimeuser"

    @pytest.mark.unit
    def test_devcontainer_path_extraction(self, sync_module):
        """Extracts user from devcontainer.local_folder path."""
        labels = {
            "devcontainer.local_folder": "/home/developer/projects/myapp",
        }

        result = sync_module.get_container_owner(labels)
        assert result == "developer"

    @pytest.mark.unit
    def test_devcontainer_non_home_path_ignored(self, sync_module):
        """Non-/home paths in devcontainer.local_folder ignored."""
        labels = {
            "devcontainer.local_folder": "/var/lib/data",
        }

        result = sync_module.get_container_owner(labels)
        assert result is None

    @pytest.mark.unit
    def test_returns_none_for_empty_labels(self, sync_module):
        """Returns None when no ownership labels present."""
        result = sync_module.get_container_owner({})
        assert result is None

    @pytest.mark.unit
    def test_handles_domain_username(self, sync_module):
        """Handles domain usernames correctly."""
        labels = {
            "ds01.user": "h.baker@hertie-school.lan",
        }

        result = sync_module.get_container_owner(labels)
        assert result == "h.baker@hertie-school.lan"


# =============================================================================
# Test: Preserving Tracker-Detected Owners
# =============================================================================


class TestPreserveTrackerOwners:
    """Tests for preserving owners detected by tracker daemon."""

    @pytest.mark.unit
    def test_preserves_tracker_owner_for_unlabeled_container(
        self, sync_module, temp_ownership_file, existing_tracker_data
    ):
        """Sync preserves tracker-detected owner when container has no labels."""
        # Write existing tracker data
        with open(temp_ownership_file, "w") as f:
            json.dump(existing_tracker_data, f)

        # Mock container with no labels
        container_inspect = [
            {
                "Id": "ghi456jkl789ghi456jkl789ghi456jkl789ghi456jkl789ghi456jkl789ghij",
                "Name": "/unlabeled-container",
                "Config": {"Labels": {}},
            }
        ]

        # Patch get_all_containers and get_admin_users
        sync_module.get_all_containers = lambda: container_inspect
        sync_module.get_admin_users = lambda: ["admin1"]

        result = sync_module.build_ownership_data()

        # Should preserve tracker-detected owner
        container_entry = result["containers"].get("ghi456jkl789")
        assert container_entry is not None
        assert container_entry["owner"] == "tracker-detected-user"

    @pytest.mark.unit
    def test_preserves_tracker_metadata(
        self, sync_module, temp_ownership_file, existing_tracker_data
    ):
        """Sync preserves tracker metadata (owner_uid, interface, etc.)."""
        with open(temp_ownership_file, "w") as f:
            json.dump(existing_tracker_data, f)

        container_inspect = [
            {
                "Id": "ghi456jkl789ghi456jkl789ghi456jkl789ghi456jkl789ghi456jkl789ghij",
                "Name": "/unlabeled-container",
                "Config": {"Labels": {}},
            }
        ]

        sync_module.get_all_containers = lambda: container_inspect
        sync_module.get_admin_users = lambda: ["admin1"]

        result = sync_module.build_ownership_data()

        container_entry = result["containers"].get("ghi456jkl789")
        assert container_entry is not None
        assert container_entry.get("owner_uid") == 2000
        assert container_entry.get("interface") == "docker"
        assert container_entry.get("detection_method") == "mount_path"

    @pytest.mark.unit
    def test_label_owner_overrides_tracker_owner(
        self, sync_module, temp_ownership_file, existing_tracker_data
    ):
        """Label-based owner takes priority over tracker-detected owner."""
        with open(temp_ownership_file, "w") as f:
            json.dump(existing_tracker_data, f)

        # Container now has a label
        container_inspect = [
            {
                "Id": "ghi456jkl789ghi456jkl789ghi456jkl789ghi456jkl789ghi456jkl789ghij",
                "Name": "/unlabeled-container",
                "Config": {"Labels": {"ds01.user": "label-owner"}},
            }
        ]

        sync_module.get_all_containers = lambda: container_inspect
        sync_module.get_admin_users = lambda: ["admin1"]

        result = sync_module.build_ownership_data()

        container_entry = result["containers"].get("ghi456jkl789")
        assert container_entry is not None
        assert container_entry["owner"] == "label-owner"


# =============================================================================
# Test: File Locking
# =============================================================================


class TestSyncFileLocking:
    """Tests for file locking in sync script."""

    @pytest.mark.unit
    def test_write_acquires_lock(self, sync_module, temp_ownership_dir):
        """Write operation acquires file lock."""
        lock_file = temp_ownership_dir / "test.lock"

        with sync_module.file_lock(lock_file):
            # Lock acquired - file should exist
            assert lock_file.exists()

    @pytest.mark.unit
    def test_write_uses_atomic_rename(self, sync_module, temp_ownership_file, temp_ownership_dir):
        """Write uses atomic temp file + rename pattern."""
        sync_module.get_all_containers = lambda: []
        sync_module.get_admin_users = lambda: []

        data = {"containers": {}, "admins": [], "service_users": [], "updated_at": "now"}
        result = sync_module.write_ownership_data(data)

        assert result is True
        assert temp_ownership_file.exists()
        # Temp file should not exist (was renamed)
        assert not temp_ownership_file.with_suffix(".tmp").exists()

    @pytest.mark.unit
    def test_write_handles_lock_timeout(self, sync_module, temp_ownership_dir):
        """Write handles lock timeout gracefully."""
        import fcntl

        lock_file = temp_ownership_dir / "container-owners.lock"

        # Hold lock
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            # Replace file_lock with one that always times out
            original_file_lock = sync_module.file_lock

            def timeout_lock(*args, **kwargs):
                raise TimeoutError("Lock timeout")

            sync_module.file_lock = timeout_lock

            data = {"containers": {}, "admins": [], "service_users": []}
            result = sync_module.write_ownership_data(data)

            # Should return False but not crash
            assert result is False

            sync_module.file_lock = original_file_lock
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


# =============================================================================
# Test: Admin Users
# =============================================================================


class TestAdminUsers:
    """Tests for admin user detection."""

    @pytest.mark.unit
    def test_reads_admins_from_yaml(self, sync_module, temp_dir):
        """Reads admin list from resource-limits.yaml."""
        import yaml

        config_file = temp_dir / "resource-limits.yaml"
        config_data = {
            "groups": {
                "admin": {
                    "members": ["admin1", "admin2"],
                }
            }
        }
        with open(config_file, "w") as f:
            yaml.safe_dump(config_data, f)

        sync_module.RESOURCE_LIMITS = config_file

        admins = sync_module.get_admin_users()

        assert "admin1" in admins
        assert "admin2" in admins

    @pytest.mark.unit
    def test_reads_admins_from_linux_group(self, sync_module):
        """Reads admin list from ds01-admin Linux group."""
        getent_output = "ds01-admin:x:1234:admin1,admin2,admin3"

        sync_module.RESOURCE_LIMITS = Path("/nonexistent")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=getent_output
            )

            admins = sync_module.get_admin_users()

            assert "admin1" in admins
            assert "admin2" in admins
            assert "admin3" in admins

    @pytest.mark.unit
    def test_combines_yaml_and_group_admins(self, sync_module, temp_dir):
        """Combines admins from YAML and Linux group."""
        import yaml

        config_file = temp_dir / "resource-limits.yaml"
        config_data = {
            "groups": {
                "admin": {
                    "members": ["yaml-admin"],
                }
            }
        }
        with open(config_file, "w") as f:
            yaml.safe_dump(config_data, f)

        sync_module.RESOURCE_LIMITS = config_file

        getent_output = "ds01-admin:x:1234:group-admin"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=getent_output
            )

            admins = sync_module.get_admin_users()

            assert "yaml-admin" in admins
            assert "group-admin" in admins


# =============================================================================
# Test: Data Structure
# =============================================================================


class TestBuildOwnershipData:
    """Tests for build_ownership_data function."""

    @pytest.mark.unit
    def test_output_structure(self, sync_module, temp_ownership_file):
        """Output has required structure."""
        sync_module.get_all_containers = lambda: []
        sync_module.get_admin_users = lambda: ["admin1"]

        result = sync_module.build_ownership_data()

        assert "containers" in result
        assert "admins" in result
        assert "service_users" in result
        assert "updated_at" in result

    @pytest.mark.unit
    def test_stores_by_multiple_keys(
        self, sync_module, temp_ownership_file, sample_container_inspect_data
    ):
        """Stores containers by short ID, full ID, and name."""
        sync_module.get_all_containers = lambda: sample_container_inspect_data
        sync_module.get_admin_users = lambda: []

        result = sync_module.build_ownership_data()
        containers = result["containers"]

        # Short ID
        assert "abc123def456" in containers
        # Full ID
        assert "abc123def456789abc123def456789abc123def456789abc123def456789abcd" in containers
        # Name
        assert "project-a" in containers

    @pytest.mark.unit
    def test_ds01_managed_detection(self, sync_module, temp_ownership_file):
        """Correctly detects ds01_managed flag."""
        containers = [
            {
                "Id": "managed123managed123managed123managed123managed123managed123mana",
                "Name": "/managed",
                "Config": {"Labels": {"ds01.managed": "true"}},
            },
            {
                "Id": "aimemanaged123aimemanaged123aimemanaged123aimemanaged123aimem",
                "Name": "/aime-managed",
                "Config": {"Labels": {"aime.mlc.DS01_MANAGED": "true"}},
            },
            {
                "Id": "unmanaged123unmanaged123unmanaged123unmanaged123unmanaged123unm",
                "Name": "/unmanaged",
                "Config": {"Labels": {}},
            },
        ]

        sync_module.get_all_containers = lambda: containers
        sync_module.get_admin_users = lambda: []

        result = sync_module.build_ownership_data()

        # Use container names for lookup (more reliable than truncated IDs)
        assert result["containers"]["managed"]["ds01_managed"] is True
        assert result["containers"]["aime-managed"]["ds01_managed"] is True
        assert result["containers"]["unmanaged"]["ds01_managed"] is False


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestSyncEdgeCases:
    """Tests for edge cases in sync script."""

    @pytest.mark.unit
    def test_handles_no_containers(self, sync_module, temp_ownership_file):
        """Handles system with no containers."""
        sync_module.get_all_containers = lambda: []
        sync_module.get_admin_users = lambda: []

        result = sync_module.build_ownership_data()

        assert result["containers"] == {}

    @pytest.mark.unit
    def test_handles_container_without_labels(self, sync_module, temp_ownership_file):
        """Handles containers with no labels (None)."""
        containers = [
            {
                "Id": "nolabel123nolabel123nolabel123nolabel123nolabel123nolabel123no",
                "Name": "/no-labels",
                "Config": {"Labels": None},
            }
        ]

        sync_module.get_all_containers = lambda: containers
        sync_module.get_admin_users = lambda: []

        result = sync_module.build_ownership_data()

        # Should not crash, owner should be None
        assert result["containers"]["nolabel123no"]["owner"] is None

    @pytest.mark.unit
    def test_handles_corrupt_existing_file(self, sync_module, temp_ownership_file):
        """Handles corrupt existing ownership file."""
        temp_ownership_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_ownership_file, "w") as f:
            f.write("{ corrupt json }")

        result = sync_module.load_existing_ownership()

        # Should return empty structure, not crash
        assert result == {"containers": {}}

    @pytest.mark.unit
    def test_handles_missing_existing_file(self, sync_module, temp_ownership_dir):
        """Handles missing ownership file."""
        missing_file = temp_ownership_dir / "nonexistent.json"
        sync_module.OUTPUT_FILE = missing_file

        result = sync_module.load_existing_ownership()

        assert result == {"containers": {}}

    @pytest.mark.unit
    def test_handles_empty_container_name(self, sync_module, temp_ownership_file):
        """Handles container with empty name."""
        containers = [
            {
                "Id": "emptyname123emptyname123emptyname123emptyname123emptyname123em",
                "Name": "",
                "Config": {"Labels": {"ds01.user": "testuser"}},
            }
        ]

        sync_module.get_all_containers = lambda: containers
        sync_module.get_admin_users = lambda: []

        # Should not crash
        result = sync_module.build_ownership_data()
        # Short ID is first 12 chars
        assert "emptyname123" in result["containers"]


# =============================================================================
# Test: CLI Interface
# =============================================================================


class TestSyncCLI:
    """Tests for sync script CLI interface."""

    @pytest.mark.unit
    def test_sync_once_returns_success(self, sync_module, temp_ownership_file, temp_ownership_dir):
        """sync_once returns True on success."""
        sync_module.get_all_containers = lambda: []
        sync_module.get_admin_users = lambda: []

        result = sync_module.sync_once()

        assert result is True
        assert temp_ownership_file.exists()

    @pytest.mark.unit
    def test_sets_file_permissions(self, sync_module, temp_ownership_file, temp_ownership_dir):
        """Output file has correct permissions (0644)."""
        sync_module.get_all_containers = lambda: []
        sync_module.get_admin_users = lambda: []

        sync_module.sync_once()

        mode = os.stat(temp_ownership_file).st_mode & 0o777
        assert mode == 0o644
