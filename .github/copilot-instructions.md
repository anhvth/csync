# csync Development Instructions

## Project Architecture

**csync** is a modern Python CLI tool that wraps rsync for bidirectional file synchronization. The architecture follows a clean modular pattern:

- **CLI Layer** (`src/csync/cli.py`) - Typer-based modern CLI with Rich formatting
- **Logic Layer** (`src/csync/rsync.py`) - Core rsync wrapper and operations
- **Config Layer** (`src/csync/config.py`) - Multi-format configuration handling
- **Daemon Layer** (`src/csync/daemon.py`) - Background file watching with inotify/watchdog
- **Analysis Layer** (`src/csync/analyzer.py`) - Smart project analysis for exclude patterns
- **Process Layer** (`src/csync/process_manager.py`) - PID management and daemon lifecycle

### Key Design Patterns

**Modern CLI with Typer + Rich**: All CLI commands use Typer's `@app.command()` decorator with type hints and Rich console for output. Follow the existing pattern in `cli.py`:

```python
@app.command()
def command_name(
    param: Annotated[Type, typer.Option("--flag", "-f", help="Description")] = default,
) -> None:
```

**Configuration Auto-Discovery**: Config files are discovered via `find_config_file()` which walks up directory tree looking for `.csync.cfg`, `.csync_config`, `.csync_config.json/yml`. Primary format is INI (.cfg), with JSON/YAML fallbacks.

**Dataclass-Based Config**: `CsyncConfig` uses `@dataclass` with `__post_init__()` for validation and default population. Always use the `from_file()` classmethod for loading.

**Daemon Process Management**: Daemons use signature-based identification from local path hash. PID files and JSON metadata stored in `~/.csync/daemons/`. Signal handlers for graceful shutdown.

## Development Workflow

**Package Management**: This project uses `uv` (not pip/poetry). Essential commands:

```bash
uv pip install -e .          # Install in editable mode
uv add package-name          # Add dependencies
uv pip list                  # List installed packages
```

**Testing CLI**: Install in editable mode, then test commands:

```bash
uv pip install -e .
csync init --smart           # Creates .csync.cfg with smart analysis
csync status                 # Shows Rich-formatted config table
csync start --foreground     # Start daemon in foreground for testing
csync daemon-status          # Show running daemons
csync stop                   # Stop daemon for current directory
```

**Rich Output Standards**: All user-facing output should use Rich formatting:

- Tables: `rich.table.Table` with specific styling (`title="📋 csync Configuration"`)
- Panels: `rich.panel.Panel` for config display and examples
- Console: Import and use the global `console = Console()` instance
- Colors: Use `style="red"` for errors, `style="green"` for success, `style="yellow"` for warnings

## Core Components

**Config Handling**: `CsyncConfig` supports 3 formats (.cfg preferred):

- `.csync.cfg` - INI format with `[csync]` section, comma-separated lists
- `.csync_config.json` - Standard JSON format
- `.csync_config.yml` - YAML format
- Auto .gitignore integration when `respect_gitignore=true`

**Rsync Wrapper**: `RsyncWrapper` builds rsync commands dynamically:

- SSH port handling via `-e "ssh -p {port}"`
- Exclude patterns via repeated `--exclude pattern` flags
- Directory trailing slash management for proper sync behavior
- Error handling for missing rsync binary

**Daemon Architecture**: Background file watching with automatic sync:

- `watchdog.Observer` for cross-platform file monitoring
- Threaded sync loop with configurable delays and batch processing
- Process signatures based on MD5 hash of local path for unique identification
- Signal handlers (SIGTERM/SIGINT) for graceful shutdown

**Smart Analysis**: Project structure analysis for intelligent exclude suggestions:

- Scans directory tree with configurable depth limits
- Identifies large files (>50MB) and directories (>1000 files or >500MB)
- Suggests exclusions based on known problematic patterns
- Rich progress display and statistics tables

**Command Pattern**: Each CLI command follows this pattern:

1. Load config via `find_and_load_config()`
2. Create appropriate wrapper/manager instance
3. Call methods with `dry_run` and `verbose` params
4. Handle success/failure with appropriate Rich output

## Project-Specific Conventions

**File Organization**: Source code in `src/csync/` with flat structure. Entry point is `csync.cli:main` defined in `pyproject.toml[project.scripts]`.

**Error Handling**: Use `typer.Exit(1)` for CLI errors, never `sys.exit()`. Rich console for user-facing error messages, stderr for system errors.

**Type Hints**: Extensive use of `typing.Annotated` for Typer parameters. All functions should have return type hints.

**Path Handling**: Always use `pathlib.Path` for file operations, `os.path.abspath()` for path normalization in config.

**Dependencies**: Core deps are typer (CLI), rich (output), pyyaml (config), watchdog (file watching), psutil (process management). Optional imports for extended functionality.

**Daemon Lifecycle**:

- Start: Fork to background, create PID file, setup signal handlers
- Run: File watcher + sync thread with configurable delays
- Stop: Signal handling, cleanup PID files, graceful shutdown

## Coding Standards

**Naming**

- snake_case for functions & variables
- PascalCase for classes

**Formatting**

- 4-space indentation
- Single quotes for strings (except docstrings use triple quotes)
- f-strings for interpolation
- Each line should be less than 88 characters
- Each file should be within 300 LOC

**Typing & Docs**

- Add type hints to all public functions & methods
- Keep docstrings minimal; comment only non-obvious logic
- Use `typing.Annotated` for Typer parameters
- Prefer clear, straightforward typing over complex generics

**Comparisons**

- Use `is` / `is not` when comparing with `None`
- Use `typer.Exit(1)` for CLI errors, never `sys.exit()`

## Tooling Assumptions

**Editor**: VS Code with Pylance

- Setting: `"python.analysis.typeCheckingMode": "basic"`
- Code must satisfy basic type checking (no strict-mode warnings)

**Preferred Libraries**

- CLI: `typer` + `rich` (already established)
- Config: `pyyaml` + `configparser` (already established)
- File watching: `watchdog` (already established)
- Process management: `psutil` (already established)
- Testing: `pytest` (when adding tests)

**Common Problems to Avoid**

- Don't use `parse_obj` - use `model_validate` for Pydantic v2
- Don't use `sys.exit()` in CLI code - use `typer.Exit(1)`
- Don't forget to handle optional dependencies with try/except ImportError
- Don't create files >300 LOC - split into multiple modules

## Integration Points

**External rsync Dependency**: Tool shells out to system `rsync` command. Handle `FileNotFoundError` gracefully with user-friendly message.

**SSH Integration**: Supports SSH via rsync's `-e` flag for custom ports. No direct SSH library usage.

**Gitignore Integration**: Reads `.gitignore` files in `_load_gitignore_patterns()` to auto-populate exclude patterns when `respect_gitignore=true`.

**File System**: Heavy reliance on file discovery (`find_config_file()`), path resolution, and directory creation (`os.makedirs()`).

**Process Management**: Uses `psutil` for cross-platform process handling, PID validation, and signal sending.

**File Watching**: Uses `watchdog` library for cross-platform file system monitoring with configurable exclusion patterns.

## Common Tasks

**Adding New Commands**:

1. Add `@app.command()` decorated function in `cli.py`
2. Follow existing parameter pattern with `Annotated` types
3. Use `find_and_load_config()` for config loading
4. Return Rich-formatted output

**Config Format Changes**: Modify `CsyncConfig.from_file()` and `to_file()` methods. Support backward compatibility with existing formats.

**Rsync Option Changes**: Update `_build_rsync_command()` in `RsyncWrapper`. Test with `--dry-run` extensively.

**Daemon Enhancements**: Modify `CsyncDaemon` class. Test with `--foreground` flag. Update signal handling in `ProcessManager`.

**Analysis Improvements**: Extend `SmartAnalyzer` patterns and thresholds. Update display methods for new metrics.
