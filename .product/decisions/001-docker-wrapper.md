# ADR-001: Universal Enforcement via Docker Wrapper

**Status:** Accepted
**Date:** 2026-01-30

## Context

DS01 needs to enforce GPU quotas, resource limits, ownership labels, and cgroup assignment on every container created on the server — regardless of how it was created (DS01 commands, docker-compose, VS Code dev containers, raw `docker run`).

The enforcement point must be universal: if a container can be created, it must pass through DS01's controls.

## Decision

Place a Docker CLI wrapper at `/usr/local/bin/docker` that intercepts all `docker` commands via PATH precedence over `/usr/bin/docker`.

The wrapper intercepts:
- **`docker run` / `docker create`:** Injects `--cgroup-parent`, ownership labels (`ds01.user`, `ds01.managed`), and routes GPU requests through `gpu_allocator_v2.py`.
- **`docker ps`:** Filters output to show only the calling user's containers (unless admin).
- **`docker stop` / `docker exec` / `docker rm`:** Verifies the caller owns the target container.

## Rationale

Universal coverage with minimal complexity. The wrapper sits at the only choke point all container creation methods share: the Docker CLI. VS Code dev containers, docker-compose, and direct `docker run` all invoke the `docker` binary.

## Alternatives Considered

- **OPA authorization plugin:** Rejected — CVE-2024-41110 bypass vulnerability makes Docker's authz mechanism untrustworthy. OPA plugin itself is demo-grade (77 GitHub commits). See ADR-013.
- **Docker API proxy:** Complex, version-dependent, requires maintaining compatibility with Docker API evolution.
- **Kubernetes admission webhooks:** Requires Kubernetes — DS01 is a single-server Docker deployment.
- **eBPF-based interception:** Powerful but high complexity for this use case. Kernel version dependencies.

## Consequences

- **Positive:** Single enforcement point for all container types. Fail-open capable. Easy to bypass in emergencies (`DS01_WRAPPER_BYPASS=1`).
- **Negative:** Adds ~1-2s latency to container creation (GPU allocation + config reads). Cannot intercept direct Docker socket access (users in docker group could bypass via socket).
- **Accepted risk:** Docker socket bypass is theoretical — no user tooling uses the socket directly, and the wrapper provides the `docker` binary they'd reach for.
