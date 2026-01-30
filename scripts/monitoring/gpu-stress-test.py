#!/usr/bin/env python3
"""
GPU Stress Test Script for DS01 Dashboard Validation

Generates compute load on specified GPUs/MIG instances to validate monitoring dashboards.
Runs continuous matrix multiplications to stress both compute and memory.

Usage:
    # Stress GPU 0
    python3 gpu-stress-test.py --device 0

    # Stress MIG instance 2.0 (use CUDA device ID from nvidia-smi)
    python3 gpu-stress-test.py --device 3

    # Stress with specific utilization target (50%)
    python3 gpu-stress-test.py --device 0 --target-util 50

    # Run multiple instances for different devices
    python3 gpu-stress-test.py --device 0 &
    python3 gpu-stress-test.py --device 3 &
    python3 gpu-stress-test.py --device 4 &
"""

import argparse
import time
import sys
import os

def stress_test_pytorch(device_id: int, target_util: int = 100, duration: int = None):
    """Run stress test using PyTorch"""
    try:
        import torch
    except ImportError:
        print("ERROR: PyTorch not installed.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install PyTorch with:", file=sys.stderr)
        print("  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or see monitoring/requirements.txt for other options", file=sys.stderr)
        return False

    try:
        device = torch.device(f"cuda:{device_id}")

        # Get device name
        device_name = torch.cuda.get_device_name(device_id)
        print(f"Starting stress test on device {device_id}: {device_name}")
        print(f"Target utilization: {target_util}%")
        if duration:
            print(f"Duration: {duration} seconds")
        else:
            print("Duration: infinite (press Ctrl+C to stop)")

        # Determine matrix size based on target utilization
        # Larger matrices = higher utilization
        base_size = 4096
        if target_util < 30:
            matrix_size = 2048
            sleep_time = 0.5
        elif target_util < 60:
            matrix_size = 4096
            sleep_time = 0.2
        elif target_util < 90:
            matrix_size = 6144
            sleep_time = 0.05
        else:
            matrix_size = 8192
            sleep_time = 0.01

        print(f"Matrix size: {matrix_size}x{matrix_size}")
        print("-" * 60)

        # Initialize matrices
        a = torch.randn(matrix_size, matrix_size, device=device)
        b = torch.randn(matrix_size, matrix_size, device=device)

        start_time = time.time()
        iteration = 0

        while True:
            # Perform matrix multiplication
            c = torch.matmul(a, b)

            # Force synchronization to ensure compute completes
            torch.cuda.synchronize()

            iteration += 1

            # Print status every 100 iterations
            if iteration % 100 == 0:
                elapsed = time.time() - start_time
                print(f"[{elapsed:.1f}s] Iteration {iteration} on device {device_id}")

            # Sleep to control utilization
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Check duration limit
            if duration and (time.time() - start_time) >= duration:
                print(f"\nCompleted {duration}s stress test on device {device_id}")
                break

    except KeyboardInterrupt:
        print(f"\n\nStopped stress test on device {device_id}")
        return True
    except Exception as e:
        print(f"ERROR on device {device_id}: {e}", file=sys.stderr)
        return False

    return True

def stress_test_cupy(device_id: int, target_util: int = 100, duration: int = None):
    """Run stress test using CuPy (fallback if PyTorch unavailable)"""
    try:
        import cupy as cp
    except ImportError:
        print("ERROR: CuPy not installed. Install with: pip install cupy-cuda12x", file=sys.stderr)
        return False

    try:
        with cp.cuda.Device(device_id):
            print(f"Starting stress test on device {device_id} using CuPy")
            print(f"Target utilization: {target_util}%")

            # Determine matrix size based on target utilization
            if target_util < 30:
                matrix_size = 2048
                sleep_time = 0.5
            elif target_util < 60:
                matrix_size = 4096
                sleep_time = 0.2
            elif target_util < 90:
                matrix_size = 6144
                sleep_time = 0.05
            else:
                matrix_size = 8192
                sleep_time = 0.01

            print(f"Matrix size: {matrix_size}x{matrix_size}")
            print("-" * 60)

            # Initialize matrices
            a = cp.random.randn(matrix_size, matrix_size, dtype=cp.float32)
            b = cp.random.randn(matrix_size, matrix_size, dtype=cp.float32)

            start_time = time.time()
            iteration = 0

            while True:
                # Perform matrix multiplication
                c = cp.matmul(a, b)

                # Force synchronization
                cp.cuda.Stream.null.synchronize()

                iteration += 1

                if iteration % 100 == 0:
                    elapsed = time.time() - start_time
                    print(f"[{elapsed:.1f}s] Iteration {iteration} on device {device_id}")

                if sleep_time > 0:
                    time.sleep(sleep_time)

                if duration and (time.time() - start_time) >= duration:
                    print(f"\nCompleted {duration}s stress test on device {device_id}")
                    break

    except KeyboardInterrupt:
        print(f"\n\nStopped stress test on device {device_id}")
        return True
    except Exception as e:
        print(f"ERROR on device {device_id}: {e}", file=sys.stderr)
        return False

    return True

def main():
    parser = argparse.ArgumentParser(
        description="GPU stress test for DS01 dashboard validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stress full GPU 0 at 100%
  python3 gpu-stress-test.py --device 0

  # Stress MIG instance (device 3) at 50% utilization
  python3 gpu-stress-test.py --device 3 --target-util 50

  # Run for 300 seconds then stop
  python3 gpu-stress-test.py --device 0 --duration 300

  # Run multiple instances in background
  python3 gpu-stress-test.py --device 0 --target-util 70 &
  python3 gpu-stress-test.py --device 3 --target-util 80 &
  python3 gpu-stress-test.py --device 4 --target-util 60 &

  # Stop all background tests
  pkill -f gpu-stress-test.py

Note: Use nvidia-smi to see CUDA device IDs for MIG instances
        """
    )
    parser.add_argument(
        "--device", "-d",
        type=int,
        required=True,
        help="CUDA device ID to stress test (see nvidia-smi)"
    )
    parser.add_argument(
        "--target-util", "-u",
        type=int,
        default=100,
        choices=range(10, 101),
        metavar="10-100",
        help="Target GPU utilization percentage (default: 100)"
    )
    parser.add_argument(
        "--duration", "-t",
        type=int,
        default=None,
        help="Duration in seconds (default: infinite, stop with Ctrl+C)"
    )
    parser.add_argument(
        "--backend",
        choices=["pytorch", "cupy"],
        default="pytorch",
        help="Backend to use for compute (default: pytorch)"
    )

    args = parser.parse_args()

    # Check CUDA is available
    if not os.path.exists("/dev/nvidiactl"):
        print("ERROR: NVIDIA GPU not detected", file=sys.stderr)
        sys.exit(1)

    # Run stress test
    if args.backend == "pytorch":
        success = stress_test_pytorch(args.device, args.target_util, args.duration)
    else:
        success = stress_test_cupy(args.device, args.target_util, args.duration)

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
