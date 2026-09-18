"""Unit tests for ds01-deploy's refusal to move prod backwards.

`resolve_target` checks a `--ref` for shape, existence and ancestry of origin/main.
An old tag passes all three - it is well-formed, it is in the clone, and it is very
much an ancestor - so before `refuse_downgrade` existed, re-pushing `v1.0.0` would
put last January into production without a single warning.

The guard is exercised by sourcing the real script and replacing the two things
that talk to the outside world: `git_owner` (git in the staging clone, as the
checkout owner) and `current_sha` (the file under /var/lib/ds01). Everything in
between is the shipped code. The commits are a throwaway repo built here, so the
ancestry being asserted is real ancestry rather than a stubbed answer.
"""

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
SYNC = REPO / "scripts/system/sync.sh"


def _git(cwd, *args):
    # hooksPath is pointed at nothing on purpose: a throwaway fixture repo must not
    # run whatever hooks the developer has installed globally (this box has one that
    # enforces a committer identity, and it fails the fixture, not the code).
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    """A throwaway repo: old -> new on main, plus `side` diverging from old."""
    path = tmp_path_factory.mktemp("staging")
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    (path / "VERSION").write_text("1.0.0\n")
    _git(path, "add", "VERSION")
    _git(path, "commit", "-qm", "old")
    old = _git(path, "rev-parse", "HEAD")
    _git(path, "checkout", "-qb", "side")
    (path / "other").write_text("x\n")
    _git(path, "add", "other")
    _git(path, "commit", "-qm", "side")
    side = _git(path, "rev-parse", "HEAD")
    _git(path, "checkout", "-q", "main")
    (path / "VERSION").write_text("1.5.0\n")
    _git(path, "add", "VERSION")
    _git(path, "commit", "-qm", "new")
    new = _git(path, "rev-parse", "HEAD")
    return {"path": path, "old": old, "new": new, "side": side}


def check(history, target: str, current: str):
    """Run the real `refuse_downgrade`. Returns its exit status and stderr."""
    script = f"""
        source {SYNC}
        git_owner() {{ git -C {history["path"]} "$@"; }}
        current_sha() {{ printf '%s' '{current}'; }}
        refuse_downgrade '{target}'
    """
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return done.returncode, done.stderr


def test_an_older_target_is_refused(history):
    # The whole point: v1.0.0 re-pushed while v1.5.0 is live.
    status, stderr = check(history, history["old"], history["new"])
    assert status != 0
    assert "BEHIND the live SHA" in stderr
    assert "backwards" in stderr


def test_the_refusal_says_how_to_do_it_on_purpose(history):
    # Going back is legitimate; it just has to be asked for. A refusal that does
    # not say so sends the reader to the source.
    _status, stderr = check(history, history["old"], history["new"])
    assert "--rollback" in stderr
    assert "--allow-downgrade" in stderr


def test_a_newer_target_is_a_normal_release(history):
    assert check(history, history["new"], history["old"])[0] == 0


def test_releasing_exactly_what_is_live_is_allowed(history):
    # A re-release is a no-op, not a downgrade - CI re-running a tag must not fail.
    assert check(history, history["new"], history["new"])[0] == 0


def test_a_divergent_target_is_not_a_downgrade(history):
    # `side` is neither ahead of nor behind `new`. Only a strict ancestor counts.
    assert check(history, history["side"], history["new"])[0] == 0


def test_nothing_deployed_yet_is_allowed(history):
    # First release on a fresh box: current-sha does not exist.
    assert check(history, history["old"], "")[0] == 0


def test_an_unknown_current_sha_fails_open_and_says_so(history):
    # History rewritten under us. Refusing here would brick releases over a
    # missing object, which is worse than the thing being guarded against.
    status, stderr = check(history, history["old"], "0" * 40)
    assert status == 0
    assert "cannot check for a downgrade" in stderr


# ------------------------------------------------------------------ the CLI


def _run(*args):
    return subprocess.run(["bash", str(SYNC), *args], capture_output=True, text=True)


def test_help_documents_the_override():
    # --help runs before the root check, so this is a real invocation.
    done = _run("--help")
    assert done.returncode == 0
    assert "--allow-downgrade" in done.stdout
    assert "--rollback" in done.stdout


def test_an_unknown_flag_is_refused_by_name():
    done = _run("--allow-downgrades")
    assert done.returncode != 0
    assert "unknown argument" in done.stderr
