# Semantic Versioning

DS01 Infrastructure uses [Semantic Versioning](https://semver.org/) with automated tooling for version bumps and changelog generation.

## Quick Reference

### Commit Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**Required format:** `type: subject` (minimum)

**Types:**
| Type | Description | Version Bump |
|------|-------------|--------------|
| `feat` | New feature | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation only | None |
| `refactor` | Code change (no feature/fix) | PATCH |
| `test` | Adding/updating tests | None |
| `chore` | Maintenance | None |
| `ci` | CI/CD changes | None |
| `perf` | Performance improvement | PATCH |
| `build` | Build system changes | None |
| `style` | Formatting, whitespace | None |
| `revert` | Revert previous commit | PATCH |

**Breaking changes:** Add `!` before colon → MAJOR bump
```
feat!: redesign API endpoints
```

### Examples

```bash
# Feature (bumps minor: 1.0.0 → 1.1.0)
feat: add GPU queue dashboard

# Bug fix (bumps patch: 1.1.0 → 1.1.1)
fix: resolve container restart race condition

# Feature with scope
feat(gpu): add MIG instance monitoring

# Breaking change (bumps major: 1.1.1 → 2.0.0)
feat!: new container lifecycle API

# Documentation (no version bump)
docs: update installation guide
```

## Setup

### Install Pre-commit Hooks

```bash
# Install pre-commit and commitizen
pip install pre-commit commitizen

# Install the commit message hook
pre-commit install --hook-type commit-msg

# Optional: install all hooks (linting, formatting)
pre-commit install
```

### Verify Setup

```bash
# Test with an invalid commit (should be rejected)
echo "invalid commit message" | python3 scripts/lib/validate-commit-msg.py /dev/stdin

# Test with a valid commit
echo "feat: test commit" | python3 scripts/lib/validate-commit-msg.py /dev/stdin
```

## Creating Releases

Releases are created manually via GitHub Actions.

### Via GitHub UI

1. Go to **Actions** → **Release**
2. Click **Run workflow**
3. Options:
   - **dry_run**: Preview changes without releasing
   - **prerelease**: Create alpha/beta/rc release

### Via GitHub CLI

```bash
# Preview next release
gh workflow run release.yml -f dry_run=true

# Create stable release
gh workflow run release.yml

# Create pre-release
gh workflow run release.yml -f prerelease=beta
```

### What Happens

1. Commitizen analyses commits since last tag
2. Determines version bump (MAJOR/MINOR/PATCH)
3. Updates `VERSION` file
4. Updates `CHANGELOG.md`
5. Creates git tag (`v1.2.3`)
6. Pushes to main
7. Creates GitHub Release

## Files

| File | Purpose |
|------|---------|
| `VERSION` | Current version (source of truth) |
| `CHANGELOG.md` | Release history |
| `pyproject.toml` | Commitizen configuration |
| `.pre-commit-config.yaml` | Hook configuration |
| `scripts/lib/validate-commit-msg.py` | Commit validator |
| `.github/workflows/release.yml` | Release automation |

## Troubleshooting

### Commit Rejected

```
❌ Commit rejected: Invalid format. Expected: type(scope): subject
```

**Solution:** Use a valid commit type prefix.

### "No commits to bump"

The release workflow found no `feat` or `fix` commits since last tag.

**Solutions:**
1. Ensure commits use proper prefixes
2. Make a commit: `chore: prepare release` (won't bump version but allows release)

### Pre-commit Not Running

```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install --hook-type commit-msg
```

### Version Mismatch

If `VERSION` file doesn't match latest git tag:

```bash
# Check current version
cat VERSION

# Check latest tag
git describe --tags --abbrev=0

# If needed, manually sync
git tag -a v$(cat VERSION) -m "Sync tag with VERSION"
```

## Version Bump Rules

```
feat:  → MINOR bump (1.0.0 → 1.1.0)
fix:   → PATCH bump (1.0.0 → 1.0.1)
feat!: → MAJOR bump (1.0.0 → 2.0.0)

BREAKING CHANGE: in footer → MAJOR bump
```

Multiple commits between releases are aggregated:
- Any `feat!` or `BREAKING CHANGE` → MAJOR
- Any `feat` (no breaking) → MINOR
- Only `fix`/`refactor`/`perf` → PATCH
