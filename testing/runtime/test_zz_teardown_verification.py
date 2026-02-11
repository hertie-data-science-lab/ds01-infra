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

pytestmark = [pytest.mark.runtime]

# Expected production values (must match resource-limits.yaml defaults)
EXPECTED = {
    "policies.grace_period": "30m",
    "policies.created_container_timeout": "30m",
    "defaults.idle_timeout": "0.5h",
    "defaults.container_hold_after_stop": "0.5h",
}


def test_config_restored_after_lifecycle_tests():
    """Production config must be restored after lifecycle tests."""
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    policies = config.get("policies", {})
    defaults = config.get("defaults", {})

    values = {
        "policies.grace_period": policies.get("grace_period"),
        "policies.created_container_timeout": policies.get("created_container_timeout"),
        "defaults.idle_timeout": defaults.get("idle_timeout"),
        "defaults.container_hold_after_stop": defaults.get("container_hold_after_stop"),
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
    assert not disabled.exists(), (
        "Cron file still disabled — test teardown did not re-enable it"
    )
