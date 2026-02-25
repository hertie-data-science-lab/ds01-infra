# DS01 Product Documentation

Product-level knowledge base for DS01 infrastructure. Maps the system as a coherent product: what it does, why decisions were made, what informed those decisions, and where it's going.

## What This Is

This directory contains **strategic product documentation** — not execution planning (`.planning/`), not admin runbooks (`docs-admin/`), not user guides (`docs-user/`). It's the product bible: research, decisions, designs, requirements, and roadmap in one place.

## Knowledge Chain

**Research** informs **decisions** informs **designs**.

```
research/          Why the industry does things this way
    ↓
decisions/         What DS01 chose and why (ADR format)
    ↓
designs/           How DS01 implements those decisions
    ↓
requirements/      What the system must do (functional + non-functional)
features/          What the system actually does (inventory with status)
roadmap/           Where the system is going (milestones + backlog)
```

## Navigation

### Research — What informed the design
- [Peer Systems](research/peer-systems.md) — SLURM, K8s GPU Operator, Run:ai, JupyterHub, AIME, academic HPC
- [Industry Practices](research/industry-practices.md) — GPU management, container orchestration, multi-tenancy patterns
- [CS Foundations](research/cs-foundations.md) — cgroups v2, file locking, atomic operations, fail-open, event sourcing
- [Security](research/security.md) — CVEs, threat model, container isolation boundaries

### Decisions — What was chosen and why
- [ADR Index](decisions/README.md) — 13 architecture decision records
- Key decisions: Docker wrapper (001), awareness-first (002), stateless GPU allocation (003), fail-open design (004), cgroup v2 (005), OPA rejection (013)

### Designs — How it works
- [GPU Allocation Flow](designs/gpu-allocation-flow.md) — Request → lock → allocate → label
- [Container Lifecycle](designs/container-lifecycle.md) — Create → run → idle detect → warn → stop → cleanup
- [Resource Enforcement](designs/resource-enforcement.md) — Two-layer: systemd slices + per-container Docker limits
- [Docker Wrapper](designs/docker-wrapper.md) — Interception points, modes, bypass
- [Deployment Pipeline](designs/deployment-pipeline.md) — deploy.sh: templates, validation, permissions
- [Notification System](designs/notification-system.md) — TTY discovery, quota caching, escalation levels

### Requirements — What it must do
- [Functional](requirements/functional.md) — 39 requirements grouped by domain, with implementation status
- [Non-Functional](requirements/non-functional.md) — Performance, reliability, security, operability constraints
- [Stakeholders](requirements/stakeholders.md) — User personas (student, researcher, faculty, admin)

### Features — What it actually does
- [Inventory](features/inventory.md) — 68 features across 8 subsystems with status

### Roadmap — Where it's going
- [Current Milestone](roadmap/current-milestone.md) — M1: Full Visibility & Control (97% complete)
- [Future Milestones](roadmap/future-milestones.md) — M2-M6 with triggers and prerequisites
- [Backlog](roadmap/backlog.md) — Deferred items, tech debt, ideas

## Relationship to Other Documentation

| Location | Purpose | Audience |
|----------|---------|----------|
| `.product/` | Product strategy, decisions, designs | Product thinking, roadmap planning |
| `.planning/` | Execution tracking, phase plans, state | Development execution |
| `docs-admin/` | Operational procedures, architecture details | System administrators |
| `docs-user/` | Guides, tutorials, command reference | End users |
| `CLAUDE.md` files | AI assistant context, module navigation | AI-assisted development |
