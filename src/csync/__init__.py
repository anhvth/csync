"""
csync - A Python wrapper for rsync to sync code between local and remote machines.
"""

__version__ = "0.1.0"
__author__ = "csync"
__description__ = (
    "A Python wrapper for rsync to sync code between local and remote machines"
)

from .config import CsyncConfig
from .rsync import RsyncWrapper
from .cli import main

# Optional imports for extended functionality
try:
    from .analyzer import analyze_project_smart
    from .daemon import start_daemon
    from .process_manager import get_process_manager
    from .ui import configure_ui, run_ui

    __all__ = [
        "CsyncConfig",
        "RsyncWrapper",
        "main",
        "analyze_project_smart",
        "start_daemon",
        "get_process_manager",
        "configure_ui",
        "run_ui",
    ]
except ImportError:
    # Fallback if optional dependencies are not available
    __all__ = ["CsyncConfig", "RsyncWrapper", "main"]
