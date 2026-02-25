# ADR-006: Multi-Strategy Container Ownership Detection

**Status:** Accepted
**Date:** 2026-01-30

## Context

DS01 must attribute every container to a user for access control, lifecycle enforcement, and quota accounting. Containers arrive from multiple sources — DS01 commands, VS Code dev containers, docker-compose, raw `docker run` — each with different labelling conventions.

No single detection method works for all container types.

## Decision

Implement a 6-strategy priority-ordered detection system:

1. **`ds01.user` label** — set by DS01 tools (100% reliable)
2. **`aime.mlc.USER` label** — legacy AIME containers (100% reliable)
3. **Container name pattern** — `name._.uid` convention (100% reliable)
4. **`devcontainer.local_folder` label** — VS Code containers (infer user from path)
5. **Bind mount paths** — `/home/{user}/...` mount analysis (validated via file ownership)
6. **Compose `working_dir` label** — docker-compose services (infer user from working directory)

Strategies are evaluated in priority order; first match wins.

## Rationale

Different container creation tools label containers differently. VS Code uses `devcontainer.*` labels, docker-compose uses `com.docker.compose.*` labels, and raw `docker run` may have no labels at all. A multi-strategy approach handles all cases without requiring users to change their workflows.

## Alternatives Considered

- **Require DS01 labels on all containers:** Would break VS Code dev containers and docker-compose — users would need to manually add labels.
- **Process genealogy only:** Track which user's shell spawned the docker command. Unreliable for background processes, cron jobs, and service-managed containers.
- **Single strategy (labels only):** Misses all containers not created via DS01 commands.

## Consequences

- **Positive:** Handles all container types transparently. No workflow changes required from users.
- **Negative:** Mount path analysis can be spoofed (user could mount another user's directory). Mitigated by validating file ownership of mount source.
- **Robustness:** Tracker daemon crashes → systemd auto-restart. Missed events → periodic sync catchup. Detection failure → container marked "unknown", allowed to proceed (fail-open).
