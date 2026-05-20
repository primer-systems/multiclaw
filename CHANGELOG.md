# Changelog

## 2.3.1 — 2026-05-20

### Fixed
- **Data directory location**: pip-installed MultiClaw now stores wallet data in the platform-standard location (`%APPDATA%/MultiClaw` on Windows, `~/.local/share/MultiClaw` on Linux, `~/Library/Application Support/MultiClaw` on macOS) instead of inside the Python installation directory.
- **CLI/GUI state sharing**: CLI commands now correctly connect to a running GUI/daemon instance via the admin API. Previously, a broken import caused the CLI to always start a standalone instance, so commands like `multiclaw address balance` would report "Wallet must be unlocked" even when the GUI had it unlocked.

### Added
- `platformdirs` dependency for cross-platform data directory resolution.
