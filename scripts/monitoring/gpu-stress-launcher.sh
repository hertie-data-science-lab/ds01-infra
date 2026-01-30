#!/bin/bash
# GPU Stress Test Launcher - Interactive dashboard validation tool
# Helps launch multiple GPU stress tests to validate Grafana dashboards

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRESS_SCRIPT="$SCRIPT_DIR/gpu-stress-test.py"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}    DS01 GPU Stress Test Launcher - Dashboard Validation${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo

# Check if PyTorch is available
if ! python3 -c "import torch" 2>/dev/null; then
    echo -e "${YELLOW}WARNING: PyTorch not found.${NC}"
    echo "The stress test requires PyTorch or CuPy for GPU compute."
    echo
    echo "Install PyTorch with:"
    echo "  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
    echo
    echo "Or see monitoring/requirements.txt for other options."
    echo
fi

# Show available GPUs
echo -e "${GREEN}Available GPU Devices:${NC}"
nvidia-smi --query-gpu=index,name,mig.mode.current --format=csv,noheader | while IFS=, read -r idx name mig; do
    echo "  GPU $idx: $name (MIG: $mig)"
done
echo

# Show MIG instances if any
if nvidia-smi -L | grep -q "MIG"; then
    echo -e "${GREEN}MIG Instances:${NC}"
    nvidia-smi -L | grep "MIG" | nl -v 0 -w 1 -s ': '
    echo
fi

echo "Example commands:"
echo -e "  ${YELLOW}# Start stress tests on multiple devices${NC}"
echo "  python3 $STRESS_SCRIPT --device 0 --target-util 70 &"
echo "  python3 $STRESS_SCRIPT --device 3 --target-util 85 &"
echo "  python3 $STRESS_SCRIPT --device 4 --target-util 60 &"
echo
echo -e "  ${YELLOW}# View running tests${NC}"
echo "  ps aux | grep gpu-stress-test"
echo
echo -e "  ${YELLOW}# Stop all tests${NC}"
echo "  pkill -f gpu-stress-test.py"
echo
echo -e "  ${YELLOW}# Monitor GPU status${NC}"
echo "  watch -n 1 nvidia-smi"
echo
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# Interactive mode
echo
read -p "Launch stress tests interactively? (y/n): " launch

if [[ "$launch" != "y" ]]; then
    echo "Exiting."
    exit 0
fi

echo

# Get device IDs to stress
read -p "Enter GPU device IDs to stress (space-separated, e.g., '0 3 4'): " devices

if [[ -z "$devices" ]]; then
    echo "No devices specified. Exiting."
    exit 0
fi

# Get duration
read -p "Duration in seconds (press Enter for infinite): " duration
duration_arg=""
if [[ -n "$duration" ]]; then
    duration_arg="--duration $duration"
fi

echo
echo -e "${GREEN}Launching stress tests...${NC}"

# Launch stress tests
for device in $devices; do
    read -p "Target utilization for device $device (10-100%, default 80): " util
    util=${util:-80}

    echo -e "${BLUE}Starting stress test on device $device at ${util}% utilization${NC}"
    nohup python3 "$STRESS_SCRIPT" --device "$device" --target-util "$util" $duration_arg \
        > "/tmp/gpu-stress-device-${device}.log" 2>&1 &

    pid=$!
    echo "  → PID: $pid, Log: /tmp/gpu-stress-device-${device}.log"
done

echo
echo -e "${GREEN}✓ Stress tests launched!${NC}"
echo
echo "Monitor with:"
echo "  watch -n 1 nvidia-smi"
echo "  dashboard  # DS01 dashboard"
echo "  tail -f /tmp/gpu-stress-device-*.log"
echo
echo "Stop all with:"
echo "  pkill -f gpu-stress-test.py"
