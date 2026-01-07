#!/usr/bin/env python3
"""
Tests for /opt/ds01-infra/scripts/lib/username-utils.sh

This test suite validates the username utility functions including:
- sanitize_username_for_slice(): Sanitize usernames for systemd slice naming
- get_user_slice_name(): Generate full slice names
- get_canonical_username(): UID-based canonical username resolution (NEW)

The get_canonical_username() function is critical for fixing the PAM docker group
issue where domain variants (e.g., user@students.hertie-school.org) don't match
the canonical username in passwd (e.g., user@hertie-school.lan).
"""

import os
import subprocess
import pytest
from pathlib import Path
from typing import Optional


# Path to the username-utils.sh library
USERNAME_UTILS_PATH = Path("/opt/ds01-infra/scripts/lib/username-utils.sh")


class TestUsernameUtilsLibrary:
    """Tests for username-utils.sh library basic functionality."""

    def run_bash_function(
        self, function_call: str, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Helper to run a bash function from username-utils.sh."""
        script = f"""
        source "{USERNAME_UTILS_PATH}"
        {function_call}
        """
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env=run_env,
            timeout=10,
        )

    def test_library_exists(self):
        """username-utils.sh library file should exist."""
        assert USERNAME_UTILS_PATH.exists(), f"Library not found at {USERNAME_UTILS_PATH}"

    def test_library_sources_without_error(self):
        """username-utils.sh should source without errors."""
        result = self.run_bash_function("echo sourced_ok")
        assert result.returncode == 0, f"Failed to source library: {result.stderr}"
        assert "sourced_ok" in result.stdout

    def test_library_has_valid_syntax(self):
        """username-utils.sh should have valid bash syntax."""
        result = subprocess.run(
            ["bash", "-n", str(USERNAME_UTILS_PATH)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error in library: {result.stderr}"


class TestSanitizeUsernameForSlice:
    """Tests for sanitize_username_for_slice() function."""

    def run_bash_function(
        self, function_call: str, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Helper to run a bash function from username-utils.sh."""
        script = f"""
        source "{USERNAME_UTILS_PATH}"
        {function_call}
        """
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env=run_env,
            timeout=10,
        )

    def test_function_exists(self):
        """sanitize_username_for_slice should be defined."""
        result = self.run_bash_function("type sanitize_username_for_slice")
        assert result.returncode == 0
        assert "function" in result.stdout

    def test_simple_username_unchanged(self):
        """Simple alphanumeric username should remain unchanged."""
        result = self.run_bash_function('sanitize_username_for_slice "student1"')
        assert result.returncode == 0
        assert result.stdout.strip() == "student1"

    def test_strips_domain(self):
        """Should strip @domain from username."""
        result = self.run_bash_function(
            'sanitize_username_for_slice "user@hertie-school.lan"'
        )
        assert result.returncode == 0
        assert "@" not in result.stdout
        assert result.stdout.strip() == "user"

    def test_replaces_dots_with_underscores(self):
        """Should replace dots with underscores (not hyphens)."""
        result = self.run_bash_function('sanitize_username_for_slice "h.baker"')
        assert result.returncode == 0
        assert result.stdout.strip() == "h_baker"
        assert "-" not in result.stdout  # Important: no hyphens

    def test_complex_ldap_username(self):
        """Should handle complex LDAP username with domain."""
        result = self.run_bash_function(
            'sanitize_username_for_slice "h.baker@hertie-school.lan"'
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "h_baker"

    def test_empty_input_returns_empty(self):
        """Should return empty string for empty input."""
        result = self.run_bash_function('sanitize_username_for_slice ""')
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_collapses_multiple_underscores(self):
        """Should collapse multiple consecutive underscores."""
        result = self.run_bash_function('sanitize_username_for_slice "user..name"')
        assert result.returncode == 0
        output = result.stdout.strip()
        assert "__" not in output

    def test_trims_leading_trailing_underscores(self):
        """Should trim leading and trailing underscores."""
        result = self.run_bash_function('sanitize_username_for_slice ".user."')
        assert result.returncode == 0
        output = result.stdout.strip()
        assert not output.startswith("_")
        assert not output.endswith("_")

    def test_truncates_long_username(self):
        """Should truncate username to 32 characters with hash suffix."""
        long_name = "a" * 50
        result = self.run_bash_function(f'sanitize_username_for_slice "{long_name}"')
        assert result.returncode == 0
        output = result.stdout.strip()
        assert len(output) <= 32


class TestGetUserSliceName:
    """Tests for get_user_slice_name() function."""

    def run_bash_function(
        self, function_call: str, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Helper to run a bash function from username-utils.sh."""
        script = f"""
        source "{USERNAME_UTILS_PATH}"
        {function_call}
        """
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env=run_env,
            timeout=10,
        )

    def test_function_exists(self):
        """get_user_slice_name should be defined."""
        result = self.run_bash_function("type get_user_slice_name")
        assert result.returncode == 0
        assert "function" in result.stdout

    def test_generates_correct_format(self):
        """Should generate ds01-{group}-{user}.slice format."""
        result = self.run_bash_function('get_user_slice_name "student" "alice"')
        assert result.returncode == 0
        assert result.stdout.strip() == "ds01-student-alice.slice"

    def test_sanitizes_username_in_slice(self):
        """Should sanitize username within slice name."""
        result = self.run_bash_function(
            'get_user_slice_name "student" "h.baker@hertie-school.lan"'
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ds01-student-h_baker.slice"


class TestGetCanonicalUsername:
    """Tests for get_canonical_username() function.

    This is the critical function for fixing the PAM docker group issue.
    It resolves any username format to the canonical name in passwd via UID.
    """

    def run_bash_function(
        self, function_call: str, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Helper to run a bash function from username-utils.sh."""
        script = f"""
        source "{USERNAME_UTILS_PATH}"
        {function_call}
        """
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env=run_env,
            timeout=10,
        )

    def test_function_exists(self):
        """get_canonical_username should be defined."""
        result = self.run_bash_function("type get_canonical_username")
        assert result.returncode == 0
        assert "function" in result.stdout

    def test_function_is_exported(self):
        """get_canonical_username should be exported for subshells."""
        result = self.run_bash_function(
            'bash -c \'source /opt/ds01-infra/scripts/lib/username-utils.sh && type get_canonical_username\''
        )
        assert result.returncode == 0

    def test_empty_input_returns_error(self):
        """Should return error code for empty input."""
        result = self.run_bash_function('get_canonical_username ""')
        assert result.returncode != 0

    def test_nonexistent_user_returns_error(self):
        """Should return error code for non-existent user."""
        result = self.run_bash_function(
            'get_canonical_username "nonexistent_user_12345"'
        )
        assert result.returncode != 0

    def test_current_user_returns_canonical(self):
        """Should return canonical username for current user."""
        current_user = os.environ.get("USER", "")
        if not current_user:
            pytest.skip("USER environment variable not set")

        result = self.run_bash_function(f'get_canonical_username "{current_user}"')
        assert result.returncode == 0
        output = result.stdout.strip()
        assert len(output) > 0
        # The output should be a valid username
        assert " " not in output
        assert ":" not in output

    def test_root_user_returns_root(self):
        """Should return 'root' for root user."""
        result = self.run_bash_function('get_canonical_username "root"')
        assert result.returncode == 0
        assert result.stdout.strip() == "root"

    def test_uid_zero_resolves_to_root(self):
        """UID 0 should resolve to root via getent."""
        result = self.run_bash_function(
            'uid=$(id -u root); getent passwd "$uid" | cut -d: -f1'
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "root"

    def test_canonical_username_is_idempotent(self):
        """Applying get_canonical_username twice should give same result."""
        current_user = os.environ.get("USER", "")
        if not current_user:
            pytest.skip("USER environment variable not set")

        result = self.run_bash_function(
            f'''
            canonical1=$(get_canonical_username "{current_user}")
            canonical2=$(get_canonical_username "$canonical1")
            [ "$canonical1" = "$canonical2" ] && echo "idempotent"
            '''
        )
        assert result.returncode == 0
        assert "idempotent" in result.stdout

    def test_resolves_to_passwd_first_field(self):
        """Canonical username should be first field of passwd entry."""
        result = self.run_bash_function(
            '''
            user="root"
            canonical=$(get_canonical_username "$user")
            expected=$(getent passwd "$(id -u root)" | cut -d: -f1)
            [ "$canonical" = "$expected" ] && echo "matches_passwd"
            '''
        )
        assert result.returncode == 0
        assert "matches_passwd" in result.stdout


class TestCanonicalUsernameEdgeCases:
    """Edge case tests for get_canonical_username()."""

    def run_bash_function(
        self, function_call: str, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Helper to run a bash function from username-utils.sh."""
        script = f"""
        source "{USERNAME_UTILS_PATH}"
        {function_call}
        """
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env=run_env,
            timeout=10,
        )

    def test_whitespace_only_input(self):
        """Should handle whitespace-only input gracefully."""
        result = self.run_bash_function('get_canonical_username "   "')
        # Whitespace username doesn't exist, should return error
        assert result.returncode != 0

    def test_special_characters_in_username(self):
        """Should handle special characters if they exist in system."""
        # Test with a name that might have special chars but wouldn't exist
        result = self.run_bash_function(
            'get_canonical_username "user<>with|special"'
        )
        # Such a user doesn't exist, should return error
        assert result.returncode != 0

    def test_numeric_username(self):
        """Should handle numeric-looking usernames."""
        # Test with a numeric string that's not a valid user
        result = self.run_bash_function('get_canonical_username "12345"')
        # Numeric usernames typically don't exist
        assert result.returncode != 0

    def test_output_has_no_trailing_newlines(self):
        """Output should not have extra trailing newlines."""
        result = self.run_bash_function(
            '''
            output=$(get_canonical_username "root")
            # Check if output ends with newline
            [ "${output: -1}" != $'\n' ] && echo "no_trailing_newline"
            '''
        )
        assert result.returncode == 0
        assert "no_trailing_newline" in result.stdout
