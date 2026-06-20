"""
Verify that runtime test teardown restored production config and cron.

This file runs AFTER test_container_lifecycle.py (alphabetical ordering) to
confirm the lowered_timeouts fixture correctly restored everything. By running
in a separate module, we're guaranteed the module-scoped fixtures from
test_container_lifecycle have already torn down.
"""

from pathlib import Path

import pytest
import yaml

from .conftest import CONFIG_FILE, CRON_FILE

pytestmark = [pytest.mark.system]

# Expected production values (must match resource-limits.yaml defaults)
EXPECTED = {
    "policies.grace_period_m": 30,
    "policies.created_container_timeout_m": 30,
    "defaults.idle_timeout_h": 0.5,
    "defaults.container_hold_after_stop_h": 0.5,
}


def test_config_restored_after_lifecycle_tests():
    """Production config must be restored after lifecycle tests."""
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    policies = config.get("policies", {})
    defaults = config.get("defaults", {})

    values = {
        "policies.grace_period_m": policies.get("grace_period_m"),
        "policies.created_container_timeout_m": policies.get("created_container_timeout_m"),
        "defaults.idle_timeout_h": defaults.get("idle_timeout_h"),
        "defaults.container_hold_after_stop_h": defaults.get("container_hold_after_stop_h"),
    }

    for key, expected in EXPECTED.items():
        actual = values[key]
        assert actual == expected, (
            f"{key} not restored: got {actual!r}, expected {expected!r}. "
            "The lowered_timeouts fixture teardown may have failed."
        )


def test_cron_restored_after_lifecycle_tests():
    """Lifecycle cron must be re-enabled after tests."""
    assert CRON_FILE.exists(), (
        f"Cron file not restored: {CRON_FILE} missing. "
        "Look for /etc/cron.d/ds01-maintenance.disabled-by-test"
    )

    disabled = Path("/etc/cron.d/ds01-maintenance.disabled-by-test")
    assert not disabled.exists(), "Cron file still disabled — test teardown did not re-enable it"
