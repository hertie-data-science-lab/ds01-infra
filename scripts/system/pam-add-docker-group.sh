#!/bin/bash
# /opt/ds01-infra/scripts/system/pam-add-docker-group.sh
# PAM session script to auto-add users to docker group on first login
#
# This script is called by PAM on user login. It runs as root.
# It checks if the user is in the docker group and adds them if not.
#
# IMPORTANT: Resolves $PAM_USER to canonical username via UID to handle
# domain variants (e.g., user@students.hertie-school.org vs user@hertie-school.lan)
#
# Installation:
#   Add to /etc/pam.d/common-session:
#   session optional pam_exec.so /opt/ds01-infra/scripts/system/pam-add-docker-group.sh
#
# PAM provides these environment variables:
#   PAM_USER - the username
#   PAM_TYPE - open_session or close_session

LOG_FILE="/var/log/ds01/docker-group-additions.log"

log_msg() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true
}

# Only run on session open
[ "$PAM_TYPE" = "open_session" ] || exit 0

# Need a username
[ -n "$PAM_USER" ] || exit 0

# Skip system users (UID < 1000)
USER_UID=$(id -u "$PAM_USER" 2>/dev/null) || exit 0
[ "$USER_UID" -ge 1000 ] || exit 0

# Resolve PAM_USER to canonical username via UID
# This handles domain variants (e.g., user@students.hertie-school.org → user@hertie-school.lan)
CANONICAL_USER=$(getent passwd "$USER_UID" 2>/dev/null | cut -d: -f1)
if [ -z "$CANONICAL_USER" ]; then
    log_msg "ERROR: Could not resolve canonical username for PAM_USER=$PAM_USER (UID=$USER_UID)"
    exit 0
fi

# Log if we detected a domain variant mismatch
if [ "$PAM_USER" != "$CANONICAL_USER" ]; then
    log_msg "INFO: Domain variant detected: PAM_USER=$PAM_USER → CANONICAL=$CANONICAL_USER (UID=$USER_UID)"
fi

# Skip if canonical user already in docker group
if groups "$CANONICAL_USER" 2>/dev/null | grep -q '\bdocker\b'; then
    exit 0
fi

# Add canonical user to docker group
if usermod -aG docker "$CANONICAL_USER" 2>/dev/null; then
    log_msg "PAM: Added $CANONICAL_USER to docker group on first login (PAM_USER=$PAM_USER)"
else
    log_msg "ERROR: Failed to add $CANONICAL_USER to docker group"
fi

exit 0
