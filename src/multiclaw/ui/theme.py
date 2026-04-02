"""
UI Theme - Design system colors and fonts.

Primer brand colors from the design system.
"""

from PyQt6.QtWidgets import QMessageBox


class Theme:
    """Primer brand colors from design system."""

    # Brand colors
    LIME = "#baea2a"
    LIME_DIM = "#7a9a1a"
    BLACK = "#09090b"          # Our black (not pure black)
    BLACK_LIGHT = "#121214"    # Elevated surfaces
    CHARCOAL = "#4A4543"       # Borders
    RUST = "#B7410E"
    WHITE = "#fafafa"

    # Status colors
    SUCCESS = "#22c55e"
    ERROR = "#ef4444"
    WARNING = "#f59e0b"

    # Help text colors
    PLACEHOLDER = "#22d3ee"  # Cyan - for <user_input> placeholders
    OPTIONAL = "#a78bfa"     # Purple - for [optional] parameters

    # Typography
    MONO_FONT = "JetBrains Mono"

    # Standard dialog sizes
    MIN_DIALOG_WIDTH = 350
    MIN_POPUP_WIDTH = 300


def ask_question(parent, title: str, message: str, default_no: bool = True) -> bool:
    """
    Show a question dialog with consistent sizing.
    Returns True if user clicked Yes, False otherwise.
    """
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(message)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    msg.setDefaultButton(
        QMessageBox.StandardButton.No if default_no else QMessageBox.StandardButton.Yes
    )
    msg.setMinimumWidth(Theme.MIN_POPUP_WIDTH)
    return msg.exec() == QMessageBox.StandardButton.Yes


def show_warning(parent, title: str, message: str) -> None:
    """Show a warning dialog with consistent sizing."""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(message)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.setMinimumWidth(Theme.MIN_POPUP_WIDTH)
    msg.exec()


def show_info(parent, title: str, message: str) -> None:
    """Show an info dialog with consistent sizing."""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(message)
    msg.setIcon(QMessageBox.Icon.Information)
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.setMinimumWidth(Theme.MIN_POPUP_WIDTH)
    msg.exec()
