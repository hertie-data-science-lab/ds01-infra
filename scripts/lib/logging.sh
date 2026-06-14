#!/bin/bash
# /opt/ds01-infra/scripts/lib/logging.sh
# Shared logging helpers: log_info / log_success / log_warning / log_error.
#
# Self-contained: defines the colour codes it uses if they are not already set,
# so it works both standalone (sourced directly by a script) and composed
# (sourced by init.sh, which exports the colours first).
#
# Usage:
#   source "$INFRA_ROOT/scripts/lib/logging.sh"

: "${RED:=\033[0;31m}"
: "${GREEN:=\033[0;32m}"
: "${YELLOW:=\033[1;33m}"
: "${BLUE:=\033[0;34m}"
: "${NC:=\033[0m}"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}
