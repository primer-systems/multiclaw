"""
Shared utility functions for MultiClaw.

Contains path helpers and common utilities used across packages.
"""

import sys
from pathlib import Path


# ============================================
# Name Validation
# ============================================

class NameValidationError(ValueError):
    """Raised when a name fails validation."""
    pass


def validate_name(name: str, field: str = "Name") -> str:
    """
    Validate a display name for agents, policies, or addresses.

    Names must:
    - Be non-empty (after stripping whitespace)
    - Contain only printable ASCII characters (codes 32-126)
    - Be 100 characters or less

    Args:
        name: The name to validate
        field: Field name for error messages (e.g., "Policy name", "Agent name")

    Returns:
        The validated name (stripped of leading/trailing whitespace)

    Raises:
        NameValidationError: If name is invalid
    """
    if not name:
        raise NameValidationError(f"{field} cannot be empty")

    name = name.strip()

    if not name:
        raise NameValidationError(f"{field} cannot be empty or whitespace only")

    if len(name) > 100:
        raise NameValidationError(f"{field} must be 100 characters or less")

    invalid = [c for c in name if not (32 <= ord(c) <= 126)]
    if invalid:
        raise NameValidationError(
            f"{field} contains invalid characters. Only printable ASCII is allowed."
        )

    return name


def get_app_dir() -> Path:
    """Get the application data directory."""
    if getattr(sys, 'frozen', False):
        # Running as compiled
        app_dir = Path(sys.executable).parent / "data"
    else:
        # Running as script
        app_dir = Path(__file__).parent.parent / "data"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_wallet_dir() -> Path:
    """Get the wallet storage directory."""
    return get_app_dir() / "wallets"


def get_default_wallet_path() -> Path:
    """Get path to default wallet file."""
    return get_wallet_dir() / "default.json"


def get_assets_dir() -> Path:
    """Get the assets directory."""
    if getattr(sys, 'frozen', False):
        # PyInstaller onefile mode extracts to temp dir
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS) / "assets"
        # Onedir mode - assets next to exe
        return Path(sys.executable).parent / "assets"
    else:
        return Path(__file__).parent.parent / "assets"


def get_settings_path() -> Path:
    """Get path to settings file."""
    return get_app_dir() / "settings.json"


def get_logs_dir() -> Path:
    """Get the logs directory."""
    logs_dir = get_app_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir
