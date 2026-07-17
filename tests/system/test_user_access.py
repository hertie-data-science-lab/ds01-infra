"""
Role-based access guards — the USER role's runtime access.

These assert the invariant that an unprivileged (non-owner, non-admin) user can
reach and execute the DS01 command surface, and read the deploy state that
user-facing commands depend on.

Motivation: a detached-prod rsync release from a umask-077 staging clone once
propagated 0700 directory perms onto /opt/ds01-infra (and 0700/0600 onto the
deploy state), silently locking every regular user out of every command and out
of `version`. Nothing caught it until a human ran `container list` by hand.
These tests make that whole failure mode loud, in CI on the live box.

They complement the admin/functional system tests (allocation, lifecycle) that
exercise the privileged path; see the `admin_role` marker.
"""

import os
import stat
from pathlib import Path

import pytest

pytestmark = [pytest.mark.system, pytest.mark.user_role]

INFRA_ROOT = Path("/opt/ds01-infra")
LOCAL_BIN = Path("/usr/local/bin")
DEPLOY_STATE = Path("/var/lib/ds01/deploy")

# Directories a regular user must traverse (o+x) to run commands and read config.
RUNTIME_DIRS = [
    INFRA_ROOT,
    INFRA_ROOT / "scripts",
    INFRA_ROOT / "scripts" / "user",
    INFRA_ROOT / "scripts" / "user" / "dispatchers",
    INFRA_ROOT / "scripts" / "docker",
    INFRA_ROOT / "config",
    INFRA_ROOT / "config" / "runtime",
]

# User-facing commands that must resolve to an other-readable+executable target.
USER_COMMANDS = ["container", "image", "project", "user", "check", "get"]


def _mode(p: Path) -> int:
    return stat.S_IMODE(os.stat(p).st_mode)


@pytest.mark.parametrize("d", RUNTIME_DIRS, ids=str)
def test_runtime_dir_is_world_traversable(d):
    """Runtime dirs must be o+x so a non-owner can traverse to the command surface."""
    assert d.is_dir(), f"{d} is missing"
    mode = _mode(d)
    assert mode & stat.S_IXOTH, (
        f"{d} is {oct(mode)} — not world-traversable (o+x); non-owner users cannot "
        f"reach the command surface. Enforced by permissions-manifest.sh (runtime dirs) "
        f"and ds01-sync's rsync --chmod=D755."
    )


@pytest.mark.parametrize("cmd", USER_COMMANDS, ids=str)
def test_user_command_executable_by_others(cmd):
    """Each deployed command must resolve to a target 'other' can read + execute,
    with every parent directory traversable — else users get 'permission denied'."""
    link = LOCAL_BIN / cmd
    if not link.exists():
        pytest.skip(f"{link} not deployed")
    target = link.resolve()
    assert target.exists(), f"{link} -> {target} is dangling"
    mode = _mode(target)
    assert (mode & stat.S_IXOTH) and (mode & stat.S_IROTH), (
        f"{target} is {oct(mode)} — not other-readable+executable; a regular user "
        f"gets 'permission denied: {cmd}'."
    )
    for parent in target.parents:
        if parent == Path("/"):
            break
        assert _mode(parent) & stat.S_IXOTH, (
            f"{parent} ({oct(_mode(parent))}) blocks non-owner traversal to {target}."
        )


def test_deploy_state_readable_by_non_root():
    """`version` (a user command) reads /var/lib/ds01/deploy/current-sha; the dir
    must be traversable and current-sha other-readable, or version shows 'unknown'."""
    if not DEPLOY_STATE.exists():
        pytest.skip(f"{DEPLOY_STATE} not present (prod not cut over?)")
    assert _mode(DEPLOY_STATE) & stat.S_IXOTH, (
        f"{DEPLOY_STATE} is {oct(_mode(DEPLOY_STATE))} — not world-traversable."
    )
    current_sha = DEPLOY_STATE / "current-sha"
    if not current_sha.exists():
        pytest.skip("current-sha not written yet")
    assert _mode(current_sha) & stat.S_IROTH, (
        f"{current_sha} is {oct(_mode(current_sha))} — not other-readable; "
        f"`version` will report 'unknown'."
    )
