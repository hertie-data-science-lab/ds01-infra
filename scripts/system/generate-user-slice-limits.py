#!/usr/bin/env python3
"""
DS01 Infrastructure - Generate User Slice Resource Limits
Reads config/runtime/resource-limits.yaml and generates systemd drop-in files
that enforce per-user aggregate resource limits.

Usage:
    generate-user-slice-limits.py [--dry-run] [--verbose] [--user USERNAME]

Purpose:
    This is the foundation of Phase 4 comprehensive resource enforcement.
    Translates YAML config aggregate sections into systemd drop-in configurations
    that enforce CPU, memory, and pids limits on existing DS01 user slices.

    Per-user limits prevent a single user from consuming unlimited resources
    across multiple containers. Container limits (via Docker) remain the primary
    enforcement, but aggregate limits provide an additional safety boundary.

Output:
    Creates/updates systemd drop-in files at:
    /etc/systemd/system/ds01-{group}-{sanitized_user}.slice.d/10-resource-limits.conf

    Drop-in format:
        [Slice]
        CPUQuota={cpu_quota}
        MemoryMax={memory_max}
        MemoryHigh={memory_high}
        TasksMax={tasks_max}

    For admin users: No drop-in file (unlimited aggregate resources).

Example:
    # Regenerate all user slice limits
    sudo python3 generate-user-slice-limits.py

    # Dry-run to preview changes
    python3 generate-user-slice-limits.py --dry-run

    # Update limits for single user (fast, for create-user-slice.sh integration)
    sudo python3 generate-user-slice-limits.py --user alice
"""

import sys
import os
import argparse
import yaml
from pathlib import Path

# Import username sanitization utility
script_dir = Path(__file__).resolve().parent
lib_dir = script_dir.parent / "lib"
sys.path.insert(0, str(lib_dir))

try:
    from username_utils import sanitize_username_for_slice
except ImportError:
    # Fallback if library not available
    import re
    def sanitize_username_for_slice(username: str) -> str:
        if not username:
            return username
        if '@' in username:
            username = username.split('@')[0]
        sanitized = username.replace('.', '_')
        sanitized = re.sub(r'[^a-zA-Z0-9_:]', '_', sanitized)
        sanitized = re.sub(r'_+', '_', sanitized).strip('_')
        return sanitized


def load_config(config_path: Path) -> dict:
    """Load and parse resource-limits.yaml."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


def load_group_members(config_dir: Path, group_name: str) -> list:
    """Load group members from config/runtime/groups/{group}.members file."""
    member_file = config_dir / "groups" / f"{group_name}.members"

    if not member_file.exists():
        return []

    members = []
    try:
        with open(member_file) as f:
            for line in f:
                line = line.split('#')[0].strip()
                if line:
                    members.append(line)
    except PermissionError:
        return []

    return members


def get_all_users_with_groups(config: dict, config_dir: Path) -> dict:
    """Get all users mapped to their groups.

    Returns:
        dict: {username: group_name}
    """
    users = {}
    groups = config.get('groups', {})

    for group_name in groups:
        members = load_group_members(config_dir, group_name)
        for username in members:
            users[username] = group_name

    return users


def get_aggregate_limits(config: dict, username: str, group: str) -> dict | None:
    """Get aggregate limits for a user.

    Resolution order:
    1. User overrides aggregate section
    2. Group aggregate section
    3. None (admin group or no aggregate section)

    Returns:
        dict with cpu_quota, memory_max, memory_high, tasks_max or None
    """
    # Check user overrides first
    user_overrides = config.get('user_overrides', {})
    if username in user_overrides:
        override = user_overrides[username]
        if 'aggregate' in override:
            return override['aggregate']

    # Check group aggregate
    groups = config.get('groups', {})
    if group in groups:
        group_config = groups[group]
        if 'aggregate' in group_config:
            return group_config['aggregate']

    # No aggregate limits (admin or missing config)
    return None


def generate_drop_in_content(limits: dict) -> str:
    """Generate systemd drop-in file content from aggregate limits."""
    content = "[Slice]\n"
    content += f"CPUQuota={limits['cpu_quota']}\n"
    content += f"MemoryMax={limits['memory_max']}\n"
    content += f"MemoryHigh={limits['memory_high']}\n"
    content += f"TasksMax={limits['tasks_max']}\n"
    return content


def write_drop_in(username: str, group: str, limits: dict, dry_run: bool, verbose: bool) -> bool:
    """Write drop-in file for a user.

    Returns:
        True if drop-in was written/updated, False if skipped
    """
    sanitized = sanitize_username_for_slice(username)
    slice_name = f"ds01-{group}-{sanitized}.slice"
    drop_in_dir = Path(f"/etc/systemd/system/{slice_name}.d")
    drop_in_file = drop_in_dir / "10-resource-limits.conf"

    content = generate_drop_in_content(limits)

    if dry_run:
        print(f"\n[DRY-RUN] Would write: {drop_in_file}")
        print(content)
        return True

    # Check if content already matches (idempotent)
    if drop_in_file.exists():
        with open(drop_in_file) as f:
            existing_content = f.read()
        if existing_content == content:
            if verbose:
                print(f"  ✓ {slice_name} (unchanged)")
            return False

    # Create drop-in directory
    drop_in_dir.mkdir(parents=True, exist_ok=True)

    # Write drop-in file
    with open(drop_in_file, 'w') as f:
        f.write(content)

    if verbose:
        print(f"  ✓ {slice_name} (updated)")

    return True


def remove_stale_drop_ins(current_users: set, config_dir: Path, dry_run: bool, verbose: bool):
    """Remove drop-in directories for users no longer in any group."""
    systemd_dir = Path("/etc/systemd/system")

    if not systemd_dir.exists():
        return

    # Find all ds01-*-*.slice.d directories
    for drop_in_dir in systemd_dir.glob("ds01-*-*.slice.d"):
        # Extract group and sanitized username from path
        # Format: ds01-{group}-{sanitized_user}.slice.d
        slice_name = drop_in_dir.name.replace(".d", "")
        parts = slice_name.split("-")

        if len(parts) < 3:
            continue

        group = parts[1]
        sanitized_user = "-".join(parts[2:]).replace(".slice", "")

        # Check if this sanitized username matches any current user
        found = False
        for username in current_users:
            if sanitize_username_for_slice(username) == sanitized_user:
                found = True
                break

        if not found:
            if dry_run:
                print(f"\n[DRY-RUN] Would remove stale: {drop_in_dir}")
            else:
                # Remove drop-in directory
                import shutil
                try:
                    shutil.rmtree(drop_in_dir)
                    if verbose:
                        print(f"  ✗ Removed stale: {slice_name}")
                except Exception as e:
                    print(f"  ! Failed to remove {drop_in_dir}: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate systemd drop-in files for per-user aggregate resource limits"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be written without writing")
    parser.add_argument("--verbose", action="store_true",
                        help="Show detailed output")
    parser.add_argument("--user", metavar="USERNAME",
                        help="Only generate limits for specific user (for fast updates)")

    args = parser.parse_args()

    # Require root unless dry-run
    if not args.dry_run and os.geteuid() != 0:
        print("Error: This script must be run as root (use sudo)", file=sys.stderr)
        print("Hint: Use --dry-run to preview without writing", file=sys.stderr)
        sys.exit(1)

    # Load configuration
    config_path = Path("/opt/ds01-infra/config/runtime/resource-limits.yaml")
    config_dir = config_path.parent

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML in {config_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if aggregate limits are enabled
    enforcement = config.get('enforcement', {})
    if not enforcement.get('aggregate_limits', False):
        print("Note: Aggregate limits disabled in config (enforcement.aggregate_limits: false)")
        if not args.dry_run:
            sys.exit(0)

    # Get all users
    all_users = get_all_users_with_groups(config, config_dir)

    if not all_users:
        print("Warning: No users found in group membership files", file=sys.stderr)
        sys.exit(0)

    # Filter to single user if requested
    if args.user:
        if args.user not in all_users:
            print(f"Error: User '{args.user}' not found in any group", file=sys.stderr)
            sys.exit(1)
        all_users = {args.user: all_users[args.user]}

    if args.verbose or args.dry_run:
        print(f"Generating aggregate limit drop-ins for {len(all_users)} user(s)...")

    # Generate drop-ins
    updated_count = 0
    skipped_count = 0

    for username, group in sorted(all_users.items()):
        limits = get_aggregate_limits(config, username, group)

        if limits is None:
            if args.verbose:
                print(f"  - {username} ({group}): No aggregate limits (admin or unconfigured)")
            skipped_count += 1
            continue

        if write_drop_in(username, group, limits, args.dry_run, args.verbose):
            updated_count += 1
        else:
            skipped_count += 1

    # Clean up stale drop-ins (only if processing all users, not single user)
    if not args.user:
        remove_stale_drop_ins(set(all_users.keys()), config_dir, args.dry_run, args.verbose)

    # Reload systemd if any changes made
    if updated_count > 0 and not args.dry_run:
        if args.verbose:
            print("\nReloading systemd daemon...")
        os.system("systemctl daemon-reload")

    # Summary
    if args.verbose or args.dry_run:
        print(f"\nSummary: {updated_count} updated, {skipped_count} unchanged/skipped")

    sys.exit(0)


if __name__ == "__main__":
    main()
