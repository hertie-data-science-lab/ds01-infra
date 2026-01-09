# scripts/user/CLAUDE.md

User-facing commands organised by layer (L2-L4).

## Directory Structure

```
user/
├── atomic/          # L2: Single-purpose commands
│   ├── container-{create|start|attach|run|stop|remove|list|stats|exit|pause}
│   └── image-{create|list|update|delete}
├── orchestrators/   # L3: Multi-step workflows
│   ├── container-deploy
│   └── container-retire
├── wizards/         # L4: Complete guided workflows
│   ├── user-setup
│   ├── project-init
│   └── project-launch
├── helpers/         # Supporting commands
│   ├── shell-setup, ssh-setup, vscode-setup
│   ├── check-limits, dir-create, git-init
│   └── readme-create, jupyter-setup
└── dispatchers/     # Command routers
    └── *-dispatcher.sh
```

## Layer Hierarchy

| Layer | Type | Example | Purpose |
|-------|------|---------|---------|
| L4 | Wizards | `user-setup` | Complete guided workflows |
| L3 | Orchestrators | `container deploy` | Multi-step sequences |
| L2 | Atomic | `container-create` | Single-purpose commands |

## User-Facing Interfaces

**DS01 Orchestration (Default)** - For all users:
- L4 Wizards: `user-setup`, `project-init`, `project launch`
- L3 Orchestrators: `container deploy`, `container retire`
- Binary state: containers are `running` or `removed`

**DS01 Atomic (Admin)** - For power users:
- Full L2 commands: `container-create`, `container-stop`, etc.
- Full state model: `created` → `running` → `stopped` → `removed`

## Command Design Patterns

### Dispatcher Pattern
```bash
container deploy    # Routes via container-dispatcher.sh
container-deploy    # Hyphenated alias also works
```

### Interactive by Default
```bash
container-deploy              # No args → interactive wizard
container-deploy my-project   # With args → direct execution
```

### 4-Tier Help System
| Flag | Type | Purpose |
|------|------|---------|
| `--help`, `-h` | Reference | Quick reference |
| `--info` | Reference | Full reference (all options) |
| `--concepts` | Education | Pre-run learning |
| `--guided` | Education | Interactive learning during execution |

### Conditional Output
Commands detect context via `DS01_CONTEXT` environment variable:
- Orchestrators set `DS01_CONTEXT=orchestration`
- Atomic commands suppress "Next steps" when called from orchestrators

## Key Commands

### L4 Wizards
```bash
user-setup                           # Full onboarding
project init my-thesis               # Create project structure
project init my-thesis --type=cv     # With use-case preset
project launch my-project            # Build image + deploy
project launch my-project --rebuild  # Force rebuild
```

### L3 Orchestrators
```bash
container deploy my-project          # Create + start
container deploy my-project --open   # Create + start + enter
container retire my-project          # Stop + remove + free GPU
container retire my-project --force  # Skip confirmations
```

### L2 Atomic
```bash
container-create my-project          # Create only
container-start my-project           # Start in background
container-run my-project             # Start and enter
container-stop my-project            # Stop only
container-remove my-project          # Remove only
container-list                       # List containers
container-stats                      # Resource usage
```

## Ephemeral Container Philosophy

**Core principle:** Containers = temporary compute sessions | Workspaces = permanent storage

**Ephemeral (removed):**
- Container instance
- GPU allocation

**Persistent (always safe):**
- `~/workspace/<project>/` files
- Dockerfiles
- Docker images

## Creating New Commands

1. Place in appropriate layer directory
2. Follow dispatcher pattern if space-separated
3. Implement 4-tier help system
4. Use `source "$(dirname "$0")/../lib/init.sh"` for bash
5. Respect `DS01_CONTEXT` for output

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
