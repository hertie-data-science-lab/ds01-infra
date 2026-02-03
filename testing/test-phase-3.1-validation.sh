#!/bin/bash
# Phase 3.1 Validation Script
# Verifies all 17 success criteria and 8 cross-phase UAT checks

set -euo pipefail

# Counters
PASS=0
FAIL=0
SKIP=0

# Output helpers
pass() { echo -e "  \033[0;32m✓\033[0m $1"; ((PASS++)) || true; }
fail() { echo -e "  \033[0;31m✗\033[0m $1"; ((FAIL++)) || true; }
skip() { echo -e "  \033[0;33m-\033[0m $1 (skipped)"; ((SKIP++)) || true; }

echo "========================================"
echo "Phase 3.1 Validation"
echo "========================================"
echo ""

# ====================
# PRE-DEPLOY CHECKS
# ====================
echo "PRE-DEPLOY CHECKS (source code verification):"
echo ""

# SC1: Permissions manifest exists in deploy.sh
if grep -q "chmod 755.*scripts" scripts/system/deploy.sh 2>/dev/null; then
    pass "SC1: Permissions manifest in deploy.sh"
else
    fail "SC1: Permissions manifest missing from deploy.sh"
fi

# SC3: Self-bootstrap pattern
if grep -q 'exec.*SELF' scripts/system/deploy.sh 2>/dev/null; then
    pass "SC3: Self-bootstrap re-exec pattern"
else
    fail "SC3: Self-bootstrap re-exec missing"
fi

# SC5: Profile.d deployment loop
if grep -q 'profile.d.*644' scripts/system/deploy.sh 2>/dev/null; then
    pass "SC5: Profile.d deployment with 644 permissions"
else
    fail "SC5: Profile.d deployment loop missing or wrong permissions"
fi

# SC6: GPU availability checker handles full GPUs
if grep -q '_get_physical_gpus' scripts/docker/gpu-availability-checker.py 2>/dev/null; then
    pass "SC6: Full GPU detection in availability checker"
else
    fail "SC6: Full GPU detection missing"
fi

# SC7: GPU allocator loads .members files
if grep -q 'member_file\|groups_dir' scripts/docker/gpu_allocator_v2.py 2>/dev/null; then
    pass "SC7: .members file loading in allocator"
else
    fail "SC7: .members loading missing"
fi

# SC8: Udev rule removal in deploy.sh
if grep -q '99-ds01-nvidia.rules' scripts/system/deploy.sh 2>/dev/null; then
    pass "SC8: Udev cleanup in deploy.sh"
else
    fail "SC8: Udev cleanup missing"
fi

# SC8b: No device permission manipulation
if grep -q 'MODE.*0660' scripts/system/deploy.sh 2>/dev/null; then
    fail "SC8b: Device permission manipulation still present"
else
    pass "SC8b: No device permission manipulation"
fi

# SC9: Video group restriction logic
if grep -q 'gpasswd -d' scripts/system/deploy.sh 2>/dev/null; then
    pass "SC9: Video group restriction logic"
else
    fail "SC9: Video group restriction missing"
fi

# SC10: Video group exemption in GPU awareness
if grep -q 'groups.*video' config/deploy/profile.d/ds01-gpu-awareness.sh 2>/dev/null; then
    pass "SC10: Video group exemption check in GPU awareness"
else
    fail "SC10: Video group exemption missing"
fi

# SC11: GPU notice library exists and is readable
if [ -f lib/libds01_gpu_notice.so ]; then
    pass "SC11: GPU notice .so exists"
else
    fail "SC11: GPU notice .so missing"
fi

# SC12: MOTD mentions container-only
if grep -q 'container-only' config/deploy/profile.d/ds01-motd.sh 2>/dev/null; then
    pass "SC12: MOTD mentions container-only access"
else
    fail "SC12: MOTD container-only message missing"
fi

# SC13: Docker wrapper enforcing mode default
if grep -q 'DS01_ISOLATION_MODE:-full' scripts/docker/docker-wrapper.sh 2>/dev/null; then
    pass "SC13: Docker wrapper enforcing mode default"
else
    fail "SC13: Enforcing mode default missing"
fi

# Python syntax checks
if python3 -c "import ast; ast.parse(open('scripts/docker/gpu-availability-checker.py').read())" 2>/dev/null; then
    pass "Syntax: gpu-availability-checker.py valid"
else
    fail "Syntax: gpu-availability-checker.py invalid"
fi

if python3 -c "import ast; ast.parse(open('scripts/docker/gpu_allocator_v2.py').read())" 2>/dev/null; then
    pass "Syntax: gpu_allocator_v2.py valid"
else
    fail "Syntax: gpu_allocator_v2.py invalid"
fi

# Bash syntax checks
if bash -n scripts/system/deploy.sh 2>/dev/null; then
    pass "Syntax: deploy.sh valid"
else
    fail "Syntax: deploy.sh invalid"
fi

if bash -n config/deploy/profile.d/ds01-gpu-awareness.sh 2>/dev/null; then
    pass "Syntax: ds01-gpu-awareness.sh valid"
else
    fail "Syntax: ds01-gpu-awareness.sh invalid"
fi

echo ""
echo "POST-DEPLOY CHECKS (require sudo deploy):"
echo ""

# SC2: Non-admin can run commands (check symlink targets are executable)
if [ -x "$(readlink -f /usr/local/bin/ds01-events 2>/dev/null)" ] 2>/dev/null; then
    pass "SC2: ds01-events executable"
else
    fail "SC2: ds01-events not executable or not deployed"
fi

if [ -x "$(readlink -f /usr/local/bin/ds01-workloads 2>/dev/null)" ] 2>/dev/null; then
    pass "SC2: ds01-workloads executable"
else
    fail "SC2: ds01-workloads not executable or not deployed"
fi

# SC4: mlc-create is symlink
if [ -L /usr/local/bin/mlc-create ] 2>/dev/null; then
    pass "SC4: mlc-create is symlink"
else
    fail "SC4: mlc-create is not a symlink or not deployed"
fi

# SC14: Grant dir traversable (711)
if [ -d /var/lib/ds01/bare-metal-grants ] 2>/dev/null && \
   stat -c '%a' /var/lib/ds01/bare-metal-grants 2>/dev/null | grep -q '711'; then
    pass "SC14: Grant directory is 711 (traversable)"
else
    fail "SC14: Grant directory missing or wrong permissions"
fi

# SC15: Grant file creation via bare-metal-access (verify script exists)
if [ -x scripts/admin/bare-metal-access ]; then
    pass "SC15: Grant file creation via bare-metal-access"
else
    fail "SC15: bare-metal-access script missing or not executable"
fi

# SC16: events.jsonl group-writable (664 docker)
if stat -c '%a %G' /var/log/ds01/events.jsonl 2>/dev/null | grep -q '664.*docker'; then
    pass "SC16: events.jsonl is 664 docker (group-writable)"
else
    fail "SC16: events.jsonl missing or wrong permissions/group"
fi

# SC17: resource-limits.yaml readable by all (644)
if stat -c '%a' /opt/ds01-infra/config/resource-limits.yaml 2>/dev/null | grep -q '644'; then
    pass "SC17: resource-limits.yaml is 644 (readable)"
else
    fail "SC17: resource-limits.yaml wrong permissions"
fi

echo ""
echo "CROSS-PHASE UAT CHECKS:"
echo ""

# UAT-1: events.jsonl writable (same as SC16)
if stat -c '%a %G' /var/log/ds01/events.jsonl 2>/dev/null | grep -q '664.*docker'; then
    pass "UAT-1: Event logging writable by non-root"
else
    fail "UAT-1: Event logging not writable"
fi

# UAT-2: ds01-events executable (same as SC2)
if [ -x "$(readlink -f /usr/local/bin/ds01-events 2>/dev/null)" ] 2>/dev/null; then
    pass "UAT-2: ds01-events accessible to non-admin"
else
    fail "UAT-2: ds01-events not accessible"
fi

# UAT-3: DCGM exporter — out of scope for Phase 3.1
skip "UAT-3: DCGM exporter (monitoring phase)"

# UAT-4: Exemption paths — grant dir + config readable
if [ -d /var/lib/ds01/bare-metal-grants ] 2>/dev/null && \
   stat -c '%a' /var/lib/ds01/bare-metal-grants 2>/dev/null | grep -q '711' && \
   stat -c '%a' /opt/ds01-infra/config/resource-limits.yaml 2>/dev/null | grep -q '644'; then
    pass "UAT-4: Exemption paths accessible (grant dir + config)"
else
    fail "UAT-4: Exemption paths not accessible"
fi

# UAT-5: Same as SC14 (grant dir)
if [ -d /var/lib/ds01/bare-metal-grants ] 2>/dev/null && \
   stat -c '%a' /var/lib/ds01/bare-metal-grants 2>/dev/null | grep -q '711'; then
    pass "UAT-5: Grant directory traversable"
else
    fail "UAT-5: Grant directory not traversable"
fi

# UAT-6: Container isolation — manual test needed (checkpoint)
skip "UAT-6: Container isolation (manual verification required)"

# UAT-7: Isolation mode — same as SC13
if grep -q 'DS01_ISOLATION_MODE:-full' scripts/docker/docker-wrapper.sh 2>/dev/null; then
    pass "UAT-7: Isolation mode enforcing by default"
else
    fail "UAT-7: Isolation mode not enforcing"
fi

# UAT-8: Profile.d permissions (all should be 644)
ALL_PROFILE_CORRECT=true
for f in /etc/profile.d/ds01-*.sh; do
    if [ -f "$f" ]; then
        perms=$(stat -c '%a' "$f" 2>/dev/null)
        if [ "$perms" != "644" ]; then
            fail "UAT-8: $f has $perms (expected 644)"
            ALL_PROFILE_CORRECT=false
        fi
    fi
done

if [ "$ALL_PROFILE_CORRECT" = true ]; then
    if ls /etc/profile.d/ds01-*.sh >/dev/null 2>&1; then
        pass "UAT-8: All profile.d scripts are 644"
    else
        fail "UAT-8: No profile.d scripts deployed"
    fi
fi

echo ""
echo "========================================"
echo "SUMMARY"
echo "========================================"
echo "PASSED: $PASS"
echo "FAILED: $FAIL"
echo "SKIPPED: $SKIP"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "\033[0;32m✓ All checks passed!\033[0m"
    exit 0
else
    echo -e "\033[0;31m✗ Some checks failed. Review output above.\033[0m"
    exit 1
fi
