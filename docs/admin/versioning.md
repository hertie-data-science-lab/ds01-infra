# Versioning & Releases

DS01 Infrastructure uses [Semantic Versioning](https://semver.org/) with manual tag-triggered releases.

> **A pushed `vX.Y.Z` tag both cuts a GitHub Release AND deploys to prod.** `release.yml`
> creates the release; `deploy.yml` (self-hosted runner) runs `sudo ds01-sync --ref vX.Y.Z`
> in parallel, which builds + smoke-tests the tag in the `/opt/ds01-staging` clone before
> releasing it to `/opt/ds01-infra` (health-gated, auto-rollback on failure). Don't push a
> `v*` tag unless you mean to ship to production now. See [Deployment](#deployment-ds01-sync)
> below.

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

## Deployment (`ds01-sync`)

`deploy.yml` fires on the same `v*.*.*` tag push (or `workflow_dispatch`) and, on the
self-hosted runner, runs:

```bash
sudo ds01-sync --ref vX.Y.Z
```

`ds01-sync` builds and smoke-tests the tag in the `/opt/ds01-staging` clone, rsyncs it to
the detached prod directory `/opt/ds01-infra` (no `.git` there — never `git pull`/`checkout`
in prod), runs `deploy.sh`'s side-effects, and health-gates the live system, auto-rolling
back to the last good SHA on failure. `current-sha` and release history live outside the
tree in `/var/lib/ds01/deploy/` (`current-sha`, `history.log`) — not in-tree `.git`.

Manual operations (admin, on the box):

```bash
sudo ds01-sync                 # release origin/main
sudo ds01-sync --ref v1.6.0    # release a specific tag (must be an ancestor of main)
sudo ds01-sync --rollback      # re-release the previous good SHA
sudo ds01-sync --list          # show release history + current SHA
```

`sudo deploy` (`deploy.sh`) on its own only reapplies side-effects (symlinks, systemd
units, sudoers, permissions) against whatever code is already on disk in prod — it does
not fetch or change code. Use `version` to check what's actually deployed; it reads
`/var/lib/ds01/deploy/current-sha` and reports `main (detached prod)@<sha>`.

## Commit Messages

Conventional Commits format is enforced by pre-commit hook. See [CONTRIBUTING.md](/develop/contributing) for details.

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
