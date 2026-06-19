#!/usr/bin/env python3
"""
Integration Tests: GPU State Reader
Tests gpu-state-reader.py with real Docker (when available)
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/opt/ds01-infra/scripts/docker")


class TestGPUStateReaderExecution:
    """Tests for GPU state reader script execution."""

    GPU_STATE_READER = Path("/opt/ds01-infra/scripts/docker/gpu-state-reader.py")

    @pytest.mark.integration
    def test_script_exists(self):
        """GPU state reader script exists."""
        assert self.GPU_STATE_READER.exists()

    @pytest.mark.integration
    @pytest.mark.xfail(
        reason="py_compile fails due to read-only __pycache__ permissions in test environment"
    )
    def test_script_syntax(self):
        """GPU state reader has valid Python syntax."""
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(self.GPU_STATE_READER)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    @pytest.mark.integration
    @pytest.mark.requires_docker
    def test_all_command(self):
        """GPU state reader 'all' command executes."""
        result = subprocess.run(
            ["python3", str(self.GPU_STATE_READER), "all"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should not crash (may have no containers)
        assert result.returncode == 0

    @pytest.mark.integration
    @pytest.mark.requires_docker
    def test_by_interface_command(self):
        """GPU state reader 'by-interface' command executes."""
        result = subprocess.run(
            ["python3", str(self.GPU_STATE_READER), "by-interface"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

    @pytest.mark.integration
    def test_usage_shown(self):
        """GPU state reader shows usage when called with no args."""
        result = subprocess.run(
            ["python3", str(self.GPU_STATE_READER)], capture_output=True, text=True, timeout=10
        )
        # Should show usage
        assert "Usage" in result.stdout or "Commands" in result.stdout


class TestGPUStateReaderClass:
    """Tests for GPUStateReader class methods."""

    @pytest.fixture
    def reader(self):
        """Create GPUStateReader instance with mocked docker."""
        try:
            # Import with careful handling of dependencies
            spec = __import__("importlib.util").util.spec_from_file_location(
                "gpu_state_reader", "/opt/ds01-infra/scripts/docker/gpu-state-reader.py"
            )
            module = __import__("importlib.util").util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.GPUStateReader()
        except Exception as e:
            pytest.skip(f"Could not import GPUStateReader: {e}")

    @pytest.mark.integration
    def test_interface_detection_method_exists(self, reader):
        """GPUStateReader has _detect_interface method."""
        assert hasattr(reader, "_detect_interface")

    @pytest.mark.integration
    def test_mig_mapping_method_exists(self, reader):
        """GPUStateReader has _get_mig_uuid_to_slot_mapping method."""
        assert hasattr(reader, "_get_mig_uuid_to_slot_mapping")

    @pytest.mark.integration
    def test_cgroup_user_extraction_method_exists(self, reader):
        """GPUStateReader has _extract_user_from_cgroup method."""
        assert hasattr(reader, "_extract_user_from_cgroup")


class TestGPUStateReaderWithMockDocker:
    """Tests with mocked Docker responses."""

    @pytest.fixture
    def mock_container_data(self, sample_docker_container):
        """Use sample container data from conftest."""
        return sample_docker_container

    @pytest.mark.integration
    def test_detect_orchestration_interface(self, mock_container_data):
        """Detect orchestration interface from labels."""
        mock_container_data["Config"]["Labels"]["ds01.interface"] = "orchestration"

        labels = mock_container_data["Config"]["Labels"]
        mock_container_data["Name"].lstrip("/")

        # Simulate detection logic
        if labels.get("ds01.interface") == "orchestration":
            interface = "orchestration"
        else:
            interface = "atomic"

        assert interface == "orchestration"

    @pytest.mark.integration
    def test_detect_atomic_interface(self, mock_container_data):
        """Detect atomic interface from AIME naming."""
        mock_container_data["Config"]["Labels"].pop("ds01.interface", None)
        mock_container_data["Name"] = "/project-a._.1001"

        name = mock_container_data["Name"].lstrip("/")

        # AIME naming convention
        if "._." in name:
            interface = "atomic"
        else:
            interface = "docker"

        assert interface == "atomic"

    @pytest.mark.integration
    def test_extract_gpu_from_device_requests(self, mock_container_data):
        """Extract GPU ID from DeviceRequests."""
        device_requests = mock_container_data["HostConfig"]["DeviceRequests"]

        gpu_ids = []
        for req in device_requests:
            if req.get("Driver") == "nvidia":
                gpu_ids.extend(req.get("DeviceIDs", []))

        assert "0" in gpu_ids

    @pytest.mark.integration
    def test_extract_user_from_cgroup_path(self, mock_container_data):
        """Extract user from cgroup parent path."""
        import re

        cgroup = mock_container_data["HostConfig"]["CgroupParent"]

        # Pattern: ds01-{group}-{user}.slice
        match = re.match(r"ds01-([^-]+)-(.+)\.slice", cgroup)
        if match:
            user = match.group(2)
        else:
            user = None

        assert user == "student1"


class TestGPUEquivalents:
    """Unit tests for the GPU-equivalent (gpueq) weight helpers.

    These cover the shared weight math (also used by the exporter PR) without
    touching Docker: get_user_allocations is mocked with synthetic full-GPU and
    MIG profiles.
    """

    @pytest.fixture
    def reader(self, infra_root):
        """Load GPUStateReader from the infra tree under test."""
        import importlib.util

        path = infra_root / "scripts" / "docker" / "gpu-state-reader.py"
        if not path.exists():
            pytest.skip(f"gpu-state-reader.py not found at {path}")
        spec = importlib.util.spec_from_file_location("gpu_state_reader_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        instance = module.GPUStateReader()
        if not hasattr(instance, "get_user_gpu_equivalents"):
            pytest.skip("get_user_gpu_equivalents not present (pre-gpueq build)")
        # Pin slices-per-GPU to 7 so the test is independent of host nvidia-smi.
        instance._slices_per_gpu = lambda: 7
        return instance

    @pytest.mark.integration
    def test_compute_slice_parsing(self, reader):
        """Leading 'Ng' of a MIG profile gives the compute slice count."""
        assert reader._parse_mig_compute_slices("2g.20gb") == 2
        assert reader._parse_mig_compute_slices("1g.10gb") == 1
        assert reader._parse_mig_compute_slices("3g.40gb") == 3
        assert reader._parse_mig_compute_slices("") == 0
        assert reader._parse_mig_compute_slices(None) == 0

    @pytest.mark.integration
    def test_full_gpu_compute_fraction_is_one(self, reader):
        """A full GPU slot weighs exactly 1.0 gpueq."""
        assert reader.get_slot_compute_fraction("0") == 1.0
        assert reader.get_slot_compute_fraction("3") == 1.0

    @pytest.mark.integration
    def test_mig_compute_fraction_is_slice_share(self, reader):
        """A MIG slot weighs its compute slices over the GPU's total slices."""
        assert reader.get_slot_compute_fraction("1.0", "2g.20gb") == pytest.approx(2 / 7)
        assert reader.get_slot_compute_fraction("1.1", "1g.10gb") == pytest.approx(1 / 7)

    @pytest.mark.integration
    def test_full_gpu_user_equivalents_equal_gpu_count(self, reader):
        """For full-GPU users, gpueq equals the distinct GPU count."""
        reader.get_user_allocations = lambda u: [
            {"gpu_slots": ["0"], "gpu_profiles": [""]},
            {"gpu_slots": ["1"], "gpu_profiles": [""]},
        ]
        assert reader.get_user_gpu_equivalents("alice") == 2.0

    @pytest.mark.integration
    def test_mig_user_equivalents_sum_compute_fractions(self, reader):
        """For MIG users, gpueq sums each slot's compute fraction."""
        reader.get_user_allocations = lambda u: [
            {"gpu_slots": ["1.0", "1.1"], "gpu_profiles": ["2g.20gb", "1g.10gb"]},
        ]
        assert reader.get_user_gpu_equivalents("bob") == pytest.approx(3 / 7)

    @pytest.mark.integration
    def test_mixed_user_equivalents(self, reader):
        """Mixed full-GPU + MIG holdings sum correctly."""
        reader.get_user_allocations = lambda u: [
            {"gpu_slots": ["0"], "gpu_profiles": [""]},
            {"gpu_slots": ["2.0"], "gpu_profiles": ["3g.40gb"]},
        ]
        assert reader.get_user_gpu_equivalents("carol") == pytest.approx(1.0 + 3 / 7)

    @pytest.mark.integration
    def test_equivalents_dedupe_distinct_slots(self, reader):
        """A slot referenced by multiple containers counts once."""
        reader.get_user_allocations = lambda u: [
            {"gpu_slots": ["0"], "gpu_profiles": [""]},
            {"gpu_slots": ["0"], "gpu_profiles": [""]},
        ]
        assert reader.get_user_gpu_equivalents("dave") == 1.0


class TestGPUStateReaderInterfaceCategories:
    """Tests for interface category grouping."""

    @pytest.mark.integration
    def test_interface_categories_complete(self):
        """All four interface categories defined."""
        expected = {"orchestration", "atomic", "docker", "other"}

        # These should be constants in the module
        try:
            from gpu_state_reader import (
                INTERFACE_ATOMIC,
                INTERFACE_DOCKER,
                INTERFACE_ORCHESTRATION,
                INTERFACE_OTHER,
            )

            actual = {INTERFACE_ORCHESTRATION, INTERFACE_ATOMIC, INTERFACE_DOCKER, INTERFACE_OTHER}
            assert actual == expected
        except ImportError:
            # Check by reading the file
            content = Path("/opt/ds01-infra/scripts/docker/gpu-state-reader.py").read_text()
            for interface in expected:
                assert f'"{interface}"' in content or f"'{interface}'" in content
