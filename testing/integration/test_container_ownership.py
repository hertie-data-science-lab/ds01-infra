#!/usr/bin/env python3
"""
Integration Tests: Container Ownership System

Tests for the integrated container ownership tracking system:
- Tracker daemon startup and catch-up
- Event handling (container create/destroy)
- Dashboard reading ownership file
- Sync script preserving tracker data
"""

import importlib.util
import importlib.machinery
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Module Loading (handles hyphenated filenames)
# =============================================================================


def load_tracker_module(temp_output_file=None, temp_lock_file=None):
    """Load container-owner-tracker.py module."""
    script_path = Path("/opt/ds01-infra/scripts/docker/container-owner-tracker.py")
    spec = importlib.util.spec_from_file_location("container_owner_tracker", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if temp_output_file:
        module.OUTPUT_FILE = temp_output_file
    if temp_lock_file:
        module.LOCK_FILE = temp_lock_file

    return module


def load_sync_module(temp_output_file=None, temp_lock_file=None, temp_output_dir=None):
    """Load sync-container-owners.py module."""
    script_path = Path("/opt/ds01-infra/scripts/docker/sync-container-owners.py")
    spec = importlib.util.spec_from_file_location("sync_container_owners", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if temp_output_file:
        module.OUTPUT_FILE = temp_output_file
    if temp_lock_file:
        module.LOCK_FILE = temp_lock_file
    if temp_output_dir:
        module.OUTPUT_DIR = temp_output_dir

    return module


def load_dashboard_module(temp_ownership_file=None):
    """Load dashboard module (handles extensionless Python scripts)."""
    script_path = Path("/opt/ds01-infra/scripts/admin/dashboard")

    # For extensionless Python scripts, we need to explicitly specify the loader
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
def temp_ownership_dir(temp_dir):
    """Create temporary ownership directory structure."""
    opa_dir = temp_dir / "var" / "lib" / "ds01" / "opa"
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
def sample_ownership_data():
    """Sample ownership data with various detection methods."""
    return {
        "containers": {
            "abc123def456": {
                "owner": "labeled-user",
                "owner_uid": 1001,
                "name": "labeled-container",
                "ds01_managed": True,
                "interface": "atomic",
                "created_at": "2025-01-01T00:00:00+00:00",
                "detection_method": "ds01_label",
            },
            "labeled-container": {
                "owner": "labeled-user",
                "owner_uid": 1001,
                "name": "labeled-container",
                "ds01_managed": True,
                "interface": "atomic",
                "created_at": "2025-01-01T00:00:00+00:00",
                "detection_method": "ds01_label",
            },
            "def789ghi012": {
                "owner": "mount-detected-user",
                "owner_uid": 2002,
                "name": "unlabeled-compose",
                "ds01_managed": False,
                "interface": "compose",
                "created_at": "2025-01-01T01:00:00+00:00",
                "detection_method": "mount_path",
            },
            "unlabeled-compose": {
                "owner": "mount-detected-user",
                "owner_uid": 2002,
                "name": "unlabeled-compose",
                "ds01_managed": False,
                "interface": "compose",
                "created_at": "2025-01-01T01:00:00+00:00",
                "detection_method": "mount_path",
            },
        },
        "admins": ["admin1", "admin2"],
        "service_users": ["ds01-dashboard"],
        "updated_at": "2025-01-07T12:00:00+00:00",
    }


# =============================================================================
# Test: Tracker Daemon Startup
# =============================================================================


class TestTrackerStartup:
    """Tests for tracker daemon startup behavior."""

    @pytest.mark.integration
    def test_tracker_script_exists(self):
        """Tracker script exists and is executable."""
        tracker_path = Path("/opt/ds01-infra/scripts/docker/container-owner-tracker.py")
        assert tracker_path.exists()
        # Check it's a valid Python script
        content = tracker_path.read_text()
        assert "#!/usr/bin/env python3" in content

    @pytest.mark.integration
    def test_tracker_has_required_functions(self, temp_ownership_file, temp_lock_file):
        """Tracker has required class and methods."""
        module = load_tracker_module(temp_ownership_file, temp_lock_file)
        tracker = module.ContainerOwnerTracker()

        # Required methods exist
        assert hasattr(tracker, "_detect_owner")
        assert hasattr(tracker, "_detect_interface")
        assert hasattr(tracker, "_validate_path_ownership")
        assert hasattr(tracker, "_resolve_uid_to_username")
        assert hasattr(tracker, "_resolve_username_to_uid")
        assert hasattr(tracker, "handle_create")
        assert hasattr(tracker, "handle_destroy")
        assert hasattr(tracker, "_startup_catchup")

    @pytest.mark.integration
    def test_tracker_loads_existing_data_on_startup(
        self, temp_ownership_file, temp_lock_file, sample_ownership_data
    ):
        """Tracker loads existing ownership data on startup."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_tracker_module(temp_ownership_file, temp_lock_file)
        tracker = module.ContainerOwnerTracker()

        # Should have loaded existing containers
        assert "abc123def456" in tracker.owners["containers"]
        assert tracker.owners["containers"]["abc123def456"]["owner"] == "labeled-user"


# =============================================================================
# Test: Dashboard Integration
# =============================================================================


class TestDashboardIntegration:
    """Tests for dashboard reading ownership file."""

    @pytest.mark.integration
    def test_dashboard_script_exists(self):
        """Dashboard script exists."""
        dashboard_path = Path("/opt/ds01-infra/scripts/admin/dashboard")
        assert dashboard_path.exists()

    @pytest.mark.integration
    def test_dashboard_has_ownership_file_constant(self):
        """Dashboard references ownership file."""
        dashboard_path = Path("/opt/ds01-infra/scripts/admin/dashboard")
        content = dashboard_path.read_text()

        assert "container-owners.json" in content
        assert "OWNERSHIP_FILE" in content or "_load_ownership_file" in content

    @pytest.mark.integration
    def test_dashboard_extract_owner_with_fallback(
        self, temp_ownership_file, sample_ownership_data
    ):
        """Dashboard extract_owner falls back to ownership file."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)

        # Clear the cache
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        # Extract owner for labeled container (should use label)
        result = module.DashboardData.extract_owner(
            ds01_user="labeled-user",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="labeled-container"
        )
        assert result == "labeled-user"

        # Extract owner for unlabeled container (should use ownership file)
        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="unlabeled-compose"
        )
        assert result == "mount-detected-user"

    @pytest.mark.integration
    def test_dashboard_handles_missing_ownership_file(self, temp_dir):
        """Dashboard handles missing ownership file gracefully."""
        missing_file = temp_dir / "nonexistent-ownership-file.json"

        module = load_dashboard_module(missing_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        # Should return "(other)" for unknown container
        result = module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="unknown-container"
        )
        assert result == "(other)"

    @pytest.mark.integration
    def test_dashboard_ownership_cache(self, temp_ownership_file, sample_ownership_data):
        """Dashboard caches ownership file for performance."""
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        module = load_dashboard_module(temp_ownership_file)
        module.DashboardData._ownership_cache = None
        module.DashboardData._ownership_cache_time = 0

        # First call loads from file
        data1 = module.DashboardData._load_ownership_file()
        cache_time = module.DashboardData._ownership_cache_time

        # Second call should use cache (same time)
        data2 = module.DashboardData._load_ownership_file()

        assert data1 == data2
        assert module.DashboardData._ownership_cache_time == cache_time


# =============================================================================
# Test: Sync Script Integration
# =============================================================================


class TestSyncIntegration:
    """Tests for sync script integration with tracker."""

    @pytest.mark.integration
    def test_sync_script_exists(self):
        """Sync script exists."""
        sync_path = Path("/opt/ds01-infra/scripts/docker/sync-container-owners.py")
        assert sync_path.exists()

    @pytest.mark.integration
    def test_sync_preserves_tracker_owners(
        self, temp_ownership_file, temp_lock_file, temp_ownership_dir, sample_ownership_data
    ):
        """Sync preserves tracker-detected owners for unlabeled containers."""
        # Write existing tracker data
        with open(temp_ownership_file, "w") as f:
            json.dump(sample_ownership_data, f)

        # Simulate container still running but no labels
        container_data = [
            {
                "Id": "def789ghi012def789ghi012def789ghi012def789ghi012def789ghi012defg",
                "Name": "/unlabeled-compose",
                "Config": {"Labels": {}},  # No labels!
            }
        ]

        module = load_sync_module(temp_ownership_file, temp_lock_file, temp_ownership_dir)
        module.get_all_containers = lambda: container_data
        module.get_admin_users = lambda: ["admin1"]

        result = module.build_ownership_data()

        # Should preserve tracker-detected owner
        entry = result["containers"].get("def789ghi012")
        assert entry is not None
        assert entry["owner"] == "mount-detected-user"
        assert entry.get("detection_method") == "mount_path"

    @pytest.mark.integration
    def test_sync_and_tracker_use_same_lock(self):
        """Sync and tracker use the same lock file path."""
        tracker_module = load_tracker_module()
        sync_module = load_sync_module()

        assert tracker_module.LOCK_FILE == sync_module.LOCK_FILE


# =============================================================================
# Test: Concurrent Access
# =============================================================================


class TestConcurrentAccess:
    """Tests for concurrent tracker and sync access."""

    @pytest.mark.integration
    def test_concurrent_writes_use_locking(self, temp_lock_file):
        """Both tracker and sync use file locking for writes."""
        tracker_module = load_tracker_module(temp_lock_file=temp_lock_file)
        sync_module = load_sync_module(temp_lock_file=temp_lock_file)

        # Both should have file_lock function
        assert callable(tracker_module.file_lock)
        assert callable(sync_module.file_lock)

        # Both should work with the same lock file
        with tracker_module.file_lock(temp_lock_file):
            pass

        with sync_module.file_lock(temp_lock_file):
            pass

    @pytest.mark.integration
    def test_atomic_write_pattern(self):
        """Both scripts use atomic write (temp file + rename)."""
        tracker_path = Path("/opt/ds01-infra/scripts/docker/container-owner-tracker.py")
        sync_path = Path("/opt/ds01-infra/scripts/docker/sync-container-owners.py")

        tracker_content = tracker_path.read_text()
        sync_content = sync_path.read_text()

        # Both should use .tmp file pattern
        assert ".tmp" in tracker_content or "with_suffix" in tracker_content
        assert ".tmp" in sync_content or "with_suffix" in sync_content

        # Both should use rename for atomic update
        assert "rename" in tracker_content
        assert "rename" in sync_content


# =============================================================================
# Test: Full Flow Integration
# =============================================================================


class TestFullFlowIntegration:
    """End-to-end integration tests for ownership tracking flow."""

    @pytest.mark.integration
    def test_tracker_create_sync_dashboard_flow(
        self, temp_ownership_file, temp_lock_file, temp_ownership_dir
    ):
        """Full flow: tracker creates entry, sync preserves it, dashboard reads it."""
        # Step 1: Tracker creates entry for container
        container_data = {
            "Id": "flow123flow123flow123flow123flow123flow123flow123flow123flow123fl",
            "Name": "/flow-test-container",
            "Config": {"Labels": {}},  # No labels
            "HostConfig": {
                "Binds": ["/home/flowuser/project:/workspace:rw"]
            },
        }

        tracker_module = load_tracker_module(temp_ownership_file, temp_lock_file)
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: container_data
        tracker._resolve_username_to_uid = lambda x: 3001
        tracker._validate_path_ownership = lambda path, uid: True

        tracker.handle_create("flow123flow123flow123flow123flow123flow123flow123flow123flow123fl")

        # Verify tracker created entry
        assert "flow-test-container" in tracker.owners["containers"]
        assert tracker.owners["containers"]["flow-test-container"]["owner"] == "flowuser"
        assert tracker.owners["containers"]["flow-test-container"]["detection_method"] == "mount_path"

        # Step 2: Sync runs and preserves tracker entry
        containers = [
            {
                "Id": "flow123flow123flow123flow123flow123flow123flow123flow123flow123fl",
                "Name": "/flow-test-container",
                "Config": {"Labels": {}},  # Still no labels
            }
        ]

        sync_module = load_sync_module(temp_ownership_file, temp_lock_file, temp_ownership_dir)
        sync_module.get_all_containers = lambda: containers
        sync_module.get_admin_users = lambda: []

        data = sync_module.build_ownership_data()
        sync_module.write_ownership_data(data)

        # Verify sync preserved owner
        assert data["containers"]["flow123flow1"]["owner"] == "flowuser"

        # Step 3: Dashboard reads ownership file
        dashboard_module = load_dashboard_module(temp_ownership_file)
        dashboard_module.DashboardData._ownership_cache = None
        dashboard_module.DashboardData._ownership_cache_time = 0

        owner = dashboard_module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="flow-test-container"
        )

        assert owner == "flowuser"

    @pytest.mark.integration
    def test_container_removal_cleans_up(self, temp_ownership_file, temp_lock_file):
        """Container removal removes entry from ownership data."""
        # Setup initial data
        initial_data = {
            "containers": {
                "remove123remo": {
                    "owner": "removeuser",
                    "owner_uid": 4001,
                    "name": "to-be-removed",
                    "ds01_managed": False,
                    "interface": "docker",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "detection_method": "mount_path",
                },
                "to-be-removed": {
                    "owner": "removeuser",
                    "owner_uid": 4001,
                    "name": "to-be-removed",
                    "ds01_managed": False,
                    "interface": "docker",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "detection_method": "mount_path",
                },
            },
            "admins": [],
            "service_users": ["ds01-dashboard"],
        }

        with open(temp_ownership_file, "w") as f:
            json.dump(initial_data, f)

        tracker_module = load_tracker_module(temp_ownership_file, temp_lock_file)
        tracker = tracker_module.ContainerOwnerTracker()

        # Container exists
        assert "to-be-removed" in tracker.owners["containers"]

        # Handle destroy event
        tracker.handle_destroy("remove123remo", "to-be-removed")

        # Container removed
        assert "to-be-removed" not in tracker.owners["containers"]
        assert "remove123remo" not in tracker.owners["containers"]


# =============================================================================
# Test: Domain User Support
# =============================================================================


class TestDomainUserSupport:
    """Tests for domain user support (LDAP/SSSD)."""

    @pytest.mark.integration
    def test_domain_user_ownership_tracking(self, temp_ownership_file, temp_lock_file):
        """Domain users with @ in username are tracked correctly."""
        container_data = {
            "Id": "domain123domain123domain123domain123domain123domain123domain1",
            "Name": "/domain-user-container",
            "Config": {"Labels": {"ds01.user": "h.baker@hertie-school.lan"}},
            "HostConfig": {"Binds": []},
        }

        tracker_module = load_tracker_module(temp_ownership_file, temp_lock_file)
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: container_data
        tracker._resolve_username_to_uid = lambda x: 1722830498

        tracker.handle_create("domain123domain123domain123domain123domain123domain123domain1")

        entry = tracker.owners["containers"].get("domain-user-container")
        assert entry is not None
        assert entry["owner"] == "h.baker@hertie-school.lan"
        assert entry["owner_uid"] == 1722830498

    @pytest.mark.integration
    def test_domain_user_in_dashboard(self, temp_ownership_file):
        """Dashboard correctly displays domain users."""
        data = {
            "containers": {
                "domain-container": {
                    "owner": "h.baker@hertie-school.lan",
                    "owner_uid": 1722830498,
                    "name": "domain-container",
                    "ds01_managed": True,
                    "interface": "atomic",
                    "detection_method": "ds01_label",
                }
            },
            "admins": [],
            "service_users": [],
        }

        with open(temp_ownership_file, "w") as f:
            json.dump(data, f)

        dashboard_module = load_dashboard_module(temp_ownership_file)
        dashboard_module.DashboardData._ownership_cache = None
        dashboard_module.DashboardData._ownership_cache_time = 0

        owner = dashboard_module.DashboardData.extract_owner(
            ds01_user="",
            aime_user_upper="",
            aime_username="",
            devcontainer_path="",
            container_name="domain-container"
        )

        assert owner == "h.baker@hertie-school.lan"
