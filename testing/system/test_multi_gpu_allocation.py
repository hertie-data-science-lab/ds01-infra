"""System tests for multi-GPU allocation path (allocate-multi).

Exercises the real allocator + wrapper end-to-end:
  * allocate-multi emits N distinct GPU UUIDs
  * wrapper rewrites --gpus N into --gpus device=UUID1,UUID2 and labels the
    container with the slot set
  * quota violations fast-fail (no 180s retry spin)

All tests run as ds01-ci-bot (3-GPU budget) via sudo. Marked @pytest.mark.system
so they only run on the self-hosted GPU runner.
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

GPU_ALLOCATOR = "/opt/ds01-infra/scripts/docker/gpu_allocator_v2.py"
TEST_USER = "ds01-ci-bot"
# Alpine is a ~5MB image; we only need a container handle for label/cgroup checks,
# not actual GPU compute. nvidia-container-toolkit still attaches the GPU device.
TEST_IMAGE = "alpine:latest"


def _alloc_cli(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Invoke gpu_allocator_v2.py as ds01-ci-bot via sudo."""
    return subprocess.run(
        ["sudo", "-u", TEST_USER, "python3", GPU_ALLOCATOR, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _sudo_docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Invoke the docker wrapper as ds01-ci-bot (exercises the real wrapper path)."""
    return subprocess.run(
        ["sudo", "-u", TEST_USER, "/usr/local/bin/docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _real_docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Bypass the wrapper (for teardown inspection)."""
    return subprocess.run(
        ["/usr/bin/docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _parse_kv(stdout: str, key: str) -> str | None:
    """Extract `KEY=VALUE` from allocator CLI stdout."""
    for line in stdout.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


@pytest.fixture
def probe_container_name() -> str:
    """Unique container name used as allocate-multi's state key; cleaned up after."""
    name = f"ds01-test-multi-{uuid.uuid4().hex[:8]}"
    yield name
    _real_docker("rm", "-f", name, timeout=15)


@pytest.mark.system
@pytest.mark.requires_gpu
def test_allocate_multi_returns_distinct_uuids(probe_container_name: str) -> None:
    """allocate-multi ds01-ci-bot <name> 2 emits DOCKER_IDS with 2 distinct UUIDs."""
    result = _alloc_cli("allocate-multi", TEST_USER, probe_container_name, "2")

    assert result.returncode == 0, f"allocate-multi failed: {result.stderr}\n{result.stdout}"

    docker_ids = _parse_kv(result.stdout, "DOCKER_IDS")
    assert docker_ids, f"DOCKER_IDS not in output:\n{result.stdout}"

    uuids = docker_ids.split(",")
    assert len(uuids) == 2, f"expected 2 UUIDs, got {len(uuids)}: {uuids}"
    assert len(set(uuids)) == 2, f"UUIDs must be distinct: {uuids}"
    assert all(u.startswith(("GPU-", "MIG-")) for u in uuids), f"bad UUID format: {uuids}"


@pytest.mark.system
@pytest.mark.requires_gpu
def test_wrapper_labels_container_with_multi_gpu_slots(probe_container_name: str) -> None:
    """docker run --gpus 2 --label ds01.interface=api: wrapper records both slots on the container."""
    # `create` so we don't need the container's payload to actually run
    create = _sudo_docker(
        "create",
        "--name",
        probe_container_name,
        "--label",
        "ds01.interface=api",
        "--gpus",
        "2",
        TEST_IMAGE,
        "true",
    )
    assert create.returncode == 0, (
        f"docker create --gpus 2 failed (exit={create.returncode})\n"
        f"stdout: {create.stdout}\nstderr: {create.stderr}"
    )

    inspect = _real_docker(
        "inspect", "--format", '{{index .Config.Labels "ds01.gpu_slot"}}', probe_container_name
    )
    assert inspect.returncode == 0, inspect.stderr

    gpu_slot_label = inspect.stdout.strip()
    uuids = gpu_slot_label.split(",")
    assert len(uuids) == 2, (
        f"ds01.gpu_slot should carry 2 UUIDs, got {len(uuids)}: {gpu_slot_label}"
    )
    assert len(set(uuids)) == 2, f"UUIDs must be distinct: {uuids}"


@pytest.mark.system
@pytest.mark.requires_gpu
def test_allocate_multi_quota_exceeded_fast_fails(probe_container_name: str) -> None:
    """Requesting more GPUs than any sensible limit returns EXCEEDS_* immediately, no retry spin."""
    result = _alloc_cli("allocate-multi", TEST_USER, probe_container_name, "99", timeout=10)

    assert result.returncode != 0, f"99 GPUs shouldn't succeed:\n{result.stdout}"
    assert "EXCEEDS_" in result.stdout + result.stderr, (
        f"expected EXCEEDS_TOTAL_LIMIT or EXCEEDS_CONTAINER_LIMIT, got:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.system
@pytest.mark.requires_gpu
def test_wrapper_rejects_multi_gpu_without_name() -> None:
    """Wrapper auto-generates --name for N>1, so the alloc succeeds. Teardown via auto-name pattern."""
    # docker run --gpus 2 without --name should now succeed (auto-name fix in #43).
    # The container won't actually do anything (alpine true exits immediately).
    result = _sudo_docker(
        "run",
        "--rm",
        "--label",
        "ds01.interface=api",
        "--gpus",
        "2",
        TEST_IMAGE,
        "true",
        timeout=60,
    )
    # Expect success — auto-naming kicks in, allocator succeeds, container runs+exits.
    assert result.returncode == 0, (
        f"--gpus 2 without --name should succeed via auto-name; got exit={result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
