"""
Smart analyzer module for csync.
Analyzes directory structure to suggest intelligent exclude patterns.
"""

import os
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.panel import Panel


@dataclass
class DirectoryStats:
    """Statistics about a directory."""

    path: str
    file_count: int
    total_size: int  # in bytes
    max_file_size: int
    avg_file_size: float
    extensions: Dict[str, int]  # extension -> count
    depth: int


@dataclass
class AnalysisResult:
    """Result of directory analysis."""

    suggested_excludes: List[str]
    large_files: List[Tuple[str, int]]  # (path, size_mb)
    large_directories: List[Tuple[str, int, int]]  # (path, file_count, size_mb)
    problematic_patterns: List[str]
    statistics: Dict[str, DirectoryStats]


class SmartAnalyzer:
    """Analyzes project structure to suggest smart exclude patterns."""

    # Configuration thresholds
    MAX_FILE_SIZE_MB = 50
    MAX_DIRECTORY_FILES = 1000
    MAX_DIRECTORY_SIZE_MB = 500

    # Known problematic patterns
    KNOWN_EXCLUDES = {
        # Build/compiled artifacts
        "build",
        "dist",
        "target",
        "out",
        "bin",
        "obj",
        # Dependencies/packages
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        # Virtual environments
        ".venv",
        "venv",
        ".env",
        "env",
        "ENV",
        # IDE/editor files
        ".vscode",
        ".idea",
        ".vs",
        "*.swp",
        "*.swo",
        "*~",
        # Version control
        ".git",
        ".svn",
        ".hg",
        ".bzr",
        # OS files
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        # Logs and temporary files
        "*.log",
        "*.tmp",
        "*.temp",
        ".cache",
        # Media files (usually large)
        "*.mp4",
        "*.avi",
        "*.mov",
        "*.mkv",
        "*.mp3",
        "*.wav",
        # Archives
        "*.zip",
        "*.tar.gz",
        "*.rar",
        "*.7z",
        # Database files
        "*.db",
        "*.sqlite",
        "*.sqlite3",
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def analyze_directory(self, root_path: str, max_depth: int = 3) -> AnalysisResult:
        """
        Analyze directory structure and suggest exclude patterns.

        Args:
            root_path: Root directory to analyze
            max_depth: Maximum directory depth to scan

        Returns:
            AnalysisResult with suggestions and statistics
        """
        root_path_obj = Path(root_path).resolve()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("🔍 Analyzing project structure...", total=None)

            # Scan directory structure
            stats = {}
            large_files = []
            large_directories = []
            problematic_patterns = set()

            for dirpath, dirnames, filenames in os.walk(root_path_obj):
                rel_path = os.path.relpath(dirpath, root_path_obj)
                depth = len(rel_path.split(os.sep)) if rel_path != "." else 0

                if depth > max_depth:
                    continue

                progress.update(task, description=f"🔍 Analyzing {rel_path}...")

                # Analyze current directory
                dir_stats = self._analyze_single_directory(dirpath, filenames)
                stats[rel_path] = dir_stats

                # Check for large files
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        size = os.path.getsize(filepath)
                        if size > self.MAX_FILE_SIZE_MB * 1024 * 1024:
                            rel_filepath = os.path.relpath(filepath, root_path_obj)
                            large_files.append((rel_filepath, size // (1024 * 1024)))
                    except (OSError, IOError):
                        continue

                # Check for large directories
                if (
                    dir_stats.file_count > self.MAX_DIRECTORY_FILES
                    or dir_stats.total_size > self.MAX_DIRECTORY_SIZE_MB * 1024 * 1024
                ):
                    size_mb = dir_stats.total_size // (1024 * 1024)
                    large_directories.append((rel_path, dir_stats.file_count, size_mb))

                # Check for known problematic patterns
                dir_name = os.path.basename(dirpath)
                if dir_name.lower() in [
                    p.lower().rstrip("*") for p in self.KNOWN_EXCLUDES
                ]:
                    if rel_path != ".":  # Don't exclude root
                        problematic_patterns.add(f"{rel_path}/")

        # Generate suggestions
        suggested_excludes = self._generate_suggestions(
            stats, large_files, large_directories, problematic_patterns
        )

        return AnalysisResult(
            suggested_excludes=list(suggested_excludes),
            large_files=large_files,
            large_directories=large_directories,
            problematic_patterns=list(problematic_patterns),
            statistics=stats,
        )

    def _analyze_single_directory(
        self, dirpath: str, filenames: List[str]
    ) -> DirectoryStats:
        """Analyze a single directory and return statistics."""
        total_size = 0
        max_file_size = 0
        extensions = defaultdict(int)

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                size = os.path.getsize(filepath)
                total_size += size
                max_file_size = max(max_file_size, size)

                # Track file extensions
                ext = Path(filename).suffix.lower()
                if ext:
                    extensions[ext] += 1
                else:
                    extensions["<no extension>"] += 1

            except (OSError, IOError):
                continue

        avg_file_size = total_size / len(filenames) if filenames else 0

        return DirectoryStats(
            path=dirpath,
            file_count=len(filenames),
            total_size=total_size,
            max_file_size=max_file_size,
            avg_file_size=avg_file_size,
            extensions=dict(extensions),
            depth=0,  # Will be set by caller
        )

    def _generate_suggestions(
        self,
        stats: Dict[str, DirectoryStats],
        large_files: List[Tuple[str, int]],
        large_directories: List[Tuple[str, int, int]],
        problematic_patterns: Set[str],
    ) -> Set[str]:
        """Generate smart exclude suggestions based on analysis."""
        suggestions = set()

        # Add known problematic patterns
        suggestions.update(problematic_patterns)

        # Add patterns for large directories
        for dir_path, file_count, size_mb in large_directories:
            if dir_path != ".":  # Don't exclude root
                suggestions.add(f"{dir_path}/")

        # Add patterns for file types that are commonly large
        for stats_entry in stats.values():
            for ext, count in stats_entry.extensions.items():
                if ext in [".mp4", ".avi", ".mov", ".zip", ".tar.gz", ".dmg", ".iso"]:
                    suggestions.add(f"*{ext}")

        # Add default exclusions
        suggestions.update(
            [
                ".git/",
                "__pycache__/",
                "*.pyc",
                "*.pyo",
                ".DS_Store",
                "*.log",
                ".venv/",
                "venv/",
                "node_modules/",
                ".pytest_cache/",
            ]
        )

        return suggestions

    def display_analysis(self, result: AnalysisResult) -> None:
        """Display analysis results in a formatted way."""

        # Display summary
        self.console.print("\n📊 [bold cyan]Project Analysis Summary[/bold cyan]")

        # Large files table
        if result.large_files:
            files_table = Table(title="🚨 Large Files (> 50MB)", show_header=True)
            files_table.add_column("File", style="yellow")
            files_table.add_column("Size (MB)", style="red", justify="right")

            for filepath, size_mb in sorted(
                result.large_files, key=lambda x: x[1], reverse=True
            )[:10]:
                files_table.add_row(filepath, str(size_mb))

            self.console.print(files_table)

        # Large directories table
        if result.large_directories:
            dirs_table = Table(title="📁 Large Directories", show_header=True)
            dirs_table.add_column("Directory", style="yellow")
            dirs_table.add_column("Files", style="blue", justify="right")
            dirs_table.add_column("Size (MB)", style="red", justify="right")

            for dir_path, file_count, size_mb in sorted(
                result.large_directories, key=lambda x: x[2], reverse=True
            )[:10]:
                dirs_table.add_row(dir_path, str(file_count), str(size_mb))

            self.console.print(dirs_table)

        # Suggested exclusions
        if result.suggested_excludes:
            excludes_text = "\n".join(
                f"• {pattern}" for pattern in sorted(result.suggested_excludes)
            )
            excludes_panel = Panel(
                excludes_text,
                title="🚫 Suggested Exclude Patterns",
                border_style="green",
            )
            self.console.print(excludes_panel)

        # Statistics summary
        total_dirs = len(result.statistics)
        total_files = sum(stats.file_count for stats in result.statistics.values())
        total_size_mb = sum(
            stats.total_size for stats in result.statistics.values()
        ) // (1024 * 1024)

        summary_table = Table(title="📈 Project Statistics", show_header=False)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Total directories scanned", str(total_dirs))
        summary_table.add_row("Total files found", str(total_files))
        summary_table.add_row("Total size", f"{total_size_mb} MB")
        summary_table.add_row("Large files detected", str(len(result.large_files)))
        summary_table.add_row(
            "Large directories detected", str(len(result.large_directories))
        )

        self.console.print(summary_table)


def analyze_project_smart(
    project_path: str, console: Optional[Console] = None
) -> AnalysisResult:
    """
    Convenience function to analyze a project and return smart exclude suggestions.

    Args:
        project_path: Path to project directory
        console: Rich console for output

    Returns:
        AnalysisResult with suggestions
    """
    analyzer = SmartAnalyzer(console)
    return analyzer.analyze_directory(project_path)
