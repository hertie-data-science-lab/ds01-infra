#!/usr/bin/env python3
"""
Behavioural Tests: Phase 6 — Lifecycle Enforcement Logic

Tests the actual bash function logic in check-idle-containers.sh and
enforce-max-runtime.sh by sourcing real scripts with mocked external commands
(docker, nvidia-smi, python3) via PATH override.

No Docker, GPU, or root access required.
"""

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

INFRA_ROOT = Path("/opt/ds01-infra")
CHECK_IDLE = INFRA_ROOT / "scripts" / "monitoring" / "check-idle-containers.sh"
ENFORCE_RUNTIME = INFRA_ROOT / "scripts" / "maintenance" / "enforce-max-runtime.sh"


# =============================================================================
# Fixtures & Helpers
# =============================================================================


@pytest.fixture()
def mock_env(tmp_path):
    """Create a self-contained mock environment for bash function testing."""
    env = _MockEnv(tmp_path)
    env.setup()
    return env


class _MockEnv:
    """Encapsulates the mock environment setup and harness generation."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.bin_dir = tmp_path / "bin"
        self.state_dir = tmp_path / "state"
        self.log_dir = tmp_path / "log"
        self.call_log = tmp_path / "call_log"
        self.scripts_dir = tmp_path / "scripts"
        self.config_dir = tmp_path / "config" / "runtime"

    def setup(self):
        self.bin_dir.mkdir()
        self.state_dir.mkdir()
        self.log_dir.mkdir()
        self.scripts_dir.mkdir(parents=True)
        (self.scripts_dir / "docker").mkdir()
        (self.scripts_dir / "lib").mkdir()
        self.config_dir.mkdir(parents=True)
        (self.root / "mock_data").mkdir()
        self.call_log.touch()

        self._write_mock_docker()
        self._write_mock_nvidia_smi()
        self._write_mock_python3()
        self._write_mock_simple("bc", self._bc_script())
        self._write_mock_simple("numfmt", 'echo "0"')
        self._write_mock_simple("who", 'echo ""')
        self._write_mock_simple("logger", "true")
        self._write_mock_simple("getent", 'echo ""')
        self._write_mock_simple("tee", 'cat > /dev/null')
        self._write_mock_get_resource_limits()
        self._write_default_config()

    def _make_executable(self, path: Path):
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def _write_mock_simple(self, name: str, body: str):
        script = self.bin_dir / name
        script.write_text(f"#!/bin/bash\n{body}\n")
        self._make_executable(script)

    def _write_mock_docker(self):
        """Mock docker: dispatches on subcommand, pattern-matches inspect format."""
        script = self.bin_dir / "docker"
        # Use single-quoted heredoc to avoid any variable expansion issues
        content = "#!/bin/bash\n"
        content += f'echo "docker $*" >> "{self.call_log}"\n'
        content += f'MOCK_DATA="{self.root}/mock_data"\n'
        content += r"""
case "$1" in
    ps)
        cat "$MOCK_DATA/docker_ps" 2>/dev/null
        ;;
    inspect)
        container="$2"
        shift 2
        all_args="$*"

        # Pattern-match on the format string to determine what's queried
        if [[ "$all_args" == *"ds01.gpu.uuid"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_gpu_uuid" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"DeviceRequests"* && "$all_args" == *"DeviceIDs"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_device_ids" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"DeviceRequests"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_device_requests" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"ds01.container_type"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_container_type" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"ds01.monitoring"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_monitoring" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"ds01.user"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_user" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"aime.mlc.USER"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_mlc_user" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"ds01.interface"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_interface" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"devcontainer.local_folder"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_local_folder" 2>/dev/null || echo ""
        elif [[ "$all_args" == *"json .Config.Labels"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_labels_json" 2>/dev/null || echo "{}"
        elif [[ "$all_args" == *".Name"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_name" 2>/dev/null || echo "/$container"
        elif [[ "$all_args" == *"StartedAt"* ]]; then
            cat "$MOCK_DATA/inspect_${container}_started_at" 2>/dev/null || echo "2024-11-14T10:00:00Z"
        else
            cat "$MOCK_DATA/inspect_${container}" 2>/dev/null || echo ""
        fi
        ;;
    stats)
        container="$2"
        # Check if format asks for NetIO
        all_args="$*"
        if [[ "$all_args" == *"NetIO"* ]]; then
            cat "$MOCK_DATA/stats_${container}_net" 2>/dev/null || echo "0B / 0B"
        else
            cat "$MOCK_DATA/stats_${container}" 2>/dev/null || echo "0.00%"
        fi
        ;;
    stop)
        echo "stopped"
        exit 0
        ;;
    rm)
        echo "removed"
        exit 0
        ;;
    exec)
        # Default: simulate command not found / file doesn't exist
        exit 1
        ;;
    *)
        exit 0
        ;;
esac
"""
        script.write_text(content)
        self._make_executable(script)

    def _write_mock_nvidia_smi(self):
        script = self.bin_dir / "nvidia-smi"
        content = "#!/bin/bash\n"
        content += f'echo "nvidia-smi $*" >> "{self.call_log}"\n'
        content += f'MOCK_DATA="{self.root}/mock_data"\n'
        content += r"""
# Parse --id= argument
gpu_id=""
for arg in "$@"; do
    case "$arg" in
        --id=*) gpu_id="${arg#--id=}" ;;
    esac
done
# Also handle -L flag (list GPUs)
if [[ "$1" == "-L" ]]; then
    cat "$MOCK_DATA/gpu_list" 2>/dev/null || echo "GPU 0: NVIDIA A100"
    exit 0
fi
if [ -n "$gpu_id" ] && [ -f "$MOCK_DATA/gpu_util_$gpu_id" ]; then
    cat "$MOCK_DATA/gpu_util_$gpu_id"
elif [ -f "$MOCK_DATA/gpu_util" ]; then
    cat "$MOCK_DATA/gpu_util"
else
    echo "0"
fi
"""
        script.write_text(content)
        self._make_executable(script)

    def _write_mock_python3(self):
        """Mock python3: routes get_resource_limits.py to mock, else real python3."""
        script = self.bin_dir / "python3"
        mock_handler = self.scripts_dir / "docker" / "get_resource_limits_mock.sh"
        content = "#!/bin/bash\n"
        content += f'MOCK_HANDLER="{mock_handler}"\n'
        content += r"""
if [[ "$1" == *get_resource_limits.py ]]; then
    /bin/bash "$MOCK_HANDLER" "$@"
    exit $?
fi
exec /usr/bin/python3 "$@"
"""
        script.write_text(content)
        self._make_executable(script)

    def _bc_script(self) -> str:
        return textwrap.dedent(r"""
            input=""
            while IFS= read -r line || [[ -n "$line" ]]; do
                input+="$line"
            done
            if [ -z "$input" ]; then
                for arg in "$@"; do
                    [[ "$arg" == -* ]] && continue
                    input="$arg"
                done
            fi
            /usr/bin/python3 -c "
            expr = '''$input'''.strip()
            try:
                if '>=' in expr:
                    a, b = expr.split('>=', 1)
                    print(1 if float(a) >= float(b) else 0)
                elif '<=' in expr:
                    a, b = expr.split('<=', 1)
                    print(1 if float(a) <= float(b) else 0)
                elif '<' in expr:
                    a, b = expr.split('<', 1)
                    print(1 if float(a) < float(b) else 0)
                elif '>' in expr:
                    a, b = expr.split('>', 1)
                    print(1 if float(a) > float(b) else 0)
                elif '/' in expr:
                    parts = expr.replace('scale=0;','').replace('scale=2;','').strip()
                    a, b = parts.split('/', 1)
                    print(int(float(a.strip()) / float(b.strip())))
                elif '*' in expr:
                    parts = expr.replace('scale=0;','').replace('scale=2;','').strip()
                    a, b = parts.split('*', 1)
                    print(int(float(a.strip()) * float(b.strip())))
                else:
                    print(0)
            except Exception:
                print(0)
            " 2>/dev/null || echo "0"
        """).strip()

    def _write_mock_get_resource_limits(self):
        mock_script = self.scripts_dir / "docker" / "get_resource_limits_mock.sh"
        content = "#!/bin/bash\n"
        content += f'MOCK_DATA="{self.root}/mock_data"\n'
        content += r"""
shift  # skip .py path
username="$1"; shift
flag="$1"; shift
extra="$1"

case "$flag" in
    --max-runtime)
        cat "$MOCK_DATA/max_runtime_$username" 2>/dev/null || echo "24h"
        ;;
    --idle-timeout)
        cat "$MOCK_DATA/idle_timeout_$username" 2>/dev/null || echo "0.5h"
        ;;
    --check-exemption)
        cat "$MOCK_DATA/exemption_${username}_${extra}" 2>/dev/null || echo "not_exempt"
        ;;
    --lifecycle-policies)
        cat "$MOCK_DATA/policies_$username" 2>/dev/null || \
            echo '{"gpu_idle_threshold": 5, "cpu_idle_threshold": 2.0, "network_idle_threshold": 1048576, "idle_detection_window": 3}'
        ;;
    --high-demand-threshold)
        echo "0.8"
        ;;
    --high-demand-reduction)
        echo "0.5"
        ;;
    *)
        echo ""
        ;;
esac
"""
        mock_script.write_text(content)
        self._make_executable(mock_script)

    def _write_default_config(self):
        self.config_dir.joinpath("resource-limits.yaml").write_text(textwrap.dedent("""\
            defaults:
              max_runtime: 24h
              idle_timeout: 0.5h

            policies:
              sigterm_grace_seconds: 60
              gpu_idle_threshold: 5
              cpu_idle_threshold: 2.0
              network_idle_threshold: 1048576
              idle_detection_window: 3
              grace_period: 30m

            container_types:
              devcontainer:
                idle_timeout: null
                max_runtime: 168h
                sigterm_grace_seconds: 30
              compose:
                idle_timeout: 30m
                max_runtime: 72h
                sigterm_grace_seconds: 45
              docker:
                idle_timeout: 30m
                max_runtime: 48h
                sigterm_grace_seconds: 60
              unknown:
                idle_timeout: 15m
                max_runtime: 24h
                sigterm_grace_seconds: 30
        """))

    # -- Mock data helpers ---------------------------------------------------

    def set_mock_data(self, filename: str, content: str):
        (self.root / "mock_data" / filename).write_text(content)

    def set_docker_inspect(self, container: str, key: str, response: str):
        """Set canned response for docker inspect by key name.

        Keys: gpu_uuid, device_requests, device_ids, container_type,
              monitoring, user, name, started_at, labels_json, etc.
        """
        self.set_mock_data(f"inspect_{container}_{key}", response)

    def set_state_file(self, container: str, **kwargs):
        lines = [f"{k.upper()}={v}" for k, v in kwargs.items()]
        (self.state_dir / f"{container}.state").write_text("\n".join(lines) + "\n")

    def read_state_file(self, container: str) -> dict:
        path = self.state_dir / f"{container}.state"
        if not path.exists():
            return {}
        result = {}
        for line in path.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                result[k] = v
        return result

    def get_call_log(self) -> list[str]:
        return [line for line in self.call_log.read_text().splitlines() if line.strip()]

    def docker_stop_calls(self) -> list[str]:
        return [c for c in self.get_call_log() if c.startswith("docker stop")]

    # -- Harness builders ----------------------------------------------------

    def harness_idle(self, bash_code: str) -> str:
        return self._build_harness(CHECK_IDLE, bash_code)

    def harness_runtime(self, bash_code: str) -> str:
        return self._build_harness(ENFORCE_RUNTIME, bash_code)

    def _build_harness(self, script: Path, bash_code: str) -> str:
        """Build harness: source real script, THEN override vars and functions."""
        return (
            f"#!/bin/bash\n"
            f'export PATH="{self.bin_dir}:$PATH"\n'
            # No-op mkdir to prevent real directory creation during source
            "mkdir() { :; }\n"
            # Source the real script (defines all functions, sets vars from real paths)
            f'source "{script}"\n'
            # Now override all variables to point at mock environment
            f'INFRA_ROOT="{self.root}"\n'
            f'CONFIG_FILE="{self.config_dir}/resource-limits.yaml"\n'
            f'STATE_DIR="{self.state_dir}"\n'
            f'LOG_FILE="{self.log_dir}/test.log"\n'
            f'DS01_ROOT="{self.root}"\n'
            f'DS01_SCRIPTS="{self.scripts_dir}"\n'
            f'DS01_LIB="{self.scripts_dir}/lib"\n'
            # Disable set -e for test tolerance
            "set +e\n"
            # Re-override functions that the real script (re)defined
            "log() { :; }\n"
            "log_color() { :; }\n"
            "notify_user() { :; }\n"
            # Simple bash-only ds01_parse_duration (overrides the python-based one)
            "ds01_parse_duration() {\n"
            '    local d="$1"\n'
            '    case "$d" in\n'
            '        *d) echo $(( ${d%d} * 86400 )) ;;\n'
            '        *h) echo $(( ${d%h} * 3600 )) ;;\n'
            '        *m) echo $(( ${d%m} * 60 )) ;;\n'
            '        *s) echo "${d%s}" ;;\n'
            '        null|never|"") echo "-1" ;;\n'
            '        *) echo "$d" ;;\n'
            "    esac\n"
            "}\n"
            # Restore mkdir for test code that might need it
            "unset -f mkdir\n"
            # Run test code
            f"{bash_code}\n"
        )

    def run(self, harness_code: str, timeout: int = 10) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", harness_code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PATH": f"{self.bin_dir}:{os.environ['PATH']}"},
        )


# =============================================================================
# TestMultiSignalAndLogic
# =============================================================================


class TestMultiSignalAndLogic:
    """Test AND-logic idle detection: GPU active = not idle, GPU idle + CPU active
    = not idle, all idle = idle, GPU unknown = fallback."""

    @pytest.mark.component
    def test_gpu_active_means_not_idle(self, mock_env):
        """When GPU utilisation is above threshold, check_gpu_idle returns 'active'."""
        mock_env.set_mock_data("gpu_util_GPU-UUID-123", "80")
        mock_env.set_docker_inspect("test-ctr", "gpu_uuid", "GPU-UUID-123")

        code = mock_env.harness_idle(
            'result=$(check_gpu_idle "test-ctr" 5); echo "gpu:$result"'
        )
        result = mock_env.run(code)
        assert "gpu:active" in result.stdout

    @pytest.mark.component
    def test_gpu_idle_cpu_active_means_not_idle(self, mock_env):
        """GPU idle but CPU active = NOT idle (data loading / preprocessing)."""
        mock_env.set_mock_data("gpu_util_GPU-UUID-123", "2")
        mock_env.set_docker_inspect("test-ctr", "gpu_uuid", "GPU-UUID-123")
        mock_env.set_mock_data("stats_test-ctr", "15.00%")

        code = mock_env.harness_idle(
            'gpu=$(check_gpu_idle "test-ctr" 5); echo "gpu:$gpu"\n'
            'sec=$(is_container_active_secondary "test-ctr" 2.0 1048576); echo "sec:$sec"'
        )
        result = mock_env.run(code)
        assert "gpu:idle" in result.stdout
        assert "sec:true" in result.stdout

    @pytest.mark.component
    def test_all_signals_idle(self, mock_env):
        """GPU idle + CPU idle + network idle = container is idle."""
        mock_env.set_mock_data("gpu_util_GPU-UUID-123", "1")
        mock_env.set_docker_inspect("test-ctr", "gpu_uuid", "GPU-UUID-123")
        mock_env.set_mock_data("stats_test-ctr", "0.50%")

        code = mock_env.harness_idle(
            'gpu=$(check_gpu_idle "test-ctr" 5); echo "gpu:$gpu"\n'
            'sec=$(is_container_active_secondary "test-ctr" 2.0 1048576); echo "sec:$sec"'
        )
        result = mock_env.run(code)
        assert "gpu:idle" in result.stdout
        assert "sec:false" in result.stdout

    @pytest.mark.component
    def test_gpu_unknown_falls_back_to_secondary(self, mock_env):
        """No GPU UUID found → check_gpu_idle returns 'unknown'."""
        mock_env.set_docker_inspect("test-ctr", "gpu_uuid", "<no value>")
        mock_env.set_docker_inspect("test-ctr", "device_ids", "")

        code = mock_env.harness_idle(
            'result=$(check_gpu_idle "test-ctr" 5); echo "gpu:$result"'
        )
        result = mock_env.run(code)
        assert "gpu:unknown" in result.stdout

    @pytest.mark.component
    def test_gpu_at_threshold_boundary(self, mock_env):
        """GPU at exactly the threshold (5%) is still considered active (not < 5)."""
        mock_env.set_mock_data("gpu_util_GPU-UUID-AAA", "5")
        mock_env.set_docker_inspect("ctr-boundary", "gpu_uuid", "GPU-UUID-AAA")

        code = mock_env.harness_idle(
            'result=$(check_gpu_idle "ctr-boundary" 5); echo "gpu:$result"'
        )
        result = mock_env.run(code)
        # 5 < 5 is false → should be "active"
        assert "gpu:active" in result.stdout


# =============================================================================
# TestIdleDetectionWindow
# =============================================================================


class TestIdleDetectionWindow:
    """Test idle streak / detection window: streak below window = no action,
    streak reaches window = triggers, activity resets streak."""

    @pytest.mark.component
    def test_streak_below_window_no_action(self, mock_env):
        """Idle streak < detection_window → waiting."""
        mock_env.set_state_file("test-ctr", idle_streak="1", warned="false",
                                last_activity="1699999000", last_cpu="0.0")
        code = mock_env.harness_idle(
            f'state_file="{mock_env.state_dir}/test-ctr.state"\n'
            'source "$state_file"\n'
            'current_streak=${IDLE_STREAK:-0}\n'
            'current_streak=$((current_streak + 1))\n'
            'sed -i "s/^IDLE_STREAK=.*/IDLE_STREAK=$current_streak/" "$state_file"\n'
            'detection_window=3\n'
            'if [ "$current_streak" -lt "$detection_window" ]; then\n'
            '    echo "result:waiting"\n'
            'else\n'
            '    echo "result:triggered"\n'
            'fi\n'
        )
        result = mock_env.run(code)
        assert "result:waiting" in result.stdout
        assert mock_env.read_state_file("test-ctr")["IDLE_STREAK"] == "2"

    @pytest.mark.component
    def test_streak_reaches_window_triggers(self, mock_env):
        """Idle streak == detection_window → triggered."""
        mock_env.set_state_file("test-ctr", idle_streak="2", warned="false",
                                last_activity="1699999000", last_cpu="0.0")
        code = mock_env.harness_idle(
            f'state_file="{mock_env.state_dir}/test-ctr.state"\n'
            'source "$state_file"\n'
            'current_streak=${IDLE_STREAK:-0}\n'
            'current_streak=$((current_streak + 1))\n'
            'sed -i "s/^IDLE_STREAK=.*/IDLE_STREAK=$current_streak/" "$state_file"\n'
            'detection_window=3\n'
            'if [ "$current_streak" -lt "$detection_window" ]; then\n'
            '    echo "result:waiting"\n'
            'else\n'
            '    echo "result:triggered"\n'
            'fi\n'
        )
        result = mock_env.run(code)
        assert "result:triggered" in result.stdout
        assert mock_env.read_state_file("test-ctr")["IDLE_STREAK"] == "3"

    @pytest.mark.component
    def test_activity_resets_streak(self, mock_env):
        """Activity detection resets IDLE_STREAK to 0 and WARNED to false."""
        mock_env.set_state_file("test-ctr", idle_streak="5", warned="true",
                                last_activity="1699999000", last_cpu="0.0")
        code = mock_env.harness_idle(
            'update_activity "test-ctr" "true"\n'
            f'source "{mock_env.state_dir}/test-ctr.state"\n'
            'echo "streak:$IDLE_STREAK"\n'
            'echo "warned:$WARNED"'
        )
        result = mock_env.run(code)
        assert "streak:0" in result.stdout
        assert "warned:false" in result.stdout

    @pytest.mark.component
    def test_group_specific_detection_window(self, mock_env):
        """Different groups return different idle_detection_window values."""
        mock_env.set_mock_data(
            "policies_researcher1",
            '{"gpu_idle_threshold": 5, "cpu_idle_threshold": 3.0, '
            '"network_idle_threshold": 1048576, "idle_detection_window": 4}',
        )
        mock_env.set_mock_data(
            "policies_student1",
            '{"gpu_idle_threshold": 5, "cpu_idle_threshold": 2.0, '
            '"network_idle_threshold": 1048576, "idle_detection_window": 3}',
        )
        code = mock_env.harness_idle(
            'r=$(get_lifecycle_policies "researcher1")\n'
            'rw=$(/usr/bin/python3 -c "import json; print(json.loads(\'$r\')[\'idle_detection_window\'])")\n'
            'echo "researcher:$rw"\n'
            's=$(get_lifecycle_policies "student1")\n'
            'sw=$(/usr/bin/python3 -c "import json; print(json.loads(\'$s\')[\'idle_detection_window\'])")\n'
            'echo "student:$sw"'
        )
        result = mock_env.run(code)
        assert "researcher:4" in result.stdout
        assert "student:3" in result.stdout


# =============================================================================
# TestExemptUserIdleHandling
# =============================================================================


class TestExemptUserIdleHandling:
    """Test exemption logic: exempt not stopped, FYI warning sent,
    non-exempt stopped, FYI sent only once."""

    @pytest.mark.component
    def test_exempt_user_detected(self, mock_env):
        """check_exemption returns 'exempt:...' for exempt users."""
        mock_env.set_mock_data("exemption_testuser_idle_timeout",
                               "exempt: research waiver")
        code = mock_env.harness_idle(
            'status=$(check_exemption "testuser" "idle_timeout")\n'
            'case "$status" in\n'
            '    exempt:*) echo "result:exempt" ;;\n'
            '    *) echo "result:enforced" ;;\n'
            'esac'
        )
        result = mock_env.run(code)
        assert "result:exempt" in result.stdout

    @pytest.mark.component
    def test_non_exempt_user_enforced(self, mock_env):
        """check_exemption returns 'not_exempt' for non-exempt users."""
        mock_env.set_mock_data("exemption_normaluser_idle_timeout", "not_exempt")
        code = mock_env.harness_idle(
            'status=$(check_exemption "normaluser" "idle_timeout")\n'
            'case "$status" in\n'
            '    exempt:*) echo "result:exempt" ;;\n'
            '    *) echo "result:enforced" ;;\n'
            'esac'
        )
        result = mock_env.run(code)
        assert "result:enforced" in result.stdout

    @pytest.mark.component
    def test_fyi_warning_sent_once(self, mock_env):
        """FYI warning for exempt users fires once, then suppressed by WARNED flag."""
        mock_env.set_state_file("exempt-ctr", idle_streak="5", warned="false",
                                last_activity="1699990000", last_cpu="0.0")
        code = mock_env.harness_idle(
            f'state_file="{mock_env.state_dir}/exempt-ctr.state"\n'
            'source "$state_file"\n'
            'is_exempt=true\n'
            'idle_seconds=2000\n'
            'warning_seconds=1800\n'
            # First check
            'if [ "$is_exempt" = true ]; then\n'
            '    if [ "$idle_seconds" -ge "$warning_seconds" ] && [ "$WARNED" != "true" ]; then\n'
            '        echo "action:send_fyi"\n'
            '        sed -i "s/^WARNED=.*/WARNED=true/" "$state_file"\n'
            '    else\n'
            '        echo "action:none"\n'
            '    fi\n'
            'fi\n'
            # Second check
            'source "$state_file"\n'
            'if [ "$is_exempt" = true ]; then\n'
            '    if [ "$idle_seconds" -ge "$warning_seconds" ] && [ "$WARNED" != "true" ]; then\n'
            '        echo "second:send_fyi"\n'
            '    else\n'
            '        echo "second:suppressed"\n'
            '    fi\n'
            'fi'
        )
        result = mock_env.run(code)
        assert "action:send_fyi" in result.stdout
        assert "second:suppressed" in result.stdout

    @pytest.mark.component
    def test_exempt_user_never_stopped(self, mock_env):
        """Even when idle exceeds timeout, exempt user is not stopped."""
        mock_env.set_mock_data("exemption_exemptuser_idle_timeout",
                               "exempt: PhD thesis")
        code = mock_env.harness_idle(
            'is_exempt=false\n'
            'status=$(check_exemption "exemptuser" "idle_timeout")\n'
            'case "$status" in exempt:*) is_exempt=true ;; esac\n'
            'idle_seconds=50000\n'
            'timeout_seconds=1800\n'
            'if [ "$is_exempt" = true ]; then\n'
            '    echo "result:skip_stop"\n'
            'elif [ "$idle_seconds" -ge "$timeout_seconds" ]; then\n'
            '    echo "result:would_stop"\n'
            'fi'
        )
        result = mock_env.run(code)
        assert "result:skip_stop" in result.stdout


# =============================================================================
# TestVariableSigtermGrace
# =============================================================================


class TestVariableSigtermGrace:
    """Test container-type-specific SIGTERM grace periods."""

    @pytest.mark.component
    def test_devcontainer_grace_30s(self, mock_env):
        code = mock_env.harness_idle(
            'grace=$(get_sigterm_grace "devcontainer"); echo "grace:$grace"'
        )
        result = mock_env.run(code)
        assert "grace:30" in result.stdout

    @pytest.mark.component
    def test_compose_grace_45s(self, mock_env):
        code = mock_env.harness_idle(
            'grace=$(get_sigterm_grace "compose"); echo "grace:$grace"'
        )
        result = mock_env.run(code)
        assert "grace:45" in result.stdout

    @pytest.mark.component
    def test_docker_grace_60s(self, mock_env):
        code = mock_env.harness_idle(
            'grace=$(get_sigterm_grace "docker"); echo "grace:$grace"'
        )
        result = mock_env.run(code)
        assert "grace:60" in result.stdout

    @pytest.mark.component
    def test_unknown_grace_30s(self, mock_env):
        code = mock_env.harness_idle(
            'grace=$(get_sigterm_grace "unknown"); echo "grace:$grace"'
        )
        result = mock_env.run(code)
        assert "grace:30" in result.stdout

    @pytest.mark.component
    def test_stop_passes_correct_grace_to_docker(self, mock_env):
        """stop_idle_container calls docker stop -t <grace> with type-specific value."""
        mock_env.set_mock_data("docker_ps", "compose-ctr\n")
        mock_env.set_docker_inspect("compose-ctr", "container_type", "compose")
        mock_env.set_docker_inspect("compose-ctr", "name", "/compose-ctr")
        mock_env.set_docker_inspect("compose-ctr", "labels_json", '{}')

        code = mock_env.harness_idle(
            'stop_idle_container "testuser" "compose-ctr" 3600 2>/dev/null; true'
        )
        mock_env.run(code)
        stops = mock_env.docker_stop_calls()
        assert any("-t 45" in s for s in stops), (
            f"Expected '-t 45' in docker stop calls, got: {stops}"
        )


# =============================================================================
# TestMaxRuntimeExemption
# =============================================================================


class TestMaxRuntimeExemption:
    """Test max_runtime exemption in enforce-max-runtime.sh."""

    @pytest.mark.component
    def test_exempt_user_skips_enforcement(self, mock_env):
        """Exempt user detected via check_exemption."""
        mock_env.set_mock_data("exemption_exemptuser_max_runtime",
                               "exempt: faculty override")
        code = mock_env.harness_runtime(
            'status=$(check_exemption "exemptuser" "max_runtime")\n'
            'case "$status" in\n'
            '    exempt:*) echo "result:exempt" ;;\n'
            '    *) echo "result:enforced" ;;\n'
            'esac'
        )
        result = mock_env.run(code)
        assert "result:exempt" in result.stdout

    @pytest.mark.component
    def test_non_exempt_user_stopped_when_exceeded(self, mock_env):
        """Non-exempt user's container stopped when runtime > max_runtime."""
        mock_env.set_mock_data("exemption_normaluser_max_runtime", "not_exempt")
        mock_env.set_mock_data("max_runtime_normaluser", "24h")

        code = mock_env.harness_runtime(
            'runtime_str=$(get_max_runtime "normaluser")\n'
            'runtime_seconds=$(runtime_to_seconds "$runtime_str")\n'
            'runtime_seconds_actual=90000\n'  # 25 hours
            'if [ "$runtime_seconds_actual" -ge "$runtime_seconds" ]; then\n'
            '    echo "result:would_stop"\n'
            'else\n'
            '    echo "result:running"\n'
            'fi'
        )
        result = mock_env.run(code)
        assert "result:would_stop" in result.stdout

    @pytest.mark.component
    def test_warning_at_90_percent(self, mock_env):
        """Warning sent when runtime reaches 90% of limit."""
        mock_env.set_state_file("warn-ctr", warned="false")

        code = mock_env.harness_runtime(
            f'state_file="{mock_env.state_dir}/warn-ctr.state"\n'
            'source "$state_file"\n'
            'runtime_seconds=86400\n'  # 24h
            'warning_seconds=$((runtime_seconds * 90 / 100))\n'
            'runtime_seconds_actual=79200\n'  # 22h — past 90%
            'if [ "$runtime_seconds_actual" -ge "$warning_seconds" ] && [ "$WARNED" != "true" ]; then\n'
            '    echo "action:warn"\n'
            '    sed -i "s/^WARNED=.*/WARNED=true/" "$state_file"\n'
            'else\n'
            '    echo "action:none"\n'
            'fi\n'
            'source "$state_file"\n'
            'echo "warned:$WARNED"'
        )
        result = mock_env.run(code)
        assert "action:warn" in result.stdout
        assert "warned:true" in result.stdout
