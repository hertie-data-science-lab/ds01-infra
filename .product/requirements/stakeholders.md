# Stakeholders

User personas, their needs, and how DS01 serves each group.

## Student

**Profile:** Undergraduate or master's students learning data science and ML. Varying technical backgrounds — many are new to Linux, Docker, and command-line workflows.

**Needs:**
- Guided workflows (wizards, interactive prompts)
- Clear error messages with suggested fixes
- Simple container creation without understanding Docker internals
- Access to GPU resources for coursework and projects
- Persistence of work between sessions (workspace model)

**DS01 serves this via:**
- L4 wizards: `user-setup`, `project-init`, `project-launch`
- 4-tier help system: `--help`, `--info`, `--concepts`, `--guided`
- Ephemeral container philosophy: containers are temporary, workspaces are permanent
- Automatic resource limits (students don't need to specify `--cpus` or `--memory`)

**Resource profile:**
- GPU: up to 3 MIG instances (full GPU access enabled)
- CPU: 32 cores per container, 96 aggregate
- Memory: 32GB per container, 96GB aggregate
- Max containers: 3
- Idle timeout: group-configured (shorter)
- Max runtime: group-configured

## Researcher

**Profile:** PhD students, postdocs, and research staff. Comfortable with command lines. Run long training jobs, need larger resource allocations and longer timeouts.

**Needs:**
- Larger GPU allocations for training
- Longer idle timeouts (data loading, model evaluation)
- Lifecycle exemptions for deadline-driven work
- Custom Docker images for specific frameworks
- Direct Docker access for advanced workflows

**DS01 serves this via:**
- L2 atomic commands for direct control
- L3 orchestrators for common workflows
- Per-user lifecycle exemptions (`lifecycle-exemptions.yaml`)
- `image-create` for custom Dockerfile builds
- Higher resource limits and more patient idle detection

**Resource profile:**
- GPU: up to 6 MIG instances
- CPU: 48 cores per container, higher aggregate
- Memory: 64GB per container
- Max runtime: 48 hours
- Idle detection window: 4 consecutive checks (more patient)
- CPU idle threshold: 3% (accounts for data loading)

## Faculty

**Profile:** Professors and senior researchers. Similar technical needs to researchers. May have administrative visibility needs.

**Needs:**
- Similar to researcher but with higher allocations
- Visibility into student/researcher usage (future: M2 dashboards)
- Priority access during teaching periods

**DS01 serves this via:**
- Same interface layers as researcher
- Higher resource limits
- Priority field exists in config (enforcement deferred to M4)

**Resource profile:**
- GPU: up to 8 MIG instances
- CPU: 64 cores per container
- Memory: 128GB per container
- Idle detection: same as researcher

## Admin (Lab Manager)

**Profile:** Single person (datasciencelab) managing the entire server. Learning Linux server administration. Needs automation to reduce toil.

**Needs:**
- Low operational burden (automation over manual intervention)
- System visibility (dashboards, logs, events)
- Easy configuration changes (YAML, not code)
- Reliable deployment (`deploy.sh` — idempotent, validated)
- Clear documentation for procedures

**DS01 serves this via:**
- Admin CLI tools: `dashboard`, `ds01-events`, `ds01-workloads`, `ds01-logs`
- Automated lifecycle enforcement (cron-based, no manual intervention)
- Single config file (`resource-limits.yaml`) for all resource policies
- Idempotent deployment with deterministic permissions
- Comprehensive admin documentation (`docs-admin/`)

**Resource profile:**
- Unlimited (no aggregate limits, no lifecycle enforcement)
- Full system access

## Hardware Context

- **Server:** Single on-premises machine
- **GPUs:** 4x NVIDIA A100 with MIG support
- **Users:** 30-200 (department-scale university lab)
- **Domain:** Active Directory / LDAP usernames (`user@domain.lan`)
