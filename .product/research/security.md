# Security Research

CVEs, threat model, and container isolation boundaries relevant to DS01's design decisions.

## CVE-2024-41110: Docker Authorization Plugin Bypass

**Severity:** Critical (CVSS 9.9)
**Affected:** Docker Engine authorization plugins (including OPA docker-authz)
**Impact:** Specially crafted API requests bypass authorization plugin checks entirely. An attacker can perform any Docker operation regardless of policy.

**Relevance to DS01:** This CVE is the primary reason DS01 rejected the OPA authorization plugin approach. The Docker Engine's authz mechanism itself is vulnerable — no plugin can be trusted as a security boundary. DS01 uses a CLI wrapper instead, which operates at a different layer (PATH interception, not API-level authorization).

**DS01 decision:** ADR-013 — OPA rejection. The wrapper approach provides equivalent functionality without depending on the broken authz mechanism.

## CVE-2025-23266: NVIDIA Container Toolkit Escape

**Severity:** Critical
**Affected:** NVIDIA Container Toolkit < 1.17.8
**Impact:** Container escape to host root via `LD_PRELOAD` in Dockerfile. A malicious Dockerfile can inject a shared library that executes with host root privileges when the NVIDIA runtime processes the container.

**Relevance to DS01:** Users build custom Docker images (`image-create`). A malicious or compromised Dockerfile could exploit this vulnerability. DS01 tracks this as a production-blocking verification item.

**Mitigation:**
1. Upgrade `nvidia-ctk` to ≥ 1.17.8.
2. Or set `features.disable-cuda-compat-lib-hook = true` in `/etc/nvidia-container-runtime/config.toml`.
3. Verify with `nvidia-ctk --version`.

## Threat Model

**Trust boundaries:**

```
┌─────────────────────────────────────────────┐
│              Host System (root)              │
│  ┌─────────────────────────────────────┐    │
│  │     Docker Daemon (root)            │    │
│  │  ┌──────────┐  ┌──────────┐        │    │
│  │  │ User A   │  │ User B   │        │    │
│  │  │ Container│  │ Container│        │    │
│  │  └──────────┘  └──────────┘        │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │     DS01 Enforcement Layer          │    │
│  │  Docker wrapper, cgroup slices,     │    │
│  │  ownership tracking, GPU allocator  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**What users CAN do:**
- Create containers with any base image (custom Dockerfiles supported)
- Access GPUs within their allocation quota
- Access their own workspace files (`/home/{user}/workspace/`)
- Run arbitrary code inside their containers

**What users CANNOT do:**
- See or manage other users' containers (wrapper filters `docker ps`, blocks cross-user operations)
- Exceed their GPU quota (allocator enforces `max_mig_instances`)
- Exceed their CPU/memory quota (systemd slices enforce aggregate limits)
- Access GPUs outside containers without video group membership (profile.d blocks `CUDA_VISIBLE_DEVICES`)
- Run containers indefinitely (lifecycle enforcement stops idle/overtime containers)

**What DS01 does NOT protect against:**
- Container escape exploits (depends on Docker + kernel security, not DS01)
- Malicious Dockerfiles (DS01 doesn't scan images — potential M6 item)
- Network-level attacks between containers (no network policies — potential M6 item)
- Denial of service within allocated resources (user can consume their full quota)

## Container Isolation Boundaries

**Docker's isolation layers:**
1. **Linux namespaces:** PID, network, mount, UTS, IPC isolation per container. Users can't see each other's processes.
2. **Cgroups:** Resource limits enforced by kernel. DS01 adds systemd slice hierarchy.
3. **Seccomp profiles:** Restrict available syscalls. Docker default profile applied.
4. **AppArmor/SELinux:** MAC policies. Default Docker profiles applied.
5. **Root capability dropping:** Containers run with reduced capabilities.

**DS01's additional layers:**
1. **Ownership filtering:** Docker wrapper injects label filters so `docker ps` only shows user's own containers.
2. **Operation authorization:** Wrapper verifies ownership before allowing `exec`, `stop`, `remove` on containers.
3. **GPU device mapping:** Containers only see their allocated GPU devices (not all GPUs on the host).
4. **Cgroup aggregate limits:** Per-user systemd slices prevent any single user from consuming all system resources.

**Known limitations:**
- Docker daemon runs as root — any container escape reaches root. Mitigated by keeping Docker + NVIDIA toolkit patched.
- Users in the `docker` group can interact with the Docker socket. DS01 wrapper intercepts CLI usage but can't prevent direct socket access (would require removing docker group membership, which breaks container access).
- MIG isolation is hardware-enforced but MIG reconfiguration requires admin access (protected by sudo rules).
