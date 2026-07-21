"""
Primer Design System - Centralized theming for PyQt6 applications.

Architecture:
    1. Token palettes (LIGHT/DARK) define all colors in one place
    2. build_qss() generates the complete stylesheet from a palette
    3. Widgets use semantic properties (role="muted", variant="primary")
    4. set_role() updates properties at runtime with automatic re-polish

Usage:
    # At app startup:
    app.setStyleSheet(build_qss(DARK))

    # On widgets:
    label.setProperty("role", "muted")
    button.setProperty("variant", "primary")

    # At runtime when state changes:
    set_role(status_dot, status="on")
"""

from PyQt6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QFrame,
    QPushButton, QLabel, QWidget
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFont, QMouseEvent

# =============================================================================
# Brand Constants (theme-independent)
# =============================================================================


class Theme:
    """Static brand constants - fonts, sizes, and raw hex values.

    For theme-aware colors, use the LIGHT/DARK palettes below.
    These constants are kept for: (1) special cases like syntax highlighting,
    (2) console windows that intentionally ignore theming.
    """

    MONO_FONT = "JetBrains Mono"

    # Raw brand colors (use sparingly - prefer palette tokens)
    LIME = "#baea2a"
    LIME_DIM = "#7a9a1a"
    BLACK = "#09090b"
    BLACK_LIGHT = "#121214"
    CHARCOAL = "#4A4543"
    RUST = "#B7410E"
    WHITE = "#fafafa"

    # Semantic status colors
    SUCCESS = "#22c55e"
    ERROR = "#ef4444"
    WARNING = "#f59e0b"

    # Syntax highlighting (console/help text)
    PLACEHOLDER = "#22d3ee"  # Cyan - <user_input> placeholders
    OPTIONAL = "#a78bfa"     # Purple - [optional] parameters

    # Standard dialog dimensions
    MIN_DIALOG_WIDTH = 350
    MIN_POPUP_WIDTH = 300


# =============================================================================
# Color Palettes
# =============================================================================

LIGHT = {
    # Backgrounds (layered hierarchy)
    "bg": "#faf8f5",
    "raised": "#f6f4ee",
    "alt": "#f4f1ec",
    "input_bg": "#ffffff",

    # Borders
    "line": "#ded9d2",
    "line2": "#cec8c0",

    # Text hierarchy
    "text": "#1c1917",
    "muted": "#78716c",
    "dim": "#a8a29e",

    # Accent
    "accent": "#6f8f16",
    "accent_dim": "#5c7414",
    "accent_soft": "#eef2df",

    # Semantic
    "error": "#c0392b",
    "warn": "#b23410",
    "success": "#3d8b40",

    # Status indicators
    "on": "#6f8f16",
    "off": "#b23410",
    "warn_dot": "#c98a00",

    # Dark islands (header/terminal stay dark in both themes)
    "header_bg": "#09090b",
    "header_text": "#fafafa",
    "header_dim": "#8f8b88",
    "term_bg": "#000000",
    "term_text": "#7a9a1a",
    "term_dim": "#4A4543",

    # Special containers
    "seed_bg": "#fbf7df",
    "seed_border": "#e3d98a",
    "warnbox_bg": "#fdf1e7",
    "warnbox_border": "#e8c3a4",
    "warnbox_text": "#8a4b1a",
}

DARK = {
    # Backgrounds
    "bg": "#09090b",
    "raised": "#121214",
    "alt": "#17171c",
    "input_bg": "#1a1a1e",

    # Borders
    "line": "#4A4543",
    "line2": "#5a5553",

    # Text hierarchy
    "text": "#fafafa",
    "muted": "#8f8b88",
    "dim": "#5a5553",

    # Accent
    "accent": "#baea2a",
    "accent_dim": "#7a9a1a",
    "accent_soft": "#17200a",

    # Semantic
    "error": "#ef4444",
    "warn": "#cf4a1c",
    "success": "#22c55e",

    # Status indicators
    "on": "#baea2a",
    "off": "#cf4a1c",
    "warn_dot": "#f59e0b",

    # Dark islands
    "header_bg": "#09090b",
    "header_text": "#fafafa",
    "header_dim": "#8f8b88",
    "term_bg": "#000000",
    "term_text": "#7a9a1a",
    "term_dim": "#4A4543",

    # Special containers
    "seed_bg": "#1a1a10",
    "seed_border": "#4a4520",
    "warnbox_bg": "#1e120a",
    "warnbox_border": "#5a3a1a",
    "warnbox_text": "#e08a4a",
}


# =============================================================================
# QSS Generation - organized by component category
# =============================================================================

def _base_styles(p: dict, font: str) -> str:
    """Core widget defaults and window backgrounds."""
    return f"""
    QWidget {{ font-family: "{font}"; color: {p['text']}; font-size: 12px; }}
    QMainWindow {{ background: {p['bg']}; }}
    QFrame#windowFrame {{ background: {p['bg']}; border: 1px solid {p['line2']}; }}
    QDialog {{ background: {p['bg']}; }}
    QStatusBar {{ background: {p['raised']}; color: {p['muted']}; border-top: 1px solid {p['line']}; }}
    QToolTip {{ background: {p['raised']}; color: {p['text']}; border: 1px solid {p['line2']}; padding: 4px 6px; }}
    """


def _menu_styles(p: dict) -> str:
    """Menu bar and dropdown menus."""
    return f"""
    QMenuBar {{ background: {p['raised']}; color: {p['muted']}; border-bottom: 1px solid {p['line']}; }}
    QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
    QMenuBar::item:selected {{ color: {p['text']}; background: {p['alt']}; }}
    QMenu {{ background: {p['bg']}; color: {p['text']}; border: 1px solid {p['line2']}; }}
    QMenu::item {{ padding: 6px 16px; }}
    QMenu::item:selected {{ background: {p['accent_soft']}; color: {p['text']}; }}
    """


def _tab_styles(p: dict) -> str:
    """Tab widget and tab bar."""
    return f"""
    QTabWidget::pane {{ border: none; background: {p['bg']}; }}
    QTabBar {{ background: {p['bg']}; }}
    QTabBar::tab {{
        background: transparent; color: {p['muted']}; padding: 8px 16px;
        border: none; border-bottom: 2px solid transparent; margin-right: 2px;
    }}
    QTabBar::tab:hover {{ color: {p['text']}; }}
    QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 2px solid {p['accent']}; background: {p['raised']}; }}
    """


def _button_styles(p: dict) -> str:
    """Button variants: default (ghost), primary, danger, segment."""
    return f"""
    /* Default: ghost style */
    QPushButton {{
        background: transparent; color: {p['accent']}; border: 1px solid {p['line2']};
        border-radius: 4px; padding: 6px 12px;
    }}
    QPushButton:hover {{ border-color: {p['accent']}; background: {p['accent_soft']}; }}
    QPushButton:pressed {{ background: {p['alt']}; }}
    QPushButton:disabled {{ color: {p['dim']}; border-color: {p['line']}; }}

    /* Primary: solid accent */
    QPushButton[variant="primary"] {{
        background: {p['accent']}; color: {p['bg']}; border-color: {p['accent']}; font-weight: bold;
    }}
    QPushButton[variant="primary"]:hover {{ background: {p['accent_dim']}; border-color: {p['accent_dim']}; }}

    /* Danger: solid warn/error */
    QPushButton[variant="danger"] {{
        background: {p['warn']}; color: #ffffff; border-color: {p['warn']}; font-weight: bold;
    }}
    QPushButton[variant="danger"]:hover {{ background: {p['error']}; border-color: {p['error']}; }}

    /* Danger ghost: text only */
    QPushButton[variant="danger-ghost"] {{ background: transparent; color: {p['warn']}; border: none; font-weight: bold; }}
    QPushButton[variant="danger-ghost"]:hover {{ color: {p['error']}; }}

    /* Segment: toggle button group */
    QPushButton[segment="true"] {{ border-radius: 0; padding: 5px 18px; color: {p['muted']}; }}
    QPushButton[segment="true"]:hover {{ color: {p['text']}; background: {p['accent_soft']}; }}
    QPushButton[segment="true"]:checked {{ background: {p['accent']}; color: {p['bg']}; border-color: {p['accent']}; }}

    /* Compact: small buttons for table actions */
    QPushButton[compact="true"] {{ padding: 2px 4px; }}
    """


def _input_styles(p: dict) -> str:
    """Text inputs, combo boxes, spin boxes."""
    return f"""
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
        background: {p['input_bg']}; color: {p['text']}; border: 1px solid {p['line2']};
        border-radius: 4px; padding: 5px 8px;
        selection-background-color: {p['accent_soft']}; selection-color: {p['text']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
        border-color: {p['accent']};
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox::down-arrow {{
        border-left: 4px solid transparent; border-right: 4px solid transparent;
        border-top: 5px solid {p['muted']}; width: 0; height: 0;
    }}
    QComboBox::down-arrow:hover {{ border-top-color: {p['text']}; }}
    QComboBox QAbstractItemView {{
        background: {p['bg']}; color: {p['text']}; border: 1px solid {p['line2']};
        selection-background-color: {p['accent_soft']}; selection-color: {p['text']};
    }}
    """


def _container_styles(p: dict) -> str:
    """Group boxes, tables, lists."""
    return f"""
    /* Group boxes */
    QGroupBox {{
        border: 1px solid {p['line']}; border-radius: 4px; margin-top: 10px; background: {p['raised']};
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {p['accent']}; }}

    /* Tables */
    QTableView, QTableWidget {{
        background: {p['bg']}; alternate-background-color: {p['alt']};
        color: {p['text']}; gridline-color: {p['line']}; border: 1px solid {p['line']};
    }}
    QTableView::item {{ padding: 4px 6px; }}
    QTableView::item:selected {{ background: {p['accent_soft']}; color: {p['text']}; }}
    QHeaderView {{ background: {p['raised']}; }}
    QHeaderView::section {{
        background: {p['raised']}; color: {p['muted']}; border: none;
        border-bottom: 1px solid {p['line']}; border-right: 1px solid {p['line']}; padding: 6px 8px;
    }}
    QTableCornerButton::section {{ background: {p['raised']}; border: none; border-bottom: 1px solid {p['line']}; }}

    /* Lists */
    QListWidget {{
        background: {p['bg']}; alternate-background-color: {p['alt']};
        color: {p['text']}; border: 1px solid {p['line']}; border-radius: 4px;
    }}
    QListWidget::item {{ padding: 4px 6px; }}
    QListWidget::item:selected {{ background: {p['accent_soft']}; color: {p['text']}; }}
    QListWidget::item:hover {{ background: {p['alt']}; }}
    """


def _checkbox_styles(p: dict) -> str:
    """Checkboxes and radio buttons."""
    return f"""
    QCheckBox, QRadioButton {{ color: {p['text']}; spacing: 8px; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 14px; height: 14px; border: 1px solid {p['line2']}; background: {p['input_bg']};
    }}
    QCheckBox::indicator {{ border-radius: 2px; }}
    QRadioButton::indicator {{ border-radius: 7px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {p['accent']}; border-color: {p['accent']};
    }}
    """


def _scrollbar_styles(p: dict) -> str:
    """Minimal scrollbar styling."""
    return f"""
    QScrollBar:vertical {{ background: {p['alt']}; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p['line2']}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
    QScrollBar:horizontal {{ background: {p['alt']}; height: 8px; }}
    QScrollBar::handle:horizontal {{ background: {p['line2']}; border-radius: 4px; min-width: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* Splitter handles blend into the theme (no default white bar) */
    QSplitter::handle {{ background: {p['bg']}; }}
    QSplitter::handle:vertical {{ height: 6px; }}
    QSplitter::handle:horizontal {{ width: 6px; }}
    QSplitter::handle:hover {{ background: {p['line2']}; }}
    """


def _label_roles(p: dict) -> str:
    """Semantic label roles: muted, hint, error, success, etc."""
    return f"""
    QLabel[role="muted"]   {{ color: {p['muted']}; }}
    QLabel[role="hint"]    {{ color: {p['muted']}; font-size: 11px; font-style: italic; }}
    QLabel[role="dim"]     {{ color: {p['dim']}; }}
    QLabel[role="error"]   {{ color: {p['error']}; }}
    QLabel[role="warn"]    {{ color: {p['warn']}; }}
    QLabel[role="success"] {{ color: {p['success']}; font-weight: bold; }}
    QLabel[role="accent"]  {{ color: {p['accent']}; }}
    QLabel[role="strong"]  {{ font-weight: bold; }}
    QLabel[role="mono"]    {{ color: {p['muted']}; font-size: 10px; }}
    QLabel[role="total"]   {{ color: {p['accent']}; font-weight: bold; font-size: 16px; }}
    QLabel[role="empty"]   {{ color: {p['dim']}; font-size: 14px; padding: 40px; }}

    /* Runtime status (use set_role() to update) */
    QLabel[status="on"]   {{ color: {p['on']}; }}
    QLabel[status="off"]  {{ color: {p['off']}; }}
    QLabel[status="warn"] {{ color: {p['warn_dot']}; }}
    """


def _special_containers(p: dict, font: str) -> str:
    """Seed boxes, warning boxes, danger zones."""
    return f"""
    QLabel#seedBox, QTextEdit#seedBox {{
        background: {p['seed_bg']}; color: {p['text']};
        border: 1px solid {p['seed_border']}; border-radius: 4px;
        padding: 12px; font-family: "{font}";
    }}
    QFrame#warningBox, QLabel#warningBox {{
        background: {p['warnbox_bg']}; color: {p['warnbox_text']};
        border: 1px solid {p['warnbox_border']}; border-radius: 4px; padding: 10px;
    }}
    QGroupBox#dangerZone {{ border-color: {p['warn']}; }}
    QGroupBox#dangerZone::title {{ color: {p['warn']}; }}
    """


def _titlebar_styles(p: dict, is_dark: bool) -> str:
    """Custom frameless title bar with menu buttons and window controls."""
    # Use theme-appropriate hover colors
    hover_bg = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.06)"
    pressed_bg = "rgba(255, 255, 255, 0.12)" if is_dark else "rgba(0, 0, 0, 0.10)"
    ctrl_hover = "rgba(255, 255, 255, 0.1)" if is_dark else "rgba(0, 0, 0, 0.08)"

    return f"""
    /* Title bar container */
    QFrame#titleBar {{
        background: {p['raised']};
        border-bottom: 1px solid {p['line']};
    }}

    /* Menu buttons (File, Agents, Settings, Help) */
    QPushButton[variant="menu"] {{
        background: transparent;
        color: {p['muted']};
        border: none;
        padding: 8px 12px;
        border-radius: 0;
    }}
    QPushButton[variant="menu"]:hover {{
        color: {p['text']};
        background: {hover_bg};
    }}
    QPushButton[variant="menu"]:pressed {{
        background: {pressed_bg};
    }}

    /* Tagline in the status bar */
    QStatusBar QLabel[role="tagline"] {{
        color: {p['muted']};
        font-style: italic;
        font-size: 11px;
        padding-right: 8px;
    }}

    /* Window control buttons base */
    #winControlMin, #winControlMax, #winControlClose {{
        background: transparent;
        color: {p['muted']};
        border: none;
        border-radius: 0;
    }}
    #winControlMin:hover, #winControlMax:hover {{
        background: {ctrl_hover};
        color: {p['text']};
    }}

    /* Close button - red on hover */
    #winControlClose:hover {{
        background: #c42b1c;
        color: #ffffff;
    }}
    #winControlClose:pressed {{
        background: #b22a1c;
    }}

    /* Dialog frame and title bar */
    QFrame#dialogFrame {{
        background: {p['bg']};
        border: 1px solid {p['line2']};
    }}
    QFrame#dialogTitleBar {{
        background: {p['raised']};
        border-bottom: 1px solid {p['line']};
    }}
    QFrame#dialogTitleBar QLabel {{
        color: {p['text']};
        background: transparent;
    }}
    #dialogClose {{
        background: transparent;
        color: {p['muted']};
        border: none;
        border-radius: 0;
    }}
    #dialogClose:hover {{
        background: #c42b1c;
        color: #ffffff;
    }}
    #dialogClose:pressed {{
        background: #b22a1c;
    }}
    """


def _dark_islands(p: dict, font: str, is_dark: bool) -> str:
    """Header and terminal styling - header follows theme, terminal stays dark."""
    # Header now follows theme colors
    header_bg = p['raised']
    header_text = p['text']
    header_dim = p['muted']
    activity_text = p['accent_dim'] if is_dark else p['accent']

    return f"""
    QWidget#header {{ background: {header_bg}; border-bottom: 1px solid {p['line']}; }}
    QWidget#header QLabel {{ color: {header_text}; background: transparent; }}
    QLabel#logo {{ color: {p['accent']}; font-weight: bold; font-size: 16px; }}
    QWidget#header QLabel[status="on"]  {{ color: {p['on']}; }}
    QWidget#header QLabel[status="off"] {{ color: {p['off']}; }}
    QWidget#header QTextEdit {{ background: transparent; border: none; color: {activity_text}; }}

    #terminal, QTextEdit#terminal, QPlainTextEdit#terminal {{
        background: {p['term_bg']}; color: {p['term_text']}; border: none;
        padding: 12px; font-family: "{font}"; selection-background-color: {p['accent_dim']};
    }}
    """


def build_qss(palette: dict) -> str:
    """Generate the complete application stylesheet from a color palette.

    Args:
        palette: Either LIGHT or DARK palette dict.

    Returns:
        Complete QSS string to pass to QApplication.setStyleSheet().
    """
    font = Theme.MONO_FONT
    is_dark = palette is DARK

    return "".join([
        _base_styles(palette, font),
        _menu_styles(palette),
        _tab_styles(palette),
        _button_styles(palette),
        _input_styles(palette),
        _container_styles(palette),
        _checkbox_styles(palette),
        _scrollbar_styles(palette),
        _label_roles(palette),
        _special_containers(palette, font),
        _titlebar_styles(palette, is_dark),
        _dark_islands(palette, font, is_dark),
    ])


# =============================================================================
# Runtime Helpers
# =============================================================================

def set_role(widget, **props) -> None:
    """Set semantic properties on a widget and re-apply styles.

    Use this when a property changes at runtime (e.g., status indicator
    switching from "on" to "off"). At widget creation, just use
    widget.setProperty() directly.

    Example:
        set_role(status_label, status="on")
        set_role(error_label, role="error")
    """
    for key, value in props.items():
        widget.setProperty(key, value)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


# =============================================================================
# Frameless Dialog Base Class
# =============================================================================

class FramelessDialog(QDialog):
    """Base class for frameless dialogs with custom title bar.

    Provides:
    - Frameless window with DWM shadow (Windows)
    - Custom title bar with title and close button
    - Window dragging via title bar
    - Content area for subclass widgets

    Usage:
        class MyDialog(FramelessDialog):
            def __init__(self, parent=None):
                super().__init__("My Dialog Title", parent)
                # Add widgets to self.content_layout
                self.content_layout.addWidget(QLabel("Hello"))
    """

    def __init__(self, title: str, parent=None, width: int = 400):
        super().__init__(parent)
        self._drag_pos: QPoint | None = None

        # Frameless setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumWidth(width)

        # Enable DWM shadow
        self._enable_dwm_shadow()

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Border frame
        self._frame = QFrame()
        self._frame.setObjectName("dialogFrame")
        self._frame.setFrameShape(QFrame.Shape.Box)
        main_layout.addWidget(self._frame)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setObjectName("dialogTitleBar")
        title_bar.setFixedHeight(32)
        frame_layout.addWidget(title_bar)

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 4, 0)
        title_layout.setSpacing(0)

        # Title text
        self._title_label = QLabel(title)
        self._title_label.setFont(QFont(Theme.MONO_FONT, 10))
        title_layout.addWidget(self._title_label)

        title_layout.addStretch()

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setObjectName("dialogClose")
        close_btn.setFixedSize(32, 32)
        close_btn.setFont(QFont(Theme.MONO_FONT, 10))
        # Don't let the close button become the dialog's default button, or
        # pressing Enter anywhere (e.g. the console input) would trigger it
        # and reject() the dialog.
        close_btn.setAutoDefault(False)
        close_btn.setDefault(False)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)

        # Content area
        content_widget = QWidget()
        frame_layout.addWidget(content_widget)

        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(16, 12, 16, 16)
        self.content_layout.setSpacing(8)

    def setDialogTitle(self, title: str):
        """Update the dialog title."""
        self._title_label.setText(title)

    def _enable_dwm_shadow(self):
        """Enable Windows DWM drop shadow."""
        import sys
        if sys.platform != 'win32':
            return

        try:
            import ctypes

            hwnd = int(self.winId())

            DWMWA_NCRENDERING_POLICY = 2
            DWMNCRP_ENABLED = 2

            class MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]

            dwmapi = ctypes.windll.dwmapi

            policy = ctypes.c_int(DWMNCRP_ENABLED)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_NCRENDERING_POLICY,
                ctypes.byref(policy), ctypes.sizeof(policy)
            )

            margins = MARGINS(1, 1, 1, 1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

        except Exception:
            pass

    def mousePressEvent(self, event: QMouseEvent):
        """Start dragging if clicking on title bar."""
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() <= 32:
                self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle window dragging."""
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            diff = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + diff)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """End dragging."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# =============================================================================
# Frameless Message Box
# =============================================================================

class FramelessMessageBox(FramelessDialog):
    """Styled message box that matches FramelessDialog appearance.

    Replaces QMessageBox with consistent frameless styling.

    Usage:
        # Question dialog
        if FramelessMessageBox.question(parent, "Confirm", "Delete this item?"):
            do_delete()

        # Warning dialog
        FramelessMessageBox.warning(parent, "Warning", "This cannot be undone.")

        # Info dialog
        FramelessMessageBox.information(parent, "Success", "Operation completed.")

        # Critical dialog
        FramelessMessageBox.critical(parent, "Error", "Something went wrong.")
    """

    # Result codes
    Yes = 1
    No = 0

    def __init__(self, title: str, message: str, buttons: list[str], parent=None,
                 default_button: int = 0, icon_type: str = "info"):
        super().__init__(title, parent, width=350)
        self.setModal(True)
        self._result = None

        layout = self.content_layout
        layout.setSpacing(12)

        # Message with optional icon indicator
        msg_layout = QHBoxLayout()
        msg_layout.setSpacing(12)

        # Icon indicator (colored circle)
        if icon_type in ("question", "warning", "critical", "info"):
            icon_label = QLabel("●")
            icon_label.setFont(QFont(Theme.MONO_FONT, 16))
            if icon_type == "question":
                icon_label.setStyleSheet(f"color: {Theme.LIME};")
            elif icon_type == "warning":
                icon_label.setStyleSheet(f"color: {Theme.RUST};")
            elif icon_type == "critical":
                icon_label.setStyleSheet(f"color: {Theme.ERROR};")
            else:  # info
                icon_label.setStyleSheet(f"color: {Theme.LIME_DIM};")
            msg_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignTop)

        # Message text
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setMinimumWidth(250)
        msg_layout.addWidget(msg_label, stretch=1)

        layout.addLayout(msg_layout)
        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._buttons = []
        for i, btn_text in enumerate(buttons):
            btn = QPushButton(btn_text)
            btn.setFixedWidth(80)
            if i == default_button:
                btn.setDefault(True)
                btn.setFocus()
            btn.clicked.connect(lambda checked, idx=i: self._on_button(idx))
            btn_layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addLayout(btn_layout)

    def _on_button(self, index: int):
        self._result = index
        self.accept()

    def result_index(self) -> int:
        return self._result if self._result is not None else 0

    @classmethod
    def question(cls, parent, title: str, message: str, default_no: bool = True) -> bool:
        """Show a Yes/No question. Returns True if Yes clicked."""
        dlg = cls(title, message, ["Yes", "No"], parent,
                  default_button=1 if default_no else 0, icon_type="question")
        dlg.exec()
        return dlg.result_index() == 0  # Yes is index 0

    @classmethod
    def warning(cls, parent, title: str, message: str) -> None:
        """Show a warning dialog with OK button."""
        dlg = cls(title, message, ["OK"], parent, default_button=0, icon_type="warning")
        dlg.exec()

    @classmethod
    def information(cls, parent, title: str, message: str) -> None:
        """Show an info dialog with OK button."""
        dlg = cls(title, message, ["OK"], parent, default_button=0, icon_type="info")
        dlg.exec()

    @classmethod
    def critical(cls, parent, title: str, message: str) -> None:
        """Show a critical error dialog with OK button."""
        dlg = cls(title, message, ["OK"], parent, default_button=0, icon_type="critical")
        dlg.exec()


# =============================================================================
# Dialog Helpers (convenience functions)
# =============================================================================

def ask_question(parent, title: str, message: str, default_no: bool = True) -> bool:
    """Show a Yes/No question dialog. Returns True if Yes clicked."""
    return FramelessMessageBox.question(parent, title, message, default_no)


def show_warning(parent, title: str, message: str) -> None:
    """Show a warning dialog."""
    FramelessMessageBox.warning(parent, title, message)


def show_info(parent, title: str, message: str) -> None:
    """Show an info dialog."""
    FramelessMessageBox.information(parent, title, message)
