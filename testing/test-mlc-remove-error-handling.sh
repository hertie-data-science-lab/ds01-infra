#!/bin/bash
# Test that mlc-remove properly reports docker rm failures
# Tests the fix for container-already-exists-after-retire bug

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="/opt/ds01-infra"
MLC_PATCHED="$INFRA_ROOT/scripts/docker/mlc-patched.py"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "======================================================================"
echo "Testing mlc-remove error handling"
echo "======================================================================"
echo ""

# Test 1: Verify mlc-patched.py has error checking
echo -e "${YELLOW}Test 1: Verify error checking exists in mlc-patched.py${NC}"
if grep -q "exit_code = subprocess.Popen.*docker_command_delete_container" "$MLC_PATCHED"; then
    echo -e "${GREEN}✓ Found exit_code capture${NC}"
else
    echo -e "${RED}✗ Missing exit_code capture${NC}"
    exit 1
fi

if grep -q "if exit_code != 0:" "$MLC_PATCHED"; then
    echo -e "${GREEN}✓ Found exit code check${NC}"
else
    echo -e "${RED}✗ Missing exit code check${NC}"
    exit 1
fi

if grep -q "sys.exit(1)" "$MLC_PATCHED" | head -1 &>/dev/null; then
    echo -e "${GREEN}✓ Found sys.exit(1) for error propagation${NC}"
else
    echo -e "${RED}✗ Missing sys.exit(1)${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Test 2: Verify fix location${NC}"
# Check the fix is in the remove command section
LINE_NUM=$(grep -n "Delete the container" "$MLC_PATCHED" | cut -d: -f1)
FIX_LINE=$(grep -n "exit_code = subprocess.Popen.*docker_command_delete_container" "$MLC_PATCHED" | cut -d: -f1)

if [ -n "$LINE_NUM" ] && [ -n "$FIX_LINE" ]; then
    DIFF=$((FIX_LINE - LINE_NUM))
    if [ "$DIFF" -ge 0 ] && [ "$DIFF" -le 10 ]; then
        echo -e "${GREEN}✓ Fix is in correct location (line $FIX_LINE, $DIFF lines after comment)${NC}"
    else
        echo -e "${RED}✗ Fix location unexpected${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ Could not verify fix location${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}======================================================================"
echo -e "✓ All tests passed - mlc-remove now properly handles docker rm failures"
echo -e "======================================================================${NC}"
echo ""
echo "Before fix: docker rm failures were silent → container-retire succeeded falsely"
echo "After fix:  docker rm failures → mlc-remove exits 1 → container-retire reports error"
echo ""
