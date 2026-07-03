# Changelog

## 2.5.0 — 2026-07-03

### Changed
- x402 v2 payment requirements are read correctly: amount from the v2 `amount` field and resource from the top-level `resource` object, in addition to the v1 fields. The version is taken from `x402Version`, or inferred when absent; payloads whose version conflicts with their fields are rejected.
- The signed payment returned for a v2 request now uses the v2 `PAYMENT-SIGNATURE` shape — an `accepted` block (including `extra`) and a top-level `resource` — so resource servers can verify it. v1 requests keep the flat v1 shape.
- Payment skill examples updated to x402 v2 (v1 still supported).

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

## 2.3.0 — 2026-05-20

### Fixed
- Amount display now uses 6 decimals consistently (sub-cent payments no longer show as 0.00).
- Removed the redundant "$" prefix from amount displays.

## 2.2.2 — 2026-05-20

### Fixed
- Windows taskbar now shows the MultiClaw icon instead of the Python icon (pip install).

### Docs
- SKILL.md updated to v2-first format (CAIP-2 networks, `PAYMENT-SIGNATURE` header).

## 2.2.1 — 2026-05-19

### Fixed
- SKILL.md is now bundled in the pip package, so the `/agent` endpoint works for pip installs.

## 2.2.0 — 2026-04-21

### Added
- Market tab — browse and search x402 services from agentic.market in the GUI, with category filtering and copy-to-clipboard agent snippets.
- Service discovery in SKILL.md — agents can discover x402 services via the Agentic.Market API, with budget-aware filtering against their spend policy.
- MultiClaw Skills package — `npx skills add primer-systems/multiclaw-skills` installs setup, payment, and discovery skills.

### Docs
- Updated the system interactions diagram.

## 2.1.0 — 2026-04-02

### Added
- Published to PyPI — `pip install multiclaw` (or `multiclaw[gui]`).
- Restructured as a proper Python package (`src/multiclaw/`).
- Assets bundled with the pip install.

## 2.0.0 — 2026-03-31

### Added
- CLI mode with an interactive REPL and scriptable single commands.
- Headless daemon mode for server deployments.
- In-GUI console window (File → Console).
- Single-instance architecture: CLI connects to a running GUI via HTTP.

## 1.0.0 — 2026-02-19

### Added
- Initial release.
