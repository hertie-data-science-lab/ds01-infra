#!/usr/bin/env python3
"""
Unit Tests: GPU-equivalents (gpueq) fraction helpers

Covers the SHARED canonical helpers added to gpu-state-reader.py for fractional
GPU accounting under MIG. The helpers compute a COMPUTE-slice fraction (the
canonical quota/capacity unit) and a MEMORY fraction per allocation, derived
live from the MIG profile. These tests use synthetic profiles and a stubbed
slices-per-GPU so they run without real MIG hardware (all DS01 GPUs are full
today, so live MIG can't be exercised on the box).
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
    inst = module.GPUStateReader()
    # Pin slices-per-GPU to the A100/H100 canonical value so the compute-fraction
    # arithmetic is deterministic without querying live MIG topology.
    inst._slices_per_gpu = lambda: 7
    return inst


# =============================================================================
# Static profile parsers (pure functions, no hardware)
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

    def test_parse_memory_gb(self, reader):
        assert reader._parse_mig_memory_gb("1g.10gb") == 10.0
        assert reader._parse_mig_memory_gb("3g.20gb") == 20.0
        assert reader._parse_mig_memory_gb("7g.40gb") == 40.0

    def test_parse_memory_gb_unparseable(self, reader):
        assert reader._parse_mig_memory_gb("") == 0.0
        assert reader._parse_mig_memory_gb(None) == 0.0
        assert reader._parse_mig_memory_gb("3g") == 0.0


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
# Memory fraction (companion metric, for visibility)
# =============================================================================


class TestMemoryFraction:
    def test_full_gpu_is_one(self, reader):
        assert reader.get_slot_memory_fraction("0") == 1.0

    def test_mig_memory_fraction(self, reader):
        # 10 GB MIG instance on a 40 GB A100 -> 0.25.
        assert reader.get_slot_memory_fraction("1.2", "1g.10gb", gpu_total_gb=40.0) == pytest.approx(
            0.25
        )
        assert reader.get_slot_memory_fraction("0.0", "3g.20gb", gpu_total_gb=40.0) == pytest.approx(
            0.5
        )

    def test_mig_memory_fraction_default_total(self, reader):
        # Default gpu_total_gb is 40 (A100-40GB).
        assert reader.get_slot_memory_fraction("1.0", "1g.10gb") == pytest.approx(0.25)

    def test_mig_memory_fraction_unparseable(self, reader):
        assert reader.get_slot_memory_fraction("1.0", "") == 0.0


# =============================================================================
# slices-per-GPU live derivation (default fallback)
# =============================================================================


class TestSlicesPerGpu:
    def test_default_fallback_is_seven(self):
        # With no MIG profiles present, _slices_per_gpu falls back to 7
        # (A100/H100 canonical) rather than a hardcoded mig_instances_per_gpu.
        module = _load_reader_module()
        inst = module.GPUStateReader()
        inst._get_present_mig_profiles = lambda: []
        assert inst._slices_per_gpu() == 7

    def test_derives_max_from_present_profiles(self):
        # Heterogeneous MIG: the largest profile's slice count defines the GPU's
        # total slices (so a 7g instance is recognised as a full GPU).
        module = _load_reader_module()
        inst = module.GPUStateReader()
        inst._get_present_mig_profiles = lambda: ["1g.10gb", "3g.20gb", "7g.40gb"]
        assert inst._slices_per_gpu() == 7


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
