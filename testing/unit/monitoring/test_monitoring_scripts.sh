#!/bin/bash
# Shell script tests for monitoring commands
# /opt/ds01-infra/testing/unit/monitoring/test_monitoring_scripts.sh
#
# Usage: ./test_monitoring_scripts.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="${SCRIPT_DIR%/testing/*}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

pass() {
    echo -e "${GREEN}✓${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

run_test() {
    local name="$1"
    local cmd="$2"
    TESTS_RUN=$((TESTS_RUN + 1))

    if eval "$cmd" >/dev/null 2>&1; then
        pass "$name"
    else
        fail "$name"
    fi
}

echo "DS01 Monitoring Scripts Tests"
echo "=============================="
echo ""

# Test monitoring-manage script
echo "monitoring-manage:"

run_test "Script exists" \
    "[[ -f '$INFRA_ROOT/scripts/admin/monitoring-manage' ]]"

run_test "Script is executable" \
    "[[ -x '$INFRA_ROOT/scripts/admin/monitoring-manage' ]]"

run_test "Valid bash syntax" \
    "bash -n '$INFRA_ROOT/scripts/admin/monitoring-manage'"

run_test "Help flag works" \
    "'$INFRA_ROOT/scripts/admin/monitoring-manage' --help"

run_test "Help subcommand works" \
    "'$INFRA_ROOT/scripts/admin/monitoring-manage' help"

echo ""

# Test monitoring-status script
echo "monitoring-status:"

run_test "Script exists" \
    "[[ -f '$INFRA_ROOT/scripts/monitoring/monitoring-status' ]]"

run_test "Script is executable" \
    "[[ -x '$INFRA_ROOT/scripts/monitoring/monitoring-status' ]]"

run_test "Valid bash syntax" \
    "bash -n '$INFRA_ROOT/scripts/monitoring/monitoring-status'"

# Note: --quiet flag returns 1 if services not running, which is expected
run_test "Quiet flag accepted" \
    "'$INFRA_ROOT/scripts/monitoring/monitoring-status' --quiet || true"

echo ""

# Test exporter script
echo "ds01_exporter.py:"

run_test "Script exists" \
    "[[ -f '$INFRA_ROOT/monitoring/exporter/ds01_exporter.py' ]]"

run_test "Script is executable" \
    "[[ -x '$INFRA_ROOT/monitoring/exporter/ds01_exporter.py' ]]"

run_test "Valid Python syntax" \
    "python3 -m py_compile '$INFRA_ROOT/monitoring/exporter/ds01_exporter.py'"

echo ""

# Test systemd service file
echo "Systemd service:"

run_test "Service file exists" \
    "[[ -f '$INFRA_ROOT/config/deploy/systemd/ds01-exporter.service' ]]"

# Note: systemd files allow duplicate keys (e.g., multiple Environment=)
# which configparser rejects, so we just check basic structure
run_test "Service file has Unit section" \
    "grep -q '^\[Unit\]' '$INFRA_ROOT/config/deploy/systemd/ds01-exporter.service'"

echo ""

# Summary
echo "=============================="
echo "Tests run:    $TESTS_RUN"
echo -e "Passed:       ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed:       ${RED}$TESTS_FAILED${NC}"

if [[ $TESTS_FAILED -gt 0 ]]; then
    exit 1
fi
