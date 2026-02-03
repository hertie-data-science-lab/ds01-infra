#!/bin/bash
# Verify CUDA_VISIBLE_DEVICES awareness layer is working correctly
# Run this as a regular user (not root) after deploying changes

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "DS01 GPU Awareness Layer Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

PASS=0
FAIL=0

# Test 1: CUDA_VISIBLE_DEVICES is set to empty string
echo "[1/4] Checking CUDA_VISIBLE_DEVICES environment variable..."
if [ "$CUDA_VISIBLE_DEVICES" = "" ]; then
    echo "  ✓ CUDA_VISIBLE_DEVICES is set to empty string"
    ((PASS++))
else
    echo "  ✗ CUDA_VISIBLE_DEVICES is not set correctly (value: '$CUDA_VISIBLE_DEVICES')"
    echo "    Expected: empty string"
    echo "    Run: logout and login again to apply profile.d changes"
    ((FAIL++))
fi
echo ""

# Test 2: nvidia-smi works and lists GPUs
echo "[2/4] Checking nvidia-smi functionality..."
if nvidia-smi -L &>/dev/null; then
    GPU_COUNT=$(nvidia-smi -L | wc -l)
    echo "  ✓ nvidia-smi works (found $GPU_COUNT GPU(s)/MIG instances)"
    ((PASS++))
else
    echo "  ✗ nvidia-smi failed"
    echo "    This indicates device permissions are still restricted"
    echo "    Run: sudo /opt/ds01-infra/scripts/system/restore-nvidia-defaults.sh"
    ((FAIL++))
fi
echo ""

# Test 3: PyTorch sees no GPUs (if PyTorch is installed)
echo "[3/4] Checking PyTorch CUDA visibility..."
if python3 -c "import torch" 2>/dev/null; then
    CUDA_AVAILABLE=$(python3 -c "import torch; print(torch.cuda.is_available())")
    if [ "$CUDA_AVAILABLE" = "False" ]; then
        echo "  ✓ PyTorch sees no GPUs (torch.cuda.is_available() = False)"
        ((PASS++))
    else
        echo "  ✗ PyTorch can see GPUs (torch.cuda.is_available() = True)"
        echo "    Expected: False (CUDA_VISIBLE_DEVICES should hide GPUs)"
        ((FAIL++))
    fi
else
    echo "  ~ PyTorch not installed (skipping test)"
fi
echo ""

# Test 4: Profile.d script exists
echo "[4/4] Checking GPU awareness profile script..."
if [ -f "/etc/profile.d/ds01-gpu-awareness.sh" ]; then
    echo "  ✓ /etc/profile.d/ds01-gpu-awareness.sh exists"
    ((PASS++))
else
    echo "  ✗ /etc/profile.d/ds01-gpu-awareness.sh not found"
    echo "    Run: sudo deploy"
    ((FAIL++))
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAIL -eq 0 ]; then
    echo "✓ All checks passed ($PASS/4)"
    echo ""
    echo "GPU awareness layer is working correctly:"
    echo "  • nvidia-smi works (GPU allocation pipeline functional)"
    echo "  • PyTorch sees no GPUs (awareness goal achieved)"
    echo "  • Users must use containers for GPU access"
else
    echo "! $FAIL checks failed, $PASS passed"
    echo ""
    echo "Fix required - see error messages above"
fi
echo ""
