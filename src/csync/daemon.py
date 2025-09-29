"""
Daemon module for csync.
Implements background file watching and automatic synchronization.
"""

import fnmatch
import os
import sys
import time
import threading
from os import PathLike
from pathlib import Path
from typing import Optional, Set, Union

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from rich.console import Console

from .config import CsyncConfig
from .rsync import RsyncWrapper
from .process_manager import DaemonInfo, ProcessManager

RawPath = Union[str, bytes, PathLike[str]]


class CsyncFileHandler(FileSystemEventHandler):
    """File system event handler for csync daemon."""

    def __init__(self, daemon: "CsyncDaemon"):
        self.daemon = daemon
        self.console = daemon.console

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event."""
        if event.is_directory:
            return

        src_path = os.fsdecode(event.src_path)
        normalized_path = self.daemon._coerce_path(src_path)

        # Skip excluded files
        if self.daemon.should_exclude_file(normalized_path):
            return

        # Add to pending changes
        self.daemon.add_pending_change(normalized_path)

        # Log the event
        event_type = event.event_type
        rel_path = self.daemon._relative_path(normalized_path)
        self.console.print(f"📝 {event_type}: {rel_path}", style="dim")


class CsyncDaemon:
    """Background daemon for automatic file synchronization."""

    def __init__(self, config: CsyncConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.rsync_wrapper = RsyncWrapper(config)
        self.process_manager = ProcessManager(console)
        self.local_path = Path(self.config.local_path).resolve()

        # Daemon state
        self.observer = Observer()
        self.is_running = False
        self.pending_changes: Set[Path] = set()
        self.last_sync_time = 0.0
        self.sync_count = 0
        self.sync_lock = threading.Lock()

        # Configuration
        self.sync_delay = 5.0  # Wait 5 seconds after last change before syncing
        self.max_sync_interval = 300.0  # Force sync every 5 minutes
        self.batch_size = 100  # Max files to sync in one batch

        # Generate daemon signature
        self.signature = self.process_manager.generate_signature(str(self.local_path))

    def _coerce_path(self, file_path: RawPath) -> Path:
        """Normalize incoming raw paths to absolute Path objects."""
        if isinstance(file_path, Path):
            path = file_path
        else:
            decoded = os.fsdecode(file_path)
            path = Path(decoded)
        if not path.is_absolute():
            path = (self.local_path / path).resolve()
        else:
            path = path.resolve()
        return path

    def _relative_path(self, path: Path) -> str:
        """Return a forward-slash relative path to the daemon root."""
        try:
            return path.relative_to(self.local_path).as_posix()
        except ValueError:
            return os.path.relpath(str(path), str(self.local_path)).replace(os.sep, "/")

    def should_exclude_file(self, file_path: RawPath) -> bool:
        """Check if a file should be excluded from sync."""
        path = self._coerce_path(file_path)
        rel_path = self._relative_path(path)

        if not self.config.exclude_patterns:
            return False

        for pattern in self.config.exclude_patterns:
            # Simple pattern matching
            normalized_pattern = pattern.replace("\\", "/")

            if normalized_pattern.endswith("/"):
                # Directory pattern
                if rel_path.startswith(normalized_pattern.rstrip("/")):
                    return True
            elif "*" in normalized_pattern:
                # Wildcard pattern
                if fnmatch.fnmatch(rel_path, normalized_pattern) or fnmatch.fnmatch(
                    path.name, normalized_pattern
                ):
                    return True
            else:
                # Exact match
                if rel_path == normalized_pattern or path.name == normalized_pattern:
                    return True

        return False

    def add_pending_change(self, file_path: RawPath) -> None:
        """Add a file to pending changes."""
        path = self._coerce_path(file_path)
        with self.sync_lock:
            self.pending_changes.add(path)

    def get_pending_changes(self) -> Set[Path]:
        """Get and clear pending changes."""
        with self.sync_lock:
            changes = self.pending_changes.copy()
            self.pending_changes.clear()
            return changes

    def should_sync_now(self) -> bool:
        """Determine if we should sync now based on timing and changes."""
        current_time = time.time()

        # Force sync if max interval exceeded
        if current_time - self.last_sync_time > self.max_sync_interval:
            return True

        # Sync if we have pending changes and delay has passed
        if (
            self.pending_changes
            and current_time - self.last_sync_time > self.sync_delay
        ):
            return True

        return False

    def perform_sync(self) -> bool:
        """Perform synchronization."""
        try:
            # Get pending changes
            changes = self.get_pending_changes()

            if changes:
                change_count = len(changes)
                display_changes = sorted(changes, key=lambda p: p.as_posix())
                self.console.print(
                    f"🔄 Syncing {change_count} changes...", style="blue"
                )

                # Show some of the changed files
                if change_count <= 5:
                    for change in display_changes[:5]:
                        rel_path = self._relative_path(change)
                        self.console.print(f"  • {rel_path}", style="dim")
                else:
                    shown_changes = display_changes[:3]
                    for change in shown_changes:
                        rel_path = self._relative_path(change)
                        self.console.print(f"  • {rel_path}", style="dim")
                    self.console.print(
                        f"  ... and {change_count - 3} more files", style="dim"
                    )
            else:
                self.console.print("🔄 Performing scheduled sync...", style="blue")

            # Perform the actual sync
            success = self.rsync_wrapper.push(dry_run=False, verbose=False)

            if success:
                self.sync_count += 1
                self.last_sync_time = time.time()

                # Update daemon stats
                self.process_manager.update_daemon_stats(
                    str(self.local_path), self.last_sync_time, self.sync_count
                )

                self.console.print("✅ Sync completed successfully", style="green")
            else:
                self.console.print("❌ Sync failed", style="red")

            return success

        except Exception as e:
            self.console.print(f"❌ Sync error: {e}", style="red")
            return False

    def sync_loop(self) -> None:
        """Main sync loop running in background thread."""
        while self.is_running:
            try:
                if self.should_sync_now():
                    self.perform_sync()

                # Sleep for a short interval
                time.sleep(1.0)

            except Exception as e:
                self.console.print(f"❌ Daemon error: {e}", style="red")
                time.sleep(5.0)  # Wait longer on error

    def start(self, detach: bool = True) -> bool:
        """
        Start the daemon.

        Args:
            detach: If True, run as background daemon

        Returns:
            True if started successfully
        """
        # Check if already running
        existing = self.process_manager.get_daemon_by_path(str(self.local_path))
        if existing:
            self.console.print(
                f"❌ Daemon already running for {self.local_path} (PID: {existing.pid})",
                style="red",
            )
            return False

        # Setup file watching
        event_handler = CsyncFileHandler(self)
        self.observer.schedule(event_handler, str(self.local_path), recursive=True)

        # Create daemon info
        daemon_info = DaemonInfo(
            pid=os.getpid(),
            local_path=str(self.local_path),
            remote_target=self.config.remote_target,
            config_file=getattr(self.config, "_config_file", ".csync.cfg"),
            signature=self.signature,
            started_at=time.time(),
            sync_count=0,
        )

        if detach:
            # Fork to background
            try:
                pid = os.fork()
                if pid > 0:
                    # Parent process
                    daemon_info.pid = pid
                    self.process_manager.start_daemon(daemon_info)
                    return True

                # Child process continues as daemon
                os.setsid()  # Create new session

                # Update PID in daemon info
                daemon_info.pid = os.getpid()

            except OSError as e:
                self.console.print(f"❌ Failed to fork daemon: {e}", style="red")
                return False

        # Register daemon
        if not detach or not self.process_manager.start_daemon(daemon_info):
            # If not detaching or registration failed, just print status
            if not detach:
                self.console.print(
                    f"🚀 Starting daemon for {self.local_path} (PID: {os.getpid()})",
                    style="green",
                )

        # Set up signal handlers
        self.process_manager.setup_signal_handlers(self.signature)

        # Start file observer
        self.observer.start()
        self.is_running = True

        # Start sync thread
        sync_thread = threading.Thread(target=self.sync_loop, daemon=True)
        sync_thread.start()

        self.console.print(
            f"👀 Watching for changes in {self.local_path}", style="cyan"
        )
        self.console.print(f"🎯 Syncing to {self.config.remote_target}", style="cyan")

        # Perform initial sync
        self.console.print("🔄 Performing initial sync...", style="blue")
        self.perform_sync()

        if detach:
            # Redirect output for daemon
            sys.stdout.close()
            sys.stderr.close()

            # Keep daemon running
            try:
                while self.is_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            # Keep running until interrupted
            try:
                while self.is_running:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                self.console.print("\n🛑 Stopping daemon...", style="yellow")

        self.stop()
        return True

    def stop(self) -> None:
        """Stop the daemon."""
        self.is_running = False

        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()

        # Clean up daemon files
        self.process_manager.cleanup_daemon_files(self.signature)

        self.console.print("✅ Daemon stopped", style="green")


def start_daemon(
    config: CsyncConfig, console: Optional[Console] = None, detach: bool = True
) -> bool:
    """
    Start a csync daemon for the given configuration.

    Args:
        config: CsyncConfig instance
        console: Rich console for output
        detach: Whether to run as background daemon

    Returns:
        True if started successfully
    """
    daemon = CsyncDaemon(config, console)
    return daemon.start(detach)
