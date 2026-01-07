# Contributing to DS01 Infrastructure

## Development Setup

```bash
# Clone the repository
git clone git@github.com:hertie-data-science-lab/ds01-infra.git
cd ds01-infra

# Install development tools
pip install pre-commit commitizen

# Install git hooks
pre-commit install --hook-type commit-msg
```

## Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for automated versioning.

### Format

```
<type>(<scope>): <subject>
```

### Types

| Type | Use for | Version bump |
|------|---------|--------------|
| `feat` | New features | MINOR |
| `fix` | Bug fixes | PATCH |
| `docs` | Documentation | None |
| `refactor` | Code restructuring | PATCH |
| `test` | Tests | None |
| `chore` | Maintenance | None |
| `ci` | CI/CD changes | None |
| `perf` | Performance | PATCH |
| `build` | Build system | None |
| `style` | Formatting | None |
| `revert` | Reverts | PATCH |

### Examples

```bash
# Good
feat: add GPU utilisation dashboard
fix(gpu): resolve allocation race condition
docs: update installation guide
feat!: new container API

# Bad (will be rejected)
Add new feature           # No type prefix
feat add something        # Missing colon
feat: A.                  # Ends with period
```

### Breaking Changes

For breaking changes, add `!` after the type:

```bash
feat!: redesign container lifecycle API
```

Or include `BREAKING CHANGE:` in the footer.

## Pull Requests

1. Create a feature branch from `main`
2. Make changes with conventional commits
3. Push and open a PR
4. Ensure CI passes

## Code Style

### Bash Scripts

- Use `set -e` for error handling
- Include usage functions
- Use `echo -e` for colours
- See `ds01-UI_UX_GUIDE.md` for formatting standards

### Python Scripts

- Use type hints for public functions
- Format with Ruff (`ruff format`)
- Lint with Ruff (`ruff check --fix`)

## Testing

```bash
# Run pre-commit hooks on all files
pre-commit run --all-files

# Run Python tests (if applicable)
pytest testing/
```

## Releases

Releases are created manually by maintainers via GitHub Actions. See `docs-admin/versioning.md` for details.
