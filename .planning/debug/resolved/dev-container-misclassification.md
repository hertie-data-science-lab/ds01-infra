---
status: resolved
trigger: "dev-container-misclassification"
created: 2026-02-05T00:00:00Z
updated: 2026-02-05T00:07:00Z
---

## Current Focus

hypothesis: Fix implemented - container-list now overrides devcontainer classification when GPU is allocated
test: Verify fix logic with different container scenarios
expecting:
  - Container with ds01.container_type=devcontainer + GPU allocated → shows as regular (no label)
  - Container with ds01.container_type=devcontainer + NO GPU → shows as "(dev container)"
  - Container with ds01.container_type=ds01 + GPU → shows as regular (no label)
next_action: Trace through fixed logic and verify correctness

## Symptoms

expected: Container "test" should show as regular container (not "dev container") since it has active GPU allocated
actual: `container list` output shows "test (dev container)" with "GPU: Allocated" — contradictory
errors: No errors, just wrong classification label
reproduction: Run `container list` as h.baker@hertie-school.lan — container test._.1722830498 shows "(dev container)" despite having GPU allocated
started: Likely always been this way — classification logic may be checking devcontainer.json presence rather than GPU allocation status

## Eliminated

## Evidence

- timestamp: 2026-02-05T00:01:00Z
  checked: scripts/user/atomic/container-list lines 218-247
  found: Classification logic at lines 218-229 checks for explicit ds01.container_type label, then devcontainer.local_folder label, but never considers GPU allocation status
  implication: A container can be classified as "devcontainer" even if it has GPU allocated - the classification is based on labels, not resource allocation

- timestamp: 2026-02-05T00:02:00Z
  checked: Lines 256-261 in container-list
  found: GPU allocation is displayed AFTER type classification is determined - these are two separate, independent checks
  implication: The display shows contradictory information because type and GPU status are not coordinated

- timestamp: 2026-02-05T00:03:00Z
  checked: docker-wrapper.sh detect_container_type() function (lines 198-228)
  found: Container type detection prioritizes devcontainer.* labels over everything else (except explicit ds01.interface label). When VS Code launches a container, it adds devcontainer.local_folder label, so docker-wrapper sets ds01.container_type=devcontainer
  implication: The container was correctly labeled as devcontainer at creation time (by docker-wrapper), but container-list should override this when GPU is allocated

- timestamp: 2026-02-05T00:04:00Z
  checked: Full classification flow
  found: 1) docker-wrapper detects devcontainer.* labels → sets ds01.container_type=devcontainer. 2) container-list reads ds01.container_type label → shows "(dev container)". 3) container-list checks GPU allocation separately for display only
  implication: ROOT CAUSE CONFIRMED - container-list needs to override devcontainer classification when GPU is present

## Resolution

root_cause: container-list uses ds01.container_type label directly without considering GPU allocation status. In DS01 terminology, "dev container" means "development without GPU resources", but the code classifies based on VS Code's devcontainer.* labels regardless of whether GPU is allocated. A container launched via container-deploy with GPU that happens to have devcontainer.json code is incorrectly shown as "(dev container)" when it should show as a regular container.

fix: Modified scripts/user/atomic/container-list show_simple() function to:
1. Check GPU allocation status BEFORE determining type display (lines 231-237)
2. Override devcontainer classification to ds01 if GPU is allocated (lines 240-243)
3. Reuse has_gpu variable for GPU display to avoid duplicate docker inspect call (line 268)
This ensures "dev container" label only shows for containers WITHOUT GPU allocation, matching DS01 terminology.

verification: PASSED
Logic verified through code trace:
- Scenario 1 (bug case): devcontainer + GPU → overridden to ds01 → no label shown ✓
- Scenario 2: devcontainer + no GPU → stays devcontainer → "(dev container)" label ✓
- Scenario 3: ds01 + GPU → stays ds01 → no label shown ✓
The fix correctly implements DS01 terminology: "dev container" = development without GPU resources.

files_changed: ["scripts/user/atomic/container-list"]

root_cause:
fix:
verification:
files_changed: []
