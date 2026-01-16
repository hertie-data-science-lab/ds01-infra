#!/usr/bin/env python3
"""
Shell Script Tests for DS01 Monitoring Commands
/opt/ds01-infra/testing/unit/monitoring/test_monitoring_scripts.py

Tests the monitoring management bash scripts for proper functionality.
Uses subprocess to invoke scripts and validate outputs.
"""

import os
import subprocess
from pathlib import Path
from typing import Tuple

import pytest


# =============================================================================
# Paths
# =============================================================================

SCRIPTS_DIR = Path("/opt/ds01-infra/scripts")
ADMIN_SCRIPTS = SCRIPTS_DIR / "admin"
MONITORING_SCRIPTS = SCRIPTS_DIR / "monitoring"


# =============================================================================
# Helper Functions
# =============================================================================

def run_script(
    script_path: Path,
    *args,
    timeout: int = 30,
    check: bool = False
) -> subprocess.CompletedProcess:
    """Run a script and return the result."""
    cmd = [str(script_path)] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )


def check_bash_syntax(script_path: Path) -> Tuple[bool, str]:
    """Check if a bash script has valid syntax."""
    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stderr


# =============================================================================
# Test: monitoring-manage Script
# =============================================================================

class TestMonitoringManage:
    """Tests for scripts/admin/monitoring-manage command."""

    SCRIPT_PATH = ADMIN_SCRIPTS / "monitoring-manage"

    def test_script_exists(self):
        """monitoring-manage script should exist."""
        assert self.SCRIPT_PATH.exists(), f"Script not found: {self.SCRIPT_PATH}"

    def test_script_is_executable(self):
        """monitoring-manage should be executable."""
        assert os.access(self.SCRIPT_PATH, os.X_OK), \
            f"Script not executable: {self.SCRIPT_PATH}"

    def test_has_valid_bash_syntax(self):
        """monitoring-manage should have valid bash syntax."""
        is_valid, error = check_bash_syntax(self.SCRIPT_PATH)
        assert is_valid, f"Bash syntax error: {error}"

    def test_help_flag_works(self):
        """monitoring-manage --help should display usage."""
        result = run_script(self.SCRIPT_PATH, "--help")

        # Should succeed or at least produce usage output
        assert result.returncode == 0 or "usage" in result.stdout.lower() or \
               "usage" in result.stderr.lower(), \
            f"--help failed: {result.stderr}"

        # Should mention key commands
        output = result.stdout + result.stderr
        assert "start" in output.lower(), "Help should mention 'start'"
        assert "stop" in output.lower(), "Help should mention 'stop'"

    def test_help_subcommand_works(self):
        """monitoring-manage help should display usage."""
        result = run_script(self.SCRIPT_PATH, "help")

        # Should produce help output
        output = result.stdout + result.stderr
        assert "start" in output.lower() or "usage" in output.lower()

    def test_unknown_command_shows_error(self):
        """monitoring-manage with unknown command should show error."""
        result = run_script(self.SCRIPT_PATH, "nonexistent-command")

        # Should fail
        assert result.returncode != 0, "Unknown command should fail"

        # Should mention unknown or error
        output = result.stdout + result.stderr
        assert "unknown" in output.lower() or "error" in output.lower() or \
               "usage" in output.lower()

    def test_shebang_is_correct(self):
        """Script shebang should be correct."""
        with open(self.SCRIPT_PATH) as f:
            first_line = f.readline().strip()

        assert first_line.startswith("#!"), "Script should have shebang"
        assert "bash" in first_line, "Script should use bash"

    def test_uses_set_e(self):
        """Script should use set -e for error handling."""
        with open(self.SCRIPT_PATH) as f:
            content = f.read()

        assert "set -e" in content or "set -euo" in content, \
            "Script should use 'set -e' for error handling"


# =============================================================================
# Test: monitoring-status Script
# =============================================================================

class TestMonitoringStatus:
    """Tests for scripts/monitoring/monitoring-status command."""

    SCRIPT_PATH = MONITORING_SCRIPTS / "monitoring-status"

    def test_script_exists(self):
        """monitoring-status script should exist."""
        assert self.SCRIPT_PATH.exists(), f"Script not found: {self.SCRIPT_PATH}"

    def test_script_is_executable(self):
        """monitoring-status should be executable."""
        assert os.access(self.SCRIPT_PATH, os.X_OK), \
            f"Script not executable: {self.SCRIPT_PATH}"

    def test_has_valid_bash_syntax(self):
        """monitoring-status should have valid bash syntax."""
        is_valid, error = check_bash_syntax(self.SCRIPT_PATH)
        assert is_valid, f"Bash syntax error: {error}"

    def test_quiet_mode_returns_exit_code(self):
        """monitoring-status --quiet should return appropriate exit code."""
        result = run_script(self.SCRIPT_PATH, "--quiet")

        # In quiet mode, output should be minimal or empty
        # Exit code 0 means all services up, non-zero means some down

        # We can't assert the exact code since services may or may not be running
        # But we can check that it runs without crashing
        assert result.returncode in [0, 1], \
            f"Unexpected exit code: {result.returncode}"

    def test_normal_mode_shows_services(self):
        """monitoring-status without --quiet should show service names."""
        result = run_script(self.SCRIPT_PATH)

        output = result.stdout + result.stderr
        # Should mention monitoring components
        assert "exporter" in output.lower() or "prometheus" in output.lower() or \
               "monitoring" in output.lower()

    def test_shebang_is_correct(self):
        """Script shebang should be correct."""
        with open(self.SCRIPT_PATH) as f:
            first_line = f.readline().strip()

        assert first_line.startswith("#!"), "Script should have shebang"
        assert "bash" in first_line, "Script should use bash"


# =============================================================================
# Test: Script Quality
# =============================================================================

class TestScriptQuality:
    """Tests for script quality and best practices."""

    SCRIPTS = [
        ADMIN_SCRIPTS / "monitoring-manage",
        MONITORING_SCRIPTS / "monitoring-status",
    ]

    @pytest.mark.parametrize("script_path", SCRIPTS)
    def test_scripts_have_usage_function_or_help(self, script_path):
        """Scripts should have usage information."""
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        has_usage = "usage" in content.lower() or "Usage" in content
        has_help = "--help" in content or "-h" in content

        assert has_usage or has_help, \
            f"Script {script_path.name} should have usage/help"

    @pytest.mark.parametrize("script_path", SCRIPTS)
    def test_scripts_use_proper_quoting(self, script_path):
        """Scripts should use proper variable quoting."""
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        # Common unquoted variable patterns that could cause issues
        # This is a basic check - could have false positives
        dangerous_patterns = [
            # Unquoted $VAR in commands (simplified check)
            # r'\[\s*\$[A-Z_]+\s*[!=]',  # [ $VAR = ... ]
        ]

        # We'll just verify the script uses some quoting
        assert '"$' in content or "'$" in content or '"${' in content, \
            f"Script {script_path.name} should quote variables"

    @pytest.mark.parametrize("script_path", SCRIPTS)
    def test_scripts_have_comments(self, script_path):
        """Scripts should have descriptive comments."""
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        # Count comment lines (excluding shebang)
        lines = content.split("\n")
        comment_lines = [
            l for l in lines[1:]  # Skip shebang
            if l.strip().startswith("#") and not l.strip() == "#"
        ]

        assert len(comment_lines) >= 3, \
            f"Script {script_path.name} should have descriptive comments"


# =============================================================================
# Test: Script Dependencies
# =============================================================================

class TestScriptDependencies:
    """Tests that script dependencies are available."""

    def test_bash_is_available(self):
        """bash should be available."""
        result = subprocess.run(["bash", "--version"], capture_output=True)
        assert result.returncode == 0, "bash not available"

    def test_curl_is_available(self):
        """curl should be available for health checks."""
        result = subprocess.run(["curl", "--version"], capture_output=True)
        assert result.returncode == 0, "curl not available"

    def test_docker_compose_is_available(self):
        """docker compose should be available."""
        # Try new docker compose command
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True
        )

        if result.returncode != 0:
            # Try legacy docker-compose
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True
            )

        assert result.returncode == 0, "docker compose not available"


# =============================================================================
# Test: Exit Codes
# =============================================================================

class TestExitCodes:
    """Tests for proper exit code usage."""

    def test_monitoring_manage_invalid_command_nonzero(self):
        """Invalid command should return non-zero exit code."""
        result = run_script(
            ADMIN_SCRIPTS / "monitoring-manage",
            "invalid-command-xyz"
        )
        assert result.returncode != 0, "Invalid command should fail"

    def test_monitoring_status_quiet_returns_valid_code(self):
        """monitoring-status --quiet should return 0 or 1."""
        result = run_script(
            MONITORING_SCRIPTS / "monitoring-status",
            "--quiet"
        )

        # 0 = all healthy, 1 = some unhealthy
        assert result.returncode in [0, 1], \
            f"Unexpected exit code: {result.returncode}"


# =============================================================================
# Test: Colour Support
# =============================================================================

class TestColourSupport:
    """Tests for terminal colour handling."""

    SCRIPTS = [
        ADMIN_SCRIPTS / "monitoring-manage",
        MONITORING_SCRIPTS / "monitoring-status",
    ]

    @pytest.mark.parametrize("script_path", SCRIPTS)
    def test_scripts_define_colours(self, script_path):
        """Scripts should define colour codes."""
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        # Check for colour variable definitions
        has_colours = any([
            "RED=" in content,
            "GREEN=" in content,
            "\\033[" in content,
            "\\e[" in content,
            "${RED}" in content,
            "${GREEN}" in content,
        ])

        assert has_colours, \
            f"Script {script_path.name} should support terminal colours"

    @pytest.mark.parametrize("script_path", SCRIPTS)
    def test_scripts_reset_colours(self, script_path):
        """Scripts should reset colours (NC/RESET)."""
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        # Check for colour reset
        has_reset = any([
            "NC=" in content,
            "RESET=" in content,
            "\\033[0m" in content,
            "\\e[0m" in content,
        ])

        if "RED=" in content or "GREEN=" in content:
            assert has_reset, \
                f"Script {script_path.name} should reset colours"


# =============================================================================
# Test: Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in scripts."""

    SCRIPTS = [
        ADMIN_SCRIPTS / "monitoring-manage",
        MONITORING_SCRIPTS / "monitoring-status",
    ]

    @pytest.mark.parametrize("script_path", SCRIPTS)
    def test_scripts_use_error_handling(self, script_path):
        """Scripts should use error handling mechanisms."""
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        has_error_handling = any([
            "set -e" in content,
            "set -o errexit" in content,
            "trap" in content,
            "|| exit" in content,
            "|| return" in content,
        ])

        assert has_error_handling, \
            f"Script {script_path.name} should have error handling"

    @pytest.mark.parametrize("script_path", SCRIPTS)
    def test_scripts_check_dependencies(self, script_path):
        """Scripts should check for required commands/files."""
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        # Scripts should check for docker-compose.yaml or similar
        has_checks = any([
            "-f " in content and "then" in content,
            "command -v" in content,
            "which " in content,
            "type " in content,
            "check_" in content,
            "exists" in content.lower(),
        ])

        assert has_checks, \
            f"Script {script_path.name} should validate dependencies"


# =============================================================================
# Test: Compose File Reference
# =============================================================================

class TestComposeFileReference:
    """Tests that scripts correctly reference compose file."""

    def test_monitoring_manage_uses_correct_compose_path(self):
        """monitoring-manage should use correct docker-compose path."""
        script_path = ADMIN_SCRIPTS / "monitoring-manage"

        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        with open(script_path) as f:
            content = f.read()

        # Should reference the monitoring directory compose file
        has_compose_ref = any([
            "monitoring/docker-compose" in content,
            "COMPOSE_FILE" in content,
            "docker-compose.yaml" in content,
        ])

        assert has_compose_ref, \
            "monitoring-manage should reference docker-compose file"
