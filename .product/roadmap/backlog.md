# Backlog

Deferred technical items, infrastructure prerequisites, and ideas for future consideration.

## Deferred Code Quality (from Phase 3.2 Audit)

| ID | Issue | Severity | Effort | Notes |
|----|-------|----------|--------|-------|
| MEDIUM-01 | MIG slot representation fragility | Medium | 30 min | Fragile `.` check in `gpu_allocator_v2.py` line 123 |
| MEDIUM-02 | SSH re-login messaging | Medium | 5 min | `add-user-to-docker.sh` lacks clear group-change message |
| MEDIUM-03 | Profile.d error visibility | Medium | 15 min | Profile.d scripts run at login, errors are silent |
| MEDIUM-04 | Event rate limiting consolidation | Medium | 1 hour | Rate limiting only in denial layer, no general event rate limit |
| MEDIUM-06 | Grant file JSON validation | Medium | 20 min | Add validation on read in profile.d script |

**Total estimated effort:** ~2.5 hours

## Deferred Infrastructure

| Item | Blocker | Milestone |
|------|---------|-----------|
| IO bandwidth enforcement | Requires BFQ scheduler switch (currently mq-deadline) | M1 deferred |
| Disk quota enforcement | Requires XFS migration (currently ext4) | M1 deferred |
| Network bandwidth limits | Not relevant until multi-node or contention | M4+ |
| Fair-share GPU scheduling | Priority-based on historical usage | M4 (SLURM) |

## Operational Items

| Item | Status | Notes |
|------|--------|-------|
| Deploy DCGM exporter systemd service | Pending | Service file created (01-02), awaiting deployment |
| Configure Alertmanager SMTP | Blocked | Waiting on IT for credentials |
| Update container-list to use wrapper | Pending | Currently calls `/usr/bin/docker` directly |
| Fix deploy.sh pip install | Pending | System Python has no pip |
| Review CI/CD pipelines | Pending | lint.yml disabled, sync-docs needs configuration |
| Wrapper group detection mismatch | Investigation | mlc-create-wrapper applies student limits to researchers |

## Ideas & Future Considerations

- ShellCheck on all critical Bash scripts (recommended by Phase 3.2 audit)
- Systematic documentation development phase
- Teams notification webhook for ds01-hub repository
- ds01-hub documentation site via GitHub Pages
- Open-sourcing with MIT licence (requires Simon/Huy approval)
- Container vulnerability scanning (M6)
- Secrets management integration (M6)
