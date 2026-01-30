# Testing Patterns

**Analysis Date:** 2026-01-26

## Test Framework

**Runner:**
- pytest (configured in `testing/pytest.ini`)
- Version: Latest compatible with Python 3.10+
- Config file: `/opt/ds01-infra/testing/pytest.ini`

**Assertion Library:**
- pytest built-in assertions (no external library needed)
- `assert result.returncode == 0`
- `assert hasattr(obj, "method_name")`

**Run Commands:**
```bash
# Run all tests in testing/ directory
pytest /opt/ds01-infra/testing/

# Run only unit tests
pytest /opt/ds01-infra/testing/ -m unit

# Run component tests (skip requires_docker tests if Docker unavailable)
pytest /opt/ds01-infra/testing/component

# Watch mode (requires pytest-watch, not installed by default)
# pytest-watch /opt/ds01-infra/testing/

# Coverage (requires pytest-cov)
# pytest /opt/ds01-infra/testing/ --cov=scripts --cov-report=html
```

## Test File Organization

**Location:**
- Co-located with code: NOT used in DS01
- Separate directory structure: `testing/{unit,component,integration,e2e}/`

**Naming:**
- Test files: `test_*.py` (e.g., `test_gpu_state_reader.py`)
- Test classes: `Test*` (e.g., `class TestGPUStateReaderExecution`)
- Test methods: `test_*` (e.g., `def test_script_exists()`)

**Structure:**
```
testing/
├── conftest.py                          # Shared fixtures (all tests)
├── unit/                                # Fast, isolated, mocked
│   ├── conftest.py
│   ├── lib/
│   │   ├── conftest.py                 # Library-specific fixtures
│   │   ├── test_ds01_core.py
│   │   └── test_username_utils.py
│   └── docker/
│       └── test_get_resource_limits.py
├── component/                           # Single component + real deps
│   ├── test_gpu_state_reader.py
│   ├── test_gpu_availability_checker.py
│   ├── test_dashboard_ownership.py
│   ├── test_bare_metal_detector.py
│   └── test_health_check.py
├── integration/                         # Multiple components together
│   ├── conftest.py
│   ├── test_gpu_allocation_flow.py
│   ├── test_container_lifecycle.py
│   ├── test_container_ownership.py
│   └── test_resource_alerts.sh
├── e2e/                                # Full user workflows (not present)
│   └── (placeholder)
├── pytest.ini                           # Configuration
└── validation/                          # Ad-hoc validation scripts
    └── (not standard pytest tests)
```

## Test Structure

**Suite organization:**
```python
class TestGPUStateReaderExecution:
    """Tests for GPU state reader script execution."""

    GPU_STATE_READER = Path("/opt/ds01-infra/scripts/docker/gpu-state-reader.py")

    @pytest.mark.component
    def test_script_exists(self):
        """GPU state reader script exists."""
        assert self.GPU_STATE_READER.exists()

    @pytest.mark.component
    @pytest.mark.requires_docker
    def test_all_command(self):
        """GPU state reader 'all' command executes."""
        result = subprocess.run(
            ["python3", str(self.GPU_STATE_READER), "all"],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0
```

**Markers for categorization:**
```python
@pytest.mark.unit              # Unit tests (fast, isolated, mocked)
@pytest.mark.component         # Component tests (single component, real deps)
@pytest.mark.integration       # Integration tests (multiple components)
@pytest.mark.e2e               # End-to-end tests (full workflows)
@pytest.mark.slow              # Slow tests (can skip with -m "not slow")
@pytest.mark.requires_docker   # Requires Docker daemon (auto-skip if unavailable)
@pytest.mark.requires_gpu      # Requires GPU/nvidia-smi (auto-skip if unavailable)
@pytest.mark.requires_root     # Requires root privileges (auto-skip if not root)
```

**Patterns:**

Setup and teardown:
```python
@pytest.fixture
def sample_gpu_state() -> Dict[str, Any]:
    """Return sample GPU allocator state."""
    return {
        "gpus": {
            "0": {"type": "physical_gpu", "containers": []},
            "1": {"type": "physical_gpu", "containers": []}
        }
    }

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test artifacts."""
    tmp = Path(tempfile.mkdtemp(prefix="ds01-test-"))
    yield tmp  # Test runs here
    shutil.rmtree(tmp, ignore_errors=True)  # Cleanup
```

Assertion patterns:
```python
# File existence
assert self.GPU_STATE_READER.exists()

# Process exit codes
assert result.returncode == 0

# Object attributes
assert hasattr(reader, "_detect_interface")

# String matching
assert "Usage" in result.stdout or "Commands" in result.stdout

# JSON parsing
data = json.loads(result.stdout)
assert isinstance(data, dict)
```

## Mocking

**Framework:**
- `unittest.mock` from Python standard library
- `MagicMock` for creating mock objects
- `patch` as context manager or decorator

**Patterns (from `conftest.py`):**

Docker client mocking:
```python
@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    mock = MagicMock()
    mock.containers.list.return_value = []
    mock.info.return_value = {
        "CgroupDriver": "systemd",
        "CgroupParent": "ds01.slice"
    }
    return mock
```

nvidia-smi mocking:
```python
@pytest.fixture
def mock_nvidia_smi():
    """Create a mock nvidia-smi response."""
    def _mock_nvidia_smi(query_type="count"):
        responses = {
            "count": "4",
            "gpu": "0, NVIDIA A100-SXM4-40GB, 40960 MiB\n1, ...",
            "mig": "GPU 0: No MIG devices found\n..."
        }
        return responses.get(query_type, "")
    return _mock_nvidia_smi
```

subprocess mocking:
```python
@pytest.fixture
def mock_subprocess_run():
    """Fixture to mock subprocess.run calls."""
    with patch("subprocess.run") as mock:
        yield mock
```

**What to mock:**
- External system calls: Docker, nvidia-smi, getent
- File I/O when testing logic, not when testing file operations
- Network calls (not present in this codebase)

**What NOT to mock:**
- The actual Python libraries being tested (`ds01_core`, `username_utils`)
- Logic you're trying to verify
- Use real files in temp directories instead of mocking file operations

## Fixtures and Factories

**Test data (from `conftest.py`):**

Sample resource limits:
```python
@pytest.fixture
def sample_resource_limits() -> Dict[str, Any]:
    return {
        "defaults": {
            "max_mig_instances": 1,
            "max_cpus": 8,
            "memory": "32g",
            "idle_timeout": "48h",
            "max_runtime": "168h"
        },
        "groups": {
            "students": {
                "max_mig_instances": 1,
                "max_cpus": 8,
                "memory": "32g",
                "members": ["student1", "student2"]
            }
        }
    }
```

Temporary files:
```python
@pytest.fixture
def temp_config_file(temp_dir, sample_resource_limits) -> Path:
    """Create a temporary resource-limits.yaml file."""
    import yaml
    config_file = temp_dir / "resource-limits.yaml"
    with open(config_file, "w") as f:
        yaml.safe_dump(sample_resource_limits, f)
    return config_file
```

Sample Docker container:
```python
@pytest.fixture
def sample_docker_container() -> Dict[str, Any]:
    return {
        "Id": "abc123def456",
        "Name": "/project-a._.1001",
        "Config": {
            "Labels": {
                "ds01.interface": "orchestration",
                "ds01.user": "student1"
            }
        },
        "HostConfig": {
            "CgroupParent": "ds01-students-student1.slice",
            "DeviceRequests": [{"Driver": "nvidia", "DeviceIDs": ["0"]}]
        }
    }
```

**Location:**
- Global fixtures: `testing/conftest.py`
- Test-specific fixtures: `testing/{type}/conftest.py` (e.g., `testing/component/conftest.py`)
- Library-specific fixtures: `testing/unit/lib/conftest.py`

## Coverage

**Requirements:**
- Not enforced (no `--cov-fail-under` setting)
- Can be run manually with pytest-cov

**View coverage:**
```bash
# Install pytest-cov
pip install pytest-cov

# Run with coverage
pytest /opt/ds01-infra/testing/ --cov=scripts --cov-report=html

# View in browser (if running locally)
open htmlcov/index.html
```

## Test Types

**Unit tests:**
- Location: `testing/unit/`
- Scope: Single function or class in isolation
- Dependencies: All mocked except the unit under test
- Speed: Fast (< 100ms per test)
- Example: `test_parse_duration()` in `test_ds01_core.py`

**Component tests:**
- Location: `testing/component/`
- Scope: Single script/module with real dependencies (but no production data)
- Dependencies: Real imports, real Docker API, no actual containers created
- Speed: Medium (< 5s per test)
- Example: `test_gpu_state_reader_script_exists()` - verifies syntax and runs command
- Auto-skip: If `@pytest.mark.requires_docker` and Docker unavailable

**Integration tests:**
- Location: `testing/integration/`
- Scope: Multiple components interacting (GPU allocator + state reader + config)
- Dependencies: Real imports, real files, real Docker (if available)
- Speed: Slow (< 30s per test)
- Example: `test_allocator_loads_config()` - verifies allocator can read config AND state reader works
- Auto-skip: If requires Docker/GPU and not available

**E2E tests:**
- Location: `testing/e2e/` (placeholder, not used yet)
- Scope: Complete user workflows (create project → launch container → allocate GPU)
- Dependencies: Everything real, full system running
- Speed: Very slow (minutes)
- Not implemented yet

## Common Patterns

**Async testing (not used):**
- No async/await in this codebase
- All tests are synchronous

**Error testing:**
```python
def test_parse_duration_invalid_input(self):
    """parse_duration returns 0 for invalid input."""
    result = parse_duration("invalid")
    assert result == 0

def test_parse_duration_special_values(self):
    """parse_duration returns -1 for no-limit values."""
    for value in ["null", "none", "never", "indefinite"]:
        assert parse_duration(value) == -1
```

**Subprocess testing:**
```python
@pytest.mark.component
@pytest.mark.requires_docker
def test_gpu_state_reader_all_command(self):
    """GPU state reader 'all' command executes."""
    result = subprocess.run(
        ["python3", str(self.GPU_STATE_READER), "all"],
        capture_output=True,
        text=True,
        timeout=30
    )
    assert result.returncode == 0
```

**Context managers and fixtures:**
```python
@pytest.fixture
def orchestration_context():
    """Set up orchestration context environment."""
    original = os.environ.get("DS01_CONTEXT")
    os.environ["DS01_CONTEXT"] = "orchestration"
    yield
    if original is None:
        os.environ.pop("DS01_CONTEXT", None)
    else:
        os.environ["DS01_CONTEXT"] = original
```

**Bash script testing (from `testing/unit/lib/conftest.py`):**
```python
def run_bash_script(script_path: Path, *args, env=None, timeout=30) -> subprocess.CompletedProcess:
    """Run a bash script and return the result."""
    return subprocess.run(
        [str(script_path)] + list(args),
        capture_output=True,
        text=True,
        env=script_env,
        timeout=timeout
    )

def source_and_run(library_path: Path, code: str, env=None) -> subprocess.CompletedProcess:
    """Source a bash library and run code."""
    full_code = f'''
    source "{library_path}"
    {code}
    '''
    return run_bash_code(full_code, env=env)
```

## Auto-Skip Logic

**From `conftest.py`:**

Tests are automatically skipped if their environment requirements aren't met:
```python
def pytest_collection_modifyitems(config, items):
    """Auto-skip tests based on environment capabilities."""

    has_docker = _check_docker()
    has_gpu = _check_gpu()
    is_root = os.geteuid() == 0

    for item in items:
        if "requires_docker" in item.keywords and not has_docker:
            item.add_marker(pytest.mark.skip(reason="Docker not available"))

        if "requires_gpu" in item.keywords and not has_gpu:
            item.add_marker(pytest.mark.skip(reason="GPU/nvidia-smi not available"))

        if "requires_root" in item.keywords and not is_root:
            item.add_marker(pytest.mark.skip(reason="Requires root"))
```

**Availability checks:**
```python
def _check_docker() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def _check_gpu() -> bool:
    """Check if nvidia-smi is available."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
```

## Test File Examples

**Unit test structure (test_ds01_core.py pattern):**
```python
#!/usr/bin/env python3
"""Unit tests for ds01_core.py"""

import pytest
import sys
sys.path.insert(0, "/opt/ds01-infra/scripts/lib")

from ds01_core import parse_duration, format_duration


class TestParseDuration:
    """Tests for parse_duration function."""

    def test_parse_hours(self):
        """parse_duration handles hours."""
        assert parse_duration("2h") == 7200

    def test_parse_fractional(self):
        """parse_duration handles fractional values."""
        assert parse_duration("0.5h") == 1800

    def test_parse_special_values(self):
        """parse_duration returns -1 for no-limit values."""
        for value in ["null", "none", "never"]:
            assert parse_duration(value) == -1
```

**Component test structure (test_gpu_state_reader.py pattern):**
```python
#!/usr/bin/env python3
"""Component tests for gpu-state-reader.py"""

import pytest
import subprocess
from pathlib import Path


class TestGPUStateReaderExecution:
    """Tests for GPU state reader script execution."""

    GPU_STATE_READER = Path("/opt/ds01-infra/scripts/docker/gpu-state-reader.py")

    @pytest.mark.component
    def test_script_exists(self):
        """GPU state reader script exists."""
        assert self.GPU_STATE_READER.exists()

    @pytest.mark.component
    @pytest.mark.requires_docker
    def test_all_command(self):
        """GPU state reader 'all' command executes."""
        result = subprocess.run(
            ["python3", str(self.GPU_STATE_READER), "all"],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0
```

---

*Testing analysis: 2026-01-26*
