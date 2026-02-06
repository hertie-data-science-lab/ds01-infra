#!/bin/bash
# /opt/ds01-infra/testing/integration/test_resource_enforcement.sh
# Integration test for Phase 4 resource enforcement system
#
# Tests the full enforcement chain: config → generator → Docker → systemd → cgroups
# Designed for manual execution by admin (requires Docker, systemd, cgroup access)
#
# Usage: sudo ./test_resource_enforcement.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Test result tracking
declare -a PASSED_TESTS
declare -a FAILED_TESTS
declare -a SKIPPED_TESTS

# Helper functions
pass() {
    local test_name="$1"
    echo -e "${GREEN}[PASS]${NC} $test_name"
    ((TESTS_PASSED++)) || true
    PASSED_TESTS+=("$test_name")
}

fail() {
    local test_name="$1"
    local reason="$2"
    echo -e "${RED}[FAIL]${NC} $test_name - $reason"
    ((TESTS_FAILED++)) || true
    FAILED_TESTS+=("$test_name: $reason")
}

skip() {
    local test_name="$1"
    local reason="$2"
    echo -e "${YELLOW}[SKIP]${NC} $test_name - $reason"
    ((TESTS_SKIPPED++)) || true
    SKIPPED_TESTS+=("$test_name: $reason")
}

require_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}ERROR: This test requires root access${NC}"
        echo "Run with: sudo $0"
        exit 1
    fi
}

# ============================================================================
# Test Functions
# ============================================================================

test_config_valid() {
    local test_name="test_config_valid"

    if [ ! -f "$INFRA_ROOT/config/runtime/resource-limits.yaml" ]; then
        fail "$test_name" "resource-limits.yaml not found"
        return
    fi

    # Check for aggregate sections
    if python3 -c "
import yaml
with open('$INFRA_ROOT/config/runtime/resource-limits.yaml') as f:
    config = yaml.safe_load(f)

groups = config.get('groups', {})
has_aggregate = False
for group_name, group_config in groups.items():
    if 'aggregate' in group_config:
        has_aggregate = True
        break

exit(0 if has_aggregate else 1)
" 2>/dev/null; then
        pass "$test_name - aggregate sections present in groups"
    else
        fail "$test_name" "no aggregate sections found in groups"
    fi
}

test_generator_dry_run() {
    local test_name="test_generator_dry_run"

    if [ ! -f "$INFRA_ROOT/scripts/system/generate-user-slice-limits.py" ]; then
        skip "$test_name" "generator script not found"
        return
    fi

    # Run dry-run and check output contains systemd directives
    local output=$(python3 "$INFRA_ROOT/scripts/system/generate-user-slice-limits.py" --dry-run 2>&1 || true)

    if echo "$output" | grep -q "CPUQuota"; then
        pass "$test_name - CPUQuota in dry-run output"
    else
        fail "$test_name" "CPUQuota not found in dry-run output"
        return
    fi

    if echo "$output" | grep -q "MemoryMax\|MemoryHigh"; then
        pass "$test_name - Memory directives in dry-run output"
    else
        fail "$test_name" "Memory directives not found in dry-run output"
    fi

    if echo "$output" | grep -q "TasksMax"; then
        pass "$test_name - TasksMax in dry-run output"
    else
        fail "$test_name" "TasksMax not found in dry-run output"
    fi
}

test_cgroup_driver() {
    local test_name="test_cgroup_driver"

    if ! command -v docker &>/dev/null; then
        skip "$test_name" "Docker not installed"
        return
    fi

    local driver=$(docker info 2>/dev/null | grep "Cgroup Driver" | awk '{print $3}')
    if [ "$driver" = "systemd" ]; then
        pass "$test_name - Docker uses systemd cgroup driver"
    else
        fail "$test_name" "Docker cgroup driver is '$driver', expected 'systemd'"
    fi
}

test_slice_exists() {
    local test_name="test_slice_exists"

    require_root

    # Find users with running containers
    local has_containers=false
    if command -v docker &>/dev/null; then
        local containers=$(docker ps --format "{{.Names}}" 2>/dev/null || true)
        if [ -n "$containers" ]; then
            has_containers=true
        fi
    fi

    if ! $has_containers; then
        skip "$test_name" "no running containers to test"
        return
    fi

    # Check if any user slices exist
    if [ -d "/sys/fs/cgroup/ds01.slice" ]; then
        local slice_count=$(find /sys/fs/cgroup/ds01.slice -maxdepth 1 -name "ds01-*-*.slice" -type d 2>/dev/null | wc -l)
        if [ "$slice_count" -gt 0 ]; then
            pass "$test_name - found $slice_count user slices"
        else
            fail "$test_name" "ds01.slice exists but no user slices found"
        fi
    else
        fail "$test_name" "ds01.slice directory does not exist"
    fi
}

test_memory_enforcement() {
    local test_name="test_memory_enforcement"

    require_root

    # Check if any user slices have memory limits set
    local slices_with_limits=0
    if [ -d "/sys/fs/cgroup/ds01.slice" ]; then
        for slice_dir in /sys/fs/cgroup/ds01.slice/ds01-*-*.slice; do
            [ -d "$slice_dir" ] || continue

            if [ -f "$slice_dir/memory.max" ]; then
                local mem_max=$(cat "$slice_dir/memory.max" 2>/dev/null || echo "")
                if [ -n "$mem_max" ] && [ "$mem_max" != "max" ]; then
                    ((slices_with_limits++))
                fi
            fi
        done
    fi

    if [ "$slices_with_limits" -gt 0 ]; then
        pass "$test_name - found $slices_with_limits slices with memory limits"
    else
        skip "$test_name" "no user slices with memory limits (may not be deployed yet)"
    fi
}

test_aggregate_gpu_limit() {
    local test_name="test_aggregate_gpu_limit"

    # Check if get_resource_limits.py supports --aggregate flag
    if [ ! -f "$INFRA_ROOT/scripts/docker/get_resource_limits.py" ]; then
        skip "$test_name" "get_resource_limits.py not found"
        return
    fi

    # Test with a hypothetical user (checking CLI functionality)
    local output=$(python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" "testuser" --aggregate 2>&1 || true)

    if echo "$output" | grep -q "gpu_limit"; then
        pass "$test_name - aggregate query includes gpu_limit field"
    else
        fail "$test_name" "gpu_limit not found in aggregate output"
    fi
}

test_wrapper_aggregate_check() {
    local test_name="test_wrapper_aggregate_check"

    if [ ! -f "$INFRA_ROOT/scripts/docker/docker-wrapper.sh" ]; then
        skip "$test_name" "docker-wrapper.sh not found"
        return
    fi

    # Check if wrapper contains aggregate quota checking logic
    if grep -q "_check_aggregate.*quota\|check_aggregate_quota" "$INFRA_ROOT/scripts/docker/docker-wrapper.sh"; then
        pass "$test_name - wrapper contains aggregate quota check function"
    else
        fail "$test_name" "aggregate quota check function not found in wrapper"
    fi
}

test_psi_files_readable() {
    local test_name="test_psi_files_readable"

    require_root

    # Check if PSI is supported (kernel 4.20+)
    if [ ! -f "/sys/fs/cgroup/cpu.pressure" ]; then
        skip "$test_name" "PSI not supported by kernel (requires 4.20+)"
        return
    fi

    # Check if user slices have readable PSI files
    local readable_count=0
    if [ -d "/sys/fs/cgroup/ds01.slice" ]; then
        for slice_dir in /sys/fs/cgroup/ds01.slice/ds01-*-*.slice; do
            [ -d "$slice_dir" ] || continue

            if [ -r "$slice_dir/memory.pressure" ] && [ -r "$slice_dir/cpu.pressure" ]; then
                ((readable_count++))
            fi
        done
    fi

    if [ "$readable_count" -gt 0 ]; then
        pass "$test_name - PSI files readable for $readable_count slices"
    else
        skip "$test_name" "no user slices found to test PSI"
    fi
}

test_login_greeting_syntax() {
    local test_name="test_login_greeting_syntax"

    if [ ! -f "$INFRA_ROOT/config/deploy/profile.d/ds01-quota-greeting.sh" ]; then
        skip "$test_name" "ds01-quota-greeting.sh not found"
        return
    fi

    if bash -n "$INFRA_ROOT/config/deploy/profile.d/ds01-quota-greeting.sh" 2>/dev/null; then
        pass "$test_name - quota greeting script has valid syntax"
    else
        fail "$test_name" "quota greeting script has syntax errors"
    fi
}

test_resource_stats_script() {
    local test_name="test_resource_stats_script"

    if [ ! -f "$INFRA_ROOT/scripts/monitoring/collect-resource-stats.sh" ]; then
        fail "$test_name" "collect-resource-stats.sh not found"
        return
    fi

    if bash -n "$INFRA_ROOT/scripts/monitoring/collect-resource-stats.sh" 2>/dev/null; then
        pass "$test_name - resource stats script has valid syntax"
    else
        fail "$test_name" "resource stats script has syntax errors"
    fi
}

test_cron_deployment() {
    local test_name="test_cron_deployment"

    if [ ! -f "$INFRA_ROOT/config/deploy/cron.d/ds01-resource-monitor" ]; then
        fail "$test_name" "ds01-resource-monitor cron file not found"
        return
    fi

    # Check if cron file contains collect-resource-stats
    if grep -q "collect-resource-stats" "$INFRA_ROOT/config/deploy/cron.d/ds01-resource-monitor"; then
        pass "$test_name - cron file references collect-resource-stats"
    else
        fail "$test_name" "cron file does not reference collect-resource-stats"
    fi
}

# ============================================================================
# Main Test Runner
# ============================================================================

main() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}DS01 Resource Enforcement - Integration Tests${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # Run all tests
    echo -e "${BOLD}Configuration Tests:${NC}"
    test_config_valid
    test_generator_dry_run
    echo ""

    echo -e "${BOLD}Docker/Systemd Tests:${NC}"
    test_cgroup_driver
    test_slice_exists
    test_memory_enforcement
    echo ""

    echo -e "${BOLD}Aggregate Enforcement Tests:${NC}"
    test_aggregate_gpu_limit
    test_wrapper_aggregate_check
    echo ""

    echo -e "${BOLD}Monitoring Tests:${NC}"
    test_psi_files_readable
    test_resource_stats_script
    test_cron_deployment
    echo ""

    echo -e "${BOLD}Profile.d Tests:${NC}"
    test_login_greeting_syntax
    echo ""

    # Summary
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}Test Results:${NC}"
    echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
    echo ""

    local total=$((TESTS_PASSED + TESTS_FAILED))
    if [ $total -gt 0 ]; then
        local pass_rate=$((TESTS_PASSED * 100 / total))
        echo -e "  Pass rate: ${pass_rate}% ($TESTS_PASSED/$total)"
    fi
    echo ""

    # Show failed tests if any
    if [ $TESTS_FAILED -gt 0 ]; then
        echo -e "${RED}Failed tests:${NC}"
        for failed in "${FAILED_TESTS[@]}"; do
            echo -e "  - $failed"
        done
        echo ""
        exit 1
    fi

    if [ $TESTS_PASSED -eq 0 ]; then
        echo -e "${YELLOW}WARNING: No tests passed (all skipped)${NC}"
        echo ""
        exit 2
    fi

    echo -e "${GREEN}All tests passed!${NC}"
    echo ""
    exit 0
}

# Run main
main
