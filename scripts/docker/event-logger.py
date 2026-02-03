#!/usr/bin/env python3
"""
DS01 Event Logger - Append-Only Audit Trail

This is an APPEND-ONLY audit log for historical events and debugging.
It is NOT a source of truth - Docker labels are the single source of truth.

Design principle:
- If events.jsonl is lost, NO IMPACT on system operation
- System reconstructs current state from Docker labels only
- Events are for: audit, debugging, dashboards, alerts
- Events are NOT used for: state recovery, allocation decisions

Usage:
    event-logger.py log <event_type> [key=value ...]
    event-logger.py tail [N]
    event-logger.py search <pattern>
    event-logger.py user <username>
    event-logger.py container <name>
    event-logger.py types
"""

import sys
import json
import re
from pathlib import Path
from typing import Dict, List

# Import shared event logging library
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from ds01_events import log_event, EVENTS_FILE, EVENT_TYPES as BASE_EVENT_TYPES


# Expanded event types for DS01 infrastructure
EVENT_TYPES = {
    # Container lifecycle
    "container.create": ["user", "container", "image", "gpu"],
    "container.start": ["user", "container"],
    "container.stop": ["user", "container", "reason"],
    "container.remove": ["user", "container"],

    # GPU allocation
    "gpu.allocate": ["user", "container", "gpu_uuid", "mig_profile"],
    "gpu.release": ["user", "container", "gpu_uuid", "reason"],
    "gpu.reject": ["user", "container", "reason"],

    # Auth events
    "auth.denied": ["user", "reason", "requested"],

    # Resource events
    "resource.cgroup_limit": ["user", "container", "resource", "limit"],
    "resource.oom_kill": ["user", "container"],

    # Maintenance
    "maintenance.cleanup": ["containers_stopped", "gpus_released", "source"],
    "maintenance.idle_kill": ["user", "container", "idle_duration"],
    "maintenance.runtime_kill": ["user", "container", "runtime"],

    # Monitoring
    "monitoring.dcgm_restart": ["reason"],
    "monitoring.scrape_failure": ["target", "error"],

    # Config changes
    "config.change": ["field", "old_value", "new_value", "changed_by"],

    # Unmanaged workload detection (LOG-03)
    "detection.unmanaged_container": ["container", "user", "source"],
    "detection.host_gpu_process": ["user", "pid", "command"],

    # Legacy event types (backward compatibility)
    "container.created": ["user", "container", "interface", "gpu"],
    "container.started": ["user", "container"],
    "container.stopped": ["user", "container", "reason"],
    "container.removed": ["user", "container", "gpu_released"],
    "gpu.allocated": ["user", "container", "gpu", "priority"],
    "gpu.released": ["user", "container", "gpu", "reason"],
    "gpu.rejected": ["user", "container", "reason"],
    "health.check": ["status", "checks_passed", "checks_failed"],
    "health.failed": ["check", "message"],
    "bare_metal.warning": ["user", "pids", "message"],
    "admin.cleanup": ["containers_removed", "gpus_freed"],
    "admin.config_change": ["field", "old_value", "new_value"],
}


class EventReader:
    """Simple reader for querying events (tail/search operations)."""

    def __init__(self, log_file: Path = EVENTS_FILE):
        self.log_file = log_file

    def tail(self, n: int = 20) -> List[Dict]:
        """Get last N events."""
        if not self.log_file.exists():
            return []

        events = []
        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
                for line in lines[-n:]:
                    try:
                        events.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        except (IOError, OSError):
            pass

        return events

    def search(self, pattern: str, limit: int = 100) -> List[Dict]:
        """Search events matching regex pattern."""
        if not self.log_file.exists():
            return []

        events = []
        regex = re.compile(pattern, re.IGNORECASE)

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    if regex.search(line):
                        try:
                            events.append(json.loads(line.strip()))
                            if len(events) >= limit:
                                break
                        except json.JSONDecodeError:
                            continue
        except (IOError, OSError):
            pass

        return events

    def get_events_for_container(self, container: str) -> List[Dict]:
        """Get all events for a specific container."""
        return self.search(f'"container":\\s*"{re.escape(container)}"')

    def get_events_for_user(self, user: str) -> List[Dict]:
        """Get all events for a specific user."""
        return self.search(f'"user":\\s*"{re.escape(user)}"')


def main():
    """CLI interface"""
    reader = EventReader()

    if len(sys.argv) < 2:
        print("Usage: event-logger.py <command> [args]")
        print("\nCommands:")
        print("  log <event_type> [key=value ...]  - Log an event")
        print("  tail [N]                          - Show last N events (default: 20)")
        print("  search <pattern>                  - Search events by regex")
        print("  user <username>                   - Show events for user")
        print("  container <name>                  - Show events for container")
        print("  types                             - List predefined event types")
        print("\nExample:")
        print("  event-logger.py log container.create user=alice container=proj gpu=1.2")
        sys.exit(1)

    command = sys.argv[1]

    if command == "log":
        if len(sys.argv) < 3:
            print("Error: Event type required")
            sys.exit(1)

        event_type = sys.argv[2]
        user = None
        source = None
        details = {}

        # Parse key=value arguments
        for arg in sys.argv[3:]:
            if '=' in arg:
                key, value = arg.split('=', 1)
                # Handle special fields
                if key == "user":
                    user = value if value else None
                elif key == "source":
                    source = value if value else None
                else:
                    # Try to parse as JSON for complex values
                    try:
                        details[key] = json.loads(value)
                    except json.JSONDecodeError:
                        details[key] = value

        # Delegate to shared library
        if log_event(event_type, user=user, source=source, **details):
            print(f"Logged: {event_type}")
        else:
            print("Warning: Event logging failed (check permissions on /var/log/ds01/events.jsonl)", file=sys.stderr)

    elif command == "tail":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        events = reader.tail(n)

        if not events:
            print("No events found")
        else:
            for event in events:
                # Handle both old (ts/event) and new (timestamp/event_type) schema
                ts = event.get('timestamp', event.get('ts', '?'))
                evt = event.get('event_type', event.get('event', '?'))
                # Remove timestamp and event_type for details display
                details = {k: v for k, v in event.items()
                          if k not in ('timestamp', 'ts', 'event_type', 'event', 'schema_version')}
                details_str = ' '.join(f"{k}={v}" for k, v in details.items())
                print(f"{ts} {evt} {details_str}")

    elif command == "search":
        if len(sys.argv) < 3:
            print("Error: Search pattern required")
            sys.exit(1)

        pattern = sys.argv[2]
        events = reader.search(pattern)

        if not events:
            print(f"No events matching '{pattern}'")
        else:
            for event in events:
                print(json.dumps(event))

    elif command == "user":
        if len(sys.argv) < 3:
            print("Error: Username required")
            sys.exit(1)

        user = sys.argv[2]
        events = reader.get_events_for_user(user)

        print(f"Events for user '{user}':")
        for event in events[-50:]:  # Last 50
            ts = event.get('timestamp', event.get('ts', '?'))
            evt = event.get('event_type', event.get('event', '?'))
            # Extract container from event or details
            container = event.get('container', event.get('details', {}).get('container', ''))
            print(f"  {ts} {evt} {container}")

    elif command == "container":
        if len(sys.argv) < 3:
            print("Error: Container name required")
            sys.exit(1)

        container = sys.argv[2]
        events = reader.get_events_for_container(container)

        print(f"Events for container '{container}':")
        for event in events:
            ts = event.get('timestamp', event.get('ts', '?'))
            evt = event.get('event_type', event.get('event', '?'))
            # Remove common fields for display
            details = {k: v for k, v in event.items()
                      if k not in ('timestamp', 'ts', 'event_type', 'event', 'container', 'schema_version')}
            # Also check details dict
            if 'details' in event:
                for k, v in event['details'].items():
                    if k != 'container':
                        details[k] = v
            details_str = ' '.join(f"{k}={v}" for k, v in details.items())
            print(f"  {ts} {evt} {details_str}")

    elif command == "types":
        print("Predefined event types:\n")
        for event_type, fields in sorted(EVENT_TYPES.items()):
            print(f"  {event_type}")
            if fields:
                print(f"    Expected fields: {', '.join(fields)}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
