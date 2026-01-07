#!/usr/bin/env python3
"""
Commit message validator for DS01 Infrastructure.

Validates:
1. Conventional commit format (flexible prefixes)
2. No AI attribution (Claude, Generated with, etc.)

Usage:
    validate-commit-msg.py <commit-msg-file>

Exit codes:
    0 - Valid commit message
    1 - Invalid commit message (with error details)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Allowed commit types (conventional commits)
ALLOWED_TYPES = {
    "feat",      # New feature
    "fix",       # Bug fix
    "docs",      # Documentation only
    "refactor",  # Code change without feature/fix
    "test",      # Adding/updating tests
    "chore",     # Maintenance tasks
    "ci",        # CI/CD changes
    "perf",      # Performance improvement
    "build",     # Build system changes
    "style",     # Code style (formatting, etc.)
    "revert",    # Revert previous commit
}

# Conventional commit pattern
# Format: type(scope)!: subject
# - type: required (from ALLOWED_TYPES)
# - (scope): optional
# - !: optional (indicates breaking change)
# - subject: required (the actual message)
CONVENTIONAL_PATTERN = re.compile(
    r"^(?P<type>\w+)"           # Type (required)
    r"(?:\((?P<scope>[^)]+)\))?" # Scope (optional)
    r"(?P<breaking>!)?"         # Breaking change indicator (optional)
    r": "                       # Separator (required)
    r"(?P<subject>.+)$",        # Subject (required)
    re.MULTILINE
)

# AI attribution patterns to block
AI_PATTERNS = [
    re.compile(r"claude", re.IGNORECASE),
    re.compile(r"generated with", re.IGNORECASE),
    re.compile(r"co-authored-by:\s*claude", re.IGNORECASE),
    re.compile(r"co-authored-by:\s*anthropic", re.IGNORECASE),
    re.compile(r"🤖.*generated", re.IGNORECASE),
]


def validate_conventional_format(message: str) -> tuple[bool, str]:
    """Validate that the commit message follows conventional commit format."""
    # Get first line (subject line)
    first_line = message.split("\n")[0].strip()

    if not first_line:
        return False, "Commit message is empty"

    match = CONVENTIONAL_PATTERN.match(first_line)
    if not match:
        return False, (
            f"Invalid format. Expected: type(scope): subject\n"
            f"  Got: {first_line}\n"
            f"  Allowed types: {', '.join(sorted(ALLOWED_TYPES))}"
        )

    commit_type = match.group("type")
    if commit_type not in ALLOWED_TYPES:
        return False, (
            f"Invalid type '{commit_type}'.\n"
            f"  Allowed types: {', '.join(sorted(ALLOWED_TYPES))}"
        )

    subject = match.group("subject")
    if len(subject) < 3:
        return False, "Subject too short (minimum 3 characters)"

    if len(first_line) > 72:
        return False, f"Subject line too long ({len(first_line)} > 72 characters)"

    if first_line.endswith("."):
        return False, "Subject should not end with a period"

    return True, ""


def validate_no_ai_attribution(message: str) -> tuple[bool, str]:
    """Validate that the commit message doesn't contain AI attribution."""
    for pattern in AI_PATTERNS:
        if pattern.search(message):
            return False, (
                "Commit message contains AI attribution.\n"
                "  Please remove references to Claude, 'Generated with', etc."
            )
    return True, ""


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: validate-commit-msg.py <commit-msg-file>", file=sys.stderr)
        return 1

    commit_msg_file = Path(sys.argv[1])
    if not commit_msg_file.exists():
        print(f"Error: File not found: {commit_msg_file}", file=sys.stderr)
        return 1

    message = commit_msg_file.read_text().strip()

    # Skip validation for merge commits and fixup commits
    if message.startswith("Merge ") or message.startswith("fixup! "):
        return 0

    # Validate conventional format
    valid, error = validate_conventional_format(message)
    if not valid:
        print(f"❌ Commit rejected: {error}", file=sys.stderr)
        print("\nExamples of valid commits:", file=sys.stderr)
        print("  feat: add GPU monitoring dashboard", file=sys.stderr)
        print("  fix(gpu): resolve allocation race condition", file=sys.stderr)
        print("  docs: update README installation steps", file=sys.stderr)
        print("  feat!: new API for container management", file=sys.stderr)
        return 1

    # Validate no AI attribution
    valid, error = validate_no_ai_attribution(message)
    if not valid:
        print(f"❌ Commit rejected: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
