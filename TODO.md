# DS01 Infrastructure TODO

**Last Updated:** 2026-01-16
**Status:** Core system production-ready, monitoring deployed, dev container integration complete (experimental)

---

## HIGH Priority (Fix Now)

### Host GPU Process Detection (GAP IN TRACKING)
- [ ] **CRITICAL: DS01 doesn't capture host GPU processes** - Users bypassing containers entirely
  - **Audit (2026-01-16):** Found user `248835@hertie-school.lan` running 2 Jupyter kernels directly on host:
    - GPU 0: 4.4GB used (PID 1879486, bloom_test venv)
    - MIG 2.0: 9.8GB used (PID 2502049, bloom_test venv)
  - **Impact:** 0 DS01 containers with GPU assignments, but ~14GB GPU memory in use
  - **Root cause:** DS01 exporter only queries Docker for `ds01.*` labelled containers
  - **Why it happens:** Users with SSH access + docker/video group can use GPUs directly
  - **Detection gap:** DCGM sees GPU activity (shows in Grafana), but DS01 can't attribute to users
- [ ] **Add host GPU process monitor** - Detect non-container GPU processes
  - Cross-reference `nvidia-smi --query-compute-apps` PIDs with Docker container cgroups
  - Flag any PID not in a container as "untracked host process"
  - Include in `ds01_exporter.py` as new metric: `ds01_untracked_gpu_processes`
- [ ] **Add alerting for host GPU usage** - Prometheus alert when untracked processes detected
- [ ] **Consider enforcement options:**
  - Remove users from `video` group (breaks direct GPU access)
  - Use udev rules to restrict `/dev/nvidia*` access
  - Systemd device policies to limit GPU access to containers only
  - Or: accept host access but ensure monitoring captures it
- [ ] **Short-term fix:** Add `ds01_host_gpu_usage` metric to exporter
  - Query `nvidia-smi` for all GPU processes
  - Match PIDs to users via `/proc/<pid>/loginuid` or process owner
  - Report as separate metric series for visibility

### Monitoring Fixes
- [x] **Fix Grafana dashboard provisioning** - was permission issue (files were 600, needed 644)
- [x] **Fix GPU-Hours query** - was using `increase()` on gauge metric, changed to `avg_over_time()`
- [ ] **Restart DCGM Exporter container** - crashed 17h ago
- [ ] **Investigate empty event log** - `/var/log/ds01/events.jsonl` has 0 lines
- [ ] **Verify metric collection** - check `/var/log/ds01-infra/metrics/` has data
- [ ] **Update documentation** - ensure docs reflect hybrid architecture (DS01 Exporter = systemd, Prometheus/Grafana = Docker)

### Dev Container Integration
- [x] **Implement devcontainer-init wizard** - creates devcontainer.json with DS01 settings
- [x] **Integrate with project-init** - Step 7 offers CLI vs VS Code workflow choice
- [x] **Add devcontainer check validator** - validates devcontainer.json for DS01 compatibility
- [x] **Update user documentation** - docs-user/core-guides/devcontainers.md
- [ ] **TOP PRIORITY: Verify dashboard/DS01 tools handle dev containers** - Next to implement!
  - Check: `dashboard` shows dev containers correctly
  - Check: `container ls` displays dev containers (already updated)
  - Check: `gpu-status` reflects dev container GPU usage
  - Check: cleanup scripts handle dev containers appropriately
  - Check: dev containers appear in monitoring/metrics
- [ ] **CRITICAL: Test full dev container workflow end-to-end** - This may be the ideal workflow!
  - Test: Open folder in VS Code, "Reopen in Container", verify GPU allocation
  - Verify: docker-wrapper.sh intercepts and allocates GPU dynamically
  - Verify: Container appears in `container ls`
  - Verify: Closing VS Code releases GPU (shutdownAction works)
  - Check: Multiple opens get different GPUs based on availability
- [ ] **Add full image-create functionality to devcontainer-init** - Parity with CLI workflow
  - Read requirements.txt automatically (like image-create does)
  - Support use-case presets (ml, cv, nlp, llm, etc.) with pre-configured packages
  - Mirror --packages and --system options from image-* commands
  - Consider postCreateCommand vs custom Dockerfile approach
  - Goal: devcontainer workflow should be as capable as image-create + container-deploy
- [ ] **Add label injection for Docker API containers** - VS Code Dev Containers lack `ds01.user` label
- [ ] **Update cleanup scripts** - use `container-owners.json` for Dev Container detection (Option C from migration doc)
- [ ] **Verify docker-wrapper.sh handles devcontainer launches** - should rewrite `--gpus all` to specific device
- [ ] **Document dev containers workflow comprehensively** - Major documentation effort needed:
  - Update ds01-infra README.md with dev containers section
  - Update ds01-infra CLAUDE.md with dev containers architecture
  - **PRIORITY: ds01-hub documentation** - this is a major user-facing feature addition
    - New guide: VS Code dev containers workflow
    - Update getting started guides
    - Add to feature overview

### Container System Bugs
- [ ] **Fix container-stats --filter bug** - "unknown flag: --filter" error
- [ ] **Complete label standardisation** - mix of `ds01.*` and `aime.mlc.*` labels

### OPA Authorization (Parked but Critical)
- [ ] **Fix OPA service configuration** - service disabled, no auth plugin in daemon.json
- [ ] **Run OPA in server mode** with data file for container ownership lookup
- [ ] **Test container operation blocking** - users shouldn't exec/stop other users' containers
- [ ] **Block `docker image prune`/`docker system prune`** for non-admins (or restrict to own images)
- Reference: `/opt/ds01-infra/docs-admin/docker-permissions-migration.md`

---

## MEDIUM Priority (Planned)

### User Migration & Access Control
- [ ] **Migrate users to container workflow** - block bare metal GPU access
- [ ] **Get LDAP query access from IT** - currently only scanning /home directories
- [ ] **Configure LDAP group permissions with cgroups**
- [ ] **Set up proper /home permissions** - chmod 700 for new users
- [ ] **Review LDAP user creation** - understand how AD users are provisioned
- [ ] **Auto-group assignment script** - add users to appropriate groups (admin/faculty/researcher/student)

### Cleanup & Maintenance
- [ ] **Set up Docker prune cron job** - preserve images, clean build cache + containers
- [ ] **CPU idle threshold adjustment** - current < 1% too strict (consider < 2-5%)
- [ ] **Delete old/unused files and directories**
- [ ] **User cleanup procedure** - report on last login, archive departed users
- [ ] **Memory-efficient deployment process**

### Infrastructure
- [ ] **Set up backup strategy** - /home dirs, docker volumes, infra repo
- [ ] **Ensure config mirrors up to date** - all configs tracked in repo
- [ ] **Set up GitHub Actions** for CI/CD

### Open Source Preparation (after core fixes)
- [ ] **Refactor README as open source offering** - implementation layer on top of AIME/Docker
- [ ] **Discuss with Simon/Huy** about making public
- [ ] **Add MIT license**
- [ ] **Publish ds01-hub as GitHub Pages**
- [ ] **Set up Teams notifications** for GitHub issues

### Images & Dockerfiles
- [ ] **Fix image-create line 1244 bug** - "creation: command not found"
- [ ] **Fix image-update rebuild flow** - should offer rebuild after Dockerfile update

### Documentation
- [ ] **Update README.md with AIME v2 details**
- [ ] **Document user groups and permissions** - ds-admin, gpu-users, gpu-priority, docker-users
- [ ] **Fix architecture documentation** - consistently say "5-layer" not "4-tiered"
- [ ] **Write full user workflow** - what to do once running a container (kernel selection, etc.)

### User Setup & Wizards
- [ ] **user-setup doesn't read user's existing images** - shows "No custom images yet" when images exist
- [ ] **VS Code setup positioning** - should come after SSH keys, before dir/image setup

---

## LOW Priority (Roadmap)

### MIG Improvements
- [ ] **Document multi-MIG limitation** - cannot assign multiple MIG instances to single container
- [ ] **Investigate unpartition device=1 workflow**
- [ ] **Dynamic MIG configuration** - auto-partition GPUs based on demand

### Container Advanced
- [ ] **Container persistence option** - `--keep-container` flag for Phase 2
- [ ] **DS01_CONTEXT for cron-launched containers** - proper tracking
- [ ] **Increase container-stop timeout** - >10s, consider 30s default
- [ ] **Add --running, --stopped, --all flags to container-list**

### Documentation
- [ ] **Convert CLAUDE.md files to admin READMEs** - make AI-assistant docs into human-readable admin guides

### CLI Improvements
- [ ] **Rename image-create --> image-build** - aligns with Docker terminology
- [ ] **alias-list for inside containers** - mirror host alias-list functionality
- [ ] **Clean up redundant admin commands** - especially dashboard duplicates

### Directory & Permissions
- [ ] **Sort out /collaborative and /readonly permissions** - base on user groups
- [ ] **Change /scratch permissions to request-based** - students request via usergroups
- [ ] **Set up /data/, /projects/, /scratch/ directories with ACLs**
- [ ] **Move collaborative/, read_only/ into /srv** - with proper structure

### Advanced Features
- [ ] **SLURM integration** - job scheduling for batch workloads (significant complexity)
- [ ] **Advanced Grafana dashboards** - Phase 4 from monitoring plan
- [ ] **GPU queue functionality** - for users waiting for availability
- [ ] **Contribute --image flag upstream to AIME** - benefit community

### Testing
- [ ] **Set up unit, functional, integration tests** - expand beyond current 149 tests

---

## Parked (Blocked/Waiting)

### LDAP Access
- Currently scanning /home directories as workaround
- Blocked on IT for full LDAP API access
- Need to understand how AD users are managed

### cgroups Verification
- Not confirmed if optimally set up
- `systemctl status ds01.slice` sometimes shows inactive
- Need robust testing with new user provisioning

---

## Reference Docs
- Monitoring plan: `~/.claude/plans/purring-tickling-jellyfish.md`
- Grafana plan: `~/.claude/plans/vectorized-twirling-turtle.md`
- OPA migration: `docs-admin/docker-permissions-migration.md`
- Architecture: `README.md`
- Testing: `testing/README.md`

---

## Questions for IT / Stakeholders

1. **How are AD users provisioned?** Need to understand for auto-registration
2. **Can we get LDAP query access?** For user discovery
3. **Backup infrastructure?** Is there existing backup for /home?
4. **Simon/Huy approval** for open-sourcing ds01-infra?
