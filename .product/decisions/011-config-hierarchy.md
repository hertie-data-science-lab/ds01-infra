# ADR-011: Deploy/Runtime/State Configuration Hierarchy

**Status:** Accepted
**Date:** 2026-02-05

## Context

DS01's configuration was originally scattered: some files in `config/`, mirrors in `config/etc-mirrors/`, runtime config mixed with deploy-time templates. It was unclear which files were read at install time vs runtime vs persisted as state. Duplicate configurations diverged silently.

## Decision

Organise all configuration by lifecycle phase:

- **`config/deploy/`** — Install-time files deployed to system locations (`/etc/`, `/usr/local/bin/`). Processed by `deploy.sh` with variable substitution. Includes: systemd units, profile.d scripts, cron jobs, sudoers rules, Docker daemon config.
- **`config/runtime/`** — Per-operation configuration read during container creation and lifecycle enforcement. Hot-reloadable (changes take effect immediately). Includes: `resource-limits.yaml` (SSOT), `lifecycle-exemptions.yaml`, `groups/*.members`.
- **`config/state/`** — Documents the structure of persistent state at `/var/lib/ds01/`. Not configuration itself, but describes where runtime state lives.

Template files (`*.template`) in `config/deploy/` are processed by `fill_config_template()` which substitutes variables from `config/variables.env`.

## Rationale

Lifecycle-based organisation makes it immediately clear when and how each file is used. Deploy-time files can be validated before deployment. Runtime files can be changed without redeployment. State documentation prevents confusion about what lives in `/var/lib/ds01/`.

## Alternatives Considered

- **Flat config directory:** All files in one `config/` folder. Original approach — became confusing as the system grew.
- **Environment-based (dev/staging/prod):** Not relevant for single-server deployment.
- **Database-backed configuration:** Overkill. YAML files are human-readable, git-trackable, and simple.

## Consequences

- **Positive:** Clear separation of concerns. Deploy-time validation catches errors before they reach production. Runtime changes take effect immediately without restart.
- **Negative:** Migration from flat structure required updating many file paths. `config/etc-mirrors/` retained as deprecated (marker file) during transition.
- **Template pipeline:** `fill_config_template()` validates no unsubstituted variables remain after processing — catches missing environment variables at deploy time rather than runtime.
