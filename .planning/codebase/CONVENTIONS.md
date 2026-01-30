# Coding Conventions

**Analysis Date:** 2026-01-26

## Naming Patterns

**Files:**
- Python scripts: `lowercase-with-hyphens.py` (e.g., `gpu-state-reader.py`, `gpu-allocator-v2.py`)
- Bash scripts: `lowercase-with-hyphens.sh` (e.g., `deploy-commands.sh`, `docker-wrapper.sh`)
- Libraries: `lowercase_with_underscores.py` for importable modules (e.g., `ds01_core.py`, `username_utils.py`)
- Directories: `lowercase/` (e.g., `scripts/docker/`, `scripts/lib/`)

**Functions:**

Python:
- Public functions: `snake_case` (e.g., `parse_duration()`, `get_container_owner()`)
- Private methods: `_snake_case` prefix (e.g., `_load_config()`, `_detect_interface()`)
- Classes: `PascalCase` (e.g., `GPUAllocatorSmart`, `GPUStateReader`)

Bash:
- Function names: `lowercase_with_underscores` (e.g., `ds01_error()`, `sanitize_username_for_slice()`)
- Functions prefixed with `ds01_` are public utilities from `init.sh`
- Helper functions may use `_name()` for private scope

**Variables:**

Python:
- Module constants: `UPPER_CASE` (e.g., `INTERFACE_ORCHESTRATION`, `INFRASTRUCTURE_CONTAINER_PATTERNS`)
- Local variables: `snake_case` (e.g., `user_containers`, `gpu_allocation`)
- Type hints: Required in function signatures, use Python 3.10+ syntax (`list[str]` not `List[str]`, `X | None` not `Optional[X]`)

Bash:
- Script constants: `UPPER_CASE` (e.g., `REAL_DOCKER`, `CURRENT_USER`)
- Environment variables: `UPPER_CASE` (e.g., `DS01_ROOT`, `DS01_CONFIG`)
- Local variables in functions: `lowercase` (e.g., `gpu_id`, `container_name`)
- Function parameters: Use `${1}`, `${2}` with descriptive local assignments (e.g., `local username="${1:?Usage: ...}"`)

**Types:**

Python:
- Type hints on all public functions (see `ds01_core.py` for examples)
- Return type hints always included
- Example: `def parse_duration(duration: str) -> int:`

## Code Style

**Formatting:**
- Python: Ruff formatter with 100 character line length (configured in `pyproject.toml`)
- Bash: No enforced formatter, but follow ShellCheck standards
- Run before committing: `ruff format` and `ruff check --fix`

**Linting:**
- Python: Ruff linter with rules `E, F, I, W` (configured in `pyproject.toml`)
- Bash: ShellCheck with `-x` flag to follow source statements (pre-commit hook)
- Large files can exceed line length; use `# noqa: E501` sparingly

**Python code structure (example from `ds01_core.py`):**
```python
#!/usr/bin/env python3
"""
Module docstring describing purpose, what it provides, usage examples.
"""

from __future__ import annotations

import stdlib_modules
import third_party_imports
import json
from typing import Optional, List, Dict, Any
from pathlib import Path


class ClassesFirst:
    """Class docstring."""
    pass


def top_level_functions():
    """Function docstring."""
    pass


if __name__ == "__main__":
    # Self-test code
    pass
```

**Bash code structure (example from `docker-wrapper.sh`):**
```bash
#!/bin/bash
# Full path in first line comment
# /opt/ds01-infra/scripts/docker/docker-wrapper.sh
#
# Description of what this script does
#

set -e  # Exit on error

# Constants at top
REAL_DOCKER="/usr/bin/docker"
DS01_ROOT="${DS01_ROOT:-/opt/ds01-infra}"

# Source libraries
source "$(dirname "$0")/../lib/init.sh"

# Functions with clear documentation
# Usage: function_name <arg1> <arg2>
function_name() {
    local arg1="${1:?Usage: function_name <arg1>}"
    local arg2="${2:-default}"
    # Function body
}

# Main execution
main() {
    # Main logic
}

main "$@"
```

## Import Organization

**Python:**
1. Standard library imports (e.g., `sys`, `json`, `subprocess`)
2. Third-party imports (e.g., `yaml`, `pytest`)
3. Local/relative imports (e.g., `from ds01_core import parse_duration`)

Imports organized by `isort` via Ruff. Path aliases defined in `pyproject.toml`:
```
known-first-party = ["ds01"]
```

**Bash:**
- Source libraries at beginning: `source /opt/ds01-infra/scripts/lib/init.sh`
- Source order: standard libs first, then custom DS01 libs
- Use absolute paths for sourcing (not relative)

## Error Handling

**Python:**
- Use explicit exception handling, not bare `except:`
- Return meaningful error values or raise exceptions
- Example from `gpu_allocator_v2.py`:
```python
try:
    result = subprocess.run(
        ['docker', 'inspect', ...],
        capture_output=True,
        text=True,
        timeout=5
    )
except (subprocess.TimeoutExpired, Exception):
    return None  # Explicit fallback
```
- Log errors to stderr when appropriate: `print(f"Error: {msg}", file=sys.stderr)`

**Bash:**
- Use `set -e` at top of scripts to exit on error
- Capture exit codes when needed: `set +e; RESULT=$(cmd); CODE=$?; set -e`
- Use conditional logic for recoverable errors:
```bash
if [ ! -f "$FILE" ]; then
    ds01_error "File not found: $FILE"
    exit 1
fi
```
- Exit codes: 0 for success, 1 for errors, other codes for specific failures

## Logging

**Framework:**
- Python: `print()` to stdout, `print(..., file=sys.stderr)` for errors
- Bash: `echo -e` with colour variables from `init.sh`

**Patterns:**

Python logging utilities (from `ds01_core.py`):
```python
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color / Reset
```

Bash logging functions (from `init.sh`):
```bash
ds01_error "message"      # Red "Error: " prefix to stderr
ds01_warn "message"       # Yellow "Warning: "
ds01_success "message"    # Green message
ds01_info "message"       # Blue message
ds01_header "Title"       # Bold header
ds01_log "msg" [logfile]  # Timestamped log entry
```

**When to log:**
- Errors always (to stderr)
- Warnings for non-fatal issues (e.g., "Config file not found, using defaults")
- Info for important milestones (not every step)
- Debug only if DEBUG_DS01_WRAPPER=1 or similar

## Comments

**When to comment:**
- Complex algorithms or non-obvious logic (see `gpu_allocator_v2.py` GPU allocation logic)
- Workarounds and why they exist (see `gpu-state-reader.py` comment on using `/usr/bin/docker` not wrapper)
- Important constraints or gotchas (see `username_utils.py` docstring about systemd hyphen hierarchy)
- Don't comment obvious code: `x = x + 1  # increment x` is bad

**JSDoc/TSDoc (not used - Python project):**
- Use Google-style docstrings for complex functions
- Simple functions get one-liner docstrings
- Include Args, Returns, Raises sections where helpful

Example from `ds01_core.py`:
```python
def parse_duration(duration: str) -> int:
    """
    Parse a duration string to seconds.

    Supports:
    - Hours: "2h", "0.5h", "48h"
    - Days: "1d", "7d"
    - Weeks: "1w", "2w"

    Args:
        duration: Duration string like "2h", "0.5d", "null"

    Returns:
        Duration in seconds, or -1 for no-limit values, or 0 if invalid

    Examples:
        >>> parse_duration("2h")
        7200
    """
```

## Function Design

**Size:**
- Prefer functions under 50 lines
- If longer, break into smaller helpers
- Scripts can have top-level code in `main()` function

**Parameters:**
- Use type hints on all parameters
- Required parameters first, optional parameters last
- Use meaningful defaults (not `True`/`False` without context)
- Bash: Use optional parameters with `${var:-default}` pattern
- Example: `def get_user_containers(username: str = None) -> List[Dict]:` allows filtering

**Return values:**
- Always annotate return type
- Return `None` for "not found" cases, not empty lists or False
- Bash functions echo output, return exit code via `return X`
- Example from `get_container_owner()`: Returns `Optional[str]` (username or `None`)

**Side effects:**
- Minimize - prefer pure functions when possible
- Document state mutations in docstring
- GPU allocator uses file locking to prevent race conditions: `self._acquire_lock()`

## Module Design

**Exports:**
- In Python, use public functions/classes (no `__all__` unless library)
- Private functions start with `_` underscore
- Library files (`ds01_core.py`, `username_utils.py`) can be imported
- Scripts are entry points, not meant for import

**Barrel files:**
- Not used in this codebase
- Imports are explicit and direct

**Shared libraries:**
- `scripts/lib/ds01_core.py`: Duration parsing, container utilities, colours
- `scripts/lib/username_utils.py`: Username sanitization for systemd
- `scripts/lib/init.sh`: Bash constants, paths, colour variables, convenience functions

## Command-Line Interfaces

**Argument handling:**

Python (example from `validate-commit-msg.py`):
```python
def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ...", file=sys.stderr)
        return 1

    commit_msg_file = Path(sys.argv[1])
    # Validate, return 0 on success, 1 on failure
```

Bash (example from `container-dispatcher.sh`):
```bash
SUBCOMMAND="${1:-}"

if [ -z "$SUBCOMMAND" ] || [ "$SUBCOMMAND" = "help" ]; then
    show_usage
    exit 0
fi

# Route to subcommand
SUBCOMMAND_SCRIPT="$SCRIPT_DIR/container-$SUBCOMMAND"
if [ ! -f "$SUBCOMMAND_SCRIPT" ]; then
    ds01_error "Unknown subcommand: $SUBCOMMAND"
    exit 1
fi
```

**Standard help patterns:**
- `-h` / `--help`: Quick reference
- `--info`: Full reference (all options)
- `--concepts`: Educational content
- `--guided`: Interactive help during execution

## Testing Integration

**Patterns:**
- Unit tests use pytest markers: `@pytest.mark.unit`, `@pytest.mark.component`, `@pytest.mark.integration`
- Tests can be marked as requiring Docker: `@pytest.mark.requires_docker`
- Tests can be marked as requiring GPU: `@pytest.mark.requires_gpu`
- Tests can be marked as requiring root: `@pytest.mark.requires_root`

**Test naming:**
- Test files: `test_*.py`
- Test classes: `Test*`
- Test methods: `test_*`

---

*Convention analysis: 2026-01-26*
