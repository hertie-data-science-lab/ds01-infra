"""Unit tests for scripts/maintenance/monthly-update.sh.

Everything that touches the system (apt-get, dpkg, modinfo, nvidia-smi, docker,
shutdown, uname, id, flock) is a stub on PATH driven by files in STUB_DIR, and
every path the script writes or reads is pointed into tmp_path. The assertions are
on what got called, what was left in the state dir, and the exit code - the exit
code is what OnFailure= alerts on.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/maintenance/monthly-update.sh"
APT_CONF = REPO / "config/deploy/apt.conf.d/52ds01-unattended-upgrades"

pytestmark = pytest.mark.unit

RUNNING = "6.8.0-138-generic"
NEW = "6.8.0-149-generic"

STUBS = {
    "id": 'echo "$(cat "$STUB_DIR/uid")"',
    "uname": 'cat "$STUB_DIR/uname"',
    "apt-get": 'echo "$*" >>"$STUB_DIR/apt-get.log"',
    "apt": "true",
    "docker": 'case "$1" in ps) printf "web\\timg\\tUp\\n" ;; info) [ -e "$STUB_DIR/docker-ok" ] ;; esac',
    "nvidia-smi": 'for i in $(seq 1 "$(cat "$STUB_DIR/gpus")"); do echo "GPU $((i - 1)): A100"; done',
    "modinfo": '[ -e "$STUB_DIR/modinfo-ok" ]',
    "dpkg": 'grep -qxF "$2" "$STUB_DIR/owned"',
    "shutdown": 'echo "$*" >>"$STUB_DIR/shutdown.log"',
    "flock": "true",
    "health": 'cat "$STUB_DIR/health.json"; exit 1',
}


def health_json(failing):
    names = ["docker_daemon", "nvidia_smi", "default_cgroup_parent", "user_slices"]
    return json.dumps({"checks": [{"check": n, "passed": n not in failing} for n in names]})


@pytest.fixture
def box(tmp_path):
    stub = tmp_path / "stub"
    bin_ = tmp_path / "bin"
    state = tmp_path / "state"
    modules = tmp_path / "modules"
    for d in (stub, bin_, modules):
        d.mkdir()
    for name, body in STUBS.items():
        f = bin_ / name
        f.write_text(f"#!/bin/bash\n{body}\n")
        f.chmod(0o755)

    (stub / "uid").write_text("0\n")
    (stub / "uname").write_text(f"{RUNNING}\n")
    (stub / "gpus").write_text("4\n")
    (stub / "modinfo-ok").touch()
    (stub / "docker-ok").touch()
    (stub / "health.json").write_text(health_json({"default_cgroup_parent"}))
    (stub / "owned").write_text("")
    grub = tmp_path / "grub.cfg"
    grub.write_text(
        "menuentry 'Ubuntu' {\n"
        f"\tlinux\t/boot/vmlinuz-{NEW} root=UUID=x ro quiet\n"
        "}\nsubmenu 'Advanced' {\n"
        f"\t\tlinux\t/boot/vmlinuz-{RUNNING} root=UUID=x ro\n}}\n"
    )
    reboot_flag = tmp_path / "reboot-required"
    reboot_flag.touch()

    env = {
        "PATH": f"{bin_}:/usr/bin:/bin",
        "STUB_DIR": str(stub),
        "DS01_MAINT_STATE_DIR": str(state),
        "DS01_MAINT_LOG": str(tmp_path / "log/monthly-update.log"),
        "DS01_GRUB_CFG": str(grub),
        "DS01_MODULES_DIR": str(modules),
        "DS01_REBOOT_FLAG": str(reboot_flag),
        "DS01_HEALTH_CHECK": str(bin_ / "health"),
    }

    class Box:
        pass

    b = Box()
    b.stub, b.state, b.modules, b.reboot_flag = stub, state, modules, reboot_flag

    def run(*args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def calls(name):
        f = stub / f"{name}.log"
        return f.read_text().splitlines() if f.exists() else []

    b.run, b.calls = run, calls
    return b


def test_refuses_without_root(box):
    (box.stub / "uid").write_text("1001\n")
    r = box.run()
    assert r.returncode == 1
    assert "must run as root" in r.stdout
    assert box.calls("apt-get") == []


def test_full_run_upgrades_then_schedules_reboot(box):
    r = box.run()
    assert r.returncode == 0, r.stdout
    apt = box.calls("apt-get")
    # argv: -y, three "-o key=value" pairs, then the subcommand
    assert [a.split()[7] for a in apt] == ["update", "full-upgrade", "autoremove"]
    assert all("--force-confold" in a for a in apt)
    assert box.calls("shutdown") and box.calls("shutdown")[0].startswith("-r +2")
    assert (box.state / "verify-pending").read_text().strip() == NEW
    assert (box.state / "gpus-before").read_text().strip() == "4"
    assert "web" in (box.state / "containers-before.txt").read_text()


def test_refuses_reboot_without_nvidia_module(box):
    (box.stub / "modinfo-ok").unlink()
    r = box.run()
    assert r.returncode == 1
    assert f"no nvidia module for {NEW}" in r.stdout
    assert box.calls("shutdown") == []
    assert not (box.state / "verify-pending").exists()


def test_no_reboot_leaves_it_to_admin(box):
    r = box.run("--no-reboot")
    assert r.returncode == 0, r.stdout
    assert box.calls("shutdown") == []
    assert "left to you" in r.stdout


def test_nothing_to_reboot_verifies_inline(box):
    box.reboot_flag.unlink()
    (box.stub / "uname").write_text(f"{NEW}\n")
    r = box.run()
    assert r.returncode == 0, r.stdout
    assert box.calls("shutdown") == []
    assert "maintenance complete" in r.stdout


def test_prunes_only_orphaned_module_dirs(box):
    for k in ("5.11.0-25-generic", NEW, RUNNING):
        (box.modules / k).mkdir()
    (box.stub / "owned").write_text(f"{box.modules / NEW}\n")
    assert box.run("--no-reboot").returncode == 0
    assert sorted(p.name for p in box.modules.iterdir()) == sorted([NEW, RUNNING])


def pending(box, kernel=NEW, gpus=4, health_before=("default_cgroup_parent",)):
    box.state.mkdir(exist_ok=True)
    (box.state / "verify-pending").write_text(f"{kernel}\n")
    (box.state / "gpus-before").write_text(f"{gpus}\n")
    (box.state / "health-before").write_text("".join(f"{h}\n" for h in health_before))
    (box.stub / "uname").write_text(f"{NEW}\n")


def test_verify_passes_with_preexisting_health_failure(box):
    pending(box)
    r = box.run("--verify")
    assert r.returncode == 0, r.stdout
    assert "already failing before: default_cgroup_parent" in r.stdout
    assert not (box.state / "verify-pending").exists()


@pytest.mark.parametrize(
    "breakage, message",
    [
        (lambda b: (b.stub / "gpus").write_text("3\n"), "3 GPUs visible, 4 before"),
        (lambda b: (b.stub / "uname").write_text(f"{RUNNING}\n"), "FAIL kernel"),
        (lambda b: (b.stub / "docker-ok").unlink(), "docker not responding"),
        (
            lambda b: (b.stub / "health.json").write_text(
                health_json({"default_cgroup_parent", "nvidia_smi"})
            ),
            "new health-check failures: nvidia_smi",
        ),
    ],
)
def test_verify_fails_on_regression(box, breakage, message):
    pending(box)
    breakage(box)
    r = box.run("--verify")
    assert r.returncode == 1
    assert message in r.stdout
    # One attempt only: the alert fires once, not on every later boot.
    assert not (box.state / "verify-pending").exists()


@pytest.mark.skipif(shutil.which("apt-config") is None, reason="needs apt-config")
def test_apt_conf_parses_and_blacklists_kernel_and_nvidia():
    out = subprocess.run(
        ["apt-config", "-c", str(APT_CONF), "dump"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for pkg in ("linux-", "nvidia-", "libnvidia-"):
        assert f'Unattended-Upgrade::Package-Blacklist:: "{pkg}";' in out
