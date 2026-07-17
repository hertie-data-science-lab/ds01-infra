# Testing - DS01 Infrastructure Test Suite

Comprehensive test suite for DS01 GPU container management infrastructure.

## Test Architecture

Tests are organized into three tiers:

```
tests/
├── conftest.py              # Pytest fixtures and shared config
├── pytest.ini               # Pytest configuration
├── run-tests.sh             # Unified test runner
├── unit/                    # Unit tests (fast, isolated, mocked)
│   ├── lib/                 # Library function tests
│   ├── monitoring/          # Monitoring component tests
│   ├── test_resource_limits.py
│   ├── test_gpu_allocator.py
│   └── ...
├── integration/             # Integration tests (real scripts via subprocess)
│   ├── test_container_lifecycle.py
│   ├── test_gpu_allocation_flow.py
│   ├── test_bare_metal_detector.py
│   ├── test_health_check.py
│   └── ...
├── system/                  # System tests (real Docker, GPU, containers)
│   ├── conftest.py          # System test fixtures (config backup, lowered timeouts)
│   ├── test_container_lifecycle.py
│   ├── test_lifecycle_enforcement.py
│   ├── test_container_workflow.py
│   ├── test_multi_gpu_allocation.py
│   ├── test_user_access.py  # role-based (user_role/admin_role) access + perms guards
│   └── test_zz_teardown_verification.py
├── fixtures/                # Test data
│   ├── resource-limits-test.yaml
│   └── mock_gpu_state.json
└── layered-architecture/    # Legacy bash tests
```

## Quick Start

```bash
# Run all tests (excludes system)
./run-tests.sh

# Run specific category
./run-tests.sh unit          # Fast, no external deps
./run-tests.sh integration   # Real scripts, may need Docker
sudo ./run-tests.sh system   # Real system (~15 min, needs root + GPU)

# Skip slow/docker tests
./run-tests.sh -m "not slow"
./run-tests.sh --no-docker

# Verbose output
./run-tests.sh -v unit

# With coverage
./run-tests.sh --coverage
```

## Test Categories

| Category | Tests | Speed | Dependencies | What it Tests |
|----------|-------|-------|--------------|---------------|
| **unit** | 664 | Fast (<1s) | None | Pure logic, mocked deps |
| **integration** | 150 | Medium | Docker (optional) | Real scripts via subprocess |
| **system** | 50 | Slow (~15 min) | Docker + GPU + sudo | Full system with real containers |

Of the 50 system tests, 37 don't need a GPU (`system and not requires_gpu`) — that's the
subset CI runs nightly Mon–Sat; the full 50 (including the 13 GPU-allocation tests) run
Sunday and on manual/`workflow_call` dispatch. See
[docs/admin/ci.md](../docs/admin/ci.md) for the CI scheduling.

## Test Markers

Tests are tagged with markers for selective execution:

```bash
# Run only tests requiring Docker
pytest -m requires_docker

# Skip GPU tests
pytest -m "not requires_gpu"

# Run only fast tests
pytest -m "not slow"
```

Available markers:
- `unit`, `integration`, `system` - Test tier
- `slow` - Long-running tests
- `requires_docker` - Needs Docker daemon
- `requires_gpu` - Needs nvidia-smi/GPU
- `requires_root` - Needs root privileges
- `user_role` - Role-based tests for the unprivileged user's access/experience
- `admin_role` - Role-based tests for the admin/service (deploy, allocation) path

## Legacy Test Suites

### cleanup-automation/

Comprehensive test suite for container lifecycle automation (idle timeout, max runtime, GPU release, container removal).

See [cleanup-automation/README.md](cleanup-automation/README.md) for details.

### validation/

System validation and health checks. See [validation/README.md](validation/README.md).

## Related Documentation

- [Root README](../README.md) - System overview
- [cleanup-automation/README.md](cleanup-automation/README.md) - Cleanup testing guide
- [validation/README.md](validation/README.md) - Validation procedures
