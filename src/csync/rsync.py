"""
Rsync wrapper module for csync.
Provides functionality to sync files between local and remote machines using rsync.
"""

import subprocess
import sys
import os
from typing import List

from .config import CsyncConfig


class RsyncWrapper:
    """A wrapper class for rsync operations."""

    def __init__(self, config: CsyncConfig):
        """
        Initialize the RsyncWrapper with a configuration.

        Args:
            config: CsyncConfig instance with sync settings
        """
        self.config = config

    def _build_rsync_command(
        self, source: str, destination: str, dry_run: bool = False
    ) -> List[str]:
        """
        Build the rsync command with appropriate options.

        Args:
            source: Source path
            destination: Destination path
            dry_run: If True, add --dry-run flag

        Returns:
            List of command arguments for subprocess
        """
        cmd = ["rsync"] + (
            self.config.rsync_options.copy() if self.config.rsync_options else []
        )

        if dry_run:
            cmd.append("--dry-run")

        # Add exclude patterns
        if self.config.exclude_patterns:
            for pattern in self.config.exclude_patterns:
                cmd.extend(["--exclude", pattern])

        # Add SSH options if specified
        if self.config.ssh_port:
            cmd.extend(["-e", f"ssh -p {self.config.ssh_port}"])

        cmd.extend([source, destination])
        return cmd

    def push(self, dry_run: bool = False, verbose: bool = True) -> bool:
        """
        Push (sync) local files to remote.

        Args:
            dry_run: If True, perform a dry run without actually copying files
            verbose: If True, print the command being executed

        Returns:
            True if sync was successful, False otherwise
        """
        source = self.config.local_path
        destination = self.config.remote_target

        cmd = self._build_rsync_command(source, destination, dry_run)

        if verbose:
            print(f"Executing: {' '.join(cmd)}")

        try:
            subprocess.run(cmd, check=True, capture_output=False)
            if verbose:
                print("✅ Push completed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Push failed with exit code {e.returncode}", file=sys.stderr)
            return False
        except FileNotFoundError:
            print("❌ rsync command not found. Please install rsync.", file=sys.stderr)
            return False

    def pull(self, dry_run: bool = False, verbose: bool = True) -> bool:
        """
        Pull (sync) remote files to local.

        Args:
            dry_run: If True, perform a dry run without actually copying files
            verbose: If True, print the command being executed

        Returns:
            True if sync was successful, False otherwise
        """
        source = self.config.remote_target
        destination = self.config.local_path

        # Ensure destination directory exists
        os.makedirs(destination, exist_ok=True)

        cmd = self._build_rsync_command(source, destination, dry_run)

        if verbose:
            print(f"Executing: {' '.join(cmd)}")

        try:
            subprocess.run(cmd, check=True, capture_output=False)
            if verbose:
                print("✅ Pull completed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Pull failed with exit code {e.returncode}", file=sys.stderr)
            return False
        except FileNotFoundError:
            print("❌ rsync command not found. Please install rsync.", file=sys.stderr)
            return False

    def status(self) -> None:
        """
        Show the current configuration status.
        """
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()

        # Create a table for configuration details
        table = Table(
            title="📋 csync Configuration", show_header=True, header_style="bold blue"
        )
        table.add_column("Setting", style="cyan", width=15)
        table.add_column("Value", style="white")

        table.add_row("Local path", self.config.local_path)
        table.add_row("Remote", self.config.remote_target)
        table.add_row(
            "Options",
            " ".join(self.config.rsync_options)
            if self.config.rsync_options
            else "None",
        )
        table.add_row(
            "Excludes",
            f"{len(self.config.exclude_patterns) if self.config.exclude_patterns else 0} patterns",
        )
        table.add_row(
            "Respect .gitignore",
            "Yes" if getattr(self.config, "respect_gitignore", True) else "No",
        )

        # Check if local path exists
        if os.path.exists(self.config.local_path):
            table.add_row("Local status", "✅ Path exists")
        else:
            table.add_row("Local status", "❌ Path does not exist")

        console.print(table)

        # Show exclude patterns if there are any
        if self.config.exclude_patterns:
            exclude_panel = Panel(
                "\n".join(
                    f"• {pattern}" for pattern in self.config.exclude_patterns[:10]
                ),
                title="🚫 Exclude Patterns"
                + (
                    " (showing first 10)"
                    if len(self.config.exclude_patterns) > 10
                    else ""
                ),
                border_style="yellow",
            )
            console.print(exclude_panel)

    def dry_run_push(self) -> bool:
        """Perform a dry run push to see what would be synced."""
        print("🔍 Dry run - showing what would be pushed:")
        return self.push(dry_run=True)

    def dry_run_pull(self) -> bool:
        """Perform a dry run pull to see what would be synced."""
        print("🔍 Dry run - showing what would be pulled:")
        return self.pull(dry_run=True)
