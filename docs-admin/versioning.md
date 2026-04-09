# Versioning & Releases

DS01 Infrastructure uses [Semantic Versioning](https://semver.org/) with manual tag-triggered releases.

## Version Bump Rules

```
feat:  → MINOR bump (1.0.0 → 1.1.0)
fix:   → PATCH bump (1.0.0 → 1.0.1)
feat!: → MAJOR bump (1.0.0 → 2.0.0)
```

## Files

| File | Purpose |
|------|---------|
| `VERSION` | Current version (single line, e.g. `1.5.0`) |
| `CHANGELOG.md` | Release history |
| `.github/workflows/release.yml` | Release automation |

## Creating a Release

1. Update `VERSION` file with the new version number
2. Commit the change:
   ```bash
   git add VERSION
   git commit -m "chore: bump version to 1.5.0"
   ```
3. Create and push the tag:
   ```bash
   git tag v1.5.0
   git push --tags
   ```
4. The `release.yml` workflow automatically:
   - Validates tag matches semver format (`vX.Y.Z`)
   - Checks `VERSION` file matches the tag
   - Creates a GitHub Release with auto-generated notes

### Via dispatch

You can also trigger a release manually:

```bash
gh workflow run release.yml -f tag=v1.5.0
```

Or via the GitHub UI: Actions → Release → Run workflow → enter tag.

## Commit Messages

Conventional Commits format is enforced by pre-commit hook. See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

## Pre-commit Setup

```bash
pip install pre-commit
pre-commit install --hook-type commit-msg
```

The commit-msg hook validates:
- Conventional commit format (`type(scope): subject`)
- Blocks AI attribution in commit messages
- Subject line under 72 characters

## Troubleshooting

### Version mismatch

If `VERSION` file doesn't match the latest git tag:

```bash
cat VERSION                        # Check file
git describe --tags --abbrev=0     # Check latest tag
```

### Release workflow fails

The workflow validates that the tag matches `vX.Y.Z` format and that the `VERSION` file contents match. Check both before retrying.
