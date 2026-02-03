# Enhancement: Clear Error Message for Host GPU Compute Attempts

## Summary

When a non-exempt user tries to run a GPU-requiring script on the host (e.g. PyTorch training), they get no clear DS01-specific error message. `CUDA_VISIBLE_DEVICES=""` makes `torch.cuda.is_available()` return False, but the user just sees a generic "no GPU available" error from their framework.

## Desired Behaviour

When a CUDA application tries to initialise GPU on host for a non-exempt user, show a helpful message like:

```
DS01: GPU compute is not available on the host.
      Use 'container deploy' to create a GPU-enabled container.
      See: bare-metal-access --help
```

## Implementation Options

1. **LD_PRELOAD .so library** — intercepts `cuInit()` and shows message. Already partially implemented (`lib/ds01_gpu_notice.c`) but had permission issues (0700). Was fixed in 03.1-01 (755). Needs verification that it actually works.

2. **Shell alias/function** — wrap common commands (python3, python) to check CUDA_VISIBLE_DEVICES and warn. Simpler but less comprehensive.

3. **Profile.d message** — print a one-time warning on login. Already have MOTD. Could be more prominent.

## Investigation (2026-02-03)

**Permissions fixed** — Library now 755, loads without ld.so error.

**Still not working** — cuInit hook doesn't intercept PyTorch CUDA init. Needs deeper investigation:

```bash
# Trace to see what CUDA functions PyTorch actually calls
LD_DEBUG=bindings python3 -c "import torch; torch.cuda.is_available()" 2>&1 | grep -i cuda
strace -e openat python3 -c "import torch; torch.cuda.FloatTensor(1)" 2>&1 | grep -i cuda
ltrace -e '*cuda*' python3 -c "import torch; torch.cuda.FloatTensor(1)" 2>&1
```

**Hypotheses:**
1. PyTorch uses CUDA Runtime API (libcudart/cudaGetDeviceCount) not Driver API (cuInit)
2. PyTorch loads CUDA via dlopen which may bypass LD_PRELOAD despite dlsym hook
3. cuInit returns success (0) even with CUDA_VISIBLE_DEVICES="" so failure check doesn't trigger
4. Need to hook cudaGetDeviceCount or cudaSetDevice instead

**Alternative:** Accept silent blocking, remove notice feature entirely (core blocking works).

## Related

- `lib/ds01_gpu_notice.c` — existing .so library for LD_PRELOAD (hooks cuInit + dlsym)
- `config/deploy/profile.d/ds01-gpu-awareness.sh` — sets CUDA_VISIBLE_DEVICES="" and LD_PRELOAD
- Phase 3.1-01 fixed permissions on .so to 755

## Priority

Low — nice to have UX improvement. CUDA_VISIBLE_DEVICES="" already blocks compute effectively.
