# Architecture Decision Records

Lightweight ADRs documenting significant design decisions in DS01. Each record captures the context, decision, rationale, and trade-offs accepted.

## Format

Each ADR follows this structure:
- **Status:** Accepted | Superseded | Deprecated
- **Date:** When the decision was made or formalised
- **Context:** The problem or situation that prompted the decision
- **Decision:** What was chosen
- **Rationale:** Why this approach over alternatives
- **Alternatives Considered:** What was rejected and why
- **Consequences:** Trade-offs and implications accepted

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-docker-wrapper.md) | Universal enforcement via Docker wrapper | Accepted |
| [002](002-awareness-first.md) | Awareness-first architecture | Accepted |
| [003](003-stateless-gpu-allocation.md) | Stateless GPU allocation via Docker labels | Accepted |
| [004](004-fail-open-design.md) | Fail-open design philosophy | Accepted |
| [005](005-cgroup-v2-systemd.md) | Cgroup v2 with systemd slices | Accepted |
| [006](006-multi-strategy-ownership.md) | Multi-strategy container ownership detection | Accepted |
| [007](007-aime-minimal-patch.md) | Minimal AIME patch strategy | Accepted |
| [008](008-layered-commands.md) | Layered command architecture | Accepted |
| [009](009-event-logging.md) | JSONL event logging with PIPE_BUF guarantee | Accepted |
| [010](010-label-namespace.md) | ds01.* label namespace migration | Accepted |
| [011](011-config-hierarchy.md) | Deploy/runtime/state configuration hierarchy | Accepted |
| [012](012-notification-delivery.md) | TTY + container file notification delivery | Accepted |
| [013](013-opa-rejection.md) | OPA authorization plugin rejection | Accepted |
