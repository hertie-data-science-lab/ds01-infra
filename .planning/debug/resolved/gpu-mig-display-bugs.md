---
status: resolved
trigger: "Multiple bugs after GPU/MIG detection changes - wrong GPU count, container contradictions, MIG options in full GPU mode, over-eager GPU notice"
created: 2026-02-03T00:00:00Z
updated: 2026-02-03T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - Multiple bugs found in display logic
test: Verified by code analysis
expecting: N/A - root cause confirmed
next_action: Implement fixes for 3 identified bugs

## Symptoms

expected:
- check-limits shows 4 GPUs (system has 4x A100)
- Container count consistent (no contradictions like "1/5 containers, 0 running")
- No MIG-related options shown when in Full GPU mode
- GPU notice only fires on actual CUDA initialization

actual:
- check-limits shows "4/6, 66%" (6 GPU limit when should be 4 total on system)
- Shows "1/5 containers, 0 running" (contradictory)
- "GPU Type Preference" prompt shows "1 distributed MIG partitions" even in Full GPU mode
- GPU notice fires on `lem experiment --help`

errors: No explicit errors, just wrong values and behavior

reproduction:
- `check-limits` as h.baker shows wrong GPU count
- `container deploy` shows MIG options even in full GPU mode
- `lem experiment --help` shows GPU blocked notice

started: After today's changes to add MIG auto-detection

## Eliminated

- Container count "1/5, 0 running" is NOT actually a bug - it correctly shows 1 stopped container of 5 limit

## Evidence

- timestamp: 2026-02-03T00:01:00Z
  checked: check-limits lines 117-172 (GPU display logic)
  found: max_mig comes from config (6 for researcher) but is NOT capped to system GPU count (4)
  implication: Display shows "4/6" when system only has 4 GPUs - user limit exceeds hardware

- timestamp: 2026-02-03T00:02:00Z
  checked: container-create lines 793-970 (MIG/GPU selection wizard)
  found: "GPU Type Preference" menu shows even when IS_MIG_MODE=false because condition only checks NUM_MIGS >= MIG_PER_GPU and MIG_PER_GPU=1 in full GPU mode
  implication: Shows "1 distributed MIG partitions" text even in full GPU mode which is confusing/wrong

- timestamp: 2026-02-03T00:03:00Z
  checked: container-create line 894 condition
  found: `if [ "$ALLOW_FULL_GPU" = "true" ] && [ "$NUM_MIGS" -ge "$MIG_PER_GPU" ]` - when MIG_PER_GPU=1, this is always true for any GPU request
  implication: The "GPU Type Preference" block (lines 893-924) should only run in MIG mode, not full GPU mode

- timestamp: 2026-02-03T00:04:00Z
  checked: lib/ds01_gpu_notice.c Layer 2 (dlsym override)
  found: Shows notice on dlsym("cuInit") lookup, which happens during PyTorch import probe even for --help
  implication: Notice fires too eagerly - should only fire when cuInit is actually called

## Resolution

root_cause: Three display bugs + 1 library bug:
1. check-limits: max_mig from config (user limit) not capped to system GPU count
2. container-create: "GPU Type Preference" menu shows in full GPU mode (should only show in MIG mode)
3. The text "distributed MIG partitions" makes no sense when IS_MIG_MODE=false
4. GPU notice: fires on dlsym lookup instead of actual cuInit call

fix:
1. check-limits: Cap max_mig to min(user_limit, system_gpu_count) for display
2. container-create: Add `IS_MIG_MODE=true` condition to "GPU Type Preference" block
3. GPU notice: Return our cuInit wrapper from dlsym instead of showing notice (notice fires when wrapper is called)

verification: Code changes applied, library rebuilt
files_changed:
- scripts/user/helpers/check-limits (cap max_mig to system GPU count)
- scripts/user/atomic/container-create (only show MIG preference in MIG mode)
- lib/ds01_gpu_notice.c (defer notice to actual cuInit call)
- lib/libds01_gpu_notice.so (rebuilt)
