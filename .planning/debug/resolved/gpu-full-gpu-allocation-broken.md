---
status: fixing
trigger: "gpu-full-gpu-allocation-broken"
created: 2026-01-31T00:00:00Z
updated: 2026-01-31T00:00:00Z
---

## Current Focus

hypothesis: Root cause confirmed - mlc-create is deployed as copy, dependencies missing in /usr/local/bin/
test: Deploy Python dependencies to /usr/local/bin/ and test GPU allocation
expecting: After deploy, container deploy should successfully allocate GPUs
next_action: Run sudo deploy to deploy gpu_allocator_v2.py and dependencies, then verify with container deploy test

## Symptoms

expected: `container deploy` should allocate a full GPU to researcher users (like h.baker@hertie-school.lan) when MIG is not configured. The allocator should see 4 available full GPUs and allocate one.
actual: `container deploy` shows "No GPUs Currently Available" even though `python3 /opt/ds01-infra/scripts/docker/gpu_allocator_v2.py status` (run directly by hbaker) shows "0/4 allocated (0.0% utilization)" — meaning the fix works when called directly but NOT through the deploy chain.
errors: "No GPUs Currently Available" — this is the allocator's "no GPU found" error message shown by mlc-create-wrapper.sh
reproduction: Run `container deploy` as h.baker@hertie-school.lan, select GPU enabled, select 1 MIG. Fails every time.
started: GPU allocation has likely been broken since MIG was disabled on the hardware. The system was designed for MIG mode. Patches applied tonight to support full GPUs, but the deploy chain doesn't use them.

## Eliminated

## Evidence

- timestamp: 2026-01-31T00:05:00Z
  checked: /usr/local/bin/mlc-create file type
  found: It's a COPY (regular file, not symlink). Size 31577 bytes, mode 755, dated Jan 31 23:10
  implication: SCRIPT_DIR resolves to /usr/local/bin/, not /opt/ds01-infra/scripts/docker/

- timestamp: 2026-01-31T00:05:30Z
  checked: /usr/local/bin/gpu_allocator_v2.py existence
  found: File does NOT exist
  implication: When mlc-create sets GPU_ALLOCATOR="$SCRIPT_DIR/gpu_allocator_v2.py", it points to non-existent /usr/local/bin/gpu_allocator_v2.py

- timestamp: 2026-01-31T00:06:00Z
  checked: deploy.sh deploy_cmd function
  found: Line 80: "cp "$target" "$DEST_DIR/$name"" — it COPIES files, not symlinks
  implication: The new deploy.sh (scripts/system/deploy.sh) copies all commands. Line 244 deploys mlc-create as copy.

- timestamp: 2026-01-31T00:06:30Z
  checked: Comment in mlc-create-wrapper.sh
  found: Line 9 says "Installation: sudo ln -sf /opt/ds01-infra/scripts/docker/mlc-create-wrapper.sh /usr/local/bin/mlc-create"
  implication: The file EXPECTS to be symlinked but is actually being COPIED by deploy.sh

## Resolution

root_cause: mlc-create is deployed as a COPY to /usr/local/bin/ (by deploy.sh), not as a symlink. When the wrapper runs, SCRIPT_DIR resolves to /usr/local/bin/ instead of /opt/ds01-infra/scripts/docker/. Therefore GPU_ALLOCATOR="$SCRIPT_DIR/gpu_allocator_v2.py" points to /usr/local/bin/gpu_allocator_v2.py which doesn't exist. The allocator with full GPU patches is never called. Dependencies: mlc-create-wrapper.sh requires 4 Python scripts from scripts/docker/: gpu_allocator_v2.py, get_resource_limits.py, mlc-patched.py, gpu-state-reader.py
fix: Added deploy_cmd calls in deploy.sh to deploy the 4 Python dependencies to /usr/local/bin/ alongside mlc-create (lines 247-250)
verification: Awaiting sudo access to run deploy, then test with container deploy
files_changed: ["scripts/system/deploy.sh"]
