#!/usr/bin/env python3
"""
Tests for PAM docker group canonical username resolution scripts.

This test suite validates the scripts that handle docker group membership
with proper canonical username resolution:

1. scripts/system/pam-add-docker-group.sh - PAM session script
2. scripts/system/add-user-to-docker.sh - Manual user addition
3. scripts/system/auto-add-docker-group.sh - Auto-add with scan mode
4. scripts/system/fix-docker-group-variants.sh - Cleanup script for past users

The problem being solved:
PAM receives $PAM_USER with domain variants (e.g., user@students.hertie-school.org)
but the canonical username in passwd is different (e.g., user@hertie-school.lan).
This causes docker group membership checks to fail.

The solution:
All scripts now resolve usernames to canonical form via UID before checking or
modifying group membership.
"""

import os
import subprocess
import pytest
from pathlib import Path
from typing import Optional


# Script paths
SCRIPTS_DIR = Path("/opt/ds01-infra/scripts/system")
PAM_ADD_DOCKER_GROUP = SCRIPTS_DIR / "pam-add-docker-group.sh"
ADD_USER_TO_DOCKER = SCRIPTS_DIR / "add-user-to-docker.sh"
AUTO_ADD_DOCKER_GROUP = SCRIPTS_DIR / "auto-add-docker-group.sh"
FIX_DOCKER_GROUP_VARIANTS = SCRIPTS_DIR / "fix-docker-group-variants.sh"


class TestScriptsExist:
    """Verify all docker group scripts exist."""

    def test_pam_add_docker_group_exists(self):
        """pam-add-docker-group.sh should exist."""
        assert PAM_ADD_DOCKER_GROUP.exists()

    def test_add_user_to_docker_exists(self):
        """add-user-to-docker.sh should exist."""
        assert ADD_USER_TO_DOCKER.exists()

    def test_auto_add_docker_group_exists(self):
        """auto-add-docker-group.sh should exist."""
        assert AUTO_ADD_DOCKER_GROUP.exists()

    def test_fix_docker_group_variants_exists(self):
        """fix-docker-group-variants.sh should exist."""
        assert FIX_DOCKER_GROUP_VARIANTS.exists()


class TestScriptSyntax:
    """Verify all scripts have valid bash syntax."""

    def test_pam_add_docker_group_syntax(self):
        """pam-add-docker-group.sh should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", str(PAM_ADD_DOCKER_GROUP)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_add_user_to_docker_syntax(self):
        """add-user-to-docker.sh should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", str(ADD_USER_TO_DOCKER)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_auto_add_docker_group_syntax(self):
        """auto-add-docker-group.sh should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", str(AUTO_ADD_DOCKER_GROUP)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_fix_docker_group_variants_syntax(self):
        """fix-docker-group-variants.sh should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", str(FIX_DOCKER_GROUP_VARIANTS)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestAddUserToDocker:
    """Tests for add-user-to-docker.sh script."""

    def run_script(
        self, *args, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Run add-user-to-docker.sh with arguments."""
        script_env = os.environ.copy()
        if env:
            script_env.update(env)
        return subprocess.run(
            ["bash", str(ADD_USER_TO_DOCKER)] + list(args),
            capture_output=True,
            text=True,
            env=script_env,
            timeout=30,
        )

    def test_requires_root(self):
        """Script should require root privileges."""
        if os.geteuid() == 0:
            pytest.skip("Test requires non-root user")

        result = self.run_script("testuser")
        assert result.returncode != 0
        assert "root" in result.stderr.lower() or "root" in result.stdout.lower()

    def test_requires_username_argument(self):
        """Script should require username argument."""
        if os.geteuid() != 0:
            pytest.skip("Test requires root to check argument handling")

        result = self.run_script()
        assert result.returncode != 0
        assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()

    def test_script_has_shebang(self):
        """Script should have proper shebang."""
        with open(ADD_USER_TO_DOCKER) as f:
            first_line = f.readline()
        assert first_line.startswith("#!/bin/bash")

    def test_script_uses_canonical_resolution(self):
        """Script should use UID-based canonical resolution."""
        content = ADD_USER_TO_DOCKER.read_text()
        # Check for canonical resolution code
        assert "getent passwd" in content
        assert "CANONICAL_USER" in content or "canonical" in content.lower()


class TestAutoAddDockerGroup:
    """Tests for auto-add-docker-group.sh script."""

    def run_script(
        self, *args, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Run auto-add-docker-group.sh with arguments."""
        script_env = os.environ.copy()
        if env:
            script_env.update(env)
        return subprocess.run(
            ["bash", str(AUTO_ADD_DOCKER_GROUP)] + list(args),
            capture_output=True,
            text=True,
            env=script_env,
            timeout=30,
        )

    def test_requires_root(self):
        """Script should require root privileges."""
        if os.geteuid() == 0:
            pytest.skip("Test requires non-root user")

        result = self.run_script("testuser")
        assert result.returncode != 0
        assert "root" in result.stderr.lower() or "root" in result.stdout.lower()

    def test_help_flag(self):
        """--help should display usage information (requires root)."""
        if os.geteuid() != 0:
            pytest.skip("Script requires root even for --help")
        result = self.run_script("--help")
        assert "usage" in result.stdout.lower() or "--scan" in result.stdout.lower()

    def test_help_content_in_script(self):
        """Script should contain help text for --help option."""
        content = AUTO_ADD_DOCKER_GROUP.read_text()
        # Verify help case exists
        assert "--help" in content
        assert "Usage" in content or "usage" in content

    def test_requires_argument_or_option(self):
        """Script should require username or --scan option."""
        if os.geteuid() != 0:
            pytest.skip("Test requires root to check argument handling")

        result = self.run_script()
        assert result.returncode != 0
        assert "error" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_has_get_canonical_username_function(self):
        """Script should define get_canonical_username function."""
        content = AUTO_ADD_DOCKER_GROUP.read_text()
        assert "get_canonical_username()" in content

    def test_uses_canonical_for_group_check(self):
        """Script should use canonical username for group membership check."""
        content = AUTO_ADD_DOCKER_GROUP.read_text()
        # Should check groups using canonical user
        assert "canonical" in content.lower()
        assert "groups" in content


class TestFixDockerGroupVariants:
    """Tests for fix-docker-group-variants.sh script."""

    def run_script(
        self, *args, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Run fix-docker-group-variants.sh with arguments."""
        script_env = os.environ.copy()
        if env:
            script_env.update(env)
        return subprocess.run(
            ["bash", str(FIX_DOCKER_GROUP_VARIANTS)] + list(args),
            capture_output=True,
            text=True,
            env=script_env,
            timeout=30,
        )

    def test_requires_root(self):
        """Script should require root privileges."""
        if os.geteuid() == 0:
            pytest.skip("Test requires non-root user")

        result = self.run_script("--report")
        assert result.returncode != 0
        assert "root" in result.stderr.lower() or "root" in result.stdout.lower()

    def test_help_flag(self):
        """--help should display usage information (requires root)."""
        if os.geteuid() != 0:
            pytest.skip("Script requires root even for --help")
        result = self.run_script("--help")
        assert result.returncode == 0
        output = result.stdout.lower()
        assert "--report" in output
        assert "--apply" in output

    def test_help_content_in_script(self):
        """Script should contain help text for --help option."""
        content = FIX_DOCKER_GROUP_VARIANTS.read_text()
        # Verify help content exists in the script
        assert "--help" in content
        assert "--report" in content
        assert "--apply" in content
        assert "Usage" in content or "usage" in content

    def test_requires_mode_flag(self):
        """Script should require --report or --apply flag."""
        if os.geteuid() != 0:
            pytest.skip("Test requires root to check mode handling")

        result = self.run_script()
        assert result.returncode != 0
        assert "--report" in result.stdout or "--apply" in result.stdout

    def test_rejects_unknown_options(self):
        """Script should reject unknown options."""
        if os.geteuid() != 0:
            pytest.skip("Test requires root to check option handling")

        result = self.run_script("--unknown")
        assert result.returncode != 0
        assert "unknown" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_has_get_canonical_username_function(self):
        """Script should define get_canonical_username function."""
        content = FIX_DOCKER_GROUP_VARIANTS.read_text()
        assert "get_canonical_username()" in content

    def test_report_mode_logic_exists(self):
        """Script should have report mode implementation."""
        content = FIX_DOCKER_GROUP_VARIANTS.read_text()
        assert "report_mode()" in content or "report_mode" in content
        assert "[OK]" in content
        assert "[VARIANT]" in content

    def test_apply_mode_logic_exists(self):
        """Script should have apply mode implementation."""
        content = FIX_DOCKER_GROUP_VARIANTS.read_text()
        assert "apply_fixes()" in content or "apply_fixes" in content
        assert "gpasswd" in content  # Used to remove users from group


class TestPamAddDockerGroup:
    """Tests for pam-add-docker-group.sh script."""

    def test_script_has_shebang(self):
        """Script should have proper shebang."""
        with open(PAM_ADD_DOCKER_GROUP) as f:
            first_line = f.readline()
        assert first_line.startswith("#!/bin/bash")

    def test_handles_pam_type_check(self):
        """Script should check PAM_TYPE for open_session."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        assert "PAM_TYPE" in content
        assert "open_session" in content

    def test_handles_pam_user_check(self):
        """Script should check PAM_USER is set."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        assert "PAM_USER" in content

    def test_skips_system_users(self):
        """Script should skip system users (UID < 1000)."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        assert "1000" in content
        assert "USER_UID" in content or "uid" in content.lower()

    def test_uses_canonical_resolution(self):
        """Script should use UID-based canonical resolution."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        assert "getent passwd" in content
        assert "CANONICAL_USER" in content

    def test_logs_domain_variant_mismatch(self):
        """Script should log when domain variant mismatch detected."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        assert "PAM_USER" in content
        assert "CANONICAL" in content.upper()
        # Should have logging for mismatch
        assert "log_msg" in content or "LOG" in content

    def test_always_exits_zero(self):
        """PAM script should always exit 0 to not block login."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        # Check for exit 0 at end
        lines = content.strip().split("\n")
        last_line = lines[-1].strip()
        assert last_line == "exit 0"


class TestCanonicalResolutionPattern:
    """Tests to verify the canonical resolution pattern is correctly implemented."""

    def test_add_user_resolution_pattern(self):
        """add-user-to-docker.sh should follow the resolution pattern."""
        content = ADD_USER_TO_DOCKER.read_text()

        # Pattern: Get UID first
        assert "id -u" in content

        # Pattern: Then resolve via getent passwd
        assert "getent passwd" in content

        # Pattern: Store in CANONICAL_USER variable
        assert "CANONICAL_USER" in content

    def test_pam_resolution_pattern(self):
        """pam-add-docker-group.sh should follow the resolution pattern."""
        content = PAM_ADD_DOCKER_GROUP.read_text()

        # Pattern: Get UID from PAM_USER
        assert "id -u" in content
        assert "PAM_USER" in content

        # Pattern: Then resolve via getent passwd
        assert "getent passwd" in content

        # Pattern: Store in CANONICAL_USER variable
        assert "CANONICAL_USER" in content

    def test_auto_add_resolution_pattern(self):
        """auto-add-docker-group.sh should have get_canonical_username function."""
        content = AUTO_ADD_DOCKER_GROUP.read_text()

        # Should define the function
        assert "get_canonical_username()" in content

        # Function should use id -u and getent passwd
        assert "id -u" in content
        assert "getent passwd" in content

    def test_fix_variants_resolution_pattern(self):
        """fix-docker-group-variants.sh should have get_canonical_username function."""
        content = FIX_DOCKER_GROUP_VARIANTS.read_text()

        # Should define the function
        assert "get_canonical_username()" in content

        # Function should use id -u and getent passwd
        assert "id -u" in content
        assert "getent passwd" in content


class TestScriptFeatures:
    """Tests for specific features in the docker group scripts."""

    def test_fix_variants_handles_orphans(self):
        """fix-docker-group-variants.sh should handle orphan entries."""
        content = FIX_DOCKER_GROUP_VARIANTS.read_text()
        assert "ORPHAN" in content or "orphan" in content.lower()

    def test_fix_variants_has_summary(self):
        """fix-docker-group-variants.sh should show summary in both modes."""
        content = FIX_DOCKER_GROUP_VARIANTS.read_text()
        assert "Summary" in content

    def test_auto_add_has_scan_mode(self):
        """auto-add-docker-group.sh should support --scan mode."""
        content = AUTO_ADD_DOCKER_GROUP.read_text()
        assert "--scan" in content
        assert "scan_and_add_new_users" in content or "/home" in content

    def test_add_user_shows_resolution(self):
        """add-user-to-docker.sh should show when resolution differs."""
        content = ADD_USER_TO_DOCKER.read_text()
        # Should display note when input != canonical
        assert "Note:" in content or "Resolved" in content


class TestDockerGroupCheckPattern:
    """Tests for docker group membership check pattern."""

    def test_pam_uses_canonical_for_group_check(self):
        """PAM script should check groups using canonical user."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        # Should check: groups "$CANONICAL_USER" ... | grep docker
        assert "groups" in content
        assert "CANONICAL_USER" in content
        assert "docker" in content

    def test_pam_uses_canonical_for_usermod(self):
        """PAM script should use canonical user in usermod."""
        content = PAM_ADD_DOCKER_GROUP.read_text()
        # Should have: usermod -aG docker "$CANONICAL_USER"
        assert "usermod" in content
        assert "CANONICAL_USER" in content

    def test_add_user_uses_canonical_for_usermod(self):
        """add-user-to-docker.sh should use canonical user in usermod."""
        content = ADD_USER_TO_DOCKER.read_text()
        assert "usermod" in content
        assert "CANONICAL_USER" in content
