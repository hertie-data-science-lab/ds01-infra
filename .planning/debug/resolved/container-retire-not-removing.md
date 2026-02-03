---
status: resolved
trigger: "container retire says '✓ Removed container: test' but container still shows in `container list --all` as 'Stopped'"
created: 2026-02-04T10:00:00Z
updated: 2026-02-04T11:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - mlc-patched.py exits with code 0 even when container not found (missing aime.mlc.USER label)
test: Created container without aime.mlc.USER label, ran container-remove - claims success but container still exists
expecting: Exit code should be non-zero when removal fails
next_action: Fix mlc-patched.py line 606 to exit(1) instead of exit(0)

## Symptoms

expected: Container should be removed from Docker after `container retire`
actual: Container still shows in `container list --all` as "Stopped" after retire claims success
errors: No visible errors - the command claims success with "✓ Removed container: test"
reproduction:
1. Run `container deploy` (create a new container named "test")
2. Run `container retire` (select the test container)
3. Run `container list --all` - container still shows as Stopped
started: Reported now, likely a regression or incomplete fix

## Eliminated

- hypothesis: docker-wrapper.sh blocking or mishandling docker container rm
  evidence: Direct test of docker container rm works correctly, wrapper passes through properly
  timestamp: 2026-02-04T10:30:00Z

- hypothesis: container-remove not calling mlc-remove correctly
  evidence: Direct test of container-remove with proper labels works correctly
  timestamp: 2026-02-04T10:32:00Z

## Evidence

- timestamp: 2026-02-04T10:35:00Z
  checked: mlc-patched.py line 606 exit code
  found: existing_user_containers() exits with exit(0) when no containers found
  implication: container-remove sees exit 0 and assumes success

- timestamp: 2026-02-04T10:36:00Z
  checked: container without aime.mlc.USER label
  found: mlc-patched.py cannot find it, exits 0, container-remove prints success
  implication: This is the root cause - containers created without aime.mlc.USER label cannot be removed via mlc-remove

- timestamp: 2026-02-04T10:37:00Z
  checked: Original user's container creation path
  found: Need to check if container-create/deploy adds aime.mlc.USER label
  implication: May be a label injection issue in container creation flow

## Resolution

root_cause: mlc-patched.py line 606 uses exit(0) when no containers found, causing container-remove to interpret failure as success
fix: Changed exit(0) to exit(1) in existing_user_containers() error case
verification: Created container without aime.mlc.USER label, ran container-remove - correctly fell through to docker rm fallback and removed container
files_changed:
- /opt/ds01-infra/scripts/docker/mlc-patched.py
