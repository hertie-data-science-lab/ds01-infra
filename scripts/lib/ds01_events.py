#!/usr/bin/env python3
"""
/opt/ds01-infra/scripts/lib/ds01_events.py
Shared event logging library for DS01 infrastructure.

This module provides a standardised event logging interface for both Python and Bash scripts.
Events are written to /var/log/ds01/events.jsonl in a consistent JSON envelope format.

Design principles:
- Never blocks calling script (returns False on failure, never raises)
- Atomic writes (single JSON line < 4KB for PIPE_BUF guarantee)
- Minimal logging overhead (NullHandler by default)
- Callable from Python (import) or Bash (CLI mode)

Usage (Python):
    from ds01_events import log_event

    log_event('container.create', user='alice', source='docker-wrapper',
              container='proj', image='ds01/pytorch:latest')

    # Returns True on success, False on failure

Usage (Bash via CLI):
    python3 scripts/lib/ds01_events.py log container.create user=alice source=docker-wrapper container=proj

Schema:
    {
        "timestamp": "2026-01-30T14:30:00Z",  # UTC ISO 8601 with Z suffix
        "event_type": "container.create",      # Dot-separated category.action
        "user": "alice",                       # Optional, omit if system event
        "source": "docker-wrapper",            # Script/component name
        "details": {                           # Optional, event-specific fields
            "container": "alice-jupyter",
            "image": "ds01/pytorch:latest"
        },
        "schema_version": "1"                  # For future evolution
    }
"""

from __future__ import annotations

import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Configuration
EVENTS_FILE = Path("/var/log/ds01/events.jsonl")
SCHEMA_VERSION = "1"
MAX_EVENT_SIZE = 4096  # PIPE_BUF - atomic write guarantee

# Add NullHandler to avoid "No handlers found" warnings
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# Predefined event types and their expected detail fields
EVENT_TYPES = {
    # Container lifecycle
    "container.create": ["user", "container", "interface", "gpu", "image"],
    "container.start": ["user", "container"],
    "container.stop": ["user", "container", "reason"],
    "container.remove": ["user", "container", "gpu_released"],

    # GPU allocation
    "gpu.allocate": ["user", "container", "gpu", "priority", "container_type"],
    "gpu.release": ["user", "container", "gpu", "reason"],
    "gpu.reject": ["user", "container", "reason"],
    "gpu.hold": ["user", "container", "gpu", "duration"],

    # System events
    "health.check": ["status", "checks_passed", "checks_failed"],
    "health.fail": ["check", "message"],
    "system.startup": ["component"],
    "system.shutdown": ["component"],

    # Bare metal detection
    "bare_metal.detect": ["user", "pids", "message"],
    "bare_metal.warning": ["user", "pids", "message"],

    # Admin actions
    "admin.cleanup": ["containers_removed", "gpus_freed"],
    "admin.config_change": ["field", "old_value", "new_value"],
    "admin.user_override": ["user", "field", "value", "reason"],

    # Monitoring
    "monitor.idle_detect": ["user", "container", "idle_duration"],
    "monitor.runtime_exceed": ["user", "container", "runtime"],
    "monitor.gpu_stale": ["user", "container", "gpu", "stopped_duration"],

    # Workload detection (Phase 2)
    "detection.container_discovered": ["user", "container_id", "name", "origin", "has_gpu", "image"],
    "detection.container_exited": ["user", "container_id", "name", "origin"],
    "detection.container_status_changed": ["user", "container_id", "name", "old_status", "new_status"],
    "detection.host_gpu_process_discovered": ["user", "pid", "cmdline", "gpu_memory_mb", "gpu_uuid"],
    "detection.host_gpu_process_exited": ["user", "pid", "cmdline"],

    # Docker wrapper events
    "docker.intercept": ["command", "user", "container_type"],
    "docker.cgroup_inject": ["user", "cgroup_parent"],
    "docker.gpu_rewrite": ["user", "original", "rewritten"],

    # Authentication/Authorization
    "auth.sudo_grant": ["user", "command"],
    "auth.access_denied": ["user", "resource", "reason"],

    # Test/Verification events
    "test.selftest": ["source", "result"],
    "test.cli": ["source", "result"],
    "test.bash_wrapper": ["source", "result"],
    "verify.python": ["source"],
    "verify.bash": ["source"],
}


def log_event(
    event_type: str,
    user: str | None = None,
    source: str | None = None,
    **details: Any
) -> bool:
    """
    Log a structured event to the DS01 event log.

    This function NEVER raises exceptions - it returns False on any error
    and prints a warning to stderr. This ensures event logging never breaks
    calling scripts.

    Args:
        event_type: Dot-separated event type (e.g., "container.create")
        user: Optional username associated with event (omit for system events)
        source: Optional source component/script name
        **details: Additional event-specific key-value pairs

    Returns:
        True if event was logged successfully, False on any error

    Examples:
        >>> log_event('container.create', user='alice', source='docker-wrapper',
        ...           container='proj', image='ds01/pytorch:latest')
        True

        >>> log_event('system.startup', source='monitoring', component='prometheus')
        True

        >>> log_event('gpu.allocate', user='bob', source='gpu-allocator',
        ...           gpu='0:1', priority=50, container_type='devcontainer')
        True
    """
    try:
        # Build event envelope
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "event_type": event_type,
            "schema_version": SCHEMA_VERSION,
        }

        # Add optional fields
        if user is not None and user != "":
            event["user"] = user

        if source is not None and source != "":
            event["source"] = source

        # Add details if any were provided
        if details:
            event["details"] = details

        # Serialize to JSON
        event_json = json.dumps(event, separators=(',', ':'))

        # Check size constraint (PIPE_BUF for atomic writes)
        if len(event_json) > MAX_EVENT_SIZE:
            print(
                f"Warning: Event too large ({len(event_json)} > {MAX_EVENT_SIZE} bytes), truncating details",
                file=sys.stderr
            )
            # Truncate details to fit
            event["details"] = {"truncated": True, "original_size": len(event_json)}
            event_json = json.dumps(event, separators=(',', ':'))

        # Ensure parent directory exists
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Append to file (atomic write for single line under PIPE_BUF)
        with open(EVENTS_FILE, 'a') as f:
            f.write(event_json + '\n')

        return True

    except PermissionError:
        # Permission errors are expected if log file isn't writable
        # Admin should run: sudo chmod 666 /var/log/ds01/events.jsonl
        print(
            f"Warning: Event logging failed - permission denied on {EVENTS_FILE}",
            file=sys.stderr
        )
        return False

    except Exception as e:
        # Catch all other errors - never break the calling script
        print(
            f"Warning: Event logging failed: {type(e).__name__}: {e}",
            file=sys.stderr
        )
        return False


def main() -> int:
    """
    CLI interface for event logging (called by bash wrapper).

    Usage:
        python3 ds01_events.py log <event_type> [user=<user>] [source=<source>] [key=value ...]
        python3 ds01_events.py types

    Returns:
        0 on success, 1 on error
    """
    if len(sys.argv) < 2:
        print("Usage: ds01_events.py <command> [args]", file=sys.stderr)
        print("\nCommands:", file=sys.stderr)
        print("  log <event_type> [key=value ...]  - Log an event", file=sys.stderr)
        print("  types                             - List predefined event types", file=sys.stderr)
        print("\nExamples:", file=sys.stderr)
        print("  ds01_events.py log container.create user=alice source=wrapper container=proj", file=sys.stderr)
        print("  ds01_events.py log test.cli source=verify result=success", file=sys.stderr)
        return 1

    command = sys.argv[1]

    if command == "log":
        if len(sys.argv) < 3:
            print("Error: Event type required", file=sys.stderr)
            print("Usage: ds01_events.py log <event_type> [key=value ...]", file=sys.stderr)
            return 1

        event_type = sys.argv[2]
        user = None
        source = None
        details = {}

        # Parse key=value arguments
        for arg in sys.argv[3:]:
            if '=' not in arg:
                print(f"Warning: Ignoring malformed argument '{arg}' (expected key=value)", file=sys.stderr)
                continue

            key, value = arg.split('=', 1)

            # Handle special fields
            if key == "user":
                user = value if value else None
            elif key == "source":
                source = value if value else None
            else:
                # Try to parse as JSON for complex values, otherwise use as string
                try:
                    details[key] = json.loads(value)
                except json.JSONDecodeError:
                    details[key] = value

        # Log the event
        success = log_event(event_type, user=user, source=source, **details)

        # Return 0 for success, 1 for failure (but never crash)
        return 0 if success else 1

    elif command == "types":
        print("Predefined event types:\n")
        for event_type, fields in sorted(EVENT_TYPES.items()):
            print(f"  {event_type}")
            if fields:
                print(f"    Expected fields: {', '.join(fields)}")
        return 0

    else:
        print(f"Error: Unknown command '{command}'", file=sys.stderr)
        print("Use 'log' or 'types'", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
