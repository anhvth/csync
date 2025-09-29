"""
Configuration module for csync.
Handles reading and parsing .csync.cfg files.
"""

import os
import json
import yaml
import configparser
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class CsyncConfig:
    """Configuration class for csync operations."""

    local_path: str
    remote_host: str
    remote_path: str
    ssh_user: Optional[str] = None
    ssh_port: Optional[int] = None
    exclude_patterns: Optional[List[str]] = None
    rsync_options: Optional[List[str]] = None
    respect_gitignore: bool = True

    def __post_init__(self):
        """Validate and normalize configuration after initialization."""
        # Ensure local_path is absolute
        self.local_path = os.path.abspath(os.path.expanduser(self.local_path))

        # Ensure local_path ends with /
        if not self.local_path.endswith("/"):
            self.local_path += "/"

        # Ensure remote_path ends with /
        if not self.remote_path.endswith("/"):
            self.remote_path += "/"

        # Set default rsync options if not provided
        if self.rsync_options is None:
            self.rsync_options = ["-av", "--progress"]

        # Set default exclude patterns if not provided
        if self.exclude_patterns is None:
            self.exclude_patterns = [
                ".git/",
                "__pycache__/",
                "*.pyc",
                ".DS_Store",
                "node_modules/",
                ".venv/",
                "venv/",
                ".pytest_cache/",
                "*.log",
            ]

        # Add gitignore patterns if respect_gitignore is True
        if self.respect_gitignore:
            gitignore_patterns = self._load_gitignore_patterns()
            if gitignore_patterns:
                # Avoid duplicates
                for pattern in gitignore_patterns:
                    if pattern not in self.exclude_patterns:
                        self.exclude_patterns.append(pattern)

    def _load_gitignore_patterns(self) -> List[str]:
        """Load patterns from .gitignore file if it exists."""
        gitignore_path = Path(self.local_path) / ".gitignore"
        if not gitignore_path.exists():
            return []

        patterns = []
        try:
            with open(gitignore_path, "r") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception:
            # If we can't read gitignore, just continue
            pass

        return patterns

    @property
    def remote_target(self) -> str:
        """Get the full remote target string for rsync."""
        if self.ssh_user:
            return f"{self.ssh_user}@{self.remote_host}:{self.remote_path}"
        return f"{self.remote_host}:{self.remote_path}"

    @classmethod
    def from_file(cls, config_path: str = ".csync.cfg") -> "CsyncConfig":
        """Load configuration from a file."""
        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        # Determine file format based on extension
        content = config_file.read_text()

        if config_path.endswith((".yml", ".yaml")):
            config_data = yaml.safe_load(content)
        elif config_path.endswith(".json"):
            config_data = json.loads(content)
        elif config_path.endswith(".cfg") or config_path.endswith(".ini"):
            # Parse INI/CFG format
            config = configparser.ConfigParser()
            config.read(config_path)

            config_data = {}
            if "csync" in config:
                section = config["csync"]
                config_data = {
                    "local_path": section.get("local_path", "."),
                    "remote_host": section.get("remote_host"),
                    "remote_path": section.get("remote_path"),
                    "ssh_user": section.get("ssh_user"),
                    "ssh_port": section.getint("ssh_port")
                    if section.get("ssh_port")
                    else None,
                    "respect_gitignore": section.getboolean("respect_gitignore", True),
                }

                # Parse lists from comma-separated strings
                exclude_patterns_str = section.get("exclude_patterns")
                if exclude_patterns_str:
                    config_data["exclude_patterns"] = [
                        p.strip() for p in exclude_patterns_str.split(",")
                    ]

                rsync_options_str = section.get("rsync_options")
                if rsync_options_str:
                    config_data["rsync_options"] = [
                        o.strip() for o in rsync_options_str.split(",")
                    ]
            else:
                raise ValueError(
                    f"No [csync] section found in config file {config_path}"
                )
        else:
            # Try to parse as JSON first, then YAML
            try:
                config_data = json.loads(content)
            except json.JSONDecodeError:
                try:
                    config_data = yaml.safe_load(content)
                except yaml.YAMLError as e:
                    raise ValueError(f"Unable to parse config file {config_path}: {e}")

        # Remove None values
        config_data = {k: v for k, v in config_data.items() if v is not None}
        return cls(**config_data)

    def to_file(self, config_path: str = ".csync.cfg") -> str:
        """Save configuration to a file and return the content."""
        config_data = {
            "local_path": self.local_path,
            "remote_host": self.remote_host,
            "remote_path": self.remote_path,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
            "exclude_patterns": self.exclude_patterns,
            "rsync_options": self.rsync_options,
            "respect_gitignore": self.respect_gitignore,
        }

        # Remove None values
        config_data = {k: v for k, v in config_data.items() if v is not None}

        config_file = Path(config_path)

        if config_path.endswith((".yml", ".yaml")):
            content = yaml.dump(config_data, default_flow_style=False)
            with open(config_file, "w") as f:
                f.write(content)
        elif config_path.endswith(".json"):
            content = json.dumps(config_data, indent=2)
            with open(config_file, "w") as f:
                f.write(content)
        elif config_path.endswith(".cfg") or config_path.endswith(".ini"):
            # Write as INI/CFG format
            config = configparser.ConfigParser()
            config.add_section("csync")

            for key, value in config_data.items():
                if isinstance(value, list):
                    # Convert list to comma-separated string
                    config.set("csync", key, ", ".join(value))
                elif isinstance(value, bool):
                    config.set("csync", key, str(value).lower())
                elif value is not None:
                    config.set("csync", key, str(value))

            with open(config_file, "w") as f:
                config.write(f)

            # Read back the content for display
            content = config_file.read_text()
        else:
            # Default to JSON
            content = json.dumps(config_data, indent=2)
            with open(config_file, "w") as f:
                f.write(content)

        return content


def create_gitignore_if_needed(project_dir: str = ".") -> bool:
    """
    Create a .gitignore file if it doesn't exist.

    Args:
        project_dir: Directory to create .gitignore in

    Returns:
        True if .gitignore was created, False if it already existed
    """
    gitignore_path = Path(project_dir) / ".gitignore"

    if gitignore_path.exists():
        return False

    # Create a basic .gitignore
    gitignore_content = """# csync config files
.csync.cfg

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Logs
*.log
"""

    with open(gitignore_path, "w") as f:
        f.write(gitignore_content)

    return True


def find_config_file(start_path: str = ".") -> Optional[str]:
    """
    Find .csync.cfg file by walking up the directory tree.

    Args:
        start_path: Directory to start searching from

    Returns:
        Path to config file if found, None otherwise
    """
    current_path = Path(start_path).resolve()
    config_names = [
        ".csync.cfg",
        ".csync_config",
        ".csync_config.json",
        ".csync_config.yml",
        ".csync_config.yaml",
    ]

    while current_path != current_path.parent:  # Not at filesystem root
        for config_name in config_names:
            config_file = current_path / config_name
            if config_file.exists():
                return str(config_file)
        current_path = current_path.parent

    return None
