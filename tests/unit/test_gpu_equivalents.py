#!/usr/bin/env python3
"""
Unit Tests: GPU-equivalents (gpueq) fraction helpers

Covers the SHARED canonical helpers added to gpu-state-reader.py for fractional
GPU accounting under MIG. The helpers compute a COMPUTE-slice fraction (the
canonical quota/capacity unit) per allocation: 1.0 for a full GPU, else
compute_slices / 7 for a MIG instance. These tests use synthetic profiles so
they run without real MIG hardware (all DS01 GPUs are full today, so live MIG
can't be exercised on the box).
"""

import importlib.util
from pathlib import Path

import pytest

# Load the dash-named reader module by file path. We test the in-repo source
# (two levels up from this test file) so the tests validate the branch under
# review, not whatever happens to be deployed at /opt/ds01-infra.
_READER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "docker" / "gpu-state-reader.py"


def _load_reader_module():
    spec = importlib.util.spec_from_file_location("gpu_state_reader_gpueq", str(_READER_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def reader():
    module = _load_reader_module()
    return module.GPUStateReader()


# =============================================================================
# Static profile parser (pure function, no hardware)
# =============================================================================


class TestProfileParsers:
    def test_parse_compute_slices(self, reader):
        assert reader._parse_mig_compute_slices("1g.10gb") == 1
        assert reader._parse_mig_compute_slices("3g.20gb") == 3
        assert reader._parse_mig_compute_slices("7g.40gb") == 7

    def test_parse_compute_slices_unparseable(self, reader):
        assert reader._parse_mig_compute_slices("") == 0
        assert reader._parse_mig_compute_slices(None) == 0
        assert reader._parse_mig_compute_slices("garbage") == 0


# =============================================================================
# Compute-slice fraction (the canonical gpueq unit)
# =============================================================================


class TestComputeFraction:
    def test_full_gpu_is_one(self, reader):
        # Full GPU slot "0" -> 1.0 regardless of profile.
        assert reader.get_slot_compute_fraction("0") == 1.0
        assert reader.get_slot_compute_fraction("3", profile="full") == 1.0

    def test_mig_1g(self, reader):
        # "1.2" is a MIG slot (dotted); 1g profile on a 7-slice GPU -> 1/7.
        assert reader.get_slot_compute_fraction("1.2", "1g.10gb") == pytest.approx(1 / 7)

    def test_mig_3g(self, reader):
        assert reader.get_slot_compute_fraction("0.0", "3g.20gb") == pytest.approx(3 / 7)

    def test_mig_7g_is_whole_gpu(self, reader):
        # A 7g MIG instance occupies the whole GPU -> 7/7 == 1.0.
        assert reader.get_slot_compute_fraction("2.0", "7g.40gb") == pytest.approx(1.0)

    def test_mig_unparseable_profile_is_zero(self, reader):
        assert reader.get_slot_compute_fraction("1.0", "") == 0.0
        assert reader.get_slot_compute_fraction("1.0", None) == 0.0


# =============================================================================
# slices-per-GPU (universal A100/H100 constant)
# =============================================================================


class TestSlicesPerGpu:
    def test_is_seven(self, reader):
        # A full GPU is always 7 compute slices; no per-device detection.
        assert reader._slices_per_gpu() == 7


# =============================================================================
# Per-user gpueq aggregation
# =============================================================================


class TestUserGpuEquivalents:
    def test_full_gpu_user_equals_slot_count(self, reader):
        # Two full GPUs -> 2.0 gpueq.
        reader.get_user_allocations = lambda user: [
            {"gpu_slots": ["0"], "gpu_profiles": [""]},
            {"gpu_slots": ["1"], "gpu_profiles": [""]},
        ]
        assert reader.get_user_gpu_equivalents("alice") == pytest.approx(2.0)

    def test_mig_user_sums_fractions(self, reader):
        # 1g + 3g MIG slices -> 1/7 + 3/7 = 4/7 gpueq.
        reader.get_user_allocations = lambda user: [
            {"gpu_slots": ["0.0", "0.1"], "gpu_profiles": ["1g.10gb", "3g.20gb"]},
        ]
        assert reader.get_user_gpu_equivalents("bob") == pytest.approx(4 / 7)

    def test_mixed_full_and_mig(self, reader):
        # One full GPU + one 1g MIG -> 1.0 + 1/7.
        reader.get_user_allocations = lambda user: [
            {"gpu_slots": ["2"], "gpu_profiles": [""]},
            {"gpu_slots": ["3.0"], "gpu_profiles": ["1g.10gb"]},
        ]
        assert reader.get_user_gpu_equivalents("carol") == pytest.approx(1.0 + 1 / 7)


# =============================================================================
# Null gpu_allocation section (regression: comments-only YAML -> None)
# =============================================================================


class TestNullGpuAllocationSection:
    """A comments-only `gpu_allocation:` block parses to None. `.get(key, {})`
    returns that None (the default only fills a *missing* key), so any downstream
    .get() crashed with AttributeError — and, since it fires once per enumerated
    GPU container, it took down every allocation and the stale-release cleanup as
    soon as one GPU container existed.
    """

    def _reader_with_config(self, tmp_path, body):
        cfg = tmp_path / "resource-limits.yaml"
        cfg.write_text(body)
        module = _load_reader_module()
        return module.GPUStateReader(config_path=str(cfg))

    def test_comments_only_section_defaults_not_crash(self, tmp_path):
        # `gpu_allocation:` with only comments under it -> None.
        reader = self._reader_with_config(
            tmp_path,
            "gpu_allocation:\n  # slots_per_gpu: 1  (all keys commented out)\n",
        )
        assert reader._get_mig_instances_per_gpu() == 1

    def test_missing_section_defaults(self, tmp_path):
        reader = self._reader_with_config(tmp_path, "defaults: {}\n")
        assert reader._get_mig_instances_per_gpu() == 1

    def test_populated_section_is_read(self, tmp_path):
        reader = self._reader_with_config(tmp_path, "gpu_allocation:\n  slots_per_gpu: 7\n")
        assert reader._get_mig_instances_per_gpu() == 7


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
