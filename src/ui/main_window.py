"""
Main Window - The primary application window.

Contains the header, tabs, status bar, and system tray.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QStatusBar, QMenuBar, QMenu, QFrame, QTextEdit,
    QSystemTrayIcon, QStyle, QMessageBox, QApplication, QDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QFont, QPixmap
from typing import Optional
from datetime import datetime

from .theme import Theme
from .tabs import (
    PoliciesTab, AgentsTab, HistoryTab, WalletTab, NetworkTab, LogTab
)
from .dialogs import SettingsDialog
from models import PolicyStore
from services import agent_server, signing_service, SigningRequest
from wallet import WalletInfo
from networks import format_address
from utils import get_app_dir, get_assets_dir


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.signing_enabled = True
        self.server_running = False

        self.setWindowTitle("MultiClaw - Get a Grip on Your Agents")
        self.setMinimumSize(900, 600)

        self.create_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.header = self.create_header()
        layout.addWidget(self.header)

        self.tabs = QTabWidget()

        # Create status bar early (before signals that might trigger update_status)
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.policy_store = PolicyStore(get_app_dir())

        # Create all tabs first
        self.agents_tab = AgentsTab(self.policy_store)
        self.agents_tab.activity.connect(self.on_agent_activity)
        self.policies_tab = PoliciesTab(self.policy_store)
        self.policies_tab.policy_deleted.connect(self.on_policy_deleted)
        self.policies_tab.activity.connect(self.on_policy_activity)
        self.wallet_tab = WalletTab()
        self.wallet_tab.wallets_changed.connect(self.on_wallets_changed)
        self.wallet_tab.wallet_deleted.connect(self.on_wallet_deleted)
        self.wallet_tab.wallet_locked.connect(self.on_wallet_locked)
        self.wallet_tab.wallet_unlocked.connect(self.on_wallet_unlocked)
        self.wallet_tab.wallet_path_changed.connect(self.on_wallet_path_changed)
        self.wallet_tab.activity.connect(self.update_activity)
        self.wallet_tab.set_agents_query_fn(self._get_agents_for_address)
        self.network_tab = NetworkTab()
        self.network_tab.activity.connect(self.update_activity)
        self.network_tab.server_toggled.connect(self.on_server_toggled)
        self.network_tab.custom_port_changed.connect(self.on_custom_port_changed)
        self.network_tab.network_toggled.connect(self.on_network_toggled)
        self.network_tab.verify_settlements_changed.connect(self.on_verify_settlements_changed)
        self.network_tab.allow_lan_changed.connect(self.on_allow_lan_changed)
        self.history_tab = HistoryTab(self.policy_store)
        self.log_tab = LogTab()

        # Add tabs in desired order: Agents, Policies, Wallets, Network, History, Logs
        self.tabs.addTab(self.agents_tab, "Agents")
        self.tabs.addTab(self.policies_tab, "Policies")
        self.tabs.addTab(self.wallet_tab, "Wallet")
        self.tabs.addTab(self.network_tab, "Network")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(self.log_tab, "Logs")

        self.agents_tab.wallets = self.wallet_tab.get_wallet_list()
        self.agents_tab.get_wallet_fn = self.wallet_tab.get_unlocked_wallet

        # Load and apply settings
        self._settings = self._load_settings()
        if self._settings.get("custom_port_enabled", False):
            self.network_tab.set_custom_port_enabled(True)
        if self._settings.get("verify_settlements", False):
            self.network_tab.set_verify_settlements(True)
        if self._settings.get("allow_lan", False):
            self.network_tab.set_allow_lan(True)

        # Load custom RPC endpoints
        custom_rpcs = self._settings.get("custom_rpcs", {})
        # Convert string keys back to int (JSON serializes int keys as strings)
        custom_rpcs = {int(k): v for k, v in custom_rpcs.items()} if custom_rpcs else {}
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
            from services.logging import cleanup_old_logs
            deleted = cleanup_old_logs(log_retention)
            if deleted > 0:
                self.log_tab.add_log(f"Cleaned up {deleted} old log file(s)")

        layout.addWidget(self.tabs)

        self.update_status()

        self.setup_tray()
        self.setup_signing_service()

        # Initialize status indicators
        self.update_status_indicators()

        # Apply startup settings
        if self._settings.get("start_minimized", False):
            QTimer.singleShot(0, self.hide if self._settings.get("minimize_to_tray", False) else self.showMinimized)

        # Auto-start server if enabled
        if self._settings.get("auto_start_server", False):
            QTimer.singleShot(500, self.network_tab.toggle_server)

    def _get_agents_for_address(self, wallet_address: str) -> list:
        """Get all agents linked to a specific wallet address."""
        return [
            agent for agent in self.policy_store.get_all_agents()
            if agent.wallet_address == wallet_address
        ]

    def on_wallets_changed(self, wallets: list):
        """Handle wallet list changes from wallet tab."""
        self.agents_tab.wallets = wallets
        self.update_status()
        self.update_activity(f"Wallet list updated: {len(wallets)} address(es)")

    def on_wallet_deleted(self, wallet_address: str):
        """Handle wallet deletion - decommission any agents using this wallet."""
        decommissioned = []
        for agent in self.policy_store.get_all_agents():
            if agent.wallet_address == wallet_address:
                agent.wallet_address = None
                agent.policy_id = None
                agent.status = "uncommissioned"
                self.policy_store.update_agent(agent)
                decommissioned.append(agent.name)

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
        if running:
            self.update_activity(f"Server started on port {agent_server.port}")
        else:
            self.update_activity("Server stopped")

    def on_custom_port_changed(self, enabled: bool):
        """Handle custom port setting change from Network tab."""
        self._settings["custom_port_enabled"] = enabled
        self._save_settings()

    def on_rpc_changed(self, chain_id: int, rpc_url: str):
        """Handle custom RPC endpoint change from Network tab."""
        if "custom_rpcs" not in self._settings:
            self._settings["custom_rpcs"] = {}
        if rpc_url:
            self._settings["custom_rpcs"][str(chain_id)] = rpc_url
        else:
            self._settings["custom_rpcs"].pop(str(chain_id), None)
        self._save_settings()
        # Update wallet tab with new RPCs
        self.wallet_tab.set_custom_rpcs(self.network_tab.get_custom_rpcs())

    def on_wallet_path_changed(self, path: str):
        """Handle wallet path change - save to settings for persistence."""
        self._settings["wallet_path"] = path
        self._save_settings()

    def on_network_toggled(self, chain_id: int, enabled: bool):
        """Handle network enable/disable from Network tab."""
        from services.signing import signing_service
        signing_service.set_network_enabled(chain_id, enabled)

    def on_verify_settlements_changed(self, enabled: bool):
        """Handle verify settlements setting change from Network tab."""
        from services.signing import signing_service
        signing_service.set_verify_settlements(enabled)
        self._settings["verify_settlements"] = enabled
        self._save_settings()

    def on_allow_lan_changed(self, enabled: bool):
        """Handle allow LAN setting change from Network tab."""
        self._settings["allow_lan"] = enabled
        self._save_settings()

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
        if has_wallets and self.wallet_tab.is_unlocked:
            self.wallet_indicator.setStyleSheet(f"color: {Theme.LIME}; font-size: 12px;")
            self.wallet_label.setStyleSheet(f"color: {Theme.LIME};")
        else:
            self.wallet_indicator.setStyleSheet(f"color: {Theme.RUST}; font-size: 12px;")
            self.wallet_label.setStyleSheet(f"color: {Theme.RUST};")

        # Server indicator
        if self.server_running:
            self.server_indicator.setStyleSheet(f"color: {Theme.LIME}; font-size: 12px;")
            self.server_label.setStyleSheet(f"color: {Theme.LIME};")
        else:
            self.server_indicator.setStyleSheet(f"color: {Theme.RUST}; font-size: 12px;")
            self.server_label.setStyleSheet(f"color: {Theme.RUST};")

        # Signing indicator
        if self.signing_enabled:
            self.signing_indicator.setStyleSheet(f"color: {Theme.LIME}; font-size: 12px;")
            self.signing_label.setStyleSheet(f"color: {Theme.LIME};")
        else:
            self.signing_indicator.setStyleSheet(f"color: {Theme.RUST}; font-size: 12px;")
            self.signing_label.setStyleSheet(f"color: {Theme.RUST};")

    def _load_settings(self) -> dict:
        """Load settings from disk."""
        import json
        import logging
        from utils import get_settings_path
        settings_path = get_settings_path()
        if settings_path.exists():
            try:
                with open(settings_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to load settings: {e}")
        return {}

    def _save_settings(self):
        """Save settings to disk."""
        import json
        import logging
        from utils import get_settings_path
        settings_path = get_settings_path()
        try:
            with open(settings_path, 'w') as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to save settings: {e}")

    def update_status(self):
        """Update status bar."""
        if agent_server.is_running:
            self.status.showMessage(f"Listening on localhost:{agent_server.port}")
        else:
            self.status.showMessage("Server stopped")

    def create_header(self) -> QFrame:
        header = QFrame()
        header.setStyleSheet(f"background-color: {Theme.BLACK};")
        header.setFixedHeight(100)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        # Logo on the left
        logo_label = QLabel()
        logo_path = get_assets_dir() / "wm_stacked.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled = pixmap.scaledToHeight(57, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
        else:
            logo_label.setText("MULTICLAW")
            logo_label.setStyleSheet(f"color: {Theme.LIME}; font-weight: bold; font-size: 16px;")

        header_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_layout.addStretch()

        # Center: Three status indicators stacked vertically
        status_layout = QVBoxLayout()
        status_layout.setSpacing(2)

        # Wallet indicator
        wallet_row = QHBoxLayout()
        wallet_row.setSpacing(4)
        self.wallet_indicator = QLabel("●")
        self.wallet_indicator.setStyleSheet(f"color: {Theme.RUST}; font-size: 12px;")
        self.wallet_indicator.setFixedWidth(12)
        wallet_row.addWidget(self.wallet_indicator)
        self.wallet_label = QLabel("Wallet")
        self.wallet_label.setFont(QFont(Theme.MONO_FONT, 9))
        self.wallet_label.setStyleSheet(f"color: {Theme.RUST};")
        self.wallet_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wallet_label.mousePressEvent = lambda e: self.on_wallet_indicator_clicked()
        wallet_row.addWidget(self.wallet_label)
        status_layout.addLayout(wallet_row)

        # Server indicator
        server_row = QHBoxLayout()
        server_row.setSpacing(4)
        self.server_indicator = QLabel("●")
        self.server_indicator.setStyleSheet(f"color: {Theme.RUST}; font-size: 12px;")
        self.server_indicator.setFixedWidth(12)
        server_row.addWidget(self.server_indicator)
        self.server_label = QLabel("Server")
        self.server_label.setFont(QFont(Theme.MONO_FONT, 9))
        self.server_label.setStyleSheet(f"color: {Theme.RUST};")
        self.server_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.server_label.mousePressEvent = lambda e: self.on_server_indicator_clicked()
        server_row.addWidget(self.server_label)
        status_layout.addLayout(server_row)

        # Signing indicator
        signing_row = QHBoxLayout()
        signing_row.setSpacing(4)
        self.signing_indicator = QLabel("●")
        self.signing_indicator.setStyleSheet(f"color: {Theme.LIME}; font-size: 12px;")
        self.signing_indicator.setFixedWidth(12)
        signing_row.addWidget(self.signing_indicator)
        self.signing_label = QLabel("Signing")
        self.signing_label.setFont(QFont(Theme.MONO_FONT, 9))
        self.signing_label.setStyleSheet(f"color: {Theme.LIME};")
        self.signing_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.signing_label.mousePressEvent = lambda e: self.toggle_global_signing()
        signing_row.addWidget(self.signing_label)
        status_layout.addLayout(signing_row)

        header_layout.addLayout(status_layout)
        header_layout.addStretch()

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setFont(QFont(Theme.MONO_FONT, 9))
        self.activity_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                color: {Theme.LIME_DIM};
            }}
        """)
        self.activity_log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.activity_log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.activity_log.setMinimumWidth(450)
        self.activity_log.setMaximumHeight(76)

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

        if len(self.activity_entries) > 5:
            self.activity_entries = self.activity_entries[-5:]

        self.activity_log.setHtml("<br>".join(self.activity_entries))

        scrollbar = self.activity_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Also write to Logs tab
        self.log_tab.add_log(message)

    def update_header_balance(self):
        """Update header when balance changes - currently a no-op since wallet info moved to tab."""
        pass

    def create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
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
        """Initialize the signing service with data stores."""
        signing_service.set_stores(self.policy_store)
        signing_service.set_wallet_provider(self.wallet_tab.get_unlocked_wallet)
        agent_server.set_signing_service(signing_service)

        # Sync network enabled state from NetworkTab
        for chain_id, enabled in self.network_tab.network_enabled.items():
            signing_service.set_network_enabled(chain_id, enabled)

        # Sync verify settlements setting
        if self._settings.get("verify_settlements", False):
            signing_service.set_verify_settlements(True)

        # Apply replay window setting
        replay_window = self._settings.get("replay_window_seconds", 300)
        signing_service.set_max_request_age(replay_window)

        signing_service.activity.connect(self.update_activity)
        signing_service.approval_needed.connect(self.on_approval_needed)
        signing_service.request_signed.connect(self.on_request_signed)
        signing_service.request_rejected.connect(self.on_request_rejected)
        signing_service.transaction_updated.connect(self.on_transaction_updated)

    def on_approval_needed(self, request: SigningRequest):
        """Handle a signing request that needs manual approval."""
        self.update_activity(
            f"Approval needed: {request.agent_name} ({request.agent_code}) requests ${request.amount_micro/1_000_000:.2f} USDC",
            is_warning=True
        )

        # Show system tray notification if enabled
        if self._settings.get("toast_enabled", True):
            if hasattr(self, 'tray') and self.tray.isVisible():
                self.tray.showMessage(
                    "Payment Approval Required",
                    f"{request.agent_name} is requesting ${request.amount_micro/1_000_000:.2f} USDC",
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

        amount_str = f"${request.amount_micro/1_000_000:.2f} USDC"
        # Prefer request_url (full URL) over resource (often path-only)
        if request.request_url:
            resource_str = f"\nURL: {request.request_url}"
        elif request.resource:
            resource_str = f"\nResource: {request.resource}"
        else:
            resource_str = ""

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Payment Approval Required")
        msg.setText(f"Agent '{request.agent_name}' is requesting payment authorization.")
        msg.setInformativeText(
            f"Amount: {amount_str}\n"
            f"Network: {request.network}\n"
            f"Recipient: {format_address(request.recipient)}"
            f"{resource_str}"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.button(QMessageBox.StandardButton.Yes).setText("Approve")
        msg.button(QMessageBox.StandardButton.No).setText("Reject")

        result = msg.exec()

        if result == QMessageBox.StandardButton.Yes:
            response = signing_service.approve_request(request.id)
            if response.get("status") == "success":
                self.update_activity(f"Approved: {amount_str} for {request.agent_name}")
            else:
                self.update_activity(f"Approval failed: {response.get('error')}", is_error=True)
                QMessageBox.warning(self, "Signing Failed", response.get("error", "Unknown error"))
        else:
            signing_service.reject_request(request.id, "User rejected")
            self.update_activity(f"Rejected: {amount_str} for {request.agent_name}", is_warning=True)

    def on_request_signed(self, agent_name: str, agent_code: str, wallet_id: str, amount_micro: int):
        """Handle a successfully signed request - refresh UI only (logging done by signing service)."""
        self.agents_tab.populate_table()

    def on_request_rejected(self, agent_code: str, reason: str):
        """Handle a rejected request."""
        self.update_activity(f"Rejected request from {agent_code}: {reason}", is_warning=True)

    def on_transaction_updated(self, transaction_id: str):
        """Handle transaction status update - refresh the history tab."""
        self.history_tab.refresh()

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

    def pause_all(self):
        """Pause all activity: stop server, lock wallet, disable signing."""
        actions = []

        # Stop server if running
        if self.server_running:
            agent_server.stop()
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
            QMessageBox.information(self, "No Addresses", "No addresses to export.")
            return

        if not self.wallet_tab.is_unlocked:
            QMessageBox.warning(
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
            self._settings.update(new_settings)
            self._save_settings()

            # Apply logging settings immediately
            self.log_tab.set_retention_days(new_settings.get("log_retention_days", 0))

            # Apply auto-lock settings
            self.wallet_tab.set_auto_lock_timeout(new_settings.get("auto_lock_minutes", 0))

            # Apply replay window setting
            replay_window = new_settings.get("replay_window_seconds", 300)
            signing_service.set_max_request_age(replay_window)

    def register_agent(self):
        """Open the agent registration dialog."""
        self.tabs.setCurrentWidget(self.agents_tab)
        self.agents_tab.register_agent()

    def suspend_all_agents(self):
        """Suspend all active agents."""
        active_agents = [a for a in self.policy_store.get_all_agents() if a.status == "active"]

        if not active_agents:
            QMessageBox.information(
                self,
                "No Active Agents",
                "There are no active agents to suspend."
            )
            return

        reply = QMessageBox.question(
            self,
            "Suspend All Agents",
            f"Suspend all {len(active_agents)} active agent(s)?\n\n"
            "This will reject all signing requests until agents are reactivated.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            for agent in active_agents:
                agent.suspend()
                self.policy_store.update_agent(agent)

            self.agents_tab.populate_table()
            self.update_activity(f"Suspended {len(active_agents)} agent(s)", is_warning=True)

    def open_documentation(self):
        """Open the documentation website."""
        import webbrowser
        webbrowser.open("https://docs.primer.systems/multiclaw.html")

    def show_about(self):
        """Show the About MultiClaw dialog."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox
        from PyQt6.QtCore import Qt

        dialog = QDialog(self)
        dialog.setWindowTitle("About MultiClaw")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        # Tagline
        tagline = QLabel("MultiClaw, by Primer")
        tagline.setStyleSheet(f"font-style: italic;")
        layout.addWidget(tagline)

        # Version
        version = QLabel("Version 1.0.0")
        version.setStyleSheet(f"color: {Theme.CHARCOAL};")
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
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Quick Start")
        dialog.setMinimumWidth(480)

        layout = QVBoxLayout(dialog)
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
                hint_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
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
            if agent_server.is_running:
                agent_server.stop()
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
