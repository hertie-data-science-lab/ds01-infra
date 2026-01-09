#!/bin/bash
# Dev Container Management - Main dispatcher for devcontainer operations
# Usage: devcontainer <subcommand> [args...]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

show_usage() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}DS01 Dev Container Management${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BOLD}Usage:${NC}"
    echo "  devcontainer <subcommand> [args...]"
    echo ""
    echo -e "${BOLD}Subcommands:${NC}"
    echo -e "  ${GREEN}init${NC}        Create devcontainer.json for VS Code"
    echo -e "  ${GREEN}check${NC}       Validate existing devcontainer.json"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo -e "  ${CYAN}devcontainer init${NC}                    # Interactive setup"
    echo -e "  ${CYAN}devcontainer init${NC} my-project         # Create for specific project"
    echo -e "  ${CYAN}devcontainer init${NC} --framework=tensorflow"
    echo -e "  ${CYAN}devcontainer check${NC}                   # Validate current config"
    echo ""
    echo -e "${BOLD}Options:${NC}"
    echo -e "  ${CYAN}devcontainer init --help${NC}     Show init options"
    echo -e "  ${CYAN}devcontainer init --concepts${NC} Learn about dev containers"
    echo -e "  ${CYAN}devcontainer init --guided${NC}   Step-by-step with explanations"
    echo ""
    echo -e "${YELLOW}Tip:${NC} You can also use hyphenated form: ${CYAN}devcontainer-init${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Get subcommand
SUBCOMMAND="${1:-}"

# No args or help → show usage
if [ -z "$SUBCOMMAND" ] || [ "$SUBCOMMAND" = "help" ] || [ "$SUBCOMMAND" = "-h" ] || [ "$SUBCOMMAND" = "--help" ] || [ "$SUBCOMMAND" = "--info" ]; then
    show_usage
    exit 0
fi

# Route subcommands
case "$SUBCOMMAND" in
    init)
        shift
        exec "$SCRIPT_DIR/devcontainer-init" "$@"
        ;;
    check)
        shift
        exec "$SCRIPT_DIR/devcontainer-check" "$@"
        ;;
    *)
        echo -e "${RED}Error:${NC} Unknown subcommand: ${BOLD}$SUBCOMMAND${NC}"
        echo ""
        echo "Available subcommands: init, check"
        echo "Run 'devcontainer help' for more information"
        exit 1
        ;;
esac
