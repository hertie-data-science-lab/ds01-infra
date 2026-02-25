# Non-Functional Requirements

Performance, reliability, security, operability, and compatibility constraints.

## Performance

| Constraint | Target | Mechanism |
|------------|--------|-----------|
| SSH login latency | < 200ms overhead | Profile.d scripts use direct cgroup reads, no Python startup |
| Container detection lag | < 60 seconds | Real-time Docker event listener + 30s polling fallback |
| GPU allocation time | < 5 seconds | File-locked atomic allocation with 5s SIGALRM timeout |
| Event log write | Atomic (single syscall) | 4KB PIPE_BUF guarantee, no file locking needed |
| Quota display at login | < 200ms | Direct cgroup filesystem reads for memory.current, pids.current |
| Configuration changes | Immediate effect | Runtime config read per operation, no restart needed |

## Reliability

| Constraint | Implementation |
|------------|---------------|
| Fail-open design | Infrastructure errors never block user operations (safe defaults, warnings logged) |
| No single point of failure | Belt-and-suspenders: event daemon + periodic sync, per-container + aggregate limits |
| Lock timeout | 5-second SIGALRM prevents indefinite hangs on stuck lockfile |
| Automatic recovery | Systemd auto-restart for tracker daemon (5s delay). Periodic sync catches missed events |
| Atomic state writes | Temp-file-then-rename for JSON state files prevents partial-write corruption |
| Emergency bypass | `DS01_WRAPPER_BYPASS=1` skips all enforcement for recovery scenarios |

## Security

| Constraint | Implementation |
|------------|---------------|
| Container isolation | Docker wrapper filters `docker ps` and blocks cross-user operations |
| GPU access control | Three-layer: CUDA_VISIBLE_DEVICES (host), Docker device mapping (container), video group (opt-in bare metal) |
| No cross-user access | Ownership verification on exec/stop/remove operations |
| CVE posture | OPA rejected (CVE-2024-41110). NVIDIA toolkit version tracking (CVE-2025-23266) |
| Admin-only operations | root, datasciencelab, ds01-admin group bypass isolation |
| Rate-limited logging | Max 10 denial logs per hour per user (prevents log flooding from repeated attempts) |

## Operability

| Constraint | Implementation |
|------------|---------------|
| Single-admin manageable | Automation for deploy, monitoring, lifecycle. Minimal manual intervention |
| Idempotent deployment | `deploy.sh` produces same result on repeated runs |
| Deterministic permissions | `permissions-manifest.sh` enforces correct file permissions on every deploy |
| Zero-restart configuration | Runtime config changes take effect immediately without service restart |
| YAML validation | Config validated before deployment (prevents broken configs reaching production) |
| Comprehensive logging | JSONL event log + cron output + systemd journal for debugging |

## Compatibility

| Constraint | Implementation |
|------------|---------------|
| Backward-compatible labels | `ds01.*` labels with `aime.mlc.*` fallback chain |
| Cgroup v1/v2 support | Runtime detection of cgroup hierarchy version (v2 deployed, v1 fallback retained) |
| LDAP username support | Username sanitisation handles `@`, `.`, and domain suffixes for systemd compatibility |
| Multiple container interfaces | Docker wrapper enforces on all: DS01, docker-compose, VS Code dev containers, raw docker |
| AIME compatibility | 2.2% patch preserves 97.8% of mlc.py (upgradeable) |
