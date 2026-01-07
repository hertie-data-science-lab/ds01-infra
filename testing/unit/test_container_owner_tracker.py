#!/usr/bin/env python3
"""
Unit Tests: Container Owner Tracker

Tests for the container-owner-tracker.py daemon that detects container ownership
via multiple strategies (labels, name patterns, mount paths, etc.)
"""

import importlib.util
import json
import os
import pwd
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest


# =============================================================================
# Module Loading (handles hyphenated filenames)
# =============================================================================


def load_tracker_module(temp_output_file=None, temp_lock_file=None):
    """
    Load container-owner-tracker.py module with optional path overrides.

    Python can't import filenames with hyphens, so we use importlib.util.
    """
    script_path = Path("/opt/ds01-infra/scripts/docker/container-owner-tracker.py")

    spec = importlib.util.spec_from_file_location("container_owner_tracker", script_path)
    module = importlib.util.module_from_spec(spec)

    # Optionally override paths before loading
    if temp_output_file or temp_lock_file:
        # We need to modify the module's globals after loading
        spec.loader.exec_module(module)
        if temp_output_file:
            module.OUTPUT_FILE = temp_output_file
        if temp_lock_file:
            module.LOCK_FILE = temp_lock_file
    else:
        spec.loader.exec_module(module)

    return module


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_ownership_file(temp_dir):
    """Create temporary ownership file path."""
    return temp_dir / "container-owners.json"


@pytest.fixture
def temp_lock_file(temp_dir):
    """Create temporary lock file path."""
    return temp_dir / "container-owners.lock"


@pytest.fixture
def tracker_module(temp_ownership_file, temp_lock_file):
    """Load tracker module with temp paths."""
    return load_tracker_module(temp_ownership_file, temp_lock_file)


@pytest.fixture
def sample_container_data():
    """Sample container data from docker inspect."""
    return {
        "Id": "abc123def456789abc123def456789abc123def456789abc123def456789abcd",
        "Name": "/test-container",
        "Config": {
            "Labels": {
                "ds01.user": "testuser",
                "ds01.managed": "true",
            }
        },
        "HostConfig": {
            "Binds": ["/home/testuser/project:/workspace:rw"]
        },
    }


@pytest.fixture
def sample_aime_container_data():
    """Sample AIME-style container data."""
    return {
        "Id": "def456abc789def456abc789def456abc789def456abc789def456abc789defg",
        "Name": "/project._.1001",
        "Config": {
            "Labels": {
                "aime.mlc.USER": "student1",
                "aime.mlc.DS01_MANAGED": "true",
            }
        },
        "HostConfig": {
            "Binds": []
        },
    }


@pytest.fixture
def sample_devcontainer_data():
    """Sample VS Code devcontainer data."""
    return {
        "Id": "ghi789jkl012ghi789jkl012ghi789jkl012ghi789jkl012ghi789jkl012ghij",
        "Name": "/vsc-myproject-abc123",
        "Config": {
            "Labels": {
                "devcontainer.local_folder": "/home/developer/projects/myproject",
            }
        },
        "HostConfig": {
            "Binds": ["/home/developer/projects/myproject:/workspace:cached"]
        },
    }


@pytest.fixture
def sample_compose_container_data():
    """Sample docker-compose container data."""
    return {
        "Id": "mno345pqr678mno345pqr678mno345pqr678mno345pqr678mno345pqr678mnop",
        "Name": "/myproject-web-1",
        "Config": {
            "Labels": {
                "com.docker.compose.project": "myproject",
                "com.docker.compose.project.working_dir": "/home/researcher/myproject",
            }
        },
        "HostConfig": {
            "Binds": ["/home/researcher/myproject:/app:rw"]
        },
    }


@pytest.fixture
def sample_unlabeled_container_data():
    """Sample container with no ownership labels."""
    return {
        "Id": "stu901vwx234stu901vwx234stu901vwx234stu901vwx234stu901vwx234stuv",
        "Name": "/random-container",
        "Config": {
            "Labels": {}
        },
        "HostConfig": {
            "Binds": ["/home/someuser/data:/data:ro"]
        },
    }


@pytest.fixture
def existing_ownership_data():
    """Sample existing ownership file data."""
    return {
        "containers": {
            "abc123def456": {
                "owner": "existinguser",
                "owner_uid": 1000,
                "name": "existing-container",
                "ds01_managed": True,
                "interface": "atomic",
                "created_at": "2025-01-01T00:00:00+00:00",
                "detection_method": "ds01_label",
            }
        },
        "admins": ["admin1"],
        "service_users": ["ds01-dashboard"],
        "updated_at": "2025-01-01T00:00:00+00:00",
    }


# =============================================================================
# Test: Owner Detection Strategies
# =============================================================================


class TestOwnerDetectionStrategies:
    """Tests for the 6 owner detection strategies."""

    @pytest.mark.unit
    def test_strategy_1_ds01_label(self, tracker_module, sample_container_data):
        """Strategy 1: ds01.user label detection."""
        tracker = tracker_module.ContainerOwnerTracker()

        # Mock the username resolution
        original_resolve = tracker._resolve_username_to_uid
        tracker._resolve_username_to_uid = lambda x: 1001

        username, uid, method = tracker._detect_owner(sample_container_data)

        assert username == "testuser"
        assert uid == 1001
        assert method == "ds01_label"

    @pytest.mark.unit
    def test_strategy_2_aime_label(self, tracker_module, sample_aime_container_data):
        """Strategy 2: aime.mlc.USER label detection."""
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._resolve_username_to_uid = lambda x: 1002

        username, uid, method = tracker._detect_owner(sample_aime_container_data)

        assert username == "student1"
        assert uid == 1002
        assert method == "aime_label"

    @pytest.mark.unit
    def test_strategy_3_container_name_pattern(self, tracker_module):
        """Strategy 3: Container name pattern (name._.uid) detection."""
        container_data = {
            "Id": "xyz123",
            "Name": "/project._.1234",
            "Config": {"Labels": {}},
            "HostConfig": {"Binds": []},
        }

        tracker = tracker_module.ContainerOwnerTracker()
        tracker._resolve_uid_to_username = lambda x: "uiduser"

        username, uid, method = tracker._detect_owner(container_data)

        assert username == "uiduser"
        assert uid == 1234
        assert method == "container_name"

    @pytest.mark.unit
    def test_strategy_4_devcontainer_local_folder(self, tracker_module, sample_devcontainer_data):
        """Strategy 4: devcontainer.local_folder label detection."""
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._resolve_username_to_uid = lambda x: 1003

        username, uid, method = tracker._detect_owner(sample_devcontainer_data)

        assert username == "developer"
        assert uid == 1003
        assert method == "devcontainer"

    @pytest.mark.unit
    def test_strategy_5_bind_mount_path(self, tracker_module):
        """Strategy 5: Bind mount path detection."""
        container_data = {
            "Id": "xyz456",
            "Name": "/plain-container",
            "Config": {"Labels": {}},
            "HostConfig": {
                "Binds": ["/home/mountuser/project:/workspace:rw"]
            },
        }

        tracker = tracker_module.ContainerOwnerTracker()
        tracker._resolve_username_to_uid = lambda x: 1004
        tracker._validate_path_ownership = lambda path, uid: True

        username, uid, method = tracker._detect_owner(container_data)

        assert username == "mountuser"
        assert uid == 1004
        assert method == "mount_path"

    @pytest.mark.unit
    def test_strategy_6_compose_working_dir(self, tracker_module, sample_compose_container_data):
        """Strategy 6: Docker Compose working_dir label detection."""
        # Remove bind mounts to force compose_dir detection
        sample_compose_container_data["HostConfig"]["Binds"] = []

        tracker = tracker_module.ContainerOwnerTracker()
        tracker._resolve_username_to_uid = lambda x: 1005

        username, uid, method = tracker._detect_owner(sample_compose_container_data)

        assert username == "researcher"
        assert uid == 1005
        assert method == "compose_dir"

    @pytest.mark.unit
    def test_strategy_priority_ds01_over_aime(self, tracker_module):
        """ds01.user label takes priority over aime.mlc.USER."""
        container_data = {
            "Id": "priority123",
            "Name": "/priority-test",
            "Config": {
                "Labels": {
                    "ds01.user": "ds01user",
                    "aime.mlc.USER": "aimeuser",
                }
            },
            "HostConfig": {"Binds": []},
        }

        tracker = tracker_module.ContainerOwnerTracker()
        tracker._resolve_username_to_uid = lambda x: 1000

        username, _, method = tracker._detect_owner(container_data)

        assert username == "ds01user"
        assert method == "ds01_label"

    @pytest.mark.unit
    def test_unknown_owner_when_no_strategy_matches(self, tracker_module):
        """Returns unknown when no detection strategy matches."""
        container_data = {
            "Id": "unknown123",
            "Name": "/mystery-container",
            "Config": {"Labels": {}},
            "HostConfig": {"Binds": []},  # No /home paths
        }

        tracker = tracker_module.ContainerOwnerTracker()
        username, uid, method = tracker._detect_owner(container_data)

        assert username is None
        assert uid is None
        assert method == "unknown"


# =============================================================================
# Test: Mount Path Ownership Validation (Security)
# =============================================================================


class TestMountPathValidation:
    """Tests for mount path ownership validation (anti-spoofing)."""

    @pytest.mark.unit
    def test_validates_path_owner_matches_claimed_uid(self, tracker_module, temp_dir):
        """Path ownership must match claimed UID."""
        # Create a test file owned by current user
        test_path = temp_dir / "testfile"
        test_path.touch()
        current_uid = os.getuid()

        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._validate_path_ownership(str(test_path), current_uid)

        assert result is True

    @pytest.mark.unit
    def test_rejects_path_when_owner_mismatch(self, tracker_module, temp_dir):
        """Rejects when path owner doesn't match claimed UID."""
        test_path = temp_dir / "testfile"
        test_path.touch()
        current_uid = os.getuid()
        wrong_uid = current_uid + 1000  # Definitely wrong

        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._validate_path_ownership(str(test_path), wrong_uid)

        assert result is False

    @pytest.mark.unit
    def test_handles_nonexistent_path_gracefully(self, tracker_module):
        """Non-existent paths don't cause crashes."""
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._validate_path_ownership("/nonexistent/path/file", 1000)

        # Should return False (reject) for unvalidatable paths
        assert result is False

    @pytest.mark.unit
    def test_extracts_source_from_bind_mount_spec(self, tracker_module, temp_dir):
        """Correctly extracts source path from bind mount spec (path:target)."""
        test_path = temp_dir / "source"
        test_path.mkdir()
        current_uid = os.getuid()

        tracker = tracker_module.ContainerOwnerTracker()
        # Bind mount format: source:target:options
        bind_spec = f"{test_path}:/container/path:rw"
        result = tracker._validate_path_ownership(bind_spec, current_uid)

        assert result is True

    @pytest.mark.unit
    def test_spoofing_attempt_detected(self, tracker_module, temp_dir):
        """
        Detect mount path spoofing where user A mounts /home/userB to claim userB's identity.

        This is the core security feature - we verify the mount source is actually
        owned by the claimed user.
        """
        # Create path that looks like another user's home
        fake_userb_home = temp_dir / "home" / "userB"
        fake_userb_home.mkdir(parents=True)

        current_uid = os.getuid()
        userb_fake_uid = 9999  # Not the owner

        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._validate_path_ownership(str(fake_userb_home), userb_fake_uid)

        # Should reject because actual owner (current_uid) != claimed owner (9999)
        assert result is False


# =============================================================================
# Test: UID/Username Resolution
# =============================================================================


class TestUIDResolution:
    """Tests for UID and username resolution including domain users."""

    @pytest.mark.unit
    def test_resolves_local_uid_to_username(self, tracker_module):
        """Resolves local UID to username via pwd module."""
        current_uid = os.getuid()
        expected_username = pwd.getpwuid(current_uid).pw_name

        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._resolve_uid_to_username(current_uid)

        assert result == expected_username

    @pytest.mark.unit
    def test_resolves_local_username_to_uid(self, tracker_module):
        """Resolves local username to UID via pwd module."""
        current_uid = os.getuid()
        current_username = pwd.getpwuid(current_uid).pw_name

        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._resolve_username_to_uid(current_username)

        assert result == current_uid

    @pytest.mark.unit
    def test_falls_back_to_getent_for_unknown_uid(self, tracker_module):
        """Falls back to getent for UIDs not in local passwd."""
        unknown_uid = 999999  # Very unlikely to exist locally

        # Mock getent to return a domain user
        getent_output = f"h.baker@hertie-school.lan:*:{unknown_uid}:999999::/home/h.baker:/bin/bash"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=getent_output
            )
            tracker = tracker_module.ContainerOwnerTracker()
            result = tracker._resolve_uid_to_username(unknown_uid)

            assert result == "h.baker@hertie-school.lan"

    @pytest.mark.unit
    def test_falls_back_to_getent_for_domain_username(self, tracker_module):
        """Falls back to getent for domain usernames."""
        domain_user = "h.baker@hertie-school.lan"
        domain_uid = 1722830498

        # Mock getent to return the UID
        getent_output = f"{domain_user}:*:{domain_uid}:999999::/home/h.baker:/bin/bash"

        with patch("pwd.getpwnam", side_effect=KeyError()), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=getent_output
            )
            tracker = tracker_module.ContainerOwnerTracker()
            result = tracker._resolve_username_to_uid(domain_user)

            assert result == domain_uid

    @pytest.mark.unit
    def test_returns_none_for_unresolvable_uid(self, tracker_module):
        """Returns None when UID cannot be resolved."""
        with patch("pwd.getpwuid", side_effect=KeyError()), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            tracker = tracker_module.ContainerOwnerTracker()
            result = tracker._resolve_uid_to_username(999999999)

            assert result is None

    @pytest.mark.unit
    def test_returns_none_for_unresolvable_username(self, tracker_module):
        """Returns None when username cannot be resolved."""
        with patch("pwd.getpwnam", side_effect=KeyError()), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            tracker = tracker_module.ContainerOwnerTracker()
            result = tracker._resolve_username_to_uid("nonexistent_user")

            assert result is None


# =============================================================================
# Test: Interface Detection
# =============================================================================


class TestInterfaceDetection:
    """Tests for detecting which interface created a container."""

    @pytest.mark.unit
    def test_detects_explicit_interface_label(self, tracker_module):
        """Detects interface from ds01.interface label."""
        container_data = {
            "Name": "/test",
            "Config": {"Labels": {"ds01.interface": "custom-interface"}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "custom-interface"

    @pytest.mark.unit
    def test_detects_ds01_managed_as_atomic(self, tracker_module):
        """DS01 managed containers detected as atomic interface."""
        container_data = {
            "Name": "/test",
            "Config": {"Labels": {"ds01.managed": "true"}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "atomic"

    @pytest.mark.unit
    def test_detects_aime_managed_as_atomic(self, tracker_module):
        """AIME managed containers detected as atomic interface."""
        container_data = {
            "Name": "/test",
            "Config": {"Labels": {"aime.mlc.DS01_MANAGED": "true"}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "atomic"

    @pytest.mark.unit
    def test_detects_aime_naming_as_atomic(self, tracker_module):
        """AIME naming convention (._.) detected as atomic interface."""
        container_data = {
            "Name": "/project._.1001",
            "Config": {"Labels": {}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "atomic"

    @pytest.mark.unit
    def test_detects_compose_interface(self, tracker_module):
        """Docker Compose containers detected."""
        container_data = {
            "Name": "/myproject-web-1",
            "Config": {"Labels": {"com.docker.compose.project": "myproject"}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "compose"

    @pytest.mark.unit
    def test_detects_devcontainer_by_labels(self, tracker_module):
        """VS Code devcontainers detected by labels."""
        container_data = {
            "Name": "/some-container",
            "Config": {"Labels": {"devcontainer.local_folder": "/home/user/project"}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "devcontainer"

    @pytest.mark.unit
    def test_detects_devcontainer_by_name_prefix(self, tracker_module):
        """VS Code devcontainers detected by vsc- name prefix."""
        container_data = {
            "Name": "/vsc-myproject-abc123",
            "Config": {"Labels": {}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "devcontainer"

    @pytest.mark.unit
    def test_default_interface_is_docker(self, tracker_module):
        """Unknown containers default to docker interface."""
        container_data = {
            "Name": "/random-container",
            "Config": {"Labels": {}}
        }
        tracker = tracker_module.ContainerOwnerTracker()
        result = tracker._detect_interface(container_data)
        assert result == "docker"


# =============================================================================
# Test: File Locking
# =============================================================================


class TestFileLocking:
    """Tests for file locking mechanism."""

    @pytest.mark.unit
    def test_file_lock_acquires_and_releases(self, tracker_module, temp_dir):
        """File lock can be acquired and released."""
        lock_path = temp_dir / "test.lock"

        with tracker_module.file_lock(lock_path):
            assert lock_path.exists()

        # After context exits, lock should be released
        # (We can acquire it again)
        with tracker_module.file_lock(lock_path):
            pass  # No error = success

    @pytest.mark.unit
    def test_file_lock_creates_parent_directories(self, tracker_module, temp_dir):
        """File lock creates parent directories if needed."""
        lock_path = temp_dir / "subdir" / "nested" / "test.lock"

        with tracker_module.file_lock(lock_path):
            assert lock_path.parent.exists()

    @pytest.mark.unit
    def test_file_lock_timeout_raises_error(self, tracker_module, temp_dir):
        """File lock raises TimeoutError when lock cannot be acquired."""
        import fcntl

        lock_path = temp_dir / "blocking.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Acquire lock in another file descriptor (simulating another process)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            with pytest.raises(TimeoutError):
                with tracker_module.file_lock(lock_path, timeout=0.3):
                    pass
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


# =============================================================================
# Test: JSON Data Format
# =============================================================================


class TestJSONDataFormat:
    """Tests for ownership JSON file format."""

    @pytest.mark.unit
    def test_initial_data_structure(self, tracker_module):
        """Initial data structure has required fields."""
        tracker = tracker_module.ContainerOwnerTracker()

        assert "containers" in tracker.owners
        assert "admins" in tracker.owners
        assert "service_users" in tracker.owners
        assert isinstance(tracker.owners["containers"], dict)
        assert isinstance(tracker.owners["admins"], list)

    @pytest.mark.unit
    def test_container_entry_format(self, tracker_module, sample_container_data):
        """Container entries have required fields."""
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: sample_container_data
        tracker._resolve_username_to_uid = lambda x: 1001

        tracker.handle_create("abc123def456")

        # Get entry (stored under short ID)
        entry = tracker.owners["containers"].get("abc123def456")

        assert entry is not None
        assert "owner" in entry
        assert "owner_uid" in entry
        assert "name" in entry
        assert "ds01_managed" in entry
        assert "interface" in entry
        assert "created_at" in entry
        assert "detection_method" in entry

    @pytest.mark.unit
    def test_stores_by_multiple_keys(self, tracker_module, sample_container_data):
        """Container entries stored by short ID, full ID, and name."""
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: sample_container_data
        tracker._resolve_username_to_uid = lambda x: 1001

        tracker.handle_create("abc123def456789abc123def456789abc123def456789abc123def456789abcd")

        containers = tracker.owners["containers"]

        # Short ID
        assert "abc123def456" in containers
        # Full ID
        assert "abc123def456789abc123def456789abc123def456789abc123def456789abcd" in containers
        # Name
        assert "test-container" in containers

    @pytest.mark.unit
    def test_loads_existing_data(self, tracker_module, temp_ownership_file, existing_ownership_data):
        """Tracker loads existing data on startup."""
        temp_ownership_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_ownership_file, "w") as f:
            json.dump(existing_ownership_data, f)

        # Need to reload module with the file present
        module = load_tracker_module(temp_ownership_file, temp_ownership_file.with_suffix(".lock"))
        tracker = module.ContainerOwnerTracker()

        assert "abc123def456" in tracker.owners["containers"]
        assert tracker.owners["containers"]["abc123def456"]["owner"] == "existinguser"


# =============================================================================
# Test: Container Lifecycle Events
# =============================================================================


class TestContainerLifecycleEvents:
    """Tests for container create/destroy event handling."""

    @pytest.mark.unit
    def test_handle_create_adds_entry(self, tracker_module, sample_container_data):
        """handle_create adds container to owners."""
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: sample_container_data
        tracker._resolve_username_to_uid = lambda x: 1001

        initial_count = len(tracker.owners["containers"])

        tracker.handle_create("abc123def456")

        assert len(tracker.owners["containers"]) > initial_count
        assert "test-container" in tracker.owners["containers"]

    @pytest.mark.unit
    def test_handle_destroy_removes_entry(self, tracker_module, sample_container_data):
        """handle_destroy removes container from owners."""
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: sample_container_data
        tracker._resolve_username_to_uid = lambda x: 1001

        tracker.handle_create("abc123def456")

        assert "test-container" in tracker.owners["containers"]

        tracker.handle_destroy("abc123def456", "test-container")

        assert "test-container" not in tracker.owners["containers"]

    @pytest.mark.unit
    def test_handle_create_with_failed_inspect(self, tracker_module):
        """handle_create handles failed docker inspect gracefully."""
        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: None

        initial_count = len(tracker.owners["containers"])

        # Should not crash
        tracker.handle_create("nonexistent123")

        # Should not add entry
        assert len(tracker.owners["containers"]) == initial_count

    @pytest.mark.unit
    def test_handle_destroy_nonexistent_container(self, tracker_module):
        """handle_destroy handles non-tracked container gracefully."""
        tracker = tracker_module.ContainerOwnerTracker()

        # Should not crash
        tracker.handle_destroy("nonexistent123", "nonexistent")

    @pytest.mark.unit
    def test_handle_destroy_removes_all_keys(self, tracker_module, sample_container_data):
        """handle_destroy removes all keys (short ID, full ID, name)."""
        full_id = "abc123def456789abc123def456789abc123def456789abc123def456789abcd"

        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: sample_container_data
        tracker._resolve_username_to_uid = lambda x: 1001

        tracker.handle_create(full_id)

        containers = tracker.owners["containers"]
        assert "abc123def456" in containers
        assert full_id in containers
        assert "test-container" in containers

        tracker.handle_destroy(full_id, "test-container")

        assert "abc123def456" not in containers
        assert full_id not in containers
        assert "test-container" not in containers


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_handles_domain_username_with_at_symbol(self, tracker_module):
        """Correctly handles domain usernames like h.baker@hertie-school.lan."""
        container_data = {
            "Id": "domain123",
            "Name": "/domain-test",
            "Config": {"Labels": {"ds01.user": "h.baker@hertie-school.lan"}},
            "HostConfig": {"Binds": []},
        }

        tracker = tracker_module.ContainerOwnerTracker()
        tracker._resolve_username_to_uid = lambda x: 1722830498

        username, uid, method = tracker._detect_owner(container_data)

        assert username == "h.baker@hertie-school.lan"
        assert uid == 1722830498

    @pytest.mark.unit
    def test_handles_container_name_with_special_chars(self, tracker_module):
        """Handles container names with underscores and dots."""
        container_data = {
            "Id": "special123",
            "Name": "/my_project.v2.test",
            "Config": {"Labels": {"ds01.user": "testuser"}},
            "HostConfig": {"Binds": []},
        }

        tracker = tracker_module.ContainerOwnerTracker()
        tracker._inspect_container = lambda x: container_data
        tracker._resolve_username_to_uid = lambda x: 1001

        tracker.handle_create("special123")

        assert "my_project.v2.test" in tracker.owners["containers"]

    @pytest.mark.unit
    def test_handles_empty_labels(self, tracker_module):
        """Handles containers with None labels."""
        container_data = {
            "Id": "nolabel123",
            "Name": "/no-labels",
            "Config": {"Labels": None},  # None, not empty dict
            "HostConfig": {"Binds": []},
        }

        tracker = tracker_module.ContainerOwnerTracker()
        username, uid, method = tracker._detect_owner(container_data)

        assert method == "unknown"

    @pytest.mark.unit
    def test_handles_empty_binds(self, tracker_module):
        """Handles containers with None binds."""
        container_data = {
            "Id": "nobind123",
            "Name": "/no-binds",
            "Config": {"Labels": {}},
            "HostConfig": {"Binds": None},  # None, not empty list
        }

        tracker = tracker_module.ContainerOwnerTracker()
        username, uid, method = tracker._detect_owner(container_data)

        assert method == "unknown"

    @pytest.mark.unit
    def test_handles_corrupt_ownership_file(self, temp_ownership_file):
        """Gracefully handles corrupt JSON ownership file."""
        temp_ownership_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_ownership_file, "w") as f:
            f.write("{ invalid json }")

        # Load module with corrupt file
        module = load_tracker_module(temp_ownership_file, temp_ownership_file.with_suffix(".lock"))
        tracker = module.ContainerOwnerTracker()

        assert "containers" in tracker.owners
        assert isinstance(tracker.owners["containers"], dict)

    @pytest.mark.unit
    def test_container_name_uid_extraction_handles_invalid_format(self, tracker_module):
        """Container name UID extraction handles invalid formats."""
        container_data = {
            "Id": "badformat123",
            "Name": "/project._.notanumber",  # Invalid UID
            "Config": {"Labels": {}},
            "HostConfig": {"Binds": []},
        }

        tracker = tracker_module.ContainerOwnerTracker()
        username, uid, method = tracker._detect_owner(container_data)

        # Should fall through to unknown since UID parse failed
        assert method == "unknown"

    @pytest.mark.unit
    def test_non_home_mount_paths_ignored(self, tracker_module):
        """Mount paths not under /home are ignored for owner detection."""
        container_data = {
            "Id": "nonhome123",
            "Name": "/data-container",
            "Config": {"Labels": {}},
            "HostConfig": {
                "Binds": ["/var/data/project:/data:rw", "/tmp/cache:/cache:rw"]
            },
        }

        tracker = tracker_module.ContainerOwnerTracker()
        username, uid, method = tracker._detect_owner(container_data)

        assert method == "unknown"
