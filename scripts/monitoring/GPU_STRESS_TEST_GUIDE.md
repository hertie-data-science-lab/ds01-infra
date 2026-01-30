# GPU Stress Test Guide

Tools for validating DS01 Grafana dashboards by generating controlled GPU load.

## Quick Start

### Interactive Launcher (Recommended)
```bash
/opt/ds01-infra/scripts/monitoring/gpu-stress-launcher.sh
```

This will:
1. Show available GPUs and MIG instances
2. Prompt for devices to stress test
3. Set target utilization for each device
4. Launch tests in background

### Manual Launch

Stress a single device:
```bash
python3 /opt/ds01-infra/scripts/monitoring/gpu-stress-test.py --device 0 --target-util 80
```

Run multiple devices in background:
```bash
# Full GPU 0 at 70%
python3 /opt/ds01-infra/scripts/monitoring/gpu-stress-test.py --device 0 --target-util 70 &

# MIG instance (device 3) at 85%
python3 /opt/ds01-infra/scripts/monitoring/gpu-stress-test.py --device 3 --target-util 85 &

# MIG instance (device 4) at 60%
python3 /opt/ds01-infra/scripts/monitoring/gpu-stress-test.py --device 4 --target-util 60 &
```

## Finding Device IDs

Use `nvidia-smi` to see CUDA device IDs:
```bash
nvidia-smi -L
```

Output example:
```
GPU 0: NVIDIA A100-SXM4-80GB (UUID: GPU-...)
GPU 1: NVIDIA A100-SXM4-80GB (UUID: GPU-...)
GPU 2: NVIDIA A100-SXM4-80GB (UUID: GPU-...)
  MIG 3g.40gb     Device  0: (UUID: MIG-...)  # Device 3
  MIG 3g.40gb     Device  1: (UUID: MIG-...)  # Device 4
...
```

## Monitoring

### Grafana Dashboard
Open the DS01 Overview dashboard at http://<server>:3000 and observe:
- **Utilisation %** panels showing real-time GPU load
- **Memory %** panels showing memory usage
- **Avg Utilisation** showing aggregate across devices
- **Temperature** and **Power** changing with load

### Command Line
```bash
# Real-time GPU status
watch -n 1 nvidia-smi

# DS01 dashboard (terminal UI)
dashboard

# View stress test logs
tail -f /tmp/gpu-stress-device-*.log
```

## Stopping Tests

Stop all running stress tests:
```bash
pkill -f gpu-stress-test.py
```

Stop specific test:
```bash
kill <PID>  # Find PID with: ps aux | grep gpu-stress-test
```

## Validation Checklist

Run stress tests and verify these dashboard metrics update correctly:

- [ ] **Slots Used** - Shows correct count of allocated MIG/GPU slots
- [ ] **Utilisation %** per device - Matches target utilization
- [ ] **Memory %** per device - Shows memory usage increasing
- [ ] **Avg Utilisation** - Aggregates correctly across devices
- [ ] **Max Temp** - Temperature increases under load
- [ ] **Total Power** - Power draw increases with utilization
- [ ] **GPU-Hours** - Counter increments over time
- [ ] Time series graphs show utilization trends

## Tips

- Start with lower utilization (50-70%) to observe gradual changes
- Run tests for at least 2-3 minutes to see dashboard trends
- Compare full GPU vs MIG instance behaviour
- Check that disaggregated metrics (MIG vs Full GPU) update independently
- Validate temperature/power metrics work for both MIG-partitioned and full GPUs

## Requirements

The stress test requires PyTorch or CuPy for GPU compute. These are **optional dependencies** - not required for core DS01 functionality.

### Option 1: Install from monitoring requirements (Recommended)
```bash
cd /opt/ds01-infra
# Edit monitoring/requirements.txt to uncomment your preferred backend
pip install -r monitoring/requirements.txt
```

### Option 2: Install PyTorch directly
```bash
# For CUDA 12.1 (most common)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# For other CUDA versions, see: https://pytorch.org/get-started/locally/
```

### Option 3: Install CuPy (lighter alternative)
```bash
pip install cupy-cuda12x
```

## Troubleshooting

**Error: "PyTorch not installed"**
- Install PyTorch or use `--backend cupy`

**Error: "CUDA device not found"**
- Check device ID with `nvidia-smi -L`
- Ensure GPU is not already fully allocated

**Low utilization despite high target**
- GPU may be throttling due to temperature
- Check `nvidia-smi` for thermal/power limits
- Reduce target utilization or increase cooling
