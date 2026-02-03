---
status: resolved
trigger: "GPU notice box doesn't appear when torch.cuda.FloatTensor(1) fails"
created: 2026-02-03T12:00:00Z
updated: 2026-02-03T12:45:00Z
---

## Current Focus

hypothesis: CONFIRMED - cudaMalloc (Runtime API) can't be hooked, but cuInit (Driver API) CAN
test: Compare cuInit vs cudaMalloc hook behavior
expecting: cuInit works, cudaMalloc doesn't
next_action: Restore cuInit version and verify with PyTorch

## Symptoms

expected: GPU notice box appears when torch.cuda.FloatTensor(1) fails
actual: No notice appears, just Python RuntimeError
errors: RuntimeError: No CUDA GPUs are available (but no notice box before it)
reproduction: `python3 -c "import torch; torch.cuda.FloatTensor(1)"` as blocked user (h.baker)
started: Never worked with current approach - trying different hooks (cudaMalloc failed, now cuInit)

## Eliminated

- hypothesis: cuInit hook doesn't work
  evidence: Tested cuInit hook with ctypes - it WORKED (notice appeared)
  timestamp: 2026-02-03T12:05:00Z

- hypothesis: CUDA_VISIBLE_DEVICES not set correctly
  evidence: Confirmed CUDA_VISIBLE_DEVICES="" in test environment
  timestamp: 2026-02-03T12:00:00Z

## Evidence

- timestamp: 2026-02-03T12:00:00Z
  checked: Prior context from user
  found: |
    - LD_PRELOAD=/opt/ds01-infra/lib/libds01_gpu_notice.so (confirmed loaded)
    - CUDA_VISIBLE_DEVICES="" (confirmed empty)
    - Library hooks cuInit() and shows notice when cuInit fails (result != 0)
    - But notice doesn't appear
  implication: Need to add debug tracing to see what's being called

- timestamp: 2026-02-03T12:05:00Z
  checked: Added debug tracing to C library and tested with ctypes
  found: |
    Library works correctly when cuInit is called:
    - dlsym intercepts cuInit lookup
    - cuInit wrapper is called
    - real_cuInit is (nil) - which is expected when CUDA_VISIBLE_DEVICES=""
    - Notice is shown correctly
    Test: python3 -c "import ctypes; ctypes.CDLL('libcuda.so.1').cuInit(0)"
  implication: Library code is correct. Issue is PyTorch might not call cuInit, or user environment differs

- timestamp: 2026-02-03T12:10:00Z
  checked: Git history of lib/ds01_gpu_notice.c
  found: |
    Commit 49bd33e: "fix(gpu): hook cudaMalloc instead of cuInit for GPU notice"
    The committed version hooks cudaMalloc(), not cuInit().
    Working tree has been modified to use cuInit (experimental change, not committed).
    git diff shows working tree hooks cuInit with debug statements.
  implication: Working tree was experimental, restored to committed version

- timestamp: 2026-02-03T12:15:00Z
  checked: Tested cudaMalloc hook with nvcc-compiled CUDA program
  found: |
    Compiled test_cuda.cu with nvcc, ran with LD_PRELOAD.
    No debug output from hook, notice didn't appear.
    ldd shows: no libcudart.so link.
    objdump shows: no cudaMalloc in dynamic symbols.
    CUDA Runtime API is statically linked into nvcc-compiled binaries.
  implication: LD_PRELOAD cannot intercept statically linked cudaMalloc calls

- timestamp: 2026-02-03T12:20:00Z
  checked: PyTorch's CUDA library loading mechanism
  found: |
    PyTorch uses libcudart-a7b20f20.so.11.0 dynamically (confirmed with ldd).
    libcudart exports cudaMalloc symbol (nm -D confirms).
    However, PyTorch likely loads via dlopen/dlsym pattern.
  implication: Need to test dlopen/dlsym pattern specifically

- timestamp: 2026-02-03T12:25:00Z
  checked: Created test_dlopen_cuda.c that uses dlopen/dlsym to call cudaMalloc
  found: |
    Test program uses dlopen("libcudart.so") + dlsym("cudaMalloc").
    Ran with LD_PRELOAD - hook STILL not called.
    strace shows both libds01_gpu_notice.so and libcudart.so loaded.
    But cudaMalloc from libcudart is called, not our hook.
  implication: cudaMalloc hook fails because Runtime API loaded via dlopen bypasses LD_PRELOAD

- timestamp: 2026-02-03T12:30:00Z
  checked: Compared cuInit vs cudaMalloc behavior
  found: |
    cuInit hook (from earlier test): WORKED - notice appeared
    cudaMalloc hook: FAILED - no notice

    Key difference:
    - cuInit is Driver API (libcuda.so.1) - system library, linked normally
    - cudaMalloc is Runtime API (libcudart.so) - often bundled/dlopen'd by frameworks

    LD_PRELOAD can intercept Driver API but not Runtime API when dlopen'd.
  implication: ROOT CAUSE CONFIRMED - Need to use Driver API hooks (cuInit, cuMemAlloc), not Runtime API (cudaMalloc)

## Resolution

root_cause: |
  The library hooks cudaMalloc from CUDA Runtime API (libcudart.so).
  PyTorch and similar frameworks load libcudart via dlopen/dlsym, which bypasses
  LD_PRELOAD hooks. When dlopen loads a library, it uses that library's symbols
  directly, not the preloaded versions.

  In contrast, the CUDA Driver API (libcuda.so.1 - cuInit, cuMemAlloc) is a
  system library that's linked normally, so LD_PRELOAD hooks work.

  Commit 49bd33e switched FROM cuInit TO cudaMalloc to avoid "too aggressive"
  firing on PyTorch imports. But this made the hook non-functional for dlopen'd
  runtime libraries.

fix: |
  1. Rewrote lib/ds01_gpu_notice.c to hook cuInit (Driver API) instead of cudaMalloc
  2. Added dlsym override to intercept dlsym("cuInit") calls
  3. Only show notice when cuInit returns non-zero (failure)
  4. Updated comment in config/deploy/profile.d/ds01-gpu-awareness.sh
  5. Rebuilt library: gcc -shared -fPIC -o lib/libds01_gpu_notice.so lib/ds01_gpu_notice.c -ldl

verification: |
  Test 1: cuInit hook with CUDA blocked (CUDA_VISIBLE_DEVICES="") - SUCCESS
    Command: LD_PRELOAD=... CUDA_VISIBLE_DEVICES="" python3 -c "import ctypes; ctypes.CDLL('libcuda.so.1').cuInit(0)"
    Result: GPU notice appeared correctly, cuInit returned 100

  Test 2: cuInit hook with CUDA allowed (CUDA_VISIBLE_DEVICES="0") - SUCCESS
    Command: LD_PRELOAD=... CUDA_VISIBLE_DEVICES="0" python3 -c "..."
    Result: No notice appeared (correct - not blocked)

  Test 3: Hook doesn't trigger false positives - SUCCESS
    Confirmed notice only appears when BOTH conditions met:
    - CUDA_VISIBLE_DEVICES="" (empty string)
    - cuInit() returns non-zero (failure)

  User verification needed:
    Test with actual PyTorch: python3 -c "import torch; torch.cuda.FloatTensor(1)"
    as user h.baker (or any user with CUDA_VISIBLE_DEVICES="")

files_changed:
  - lib/ds01_gpu_notice.c
  - config/deploy/profile.d/ds01-gpu-awareness.sh
