#!/bin/bash
# Comprehensive container enforcement system

# ONLY RUN THIS WHEN CONTAINER SET UP IS ROBUST!  sudo /opt/ds01-infra/scripts/docker/enforce-containers.sh
#
# MAKE SURE TO DOCUMENT ANY CONFIG UPDATES IN ETC-MIRRORS
# MAKE SURE TO ALLOW EXCEPTIONS FOR ADMINS in

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "DS01 Container Enforcement Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Create wrapper directory
echo "1. Creating command wrappers..."
WRAPPER_DIR="/opt/ds01-infra/wrappers"
mkdir -p "$WRAPPER_DIR"

# Backup original binaries
BACKUP_DIR="/opt/ds01-system/bin-originals"
mkdir -p "$BACKUP_DIR"

# Commands to wrap
WRAPPED_COMMANDS="python python3 pip pip3 jupyter jupyter-lab jupyter-notebook conda node npm R Rscript julia"

for cmd in $WRAPPED_COMMANDS; do
    REAL_PATH=$(which "$cmd" 2>/dev/null || echo "")

    if [ -n "$REAL_PATH" ]; then
        # Create wrapper
        cat >"$WRAPPER_DIR/$cmd" <<WRAPEOF
#!/bin/bash
# DS01 Container Enforcement Wrapper for $cmd

# Check if in container
if [ -f /.dockerenv ] || [ -n "\$DS01_CONTAINER" ] || [ -n "\$container" ]; then
    # In container - use real command
    exec "$REAL_PATH" "\$@"
fi

# Not in container - block
cat << 'MSGEOF'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⛔ Bare Metal Execution Not Allowed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Command: $cmd

All compute workloads must run inside containers.

🚀 Quick Start:
   mlc-open <container-name>

📋 Your Containers:
MSGEOF

docker ps -a --filter "label=ds01.user=\$(whoami)" \
    --format "   • {{.Names}} [{{.Status}}]" 2>/dev/null | \
    sed 's/\._\..*\ /\ /' || echo "   (none found)"

cat << 'MSGEOF'

🆕 Create a New Container:
   ds01-setup

💡 Why Containers?
   • Enforced resource limits
   • Fair GPU allocation
   • Reproducible environments
   • No user conflicts

❓ Need Help?
   Email: datasciencelab@university.edu
   Docs: /home/shared/docs/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MSGEOF

exit 1
WRAPEOF

        chmod +x "$WRAPPER_DIR/$cmd"
        echo "  ✓ Created wrapper for $cmd"
    fi
done

# 2. Create user setup script
echo ""
echo "2. Creating user environment setup..."

cat >/opt/ds01-infra/scripts/user/enable-container-enforcement.sh <<'ENABLEEOF'
#!/bin/bash
# Enable container enforcement for a user

USERNAME="${1:-$(whoami)}"
USER_HOME=$(eval echo "~$USERNAME")
BASHRC="$USER_HOME/.bashrc"

# Backup
cp "$BASHRC" "$BASHRC.backup-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true

# Remove old enforcement if exists
sed -i '/# DS01 Container Enforcement/,/# End DS01 Container Enforcement/d' "$BASHRC"

# Add new enforcement
cat >> "$BASHRC" << 'BASHEOF'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DS01 Container Enforcement
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Set marker when in container
if [ -f /.dockerenv ]; then
    export DS01_CONTAINER=1
fi

# Prioritize wrappers in PATH (only outside containers)
if [ -z "$DS01_CONTAINER" ]; then
    export PATH="/opt/ds01-infra/wrappers:$PATH"
fi

# Welcome message on login
if [ -z "$DS01_CONTAINER" ] && [ -z "$DS01_WELCOME_SHOWN" ]; then
    export DS01_WELCOME_SHOWN=1
    
    # Count containers
    CONTAINER_COUNT=$(docker ps -a --filter "label=ds01.user=$(whoami)" --format "{{.Names}}" 2>/dev/null | wc -l)
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "👋 DS01 GPU Server"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ "$CONTAINER_COUNT" -eq 0 ]; then
        echo ""
        echo "🚀 Get started: ds01-setup"
        echo ""
    else
        echo ""
        echo "📦 Your containers:"
        docker ps -a --filter "label=ds01.user=$(whoami)" \
            --format "  • {{.Names}}\t{{.Status}}" 2>/dev/null | \
            sed 's/\._\..*\t/\t/'
        echo ""
        echo "🔧 Commands:"
        echo "  mlc-open <name>    # Open container"
        echo "  ds01-dashboard     # Monitor resources"
        echo ""
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
fi

# End DS01 Container Enforcement
BASHEOF

chown "$USERNAME:$USERNAME" "$BASHRC"
echo "✓ Container enforcement enabled for $USERNAME"
ENABLEEOF

chmod +x /opt/ds01-infra/scripts/user/enable-container-enforcement.sh

# 3. Update container images to set marker
echo ""
echo "3. Creating container init script..."

cat >/opt/ds01-infra/scripts/docker/container-init.sh <<'INITEOF'
#!/bin/bash
# Script to run when container starts - marks it as a container

export DS01_CONTAINER=1

# Add to bashrc if not present
if [ ! -f ~/.bashrc ] || ! grep -q "DS01_CONTAINER" ~/.bashrc; then
    echo 'export DS01_CONTAINER=1' >> ~/.bashrc
fi

# Add visual indicator to prompt
if ! grep -q "DS01 CONTAINER" ~/.bashrc; then
    cat >> ~/.bashrc << 'PROMPTEOF'

# DS01 CONTAINER PROMPT
if [ -n "$DS01_CONTAINER" ]; then
    export PS1="\[\033[0;32m\][CONTAINER]\[\033[0m\] $PS1"
fi
PROMPTEOF
fi
INITEOF

chmod +x /opt/ds01-infra/scripts/docker/container-init.sh

# 4. Apply to all existing users in ds01-students group
echo ""
echo "4. Applying to existing users..."

# Get student group members (adjust as needed)
STUDENTS=$(getent group ds01-students | cut -d: -f4 | tr ',' ' ')

if [ -z "$STUDENTS" ]; then
    echo "  ⚠  No students found in ds01-students group"
    echo "  Manually run for each user:"
    echo "    /opt/ds01-infra/scripts/user/enable-container-enforcement.sh <username>"
else
    for student in $STUDENTS; do
        /opt/ds01-infra/scripts/user/enable-container-enforcement.sh "$student"
    done
fi

# Apply to admins too (they can override if needed)
/opt/ds01-infra/scripts/user/enable-container-enforcement.sh datasciencelab

# 5. Update container creation scripts
echo ""
echo "5. Updating container creation scripts..."

# Modify mlc-create-from-image to include init script
SCRIPT_PATH="/opt/ds01-infra/scripts/mlc-create-from-image.sh"

if ! grep -q "container-init.sh" "$SCRIPT_PATH"; then
    # Add volume mount for init script in docker run command
    # This would require editing the script directly
    echo "  ⚠  Manual step: Update mlc-create-from-image.sh to mount init script"
    echo "     Add this volume: -v /opt/ds01-infra/scripts/docker/container-init.sh:/etc/profile.d/ds01-init.sh:ro"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Container Enforcement Setup Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Next steps:"
echo "  1. Test with a student account: su - <student>"
echo "  2. Try: python --version (should be blocked)"
echo "  3. Open container: mlc-open <name>"
echo "  4. Inside: python --version (should work)"
echo ""
echo "🔧 To disable for a specific user:"
echo "  sed -i '/DS01 Container Enforcement/,/End DS01 Container Enforcement/d' ~<user>/.bashrc"
echo ""
