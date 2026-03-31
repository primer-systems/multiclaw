"""
Console Window - Terminal-style interface for MultiClaw.

Provides command-line access to all MultiClaw functions within the GUI.
"""

import html as _html
from typing import Callable, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QHBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QKeyEvent

from .theme import Theme
from commands import CommandHandler, CommandResult

if TYPE_CHECKING:
    from core import MultiClaw


# ASCII art banner
CONSOLE_BANNER = (
    f'<pre style="font-family: Consolas, monospace; font-size: 12px; line-height: 1.1; margin: 8px;">'
    '<br>'
    f'<span style="color: {Theme.LIME};">█▀▄▀█ █ █ █   ▀█▀ █</span><span style="color: #E94435;"> █▀▀ █   ▄▀█ █ █ █</span><br>'
    f'<span style="color: {Theme.LIME};">█ ▀ █ █▄█ █▄▄  █  █</span><span style="color: #E94435;"> █▄▄ █▄▄ █▀█ ▀▄▀▄▀</span><br>'
    '</pre>'
    f'<span style="color: #888888;">Console</span><br>'
    f'<span style="color: {Theme.CHARCOAL};">═══════════════════════════════════════</span><br>'
    f'<span style="color: #888888;">Type </span><span style="color: {Theme.LIME};">help</span>'
    f'<span style="color: #888888;"> for available commands</span><br>'
    f'<span style="color: {Theme.CHARCOAL};">═══════════════════════════════════════</span><br><br>'
)


class PromptLabel(QLabel):
    """Fixed prompt label that appears before the input."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont(Theme.MONO_FONT, 11))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.CHARCOAL};
                color: {Theme.LIME};
                border: none;
                padding: 8px 0px 8px 12px;
            }}
        """)


class CommandInput(QLineEdit):
    """Custom input that handles command history and password mode."""

    def __init__(self, on_submit: Callable[[str], None], parent=None):
        super().__init__(parent)
        self._on_submit = on_submit
        self._history: list[str] = []
        self._history_index = -1
        self._current_input = ""
        self._password_mode = False

        self.setFont(QFont(Theme.MONO_FONT, 11))
        self._apply_normal_style()
        self.returnPressed.connect(self._submit)

    def _apply_normal_style(self):
        """Apply normal input styling."""
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.CHARCOAL};
                color: {Theme.LIME};
                border: none;
                border-top: 1px solid {Theme.CHARCOAL};
                padding: 8px 12px 8px 4px;
                selection-background-color: {Theme.LIME_DIM};
            }}
        """)
        self.setEchoMode(QLineEdit.EchoMode.Normal)
        self.setPlaceholderText("")

    def _apply_password_style(self):
        """Apply password input styling."""
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.CHARCOAL};
                color: {Theme.RUST};
                border: none;
                border-top: 1px solid {Theme.RUST};
                padding: 8px 12px 8px 4px;
                selection-background-color: {Theme.LIME_DIM};
            }}
        """)
        self.setEchoMode(QLineEdit.EchoMode.Password)

    def set_password_mode(self, enabled: bool):
        """Enable or disable password input mode."""
        self._password_mode = enabled
        if enabled:
            self._apply_password_style()
        else:
            self._apply_normal_style()

    def _submit(self):
        text = self.text()
        self.clear()

        # Don't add password entries to history
        if not self._password_mode and text.strip():
            self._history.append(text.strip())
            self._history_index = -1
            self._current_input = ""

        self._on_submit(text)

    def keyPressEvent(self, event: QKeyEvent):
        # Disable history navigation in password mode
        if self._password_mode:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Up:
            self._navigate_history(1)  # Up = go back in history
        elif event.key() == Qt.Key.Key_Down:
            self._navigate_history(-1)  # Down = go forward in history
        else:
            super().keyPressEvent(event)

    def _navigate_history(self, direction: int):
        if not self._history:
            return

        if self._history_index == -1:
            self._current_input = self.text()

        new_index = self._history_index + direction

        if new_index < -1:
            new_index = -1
        elif new_index >= len(self._history):
            new_index = len(self._history) - 1

        self._history_index = new_index

        if new_index == -1:
            self.setText(self._current_input)
        else:
            self.setText(self._history[-(new_index + 1)])


class ConsoleWindow(QMainWindow):
    """Terminal-style console window for MultiClaw."""

    def __init__(self, core: "MultiClaw", parent=None):
        super().__init__(parent)
        self.core = core
        self._handler = CommandHandler(self.core)

        # Pending input state for multi-step commands
        self._waiting_for_input = False
        self._input_field = None  # "password", "confirm", "text"

        self.setWindowTitle("MultiClaw Console")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Output area
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont(Theme.MONO_FONT, 10))
        self.output.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BLACK};
                color: {Theme.LIME};
                border: none;
                padding: 12px;
                selection-background-color: {Theme.LIME_DIM};
            }}
        """)
        layout.addWidget(self.output)

        # Input area with prompt label
        input_container = QWidget()
        input_container.setStyleSheet(f"background-color: {Theme.CHARCOAL};")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)

        self.prompt_label = PromptLabel("multiclaw>")
        input_layout.addWidget(self.prompt_label)

        self.input = CommandInput(self._handle_input, self)
        input_layout.addWidget(self.input)

        layout.addWidget(input_container)

        # Show banner
        self.output.setHtml(CONSOLE_BANNER)

        # Subscribe to events
        self._setup_event_subscriptions()

        # Focus input
        self.input.setFocus()

    def _setup_event_subscriptions(self):
        """Subscribe to core events for live updates."""
        from core.events import EventType

        def on_event(event):
            QTimer.singleShot(0, lambda: self._show_event(event))

        self.core.event_bus.subscribe(EventType.ACTIVITY, on_event)
        self.core.event_bus.subscribe(EventType.APPROVAL_NEEDED, on_event)
        self.core.event_bus.subscribe(EventType.TRANSACTION_CREATED, on_event)

    def _show_event(self, event):
        """Display an event in the console."""
        from core.events import EventType

        if event.type == EventType.ACTIVITY:
            msg = event.data.get("message", "")
            is_error = event.data.get("is_error", False)
            color = "#E94435" if is_error else "#888888"
            self._append(f"[event] {msg}", color)
        elif event.type == EventType.APPROVAL_NEEDED:
            agent = event.data.get("agent_name", "unknown")
            amount = event.data.get("amount_micro", 0) / 1_000_000
            self._append(f"[approval needed] {agent} requests ${amount:.6f}", "#FFA500")

    def _append(self, text: str, color: str = None):
        """Append text to output."""
        color = color or Theme.LIME
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(f'<span style="color: {color};">{text}</span><br>')
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _append_lines(self, lines: list[tuple[str, str]]):
        """Append multiple lines. Each tuple is (text, color)."""
        for text, color in lines:
            self._append(text, color)

    def _handle_input(self, text: str):
        """Handle input - either a command or a pending input response."""
        if self._waiting_for_input:
            was_password = self.input._password_mode
            self._waiting_for_input = False
            field = self._input_field
            self._input_field = None
            # Reset prompt label
            self.prompt_label.setText("multiclaw>")
            self.prompt_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.CHARCOAL};
                    color: {Theme.LIME};
                    border: none;
                    padding: 8px 0px 8px 12px;
                }}
            """)
            self.input.set_password_mode(False)
            if was_password:
                self._append("> ********", "#888888")
            else:
                self._append(f"> {text.strip()}", Theme.WHITE)
            result = self._handler.execute("", inputs={field: text.strip()})
            self._handle_result(result)
            return

        text = text.strip()
        if not text:
            return

        self._append(f"multiclaw> {text}", Theme.WHITE)
        result = self._handler.execute(text)
        self._handle_result(result)

    def _handle_result(self, result: CommandResult):
        """Interpret a CommandResult and update the console."""
        # Special actions
        if result.data:
            action = result.data.get("action")
            if action == "clear":
                self.output.setHtml(CONSOLE_BANNER)
                return
            if action == "exit":
                self.hide()
                return

        # Needs more input (password, confirmation, etc.)
        if result.needs_input:
            ni = result.needs_input
            self._append(ni["prompt"], "#888888")
            self._input_field = ni["type"]
            self._waiting_for_input = True
            is_password = ni["type"] == "password"
            self.prompt_label.setText("password:" if is_password else "")
            self.prompt_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.CHARCOAL};
                    color: {Theme.RUST if is_password else Theme.LIME};
                    border: none;
                    padding: 8px 0px 8px 12px;
                }}
            """)
            self.input.set_password_mode(is_password)
            return

        # Output
        color = Theme.LIME if result.success else "#E94435"
        if result.output:
            for line in result.output.split("\n"):
                self._append(_html.escape(line), color)
        if result.error:
            self._append(_html.escape(result.error), "#E94435")

    # _register_commands and all duplicate _cmd_* methods removed.
    # All commands are routed through CommandHandler (src/commands/).
