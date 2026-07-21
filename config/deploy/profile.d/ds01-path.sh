#!/bin/sh
# DS01 Infrastructure - System-wide PATH configuration
# Deployed to /etc/profile.d/ automatically by scripts/system/deploy.sh (sudo deploy).
#
# Ensures /usr/local/bin is in PATH for all users (domain + local)
# Required for DS01 CLI commands: container-*, image-*, ds01-dashboard, etc.

# Only modify PATH if /usr/local/bin is not already present
case ":${PATH}:" in
    *:/usr/local/bin:*)
        # Already in PATH, do nothing
        ;;
    *)
        # Add /usr/local/bin to PATH
        export PATH="/usr/local/bin:${PATH}"
        ;;
esac
