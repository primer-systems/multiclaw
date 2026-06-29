# Changelog

## 2.4.1 — 2026-06-29

### Fixed
- Version display in Settings tab now shows correct version dynamically.

## 2.4.0 — 2026-06-28

### Added
- **View Instructions**: New feature to view agent credentials after initial creation. Access via "View Instructions" button in the Edit Agent dialog (GUI), `agent instructions <name>` command (CLI/Console), or double-click agent row context menu.
- **Regenerate Bearer Token**: For Bearer auth agents, you can regenerate the token if the original was lost. Use `--regenerate` flag in CLI or the "Regenerate Token" button in GUI.
- HMAC agent secrets can be retrieved at any time (decrypted from wallet).
- Bearer tokens cannot be recovered after creation, but can be regenerated.

## 2.3.1 — 2026-05-20

### Fixed
- **Data directory location**: pip-installed MultiClaw now stores wallet data in the platform-standard location (`%APPDATA%/MultiClaw` on Windows, `~/.local/share/MultiClaw` on Linux, `~/Library/Application Support/MultiClaw` on macOS) instead of inside the Python installation directory.
- **CLI/GUI state sharing**: CLI commands now correctly connect to a running GUI/daemon instance via the admin API. Previously, a broken import caused the CLI to always start a standalone instance, so commands like `multiclaw address balance` would report "Wallet must be unlocked" even when the GUI had it unlocked.

### Added
- `platformdirs` dependency for cross-platform data directory resolution.
