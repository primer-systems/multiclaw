"""
Main Window - The primary application window.

Contains the header, tabs, status bar, and system tray.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QStatusBar, QMenuBar, QMenu, QFrame, QTextEdit,
    QSystemTrayIcon, QStyle, QApplication, QDialog,
    QPushButton, QSizeGrip
)
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QPoint
from PyQt6.QtGui import QAction, QIcon, QFont, QPixmap, QMouseEvent
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from .theme import Theme, DARK, build_qss, set_role, FramelessMessageBox
from .tabs import (
    PoliciesTab, AgentsTab, HistoryTab, WalletTab, NetworkTab, LogTab
)
from .market_tab import MarketTab
from .dialogs import SettingsDialog
from ..services import SigningRequest
from ..version import __version__
from ..wallet import WalletInfo
from ..networks import format_address
from ..utils import get_app_dir, get_assets_dir
if TYPE_CHECKING:
    from ..core import MultiClaw


class GUIApprovalHandler(QObject):
    """
    Approval handler for GUI mode.

    Shows dialogs to the user for manual payment approvals.
    Implements the ApprovalHandler protocol defined in core.interfaces.

    Uses a Qt signal to safely deliver approval requests from the HTTP
    server thread to the Qt main thread.
    """

    # Signal to safely cross from HTTP thread to Qt main thread
    _approval_requested = pyqtSignal(object)

    def __init__(self, main_window: "MainWindow"):
        super().__init__(parent=main_window)
        self._main_window = main_window
        self._pending_dialogs: dict[str, QDialog] = {}
        self._approval_requested.connect(self._show_approval)

    def request_approval(self, request: SigningRequest) -> None:
        """
        Called when a payment needs manual approval.

        Shows the approval dialog to the user. The dialog will call
        core.approve_request() or core.reject_request() when the user decides.
        """
        # Emit signal — Qt guarantees delivery to the main thread
        self._approval_requested.emit(request)

    def _show_approval(self, request: SigningRequest) -> None:
        """Show approval dialog on the Qt main thread."""
        self._main_window.on_approval_needed(request)

    def on_approval_resolved(self, request_id: str, approved: bool, reason: Optional[str] = None) -> None:
        """
        Called when an approval has been resolved.

        Allows us to close any open dialogs for this request.
        """
        # If we had a dialog open for this request, close it
        if request_id in self._pending_dialogs:
            dialog = self._pending_dialogs.pop(request_id)
            if dialog.isVisible():
                dialog.close()


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, core: "MultiClaw"):
        super().__init__()
        self.core = core
        self.signing_enabled = True
        self.server_running = False
        self._console_window = None

        # Frameless window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._drag_pos: QPoint | None = None
        self._is_maximized = False

        # Enable DWM shadow on Windows
        self._enable_dwm_shadow()

        self.setWindowTitle("MultiClaw - Get a Grip on Your Agents")
        self.setMinimumSize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Border frame wraps all content
        self.window_frame = QFrame()
        self.window_frame.setObjectName("windowFrame")
        self.window_frame.setFrameShape(QFrame.Shape.Box)
        outer_layout.addWidget(self.window_frame)

        layout = QVBoxLayout(self.window_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Custom title bar (replaces native menu bar)
        self.title_bar = self.create_title_bar()
        layout.addWidget(self.title_bar)

        self.header = self.create_header()
        layout.addWidget(self.header)

        self.tabs = QTabWidget()

        # Create status bar early (before signals that might trigger update_status)
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # --- Tagline (bottom-right of the status bar) ---
        self.statusbar_tagline = QLabel("MultiClaw - Get a Grip on Your Agents!")
        self.statusbar_tagline.setProperty("role", "tagline")
        self.status.addPermanentWidget(self.statusbar_tagline)

        # Create all tabs first - all tabs receive core, not store
        self.agents_tab = AgentsTab(self.core)
        self.agents_tab.activity.connect(self.on_agent_activity)
        self.policies_tab = PoliciesTab(self.core)
        self.policies_tab.policy_deleted.connect(self.on_policy_deleted)
        self.policies_tab.activity.connect(self.on_policy_activity)
        self.wallet_tab = WalletTab(core=self.core)
        self.wallet_tab.wallets_changed.connect(self.on_wallets_changed)
        self.wallet_tab.wallet_deleted.connect(self.on_wallet_deleted)
        self.wallet_tab.wallet_locked.connect(self.on_wallet_locked)
        self.wallet_tab.wallet_unlocked.connect(self.on_wallet_unlocked)
        self.wallet_tab.wallet_path_changed.connect(self.on_wallet_path_changed)
        self.wallet_tab.activity.connect(self.update_activity)
        self.wallet_tab.set_agents_query_fn(self._get_agents_for_address)
        self.network_tab = NetworkTab(self.core)
        self.network_tab.activity.connect(self.update_activity)
        self.network_tab.server_toggled.connect(self.on_server_toggled)
        self.network_tab.custom_port_changed.connect(self.on_custom_port_changed)
        self.network_tab.network_toggled.connect(self.on_network_toggled)
        self.network_tab.verify_settlements_changed.connect(self.on_verify_settlements_changed)
        self.network_tab.allow_lan_changed.connect(self.on_allow_lan_changed)
        self.history_tab = HistoryTab(self.core)
        self.log_tab = LogTab()
        self.market_tab = MarketTab()
        self.market_tab.activity.connect(self.update_activity)

        # Add tabs in desired order: Agents, Policies, Wallets, Network, Market, History, Logs
        self.tabs.addTab(self.agents_tab, "Agents")
        self.tabs.addTab(self.policies_tab, "Policies")
        self.tabs.addTab(self.wallet_tab, "Wallet")
        self.tabs.addTab(self.network_tab, "Network")
        self.tabs.addTab(self.market_tab, "Market")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(self.log_tab, "Logs")

        self.agents_tab.wallets = self.wallet_tab.get_wallet_list()
        self.agents_tab.get_wallet_fn = self.wallet_tab.get_unlocked_wallet

        # Load and apply settings
        # GUI-specific settings (window state, paths, etc.)
        self._settings = self._load_settings()
        if self._settings.get("custom_port_enabled", False):
            self.network_tab.set_custom_port_enabled(True)

        # Load shared settings from Core (persisted and cross-process synced)
        core_settings = self.core.settings_manager.settings
        self.network_tab.set_verify_settlements(core_settings.signing.verify_settlements)
        self.network_tab.set_allow_lan(core_settings.server.allow_lan)

        # Load custom RPC endpoints from Core settings
        custom_rpcs = {int(k): v for k, v in core_settings.rpc.endpoints.items() if v}
        self.network_tab.set_custom_rpcs(custom_rpcs)
        self.wallet_tab.set_custom_rpcs(custom_rpcs)
        self.network_tab.rpc_changed.connect(self.on_rpc_changed)

        # Load auto-lock timeout
        auto_lock_minutes = self._settings.get("auto_lock_minutes", 0)
        self.wallet_tab.set_auto_lock_timeout(auto_lock_minutes)

        # Load wallet path
        wallet_path = self._settings.get("wallet_path", "")
        if wallet_path:
            self.wallet_tab.set_wallet_path(wallet_path)

        # Configure logging persistence
        log_retention = self._settings.get("log_retention_days", 0)
        log_lines = self._settings.get("log_lines_on_startup", 0)
        self.log_tab.set_retention_days(log_retention)
        if log_lines > 0:
            self.log_tab.load_recent(log_lines)

        # Cleanup old log files
        if log_retention > 0:
            from ..services.logging import cleanup_old_logs
            deleted = cleanup_old_logs(log_retention)
            if deleted > 0:
                self.log_tab.add_log(f"Cleaned up {deleted} old log file(s)")

        layout.addWidget(self.tabs)

        self.update_status()

        self.setup_tray()
        self.setup_signing_service()
        self.setup_event_subscriptions()

        # Apply theme (default to light)
        self.apply_theme(self._settings.get("theme", "light"))

        # Initialize status indicators
        self.update_status_indicators()

        # Apply startup settings
        if self._settings.get("start_minimized", False):
            QTimer.singleShot(0, self.hide if self._settings.get("minimize_to_tray", False) else self.showMinimized)

        # Auto-start server if enabled
        if self._settings.get("auto_start_server", True):
            QTimer.singleShot(500, self.network_tab.toggle_server)

    def _get_agents_for_address(self, wallet_address: str) -> list:
        """Get all agents linked to a specific wallet address."""
        return [
            agent for agent in self.core.get_all_agents()
            if agent.wallet_address == wallet_address
        ]

    def on_wallets_changed(self, wallets: list):
        """Handle wallet list changes from wallet tab."""
        self.agents_tab.wallets = wallets
        self.update_status()
        self.update_activity(f"Wallet list updated: {len(wallets)} address(es)")

    def on_wallet_deleted(self, wallet_address: str):
        """Handle wallet deletion - decommission any agents using this wallet."""
        decommissioned = self.core.decommission_agents_for_address(wallet_address)

        if decommissioned:
            self.agents_tab.populate_table()
            count = len(decommissioned)
            names = ", ".join(decommissioned[:3])
            if count > 3:
                names += f" (+{count - 3} more)"
            self.update_activity(f"Decommissioned {count} agent(s): {names}")

    def on_policy_deleted(self, policy_id: str, decommissioned: list):
        """Handle policy deletion - refresh agents tab if any were decommissioned."""
        if decommissioned:
            self.agents_tab.populate_table()
            count = len(decommissioned)
            names = ", ".join(decommissioned[:3])
            if count > 3:
                names += f" (+{count - 3} more)"
            self.update_activity(f"Policy deleted, decommissioned {count} agent(s): {names}")
        else:
            self.update_activity("Policy deleted")

    def on_agent_activity(self, message: str, is_error: bool):
        """Handle activity from agents tab."""
        self.update_activity(message, is_error)

    def on_policy_activity(self, message: str, is_error: bool):
        """Handle activity from policies tab."""
        self.update_activity(message, is_error)

    def on_server_toggled(self, running: bool):
        """Handle server start/stop."""
        self.server_running = running
        self.update_status()
        self.update_status_indicators()
        # Activity messages are emitted by core via event bus - no need to duplicate here

    def on_custom_port_changed(self, enabled: bool):
        """Handle custom port setting change from Network tab."""
        self._settings["custom_port_enabled"] = enabled
        self._save_settings()

    def on_rpc_changed(self, chain_id: int, rpc_url: str):
        """Handle custom RPC endpoint change from Network tab."""
        # Core persists this setting
        self.core.settings_manager.set_rpc_endpoint(chain_id, rpc_url if rpc_url else None)
        # Update wallet tab with new RPCs
        self.wallet_tab.set_custom_rpcs(self.network_tab.get_custom_rpcs())

    def on_wallet_path_changed(self, path: str):
        """Handle wallet path change - save to settings for persistence."""
        self._settings["wallet_path"] = path
        self._save_settings()

    def on_network_toggled(self, chain_id: int, enabled: bool):
        """Handle network enable/disable from Network tab."""
        self.core.set_network_enabled(chain_id, enabled)

    def on_verify_settlements_changed(self, enabled: bool):
        """Handle verify settlements setting change from Network tab."""
        # Core persists this setting
        self.core.set_verify_settlements(enabled)

    def on_allow_lan_changed(self, enabled: bool):
        """Handle allow LAN setting change from Network tab."""
        # Core persists this setting
        self.core.settings_manager.set_allow_lan(enabled)

    def on_wallet_locked(self):
        """Handle wallet lock."""
        self.update_status_indicators()
        self.update_activity("Wallet locked")

    def on_wallet_unlocked(self):
        """Handle wallet unlock."""
        self.update_status_indicators()
        self.update_activity("Wallet unlocked")

    def on_wallet_indicator_clicked(self):
        """Handle click on wallet indicator - go to wallet tab."""
        self.tabs.setCurrentWidget(self.wallet_tab)
        if not self.wallet_tab.is_unlocked:
            self.wallet_tab.password_input.setFocus()

    def on_server_indicator_clicked(self):
        """Handle click on server indicator - go to network tab."""
        self.tabs.setCurrentWidget(self.network_tab)

    def update_status_indicators(self):
        """Update all three status indicators in the header."""
        # Wallet indicator - green only if we have wallets AND unlocked
        has_wallets = len(self.wallet_tab.get_wallet_list()) > 0
        wallet_on = has_wallets and self.wallet_tab.is_unlocked
        set_role(self.wallet_indicator, status="on" if wallet_on else "off")
        set_role(self.wallet_label, status="on" if wallet_on else "off")

        # Server indicator
        set_role(self.server_indicator, status="on" if self.server_running else "off")
        set_role(self.server_label, status="on" if self.server_running else "off")

        # Signing indicator
        set_role(self.signing_indicator, status="on" if self.signing_enabled else "off")
        set_role(self.signing_label, status="on" if self.signing_enabled else "off")

    def _load_settings(self) -> dict:
        """Load GUI-specific settings from disk.

        Note: Shared settings (verify_settlements, networks, etc.) are now
        managed by Core's SettingsManager. This only loads GUI-specific
        settings like window state, wallet path, etc.
        """
        import json
        import logging
        from ..utils import get_app_dir
        settings_path = get_app_dir() / "gui_settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to load GUI settings: {e}")
        return {}

    def _save_settings(self):
        """Save GUI-specific settings to disk."""
        import json
        import logging
        from ..utils import get_app_dir
        settings_path = get_app_dir() / "gui_settings.json"
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to save GUI settings: {e}")

    def apply_theme(self, theme_name: str = "light"):
        """Apply the selected theme (light or dark) to the application."""
        from .theme import LIGHT, DARK, build_qss
        palette = DARK if theme_name == "dark" else LIGHT
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_qss(palette))
        self._settings["theme"] = theme_name
        self._save_settings()
        # Update logo for theme
        self._update_logo()

    def _update_logo(self):
        """Update logo based on current theme."""
        theme = getattr(self, '_settings', {}).get("theme", "light")
        if theme == "light":
            logo_path = get_assets_dir() / "wm_stacked_lightmode.png"
        else:
            logo_path = get_assets_dir() / "wm_stacked.png"

        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled = pixmap.scaledToHeight(57, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(scaled)
        else:
            # Fallback to default or text
            fallback = get_assets_dir() / "wm_stacked.png"
            if fallback.exists():
                pixmap = QPixmap(str(fallback))
                scaled = pixmap.scaledToHeight(57, Qt.TransformationMode.SmoothTransformation)
                self.logo_label.setPixmap(scaled)
            else:
                self.logo_label.setText("MULTICLAW")
                self.logo_label.setObjectName("logo")

    def update_status(self):
        """Update status bar."""
        if self.core.is_server_running():
            self.status.showMessage(f"Listening on localhost:{self.core.server_port}")
        else:
            self.status.showMessage("Server stopped")

    def create_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")  # Styled via QSS #header selector
        header.setFixedHeight(140)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        # Logo on the left (stored for theme switching)
        self.logo_label = QLabel()
        self._update_logo()

        header_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_layout.addStretch()

        # Center: Three status indicators stacked vertically
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        # Wallet indicator
        wallet_row = QHBoxLayout()
        wallet_row.setSpacing(4)
        self.wallet_indicator = QLabel("●")
        self.wallet_indicator.setProperty("status", "off")
        self.wallet_indicator.setFixedSize(12, 14)
        wallet_row.addWidget(self.wallet_indicator)
        self.wallet_label = QLabel("Wallet")
        self.wallet_label.setFont(QFont(Theme.MONO_FONT, 9))
        self.wallet_label.setFixedHeight(14)
        self.wallet_label.setProperty("status", "off")
        self.wallet_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wallet_label.mousePressEvent = lambda e: self.on_wallet_indicator_clicked()
        wallet_row.addWidget(self.wallet_label)
        status_layout.addLayout(wallet_row)

        # Server indicator
        server_row = QHBoxLayout()
        server_row.setSpacing(4)
        self.server_indicator = QLabel("●")
        self.server_indicator.setProperty("status", "off")
        self.server_indicator.setFixedSize(12, 14)
        server_row.addWidget(self.server_indicator)
        self.server_label = QLabel("Server")
        self.server_label.setFont(QFont(Theme.MONO_FONT, 9))
        self.server_label.setFixedHeight(14)
        self.server_label.setProperty("status", "off")
        self.server_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.server_label.mousePressEvent = lambda e: self.on_server_indicator_clicked()
        server_row.addWidget(self.server_label)
        status_layout.addLayout(server_row)

        # Signing indicator (starts enabled)
        signing_row = QHBoxLayout()
        signing_row.setSpacing(4)
        self.signing_indicator = QLabel("●")
        self.signing_indicator.setProperty("status", "on")
        self.signing_indicator.setFixedSize(12, 14)
        signing_row.addWidget(self.signing_indicator)
        self.signing_label = QLabel("Signing")
        self.signing_label.setFont(QFont(Theme.MONO_FONT, 9))
        self.signing_label.setFixedHeight(14)
        self.signing_label.setProperty("status", "on")
        self.signing_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.signing_label.mousePressEvent = lambda e: self.toggle_global_signing()
        signing_row.addWidget(self.signing_label)
        status_layout.addLayout(signing_row)

        header_layout.addLayout(status_layout)
        header_layout.addStretch()

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        font = QFont(Theme.MONO_FONT, 9)
        self.activity_log.setFont(font)
        # Activity log is styled via QSS: QWidget#header QTextEdit
        self.activity_log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.activity_log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.activity_log.setMinimumWidth(450)
        # Calculate height for 6 lines using font metrics, plus half line buffer for HTML rendering
        self.activity_log.document().setDocumentMargin(0)
        from PyQt6.QtGui import QFontMetrics
        line_height = QFontMetrics(font).lineSpacing()
        self.activity_log.setFixedHeight(line_height * 6 + line_height // 2)

        self.activity_entries = []

        header_layout.addWidget(self.activity_log)

        return header

    def update_activity(self, message: str, is_error: bool = False, is_warning: bool = False):
        """Update both the activity log in the header and the Logs tab."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Update header activity log
        if is_error:
            color = Theme.ERROR
        elif is_warning:
            color = Theme.RUST
        else:
            color = Theme.LIME_DIM

        entry = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.activity_entries.append(entry)

        if len(self.activity_entries) > 6:
            self.activity_entries = self.activity_entries[-6:]

        self.activity_log.setHtml("<br>".join(self.activity_entries))

        # Also write to Logs tab
        self.log_tab.add_log(message)

    def update_header_balance(self):
        """Update header when balance changes - currently a no-op since wallet info moved to tab."""
        pass

    def create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("Console", self.open_console)
        file_menu.addSeparator()
        file_menu.addAction("Pause", self.pause_all)
        file_menu.addSeparator()
        file_menu.addAction("Export Keys...", self.export_keys)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        agents_menu = menubar.addMenu("Agents")
        agents_menu.addAction("Register Agent...", self.register_agent)
        agents_menu.addSeparator()
        agents_menu.addAction("Suspend All", self.suspend_all_agents)

        settings_menu = menubar.addMenu("Settings")
        settings_menu.addAction("Preferences...", self.show_settings)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("Quick Start", self.show_quick_start)
        help_menu.addAction("Documentation", self.open_documentation)
        help_menu.addSeparator()
        help_menu.addAction("About MultiClaw", self.show_about)

    def setup_signing_service(self):
        """Initialize signing service configuration via Core's public API.

        Uses the proper ApprovalHandler pattern instead of overwriting
        signing service callbacks directly.
        """
        # Register GUI approval handler with core
        # This is the proper interface for handling approval requests
        self._approval_handler = GUIApprovalHandler(self)
        self.core.set_approval_handler(self._approval_handler)

        # Sync network enabled state from Core settings to NetworkTab
        for chain_id, enabled in self.core.get_enabled_networks().items():
            self.network_tab.set_network_enabled(chain_id, enabled)

        # Settings are already loaded from Core in __init__
        # verify_settlements, allow_lan, replay_window are persisted by Core

    def setup_event_subscriptions(self):
        """Subscribe to core EventBus events.

        This is the proper way to receive notifications from Core.
        GUI subscribes to EventBus just like Console does.
        """
        from ..core.events import EventType

        def on_agent_event(event):
            """Refresh agents tab when agents change."""
            QTimer.singleShot(0, self._refresh_agents_tab)

        def on_policy_event(event):
            """Refresh policies tab when policies change."""
            QTimer.singleShot(0, self._refresh_policies_tab)

        def on_transaction_event(event):
            """Refresh history tab when transactions change."""
            QTimer.singleShot(0, self._refresh_history_tab)

        def on_wallet_event(event):
            """Refresh wallet tab and status when wallet state changes."""
            QTimer.singleShot(0, self._refresh_wallet_state)

        def on_activity_event(event):
            """Handle activity log messages from Core."""
            message = event.data.get("message", "")
            is_error = event.data.get("is_error", False)
            QTimer.singleShot(0, lambda: self.update_activity(message, is_error))

        def on_settings_event(event):
            """Handle settings changes from Core (cross-process sync)."""
            QTimer.singleShot(0, self._apply_core_settings)

        # Subscribe to agent events
        self.core.event_bus.subscribe(EventType.AGENT_CREATED, on_agent_event)
        self.core.event_bus.subscribe(EventType.AGENT_UPDATED, on_agent_event)
        self.core.event_bus.subscribe(EventType.AGENT_DELETED, on_agent_event)

        # Subscribe to policy events
        self.core.event_bus.subscribe(EventType.POLICY_CREATED, on_policy_event)
        self.core.event_bus.subscribe(EventType.POLICY_UPDATED, on_policy_event)
        self.core.event_bus.subscribe(EventType.POLICY_DELETED, on_policy_event)

        # Subscribe to transaction events
        self.core.event_bus.subscribe(EventType.TRANSACTION_CREATED, on_transaction_event)
        self.core.event_bus.subscribe(EventType.TRANSACTION_UPDATED, on_transaction_event)

        # Subscribe to wallet events
        self.core.event_bus.subscribe(EventType.WALLET_LOCKED, on_wallet_event)
        self.core.event_bus.subscribe(EventType.WALLET_UNLOCKED, on_wallet_event)

        # Subscribe to activity events (logging/status messages)
        self.core.event_bus.subscribe(EventType.ACTIVITY, on_activity_event)

        # Subscribe to settings events (cross-process sync)
        self.core.event_bus.subscribe(EventType.SETTINGS_CHANGED, on_settings_event)

    def _refresh_agents_tab(self):
        """Refresh the agents tab display."""
        if hasattr(self.agents_tab, 'populate_table'):
            self.agents_tab.populate_table()

    def _refresh_policies_tab(self):
        """Refresh the policies tab display."""
        if hasattr(self.policies_tab, 'populate_table'):
            self.policies_tab.populate_table()

    def _refresh_history_tab(self):
        """Refresh the history tab display."""
        if hasattr(self.history_tab, 'refresh'):
            self.history_tab.refresh()

    def _refresh_wallet_state(self):
        """Refresh wallet-related UI state."""
        # Sync wallet tab state from core (handles console-initiated changes)
        self.wallet_tab.sync_from_core()
        self.update_status()
        self.update_status_indicators()
        # Also refresh agents tab since it shows wallet addresses
        self._refresh_agents_tab()

    def _apply_core_settings(self):
        """Apply settings from Core (handles cross-process settings sync)."""
        core_settings = self.core.settings_manager.settings

        # Update network tab with new settings
        self.network_tab.set_verify_settlements(core_settings.signing.verify_settlements)
        self.network_tab.set_allow_lan(core_settings.server.allow_lan)

        # Update network enabled states
        for chain_id_str, enabled in core_settings.signing.enabled_networks.items():
            try:
                chain_id = int(chain_id_str)
                self.network_tab.set_network_enabled(chain_id, enabled)
            except ValueError:
                pass

        # Update custom RPC endpoints
        custom_rpcs = {int(k): v for k, v in core_settings.rpc.endpoints.items() if v}
        self.network_tab.set_custom_rpcs(custom_rpcs)
        self.wallet_tab.set_custom_rpcs(custom_rpcs)

    def on_approval_needed(self, request: SigningRequest):
        """Handle a signing request that needs manual approval."""
        self.update_activity(
            f"Approval needed: {request.agent_name} ({request.agent_id}) requests {request.amount_micro/1_000_000:.6f} USDC",
            is_warning=True
        )

        # Show system tray notification if enabled
        if self._settings.get("toast_enabled", True):
            if hasattr(self, 'tray') and self.tray.isVisible():
                self.tray.showMessage(
                    "Payment Approval Required",
                    f"{request.agent_name} is requesting {request.amount_micro/1_000_000:.6f} USDC",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000
                )

        # Play sound if enabled
        if self._settings.get("sound_enabled", True):
            try:
                import winsound
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except (ImportError, RuntimeError):
                pass

        # Flash taskbar if enabled (Windows)
        if self._settings.get("flash_taskbar", True):
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.alert(self, 0)  # 0 = flash until focused
            except Exception:
                pass

        self.show_approval_dialog(request)

    def show_approval_dialog(self, request: SigningRequest):
        """Show dialog to approve/reject a payment request."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

        amount_str = f"{request.amount_micro/1_000_000:.6f} USDC"
        # Prefer request_url (full URL) over resource (often path-only)
        if request.request_url:
            resource_str = f"\nURL: {request.request_url}"
        elif request.resource:
            resource_str = f"\nResource: {request.resource}"
        else:
            resource_str = ""

        message = (
            f"Agent '{request.agent_name}' is requesting payment authorization.\n\n"
            f"Amount: {amount_str}\n"
            f"Network: {request.network}\n"
            f"Recipient: {format_address(request.recipient)}"
            f"{resource_str}"
        )

        if FramelessMessageBox.question(self, "Payment Approval Required", message):
            response = self.core.approve_request(request.id)
            if response.get("status") == "success":
                self.update_activity(f"Approved: {amount_str} for {request.agent_name}")
            else:
                self.update_activity(f"Approval failed: {response.get('error')}", is_error=True)
                FramelessMessageBox.warning(self, "Signing Failed", response.get("error", "Unknown error"))
        else:
            self.core.reject_request(request.id, "User rejected")
            self.update_activity(f"Rejected: {amount_str} for {request.agent_name}", is_warning=True)

    def setup_tray(self):
        """Set up system tray icon with context menu."""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            icon_path = get_assets_dir() / "icon256.ico"
            if icon_path.exists():
                self.tray.setIcon(QIcon(str(icon_path)))
            else:
                self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            self.tray.setToolTip("MultiClaw by Primer")

            tray_menu = QMenu()

            show_action = tray_menu.addAction("Show MultiClaw")
            show_action.triggered.connect(self.show_and_activate)

            tray_menu.addSeparator()

            pause_action = tray_menu.addAction("Pause")
            pause_action.triggered.connect(self.pause_all)

            tray_menu.addSeparator()

            quit_action = tray_menu.addAction("Quit")
            quit_action.triggered.connect(QApplication.quit)

            self.tray.setContextMenu(tray_menu)

            self.tray.activated.connect(self.on_tray_activated)

            self.tray.show()

    def show_and_activate(self):
        """Show and bring window to front."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def on_tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_and_activate()

    def open_console(self):
        """Open the console window."""
        from .console import ConsoleWindow

        if self._console_window is None or not self._console_window.isVisible():
            self._console_window = ConsoleWindow(self.core, self)
            self._console_window.show()
        else:
            self._console_window.activateWindow()
            self._console_window.raise_()

    def pause_all(self):
        """Pause all activity: stop server, lock wallet, disable signing."""
        actions = []

        # Stop server if running
        if self.server_running:
            self.core.stop_server()
            actions.append("server stopped")

        # Lock wallet if unlocked (and wallet is actually set up)
        if self.wallet_tab.is_unlocked and self.wallet_tab.has_wallets:
            self.wallet_tab.lock()
            actions.append("wallet locked")

        # Disable signing if enabled
        if self.signing_enabled:
            self.signing_enabled = False
            self.update_status_indicators()
            actions.append("signing disabled")

        if actions:
            self.update_activity(f"Paused: {', '.join(actions)}", is_warning=True)
        else:
            self.update_activity("Already paused (nothing to disable)")

    def toggle_global_signing(self):
        """Toggle global signing on/off."""
        self.signing_enabled = not self.signing_enabled
        self.update_status_indicators()
        status = "enabled" if self.signing_enabled else "disabled"
        self.update_activity(f"Signing {status}", is_warning=not self.signing_enabled)

    def export_keys(self):
        """Open the export keys dialog."""
        from .dialogs import ExportKeysDialog

        wallets = self.wallet_tab.get_wallet_list()
        if not wallets:
            FramelessMessageBox.information(self, "No Addresses", "No addresses to export.")
            return

        if not self.wallet_tab.is_unlocked:
            FramelessMessageBox.warning(
                self, "Wallet Locked",
                "Please unlock your wallet first to export keys."
            )
            self.tabs.setCurrentWidget(self.wallet_tab)
            self.wallet_tab.password_input.setFocus()
            return

        dialog = ExportKeysDialog(
            wallets=wallets,
            get_wallet_fn=self.wallet_tab.get_unlocked_wallet,
            parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.update_activity("Keys exported", is_warning=True)

    def show_settings(self):
        """Show the settings dialog."""
        from PyQt6.QtWidgets import QDialog
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.has_changes():
            new_settings = dialog.get_settings()
            old_theme = self._settings.get("theme", "light")
            self._settings.update(new_settings)
            self._save_settings()

            # Apply logging settings immediately
            self.log_tab.set_retention_days(new_settings.get("log_retention_days", 0))

            # Apply auto-lock settings
            self.wallet_tab.set_auto_lock_timeout(new_settings.get("auto_lock_minutes", 0))

            # Apply replay window setting
            replay_window = new_settings.get("replay_window_seconds", 300)
            self.core.set_max_request_age(replay_window)

            # Apply theme if changed
            new_theme = new_settings.get("theme", "light")
            if new_theme != old_theme:
                self.apply_theme(new_theme)

    def register_agent(self):
        """Open the agent registration dialog."""
        self.tabs.setCurrentWidget(self.agents_tab)
        self.agents_tab.register_agent()

    def suspend_all_agents(self):
        """Suspend all active agents."""
        active_agents = [a for a in self.core.get_all_agents() if a.status == "active"]

        if not active_agents:
            FramelessMessageBox.information(
                self,
                "No Active Agents",
                "There are no active agents to suspend."
            )
            return

        if FramelessMessageBox.question(
            self,
            "Suspend All Agents",
            f"Suspend all {len(active_agents)} active agent(s)?\n\n"
            "This will reject all signing requests until agents are reactivated."
        ):
            for agent in active_agents:
                self.core.suspend_agent(agent.code)

            self.agents_tab.populate_table()
            self.update_activity(f"Suspended {len(active_agents)} agent(s)", is_warning=True)

    def open_documentation(self):
        """Open the documentation website."""
        import webbrowser
        webbrowser.open("https://docs.primer.systems/multiclaw.html")

    def show_about(self):
        """Show the About MultiClaw dialog."""
        from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox
        from PyQt6.QtCore import Qt
        from .theme import FramelessDialog

        dialog = FramelessDialog("About MultiClaw", self, width=400)

        layout = dialog.content_layout
        layout.setSpacing(12)

        # Tagline
        tagline = QLabel("MultiClaw, by Primer")
        tagline.setProperty("role", "hint")
        layout.addWidget(tagline)

        # Version
        version = QLabel(f"Version {__version__}")
        version.setProperty("role", "muted")
        layout.addWidget(version)

        layout.addSpacing(4)

        # Description
        desc = QLabel(
            "Authorize AI agent x402 payments locally.\n"
            "Your keys never leave your machine."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(8)

        # Website
        website = QLabel(
            f'<a href="https://primer.systems" style="color: {Theme.LIME_DIM};">primer.systems</a>'
        )
        website.setOpenExternalLinks(True)
        layout.addWidget(website)

        layout.addSpacing(4)

        # Social links in a row: X  TG  GIT
        social_layout = QHBoxLayout()
        social_layout.setSpacing(16)

        x_link = QLabel(f'<a href="https://x.com/primer_systems" style="color: {Theme.LIME_DIM};">X</a>')
        x_link.setOpenExternalLinks(True)
        social_layout.addWidget(x_link)

        tg_link = QLabel(f'<a href="https://t.me/primer_HQ" style="color: {Theme.LIME_DIM};">TG</a>')
        tg_link.setOpenExternalLinks(True)
        social_layout.addWidget(tg_link)

        git_link = QLabel(f'<a href="https://github.com/primer-systems" style="color: {Theme.LIME_DIM};">GIT</a>')
        git_link.setOpenExternalLinks(True)
        social_layout.addWidget(git_link)

        social_layout.addStretch()
        layout.addLayout(social_layout)

        layout.addStretch()

        # OK button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    def show_quick_start(self):
        """Show the Quick Start guide dialog."""
        from PyQt6.QtWidgets import QVBoxLayout, QLabel, QDialogButtonBox
        from .theme import FramelessDialog

        dialog = FramelessDialog("Quick Start", self, width=480)

        layout = dialog.content_layout
        layout.setSpacing(8)

        # Steps
        steps = [
            ("1.", "Add an address funded with USDC", "Wallet tab"),
            ("2.", "Create a Spend Policy", "Policies tab"),
            ("3.", "Start the Server", "Network tab"),
            ("4.", "Register an Agent", "Agents tab"),
            ("5.", "Give your agent the provided configuration", ""),
            ("6.", 'Direct your agent to <a href="http://localhost:9402/agent" style="color: {lime};">http://localhost:9402/agent</a> for instructions'.format(lime=Theme.LIME_DIM), ""),
        ]

        for num, text, hint in steps:
            step_label = QLabel(f"<b>{num}</b> {text}")
            step_label.setWordWrap(True)
            step_label.setOpenExternalLinks(True)
            layout.addWidget(step_label)

            if hint:
                hint_label = QLabel(f"    <i>{hint}</i>")
                hint_label.setProperty("role", "muted")
                layout.addWidget(hint_label)

        layout.addSpacing(12)

        # Link to full docs
        docs_label = QLabel(
            f'For more details, see the <a href="https://docs.primer.systems/multiclaw.html" '
            f'style="color: {Theme.LIME_DIM};">full documentation</a>.'
        )
        docs_label.setOpenExternalLinks(True)
        layout.addWidget(docs_label)

        layout.addStretch()

        # OK button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    def closeEvent(self, event):
        """Handle window close - optionally minimize to tray instead."""
        if self._settings.get("close_to_tray", False) and hasattr(self, 'tray') and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "MultiClaw",
                "MultiClaw is still running in the system tray.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            # Actually close - stop server first
            if self.core.is_server_running():
                self.core.stop_server()
            event.accept()

    def changeEvent(self, event):
        """Handle window state changes - optionally minimize to tray."""
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                if self._settings.get("minimize_to_tray", False) and hasattr(self, 'tray') and self.tray.isVisible():
                    event.ignore()
                    QTimer.singleShot(0, self.hide)
                    return
        super().changeEvent(event)

    # ------------------------------------------------------------------
    # Custom Title Bar & Frameless Window
    # ------------------------------------------------------------------

    def create_title_bar(self) -> QFrame:
        """Create custom title bar with menus and window controls."""
        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(36)

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(0)

        # --- Menu buttons (left side) ---
        menu_layout = QHBoxLayout()
        menu_layout.setSpacing(0)

        # File menu
        self.file_menu_btn = QPushButton("File")
        self.file_menu_btn.setFont(QFont(Theme.MONO_FONT, 9))
        self.file_menu_btn.setProperty("variant", "menu")
        self.file_menu_btn.clicked.connect(self._show_file_menu)
        menu_layout.addWidget(self.file_menu_btn)

        # Agents menu
        self.agents_menu_btn = QPushButton("Agents")
        self.agents_menu_btn.setFont(QFont(Theme.MONO_FONT, 9))
        self.agents_menu_btn.setProperty("variant", "menu")
        self.agents_menu_btn.clicked.connect(self._show_agents_menu)
        menu_layout.addWidget(self.agents_menu_btn)

        # Settings menu
        self.settings_menu_btn = QPushButton("Settings")
        self.settings_menu_btn.setFont(QFont(Theme.MONO_FONT, 9))
        self.settings_menu_btn.setProperty("variant", "menu")
        self.settings_menu_btn.clicked.connect(self._show_settings_menu)
        menu_layout.addWidget(self.settings_menu_btn)

        # Help menu
        self.help_menu_btn = QPushButton("Help")
        self.help_menu_btn.setFont(QFont(Theme.MONO_FONT, 9))
        self.help_menu_btn.setProperty("variant", "menu")
        self.help_menu_btn.clicked.connect(self._show_help_menu)
        menu_layout.addWidget(self.help_menu_btn)

        layout.addLayout(menu_layout)

        # --- Spacer (draggable area) ---
        layout.addStretch()

        # --- Window controls (right side) ---
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(0)

        # Minimize
        self.min_btn = QPushButton("─")
        self.min_btn.setObjectName("winControlMin")
        self.min_btn.setFixedSize(46, 36)
        self.min_btn.setFont(QFont(Theme.MONO_FONT, 10))
        self.min_btn.clicked.connect(self.showMinimized)
        controls_layout.addWidget(self.min_btn)

        # Maximize/Restore
        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("winControlMax")
        self.max_btn.setFixedSize(46, 36)
        self.max_btn.setFont(QFont(Theme.MONO_FONT, 10))
        self.max_btn.clicked.connect(self._toggle_maximize)
        controls_layout.addWidget(self.max_btn)

        # Close
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("winControlClose")
        self.close_btn.setFixedSize(46, 36)
        self.close_btn.setFont(QFont(Theme.MONO_FONT, 10))
        self.close_btn.clicked.connect(self.close)
        controls_layout.addWidget(self.close_btn)

        layout.addLayout(controls_layout)

        return title_bar

    def _show_file_menu(self):
        """Show File menu below button."""
        menu = QMenu(self)
        menu.addAction("Console", self.open_console)
        menu.addSeparator()
        menu.addAction("Pause", self.pause_all)
        menu.addSeparator()
        menu.addAction("Export Keys...", self.export_keys)
        menu.addSeparator()
        menu.addAction("Quit", self.close)
        menu.exec(self.file_menu_btn.mapToGlobal(self.file_menu_btn.rect().bottomLeft()))

    def _show_agents_menu(self):
        """Show Agents menu below button."""
        menu = QMenu(self)
        menu.addAction("Register Agent...", self.register_agent)
        menu.addSeparator()
        menu.addAction("Suspend All", self.suspend_all_agents)
        menu.exec(self.agents_menu_btn.mapToGlobal(self.agents_menu_btn.rect().bottomLeft()))

    def _show_settings_menu(self):
        """Show Settings menu below button."""
        menu = QMenu(self)
        menu.addAction("Preferences...", self.show_settings)
        menu.exec(self.settings_menu_btn.mapToGlobal(self.settings_menu_btn.rect().bottomLeft()))

    def _show_help_menu(self):
        """Show Help menu below button."""
        menu = QMenu(self)
        menu.addAction("Quick Start", self.show_quick_start)
        menu.addAction("Documentation", self.open_documentation)
        menu.addSeparator()
        menu.addAction("About MultiClaw", self.show_about)
        menu.exec(self.help_menu_btn.mapToGlobal(self.help_menu_btn.rect().bottomLeft()))

    def _toggle_maximize(self):
        """Toggle between maximized and normal window state."""
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("□")
        else:
            self.showMaximized()
            self.max_btn.setText("❐")

    # --- Mouse events for dragging ---
    def mousePressEvent(self, event: QMouseEvent):
        """Start dragging if clicking on title bar."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is in title bar area (top 36px)
            if event.position().y() <= 36:
                self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle window dragging."""
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            # If maximized, restore to normal first
            if self.isMaximized():
                # Get the proportion of click position
                ratio = event.position().x() / self.width()
                self.showNormal()
                # Reposition so cursor stays at same relative position
                new_x = int(event.globalPosition().x() - self.width() * ratio)
                new_y = int(event.globalPosition().y() - 18)  # Center of title bar
                self.move(new_x, new_y)
                self._drag_pos = event.globalPosition().toPoint()
                self.max_btn.setText("□")
            else:
                diff = event.globalPosition().toPoint() - self._drag_pos
                self.move(self.pos() + diff)
                self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """End dragging."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double-click on title bar toggles maximize."""
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 36:
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)

    def _enable_dwm_shadow(self):
        """Enable Windows DWM drop shadow for frameless window."""
        import sys
        if sys.platform != 'win32':
            return

        try:
            import ctypes
            from ctypes import wintypes

            # Get the window handle
            hwnd = int(self.winId())

            # DWM constants
            DWMWA_NCRENDERING_POLICY = 2
            DWMNCRP_ENABLED = 2

            # Margins for extending frame into client area (-1 = full shadow)
            class MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]

            dwmapi = ctypes.windll.dwmapi

            # Enable non-client rendering
            policy = ctypes.c_int(DWMNCRP_ENABLED)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_NCRENDERING_POLICY,
                ctypes.byref(policy), ctypes.sizeof(policy)
            )

            # Extend frame to create shadow
            margins = MARGINS(1, 1, 1, 1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

        except Exception:
            pass  # Silently fail on non-Windows or if DWM unavailable
