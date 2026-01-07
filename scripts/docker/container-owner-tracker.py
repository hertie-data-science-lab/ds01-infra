#!/usr/bin/env python3
"""
Container Ownership Tracker - Real-time ownership detection daemon

Listens to Docker events and determines container ownership via multiple strategies:
1. Docker labels (ds01.user, aime.mlc.USER)
2. Container name pattern (name._.uid)
3. Bind mount paths (/home/{user}/...)
4. devcontainer.local_folder label
5. Docker Compose working directory

This enables the dashboard to show ALL containers regardless of how they were created
(docker-compose, docker run, devcontainers, etc.).

Usage:
    python3 container-owner-tracker.py          # Run daemon (foreground)
    systemctl start ds01-container-owner-tracker  # Run as service

Output: /var/lib/ds01/opa/container-owners.json
"""

import fcntl
import json
import os
import pwd
import subprocess
import sys
import signal
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator


# Configuration
OUTPUT_FILE = Path("/var/lib/ds01/opa/container-owners.json")
LOCK_FILE = Path("/var/lib/ds01/opa/container-owners.lock")
DOCKER_BIN = "/usr/bin/docker"
LOG_PREFIX = "[container-owner-tracker]"


@contextmanager
def file_lock(lock_path: Path, timeout: float = 10.0) -> Generator[None, None, None]:
    """
    Acquire exclusive lock on file for safe concurrent access.

    Used to prevent race conditions between tracker and sync-container-owners.py.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        # Try to acquire lock with timeout
        import time

        start = time.time()
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() - start > timeout:
                    raise TimeoutError(f"Could not acquire lock on {lock_path}")
                time.sleep(0.1)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def log(msg: str, error: bool = False) -> None:
    """Log message to stdout/stderr with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output = sys.stderr if error else sys.stdout
    print(f"{timestamp} {LOG_PREFIX} {msg}", file=output, flush=True)


class ContainerOwnerTracker:
    """Tracks container ownership via Docker events."""

    def __init__(self):
        self.owners: dict[str, Any] = self._load_existing()
        self._running = True

    def _load_existing(self) -> dict[str, Any]:
        """Load existing ownership data from file."""
        if OUTPUT_FILE.exists():
            try:
                with open(OUTPUT_FILE) as f:
                    data = json.load(f)
                    log(f"Loaded {len(data.get('containers', {}))} existing entries")
                    return data
            except (json.JSONDecodeError, IOError) as e:
                log(f"Warning: Could not load existing data: {e}", error=True)
        return {
            "containers": {},
            "admins": [],
            "service_users": ["ds01-dashboard"],
        }

    def _save(self) -> None:
        """Atomically save ownership data to file with locking."""
        self.owners["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Ensure directory exists
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

        try:
            with file_lock(LOCK_FILE):
                # Atomic write: temp file then rename
                temp = OUTPUT_FILE.with_suffix(".tmp")
                with open(temp, "w") as f:
                    json.dump(self.owners, f, indent=2)
                temp.rename(OUTPUT_FILE)
                os.chmod(OUTPUT_FILE, 0o644)
        except TimeoutError:
            log("Warning: Could not acquire lock, skipping save", error=True)
        except IOError as e:
            log(f"Error saving ownership data: {e}", error=True)

    def _inspect_container(self, container_id: str) -> dict[str, Any] | None:
        """Get container details via docker inspect."""
        try:
            result = subprocess.run(
                [DOCKER_BIN, "inspect", container_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data[0] if data else None
        except subprocess.TimeoutExpired:
            log(f"Timeout inspecting container {container_id[:12]}", error=True)
        except (json.JSONDecodeError, subprocess.SubprocessError) as e:
            log(f"Error inspecting container {container_id[:12]}: {e}", error=True)
        return None

    def _resolve_uid_to_username(self, uid: int) -> str | None:
        """Resolve UID to username, handling domain users."""
        # Try local passwd first
        try:
            pw = pwd.getpwuid(uid)
            return pw.pw_name
        except KeyError:
            pass

        # Try getent for LDAP/SSSD users
        try:
            result = subprocess.run(
                ["getent", "passwd", str(uid)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.split(":")[0]
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        return None

    def _resolve_username_to_uid(self, username: str) -> int | None:
        """Resolve username to UID, handling domain users."""
        try:
            pw = pwd.getpwnam(username)
            return pw.pw_uid
        except KeyError:
            pass

        # Try getent for LDAP/SSSD users
        try:
            result = subprocess.run(
                ["getent", "passwd", username],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                parts = result.stdout.split(":")
                if len(parts) >= 3:
                    return int(parts[2])
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError):
            pass

        return None

    def _validate_path_ownership(self, path: str, claimed_uid: int) -> bool:
        """
        Validate that a path is owned by the claimed user.

        Prevents mount path spoofing where user A mounts /home/userB/... to
        appear as userB. We verify the mount source is actually owned by the
        claimed user.
        """
        try:
            # Get the mount source (before the colon in bind mounts)
            mount_source = path.split(":")[0] if ":" in path else path

            # Check ownership of the path or its closest existing parent
            check_path = Path(mount_source)
            while not check_path.exists() and check_path != check_path.parent:
                check_path = check_path.parent

            if check_path.exists():
                actual_uid = check_path.stat().st_uid
                return actual_uid == claimed_uid

        except (OSError, ValueError):
            pass

        # If we can't validate, reject the ownership claim
        return False

    def _detect_owner(
        self, container_data: dict[str, Any]
    ) -> tuple[str | None, int | None, str]:
        """
        Detect container owner using multiple strategies.

        Returns: (username, uid, detection_method)
        """
        labels = container_data.get("Config", {}).get("Labels", {}) or {}
        name = container_data.get("Name", "").lstrip("/")

        # Strategy 1: ds01.user label (highest priority)
        if labels.get("ds01.user"):
            username = labels["ds01.user"]
            uid = self._resolve_username_to_uid(username)
            return username, uid, "ds01_label"

        # Strategy 2: aime.mlc.USER label
        if labels.get("aime.mlc.USER"):
            username = labels["aime.mlc.USER"]
            uid = self._resolve_username_to_uid(username)
            return username, uid, "aime_label"

        # Strategy 3: Container name pattern (name._.uid)
        if "._." in name:
            try:
                uid_str = name.split("._.")[-1]
                uid = int(uid_str)
                username = self._resolve_uid_to_username(uid)
                if username:
                    return username, uid, "container_name"
            except (ValueError, IndexError):
                pass

        # Strategy 4: devcontainer.local_folder label
        local_folder = labels.get("devcontainer.local_folder", "")
        if local_folder.startswith("/home/"):
            parts = local_folder.split("/")
            if len(parts) >= 3:
                username = parts[2]
                uid = self._resolve_username_to_uid(username)
                if uid is not None:  # Validate it's a real user
                    return username, uid, "devcontainer"

        # Strategy 5: Bind mount paths (with ownership validation)
        mounts = container_data.get("HostConfig", {}).get("Binds", []) or []
        for mount in mounts:
            if isinstance(mount, str) and mount.startswith("/home/"):
                # Extract username from /home/{user}/...
                parts = mount.split("/")
                if len(parts) >= 3:
                    username = parts[2]
                    uid = self._resolve_username_to_uid(username)
                    # Validate user exists AND actually owns the mount path
                    if uid is not None and self._validate_path_ownership(mount, uid):
                        return username, uid, "mount_path"

        # Strategy 6: Docker Compose working_dir label
        working_dir = labels.get("com.docker.compose.project.working_dir", "")
        if working_dir.startswith("/home/"):
            parts = working_dir.split("/")
            if len(parts) >= 3:
                username = parts[2]
                uid = self._resolve_username_to_uid(username)
                if uid is not None:
                    return username, uid, "compose_dir"

        return None, None, "unknown"

    def _detect_interface(self, container_data: dict[str, Any]) -> str:
        """Detect which interface/tool created the container."""
        labels = container_data.get("Config", {}).get("Labels", {}) or {}
        name = container_data.get("Name", "").lstrip("/")

        # Explicit interface label
        if labels.get("ds01.interface"):
            return labels["ds01.interface"]

        # DS01 managed containers
        if labels.get("ds01.managed") == "true":
            return "atomic"
        if labels.get("aime.mlc.DS01_MANAGED") == "true":
            return "atomic"

        # AIME naming convention
        if "._." in name:
            return "atomic"

        # Docker Compose
        if labels.get("com.docker.compose.project"):
            return "compose"

        # VS Code devcontainers
        if any(k.startswith("devcontainer.") for k in labels):
            return "devcontainer"
        if name.startswith("vsc-"):
            return "devcontainer"

        return "docker"

    def handle_create(self, container_id: str) -> None:
        """Handle container create event."""
        container_data = self._inspect_container(container_id)
        if not container_data:
            log(f"Could not inspect container {container_id[:12]}", error=True)
            return

        name = container_data.get("Name", "").lstrip("/")
        full_id = container_data.get("Id", container_id)
        short_id = full_id[:12]

        username, uid, method = self._detect_owner(container_data)
        interface = self._detect_interface(container_data)

        labels = container_data.get("Config", {}).get("Labels", {}) or {}
        ds01_managed = (
            labels.get("ds01.managed") == "true"
            or labels.get("aime.mlc.DS01_MANAGED") == "true"
        )

        entry = {
            "owner": username,
            "owner_uid": uid,
            "name": name,
            "ds01_managed": ds01_managed,
            "interface": interface,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "detection_method": method,
        }

        # Store by multiple keys for flexible lookup
        self.owners["containers"][short_id] = entry
        self.owners["containers"][full_id] = entry
        if name:
            self.owners["containers"][name] = entry

        self._save()

        owner_str = username if username else "(unknown)"
        log(f"Tracked: {name} owner={owner_str} interface={interface} method={method}")

    def handle_destroy(self, container_id: str, container_name: str = "") -> None:
        """Handle container destroy event."""
        containers = self.owners.get("containers", {})

        # Find all keys to remove for this container
        keys_to_remove = [container_id, container_id[:12]]
        if container_name:
            keys_to_remove.append(container_name)

        # Also find entries by full_id prefix
        for key in list(containers.keys()):
            if key.startswith(container_id[:12]):
                keys_to_remove.append(key)

        removed_any = False
        for key in set(keys_to_remove):  # dedupe
            if containers.pop(key, None) is not None:
                removed_any = True

        if removed_any:
            self._save()
            display_name = container_name if container_name else container_id[:12]
            log(f"Removed: {display_name}")

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        log(f"Received signal {signum}, shutting down...")
        self._running = False

    def _startup_catchup(self) -> None:
        """
        Scan all existing containers on startup.

        Ensures we track containers that were created while the daemon was down.
        Only processes containers not already in our ownership data.
        """
        log("Running startup catch-up scan...")
        try:
            result = subprocess.run(
                [DOCKER_BIN, "ps", "-a", "--format", "{{.ID}}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                log(f"Warning: Could not list containers for catch-up: {result.stderr}", error=True)
                return

            container_ids = [cid.strip() for cid in result.stdout.strip().split("\n") if cid.strip()]
            existing_keys = set(self.owners.get("containers", {}).keys())

            new_count = 0
            for container_id in container_ids:
                short_id = container_id[:12]
                # Skip if we already have this container
                if short_id in existing_keys or container_id in existing_keys:
                    continue

                self.handle_create(container_id)
                new_count += 1

            log(f"Catch-up complete: {new_count} new containers tracked, {len(container_ids)} total")

        except subprocess.TimeoutExpired:
            log("Warning: Timeout during startup catch-up", error=True)
        except Exception as e:
            log(f"Warning: Error during startup catch-up: {e}", error=True)

    def run(self) -> None:
        """Main event loop - listen to Docker events."""
        log("Starting Container Owner Tracker")
        log(f"Output file: {OUTPUT_FILE}")

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Catch up on any containers created while daemon was down
        self._startup_catchup()

        # Docker events command
        cmd = [
            DOCKER_BIN,
            "events",
            "--format",
            "{{json .}}",
            "--filter",
            "type=container",
            "--filter",
            "event=create",
            "--filter",
            "event=destroy",
        ]

        while self._running:
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                log("Connected to Docker events stream")

                for line in process.stdout:
                    if not self._running:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                        action = event.get("Action", "")
                        actor = event.get("Actor", {})
                        container_id = actor.get("ID", "")
                        container_name = actor.get("Attributes", {}).get("name", "")

                        if action == "create":
                            self.handle_create(container_id)
                        elif action == "destroy":
                            self.handle_destroy(container_id, container_name)

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        log(f"Error processing event: {e}", error=True)

                process.terminate()
                process.wait(timeout=5)

            except Exception as e:
                log(f"Event stream error: {e}, reconnecting...", error=True)
                if self._running:
                    import time

                    time.sleep(2)

        log("Container Owner Tracker stopped")


def main() -> None:
    """Entry point."""
    tracker = ContainerOwnerTracker()
    tracker.run()


if __name__ == "__main__":
    main()
