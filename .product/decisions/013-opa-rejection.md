# ADR-013: OPA Authorization Plugin Rejection

**Status:** Accepted
**Date:** 2026-02-01

## Context

DS01 initially planned to use Open Policy Agent (OPA) as a Docker authorization plugin for container isolation — preventing users from seeing or managing other users' containers.

The OPA docker-authz plugin was evaluated, partially implemented, and ultimately rejected.

## Decision

Abandon OPA authorization plugin. Implement user isolation in the Docker CLI wrapper instead.

## Rationale

Two critical issues:

1. **CVE-2024-41110 (CVSS 9.9):** Docker Engine's authorization plugin mechanism itself has a bypass vulnerability. Specially crafted API requests skip the plugin entirely. No authorization plugin can be trusted as a security boundary while this vulnerability class exists.

2. **Plugin maturity:** The `opa-docker-authz` plugin has 77 GitHub commits and is effectively a demo project. It lacks production-grade error handling, monitoring, and update mechanisms. Running it as a Docker plugin means crashes can affect the Docker daemon.

The Docker wrapper already intercepts all CLI commands. Adding ownership verification (check `ds01.user` label before allowing `exec`/`stop`/`rm`) achieves the same functional outcome without depending on the broken authz mechanism.

## Alternatives Considered

- **Fix OPA plugin:** Cannot fix the underlying Docker Engine CVE from the plugin side. The authz mechanism itself is broken.
- **Custom Docker plugin:** Same CVE applies. Any Docker authorization plugin is affected.
- **Kubernetes network policies:** Requires Kubernetes. Out of scope.
- **SELinux/AppArmor policies:** Could provide container isolation but extremely complex to configure and maintain for dynamic container creation.

## Consequences

- **Positive:** No dependency on a vulnerable Docker mechanism. Wrapper-based isolation is simpler, debuggable, and fail-open capable.
- **Negative:** Wrapper only intercepts CLI usage, not direct Docker socket access. Users in the docker group could theoretically bypass isolation via the socket.
- **Accepted risk:** No current tooling uses the Docker socket directly. If this changes, socket access can be restricted via Unix permissions.
- **OPA artefacts:** OPA service files and policy (`docker-authz.rego`) remain in the codebase as deprecated/parked references.
