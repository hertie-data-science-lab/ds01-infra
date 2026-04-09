# Contributing to DS01 Infrastructure

## Development Setup

```bash
# Clone the repository
git clone git@github.com:hertie-data-science-lab/ds01-infra.git
cd ds01-infra

# Install development tools
pip install pre-commit ruff
pip install shellcheck-py  # optional, for local shellcheck

# Install git hooks
pre-commit install --hook-type commit-msg
```

## Local CI

The Makefile mirrors the CI pipeline. Run before pushing:

```bash
make check         # Full CI locally (lint + test)
make fmt           # Auto-format all code (ruff + shfmt)
make lint          # Check without fixing
make test          # Unit + integration tests
```

Requires `ruff`, `shfmt`, and `shellcheck` on PATH. See `make help` for all targets.

## Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/).

### Format

```
<type>(<scope>): <subject>
```

### Types

| Type | Use for |
|------|---------|
| `feat` | New features |
| `fix` | Bug fixes |
| `docs` | Documentation |
| `refactor` | Code restructuring |
| `test` | Tests |
| `chore` | Maintenance |
| `ci` | CI/CD changes |

### Examples

```bash
feat: add GPU utilisation dashboard
fix(gpu): resolve allocation race condition
docs: update installation guide
feat!: new container API     # breaking change
```

## Pull Requests

1. Create a feature branch from `main`
2. Make changes with conventional commits
3. Run `make check` locally
4. Push and open a PR
5. CI must pass (the `CI` gate check)
6. Squash merge to main

## Code Style

### Bash Scripts

- Formatted with shfmt (`-i 4 -ci -s` — 4-space indent, case indent, simplify)
- Linted with shellcheck (`-x -S warning`)
- Use `set -e` for error handling, include usage functions

### Python Scripts

- Formatted with Ruff (100 char line length, target py310)
- Use type hints for public functions
- Use `pathlib.Path` over `os.path`

## Testing

```bash
make test          # Unit + integration (excludes system tests)
make test-all      # All tests including system (requires sudo + GPU)
```

See [testing/README.md](testing/README.md) for test structure and markers.

## Releases

Releases are manual, tag-triggered. See [docs-admin/ci.md](docs-admin/ci.md) for the full process.

```bash
# Update VERSION, commit, tag, push
echo "1.5.0" > VERSION
git add VERSION && git commit -m "chore: bump version to 1.5.0"
git tag v1.5.0 && git push --tags
```
