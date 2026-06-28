"""
UI Dialogs - Application dialogs for agents, policies, and wallets.

Contains dialogs for:
- Agent registration and commission
- Policy creation/editing
- Wallet management
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QGroupBox, QFormLayout, QComboBox,
    QMessageBox, QCheckBox, QListWidget, QListWidgetItem,
    QDoubleSpinBox, QDialogButtonBox, QAbstractItemView,
    QApplication, QWidget, QRadioButton, QButtonGroup, QStackedWidget,
    QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from typing import Optional
from datetime import datetime

from .theme import Theme

# Clipboard auto-clear timeout (seconds)
# Security: Sensitive data (secrets, private keys, seed phrases) should not
# remain in clipboard indefinitely. Auto-clear reduces exposure window.
CLIPBOARD_CLEAR_TIMEOUT = 60


def copy_sensitive_to_clipboard(text: str, parent: QWidget = None, timeout_sec: int = CLIPBOARD_CLEAR_TIMEOUT):
    """
    Copy sensitive data to clipboard with auto-clear.

    Security: Sensitive data like agent secrets, private keys, or seed phrases
    should not remain in the clipboard indefinitely. This function:
    1. Copies the text to clipboard
    2. Schedules automatic clearing after timeout (default 60 seconds)
    3. Only clears if clipboard still contains our text (user may have copied something else)

    Args:
        text: Sensitive text to copy
        parent: Parent widget for notification dialog (optional)
        timeout_sec: Seconds before auto-clear (default: 60)
    """
    clipboard = QApplication.clipboard()
    clipboard.setText(text)

    # Schedule clipboard clear
    def clear_clipboard():
        if clipboard.text() == text:
            clipboard.clear()

    QTimer.singleShot(timeout_sec * 1000, clear_clipboard)

    # Show notification if parent available
    if parent:
        QMessageBox.information(
            parent,
            "Copied",
            f"Data copied to clipboard.\n\nClipboard will auto-clear in {timeout_sec} seconds."
        )
from ..models import SpendPolicy, Agent
from ..wallet import WalletInfo, Wallet, PrivateKeyWallet, AddressEntry
from ..networks import NETWORKS, format_address

# Type alias for wallet info objects (both old and new)
WalletInfoLike = WalletInfo | AddressEntry


# ============================================
# Agent Registration Dialog
# ============================================

class AgentRegistrationDialog(QDialog):
    """Two-page wizard for registering a new agent with configurable authentication."""

    # Pages
    PAGE_CONFIGURE = 0
    PAGE_CREDENTIALS = 1

    def __init__(self, core, parent=None):
        """
        Create agent registration dialog.

        Args:
            core: MultiClaw core instance (required)
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Register New Agent")
        self.setMinimumWidth(550)
        self.setMinimumHeight(400)

        self._core = core
        self.agent = None
        self.agent_token = None
        self.config_text = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Stacked widget for pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Create pages
        self._create_configure_page()
        self._create_credentials_page()

        # Navigation buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.action_btn = QPushButton("Generate Token")
        self.action_btn.setDefault(True)
        self.action_btn.clicked.connect(self._on_action)
        btn_layout.addWidget(self.action_btn)

        layout.addLayout(btn_layout)

        # Start on configure page
        self.stack.setCurrentIndex(self.PAGE_CONFIGURE)

    def _create_configure_page(self):
        """Page 1: Agent name and authentication mode selection."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        # Description
        desc = QLabel(
            "Register an AI agent to use with MultiClaw. Choose a name and"
            "authentication method for the agent."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(8)

        # Agent name
        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., claude-dev, research-bot")
        form.addRow("Agent Name:", self.name_input)
        layout.addLayout(form)

        layout.addSpacing(12)

        # Authentication Mode section
        auth_group = QGroupBox("Authentication Mode")
        auth_layout = QVBoxLayout(auth_group)

        self.auth_mode_group = QButtonGroup(self)

        # HMAC option (default)
        self.hmac_radio = QRadioButton("HMAC-SHA256 Signing (Recommended)")
        self.hmac_radio.setChecked(True)
        self.auth_mode_group.addButton(self.hmac_radio, 0)
        auth_layout.addWidget(self.hmac_radio)

        hmac_desc = QLabel(
            "Agent signs each request with a shared secret. The secret is never "
            "transmitted—only proof of knowing it. More secure but requires signing code."
        )
        hmac_desc.setWordWrap(True)
        hmac_desc.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px; margin-left: 20px;")
        auth_layout.addWidget(hmac_desc)

        auth_layout.addSpacing(12)

        # Bearer option
        self.bearer_radio = QRadioButton("Bearer Token (Simple)")
        self.auth_mode_group.addButton(self.bearer_radio, 1)
        auth_layout.addWidget(self.bearer_radio)

        bearer_desc = QLabel(
            "Agent sends the token directly with requests. Simpler for agents that "
            "struggle with signing, but the token is transmitted with every request."
        )
        bearer_desc.setWordWrap(True)
        bearer_desc.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px; margin-left: 20px;")
        auth_layout.addWidget(bearer_desc)

        # Security warning for bearer
        self.bearer_warning = QLabel(
            "⚠️ Less secure: Anyone who intercepts the token can impersonate this agent."
        )
        self.bearer_warning.setWordWrap(True)
        self.bearer_warning.setStyleSheet("color: #B7410E; font-size: 11px; margin-left: 20px; padding-bottom: 2px;")
        self.bearer_warning.setVisible(False)
        auth_layout.addWidget(self.bearer_warning)

        # Show/hide warning based on selection
        self.bearer_radio.toggled.connect(self.bearer_warning.setVisible)

        layout.addWidget(auth_group)

        layout.addStretch()
        self.stack.addWidget(page)

    def _create_credentials_page(self):
        """Page 2: Generated token display."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        # Title
        title = QLabel("Agent Credentials")
        title.setFont(QFont("", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        # Description
        desc = QLabel("Copy this configuration to your agent's environment:")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(4)

        # Config display - more space now that it has the full page
        self.config_display = QTextEdit()
        self.config_display.setReadOnly(True)
        self.config_display.setFont(QFont(Theme.MONO_FONT, 10))
        self.config_display.setMinimumHeight(140)
        layout.addWidget(self.config_display)

        # Copy button row
        copy_row = QHBoxLayout()
        copy_row.addStretch()

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setFixedWidth(140)
        copy_btn.clicked.connect(self._copy_config)
        copy_row.addWidget(copy_btn)

        layout.addLayout(copy_row)

        layout.addSpacing(8)

        # Port note
        port_note = QLabel(
            "Note: If you change the server port, update MULTICLAW_URL in your agent configuration."
        )
        port_note.setWordWrap(True)
        port_note.setStyleSheet(f"color: {Theme.CHARCOAL}; font-style: italic;")
        layout.addWidget(port_note)

        layout.addSpacing(8)

        # Warning
        warning = QLabel(
            "⚠️ Save this configuration now! The token cannot be retrieved later."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #B7410E; font-weight: bold;")
        layout.addWidget(warning)

        layout.addStretch()
        self.stack.addWidget(page)

    def keyPressEvent(self, event):
        """Handle key presses - prevent Enter from closing dialog on page 1."""
        from PyQt6.QtCore import Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Handle Enter explicitly via action button logic
            self._on_action()
            return  # Don't propagate to QDialog default handling
        super().keyPressEvent(event)

    def _on_action(self):
        """Handle action button click based on current page."""
        if self.stack.currentIndex() == self.PAGE_CONFIGURE:
            self._generate_token()
        else:
            self._register_agent()

    def _generate_token(self):
        """Generate authentication credentials via core and move to credentials page."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Agent name is required.")
            return

        # Check for duplicate name using core
        for agent in self._core.get_all_agents():
            if agent.name == name:
                QMessageBox.warning(self, "Duplicate Name", f"Agent name '{name}' already exists.")
                return

        # Determine auth mode
        auth_mode = "hmac" if self.hmac_radio.isChecked() else "bearer"

        # Create agent via core - this handles all the crypto
        try:
            self.agent, self.agent_token = self._core.create_agent(name, auth_mode)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create agent: {e}")
            return

        # Build config text
        self.config_text = f"""I have set up a local service called MultiClaw that I want you to interact with. You can use this to handle x402 payments on my behalf.

Usage instructions are at http://localhost:9402/agent
Familiarise yourself with the instructions now, and use them any time you encounter a HTTP 402 (Payment Required) response.

Your credentials:
MULTICLAW_AGENT_ID={self.agent.id}
MULTICLAW_AGENT_TOKEN={self.agent_token}
MULTICLAW_AUTH_MODE={auth_mode}
MULTICLAW_URL=http://localhost:9402"""

        self.config_display.setPlainText(self.config_text)

        # Move to credentials page
        self.stack.setCurrentIndex(self.PAGE_CREDENTIALS)
        self.action_btn.setText("Done")

    def _copy_config(self):
        """Copy configuration to clipboard."""
        if self.config_text:
            QApplication.clipboard().setText(self.config_text)
            QMessageBox.information(self, "Copied", "Agent configuration copied to clipboard.")

    def _register_agent(self):
        """Complete registration - agent already created via core."""
        # Agent was created when Generate Token was clicked
        # Just close the dialog
        self.accept()

    def get_agent(self) -> Agent:
        """Return the created agent."""
        return self.agent


# ============================================
# Commission Dialog
# ============================================

class CommissionDialog(QDialog):
    """Dialog for commissioning an agent with a spend policy and signing address."""

    def __init__(
        self,
        agent: Agent,
        core,
        wallets: list[WalletInfoLike] = None,
        get_wallet_fn=None,
        parent=None
    ):
        """
        Args:
            agent: Agent to commission
            core: MultiClaw core instance
            wallets: List of available wallet addresses
            get_wallet_fn: Function to get unlocked wallet by address
            parent: Parent widget
        """
        super().__init__(parent)
        self.agent = agent
        self.core = core
        self.wallets = wallets or []
        self.get_wallet_fn = get_wallet_fn  # Function to get unlocked wallet by address
        self.selected_policy: Optional[SpendPolicy] = None
        self.selected_wallet_address: Optional[str] = None
        self.wallet_sort_by_id = True
        self.generated_mandate: Optional[dict] = None

        self.setWindowTitle(f"Commission Agent: {agent.name}")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        desc = QLabel(
            "Select a spend policy and signing address to enable this agent. "
            "The agent will sign payments using the linked address."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(12)

        policy_label = QLabel("Spend Policy:")
        layout.addWidget(policy_label)

        self.policy_combo = QComboBox()
        policies = self.core.get_all_policies()

        if not policies:
            self.policy_combo.addItem("No policies available", None)
            self.policy_combo.setEnabled(False)
        else:
            self.policy_combo.addItem("Select a policy...", None)
            for policy in policies:
                self.policy_combo.addItem(policy.name, policy.id)

        self.policy_combo.currentIndexChanged.connect(self.on_selection_changed)
        layout.addWidget(self.policy_combo)

        self.policy_details = QWidget()
        details_layout = QVBoxLayout(self.policy_details)
        details_layout.setContentsMargins(8, 4, 8, 4)
        details_layout.setSpacing(2)

        self.detail_networks = QLabel("Networks: —")
        self.detail_networks.setStyleSheet(f"color: {Theme.CHARCOAL};")
        details_layout.addWidget(self.detail_networks)

        self.detail_limits = QLabel("Limits: —")
        self.detail_limits.setStyleSheet(f"color: {Theme.CHARCOAL};")
        details_layout.addWidget(self.detail_limits)

        self.detail_domains = QLabel("Domains: —")
        self.detail_domains.setStyleSheet(f"color: {Theme.CHARCOAL};")
        details_layout.addWidget(self.detail_domains)

        policy_hint = QLabel("See Policies tab for more information.")
        policy_hint.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px; font-style: italic;")
        details_layout.addWidget(policy_hint)

        layout.addWidget(self.policy_details)

        layout.addSpacing(8)

        wallet_header = QHBoxLayout()
        wallet_label = QLabel("Signing Address:")
        wallet_header.addWidget(wallet_label)

        wallet_header.addStretch()

        sort_label = QLabel("Sort:")
        sort_label.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px;")
        wallet_header.addWidget(sort_label)

        self.sort_id_btn = QPushButton("ID")
        self.sort_id_btn.setMaximumWidth(40)
        self.sort_id_btn.setStyleSheet("font-size: 10px; font-weight: bold;")
        self.sort_id_btn.clicked.connect(lambda: self.sort_wallets(by_id=True))
        wallet_header.addWidget(self.sort_id_btn)

        self.sort_name_btn = QPushButton("Name")
        self.sort_name_btn.setMaximumWidth(50)
        self.sort_name_btn.setStyleSheet("font-size: 10px;")
        self.sort_name_btn.clicked.connect(lambda: self.sort_wallets(by_id=False))
        wallet_header.addWidget(self.sort_name_btn)

        layout.addLayout(wallet_header)

        self.wallet_list = QListWidget()
        self.wallet_list.setMaximumHeight(150)
        self.wallet_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.wallet_list.itemSelectionChanged.connect(self.on_wallet_selected)
        self.wallet_list.setFont(QFont(Theme.MONO_FONT, 9))

        if self.wallets:
            self.populate_wallet_list()
        else:
            self.wallet_list.setEnabled(False)
            item = QListWidgetItem("No addresses available")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.wallet_list.addItem(item)

        layout.addWidget(self.wallet_list)

        # AP2 Intent Mandate generation option
        layout.addSpacing(8)

        ap2_group = QGroupBox("AP2 Integration (Optional)")
        ap2_layout = QVBoxLayout(ap2_group)

        self.generate_mandate_checkbox = QCheckBox("Generate Intent Mandate VDC")
        self.generate_mandate_checkbox.setToolTip(
            "Generate an AP2-compatible Verifiable Digital Credential documenting "
            "this agent's authorization to make payments within the policy limits."
        )
        self.generate_mandate_checkbox.stateChanged.connect(self._on_mandate_checkbox_changed)
        ap2_layout.addWidget(self.generate_mandate_checkbox)

        # Registry upload option (enabled only when mandate generation is checked)
        self.upload_registry_checkbox = QCheckBox("Upload to AP2 Registry")
        self.upload_registry_checkbox.setEnabled(False)
        self.upload_registry_checkbox.setToolTip(
            "Publish the Intent Mandate to the MultiClaw AP2 Registry for external verification. "
            "Merchants can verify this agent's authorization at ap2.primer.systems"
        )
        ap2_layout.addWidget(self.upload_registry_checkbox)

        mandate_note = QLabel(
            "An Intent Mandate is a cryptographically signed document that external"
            "parties can use to verify this agent's spending authorization."
        )
        mandate_note.setWordWrap(True)
        mandate_note.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px;")
        ap2_layout.addWidget(mandate_note)

        layout.addWidget(ap2_group)

        self.no_policy_warning = QLabel(
            "⚠️ No spend policies exist. Create a policy in the Policies tab first."
        )
        self.no_policy_warning.setWordWrap(True)
        self.no_policy_warning.setStyleSheet("color: #B7410E;")
        self.no_policy_warning.setVisible(not policies)
        layout.addWidget(self.no_policy_warning)

        self.no_wallet_warning = QLabel(
            "⚠️ No addresses available. Add an address in the Wallet tab first."
        )
        self.no_wallet_warning.setWordWrap(True)
        self.no_wallet_warning.setStyleSheet("color: #B7410E;")
        self.no_wallet_warning.setVisible(not self.wallets)
        layout.addWidget(self.no_wallet_warning)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.commission_btn = QPushButton("Commission Agent")
        self.commission_btn.setEnabled(False)
        self.commission_btn.clicked.connect(self.commission)
        btn_layout.addWidget(self.commission_btn)

        layout.addLayout(btn_layout)

    def populate_wallet_list(self):
        """Populate the wallet list, sorted by current sort order."""
        self.wallet_list.clear()
        # Support both WalletInfo (wallet_id) and AddressEntry (id)
        def get_id(w):
            return getattr(w, 'wallet_id', None) or getattr(w, 'id', '')
        sorted_wallets = sorted(
            self.wallets,
            key=lambda w: get_id(w) if self.wallet_sort_by_id else w.name.lower()
        )
        for wallet_info in sorted_wallets:
            addr_short = format_address(wallet_info.address)
            entry_id = get_id(wallet_info)
            item = QListWidgetItem(f"{entry_id}  {wallet_info.name}  ({addr_short})")
            item.setData(Qt.ItemDataRole.UserRole, wallet_info.address)
            self.wallet_list.addItem(item)

    def sort_wallets(self, by_id: bool):
        """Sort the wallet list by ID or name."""
        self.wallet_sort_by_id = by_id
        if by_id:
            self.sort_id_btn.setStyleSheet("font-size: 10px; font-weight: bold;")
            self.sort_name_btn.setStyleSheet("font-size: 10px;")
        else:
            self.sort_id_btn.setStyleSheet("font-size: 10px;")
            self.sort_name_btn.setStyleSheet("font-size: 10px; font-weight: bold;")
        current_addr = self.selected_wallet_address
        self.populate_wallet_list()
        if current_addr:
            for i in range(self.wallet_list.count()):
                item = self.wallet_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == current_addr:
                    self.wallet_list.setCurrentItem(item)
                    break

    def on_wallet_selected(self):
        """Handle wallet selection from list."""
        selected = self.wallet_list.currentItem()
        if selected:
            self.selected_wallet_address = selected.data(Qt.ItemDataRole.UserRole)
        else:
            self.selected_wallet_address = None
        self.update_commission_button()

    def on_selection_changed(self, index: int = 0):
        """Handle policy selection change."""
        policy_id = self.policy_combo.currentData()

        if policy_id:
            policy = self.core.get_policy(policy_id)
            if policy:
                self.selected_policy = policy

                network_names = []
                for chain_id in policy.networks:
                    network = NETWORKS.get(chain_id)
                    if network:
                        network_names.append(network.display_name)
                self.detail_networks.setText(f"Networks: {', '.join(network_names) or 'None'}")

                daily = policy.format_daily_limit()
                per_req = policy.format_per_request_max()
                auto = policy.format_auto_approve()
                self.detail_limits.setText(f"Limits: {daily} daily / {per_req} txn / {auto} approval")

                domains = policy.format_domain_restrictions()
                self.detail_domains.setText(f"Domains: {domains}")
        else:
            self.selected_policy = None
            self.detail_networks.setText("Networks: —")
            self.detail_limits.setText("Limits: —")
            self.detail_domains.setText("Domains: —")

        self.update_commission_button()

    def update_commission_button(self):
        """Enable commission button only if both policy and wallet are selected."""
        policy_id = self.policy_combo.currentData()
        can_commission = policy_id is not None and self.selected_wallet_address is not None
        self.commission_btn.setEnabled(can_commission)

    def _on_mandate_checkbox_changed(self, state: int):
        """Enable/disable registry upload based on mandate generation checkbox."""
        self.upload_registry_checkbox.setEnabled(state == Qt.CheckState.Checked.value)

    def commission(self):
        """Commission the agent with selected policy and wallet."""
        if not self.selected_policy or not self.selected_wallet_address:
            return

        # Generate IntentMandate if requested - all through core
        mandate = None
        if self.generate_mandate_checkbox.isChecked():
            mandate = self.core.generate_intent_mandate(
                agent_code=self.agent.code,
                policy_id=self.selected_policy.id,
                wallet_address=self.selected_wallet_address,
                sign=True  # Request signing if wallet is unlocked
            )
            self.generated_mandate = mandate

            # Upload to registry if requested (UI operation - shows message box)
            if self.upload_registry_checkbox.isChecked():
                self._upload_to_registry(mandate)

        # Single call to core - core handles agent state changes
        self.core.commission_agent(
            agent_code=self.agent.code,
            policy_id=self.selected_policy.id,
            wallet_address=self.selected_wallet_address,
            intent_mandate=mandate
        )
        self.accept()

    def get_policy_id(self) -> Optional[str]:
        """Return the selected policy ID."""
        return self.selected_policy.id if self.selected_policy else None

    def get_intent_mandate(self) -> Optional[dict]:
        """Return the generated Intent Mandate, if any."""
        return self.generated_mandate

    def _upload_to_registry(self, mandate: dict) -> bool:
        """
        Upload the Intent Mandate to the AP2 Registry.

        Returns True on success, False on failure.
        """
        result = self.core.upload_mandate_to_registry(mandate)

        if result.get("success"):
            # Store registry info on the mandate
            self.generated_mandate["registryId"] = result["mandate_id"]
            self.generated_mandate["registryUrl"] = result["viewer_url"]

            # Show success message with clickable link
            msg = QMessageBox(self)
            msg.setWindowTitle("Mandate Published")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText("Intent Mandate uploaded to AP2 Registry.")
            msg.setInformativeText(
                f"<a href='{result['viewer_url']}'>{result['viewer_url']}</a>"
            )
            msg.setTextFormat(Qt.TextFormat.RichText)
            msg.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            msg.exec()
            return True
        else:
            QMessageBox.warning(
                self,
                "Registry Upload Failed",
                f"Could not upload Intent Mandate to registry.\n\n"
                f"{result.get('error', 'Unknown error')}\n"
                f"The mandate was generated locally but not published."
            )
            return False


# ============================================
# Edit Agent Dialog
# ============================================

class EditAgentDialog(QDialog):
    """Dialog for editing an agent's policy and signing address assignment."""

    def __init__(self, agent: Agent, core, wallets: list[WalletInfoLike] = None, parent=None):
        """
        Args:
            agent: Agent to edit
            core: MultiClaw core instance
            wallets: List of available wallet addresses
            parent: Parent widget
        """
        super().__init__(parent)
        self.agent = agent
        self.core = core
        self.wallets = wallets or []
        self.selected_policy_id: Optional[str] = agent.policy_id
        self.selected_wallet_address: Optional[str] = agent.wallet_address
        self.wallet_sort_by_id = True

        self.setWindowTitle(f"Edit Agent: {agent.name}")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        desc = QLabel(
            "Change the agent's spend policy or signing address. "
            "Removing either will decommission the agent."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Agent info
        info_group = QGroupBox("Agent Info")
        info_layout = QFormLayout(info_group)
        info_layout.addRow("ID:", QLabel(agent.id))
        info_layout.addRow("Status:", QLabel(agent.status))
        info_layout.addRow("Spent Today:", QLabel(agent.format_spent_today()))
        layout.addWidget(info_group)

        layout.addSpacing(8)

        # Policy selection
        policy_label = QLabel("Spend Policy:")
        layout.addWidget(policy_label)

        self.policy_combo = QComboBox()
        policies = self.core.get_all_policies()

        self.policy_combo.addItem("None (decommission)", None)
        for policy in policies:
            self.policy_combo.addItem(policy.name, policy.id)
            if policy.id == agent.policy_id:
                self.policy_combo.setCurrentIndex(self.policy_combo.count() - 1)

        self.policy_combo.currentIndexChanged.connect(self.on_policy_changed)
        layout.addWidget(self.policy_combo)

        # Policy details
        self.policy_details = QWidget()
        details_layout = QVBoxLayout(self.policy_details)
        details_layout.setContentsMargins(8, 4, 8, 4)
        details_layout.setSpacing(2)

        self.detail_networks = QLabel("Networks: —")
        self.detail_networks.setStyleSheet(f"color: {Theme.CHARCOAL};")
        details_layout.addWidget(self.detail_networks)

        self.detail_limits = QLabel("Limits: —")
        self.detail_limits.setStyleSheet(f"color: {Theme.CHARCOAL};")
        details_layout.addWidget(self.detail_limits)

        self.detail_domains = QLabel("Domains: —")
        self.detail_domains.setStyleSheet(f"color: {Theme.CHARCOAL};")
        details_layout.addWidget(self.detail_domains)

        layout.addWidget(self.policy_details)

        # Show current policy details
        self.on_policy_changed()

        layout.addSpacing(8)

        # Wallet selection
        wallet_header = QHBoxLayout()
        wallet_label = QLabel("Signing Address:")
        wallet_header.addWidget(wallet_label)

        wallet_header.addStretch()

        sort_label = QLabel("Sort:")
        sort_label.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px;")
        wallet_header.addWidget(sort_label)

        self.sort_id_btn = QPushButton("ID")
        self.sort_id_btn.setMaximumWidth(40)
        self.sort_id_btn.setStyleSheet("font-size: 10px; font-weight: bold;")
        self.sort_id_btn.clicked.connect(lambda: self.sort_wallets(by_id=True))
        wallet_header.addWidget(self.sort_id_btn)

        self.sort_name_btn = QPushButton("Name")
        self.sort_name_btn.setMaximumWidth(50)
        self.sort_name_btn.setStyleSheet("font-size: 10px;")
        self.sort_name_btn.clicked.connect(lambda: self.sort_wallets(by_id=False))
        wallet_header.addWidget(self.sort_name_btn)

        layout.addLayout(wallet_header)

        self.wallet_list = QListWidget()
        self.wallet_list.setMaximumHeight(120)
        self.wallet_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.wallet_list.itemSelectionChanged.connect(self.on_wallet_selected)
        self.wallet_list.setFont(QFont(Theme.MONO_FONT, 9))

        # Add "None" option at the top
        none_item = QListWidgetItem("(None - decommission)")
        none_item.setData(Qt.ItemDataRole.UserRole, None)
        self.wallet_list.addItem(none_item)

        if self.wallets:
            self.populate_wallet_list()
        else:
            item = QListWidgetItem("No addresses available")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.wallet_list.addItem(item)

        # Select current wallet
        self.select_current_wallet()

        layout.addWidget(self.wallet_list)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()

        # View Instructions button
        self.instructions_btn = QPushButton("View Instructions")
        self.instructions_btn.clicked.connect(self._show_instructions)
        btn_layout.addWidget(self.instructions_btn)

        # Mandate button - shows "Create Mandate" or "View Mandate" based on state
        self.mandate_btn = QPushButton()
        self._update_mandate_button()
        btn_layout.addWidget(self.mandate_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self.save_changes)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def populate_wallet_list(self):
        """Populate the wallet list (excluding the None item at index 0)."""
        # Remove all items except the first (None)
        while self.wallet_list.count() > 1:
            self.wallet_list.takeItem(1)

        # Support both WalletInfo (wallet_id) and AddressEntry (id)
        def get_id(w):
            return getattr(w, 'wallet_id', None) or getattr(w, 'id', '')
        sorted_wallets = sorted(
            self.wallets,
            key=lambda w: get_id(w) if self.wallet_sort_by_id else w.name.lower()
        )
        for wallet_info in sorted_wallets:
            addr_short = format_address(wallet_info.address)
            entry_id = get_id(wallet_info)
            item = QListWidgetItem(f"{entry_id}  {wallet_info.name}  ({addr_short})")
            item.setData(Qt.ItemDataRole.UserRole, wallet_info.address)
            self.wallet_list.addItem(item)

    def select_current_wallet(self):
        """Select the current wallet in the list."""
        if self.selected_wallet_address is None:
            self.wallet_list.setCurrentRow(0)  # Select "None"
        else:
            for i in range(self.wallet_list.count()):
                item = self.wallet_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == self.selected_wallet_address:
                    self.wallet_list.setCurrentItem(item)
                    break

    def sort_wallets(self, by_id: bool):
        """Sort the wallet list by ID or name."""
        self.wallet_sort_by_id = by_id
        if by_id:
            self.sort_id_btn.setStyleSheet("font-size: 10px; font-weight: bold;")
            self.sort_name_btn.setStyleSheet("font-size: 10px;")
        else:
            self.sort_id_btn.setStyleSheet("font-size: 10px;")
            self.sort_name_btn.setStyleSheet("font-size: 10px; font-weight: bold;")
        current_addr = self.selected_wallet_address
        self.populate_wallet_list()
        self.select_current_wallet()

    def on_wallet_selected(self):
        """Handle wallet selection from list."""
        selected = self.wallet_list.currentItem()
        if selected:
            self.selected_wallet_address = selected.data(Qt.ItemDataRole.UserRole)
        else:
            self.selected_wallet_address = None

    def on_policy_changed(self):
        """Handle policy selection change."""
        policy_id = self.policy_combo.currentData()
        self.selected_policy_id = policy_id

        if policy_id:
            policy = self.core.get_policy(policy_id)
            if policy:
                network_names = []
                for chain_id in policy.networks:
                    network = NETWORKS.get(chain_id)
                    if network:
                        network_names.append(network.display_name)
                self.detail_networks.setText(f"Networks: {', '.join(network_names) or 'None'}")

                daily = policy.format_daily_limit()
                per_req = policy.format_per_request_max()
                auto = policy.format_auto_approve()
                self.detail_limits.setText(f"Limits: {daily} daily / {per_req} txn / {auto} approval")

                domains = policy.format_domain_restrictions()
                self.detail_domains.setText(f"Domains: {domains}")
                return

        self.detail_networks.setText("Networks: —")
        self.detail_limits.setText("Limits: —")
        self.detail_domains.setText("Domains: —")

    def save_changes(self):
        """Save the agent changes."""
        # Determine new status
        if self.selected_policy_id and self.selected_wallet_address:
            # Has both - keep active or activate
            if self.agent.status == "uncommissioned":
                self.agent.status = "active"
            # If suspended, leave suspended
            # If limit_reached, leave limit_reached
        else:
            # Missing one or both - decommission
            self.agent.status = "uncommissioned"

        self.agent.policy_id = self.selected_policy_id
        self.agent.wallet_address = self.selected_wallet_address
        self.accept()

    def _show_instructions(self):
        """Show the agent instructions dialog."""
        dialog = ViewInstructionsDialog(self.agent, self.core, parent=self)
        dialog.exec()

    def get_changes(self) -> tuple[Optional[str], Optional[str]]:
        """Return the new policy_id and wallet_address."""
        return self.selected_policy_id, self.selected_wallet_address

    def _update_mandate_button(self):
        """Update the mandate button text and handler based on current state."""
        # Disconnect any existing connections
        try:
            self.mandate_btn.clicked.disconnect()
        except TypeError:
            pass  # No connections to disconnect

        if self.agent.intent_mandate:
            self.mandate_btn.setText("View Mandate")
            self.mandate_btn.setToolTip("View the agent's Intent Mandate")
            self.mandate_btn.clicked.connect(self._view_mandate)
            self.mandate_btn.setEnabled(True)
        else:
            # Can only create mandate if agent is commissioned (has policy and wallet)
            can_create = self.agent.policy_id is not None and self.agent.wallet_address is not None
            self.mandate_btn.setText("Create Mandate")
            if can_create:
                self.mandate_btn.setToolTip("Generate an Intent Mandate for this agent")
                self.mandate_btn.clicked.connect(self._create_mandate)
                self.mandate_btn.setEnabled(True)
            else:
                self.mandate_btn.setToolTip("Agent must be commissioned first (assign policy and wallet)")
                self.mandate_btn.setEnabled(False)

    def _view_mandate(self):
        """Show the mandate viewer dialog."""
        # Get current policy to check for staleness
        current_policy = self.core.get_policy(self.agent.policy_id) if self.agent.policy_id else None
        dialog = MandateViewerDialog(self.agent, current_policy, self)
        dialog.exec()
        # If mandate was revoked, update button state
        if dialog.was_revoked():
            self._mandate_revoked = True
            self._update_mandate_button()

    def _create_mandate(self):
        """Create a new Intent Mandate for this agent."""
        policy = self.core.get_policy(self.agent.policy_id)
        if not policy:
            QMessageBox.warning(self, "Error", "Cannot create mandate: policy not found")
            return

        # Ask about publishing to registry
        reply = QMessageBox.question(
            self,
            "Create Intent Mandate",
            "Generate an Intent Mandate for this agent?\n\n"
            "This documents the authorization granted to this agent under the current policy.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Generate and set mandate through core
        mandate = self.core.generate_intent_mandate(
            agent_code=self.agent.code,
            policy_id=self.agent.policy_id,
            wallet_address=self.agent.wallet_address,
            sign=False  # Unsigned mandate
        )
        self.core.set_agent_mandate(self.agent.code, mandate)

        # Update local copy for display
        self.agent.intent_mandate = mandate
        self._mandate_created = True

        QMessageBox.information(
            self,
            "Mandate Created",
            f"Intent Mandate generated successfully.\n\nID: {mandate.get('id', 'unknown')[:8]}..."
        )

        # Update button to show "View Mandate" now
        self._update_mandate_button()

    def was_mandate_revoked(self) -> bool:
        """Return True if the mandate was revoked during this dialog session."""
        return getattr(self, '_mandate_revoked', False)

    def was_mandate_created(self) -> bool:
        """Return True if a mandate was created during this dialog session."""
        return getattr(self, '_mandate_created', False)


# ============================================
# View Instructions Dialog
# ============================================

class ViewInstructionsDialog(QDialog):
    """Dialog for viewing agent credentials and setup instructions."""

    def __init__(self, agent: Agent, core, parent=None):
        """
        Args:
            agent: Agent to show instructions for
            core: MultiClaw core instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.agent = agent
        self.core = core

        self.setWindowTitle(f"Agent Instructions: {agent.name}")
        self.setMinimumWidth(550)
        self.setMinimumHeight(350)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("Agent Credentials")
        title.setFont(QFont("", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        # Description
        desc = QLabel("Copy this configuration to your agent's environment:")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(4)

        # Config display
        self.config_display = QTextEdit()
        self.config_display.setReadOnly(True)
        self.config_display.setFont(QFont(Theme.MONO_FONT, 10))
        self.config_display.setMinimumHeight(140)
        layout.addWidget(self.config_display)

        # Copy button row
        copy_row = QHBoxLayout()
        copy_row.addStretch()

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setFixedWidth(140)
        self.copy_btn.clicked.connect(self._copy_config)
        copy_row.addWidget(self.copy_btn)

        layout.addLayout(copy_row)

        layout.addSpacing(8)

        # Port note
        port_note = QLabel(
            "Note: If you change the server port, update MULTICLAW_URL in your agent configuration."
        )
        port_note.setWordWrap(True)
        port_note.setStyleSheet(f"color: {Theme.CHARCOAL}; font-style: italic;")
        layout.addWidget(port_note)

        layout.addSpacing(8)

        # Status/warning area (varies by auth mode and state)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Regenerate button (only for Bearer mode)
        self.regenerate_btn = QPushButton("Regenerate Token")
        self.regenerate_btn.setVisible(False)
        self.regenerate_btn.clicked.connect(self._regenerate_token)
        layout.addWidget(self.regenerate_btn)

        layout.addStretch()

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        # Load credentials and populate display
        self._load_credentials()

    def _load_credentials(self):
        """Load credentials from core and populate the display."""
        try:
            agent_id, token, auth_mode = self.core.get_agent_credentials(self.agent.code)
        except Exception as e:
            self.config_display.setPlainText(f"Error loading credentials: {e}")
            return

        if auth_mode == "hmac":
            if token:
                # HMAC with decrypted secret
                self._show_hmac_credentials(agent_id, token)
            else:
                # HMAC but wallet locked or decryption failed
                self._show_hmac_locked(agent_id)
        else:
            # Bearer mode - token is unrecoverable
            self._show_bearer_credentials(agent_id)

    def _build_config_text(self, agent_id: str, token: str, auth_mode: str) -> str:
        """Build the configuration snippet text."""
        return f"""I have set up a local service called MultiClaw that I want you to interact with. You can use this to handle x402 payments on my behalf.

Usage instructions are at http://localhost:9402/agent
Familiarise yourself with the instructions now, and use them any time you encounter a HTTP 402 (Payment Required) response.

Your credentials:
MULTICLAW_AGENT_ID={agent_id}
MULTICLAW_AGENT_TOKEN={token}
MULTICLAW_AUTH_MODE={auth_mode}
MULTICLAW_URL=http://localhost:9402"""

    def _show_hmac_credentials(self, agent_id: str, token: str):
        """Show full HMAC credentials with the decrypted secret."""
        config_text = self._build_config_text(agent_id, token, "hmac")
        self.config_display.setPlainText(config_text)

        self.status_label.setText(
            "This is your agent's HMAC signing secret. Keep it secure."
        )
        self.status_label.setStyleSheet(f"color: {Theme.CHARCOAL}; font-style: italic;")

        self.regenerate_btn.setVisible(False)
        self.copy_btn.setEnabled(True)
        self._current_config = config_text

    def _show_hmac_locked(self, agent_id: str):
        """Show HMAC credentials with placeholder when wallet is locked."""
        config_text = self._build_config_text(agent_id, "<unlock wallet to view>", "hmac")
        self.config_display.setPlainText(config_text)

        self.status_label.setText(
            "Unlock the wallet to view the HMAC signing secret."
        )
        self.status_label.setStyleSheet("color: #B7410E;")

        self.regenerate_btn.setVisible(False)
        self.copy_btn.setEnabled(False)
        self._current_config = None

    def _show_bearer_credentials(self, agent_id: str):
        """Show Bearer credentials with unrecoverable token notice."""
        config_text = self._build_config_text(agent_id, "<token not recoverable>", "bearer")
        self.config_display.setPlainText(config_text)

        self.status_label.setText(
            "Bearer tokens cannot be retrieved after creation. "
            "You can regenerate a new token, which will invalidate the old one."
        )
        self.status_label.setStyleSheet("color: #B7410E;")

        self.regenerate_btn.setVisible(True)
        self.copy_btn.setEnabled(False)
        self._current_config = None

    def _copy_config(self):
        """Copy configuration to clipboard with auto-clear for security."""
        if hasattr(self, '_current_config') and self._current_config:
            copy_sensitive_to_clipboard(self._current_config, self)

    def _regenerate_token(self):
        """Regenerate Bearer token after confirmation."""
        reply = QMessageBox.warning(
            self,
            "Regenerate Token",
            "This will create a new token and immediately invalidate the old one.\n\n"
            "Any agents using the old token will stop working until updated.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            new_token = self.core.regenerate_agent_token(self.agent.code)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to regenerate token: {e}")
            return

        # Show the new token
        config_text = self._build_config_text(self.agent.id, new_token, "bearer")
        self.config_display.setPlainText(config_text)

        self.status_label.setText(
            "New token generated. Copy it now - it cannot be retrieved later."
        )
        self.status_label.setStyleSheet("color: #228B22; font-weight: bold;")

        self.copy_btn.setEnabled(True)
        self._current_config = config_text

        QMessageBox.information(
            self,
            "Token Regenerated",
            "A new Bearer token has been generated.\n\n"
            "Copy the configuration now and update your agent."
        )


# ============================================
# New Policy Dialog
# ============================================

class NewPolicyDialog(QDialog):
    """Dialog for creating or editing a spend policy."""

    def __init__(self, parent=None, policy: SpendPolicy = None, core=None):
        """
        Args:
            parent: Parent widget
            policy: Existing policy to edit (None for new policy)
            core: MultiClaw core instance (required for validation)
        """
        super().__init__(parent)
        self.existing_policy = policy
        self._core = core

        if policy:
            self.setWindowTitle("Edit Spend Policy")
        else:
            self.setWindowTitle("New Spend Policy")

        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Low Spend, High Limit")
        if policy:
            self.name_input.setText(policy.name)
        layout.addRow("Name:", self.name_input)

        networks_group = QGroupBox("Allowed Networks")
        networks_grid = QGridLayout(networks_group)
        networks_grid.setHorizontalSpacing(16)
        self.network_checkboxes: dict[int, QCheckBox] = {}

        # Grid positions: (chain_id) -> (row, col)
        # Row 0 = mainnets, Row 1 = testnets
        # Col 0 = Ethereum, Col 1 = Base, Col 2 = SKALE
        grid_positions = {
            1: (0, 0),           # Ethereum
            11155111: (1, 0),    # Ethereum Sepolia
            8453: (0, 1),        # Base
            84532: (1, 1),       # Base Sepolia
            1187947933: (0, 2),  # SKALE Base
            324705682: (1, 2),   # SKALE Base Sepolia
        }

        for chain_id, network in NETWORKS.items():
            checkbox = QCheckBox(network.display_name)
            if policy:
                checkbox.setChecked(chain_id in policy.networks)
            self.network_checkboxes[chain_id] = checkbox
            row, col = grid_positions.get(chain_id, (0, 0))
            networks_grid.addWidget(checkbox, row, col)

        layout.addRow(networks_group)

        daily_label = QLabel("Daily Limit:")
        self.daily_limit_input = QDoubleSpinBox()
        self.daily_limit_input.setRange(0.000001, 100000)
        self.daily_limit_input.setDecimals(6)
        self.daily_limit_input.setValue(10.0 if not policy else policy.daily_limit_micro / 1_000_000)
        self.daily_limit_input.setSuffix(" USDC")
        layout.addRow(daily_label, self.daily_limit_input)

        self.per_request_input = QDoubleSpinBox()
        self.per_request_input.setRange(0.000001, 10000)
        self.per_request_input.setDecimals(6)
        self.per_request_input.setValue(1.0 if not policy else policy.per_request_max_micro / 1_000_000)
        self.per_request_input.setSuffix(" USDC")
        layout.addRow("Per Request Max:", self.per_request_input)

        self.auto_approve_enabled = QCheckBox("Enable auto-approve below threshold")
        layout.addRow(self.auto_approve_enabled)

        self.auto_approve_input = QDoubleSpinBox()
        self.auto_approve_input.setRange(0.000001, 1000)
        self.auto_approve_input.setDecimals(6)
        self.auto_approve_input.setValue(0.10)
        self.auto_approve_input.setSuffix(" USDC")
        self.auto_approve_input.setEnabled(False)
        self.auto_approve_enabled.toggled.connect(self.auto_approve_input.setEnabled)

        if policy and policy.auto_approve_below_micro is not None:
            self.auto_approve_enabled.setChecked(True)
            self.auto_approve_input.setValue(policy.auto_approve_below_micro / 1_000_000)

        layout.addRow("Auto-Approve Below:", self.auto_approve_input)

        auto_approve_help = QLabel(
            "Auto-approve signs payments below the threshold without confirmation. Spend limits still apply."
        )
        auto_approve_help.setWordWrap(True)
        auto_approve_help.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px;")
        layout.addRow(auto_approve_help)

        # Domain restrictions section
        domains_group = QGroupBox("Domain Restrictions")
        domains_layout = QVBoxLayout(domains_group)

        # Allowed domains
        allowed_label = QLabel("Allowed domains (one per line):")
        domains_layout.addWidget(allowed_label)

        self.allowed_domains_input = QTextEdit()
        self.allowed_domains_input.setPlaceholderText("e.g., stripe.com\nopenai.com")
        self.allowed_domains_input.setMaximumHeight(70)
        self.allowed_domains_input.setFont(QFont(Theme.MONO_FONT, 9))
        if policy and policy.allowed_domains:
            self.allowed_domains_input.setPlainText("\n".join(policy.allowed_domains))
        domains_layout.addWidget(self.allowed_domains_input)

        allowed_help = QLabel("Leave empty to allow all domains.")
        allowed_help.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px;")
        domains_layout.addWidget(allowed_help)

        # Blocked domains
        blocked_label = QLabel("Blocked domains (one per line):")
        domains_layout.addWidget(blocked_label)

        self.blocked_domains_input = QTextEdit()
        self.blocked_domains_input.setPlaceholderText("e.g., malicious-site.com")
        self.blocked_domains_input.setMaximumHeight(70)
        self.blocked_domains_input.setFont(QFont(Theme.MONO_FONT, 9))
        if policy and policy.blocked_domains:
            self.blocked_domains_input.setPlainText("\n".join(policy.blocked_domains))
        domains_layout.addWidget(self.blocked_domains_input)

        blocked_help = QLabel("Blocked entries override the allowlist.")
        blocked_help.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px;")
        domains_layout.addWidget(blocked_help)

        # General domain help
        domain_note = QLabel("Subdomains are included automatically (e.g., stripe.com includes api.stripe.com).")
        domain_note.setWordWrap(True)
        domain_note.setStyleSheet(f"color: {Theme.CHARCOAL}; font-size: 11px; font-style: italic;")
        domains_layout.addWidget(domain_note)

        layout.addRow(domains_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def validate_and_accept(self):
        """Validate inputs before accepting."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Policy name is required.")
            return

        # Check for duplicate name using core
        if self._core:
            for policy in self._core.get_all_policies():
                if policy.name == name and (not self.existing_policy or policy.id != self.existing_policy.id):
                    QMessageBox.warning(self, "Duplicate Name", f"Policy name '{name}' already exists.")
                    return

        selected_networks = [
            chain_id for chain_id, cb in self.network_checkboxes.items() if cb.isChecked()
        ]
        if not selected_networks:
            QMessageBox.warning(self, "Validation Error", "Select at least one network.")
            return

        self.accept()

    def _parse_domains(self, text: str) -> list[str]:
        """Parse domain list from textarea, filtering empty lines."""
        lines = text.strip().split("\n")
        return [line.strip().lower() for line in lines if line.strip()]

    def get_policy(self) -> SpendPolicy:
        """Create a SpendPolicy from the dialog inputs."""
        name = self.name_input.text().strip()
        networks = [
            chain_id for chain_id, cb in self.network_checkboxes.items() if cb.isChecked()
        ]
        # Convert dollars to micro-USDC (6 decimals)
        daily_limit_micro = round(self.daily_limit_input.value() * 1_000_000)
        per_request_max_micro = round(self.per_request_input.value() * 1_000_000)

        auto_approve_below_micro = None
        if self.auto_approve_enabled.isChecked():
            auto_approve_below_micro = round(self.auto_approve_input.value() * 1_000_000)

        allowed_domains = self._parse_domains(self.allowed_domains_input.toPlainText())
        blocked_domains = self._parse_domains(self.blocked_domains_input.toPlainText())

        return SpendPolicy.create(
            name=name,
            networks=networks,
            daily_limit_micro=daily_limit_micro,
            per_request_max_micro=per_request_max_micro,
            auto_approve_below_micro=auto_approve_below_micro,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains
        )

    def get_policy_data(self) -> dict:
        """Return policy parameters as dict for core.create_policy()."""
        name = self.name_input.text().strip()
        networks = [
            chain_id for chain_id, cb in self.network_checkboxes.items() if cb.isChecked()
        ]
        daily_limit_micro = round(self.daily_limit_input.value() * 1_000_000)
        per_request_max_micro = round(self.per_request_input.value() * 1_000_000)

        auto_approve_below_micro = None
        if self.auto_approve_enabled.isChecked():
            auto_approve_below_micro = round(self.auto_approve_input.value() * 1_000_000)

        allowed_domains = self._parse_domains(self.allowed_domains_input.toPlainText())
        blocked_domains = self._parse_domains(self.blocked_domains_input.toPlainText())

        return {
            "name": name,
            "networks": networks,
            "daily_limit_micro": daily_limit_micro,
            "per_request_max_micro": per_request_max_micro,
            "auto_approve_below_micro": auto_approve_below_micro,
            "allowed_domains": allowed_domains if allowed_domains else None,
            "blocked_domains": blocked_domains if blocked_domains else None,
        }


# ============================================
# Settings Dialog
# ============================================

class SettingsDialog(QDialog):
    """Dialog for application settings (notifications, startup, window behavior)."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(450)

        self._settings = settings.copy()
        self._changed = False

        layout = QVBoxLayout(self)

        # Notifications group
        notif_group = QGroupBox("Notifications")
        notif_layout = QFormLayout(notif_group)

        notif_desc = QLabel("Control how MultiClaw notifies you about events.")
        notif_desc.setWordWrap(True)
        notif_desc.setStyleSheet(f"color: {Theme.CHARCOAL};")
        notif_layout.addRow(notif_desc)

        self.sound_checkbox = QCheckBox("Play sound for approval requests")
        self.sound_checkbox.setChecked(self._settings.get("sound_enabled", True))
        self.sound_checkbox.stateChanged.connect(self._on_setting_changed)
        notif_layout.addRow(self.sound_checkbox)

        self.toast_checkbox = QCheckBox("Show system notifications")
        self.toast_checkbox.setChecked(self._settings.get("toast_enabled", True))
        self.toast_checkbox.stateChanged.connect(self._on_setting_changed)
        notif_layout.addRow(self.toast_checkbox)

        self.flash_checkbox = QCheckBox("Flash taskbar for approval requests")
        self.flash_checkbox.setChecked(self._settings.get("flash_taskbar", True))
        self.flash_checkbox.stateChanged.connect(self._on_setting_changed)
        notif_layout.addRow(self.flash_checkbox)

        layout.addWidget(notif_group)

        # Window behavior group
        window_group = QGroupBox("Window Behavior")
        window_layout = QFormLayout(window_group)

        self.minimize_to_tray_checkbox = QCheckBox("Minimize to system tray instead of taskbar")
        self.minimize_to_tray_checkbox.setChecked(self._settings.get("minimize_to_tray", False))
        self.minimize_to_tray_checkbox.stateChanged.connect(self._on_setting_changed)
        window_layout.addRow(self.minimize_to_tray_checkbox)

        self.close_to_tray_checkbox = QCheckBox("Close to system tray (keep running)")
        self.close_to_tray_checkbox.setChecked(self._settings.get("close_to_tray", False))
        self.close_to_tray_checkbox.stateChanged.connect(self._on_setting_changed)
        window_layout.addRow(self.close_to_tray_checkbox)

        self.start_minimized_checkbox = QCheckBox("Start minimized")
        self.start_minimized_checkbox.setChecked(self._settings.get("start_minimized", False))
        self.start_minimized_checkbox.stateChanged.connect(self._on_setting_changed)
        window_layout.addRow(self.start_minimized_checkbox)

        layout.addWidget(window_group)

        # Startup group
        startup_group = QGroupBox("Startup")
        startup_layout = QFormLayout(startup_group)

        self.auto_start_server_checkbox = QCheckBox("Start server automatically on launch")
        self.auto_start_server_checkbox.setChecked(self._settings.get("auto_start_server", False))
        self.auto_start_server_checkbox.stateChanged.connect(self._on_setting_changed)
        startup_layout.addRow(self.auto_start_server_checkbox)

        layout.addWidget(startup_group)

        # Logging group
        logging_group = QGroupBox("Logging")
        logging_layout = QFormLayout(logging_group)

        logging_desc = QLabel("Control log persistence between sessions.")
        logging_desc.setWordWrap(True)
        logging_desc.setStyleSheet(f"color: {Theme.CHARCOAL};")
        logging_layout.addRow(logging_desc)

        from PyQt6.QtWidgets import QSpinBox

        self.log_lines_input = QSpinBox()
        self.log_lines_input.setRange(0, 10000)
        self.log_lines_input.setSingleStep(100)
        self.log_lines_input.setValue(self._settings.get("log_lines_on_startup", 0))
        self.log_lines_input.setToolTip("0 = start fresh each session")
        self.log_lines_input.setMaximumWidth(100)
        self.log_lines_input.valueChanged.connect(self._on_setting_changed)
        logging_layout.addRow("Load recent logs on startup:", self.log_lines_input)

        self.log_retention_input = QSpinBox()
        self.log_retention_input.setRange(0, 365)
        self.log_retention_input.setValue(self._settings.get("log_retention_days", 0))
        self.log_retention_input.setSuffix(" days")
        self.log_retention_input.setToolTip("0 = don't save logs to disk")
        self.log_retention_input.setMaximumWidth(100)
        self.log_retention_input.valueChanged.connect(self._on_setting_changed)
        logging_layout.addRow("Keep log files for:", self.log_retention_input)

        layout.addWidget(logging_group)

        # Security group
        security_group = QGroupBox("Security")
        security_layout = QFormLayout(security_group)

        security_desc = QLabel("Automatically lock wallet after period of inactivity.")
        security_desc.setWordWrap(True)
        security_desc.setStyleSheet(f"color: {Theme.CHARCOAL};")
        security_layout.addRow(security_desc)

        self.auto_lock_input = QSpinBox()
        self.auto_lock_input.setRange(0, 60)
        self.auto_lock_input.setValue(self._settings.get("auto_lock_minutes", 0))
        self.auto_lock_input.setSuffix(" min")
        self.auto_lock_input.setToolTip("0 = disabled")
        self.auto_lock_input.setMaximumWidth(100)
        self.auto_lock_input.valueChanged.connect(self._on_setting_changed)
        security_layout.addRow("Auto-lock timeout:", self.auto_lock_input)

        # Replay window for signed requests
        replay_desc = QLabel("Maximum age for signed agent requests (prevents replay attacks).")
        replay_desc.setWordWrap(True)
        replay_desc.setStyleSheet(f"color: {Theme.CHARCOAL};")
        security_layout.addRow(replay_desc)

        self.replay_window_input = QSpinBox()
        self.replay_window_input.setRange(30, 600)  # 30 seconds to 10 minutes
        self.replay_window_input.setValue(self._settings.get("replay_window_seconds", 300))
        self.replay_window_input.setSuffix(" sec")
        self.replay_window_input.setToolTip("How long signed requests remain valid (30-600 seconds)")
        self.replay_window_input.setMaximumWidth(100)
        self.replay_window_input.valueChanged.connect(self._on_setting_changed)
        security_layout.addRow("Replay window:", self.replay_window_input)

        layout.addWidget(security_group)

        layout.addStretch()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_setting_changed(self, state: int):
        """Handle any setting checkbox change."""
        self._changed = True

    def get_settings(self) -> dict:
        """Return the modified settings."""
        return {
            "sound_enabled": self.sound_checkbox.isChecked(),
            "toast_enabled": self.toast_checkbox.isChecked(),
            "flash_taskbar": self.flash_checkbox.isChecked(),
            "minimize_to_tray": self.minimize_to_tray_checkbox.isChecked(),
            "close_to_tray": self.close_to_tray_checkbox.isChecked(),
            "start_minimized": self.start_minimized_checkbox.isChecked(),
            "auto_start_server": self.auto_start_server_checkbox.isChecked(),
            "log_lines_on_startup": self.log_lines_input.value(),
            "log_retention_days": self.log_retention_input.value(),
            "auto_lock_minutes": self.auto_lock_input.value(),
            "replay_window_seconds": self.replay_window_input.value(),
        }

    def has_changes(self) -> bool:
        """Check if settings were modified."""
        return self._changed


# ============================================
# Transaction Detail Dialog
# ============================================

class TransactionDetailDialog(QDialog):
    """Dialog showing full details of a transaction."""

    STATUS_COLORS = {
        "received": "#888888",
        "signed": "#4A90D9",
        "rejected": Theme.ERROR,
        "submitted": "#D9A74A",
        "settled": Theme.SUCCESS,
        "failed": Theme.ERROR,
    }

    def __init__(self, tx, core, parent=None):
        """
        Args:
            tx: Transaction to display
            core: MultiClaw core instance for verification/receipts
            parent: Parent widget
        """
        super().__init__(parent)
        self.tx = tx
        self.core = core
        self.setWindowTitle(f"Transaction Details - {tx.id[:8]}")
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header with status
        header = QHBoxLayout()
        title = QLabel(f"Transaction {tx.id[:8]}...")
        title.setFont(QFont("", 14, QFont.Weight.Bold))
        header.addWidget(title)

        status_label = QLabel(tx.status.upper())
        color = self.STATUS_COLORS.get(tx.status, "#888888")
        # Settled but not verified should be orange, not green
        if tx.status == "settled" and getattr(tx, 'verification_status', None) != "verified":
            color = Theme.WARNING
        status_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        header.addStretch()
        header.addWidget(status_label)

        layout.addLayout(header)

        # Info grid
        info_group = QGroupBox("Details")
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(8)

        info_layout.addRow("Agent:", QLabel(f"{tx.agent_name} ({tx.agent_id})"))
        info_layout.addRow("Amount:", QLabel(tx.format_amount()))
        info_layout.addRow("Network:", QLabel(tx.network))

        recipient_label = QLabel(tx.recipient)
        recipient_label.setWordWrap(True)
        recipient_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addRow("Recipient:", recipient_label)

        if tx.resource:
            resource_label = QLabel(tx.resource)
            resource_label.setWordWrap(True)
            resource_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info_layout.addRow("Resource:", resource_label)

        if tx.wallet_id:
            info_layout.addRow("Wallet:", QLabel(tx.wallet_id))

        layout.addWidget(info_group)

        # Timeline
        timeline_group = QGroupBox("Timeline")
        timeline_layout = QFormLayout(timeline_group)
        timeline_layout.setSpacing(6)

        timeline_layout.addRow("Received:", QLabel(tx.format_datetime()))

        if tx.signed_at:
            try:
                dt = datetime.fromisoformat(tx.signed_at.replace('Z', '+00:00'))
                signed_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                signed_str = tx.signed_at
            auto_str = " (auto)" if tx.auto_approved else ""
            timeline_layout.addRow("Signed:", QLabel(f"{signed_str}{auto_str}"))

        if tx.submitted_at:
            try:
                dt = datetime.fromisoformat(tx.submitted_at.replace('Z', '+00:00'))
                submitted_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                submitted_str = tx.submitted_at
            timeline_layout.addRow("Submitted:", QLabel(submitted_str))

        if tx.settled_at:
            try:
                dt = datetime.fromisoformat(tx.settled_at.replace('Z', '+00:00'))
                settled_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                settled_str = tx.settled_at
            timeline_layout.addRow("Settled:", QLabel(settled_str))

        if tx.reject_reason:
            reason_label = QLabel(tx.reject_reason)
            reason_label.setStyleSheet(f"color: {Theme.ERROR};")
            timeline_layout.addRow("Reason:", reason_label)

        layout.addWidget(timeline_group)

        # Transaction hash (if settled)
        if tx.tx_hash:
            hash_group = QGroupBox("On-Chain")
            hash_layout = QVBoxLayout(hash_group)

            hash_row = QHBoxLayout()
            hash_label = QLabel(tx.tx_hash)
            hash_label.setFont(QFont(Theme.MONO_FONT, 9))
            hash_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            hash_row.addWidget(hash_label)

            copy_btn = QPushButton("Copy")
            copy_btn.setMaximumWidth(60)
            copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(tx.tx_hash))
            hash_row.addWidget(copy_btn)

            hash_layout.addLayout(hash_row)

            # Verification status
            verify_row = QHBoxLayout()
            self.verify_status_label = QLabel(self._format_verification_status())
            verify_row.addWidget(self.verify_status_label)
            verify_row.addStretch()

            self.verify_btn = QPushButton("Verify")
            self.verify_btn.setMaximumWidth(70)
            self.verify_btn.setToolTip("Query blockchain to verify this transaction exists")
            self.verify_btn.clicked.connect(self._on_verify_clicked)
            # Disable if already verifying
            if tx.verification_status == "pending":
                self.verify_btn.setEnabled(False)
            verify_row.addWidget(self.verify_btn)

            hash_layout.addLayout(verify_row)

            # Link to block explorer
            if tx.network in ("skale-base", "eip155:1187947933"):
                explorer_url = f"https://skale-base-explorer.skalenodes.com/tx/{tx.tx_hash}"
            elif tx.network in ("skale-base-sepolia", "eip155:324705682"):
                explorer_url = f"https://base-sepolia-testnet-explorer.skalenodes.com/tx/{tx.tx_hash}"
            elif tx.network in ("base", "eip155:8453"):
                explorer_url = f"https://basescan.org/tx/{tx.tx_hash}"
            elif tx.network in ("base-sepolia", "eip155:84532"):
                explorer_url = f"https://sepolia.basescan.org/tx/{tx.tx_hash}"
            else:
                explorer_url = None

            if explorer_url:
                link = QLabel(f'<a href="{explorer_url}">View on Block Explorer</a>')
                link.setOpenExternalLinks(True)
                hash_layout.addWidget(link)

            layout.addWidget(hash_group)

        # x402 payload (collapsible)
        if tx.x402_data:
            payload_group = QGroupBox("x402 Payload")
            payload_layout = QVBoxLayout(payload_group)

            import json
            payload_text = QTextEdit()
            payload_text.setReadOnly(True)
            payload_text.setFont(QFont(Theme.MONO_FONT, 9))
            payload_text.setPlainText(json.dumps(tx.x402_data, indent=2))
            payload_text.setMaximumHeight(150)
            payload_layout.addWidget(payload_text)

            layout.addWidget(payload_group)

        layout.addStretch()

        # AP2 Receipt button and Close button
        button_row = QHBoxLayout()

        receipt_btn = QPushButton("View AP2 Receipt")
        receipt_btn.setToolTip("View AP2-formatted receipt for audit/compliance")
        receipt_btn.clicked.connect(self._show_ap2_receipt)
        button_row.addWidget(receipt_btn)

        button_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

        # Poll for transaction updates if we have a verify button
        # (signing_service uses callbacks, not Qt signals)
        if hasattr(self, 'verify_btn'):
            from PyQt6.QtCore import QTimer
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(self._check_for_updates)
            self._update_timer.start(500)  # Check every 500ms

    def _format_verification_status(self) -> str:
        """Format verification status for display."""
        status = self.tx.verification_status
        if status == "verified":
            block = self.tx.verification_block
            block_str = f" (block {block})" if block else ""
            return f'<span style="color: {Theme.SUCCESS};">✓ Verified{block_str}</span>'
        elif status == "failed":
            return f'<span style="color: {Theme.ERROR};">✗ Failed on-chain</span>'
        elif status == "not_found":
            return f'<span style="color: {Theme.ERROR};">✗ Not found on-chain</span>'
        elif status == "pending":
            return f'<span style="color: {Theme.WARNING};">⏳ Verifying...</span>'
        else:
            return '<span style="color: #888888;">Not verified</span>'

    def _on_verify_clicked(self):
        """Handle verify button click."""
        self.verify_btn.setEnabled(False)
        self.tx.verification_status = "pending"  # Optimistic update
        self.verify_status_label.setText(self._format_verification_status())
        self.core.verify_transaction(self.tx)

    def _check_for_updates(self):
        """Poll for transaction updates (verification status changes)."""
        if not hasattr(self, 'verify_status_label'):
            return
        # Re-read from dialog's tx object which signing_service updates in place
        self.verify_status_label.setText(self._format_verification_status())
        if hasattr(self, 'verify_btn'):
            self.verify_btn.setEnabled(self.tx.verification_status != "pending")
        # Stop polling if verification is complete
        if self.tx.verification_status in ("verified", "failed", "not_found"):
            if hasattr(self, '_update_timer'):
                self._update_timer.stop()

    def _show_ap2_receipt(self):
        """Show AP2-formatted receipt in a dialog."""
        import json

        receipt = self.core.get_receipt(self.tx.id)

        if receipt.get("error"):
            QMessageBox.warning(self, "Error", f"Could not get receipt: {receipt.get('error')}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"AP2 Receipt - {self.tx.id[:8]}")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # Status header
        status = receipt.get("status", "unknown")
        status_label = QLabel(f"Status: {status.upper()}")
        status_label.setFont(QFont("", 12, QFont.Weight.Bold))
        status_label.setStyleSheet(f"color: {Theme.SUCCESS if status == 'payment-completed' else Theme.WARNING};")
        layout.addWidget(status_label)

        # JSON view
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont(Theme.MONO_FONT, 9))
        text_edit.setPlainText(json.dumps(receipt, indent=2))
        layout.addWidget(text_edit)

        # Buttons
        button_row = QHBoxLayout()

        copy_btn = QPushButton("Copy JSON")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(json.dumps(receipt, indent=2)))
        button_row.addWidget(copy_btn)

        button_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

        dialog.exec()


# ============================================
# Mandate Viewer Dialog
# ============================================

class MandateViewerDialog(QDialog):
    """Dialog for viewing and managing an agent's Intent Mandate."""

    def __init__(self, agent: Agent, current_policy: Optional[SpendPolicy] = None, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.mandate = agent.intent_mandate
        self.current_policy = current_policy
        self.revoked = False

        self.setWindowTitle(f"Intent Mandate - {agent.name}")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Check for staleness
        stale, stale_reason = self._check_staleness()
        if stale and self.mandate:
            stale_banner = QLabel(f"⚠️ Mandate is stale: {stale_reason}\nConsider re-commissioning to regenerate.")
            stale_banner.setWordWrap(True)
            stale_banner.setStyleSheet(f"background: {Theme.WARNING}; color: #000; padding: 8px; border-radius: 4px;")
            layout.addWidget(stale_banner)

        if not self.mandate:
            # No mandate
            no_mandate = QLabel("No Intent Mandate has been generated for this agent.")
            no_mandate.setStyleSheet(f"color: {Theme.CHARCOAL}; padding: 40px;")
            no_mandate.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_mandate)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
            return

        # Header
        header = QHBoxLayout()
        title = QLabel("Intent Mandate")
        title.setFont(QFont("", 14, QFont.Weight.Bold))
        header.addWidget(title)

        mandate_id = self.mandate.get('id', 'unknown')[:8]
        id_label = QLabel(f"Mandate: {mandate_id}...")
        id_label.setFont(QFont(Theme.MONO_FONT, 10))
        id_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
        header.addStretch()
        header.addWidget(id_label)

        layout.addLayout(header)

        # Agent info
        agent_group = QGroupBox("Agent")
        agent_layout = QFormLayout(agent_group)
        agent_layout.setSpacing(6)

        agent_info = self.mandate.get('agent', {})
        agent_id_label = QLabel(agent_info.get('id', 'Unknown'))
        agent_id_label.setFont(QFont(Theme.MONO_FONT, 10))
        agent_layout.addRow("Agent ID:", agent_id_label)

        fingerprint = agent_info.get('authKeyFingerprint', '')
        if fingerprint:
            fp_label = QLabel(fingerprint)
            fp_label.setFont(QFont(Theme.MONO_FONT, 9))
            fp_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            agent_layout.addRow("Auth Fingerprint:", fp_label)

        layout.addWidget(agent_group)

        # Authorization
        auth_group = QGroupBox("Authorization")
        auth_layout = QFormLayout(auth_group)
        auth_layout.setSpacing(6)

        auth = self.mandate.get('authorization', {})
        # Show policy name from current_policy if available, otherwise just policy ID
        policy_display = self.current_policy.name if self.current_policy else auth.get('policyId', 'Unknown')[:8] + '...'
        auth_layout.addRow("Policy:", QLabel(policy_display))

        limits = auth.get('limits', {})
        currency = limits.get('currency', 'USDC')
        decimals = limits.get('decimals', 6)
        divisor = 10 ** decimals
        daily = limits.get('dailyLimit') or 0
        per_req = limits.get('perRequestMax') or 0
        auto = limits.get('autoApproveBelow')  # Can be None for manual-only
        auth_layout.addRow("Daily Limit:", QLabel(f"{daily/divisor:.6f} {currency}"))
        auth_layout.addRow("Per Request Max:", QLabel(f"{per_req/divisor:.6f} {currency}"))
        auto_text = f"{auto/divisor:.6f} {currency}" if auto is not None else "Manual only"
        auth_layout.addRow("Auto-approve Below:", QLabel(auto_text))

        networks = auth.get('networks', [])
        auth_layout.addRow("Networks:", QLabel(", ".join(networks) if networks else "None"))

        domains = auth.get('domains', {})
        allowlist = domains.get('allowlist', [])
        blocklist = domains.get('blocklist', [])
        if allowlist:
            auth_layout.addRow("Allowed Domains:", QLabel(", ".join(allowlist)))
        if blocklist:
            auth_layout.addRow("Blocked Domains:", QLabel(", ".join(blocklist)))

        layout.addWidget(auth_group)

        # Wallet
        wallet_group = QGroupBox("Signing Wallet")
        wallet_layout = QFormLayout(wallet_group)

        wallet_info = self.mandate.get('wallet', {})
        address = wallet_info.get('address', 'Unknown')
        addr_label = QLabel(address)
        addr_label.setFont(QFont(Theme.MONO_FONT, 9))
        addr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        wallet_layout.addRow("Address:", addr_label)

        layout.addWidget(wallet_group)

        # Signature
        sig_info = self.mandate.get('signature', {})
        if sig_info:
            sig_group = QGroupBox("Signature")
            sig_layout = QFormLayout(sig_group)

            sig_layout.addRow("Type:", QLabel(sig_info.get('type', 'Unknown')))
            signer = sig_info.get('signer', '')
            if signer:
                signer_label = QLabel(signer)
                signer_label.setFont(QFont(Theme.MONO_FONT, 9))
                sig_layout.addRow("Signer:", signer_label)

            sig_value = sig_info.get('value', '')
            if sig_value:
                sig_short = sig_value[:20] + "..." if len(sig_value) > 20 else sig_value
                sig_label = QLabel(sig_short)
                sig_label.setFont(QFont(Theme.MONO_FONT, 9))
                sig_label.setToolTip(sig_value)
                sig_layout.addRow("Signature:", sig_label)

            layout.addWidget(sig_group)

        # Timestamps
        issued_at = self.mandate.get('issuedAt', '')
        if issued_at:
            try:
                dt = datetime.fromisoformat(issued_at.replace('Z', '+00:00'))
                issued_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except (ValueError, TypeError):
                issued_str = issued_at
            issued_label = QLabel(f"Issued: {issued_str}")
            issued_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
            layout.addWidget(issued_label)

        # Registry URL if available
        registry_url = self.mandate.get('registryUrl', '')
        if registry_url:
            registry_row = QHBoxLayout()
            registry_label = QLabel(f'<a href="{registry_url}">View on AP2 Registry</a>')
            registry_label.setOpenExternalLinks(True)
            registry_row.addWidget(registry_label)
            registry_row.addStretch()
            layout.addLayout(registry_row)

        layout.addStretch()

        # Buttons
        button_row = QHBoxLayout()

        view_json_btn = QPushButton("View JSON")
        view_json_btn.clicked.connect(self._show_json)
        button_row.addWidget(view_json_btn)

        copy_btn = QPushButton("Copy JSON")
        copy_btn.clicked.connect(self._copy_json)
        button_row.addWidget(copy_btn)

        button_row.addStretch()

        revoke_btn = QPushButton("Revoke Mandate")
        revoke_btn.setToolTip("Remove the mandate from this agent (cannot be undone)")
        revoke_btn.setStyleSheet(f"background: {Theme.RUST}; color: {Theme.WHITE};")
        revoke_btn.clicked.connect(self._revoke_mandate)
        button_row.addWidget(revoke_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

    def _show_json(self):
        """Show full mandate JSON in a dialog."""
        import json

        dialog = QDialog(self)
        dialog.setWindowTitle("Intent Mandate JSON")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont(Theme.MONO_FONT, 9))
        text_edit.setPlainText(json.dumps(self.mandate, indent=2))
        layout.addWidget(text_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.exec()

    def _copy_json(self):
        """Copy mandate JSON to clipboard."""
        import json
        QApplication.clipboard().setText(json.dumps(self.mandate, indent=2))

    def _revoke_mandate(self):
        """Revoke the mandate from the agent."""
        reply = QMessageBox.question(
            self,
            "Revoke Mandate",
            f"Revoke the Intent Mandate for agent '{self.agent.name}'?\n\n"
            "This will remove the mandate from this agent. "
            "The agent can be recommissioned to generate a new mandate.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.agent.intent_mandate = None
            self.revoked = True
            self.accept()

    def was_revoked(self) -> bool:
        """Return True if the mandate was revoked."""
        return self.revoked

    def _check_staleness(self) -> tuple[bool, Optional[str]]:
        """Check if mandate is stale (doesn't match current policy)."""
        if not self.mandate or not self.current_policy:
            return False, None

        auth = self.mandate.get("authorization", {})
        mandate_policy_id = auth.get("policyId")
        mandate_limits = auth.get("limits", {})

        # Check if policy ID changed
        if mandate_policy_id != self.current_policy.id:
            return True, "Agent assigned a different policy"

        # Check if limits changed
        if mandate_limits.get("dailyLimit") != self.current_policy.daily_limit_micro:
            return True, "Daily limit changed"
        if mandate_limits.get("perRequestMax") != self.current_policy.per_request_max_micro:
            return True, "Per-request maximum changed"
        if mandate_limits.get("autoApproveBelow") != self.current_policy.auto_approve_below_micro:
            return True, "Auto-approve threshold changed"

        # Check domain restrictions
        mandate_domains = auth.get("domains", {})
        mandate_allowlist = set(mandate_domains.get("allowlist", []))
        mandate_blocklist = set(mandate_domains.get("blocklist", []))
        current_allowlist = set(self.current_policy.allowed_domains or [])
        current_blocklist = set(self.current_policy.blocked_domains or [])

        if mandate_allowlist != current_allowlist:
            return True, "Allowed domains changed"
        if mandate_blocklist != current_blocklist:
            return True, "Blocked domains changed"

        return False, None


# ============================================
# Export Keys Dialog
# ============================================

class ExportKeysDialog(QDialog):
    """Dialog for exporting private keys and seed phrases."""

    def __init__(self, wallets: list[WalletInfoLike], get_wallet_fn, parent=None):
        """
        Initialize the export keys dialog.

        Args:
            wallets: List of WalletInfo objects for available wallets
            get_wallet_fn: Function to get an unlocked wallet by address
            parent: Parent widget
        """
        super().__init__(parent)
        self.wallets = wallets
        self.get_wallet_fn = get_wallet_fn

        self.setWindowTitle("Export Keys")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Warning header
        warning_box = QGroupBox()
        warning_box.setStyleSheet(f"""
            QGroupBox {{
                background-color: #FFF3CD;
                border: 1px solid #FFECB5;
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        warning_layout = QVBoxLayout(warning_box)

        warning_title = QLabel("Security Warning")
        warning_title.setFont(QFont("", 11, QFont.Weight.Bold))
        warning_title.setStyleSheet("color: #856404;")
        warning_layout.addWidget(warning_title)

        warning_text = QLabel(
            "Private keys and seed phrases give full control over your funds. "
            "Never share them with anyone. Store backups securely offline."
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #856404;")
        warning_layout.addWidget(warning_text)

        layout.addWidget(warning_box)

        # Address selection
        addr_label = QLabel("Select address to export:")
        layout.addWidget(addr_label)

        self.address_combo = QComboBox()
        self.address_combo.setFont(QFont(Theme.MONO_FONT, 9))
        for wallet_info in wallets:
            addr_short = format_address(wallet_info.address)
            entry_id = getattr(wallet_info, 'wallet_id', None) or getattr(wallet_info, 'id', '')
            self.address_combo.addItem(
                f"{entry_id}  {wallet_info.name}  ({addr_short})",
                wallet_info
            )
        self.address_combo.currentIndexChanged.connect(self._on_address_changed)
        layout.addWidget(self.address_combo)

        # Export options
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout(options_group)

        self.export_pkey_checkbox = QCheckBox("Private Key (hex)")
        self.export_pkey_checkbox.setChecked(True)
        options_layout.addWidget(self.export_pkey_checkbox)

        self.export_seed_checkbox = QCheckBox("Seed Phrase (if available)")
        self.export_seed_checkbox.setEnabled(False)  # Will be updated based on wallet type
        options_layout.addWidget(self.export_seed_checkbox)

        layout.addWidget(options_group)

        # Output area
        output_group = QGroupBox("Exported Data")
        output_layout = QVBoxLayout(output_group)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont(Theme.MONO_FONT, 9))
        self.output_text.setPlaceholderText("Click 'Reveal Keys' to show sensitive data...")
        self.output_text.setMinimumHeight(100)
        output_layout.addWidget(self.output_text)

        # Copy button
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        output_layout.addWidget(copy_btn)

        layout.addWidget(output_group)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        self.reveal_btn = QPushButton("Reveal Keys")
        self.reveal_btn.setDefault(True)
        self.reveal_btn.clicked.connect(self._reveal_keys)
        btn_layout.addWidget(self.reveal_btn)

        layout.addLayout(btn_layout)

        # Initialize state
        self._on_address_changed()

    def _on_address_changed(self):
        """Handle address selection change."""
        wallet_info = self.address_combo.currentData()
        if not wallet_info:
            return

        # Check if this is an HD wallet (has seed) or private key wallet
        wallet = self.get_wallet_fn(wallet_info.address)
        if wallet:
            is_hd = hasattr(wallet, 'seed_phrase') and wallet.seed_phrase is not None
            self.export_seed_checkbox.setEnabled(is_hd)
            if is_hd:
                self.export_seed_checkbox.setText("Seed Phrase")
            else:
                self.export_seed_checkbox.setText("Seed Phrase (not available - private key wallet)")
                self.export_seed_checkbox.setChecked(False)

        # Clear output when address changes
        self.output_text.clear()

    def _reveal_keys(self):
        """Reveal the selected keys."""
        wallet_info = self.address_combo.currentData()
        if not wallet_info:
            QMessageBox.warning(self, "Error", "No address selected.")
            return

        wallet = self.get_wallet_fn(wallet_info.address)
        if not wallet:
            QMessageBox.warning(
                self, "Error",
                "Could not retrieve wallet. Make sure the wallet is unlocked."
            )
            return

        # Confirm before revealing
        confirm = QMessageBox.warning(
            self,
            "Confirm Export",
            "You are about to reveal sensitive key material.\n\n"
            "Make sure no one is watching your screen.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        output_lines = []
        output_lines.append(f"Address: {wallet_info.address}")
        output_lines.append(f"Name: {wallet_info.name}")
        output_lines.append("")

        # Export private key
        if self.export_pkey_checkbox.isChecked():
            try:
                # Find the address index for HD wallets
                if hasattr(wallet, '_addresses'):
                    # HD wallet - find the index from derivation path
                    pkey = None
                    for addr in wallet._addresses:
                        if addr.address.lower() == wallet_info.address.lower():
                            # Extract index from path like "m/44'/60'/0'/0/0"
                            path_parts = addr.path.split('/')
                            if path_parts:
                                try:
                                    index = int(path_parts[-1])
                                    pkey = wallet.get_private_key(index)
                                except ValueError:
                                    pkey = wallet.get_private_key(0)
                            break
                    if pkey is None:
                        # Fallback to index 0
                        pkey = wallet.get_private_key(0)
                else:
                    # Private key wallet
                    pkey = wallet.get_private_key(0)

                output_lines.append("Private Key:")
                output_lines.append(f"0x{pkey.hex()}")
                output_lines.append("")
            except Exception as e:
                output_lines.append(f"Error getting private key: {e}")
                output_lines.append("")

        # Export seed phrase
        if self.export_seed_checkbox.isChecked() and self.export_seed_checkbox.isEnabled():
            try:
                seed = wallet.seed_phrase
                if seed:
                    output_lines.append("Seed Phrase:")
                    output_lines.append(seed)
                    output_lines.append("")
            except Exception as e:
                output_lines.append(f"Error getting seed phrase: {e}")
                output_lines.append("")

        self.output_text.setPlainText("\n".join(output_lines))

    def _copy_to_clipboard(self):
        """Copy the output to clipboard with auto-clear."""
        text = self.output_text.toPlainText()
        if not text or text == self.output_text.placeholderText():
            QMessageBox.information(
                self, "Nothing to Copy",
                "Click 'Reveal Keys' first to show the data."
            )
            return

        copy_sensitive_to_clipboard(text, self)


# ============================================
# Withdraw USDC Dialog
# ============================================

class WithdrawUSDCDialog(QDialog):
    """Dialog for withdrawing USDC from a wallet (requires gas)."""

    def __init__(
        self,
        wallet_entry: AddressEntry,
        balance: float,
        get_private_key_fn,
        chain_id: int,
        parent=None
    ):
        """
        Initialize the withdraw dialog.

        Args:
            wallet_entry: The AddressEntry for the source wallet
            balance: Current USDC balance
            get_private_key_fn: Function to get private key by address_id
            chain_id: Chain ID for the transaction
            parent: Parent widget
        """
        super().__init__(parent)
        self.wallet_entry = wallet_entry
        self.balance = balance
        self.get_private_key_fn = get_private_key_fn
        self.chain_id = chain_id

        self.setWindowTitle(f"Withdraw USDC - {wallet_entry.id}")
        self.setFixedWidth(450)
        self.setFixedHeight(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Source info
        source_group = QGroupBox("Source")
        source_layout = QFormLayout(source_group)

        addr_label = QLabel(wallet_entry.address)
        addr_label.setFont(QFont(Theme.MONO_FONT, 9))
        addr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        source_layout.addRow("Address:", addr_label)

        balance_label = QLabel(f"{balance:.6f} USDC")
        balance_label.setStyleSheet("font-weight: bold;")
        source_layout.addRow("Balance:", balance_label)

        network = NETWORKS.get(chain_id)
        network_label = QLabel(network.display_name if network else f"Chain {chain_id}")
        source_layout.addRow("Network:", network_label)

        layout.addWidget(source_group)

        # Warning about gas
        warning_box = QGroupBox()
        warning_box.setStyleSheet("""
            QGroupBox {
                background-color: #FFF3E0;
                border: 1px solid #FFB74D;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        warning_layout = QVBoxLayout(warning_box)
        warning_text = QLabel(
            "This transaction requires gas. Ensure the source wallet has "
            f"sufficient {network.native_symbol if network else 'native token'} for gas fees."
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #E65100;")
        warning_layout.addWidget(warning_text)
        layout.addWidget(warning_box)

        # Destination
        dest_group = QGroupBox("Destination")
        dest_layout = QFormLayout(dest_group)

        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText("0x...")
        self.dest_input.setFont(QFont(Theme.MONO_FONT, 9))
        dest_layout.addRow("Address:", self.dest_input)

        layout.addWidget(dest_group)

        # Amount
        amount_group = QGroupBox("Amount")
        amount_layout = QFormLayout(amount_group)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setDecimals(6)  # USDC has 6 decimals
        self.amount_input.setMinimum(0.000001)
        self.amount_input.setMaximum(balance)
        self.amount_input.setValue(balance)
        self.amount_input.setSuffix(" USDC")
        amount_layout.addRow("Amount:", self.amount_input)

        max_btn = QPushButton("Max")
        max_btn.clicked.connect(lambda: self.amount_input.setValue(balance))
        amount_layout.addRow("", max_btn)

        layout.addWidget(amount_group)

        # Export key link
        export_link = QLabel('<a href="#">Export private key to use with external wallet</a>')
        export_link.setOpenExternalLinks(False)
        export_link.linkActivated.connect(self._export_key)
        export_link.setStyleSheet(f"color: {Theme.CHARCOAL};")
        layout.addWidget(export_link)

        # Status area (hidden by default)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.send_btn = QPushButton("Send USDC")
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._execute_withdraw)
        btn_layout.addWidget(self.send_btn)

        layout.addLayout(btn_layout)

    def _export_key(self):
        """Export the private key for this wallet."""
        confirm = QMessageBox.warning(
            self,
            "Export Private Key",
            "Are you sure you want to export the private key?\n\n"
            "Anyone with this key can access all funds in this wallet.\n"
            "Never share it with anyone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            pkey = self.get_private_key_fn(self.wallet_entry.id)
            if pkey:
                # Convert bytes to hex string if needed
                if isinstance(pkey, bytes):
                    pkey = "0x" + pkey.hex()
                copy_sensitive_to_clipboard(pkey, self)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export key: {e}")

    def _execute_withdraw(self):
        """Execute the USDC transfer."""
        # Validate destination
        dest = self.dest_input.text().strip()
        if not dest or not dest.startswith("0x") or len(dest) != 42:
            QMessageBox.warning(self, "Invalid Address", "Please enter a valid destination address.")
            return

        amount = self.amount_input.value()
        if amount <= 0 or amount > self.balance:
            QMessageBox.warning(self, "Invalid Amount", "Please enter a valid amount.")
            return

        # Confirm
        confirm = QMessageBox.question(
            self,
            "Confirm Transfer",
            f"Send {amount:.6f} USDC to:\n\n"
            f"{dest[:20]}...{dest[-8:]}\n\n"
            "This will use gas from the source wallet.\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.send_btn.setEnabled(False)
        self.send_btn.setText("Sending...")
        self.status_label.setText("Preparing transaction...")
        self.status_label.setVisible(True)
        QApplication.processEvents()

        try:
            from web3 import Web3
            from ..networks import TOKENS

            network = NETWORKS.get(self.chain_id)
            if not network:
                raise ValueError(f"Network not found: {self.chain_id}")

            usdc_config = TOKENS.get("USDC")
            if not usdc_config or self.chain_id not in usdc_config.addresses:
                raise ValueError(f"USDC not configured for chain {self.chain_id}")

            usdc_address = usdc_config.addresses[self.chain_id]
            # Use Decimal to avoid floating point errors, then floor to ensure we don't exceed balance
            from decimal import Decimal, ROUND_DOWN
            amount_decimal = Decimal(str(amount)).quantize(Decimal('0.000001'), rounding=ROUND_DOWN)
            amount_raw = int(amount_decimal * 1_000_000)

            # Get private key
            pkey = self.get_private_key_fn(self.wallet_entry.id)
            if not pkey:
                raise ValueError("Could not retrieve private key")

            # Connect to network
            w3 = Web3(Web3.HTTPProvider(network.rpc_url))
            if not w3.is_connected():
                raise ValueError(f"Could not connect to {network.display_name}")

            # ERC-20 transfer ABI
            erc20_abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_to", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "transfer",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                }
            ]

            contract = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address),
                abi=erc20_abi
            )

            # Build transaction
            from_addr = Web3.to_checksum_address(self.wallet_entry.address)
            to_addr = Web3.to_checksum_address(dest)

            self.status_label.setText("Estimating gas...")
            QApplication.processEvents()

            nonce = w3.eth.get_transaction_count(from_addr)
            gas_price = w3.eth.gas_price

            tx = contract.functions.transfer(to_addr, amount_raw).build_transaction({
                'from': from_addr,
                'nonce': nonce,
                'gasPrice': gas_price,
                'chainId': self.chain_id,
            })

            # Estimate gas
            try:
                gas_estimate = w3.eth.estimate_gas(tx)
                tx['gas'] = int(gas_estimate * 1.2)  # 20% buffer
            except Exception as e:
                raise ValueError(f"Gas estimation failed: {e}")

            self.status_label.setText("Signing transaction...")
            QApplication.processEvents()

            # Sign and send
            from eth_account import Account
            account = Account.from_key(pkey)
            signed_tx = account.sign_transaction(tx)

            self.status_label.setText("Broadcasting transaction...")
            QApplication.processEvents()

            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            self.status_label.setText(f"Transaction sent: {tx_hash_hex[:16]}...")
            self.status_label.setStyleSheet("color: green;")

            # Show success with explorer link
            explorer_url = f"{network.explorer_url}/tx/0x{tx_hash_hex}"
            QMessageBox.information(
                self,
                "Transaction Sent",
                f"USDC transfer submitted!\n\n"
                f"Amount: {amount:.6f} USDC\n"
                f"To: {dest[:16]}...{dest[-8:]}\n\n"
                f"Transaction: {tx_hash_hex[:16]}...\n\n"
                f"View on explorer:\n{explorer_url}"
            )

            self.accept()

        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Transfer Failed", str(e))

        finally:
            self.send_btn.setEnabled(True)
            self.send_btn.setText("Send USDC")


# ============================================
# Sweep USDC Dialog
# ============================================

class SweepUSDCDialog(QDialog):
    """
    Dialog for sweeping USDC from multiple donor addresses to a single recipient.
    Uses EIP-3009 transferWithAuthorization so sponsor pays all gas.
    """

    def __init__(
        self,
        parent: QWidget,
        addresses: list,  # List of AddressEntry objects
        get_private_key_fn,  # Function(address_id) -> bytes
        chain_id: int,
    ):
        super().__init__(parent)
        self.addresses = addresses
        self.get_private_key_fn = get_private_key_fn
        self.chain_id = chain_id

        self.setWindowTitle("Sweep USDC")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)

        self._setup_ui()
        self._refresh_balances()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Network selector
        network_layout = QHBoxLayout()
        network_layout.addWidget(QLabel("Network:"))
        self.network_combo = QComboBox()
        from ..networks import NETWORKS
        for cid, network in NETWORKS.items():
            self.network_combo.addItem(network.display_name, cid)
            if cid == self.chain_id:
                self.network_combo.setCurrentIndex(self.network_combo.count() - 1)
        self.network_combo.currentIndexChanged.connect(self._on_network_changed)
        self.network_combo.setFixedWidth(180)
        network_layout.addWidget(self.network_combo)
        network_layout.addStretch()
        layout.addLayout(network_layout)

        # Sponsor (pays gas)
        sponsor_group = QGroupBox("Sponsor (pays gas)")
        sponsor_layout = QFormLayout(sponsor_group)
        self.sponsor_combo = QComboBox()
        self.sponsor_combo.setFont(QFont(Theme.MONO_FONT, 9))
        sponsor_layout.addRow("Address:", self.sponsor_combo)
        self.sponsor_balance_label = QLabel("")
        self.sponsor_balance_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
        sponsor_layout.addRow("", self.sponsor_balance_label)
        layout.addWidget(sponsor_group)

        # Recipient
        recipient_group = QGroupBox("Recipient (receives all USDC)")
        recipient_layout = QVBoxLayout(recipient_group)

        self.use_internal_radio = QRadioButton("Use wallet address")
        self.use_internal_radio.setChecked(True)
        self.use_internal_radio.toggled.connect(self._on_recipient_mode_changed)
        recipient_layout.addWidget(self.use_internal_radio)

        self.recipient_combo = QComboBox()
        self.recipient_combo.setFont(QFont(Theme.MONO_FONT, 9))
        recipient_layout.addWidget(self.recipient_combo)

        self.use_external_radio = QRadioButton("Use external address")
        self.use_external_radio.toggled.connect(self._on_recipient_mode_changed)
        recipient_layout.addWidget(self.use_external_radio)

        self.external_input = QLineEdit()
        self.external_input.setPlaceholderText("0x...")
        self.external_input.setFont(QFont(Theme.MONO_FONT, 9))
        self.external_input.setEnabled(False)
        recipient_layout.addWidget(self.external_input)

        layout.addWidget(recipient_group)

        # Donors (sources)
        donor_group = QGroupBox("Donors (sweep FROM these addresses)")
        donor_layout = QVBoxLayout(donor_group)

        # Select all / deselect all
        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all_donors)
        btn_row.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all_donors)
        btn_row.addWidget(deselect_all_btn)

        btn_row.addStretch()

        self.total_label = QLabel("Selected: 0.000000 USDC")
        self.total_label.setStyleSheet(f"font-weight: bold; color: {Theme.LIME_DIM};")
        btn_row.addWidget(self.total_label)

        donor_layout.addLayout(btn_row)

        # Donor list with checkboxes
        self.donor_list = QListWidget()
        self.donor_list.setFont(QFont(Theme.MONO_FONT, 9))
        self.donor_list.setMinimumHeight(150)
        self.donor_list.itemChanged.connect(self._on_donor_selection_changed)
        donor_layout.addWidget(self.donor_list)

        layout.addWidget(donor_group)

        # Status
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Progress (hidden by default)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.sweep_btn = QPushButton("Sweep USDC")
        self.sweep_btn.setDefault(True)
        self.sweep_btn.clicked.connect(self._execute_sweep)
        btn_layout.addWidget(self.sweep_btn)

        layout.addLayout(btn_layout)

    def _on_network_changed(self):
        """Handle network change."""
        self.chain_id = self.network_combo.currentData()
        self._refresh_balances()

    def _on_recipient_mode_changed(self):
        """Toggle between internal and external recipient."""
        use_internal = self.use_internal_radio.isChecked()
        self.recipient_combo.setEnabled(use_internal)
        self.external_input.setEnabled(not use_internal)

    def _refresh_balances(self):
        """Refresh all balance displays for current network."""
        from ..networks import NETWORKS, BalanceFetcher, TOKENS
        from web3 import Web3

        network = NETWORKS.get(self.chain_id)
        if not network:
            return

        # Clear and repopulate combos
        self.sponsor_combo.clear()
        self.recipient_combo.clear()
        self.donor_list.clear()

        self._balances = {}  # address -> (usdc_balance, native_balance)

        try:
            fetcher = BalanceFetcher(network)
            usdc_config = TOKENS.get("USDC")
            usdc_addr = usdc_config.addresses.get(self.chain_id) if usdc_config else None

            for addr_entry in self.addresses:
                address = addr_entry.address
                try:
                    balances = fetcher.get_all_balances(address)
                    native_bal = 0.0
                    usdc_bal = 0.0
                    usdc_raw = 0
                    native_failed = False
                    usdc_failed = False

                    for bal in balances:
                        if bal.symbol == network.native_symbol:
                            native_bal = bal.formatted
                            native_failed = bal.fetch_failed
                        elif bal.symbol == "USDC":
                            usdc_bal = bal.formatted
                            usdc_raw = bal.raw
                            usdc_failed = bal.fetch_failed

                    self._balances[address] = {
                        'native': native_bal,
                        'usdc': usdc_bal,
                        'usdc_raw': usdc_raw,
                        'entry': addr_entry,
                        'native_failed': native_failed,
                        'usdc_failed': usdc_failed,
                    }

                    short_addr = f"{address[:8]}...{address[-6:]}"
                    name = addr_entry.name if addr_entry.name else ""
                    name_display = f" [{name}]" if name else ""

                    # Sponsor combo - show name + native balance or "--" if failed
                    if native_failed:
                        sponsor_text = f"{short_addr}{name_display}  (-- {network.native_symbol})"
                    else:
                        sponsor_text = f"{short_addr}{name_display}  ({native_bal:.6f} {network.native_symbol})"
                    self.sponsor_combo.addItem(sponsor_text, address)

                    # Recipient combo - show name
                    self.recipient_combo.addItem(f"{short_addr}{name_display}", address)

                    # Donor list - show name + USDC balance or "--" if failed
                    if usdc_failed:
                        item = QListWidgetItem(f"{short_addr}{name_display}    -- USDC (RPC error)")
                        item.setForeground(Qt.GlobalColor.red)
                    else:
                        item = QListWidgetItem(f"{short_addr}{name_display}    {usdc_bal:.6f} USDC")
                        # Gray out if confirmed zero
                        if usdc_bal == 0:
                            item.setForeground(Qt.GlobalColor.gray)
                    item.setData(Qt.ItemDataRole.UserRole, address)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    # Auto-check if has USDC (and fetch succeeded)
                    item.setCheckState(Qt.CheckState.Checked if usdc_bal > 0 and not usdc_failed else Qt.CheckState.Unchecked)
                    self.donor_list.addItem(item)

                except Exception as e:
                    # Still add to combos even if balance fetch fails entirely
                    short_addr = f"{address[:8]}...{address[-6:]}"
                    name = addr_entry.name if addr_entry.name else ""
                    name_display = f" [{name}]" if name else ""
                    self.sponsor_combo.addItem(f"{short_addr}{name_display}  (-- RPC error)", address)
                    self.recipient_combo.addItem(f"{short_addr}{name_display}", address)
                    self._balances[address] = {
                        'native': 0.0,
                        'usdc': 0.0,
                        'usdc_raw': 0,
                        'entry': addr_entry,
                        'native_failed': True,
                        'usdc_failed': True,
                    }
                    # Add to donor list with error indicator
                    item = QListWidgetItem(f"{short_addr}{name_display}    -- USDC (RPC error)")
                    item.setData(Qt.ItemDataRole.UserRole, address)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setForeground(Qt.GlobalColor.red)
                    self.donor_list.addItem(item)

            self._update_totals()

        except Exception as e:
            # If fetcher fails entirely, still populate addresses without balances
            for addr_entry in self.addresses:
                address = addr_entry.address
                short_addr = f"{address[:8]}...{address[-6:]}"
                name = addr_entry.name if addr_entry.name else ""
                name_display = f" [{name}]" if name else ""
                self.sponsor_combo.addItem(f"{short_addr}{name_display}  (RPC error)", address)
                self.recipient_combo.addItem(f"{short_addr}{name_display}", address)
                self._balances[address] = {
                    'native': 0.0,
                    'usdc': 0.0,
                    'usdc_raw': 0,
                    'entry': addr_entry
                }
            QMessageBox.warning(self, "Error", f"Failed to fetch balances: {e}")

    def _select_all_donors(self):
        """Select all donors with non-zero balance."""
        for i in range(self.donor_list.count()):
            item = self.donor_list.item(i)
            addr = item.data(Qt.ItemDataRole.UserRole)
            if addr in self._balances and self._balances[addr]['usdc'] > 0:
                item.setCheckState(Qt.CheckState.Checked)
        self._update_totals()

    def _deselect_all_donors(self):
        """Deselect all donors."""
        for i in range(self.donor_list.count()):
            item = self.donor_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)
        self._update_totals()

    def _on_donor_selection_changed(self, item):
        """Handle donor checkbox change."""
        self._update_totals()

    def _update_totals(self):
        """Update the total selected amount."""
        total = 0.0
        count = 0
        for i in range(self.donor_list.count()):
            item = self.donor_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                addr = item.data(Qt.ItemDataRole.UserRole)
                if addr in self._balances:
                    total += self._balances[addr]['usdc']
                    count += 1

        self.total_label.setText(f"Selected: {count} addresses, {total:.6f} USDC")
        self.sweep_btn.setText(f"Sweep {total:.6f} USDC")
        self.sweep_btn.setEnabled(count > 0 and total > 0)

    def _get_selected_donors(self) -> list:
        """Get list of selected donor addresses with balances."""
        donors = []
        for i in range(self.donor_list.count()):
            item = self.donor_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                addr = item.data(Qt.ItemDataRole.UserRole)
                if addr in self._balances and self._balances[addr]['usdc_raw'] > 0:
                    donors.append({
                        'address': addr,
                        'entry': self._balances[addr]['entry'],
                        'usdc_raw': self._balances[addr]['usdc_raw'],
                        'usdc': self._balances[addr]['usdc']
                    })
        return donors

    def _execute_sweep(self):
        """Execute the sweep operation."""
        from ..networks import NETWORKS, TOKENS
        from web3 import Web3
        from eth_account import Account
        from ..services.eip3009 import sign_transfer_authorization
        import secrets
        import time

        # Get inputs
        sponsor_addr = self.sponsor_combo.currentData()
        if not sponsor_addr:
            QMessageBox.warning(self, "Error", "Please select a sponsor address.")
            return

        if self.use_internal_radio.isChecked():
            recipient_addr = self.recipient_combo.currentData()
        else:
            recipient_addr = self.external_input.text().strip()

        if not recipient_addr or not recipient_addr.startswith("0x") or len(recipient_addr) != 42:
            QMessageBox.warning(self, "Error", "Please enter a valid recipient address.")
            return

        donors = self._get_selected_donors()
        if not donors:
            QMessageBox.warning(self, "Error", "Please select at least one donor address.")
            return

        # Confirm
        total_usdc = sum(d['usdc'] for d in donors)
        confirm = QMessageBox.question(
            self,
            "Confirm Sweep",
            f"Sweep {total_usdc:.6f} USDC from {len(donors)} address(es)\n\n"
            f"To: {recipient_addr[:16]}...{recipient_addr[-8:]}\n"
            f"Gas paid by: {sponsor_addr[:16]}...{sponsor_addr[-8:]}\n\n"
            "This will execute multiple transactions. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Disable UI
        self.sweep_btn.setEnabled(False)
        self.sweep_btn.setText("Sweeping...")
        self.status_label.setVisible(True)
        self.progress_label.setVisible(True)

        try:
            network = NETWORKS.get(self.chain_id)
            usdc_config = TOKENS.get("USDC")
            usdc_address = usdc_config.addresses.get(self.chain_id)

            if not network or not usdc_address:
                raise ValueError("Network or USDC not configured")

            # Connect to network
            w3 = Web3(Web3.HTTPProvider(network.rpc_url))
            if not w3.is_connected():
                raise ValueError(f"Could not connect to {network.display_name}")

            # Get sponsor private key
            sponsor_entry = self._balances[sponsor_addr]['entry']
            sponsor_pkey = self.get_private_key_fn(sponsor_entry.id)
            if not sponsor_pkey:
                raise ValueError("Could not get sponsor private key")
            if isinstance(sponsor_pkey, bytes):
                sponsor_pkey = "0x" + sponsor_pkey.hex()

            sponsor_account = Account.from_key(sponsor_pkey)

            # USDC contract ABI for transferWithAuthorization
            twa_abi = [{
                "inputs": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "validAfter", "type": "uint256"},
                    {"name": "validBefore", "type": "uint256"},
                    {"name": "nonce", "type": "bytes32"},
                    {"name": "v", "type": "uint8"},
                    {"name": "r", "type": "bytes32"},
                    {"name": "s", "type": "bytes32"}
                ],
                "name": "transferWithAuthorization",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }]

            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address),
                abi=twa_abi
            )

            # Process each donor
            successful = 0
            failed = 0
            tx_hashes = []

            for idx, donor in enumerate(donors):
                self.progress_label.setText(f"Processing {idx + 1}/{len(donors)}: {donor['address'][:10]}...")
                QApplication.processEvents()

                try:
                    # Get donor private key
                    donor_pkey = self.get_private_key_fn(donor['entry'].id)
                    if not donor_pkey:
                        raise ValueError("Could not get donor private key")
                    if isinstance(donor_pkey, bytes):
                        donor_pkey = "0x" + donor_pkey.hex()

                    # Sign authorization
                    now = int(time.time())
                    valid_after = now - 60
                    valid_before = now + 3600
                    nonce_bytes = secrets.token_bytes(32)

                    signature = sign_transfer_authorization(
                        private_key=donor_pkey,
                        chain_id=self.chain_id,
                        token_address=usdc_address,
                        token_name="USD Coin",
                        token_version="2",
                        from_address=donor['address'],
                        to_address=recipient_addr,
                        value=donor['usdc_raw'],
                        valid_after=valid_after,
                        valid_before=valid_before,
                        nonce=nonce_bytes
                    )

                    # Parse signature into v, r, s
                    sig_bytes = bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)
                    r = sig_bytes[:32]
                    s = sig_bytes[32:64]
                    v = sig_bytes[64]

                    # Build transaction from sponsor
                    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(sponsor_addr))
                    gas_price = w3.eth.gas_price

                    tx = usdc_contract.functions.transferWithAuthorization(
                        Web3.to_checksum_address(donor['address']),
                        Web3.to_checksum_address(recipient_addr),
                        donor['usdc_raw'],
                        valid_after,
                        valid_before,
                        nonce_bytes,
                        v,
                        r,
                        s
                    ).build_transaction({
                        'from': Web3.to_checksum_address(sponsor_addr),
                        'nonce': nonce,
                        'gasPrice': gas_price,
                        'chainId': self.chain_id,
                    })

                    # Estimate gas
                    gas_estimate = w3.eth.estimate_gas(tx)
                    tx['gas'] = int(gas_estimate * 1.2)

                    # Sign and send
                    signed_tx = sponsor_account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                    tx_hashes.append(tx_hash.hex())
                    successful += 1

                    self.status_label.setText(f"Sent: ${donor['usdc']:.6f} from {donor['address'][:10]}...")
                    self.status_label.setStyleSheet(f"color: {Theme.LIME};")

                except Exception as e:
                    failed += 1
                    self.status_label.setText(f"Failed: {donor['address'][:10]}... - {e}")
                    self.status_label.setStyleSheet(f"color: {Theme.ERROR};")

                QApplication.processEvents()

            # Summary
            self.progress_label.setText(f"Complete: {successful} successful, {failed} failed")

            if successful > 0:
                QMessageBox.information(
                    self,
                    "Sweep Complete",
                    f"Successfully swept {successful} address(es).\n"
                    f"Failed: {failed}\n\n"
                    f"Transactions:\n" + "\n".join(tx_hashes[:5]) +
                    ("\n..." if len(tx_hashes) > 5 else "")
                )
                self.accept()
            else:
                QMessageBox.warning(self, "Sweep Failed", "All transfers failed.")

        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet(f"color: {Theme.ERROR};")
            QMessageBox.critical(self, "Sweep Failed", str(e))

        finally:
            self.sweep_btn.setEnabled(True)
            self.sweep_btn.setText("Sweep USDC")
