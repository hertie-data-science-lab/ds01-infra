#!/bin/bash
# Enable very short timeouts for testing cron jobs
# This modifies resource-limits.yaml temporarily

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
CONFIG_FILE="$INFRA_ROOT/config/resource-limits.yaml"
BACKUP_FILE="$CONFIG_FILE.backup-$(date +%Y%m%d-%H%M%S)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Setting up test timeouts...${NC}"
echo ""

# Backup current config
echo -e "${YELLOW}Creating backup: $BACKUP_FILE${NC}"
cp "$CONFIG_FILE" "$BACKUP_FILE"

# Show current values
echo ""
echo -e "${BLUE}Current values:${NC}"
grep -E "max_runtime_h:|idle_timeout_h:|gpu_hold_after_stop_h:|container_hold_after_stop_h:" "$CONFIG_FILE" | head -4

# Modify for testing (very short timeouts)
echo ""
echo -e "${YELLOW}Setting test timeouts...${NC}"

# Use sed to replace timeout values
sed -i 's/max_runtime_h: .*/max_runtime_h: 0.05                # TEST: 3 minutes/' "$CONFIG_FILE"
sed -i 's/idle_timeout_h: .*/idle_timeout_h: 0.02                # TEST: ~1 minute/' "$CONFIG_FILE"
sed -i 's/gpu_hold_after_stop_h: .*/gpu_hold_after_stop_h: 0.01          # TEST: 36 seconds/' "$CONFIG_FILE"
sed -i 's/container_hold_after_stop_h: .*/container_hold_after_stop_h: 0.02      # TEST: ~1 minute/' "$CONFIG_FILE"

echo ""
echo -e "${BLUE}New values:${NC}"
grep -E "max_runtime_h:|idle_timeout_h:|gpu_hold_after_stop_h:|container_hold_after_stop_h:" "$CONFIG_FILE" | head -4

echo ""
echo -e "${GREEN}✓ Test timeouts enabled${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT:${NC}"
echo "  - max_runtime_h: 3 minutes (containers stopped after 3 min runtime)"
echo "  - idle_timeout_h: ~1 minute (idle containers stopped after ~1 min idle)"
echo "  - gpu_hold_after_stop_h: 36 seconds (GPUs released 36s after stop)"
echo "  - container_hold_after_stop_h: ~1 minute (containers removed ~1 min after stop)"
echo ""
echo "To restore original config:"
echo "  cp $BACKUP_FILE $CONFIG_FILE"
echo ""
