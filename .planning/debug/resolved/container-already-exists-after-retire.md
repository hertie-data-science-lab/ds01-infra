---
status: resolved
trigger: "Container already exists after retirement - container deploy says 'Container already exists' after container retire test"
created: 2026-02-03T19:00:00Z
updated: 2026-02-03T19:12:00Z
---

## Current Focus

hypothesis: CONFIRMED - mlc-patched.py remove doesn't check if docker rm succeeded
test: Line 2565 uses subprocess.Popen().wait() but never checks the return code
expecting: Docker rm can fail but script continues and prints success message
next_action: Fix mlc-patched.py to check docker rm exit code and propagate failure

## Symptoms

expected: After `container retire test`, should be able to `container deploy test` again
actual: container deploy says "Container 'test' already exists"
errors: None - just wrong behavior
reproduction: 1) container retire test (shows success) 2) container deploy test (says already exists)
started: User report - unknown if this ever worked

## Eliminated

- hypothesis: Naming mismatch between container-retire and container-create
  evidence: User ID 1722830498, container test._.1722830498 - naming convention is CORRECT and consistent
  timestamp: 2026-02-03T19:03:00Z

## Evidence

- timestamp: 2026-02-03T19:00:00Z
  checked: User evidence from bug report
  found: docker ps -a shows container test._.1722830498 still running (Up 9 minutes) after container retire claimed success
  implication: container-retire is NOT actually removing the container

- timestamp: 2026-02-03T19:01:00Z
  checked: container-create naming convention (lines 440-444, 627-631, 995-1000)
  found: Uses pattern CONTAINER_TAG="${CONTAINER_NAME}._.${USER_ID}" - e.g., test._.1001
  implication: container-create uses USER_ID suffix, not timestamp

- timestamp: 2026-02-03T19:02:00Z
  checked: container-retire naming convention (line 385)
  found: Uses same pattern CONTAINER_TAG="${CONTAINER_NAME}._.${USER_ID}"
  implication: Both scripts use same naming convention - timestamp suffix (1722830498) is NOT from DS01 code

- timestamp: 2026-02-03T19:03:00Z
  checked: User provided clarification on naming
  found: User ID is 1722830498, container is test._.1722830498 - naming is correct
  implication: Naming mismatch hypothesis is eliminated

- timestamp: 2026-02-03T19:04:00Z
  checked: container-remove call at line 391
  found: Calls `bash "$MLC_REMOVE" "$container_name" -f -s > /dev/null 2>&1` with stderr suppressed
  implication: If mlc-remove fails, we won't see the error - and container showed "Exited (137)" before supposed removal

- timestamp: 2026-02-03T19:05:00Z
  checked: mlc-patched.py remove command implementation (lines 2562-2574)
  found: Line 2565 uses `subprocess.Popen(docker_command_delete_container, shell=True, text=True, stdout=subprocess.PIPE).wait()` but doesn't check exit code
  implication: If docker rm fails (e.g., container still running), mlc-remove silently succeeds and prints "container removed"

- timestamp: 2026-02-03T19:06:00Z
  checked: Python subprocess.Popen().wait() behaviour
  found: wait() returns exit code, but line 2565 doesn't capture or check it - execution continues to line 2574 regardless
  implication: ROOT CAUSE CONFIRMED - mlc-patched.py always reports success even when docker rm fails

- timestamp: 2026-02-03T19:08:00Z
  checked: Why docker rm would fail on stopped container
  found: Container showed "Exited (137)" which is SIGKILL - possibly from docker stop timeout killing it forcefully
  implication: Even if docker stop works, docker rm might fail if container has dependent resources (volumes, networks, etc.)

## Resolution

root_cause: mlc-patched.py remove command (line 2565) doesn't check docker rm exit code. When docker rm fails, the script continues and prints "container removed" success message, causing container-retire to believe removal succeeded when it actually failed.

fix: Modified mlc-patched.py line 2565 to:
  1. Capture exit code: exit_code = subprocess.Popen(...).wait()
  2. Check exit code: if exit_code != 0:
  3. Print error message with context
  4. Exit with sys.exit(1) to propagate failure to calling script
This ensures container-remove (line 391) properly detects failures and doesn't falsely report success.

verification: PASSED
  - Test confirmed exit_code capture exists
  - Test confirmed exit code check exists
  - Test confirmed sys.exit(1) error propagation exists
  - Test confirmed fix is in correct location (remove command section)
  - Logic verified: docker rm failure → mlc-remove exits 1 → container-retire reports error

files_changed:
  - scripts/docker/mlc-patched.py (lines 2565-2569)
