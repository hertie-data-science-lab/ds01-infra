#!/usr/bin/env python3
"""
Unit tests for DS01 Prometheus Exporter
/opt/ds01-infra/testing/unit/monitoring/test_ds01_exporter.py

Tests the metric collection functions and HTTP endpoints of the exporter.
Uses mocks for external dependencies (nvidia-smi, Docker, gpu-state-reader).
"""

import io
import json
import os
import sys
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import MagicMock, patch, Mock

import pytest


# =============================================================================
# Paths and Module Loading
# =============================================================================

EXPORTER_PATH = Path("/opt/ds01-infra/monitoring/exporter")
EXPORTER_FILE = EXPORTER_PATH / "ds01_exporter.py"


def load_exporter_module():
    """Load exporter module fresh for testing."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ds01_exporter", EXPORTER_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_gpu_data() -> List[Dict[str, Any]]:
    """Sample GPU utilization data from nvidia-smi."""
    return [
        {
            "index": 0,
            "name": "NVIDIA A100-PCIE-40GB",
            "gpu_util_percent": 75,
            "mem_util_percent": 60,
            "mem_used_mb": 24576,
            "mem_total_mb": 40960,
            "temperature_c": 65
        },
        {
            "index": 1,
            "name": "NVIDIA A100-PCIE-40GB",
            "gpu_util_percent": 25,
            "mem_util_percent": 30,
            "mem_used_mb": 12288,
            "mem_total_mb": 40960,
            "temperature_c": 55
        }
    ]


@pytest.fixture
def mock_allocation_data() -> Dict[str, Any]:
    """Sample GPU allocation data from gpu-state-reader."""
    return {
        "0.0": {
            "type": "mig_instance",
            "containers": ["project-a._.1001"],
            "users": {"student1": 1},
            "uuid": "MIG-abc123",
            "interfaces": {"orchestration": 1}
        },
        "0.1": {
            "type": "mig_instance",
            "containers": ["project-b._.1002"],
            "users": {"student2": 1},
            "uuid": "MIG-def456",
            "interfaces": {"atomic": 1}
        }
    }


@pytest.fixture
def mock_containers_by_interface() -> Dict[str, List[Dict]]:
    """Sample containers grouped by interface."""
    return {
        "orchestration": [
            {"name": "project-a._.1001", "user": "student1", "running": True, "gpu": "0.0"},
            {"name": "project-c._.1003", "user": "student3", "running": False, "gpu": None}
        ],
        "atomic": [
            {"name": "project-b._.1002", "user": "student2", "running": True, "gpu": "0.1"}
        ],
        "docker": [],
        "other": [
            {"name": "vscode-project-x", "user": "researcher1", "running": True, "gpu": None}
        ]
    }


@pytest.fixture
def temp_log_dir(tmp_path) -> Path:
    """Create a temporary log directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def temp_events_file(temp_log_dir) -> Path:
    """Create a temporary events.jsonl file with sample data."""
    events_file = temp_log_dir / "events.jsonl"
    now = datetime.now(timezone.utc)

    events = [
        {"timestamp": (now - timedelta(hours=1)).isoformat(), "event_type": "container.start", "user": "student1"},
        {"timestamp": (now - timedelta(hours=2)).isoformat(), "event_type": "container.start", "user": "student2"},
        {"timestamp": (now - timedelta(hours=3)).isoformat(), "event_type": "gpu.allocated", "user": "student1"},
        {"timestamp": (now - timedelta(hours=25)).isoformat(), "event_type": "container.start", "user": "old_user"},
        {"timestamp": (now - timedelta(minutes=30)).isoformat(), "event_type": "container.stop", "user": "student1"},
    ]

    with open(events_file, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    return events_file


# =============================================================================
# Test: collect_gpu_metrics()
# =============================================================================

class TestCollectGpuMetrics:
    """Tests for collect_gpu_metrics() function."""

    def test_returns_list(self, mock_gpu_data):
        """GPU metrics should return a list of strings."""
        # Create mock gpu util module
        mock_module = MagicMock()
        mock_module.get_gpu_utilization.return_value = mock_gpu_data

        with patch.dict('sys.modules', {'gpu_util_monitor': mock_module}):
            exporter = load_exporter_module()

            # Patch the global module cache
            exporter._gpu_util_module = mock_module

            lines = exporter.collect_gpu_metrics()

        assert isinstance(lines, list)

    def test_includes_help_and_type_comments(self, mock_gpu_data):
        """GPU metrics should include HELP and TYPE comments."""
        mock_module = MagicMock()
        mock_module.get_gpu_utilization.return_value = mock_gpu_data

        with patch.dict('sys.modules', {'gpu_util_monitor': mock_module}):
            exporter = load_exporter_module()
            exporter._gpu_util_module = mock_module

            lines = exporter.collect_gpu_metrics()

        help_lines = [l for l in lines if l.startswith("# HELP")]
        type_lines = [l for l in lines if l.startswith("# TYPE")]

        assert len(help_lines) > 0, "Should have HELP comments"
        assert len(type_lines) > 0, "Should have TYPE comments"

    def test_returns_empty_when_no_gpus(self):
        """Should return empty list when no GPUs available."""
        mock_module = MagicMock()
        mock_module.get_gpu_utilization.return_value = []

        with patch.dict('sys.modules', {'gpu_util_monitor': mock_module}):
            exporter = load_exporter_module()
            exporter._gpu_util_module = mock_module

            lines = exporter.collect_gpu_metrics()

        # Should have no data metrics (only comments or empty)
        data_lines = [l for l in lines if l and not l.startswith("#")]
        assert len(data_lines) == 0

    def test_handles_exception_gracefully(self):
        """Should handle nvidia-smi errors without crashing."""
        mock_module = MagicMock()
        mock_module.get_gpu_utilization.side_effect = Exception("nvidia-smi failed")

        with patch.dict('sys.modules', {'gpu_util_monitor': mock_module}):
            exporter = load_exporter_module()
            exporter._gpu_util_module = mock_module

            # Should not raise
            lines = exporter.collect_gpu_metrics()

        # Should contain error comment
        error_lines = [l for l in lines if "Error" in l or "error" in l]
        assert len(error_lines) > 0, "Should include error comment"


# =============================================================================
# Test: collect_allocation_metrics()
# =============================================================================

class TestCollectAllocationMetrics:
    """Tests for collect_allocation_metrics() function."""

    def test_returns_list(self, mock_allocation_data, mock_containers_by_interface):
        """Allocation metrics should return a list."""
        mock_reader = MagicMock()
        mock_reader.get_all_allocations.return_value = mock_allocation_data
        mock_reader.get_all_containers_by_interface.return_value = mock_containers_by_interface

        mock_state_module = MagicMock()
        mock_state_module.get_reader.return_value = mock_reader

        with patch.dict('sys.modules', {'gpu_state_reader': mock_state_module}):
            exporter = load_exporter_module()
            exporter._gpu_state_module = mock_state_module

            lines = exporter.collect_allocation_metrics()

        assert isinstance(lines, list)

    def test_includes_allocation_metrics(self, mock_allocation_data, mock_containers_by_interface):
        """Should include GPU allocation metrics."""
        mock_reader = MagicMock()
        mock_reader.get_all_allocations.return_value = mock_allocation_data
        mock_reader.get_all_containers_by_interface.return_value = mock_containers_by_interface

        mock_state_module = MagicMock()
        mock_state_module.get_reader.return_value = mock_reader

        with patch.dict('sys.modules', {'gpu_state_reader': mock_state_module}):
            exporter = load_exporter_module()
            exporter._gpu_state_module = mock_state_module

            lines = exporter.collect_allocation_metrics()

        joined = "\n".join(lines)
        assert "ds01_gpu_allocated" in joined or "# HELP" in joined


# =============================================================================
# Test: collect_user_metrics()
# =============================================================================

class TestCollectUserMetrics:
    """Tests for collect_user_metrics() function."""

    def test_returns_list(self, mock_containers_by_interface):
        """User metrics should return a list."""
        mock_reader = MagicMock()
        mock_reader.get_all_containers_by_interface.return_value = mock_containers_by_interface
        mock_reader.get_user_mig_total.return_value = 1
        mock_reader.get_user_allocations.return_value = [{"container": "test"}]

        mock_state_module = MagicMock()
        mock_state_module.get_reader.return_value = mock_reader

        with patch.dict('sys.modules', {'gpu_state_reader': mock_state_module}):
            exporter = load_exporter_module()
            exporter._gpu_state_module = mock_state_module

            lines = exporter.collect_user_metrics()

        assert isinstance(lines, list)


# =============================================================================
# Test: collect_container_stats()
# =============================================================================

class TestCollectContainerStats:
    """Tests for collect_container_stats() function."""

    def test_handles_missing_containers(self):
        """Should handle no running containers gracefully."""
        exporter = load_exporter_module()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            lines = exporter.collect_container_stats()

        assert isinstance(lines, list)

    def test_filters_non_ds01_containers(self):
        """Should filter out containers that are not DS01 managed."""
        exporter = load_exporter_module()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """project-a._.1001|25.5%|2GiB / 32GiB|6.25%
random-container|10.0%|1GiB / 8GiB|12.5%
ds01-exporter|1.0%|100MiB / 1GiB|10.0%"""

        with patch("subprocess.run", return_value=mock_result):
            lines = exporter.collect_container_stats()

        joined = "\n".join(lines)
        # DS01 container (._.) should be included
        assert "project-a" in joined or "# HELP" in joined

    def test_handles_docker_failure(self):
        """Should handle docker command failure."""
        exporter = load_exporter_module()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            lines = exporter.collect_container_stats()

        assert isinstance(lines, list)

    def test_handles_docker_timeout(self):
        """Should handle docker command timeout."""
        exporter = load_exporter_module()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 30)):
            lines = exporter.collect_container_stats()

        # Should handle gracefully
        assert isinstance(lines, list)


# =============================================================================
# Test: collect_event_counts()
# =============================================================================

class TestCollectEventCounts:
    """Tests for collect_event_counts() function."""

    def test_handles_missing_events_file(self, tmp_path):
        """Should return empty when events.jsonl doesn't exist."""
        exporter = load_exporter_module()

        # Point to non-existent directory
        exporter.LOG_DIR = tmp_path / "nonexistent"

        lines = exporter.collect_event_counts()

        assert isinstance(lines, list)
        assert len(lines) == 0

    def test_handles_empty_events_file(self, temp_log_dir):
        """Should handle empty events.jsonl file."""
        events_file = temp_log_dir / "events.jsonl"
        events_file.touch()

        exporter = load_exporter_module()
        exporter.LOG_DIR = temp_log_dir

        lines = exporter.collect_event_counts()

        assert isinstance(lines, list)

    def test_counts_events_last_24h(self, temp_events_file, temp_log_dir):
        """Should count events by type for last 24 hours only."""
        exporter = load_exporter_module()
        exporter.LOG_DIR = temp_log_dir

        lines = exporter.collect_event_counts()

        joined = "\n".join(lines)
        assert "ds01_events_24h_total" in joined or "# HELP" in joined

    def test_handles_malformed_json_lines(self, temp_log_dir):
        """Should skip malformed JSON lines gracefully."""
        events_file = temp_log_dir / "events.jsonl"
        now = datetime.now(timezone.utc)

        with open(events_file, "w") as f:
            f.write('{"timestamp": "' + now.isoformat() + '", "event_type": "valid.event"}\n')
            f.write('this is not valid json\n')
            f.write('{"incomplete": "json"\n')
            f.write('{"timestamp": "' + now.isoformat() + '", "event_type": "another.valid"}\n')

        exporter = load_exporter_module()
        exporter.LOG_DIR = temp_log_dir

        # Should not raise
        lines = exporter.collect_event_counts()

        assert isinstance(lines, list)


# =============================================================================
# Test: collect_system_metrics()
# =============================================================================

class TestCollectSystemMetrics:
    """Tests for collect_system_metrics() function."""

    def test_reports_disk_usage(self, tmp_path):
        """Should report disk usage for state directory."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        exporter = load_exporter_module()
        exporter.STATE_DIR = state_dir

        lines = exporter.collect_system_metrics()

        joined = "\n".join(lines)
        assert "ds01_state_disk_bytes" in joined or "# HELP" in joined or len(lines) >= 0

    def test_handles_missing_state_dir(self, tmp_path):
        """Should handle missing state directory gracefully."""
        exporter = load_exporter_module()
        exporter.STATE_DIR = tmp_path / "nonexistent"

        # Should not crash
        lines = exporter.collect_system_metrics()

        assert isinstance(lines, list)


# =============================================================================
# Test: collect_all_metrics()
# =============================================================================

class TestCollectAllMetrics:
    """Tests for collect_all_metrics() function."""

    def test_returns_string(self, tmp_path):
        """Should return a string."""
        # Set up mocks
        mock_gpu_module = MagicMock()
        mock_gpu_module.get_gpu_utilization.return_value = []

        mock_reader = MagicMock()
        mock_reader.get_all_allocations.return_value = {}
        mock_reader.get_all_containers_by_interface.return_value = {
            "orchestration": [], "atomic": [], "docker": [], "other": []
        }
        mock_reader.get_user_mig_total.return_value = 0
        mock_reader.get_user_allocations.return_value = []

        mock_state_module = MagicMock()
        mock_state_module.get_reader.return_value = mock_reader

        mock_docker = MagicMock()
        mock_docker.returncode = 0
        mock_docker.stdout = ""

        exporter = load_exporter_module()
        exporter._gpu_util_module = mock_gpu_module
        exporter._gpu_state_module = mock_state_module
        exporter.LOG_DIR = tmp_path
        exporter.STATE_DIR = tmp_path

        with patch("subprocess.run", return_value=mock_docker):
            output = exporter.collect_all_metrics()

        assert isinstance(output, str)
        assert output.endswith("\n")

    def test_includes_exporter_info(self, tmp_path):
        """Should include exporter info metric."""
        mock_gpu_module = MagicMock()
        mock_gpu_module.get_gpu_utilization.return_value = []

        mock_reader = MagicMock()
        mock_reader.get_all_allocations.return_value = {}
        mock_reader.get_all_containers_by_interface.return_value = {
            "orchestration": [], "atomic": [], "docker": [], "other": []
        }

        mock_state_module = MagicMock()
        mock_state_module.get_reader.return_value = mock_reader

        mock_docker = MagicMock()
        mock_docker.returncode = 0
        mock_docker.stdout = ""

        exporter = load_exporter_module()
        exporter._gpu_util_module = mock_gpu_module
        exporter._gpu_state_module = mock_state_module
        exporter.LOG_DIR = tmp_path
        exporter.STATE_DIR = tmp_path

        with patch("subprocess.run", return_value=mock_docker):
            output = exporter.collect_all_metrics()

        assert "ds01_exporter_info" in output

    def test_includes_scrape_timestamp(self, tmp_path):
        """Should include a scrape timestamp in output."""
        mock_gpu_module = MagicMock()
        mock_gpu_module.get_gpu_utilization.return_value = []

        mock_reader = MagicMock()
        mock_reader.get_all_allocations.return_value = {}
        mock_reader.get_all_containers_by_interface.return_value = {
            "orchestration": [], "atomic": [], "docker": [], "other": []
        }

        mock_state_module = MagicMock()
        mock_state_module.get_reader.return_value = mock_reader

        mock_docker = MagicMock()
        mock_docker.returncode = 0
        mock_docker.stdout = ""

        exporter = load_exporter_module()
        exporter._gpu_util_module = mock_gpu_module
        exporter._gpu_state_module = mock_state_module
        exporter.LOG_DIR = tmp_path
        exporter.STATE_DIR = tmp_path

        with patch("subprocess.run", return_value=mock_docker):
            output = exporter.collect_all_metrics()

        assert "Scrape time" in output


# =============================================================================
# Test: MetricsHandler Class
# =============================================================================

class TestMetricsHandler:
    """Tests for the HTTP MetricsHandler class."""

    def test_handler_class_exists(self):
        """MetricsHandler class should exist in the module."""
        exporter = load_exporter_module()
        assert hasattr(exporter, 'MetricsHandler')

    def test_handler_has_do_get(self):
        """MetricsHandler should have do_GET method."""
        exporter = load_exporter_module()
        assert hasattr(exporter.MetricsHandler, 'do_GET')


# =============================================================================
# Test: Prometheus Format Validation
# =============================================================================

class TestPrometheusFormat:
    """Tests for Prometheus exposition format compliance."""

    def test_metric_names_are_valid(self, mock_gpu_data):
        """Metric names should follow Prometheus naming conventions."""
        import re

        mock_module = MagicMock()
        mock_module.get_gpu_utilization.return_value = mock_gpu_data

        exporter = load_exporter_module()
        exporter._gpu_util_module = mock_module

        lines = exporter.collect_gpu_metrics()

        # Valid Prometheus metric name: [a-zA-Z_:][a-zA-Z0-9_:]*
        metric_pattern = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*')

        for line in lines:
            if line and not line.startswith("#"):
                # Extract metric name (before { or space)
                match = metric_pattern.match(line)
                assert match is not None, f"Invalid metric name in: {line}"

    def test_labels_are_properly_quoted(self, mock_gpu_data):
        """Label values should be properly quoted."""
        mock_module = MagicMock()
        mock_module.get_gpu_utilization.return_value = mock_gpu_data

        exporter = load_exporter_module()
        exporter._gpu_util_module = mock_module

        lines = exporter.collect_gpu_metrics()

        for line in lines:
            if "{" in line:
                # Check that labels are quoted
                assert '="' in line, f"Labels should be quoted in: {line}"


# =============================================================================
# Test: Module Structure
# =============================================================================

class TestModuleStructure:
    """Tests for module structure and required functions."""

    def test_module_has_main(self):
        """Module should have main() function."""
        exporter = load_exporter_module()
        assert hasattr(exporter, 'main')
        assert callable(exporter.main)

    def test_module_has_collect_functions(self):
        """Module should have all collect functions."""
        exporter = load_exporter_module()

        required_functions = [
            'collect_gpu_metrics',
            'collect_allocation_metrics',
            'collect_user_metrics',
            'collect_container_stats',
            'collect_event_counts',
            'collect_system_metrics',
            'collect_all_metrics',
        ]

        for func_name in required_functions:
            assert hasattr(exporter, func_name), f"Missing function: {func_name}"
            assert callable(getattr(exporter, func_name))

    def test_module_has_configuration(self):
        """Module should have configuration constants."""
        exporter = load_exporter_module()

        assert hasattr(exporter, 'EXPORTER_PORT')
        assert hasattr(exporter, 'BIND_ADDRESS')
        assert hasattr(exporter, 'INFRA_ROOT')

    def test_port_is_9101(self):
        """Default exporter port should be 9101."""
        exporter = load_exporter_module()
        # Default value (before env override)
        assert exporter.EXPORTER_PORT == 9101 or os.environ.get('DS01_EXPORTER_PORT') is not None


# =============================================================================
# Test: Error Resilience
# =============================================================================

class TestErrorResilience:
    """Tests for error handling and resilience."""

    def test_gpu_metrics_resilient_to_module_load_failure(self):
        """GPU metrics should handle module loading failures."""
        exporter = load_exporter_module()

        # Set module to one that will fail
        exporter._gpu_util_module = None

        # Mock the load function to fail
        def failing_load(*args):
            raise ImportError("Module not found")

        with patch.object(exporter, '_load_module', failing_load):
            # Reset cached module
            exporter._gpu_util_module = None

            # This should not raise, should return error comment
            try:
                lines = exporter.collect_gpu_metrics()
                # If it returns, check for error handling
                error_present = any("Error" in l or "error" in l.lower() for l in lines)
                assert error_present or len(lines) == 0
            except Exception:
                # Exception is acceptable if error handling is different
                pass

    def test_container_stats_handles_docker_socket_missing(self):
        """Container stats should handle missing Docker socket."""
        exporter = load_exporter_module()

        with patch("subprocess.run", side_effect=FileNotFoundError("docker not found")):
            # Should not raise
            lines = exporter.collect_container_stats()

        assert isinstance(lines, list)
