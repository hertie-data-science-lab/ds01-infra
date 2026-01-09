# scripts/lib/CLAUDE.md

Shared libraries for bash and Python scripts.

## Key Files

### Bash Libraries
| File | Purpose |
|------|---------|
| `init.sh` | Standard bash initialisation (paths, colours, utilities) |
| `dockerfile-generator.sh` | Shared Dockerfile generation (used by project-init, image-create) |
| `container-session.sh` | Unified handler for start/run/attach |
| `container-logger.sh` | Centralised event logging wrapper |
| `ds01-context.sh` | Context detection for conditional output |
| `interactive-select.sh` | Container/image selection UI |
| `error-messages.sh` | User-friendly error messages |
| `aime-images.sh` | AIME base image resolution |
| `project-metadata.sh` | pyproject.toml parsing/creation |
| `username-utils.sh` | Username sanitisation for systemd |
| `validate-resource-limits.sh` | Resource limit validation |

### Python Libraries
| File | Purpose |
|------|---------|
| `ds01_core.py` | Core utilities (duration parsing, container utils) |
| `username_utils.py` | Python username sanitisation |

## Usage

### Bash Scripts
```bash
# Source at start of script
source "$(dirname "$0")/../lib/init.sh"

# Available after sourcing:
# - Colour variables: $RED, $GREEN, $YELLOW, $BLUE, $NC
# - Utility functions: log_info, log_error, log_warning
# - Path variables: $DS01_ROOT, $DS01_CONFIG
```

### Python Scripts
```python
import sys
sys.path.insert(0, '/opt/ds01-infra/scripts/lib')
from ds01_core import parse_duration, get_container_owner
```

## Context Detection

`ds01-context.sh` provides `DS01_CONTEXT` environment variable:
- Orchestrators set `DS01_CONTEXT=orchestration`
- Atomic commands check this to suppress "Next steps" output

## Notes

- `init.sh` must be sourced, not executed
- Python libraries use `/opt/ds01-infra/scripts/lib` in sys.path
- Dockerfile generator supports 4 phases: Framework → Jupyter → Data Science → Use Case

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
