"""
MultiClaw - x402 Agent Manifold

A standalone desktop app for authorizing AI agent payments via x402.

Entry point for the application.
"""

import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from ui import MainWindow
from utils import get_assets_dir
from services.logging import configure_logging


def main():
    """Application entry point."""
    # Configure logging before anything else
    configure_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("MultiClaw")
    app.setOrganizationName("Primer")

    # Set application icon
    icon_path = get_assets_dir() / "icon256.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Show main window
    window = MainWindow()
    window.show()

    # Initial activity message
    addresses = window.wallet_tab.get_wallet_list()
    if addresses:
        window.update_activity(f"Loaded {len(addresses)} address(es)")
    else:
        window.update_activity("Welcome to MultiClaw • Create a wallet to get started")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
