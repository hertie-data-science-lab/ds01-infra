#!/bin/bash
# DS01 Infrastructure - Command Deployment
# Symlinks all DS01 commands to /usr/local/bin
# Run with: sudo /opt/ds01-infra/scripts/system/deploy.sh
#
# Deployment: Uses symlinks so SCRIPT_DIR resolves to /opt/ds01-infra/scripts/
# and co-located Python dependencies (gpu_allocator_v2.py, etc.) are found.
# Requires /opt/ds01-infra/scripts/ to be world-readable (755).
#
# Usage: sudo deploy [--verbose|-v]

# Self-bootstrap: if running as deployed copy, re-exec from source
INFRA_ROOT="/opt/ds01-infra"
SELF="$INFRA_ROOT/scripts/system/deploy.sh"
if [ "$0" = "/usr/local/bin/deploy" ] || { [ "$(basename "$0")" = "deploy" ] && [ "$0" != "$SELF" ]; }; then
    exec "$SELF" "$@"
fi
DEST_DIR="/usr/local/bin"

# Subdirectory shortcuts
USER_ATOMIC="$INFRA_ROOT/scripts/user/atomic"
USER_ORCHESTRATORS="$INFRA_ROOT/scripts/user/orchestrators"
USER_WIZARDS="$INFRA_ROOT/scripts/user/wizards"
USER_HELPERS="$INFRA_ROOT/scripts/user/helpers"
USER_DISPATCHERS="$INFRA_ROOT/scripts/user/dispatchers"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Parse arguments
VERBOSE=false
for arg in "$@"; do
    case $arg in
        -v|--verbose) VERBOSE=true ;;
        -h|--help)
            echo "Usage: sudo deploy [OPTIONS]"
            echo ""
            echo "Deploy DS01 commands to /usr/local/bin"
            echo ""
            echo "Options:"
            echo "  -v, --verbose    Show each command being deployed"
            echo "  -h, --help       Show this help"
            exit 0
            ;;
    esac
done

# Require root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This command requires sudo${NC}"
    echo "Run with: sudo deploy"
    exit 1
fi

# Verify Docker cgroup driver early (warn only, don't block deployment)
echo -e "${BOLD}Verifying Docker configuration...${NC}"
if [ -f "$INFRA_ROOT/scripts/system/verify-cgroup-driver.sh" ]; then
    if bash "$INFRA_ROOT/scripts/system/verify-cgroup-driver.sh"; then
        echo ""
    else
        echo -e "${YELLOW}WARNING: Docker cgroup driver check failed${NC}"
        echo -e "${YELLOW}Resource enforcement may not work correctly${NC}"
        echo ""
        # Don't exit - allow deployment to continue (other components may still be useful)
    fi
fi

# ============================================================================
# Helper Functions
# ============================================================================

# Source deploy-time variables
if [ -f "$INFRA_ROOT/config/variables.env" ]; then
    source "$INFRA_ROOT/config/variables.env"
fi

# Generative config pipeline: fill template with variables
# Usage: fill_config_template <template_file> <output_file>
fill_config_template() {
    local template_file=$1
    local output_file=$2

    if [ ! -f "$template_file" ]; then
        echo -e "  ${RED}✗${NC} Template not found: $template_file"
        return 1
    fi

    # Use envsubst to substitute variables
    if ! envsubst < "$template_file" > "$output_file" 2>/dev/null; then
        echo -e "  ${RED}✗${NC} Failed to process template: $template_file"
        return 1
    fi

    # Validate: check for unsubstituted variables
    if grep -q '\${[A-Z_][A-Z0-9_]*}' "$output_file"; then
        echo -e "  ${YELLOW}!${NC} WARNING: Unsubstituted variables in $output_file"
        grep -o '\${[A-Z_][A-Z0-9_]*}' "$output_file" | sort -u | sed 's/^/    /'
        return 1
    fi

    return 0
}

# Counters for each category
declare -A CATEGORY_SUCCESS
declare -A CATEGORY_FAIL
declare -A CATEGORY_ERRORS
TOTAL_SUCCESS=0
TOTAL_FAIL=0

# Deploy a single command (silent by default)
deploy_cmd() {
    local target=$1
    local name=$2
    local category=$3

    if [ ! -f "$target" ]; then
        CATEGORY_FAIL[$category]=$((${CATEGORY_FAIL[$category]:-0} + 1))
        CATEGORY_ERRORS[$category]+="  ${YELLOW}!${NC} $name (not found)\n"
        ((TOTAL_FAIL++))
        return 1
    fi

    rm -f "$DEST_DIR/$name" 2>/dev/null
    if ln -sf "$target" "$DEST_DIR/$name" 2>/dev/null; then
        CATEGORY_SUCCESS[$category]=$((${CATEGORY_SUCCESS[$category]:-0} + 1))
        ((TOTAL_SUCCESS++))
        $VERBOSE && echo -e "  ${GREEN}✓${NC} $name"
        return 0
    else
        CATEGORY_FAIL[$category]=$((${CATEGORY_FAIL[$category]:-0} + 1))
        CATEGORY_ERRORS[$category]+="  ${RED}✗${NC} $name (copy failed)\n"
        ((TOTAL_FAIL++))
        return 1
    fi
}

# Print category result
print_category() {
    local name=$1
    local success=${CATEGORY_SUCCESS[$name]:-0}
    local fail=${CATEGORY_FAIL[$name]:-0}
    local total=$((success + fail))

    if [ $fail -eq 0 ]; then
        printf "  %-28s ${GREEN}✓${NC} %d commands\n" "$name" "$success"
    else
        printf "  %-28s ${YELLOW}!${NC} %d/%d (${YELLOW}%d failed${NC})\n" "$name" "$success" "$total" "$fail"
        echo -e "${CATEGORY_ERRORS[$name]}"
    fi
}

# ============================================================================
# Header
# ============================================================================

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}DS01 Infrastructure - Command Deployment${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ============================================================================
# Validate Critical Configuration Files
# ============================================================================
# Validate YAML syntax before deploying to prevent broken config deployment

validate_yaml() {
    local yaml_file="$1"
    local name="$2"

    if [ ! -f "$yaml_file" ]; then
        echo -e "${RED}ERROR: $name not found at $yaml_file${NC}"
        exit 1
    fi

    if ! python3 -c "import yaml; yaml.safe_load(open('$yaml_file'))" 2>/dev/null; then
        echo -e "${RED}ERROR: Invalid YAML in $name${NC}"
        echo -e "${YELLOW}Path: $yaml_file${NC}"
        echo ""
        python3 -c "import yaml; yaml.safe_load(open('$yaml_file'))"  # Show error
        exit 1
    fi
}

echo -e "${BOLD}Validating configuration files...${NC}"
validate_yaml "$INFRA_ROOT/config/runtime/resource-limits.yaml" "resource-limits.yaml"
echo -e "${GREEN}✓${NC} resource-limits.yaml"
echo ""

echo ""

# ============================================================================
# Deterministic Permissions Manifest
# ============================================================================
# Sourced from config/permissions-manifest.sh — the single source of truth
# for all DS01 file permissions. Edit that file to add/change permissions.

source "$INFRA_ROOT/config/permissions-manifest.sh"

echo ""

# ============================================================================
# Deploy Commands
# ============================================================================

echo -e "${BOLD}Deploying commands...${NC}"
echo ""

# --- Wizards (L4) ---
$VERBOSE && echo -e "${DIM}Wizards:${NC}"
deploy_cmd "$USER_WIZARDS/user-setup" "user-setup" "Wizards"
deploy_cmd "$USER_WIZARDS/project-init" "project-init" "Wizards"
deploy_cmd "$USER_WIZARDS/project-launch" "project-launch" "Wizards"
deploy_cmd "$USER_WIZARDS/devcontainer-init" "devcontainer-init" "Wizards"

# --- Orchestrators (L3) ---
$VERBOSE && echo -e "${DIM}Orchestrators:${NC}"
deploy_cmd "$USER_ORCHESTRATORS/container-deploy" "container-deploy" "Orchestrators"
deploy_cmd "$USER_ORCHESTRATORS/container-retire" "container-retire" "Orchestrators"

# --- Atomic Container Commands (L2) ---
$VERBOSE && echo -e "${DIM}Container:${NC}"
deploy_cmd "$USER_ATOMIC/container-create" "container-create" "Container"
deploy_cmd "$USER_ATOMIC/container-start" "container-start" "Container"
deploy_cmd "$USER_ATOMIC/container-run" "container-run" "Container"
deploy_cmd "$USER_ATOMIC/container-attach" "container-attach" "Container"
deploy_cmd "$USER_ATOMIC/container-stop" "container-stop" "Container"
deploy_cmd "$USER_ATOMIC/container-remove" "container-remove" "Container"
deploy_cmd "$USER_ATOMIC/container-pause" "container-pause" "Container"
deploy_cmd "$USER_ATOMIC/container-unpause" "container-unpause" "Container"
deploy_cmd "$USER_ATOMIC/container-exit" "container-exit" "Container"
deploy_cmd "$USER_ATOMIC/container-list" "container-list" "Container"
deploy_cmd "$USER_ATOMIC/container-stats" "container-stats" "Container"

# --- Atomic Image Commands (L2) ---
$VERBOSE && echo -e "${DIM}Image:${NC}"
deploy_cmd "$USER_ATOMIC/image-create" "image-create" "Image"
deploy_cmd "$USER_ATOMIC/image-update" "image-update" "Image"
deploy_cmd "$USER_HELPERS/install-to-image.sh" "image-install" "Image"
deploy_cmd "$USER_ATOMIC/image-list" "image-list" "Image"
deploy_cmd "$USER_ATOMIC/image-delete" "image-delete" "Image"

# --- Dispatchers ---
$VERBOSE && echo -e "${DIM}Dispatchers:${NC}"
deploy_cmd "$USER_DISPATCHERS/container-dispatcher.sh" "container" "Dispatchers"
deploy_cmd "$USER_DISPATCHERS/image-dispatcher.sh" "image" "Dispatchers"
deploy_cmd "$USER_DISPATCHERS/project-dispatcher.sh" "project" "Dispatchers"
deploy_cmd "$USER_DISPATCHERS/user-dispatcher.sh" "user" "Dispatchers"
deploy_cmd "$USER_DISPATCHERS/check-dispatcher.sh" "check" "Dispatchers"
deploy_cmd "$USER_DISPATCHERS/get-dispatcher.sh" "get" "Dispatchers"
deploy_cmd "$USER_DISPATCHERS/devcontainer-dispatcher.sh" "devcontainer" "Dispatchers"

# --- Helpers ---
$VERBOSE && echo -e "${DIM}Helpers:${NC}"
deploy_cmd "$USER_HELPERS/shell-setup" "shell-setup" "Helpers"
deploy_cmd "$USER_HELPERS/ssh-setup" "ssh-setup" "Helpers"
deploy_cmd "$USER_HELPERS/vscode-setup" "vscode-setup" "Helpers"
deploy_cmd "$USER_HELPERS/check-limits" "check-limits" "Helpers"
deploy_cmd "$USER_HELPERS/check-limits" "get-limits" "Helpers"
deploy_cmd "$INFRA_ROOT/scripts/docker/gpu-queue-manager.py" "gpu-queue" "Helpers"
deploy_cmd "$USER_HELPERS/devcontainer-check" "devcontainer-check" "Helpers"

# --- Help & Info ---
$VERBOSE && echo -e "${DIM}Help:${NC}"
deploy_cmd "$INFRA_ROOT/scripts/admin/alias-list" "help" "Help"
deploy_cmd "$INFRA_ROOT/scripts/admin/alias-list" "commands" "Help"
deploy_cmd "$INFRA_ROOT/scripts/admin/alias-list" "aliases" "Help"
deploy_cmd "$INFRA_ROOT/scripts/admin/alias-list" "alias-list" "Help"
deploy_cmd "$INFRA_ROOT/scripts/admin/version" "version" "Help"
deploy_cmd "$INFRA_ROOT/scripts/admin/dashboard" "dashboard" "Help"

# --- Legacy aliases ---
$VERBOSE && echo -e "${DIM}Legacy:${NC}"
deploy_cmd "$USER_WIZARDS/project-init" "new-project" "Legacy"
deploy_cmd "$USER_WIZARDS/user-setup" "new-user" "Legacy"

# --- Admin Commands ---
$VERBOSE && echo -e "${DIM}Admin:${NC}"
deploy_cmd "$INFRA_ROOT/scripts/system/deploy.sh" "deploy" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/admin/dashboard" "ds01-dashboard" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/gpu-status-dashboard.py" "ds01-gpu" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/container-dashboard.sh" "ds01-containers" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/gpu-utilization-monitor.py" "ds01-gpu-util" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/mig-utilization-monitor.py" "ds01-mig-util" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/admin/ds01-users" "ds01-users" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/admin/ds01-logs" "ds01-logs" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/ds01-events" "ds01-events" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/ds01-workloads" "ds01-workloads" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/monitoring-status" "monitoring-status" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/admin/ds01-mig-partition" "ds01-mig-partition" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/admin/mig-configure" "mig-configure" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/who-owns-containers.sh" "ds01-who" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/ds01-health-check" "ds01-health" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/audit-system.sh" "ds01-audit" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/audit-docker.sh" "ds01-audit-docker" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/audit-container.sh" "ds01-audit-container" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/docker/gpu-queue-manager.py" "ds01-gpu-queue" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/resource-alert-checker.sh" "ds01-alerts" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/check-idle-containers.sh" "ds01-idle" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/maintenance/backup-logs.sh" "ds01-backup" "Admin"
deploy_cmd "$INFRA_ROOT/scripts/system/verify-cgroup-driver.sh" "ds01-verify-cgroup" "Admin"

# --- Internal (hidden from users) ---
$VERBOSE && echo -e "${DIM}Internal:${NC}"
deploy_cmd "$INFRA_ROOT/scripts/docker/docker-wrapper.sh" "docker" "Internal"
deploy_cmd "$INFRA_ROOT/scripts/docker/mlc-create-wrapper.sh" "mlc-create" "Internal"
deploy_cmd "$INFRA_ROOT/scripts/monitoring/mlc-stats-wrapper.sh" "mlc-stats" "Internal"

# Note: mlc-create dependencies (gpu_allocator_v2.py, etc.) are found automatically
# via SCRIPT_DIR resolution since deploy uses symlinks back to the repo.

# ============================================================================
# Deploy Access Control
# ============================================================================

echo ""
echo -e "${BOLD}Deploying access control...${NC}"
echo ""

# --- Prerequisites: Ensure at command is available ---
if ! command -v at &>/dev/null || ! systemctl is-active --quiet atd; then
    echo -e "  ${DIM}Installing at scheduler (required for temporary grants)...${NC}"
    apt-get install -y at &>/dev/null && systemctl enable --now atd &>/dev/null && \
        echo -e "  ${GREEN}✓${NC} at/atd installed and active" || \
        echo -e "  ${YELLOW}!${NC} WARNING: Failed to install at — temporary grants will not auto-revoke"
fi

# --- Deploy bare-metal-access admin CLI ---
deploy_cmd "$INFRA_ROOT/scripts/admin/bare-metal-access" "bare-metal-access" "Access Control"

# --- Deploy nvidia device permissions (0666 for GPU allocation chain) ---
# modprobe.d: kernel module creates devices with correct perms on load/reboot
MODPROBE_SRC="$INFRA_ROOT/config/deploy/modprobe.d/nvidia-permissions.conf"
MODPROBE_DST="/etc/modprobe.d/nvidia-permissions.conf"
if [ -f "$MODPROBE_SRC" ]; then
    cp "$MODPROBE_SRC" "$MODPROBE_DST"
    chmod 644 "$MODPROBE_DST"
    echo -e "  ${GREEN}✓${NC} Deployed modprobe.d nvidia config (0666 on next module load)"
fi
# udev: belt-and-suspenders for device re-creation events
UDEV_SRC="$INFRA_ROOT/config/deploy/udev/99-ds01-nvidia.rules"
UDEV_DST="/etc/udev/rules.d/99-ds01-nvidia.rules"
if [ -f "$UDEV_SRC" ]; then
    cp "$UDEV_SRC" "$UDEV_DST"
    chmod 644 "$UDEV_DST"
    udevadm control --reload-rules 2>/dev/null || true
fi
# Immediate: fix current devices without waiting for reboot
chmod 0666 /dev/nvidia[0-9]* /dev/nvidiactl /dev/nvidia-modeset /dev/nvidia-uvm /dev/nvidia-uvm-tools 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Set nvidia devices to 0666"
echo -e "  ${GREEN}✓${NC} Video group: managed by add-user-to-docker.sh (all docker users)"

# --- Docker wrapper isolation ---
# Docker wrapper defaults to enforcing mode (DS01_ISOLATION_MODE=full)
# Set DS01_ISOLATION_MODE=monitoring in environment to switch to monitoring mode
echo -e "  ${GREEN}✓${NC} Docker wrapper isolation: enforcing (default)"

# --- Deploy profile.d scripts (644 — sourced, not executed) ---
echo -e "${DIM}Deploying profile.d scripts...${NC}"

# From config/deploy/profile.d/ (single source of truth)
for script in "$INFRA_ROOT"/config/deploy/profile.d/ds01-*.sh; do
    [ -f "$script" ] || continue
    name="$(basename "$script")"

    # Check if template file (ends with .template)
    if [[ "$name" == *.template ]]; then
        # Generate from template
        output_name="${name%.template}"
        if fill_config_template "$script" "/etc/profile.d/$output_name"; then
            chmod 644 "/etc/profile.d/$output_name"
            echo -e "  ${GREEN}✓${NC} Generated $output_name from template"
        fi
    else
        # Direct copy
        cp "$script" /etc/profile.d/"$name"
        chmod 644 /etc/profile.d/"$name"
    fi
done

echo -e "  ${GREEN}✓${NC} Profile.d scripts deployed (644)"

# --- Deploy sudoers.d files (440 — read by sudo) ---
echo -e "${DIM}Deploying sudoers.d files...${NC}"

for sudoers_file in "$INFRA_ROOT"/config/deploy/sudoers.d/ds01-*; do
    [ -f "$sudoers_file" ] || continue
    name="$(basename "$sudoers_file")"
    cp "$sudoers_file" /etc/sudoers.d/"$name"
    chmod 440 /etc/sudoers.d/"$name"
done

echo -e "  ${GREEN}✓${NC} Sudoers.d files deployed (440)"

# --- Deploy cron.d files (644 — read by cron daemon) ---
echo -e "${DIM}Deploying cron.d files...${NC}"

for cron_file in "$INFRA_ROOT"/config/deploy/cron.d/ds01-*; do
    [ -f "$cron_file" ] || continue
    name="$(basename "$cron_file")"
    cp "$cron_file" /etc/cron.d/"$name"
    chmod 644 /etc/cron.d/"$name"
done

echo -e "  ${GREEN}✓${NC} Cron.d files deployed (644)"

# --- Ensure state directories exist ---
echo -e "${DIM}Creating state directories...${NC}"

mkdir -p /var/lib/ds01/resource-stats
chmod 755 /var/lib/ds01/resource-stats
mkdir -p /var/log/ds01
chmod 755 /var/log/ds01

# Ensure MOTD announcements file exists (empty = no announcements shown)
touch /etc/ds01-motd
chmod 644 /etc/ds01-motd

echo -e "  ${GREEN}✓${NC} State directories created"

# ============================================================================
# Validate Runtime Configuration
# ============================================================================

echo ""
echo -e "${BOLD}Validating runtime configuration...${NC}"
echo ""

# --- YAML validation for resource-limits.yaml ---
echo -e "${DIM}Validating resource-limits.yaml...${NC}"
if [ -f "$INFRA_ROOT/config/runtime/resource-limits.yaml" ]; then
    if python3 -c "import yaml; yaml.safe_load(open('$INFRA_ROOT/config/runtime/resource-limits.yaml'))" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} resource-limits.yaml is valid YAML"
    else
        echo -e "  ${RED}✗${NC} resource-limits.yaml has YAML syntax errors"
        python3 -c "import yaml; yaml.safe_load(open('$INFRA_ROOT/config/runtime/resource-limits.yaml'))" 2>&1 | head -5 | sed 's/^/    /'
        echo -e "  ${YELLOW}!${NC} Fix YAML errors before deployment"
    fi
else
    echo -e "  ${YELLOW}!${NC} resource-limits.yaml not found"
fi

# ============================================================================
# Deploy Systemd Units
# ============================================================================

echo ""
echo -e "${BOLD}Deploying systemd units...${NC}"
echo ""

# Ensure Python docker package is installed (required for workload detector)
echo -e "${DIM}Checking Python docker package...${NC}"
if ! python3 -c "import docker" 2>/dev/null; then
    echo -e "  ${YELLOW}!${NC} Installing docker package..."
    pip3 install docker >/dev/null 2>&1
    if python3 -c "import docker" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Python docker package installed"
    else
        echo -e "  ${RED}✗${NC} Failed to install docker package"
    fi
else
    echo -e "  ${GREEN}✓${NC} Python docker package already installed"
fi

# Ensure detect-workloads.py is executable
if [ -f "$INFRA_ROOT/scripts/monitoring/detect-workloads.py" ]; then
    chmod +x "$INFRA_ROOT/scripts/monitoring/detect-workloads.py"
fi

# Deploy workload detector systemd units
if [ -f "$INFRA_ROOT/config/deploy/systemd/ds01-workload-detector.timer" ] && \
   [ -f "$INFRA_ROOT/config/deploy/systemd/ds01-workload-detector.service" ]; then
    echo -e "${DIM}Deploying workload detector units...${NC}"
    cp "$INFRA_ROOT/config/deploy/systemd/ds01-workload-detector.timer" /etc/systemd/system/
    cp "$INFRA_ROOT/config/deploy/systemd/ds01-workload-detector.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable ds01-workload-detector.timer >/dev/null 2>&1
    systemctl start ds01-workload-detector.timer >/dev/null 2>&1

    # Check timer status
    if systemctl is-active --quiet ds01-workload-detector.timer; then
        echo -e "  ${GREEN}✓${NC} Workload detector timer enabled and started"
        # Show next trigger time
        NEXT_RUN=$(systemctl status ds01-workload-detector.timer 2>/dev/null | grep "Trigger:" | sed 's/.*Trigger: //')
        if [ -n "$NEXT_RUN" ]; then
            echo -e "  ${DIM}  Next scan: $NEXT_RUN${NC}"
        fi
    else
        echo -e "  ${YELLOW}!${NC} Workload detector timer not running (check systemctl status)"
    fi
else
    echo -e "  ${DIM}Workload detector units not found (will be created in Phase 2)${NC}"
fi

# Deploy DCGM exporter systemd unit (manages restart lifecycle for docker-compose container)
if [ -f "$INFRA_ROOT/config/deploy/systemd/ds01-dcgm-exporter.service" ]; then
    echo -e "${DIM}Deploying DCGM exporter unit...${NC}"
    cp "$INFRA_ROOT/config/deploy/systemd/ds01-dcgm-exporter.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable ds01-dcgm-exporter >/dev/null 2>&1

    if systemctl is-active --quiet ds01-dcgm-exporter; then
        echo -e "  ${GREEN}✓${NC} DCGM exporter service already running"
    else
        echo -e "  ${YELLOW}!${NC} DCGM exporter service enabled (start with: sudo systemctl start ds01-dcgm-exporter)"
    fi
else
    echo -e "  ${DIM}DCGM exporter unit not found${NC}"
fi

# ============================================================================
# Resource Enforcement: Generate Per-User Aggregate Limits
# ============================================================================

echo -e "${DIM}Deploying aggregate limit generator...${NC}"

# Deploy generator script as symlink
deploy_cmd "$INFRA_ROOT/scripts/system/generate-user-slice-limits.py" "ds01-generate-limits" "Internal"

# Generate/update aggregate limit drop-ins for all users
if [ -x "$INFRA_ROOT/scripts/system/generate-user-slice-limits.py" ]; then
    echo -e "${DIM}Generating aggregate limit drop-ins...${NC}"
    if python3 "$INFRA_ROOT/scripts/system/generate-user-slice-limits.py" --verbose 2>&1 | grep -q "updated\|unchanged"; then
        echo -e "  ${GREEN}✓${NC} Aggregate limits generated"
    else
        echo -e "  ${YELLOW}!${NC} No users found or aggregate limits disabled"
    fi
else
    echo -e "  ${YELLOW}!${NC} Generator script not found, skipping aggregate limit generation"
fi

# ============================================================================
# Summary
# ============================================================================

if ! $VERBOSE; then
    # Compact output (default)
    print_category "Wizards"
    print_category "Orchestrators"
    print_category "Container"
    print_category "Image"
    print_category "Dispatchers"
    print_category "Helpers"
    print_category "Help"
    print_category "Admin"
    print_category "Internal"
    print_category "Access Control"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ $TOTAL_FAIL -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Deployed ${BOLD}$TOTAL_SUCCESS${NC} commands successfully"
else
    echo -e "${YELLOW}!${NC} Deployed ${BOLD}$TOTAL_SUCCESS${NC} commands, ${YELLOW}$TOTAL_FAIL failed${NC}"
fi

echo ""
echo -e "${DIM}Run 'help' to see all available commands${NC}"
echo ""

