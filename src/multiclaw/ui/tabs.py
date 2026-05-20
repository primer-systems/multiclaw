"""
UI Tabs - Main application tabs.

Contains:
- PoliciesTab: Manage spend policies
- AgentsTab: Manage registered agents
- HistoryTab: Transaction history
- WalletTab: Multi-wallet management
- NetworkTab: Server and network settings
- SettingsTab: Advanced application settings
- LogTab: Real-time logs
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QCheckBox, QSpinBox, QLineEdit, QTextEdit, QGroupBox,
    QFormLayout, QMessageBox, QFileDialog, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from typing import Optional
import csv

from .theme import Theme, ask_question
from .dialogs import (
    AgentRegistrationDialog, CommissionDialog, EditAgentDialog,
    NewPolicyDialog
)
from ..models import SpendPolicy, Agent, Transaction
from ..wallet import MultiClawWallet, AddressEntry, NO_PASSWORD_SENTINEL
from ..wallet.dialogs import (
    AddAddressDialog, SeedSelectionDialog, DerivationBrowserDialog,
    NewSeedDialog, ImportSeedToWalletDialog, ImportPrivateKeyToWalletDialog,
    MultiClawWalletUnlockDialog, CreateWalletWizard,
    AddWalletChoiceDialog, WalletFilenameDialog,
)
# agent_server is now passed to NetworkTab constructor
from ..networks import NETWORKS, DEFAULT_NETWORK, MultiNetworkBalanceFetcher, format_address, Balance
# Note: Do NOT import get_wallet_dir or get_app_dir here. Use core methods instead.
# See ARCHITECTURE.md "Common Mistakes" section.

# MultiClaw wallet filename
MULTICLAW_WALLET_FILE = "multiclaw.wallet"


# ============================================
# Balance Fetcher Thread
# ============================================

class BalanceFetcherThread(QThread):
    """Background thread for fetching balances."""

    balances_updated = pyqtSignal(dict)  # chain_id -> list[Balance]

    def __init__(self, address: str, custom_rpcs: Optional[dict[int, str]] = None):
        super().__init__()
        self.address = address
        self.custom_rpcs = custom_rpcs

    def run(self):
        import logging
        logger = logging.getLogger(__name__)
        try:
            fetcher = MultiNetworkBalanceFetcher(custom_rpcs=self.custom_rpcs)
            balances = fetcher.get_all_balances(self.address)
            self.balances_updated.emit(balances)
        except Exception as e:
            logger.warning(f"Balance fetch error: {e}")
            self.balances_updated.emit({})


# ============================================
# Policies Tab
# ============================================

class PoliciesTab(QWidget):
    """Tab for managing spend policies."""

    policy_changed = pyqtSignal()
    policy_deleted = pyqtSignal(str, list)  # policy_id, list of decommissioned agent names
    activity = pyqtSignal(str, bool)  # message, is_error

    def __init__(self, core):
        """
        Args:
            core: MultiClaw core instance
        """
        super().__init__()
        self.core = core

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        add_btn = QPushButton("+ New Policy")
        add_btn.clicked.connect(self.add_policy)
        toolbar.addWidget(add_btn)

        toolbar.addStretch()

        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Name", "Networks", "Daily Limit", "Per Request", "Auto-Approve", "Domains", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 80)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.on_row_double_clicked)

        self.populate_table()
        layout.addWidget(self.table)

        help_text = QLabel(
            "Spend policies control how much agents can spend. "
            "Double-click to edit."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(f"color: {Theme.CHARCOAL}; margin-top: 8px;")
        layout.addWidget(help_text)

    def populate_table(self):
        """Refresh the table with current policies."""
        policies = self.core.get_all_policies()
        self.table.setRowCount(len(policies))

        for row, policy in enumerate(policies):
            self.table.setItem(row, 0, QTableWidgetItem(policy.name))

            network_names = []
            for chain_id in (policy.networks or []):
                network = NETWORKS.get(chain_id)
                if network:
                    network_names.append(network.display_name)
            self.table.setItem(row, 1, QTableWidgetItem(", ".join(network_names) or "None"))

            self.table.setItem(row, 2, QTableWidgetItem(policy.format_daily_limit()))
            self.table.setItem(row, 3, QTableWidgetItem(policy.format_per_request_max()))
            self.table.setItem(row, 4, QTableWidgetItem(policy.format_auto_approve()))
            self.table.setItem(row, 5, QTableWidgetItem(policy.format_domain_restrictions()))

            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.setSpacing(4)

            delete_btn = QPushButton("X")
            delete_btn.setFixedSize(28, 24)
            delete_btn.setToolTip("Delete")
            delete_btn.setStyleSheet(f"font-size: 12px; font-weight: bold; background: {Theme.RUST}; color: {Theme.WHITE}; border-radius: 3px;")
            delete_btn.clicked.connect(lambda checked, p=policy: self.delete_policy(p))
            actions_layout.addWidget(delete_btn)

            actions_layout.addStretch()
            self.table.setCellWidget(row, 6, actions_widget)

    def add_policy(self):
        """Show dialog to create a new policy."""
        dialog = NewPolicyDialog(self, core=self.core)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            policy_data = dialog.get_policy_data()
            policy = self.core.create_policy(**policy_data)
            self.populate_table()
            self.policy_changed.emit()
            self.activity.emit(f"Policy '{policy.name}' created", False)

    def edit_policy(self, policy: SpendPolicy):
        """Show dialog to edit an existing policy."""
        dialog = NewPolicyDialog(self, policy, core=self.core)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            policy_data = dialog.get_policy_data()
            # Update policy fields from dialog data
            policy.name = policy_data["name"]
            policy.daily_limit_micro = policy_data["daily_limit_micro"]
            policy.per_request_max_micro = policy_data["per_request_max_micro"]
            policy.auto_approve_below_micro = policy_data["auto_approve_below_micro"]
            policy.allowed_domains = policy_data.get("allowed_domains", [])
            policy.blocked_domains = policy_data.get("blocked_domains", [])
            policy.networks = policy_data.get("networks", [])
            # Call core with updated policy object (same as Console)
            self.core.update_policy(policy)
            self.populate_table()
            self.policy_changed.emit()
            self.activity.emit(f"Policy '{policy.name}' updated", False)

    def delete_policy(self, policy: SpendPolicy):
        """Delete a policy after confirmation."""
        # Check if any agents use this policy
        agents_using = [a.name for a in self.core.get_all_agents() if a.policy_id == policy.id]

        if agents_using:
            message = (
                f"Delete policy '{policy.name}'?\n\n"
                f"This will decommission {len(agents_using)} agent(s):\n"
                f"{', '.join(agents_using[:5])}"
            )
            if len(agents_using) > 5:
                message += f" (+{len(agents_using) - 5} more)"
        else:
            message = f"Delete policy '{policy.name}'?\n\nThis cannot be undone."

        if ask_question(self, "Delete Policy", message):
            decommissioned = self.core.delete_policy(policy.id)
            self.populate_table()
            self.policy_changed.emit()
            self.policy_deleted.emit(policy.id, decommissioned)

    def on_row_double_clicked(self, index):
        """Handle double-click on a table row to edit the policy."""
        row = index.row()
        policies = self.core.get_all_policies()
        if 0 <= row < len(policies):
            self.edit_policy(policies[row])




# ============================================
# Agents Tab
# ============================================

class AgentsTab(QWidget):
    """Tab showing registered agents."""

    agent_changed = pyqtSignal()
    activity = pyqtSignal(str, bool)  # message, is_error

    def __init__(self, core):
        """
        Args:
            core: MultiClaw core instance
        """
        super().__init__()
        self.core = core
        self.wallets: list[WalletInfo] = []
        self.get_wallet_fn = None  # Set by MainWindow for wallet access

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        add_btn = QPushButton("+ Register Agent")
        add_btn.clicked.connect(self.register_agent)
        toolbar.addWidget(add_btn)

        toolbar.addStretch()

        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Name", "Code", "Verify Key", "Policy", "Spent Today", "Status", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(6, 80)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.on_row_double_clicked)

        self.populate_table()
        layout.addWidget(self.table)

        help_text = QLabel(
            "Register agents to generate tokens. Commission them with a spend policy to enable signing. "
            "Double-click to edit."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(f"color: {Theme.CHARCOAL}; margin-top: 8px;")
        layout.addWidget(help_text)

    def populate_table(self):
        """Refresh the table with current agents."""
        agents = self.core.get_all_agents()
        self.table.setRowCount(len(agents))

        for row, agent in enumerate(agents):
            self.table.setItem(row, 0, QTableWidgetItem(agent.name))

            id_item = QTableWidgetItem(agent.id)
            id_item.setFont(QFont(Theme.MONO_FONT, 9))
            self.table.setItem(row, 1, id_item)

            pubkey_short = agent.auth_key[:8] + "..." + agent.auth_key[-6:]
            pubkey_item = QTableWidgetItem(pubkey_short)
            pubkey_item.setFont(QFont(Theme.MONO_FONT, 9))
            self.table.setItem(row, 2, pubkey_item)

            if agent.policy_id:
                policy = self.core.get_policy(agent.policy_id)
                policy_name = policy.name if policy else "Unknown"
            else:
                policy_name = "—"
            self.table.setItem(row, 3, QTableWidgetItem(policy_name))

            self.table.setItem(row, 4, QTableWidgetItem(agent.format_spent_today()))

            status_item = QTableWidgetItem(agent.status)
            if agent.status == "active":
                status_item.setForeground(QColor(Theme.LIME_DIM))
            elif agent.status == "suspended":
                status_item.setForeground(QColor(Theme.ERROR))
            elif agent.status == "limit_reached":
                status_item.setForeground(QColor(Theme.WARNING))
            else:
                status_item.setForeground(QColor(Theme.CHARCOAL))
            self.table.setItem(row, 5, status_item)

            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.setSpacing(4)

            # Primary action button: Commission / Activate / Suspend
            primary_btn = QPushButton()
            primary_btn.setFixedSize(28, 24)

            if agent.status == "uncommissioned":
                # ^ for commission
                primary_btn.setText("^")
                primary_btn.setToolTip("Commission")
                primary_btn.setStyleSheet(f"font-size: 14px; font-weight: bold; background: {Theme.LIME}; color: {Theme.BLACK}; border-radius: 3px;")
                primary_btn.clicked.connect(lambda checked, a=agent: self.commission_agent(a))
            elif agent.status == "suspended":
                # > for enable (play)
                primary_btn.setText(">")
                primary_btn.setToolTip("Enable")
                primary_btn.setStyleSheet(f"font-size: 14px; font-weight: bold; background: {Theme.LIME}; color: {Theme.BLACK}; border-radius: 3px;")
                primary_btn.clicked.connect(lambda checked, a=agent: self.activate_agent(a))
            elif agent.status == "active":
                # II for disable (pause)
                primary_btn.setText("II")
                primary_btn.setToolTip("Disable")
                primary_btn.setStyleSheet(f"font-size: 11px; font-weight: bold; background: {Theme.RUST}; color: {Theme.WHITE}; border-radius: 3px;")
                primary_btn.clicked.connect(lambda checked, a=agent: self.suspend_agent(a))
            else:
                # limit_reached or other states - show disable option
                primary_btn.setText("II")
                primary_btn.setToolTip("Disable")
                primary_btn.setStyleSheet(f"font-size: 11px; font-weight: bold; background: {Theme.RUST}; color: {Theme.WHITE}; border-radius: 3px;")
                primary_btn.clicked.connect(lambda checked, a=agent: self.suspend_agent(a))

            actions_layout.addWidget(primary_btn)

            # Delete button - always available
            delete_btn = QPushButton("X")
            delete_btn.setFixedSize(28, 24)
            delete_btn.setToolTip("Delete")
            delete_btn.setStyleSheet(f"font-size: 12px; font-weight: bold; background: {Theme.RUST}; color: {Theme.WHITE}; border-radius: 3px;")
            delete_btn.clicked.connect(lambda checked, a=agent: self.delete_agent(a))
            actions_layout.addWidget(delete_btn)

            actions_layout.addStretch()
            self.table.setCellWidget(row, 6, actions_widget)

    def register_agent(self):
        """Show dialog to register a new agent."""
        # Check if wallet is unlocked (core needs it for agent secret encryption)
        if not self.core.is_wallet_unlocked():
            QMessageBox.warning(
                self,
                "Wallet Required",
                "Please unlock a wallet first before registering an agent.\n\n"
                "Agent credentials are encrypted with your wallet password for security."
            )
            return

        dialog = AgentRegistrationDialog(self.core, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            agent = dialog.get_agent()
            # Agent already created via core.create_agent() in dialog
            self.populate_table()
            self.agent_changed.emit()
            self.activity.emit(f"Agent '{agent.name}' registered (ID: {agent.id})", False)

    def commission_agent(self, agent: Agent):
        """Show dialog to commission an agent with a policy."""
        dialog = CommissionDialog(agent, self.core, self.wallets, self.get_wallet_fn, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Core already updated the agent - just refresh display
            self.populate_table()
            self.agent_changed.emit()

            # Get fresh agent data from core for accurate logging
            updated_agent = self.core.get_agent_by_code(agent.code)
            policy = self.core.get_policy(updated_agent.policy_id) if updated_agent and updated_agent.policy_id else None
            policy_name = policy.name if policy else "Unknown"
            self.activity.emit(f"Agent '{agent.name}' commissioned with policy '{policy_name}'", False)

            # Log Intent Mandate generation
            mandate = dialog.get_intent_mandate()
            if mandate:
                mandate_id = mandate.get('id', 'unknown')[:8]
                self.activity.emit(f"Intent Mandate generated for '{agent.name}' (ID: {mandate_id}...)", False)
                # Log registry upload if it happened
                if mandate.get('registryUrl'):
                    self.activity.emit(f"Mandate published to: {mandate.get('registryUrl')}", False)

    def suspend_agent(self, agent: Agent):
        """Suspend an active agent."""
        if ask_question(
            self,
            "Suspend Agent",
            f"Suspend agent '{agent.name}'?\n\nThis will reject all signing requests from this agent."
        ):
            self.core.suspend_agent(agent.code)
            self.populate_table()
            self.agent_changed.emit()
            self.activity.emit(f"Agent '{agent.name}' suspended", False)

    def activate_agent(self, agent: Agent):
        """Reactivate a suspended agent."""
        self.core.activate_agent(agent.code)
        self.populate_table()
        self.agent_changed.emit()
        self.activity.emit(f"Agent '{agent.name}' activated", False)

    def delete_agent(self, agent: Agent):
        """Delete an agent."""
        if ask_question(
            self,
            "Delete Agent",
            f"Delete agent '{agent.name}'?\n\nThis cannot be undone."
        ):
            self.core.delete_agent(agent.code)
            self.populate_table()
            self.agent_changed.emit()
            self.activity.emit(f"Agent '{agent.name}' deleted", False)

    def on_row_double_clicked(self, index):
        """Handle double-click on a table row to edit the agent."""
        row = index.row()
        agents = self.core.get_all_agents()
        if 0 <= row < len(agents):
            self.edit_agent(agents[row])

    def edit_agent(self, agent: Agent):
        """Show dialog to edit an agent's policy and wallet."""
        old_policy_id = agent.policy_id
        old_wallet = agent.wallet_address
        old_status = agent.status
        old_mandate = agent.intent_mandate

        dialog = EditAgentDialog(agent, self.core, self.wallets, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        mandate_revoked = dialog.was_mandate_revoked()

        # If mandate was revoked, always save even if dialog was cancelled
        if accepted or mandate_revoked:
            self.core.update_agent(agent)
            self.populate_table()
            self.agent_changed.emit()

            # Log what changed
            changes = []
            if agent.policy_id != old_policy_id:
                if agent.policy_id:
                    policy = self.core.get_policy(agent.policy_id)
                    changes.append(f"policy → {policy.name if policy else 'Unknown'}")
                else:
                    changes.append("policy removed")
            if agent.wallet_address != old_wallet:
                if agent.wallet_address:
                    changes.append(f"wallet → {agent.wallet_address[:10]}...")
                else:
                    changes.append("wallet removed")
            if agent.status != old_status:
                changes.append(f"status → {agent.status}")
            if mandate_revoked and old_mandate is not None:
                changes.append("mandate revoked")

            if changes:
                self.activity.emit(f"Agent '{agent.name}' updated: {', '.join(changes)}", False)


# ============================================
# History Tab
# ============================================

class HistoryTab(QWidget):
    """Tab showing transaction history."""

    # Status colors for the lifecycle
    STATUS_COLORS = {
        "received": "#888888",    # Gray
        "signed": "#4A90D9",      # Blue
        "rejected": Theme.ERROR,  # Red
        "submitted": "#D9A74A",   # Amber
        "settled": Theme.SUCCESS, # Green
        "failed": Theme.ERROR,    # Red
    }

    def __init__(self, core):
        """
        Args:
            core: MultiClaw core instance
        """
        super().__init__()
        self.core = core
        self._transactions: list[Transaction] = []

        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Filter:"))

        self.agent_filter = QComboBox()
        self.agent_filter.addItem("All Agents", None)
        self.agent_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.agent_filter)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Status", "Signed", "Settled", "Rejected", "Pending"])
        self.status_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.status_filter)

        filters.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        filters.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_history)
        filters.addWidget(clear_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv)
        filters.addWidget(export_btn)

        layout.addLayout(filters)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Time", "Agent", "Amount", "Resource", "Status", "Wallet"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 60)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.on_row_double_clicked)

        layout.addWidget(self.table)

        self.empty_label = QLabel("No transactions yet")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #666; font-size: 14px; padding: 40px;")
        layout.addWidget(self.empty_label)

        # Auto-refresh timer (every 5 seconds)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(5000)

        self.refresh()

    def refresh(self):
        """Reload transactions from core."""
        self._transactions = self.core.get_recent_transactions(limit=1000)
        self.update_agent_filter()
        self.apply_filters()

    def clear_history(self):
        """Clear all transaction history after confirmation."""
        count = len(self._transactions)
        if count == 0:
            return

        reply = QMessageBox.question(
            self,
            "Clear History",
            f"Delete all {count} transaction(s) from history?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.core.clear_transactions()
            self.refresh()

    def update_agent_filter(self):
        """Update agent filter dropdown with current agents."""
        current = self.agent_filter.currentData()
        self.agent_filter.blockSignals(True)
        self.agent_filter.clear()
        self.agent_filter.addItem("All Agents", None)

        agent_names = sorted(set(tx.agent_name for tx in self._transactions))
        for name in agent_names:
            self.agent_filter.addItem(name, name)

        if current:
            idx = self.agent_filter.findData(current)
            if idx >= 0:
                self.agent_filter.setCurrentIndex(idx)

        self.agent_filter.blockSignals(False)

    def apply_filters(self):
        """Apply current filters and update table."""
        agent_name = self.agent_filter.currentData()
        status_text = self.status_filter.currentText().lower()

        filtered = self._transactions

        if agent_name:
            filtered = [tx for tx in filtered if tx.agent_name == agent_name]

        if status_text == "signed":
            filtered = [tx for tx in filtered if tx.status in ("signed", "submitted")]
        elif status_text == "settled":
            filtered = [tx for tx in filtered if tx.status == "settled"]
        elif status_text == "rejected":
            filtered = [tx for tx in filtered if tx.status in ("rejected", "failed")]
        elif status_text == "pending":
            filtered = [tx for tx in filtered if tx.status in ("received", "signed", "submitted")]
        # "all status" shows everything

        self.populate_table(filtered)

    def populate_table(self, transactions: list[Transaction]):
        """Populate table with transactions."""
        self.table.setRowCount(len(transactions))

        self.empty_label.setVisible(len(transactions) == 0)
        self.table.setVisible(len(transactions) > 0)

        for row, tx in enumerate(transactions):
            # Store transaction ID in the first column for double-click lookup
            time_item = QTableWidgetItem(tx.format_time())
            time_item.setData(Qt.ItemDataRole.UserRole, tx.id)
            self.table.setItem(row, 0, time_item)

            # Agent name with ID
            agent_text = f"{tx.agent_name} ({tx.agent_id})"
            self.table.setItem(row, 1, QTableWidgetItem(agent_text))

            self.table.setItem(row, 2, QTableWidgetItem(tx.format_amount()))

            # Show resource URL if available, otherwise recipient address
            resource = tx.resource or tx.recipient
            if len(resource) > 40:
                resource = resource[:37] + "..."
            self.table.setItem(row, 3, QTableWidgetItem(resource))

            # Status with color coding and verification indicator
            status_text = tx.status.upper()
            color = self.STATUS_COLORS.get(tx.status, "#888888")

            # Override color and text for settled transactions based on verification
            if tx.status == "settled":
                if tx.verification_status == "verified":
                    status_text = "SETTLED ✓"
                    color = Theme.SUCCESS  # Green
                elif tx.verification_status == "not_found":
                    status_text = "SETTLED ✗"
                    color = Theme.ERROR  # Red
                elif tx.verification_status == "failed":
                    status_text = "SETTLED ✗"
                    color = Theme.ERROR  # Red
                elif tx.verification_status == "pending":
                    status_text = "SETTLED"
                    color = "#D9A74A"  # Amber
                # else: no verification_status = green SETTLED (default, presumed ok)

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(color))
            self.table.setItem(row, 4, status_item)

            # Wallet ID
            wallet_text = tx.wallet_id or ""
            wallet_item = QTableWidgetItem(wallet_text)
            wallet_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, wallet_item)

    def on_row_double_clicked(self, index):
        """Handle double-click on a row to show transaction details."""
        row = index.row()
        time_item = self.table.item(row, 0)
        if time_item:
            tx_id = time_item.data(Qt.ItemDataRole.UserRole)
            if tx_id:
                tx = self.core.get_transaction(tx_id)
                if tx:
                    self.show_transaction_detail(tx)

    def show_transaction_detail(self, tx: Transaction):
        """Show a dialog with full transaction details."""
        from .dialogs import TransactionDetailDialog
        dialog = TransactionDetailDialog(tx, self.core, self)
        dialog.exec()

    def export_csv(self):
        """Export transactions to CSV file."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Transactions", "transactions.csv", "CSV Files (*.csv)"
        )
        if not filename:
            return

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "Agent", "ID", "Amount", "Recipient", "Resource",
                    "Network", "Status", "Auto", "Wallet ID", "TX Hash"
                ])
                for tx in self._transactions:
                    writer.writerow([
                        tx.timestamp,
                        tx.agent_name,
                        tx.agent_id,
                        tx.format_amount(),
                        tx.recipient,
                        tx.resource or "",
                        tx.network,
                        tx.status,
                        "Yes" if tx.auto_approved else "No",
                        tx.wallet_id or "",
                        tx.tx_hash or ""
                    ])
            QMessageBox.information(self, "Export Complete", f"Exported {len(self._transactions)} transactions to {filename}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Could not export: {e}")


# ============================================
# Wallet Tab (New Multi-Seed Architecture)
# ============================================

class WalletTab(QWidget):
    """Tab for managing the wallet with multiple seeds and addresses."""

    wallets_changed = pyqtSignal(list)  # Emitted when address list changes (list of AddressEntry)
    wallet_deleted = pyqtSignal(str)    # Emitted when address deleted (0x address for agent cleanup)
    wallet_locked = pyqtSignal()        # Emitted when wallet is locked
    wallet_unlocked = pyqtSignal()      # Emitted when wallet is unlocked
    wallet_path_changed = pyqtSignal(str)  # Emitted when wallet path changes (for settings persistence)
    activity = pyqtSignal(str, bool)    # Activity log (message, is_error)

    def __init__(self, core):
        super().__init__()

        self.core = core  # MultiClaw core instance (required)
        self._wallet: Optional[MultiClawWallet] = None
        wallet_dir = core.get_wallet_dir()
        self._wallet_path = wallet_dir / MULTICLAW_WALLET_FILE
        self._custom_rpcs: dict[int, str] = {}
        self._balance_threads: list = []
        self._selected_network_chain_id: int = 1  # Ethereum Mainnet - first in list

        # Lock state
        self._is_unlocked = False

        # Callback to get agents linked to an address (set by main_window)
        # Signature: (wallet_address: str) -> list[Agent]
        self._get_agents_for_address = None

        # Auto-lock timer (0 = disabled)
        self._auto_lock_minutes = 0
        self._auto_lock_timer = QTimer()
        self._auto_lock_timer.setSingleShot(True)
        self._auto_lock_timer.timeout.connect(self._on_auto_lock_timeout)

        layout = QVBoxLayout(self)

        # Lock overlay - shown when wallet is locked
        self.lock_overlay = QWidget()
        lock_layout = QVBoxLayout(self.lock_overlay)
        lock_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lock_icon = QLabel("🔒")
        lock_icon.setStyleSheet("font-size: 48px;")
        lock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lock_layout.addWidget(lock_icon)

        lock_title = QLabel("Wallet Locked")
        lock_title.setFont(QFont("", 14, QFont.Weight.Bold))
        lock_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lock_layout.addWidget(lock_title)

        lock_subtitle = QLabel("Enter your password to unlock")
        lock_subtitle.setStyleSheet(f"color: {Theme.CHARCOAL};")
        lock_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lock_layout.addWidget(lock_subtitle)

        lock_layout.addSpacing(16)

        # Password input row
        pw_layout = QHBoxLayout()
        pw_layout.addStretch()

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password")
        self.password_input.setMaximumWidth(200)
        self.password_input.returnPressed.connect(self.try_unlock)
        pw_layout.addWidget(self.password_input)

        unlock_btn = QPushButton("Unlock")
        unlock_btn.clicked.connect(self.try_unlock)
        pw_layout.addWidget(unlock_btn)

        pw_layout.addStretch()
        lock_layout.addLayout(pw_layout)

        self.lock_error_label = QLabel("")
        self.lock_error_label.setStyleSheet(f"color: {Theme.ERROR};")
        self.lock_error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lock_layout.addWidget(self.lock_error_label)

        layout.addWidget(self.lock_overlay)

        # Main content (shown when unlocked)
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Warning banner for unencrypted wallets
        self.unencrypted_warning = QLabel(
            "⚠️ Warning: This wallet has no password set and is NOT encrypted. "
            "Your private keys are stored in plaintext."
        )
        self.unencrypted_warning.setWordWrap(True)
        self.unencrypted_warning.setStyleSheet(
            "background-color: #FFF3CD; color: #856404; padding: 8px; "
            "border: 1px solid #FFECB5; border-radius: 4px; margin-bottom: 8px;"
        )
        self.unencrypted_warning.setVisible(False)
        content_layout.addWidget(self.unencrypted_warning)

        toolbar = QHBoxLayout()

        # Button changes based on whether wallet exists
        self.add_btn = QPushButton("+ Add Wallet")
        self.add_btn.clicked.connect(self.on_add_button)
        toolbar.addWidget(self.add_btn)

        toolbar.addStretch()

        # Network selector dropdown
        self.network_combo = QComboBox()
        self.network_combo.setToolTip("Select network for balance display")
        self.network_combo.setFixedWidth(140)
        for chain_id, network in NETWORKS.items():
            self.network_combo.addItem(network.display_name, chain_id)
            if chain_id == self._selected_network_chain_id:
                self.network_combo.setCurrentIndex(self.network_combo.count() - 1)
        self.network_combo.currentIndexChanged.connect(self._on_network_changed)
        toolbar.addWidget(self.network_combo)

        # Sweep button
        self.sweep_btn = QPushButton("Sweep")
        self.sweep_btn.setToolTip("Sweep USDC from multiple addresses to one recipient")
        self.sweep_btn.clicked.connect(self._on_sweep_clicked)
        self.sweep_btn.setVisible(False)  # Only show when wallet loaded
        toolbar.addWidget(self.sweep_btn)

        # Wallet name label (center-right of toolbar)
        self.wallet_label = QLabel("")
        self.wallet_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
        toolbar.addWidget(self.wallet_label)

        # Detach wallet button (visible when wallet loaded)
        self.detach_btn = QPushButton("Detach")
        self.detach_btn.setToolTip("Unload this wallet without deleting it")
        self.detach_btn.clicked.connect(self._on_detach_wallet)
        self.detach_btn.setVisible(False)
        toolbar.addWidget(self.detach_btn)

        # Delete wallet button (visible when wallet loaded)
        self.delete_wallet_btn = QPushButton("Delete")
        self.delete_wallet_btn.setToolTip("Delete this wallet file permanently")
        self.delete_wallet_btn.clicked.connect(self._on_delete_wallet)
        self.delete_wallet_btn.setVisible(False)
        toolbar.addWidget(self.delete_wallet_btn)

        content_layout.addLayout(toolbar)

        # New table structure: Seed | Name | Address | Balance | Actions
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Seed", "Name", "Address", "Balance", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 80)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._on_table_double_click)

        content_layout.addWidget(self.table)

        help_text = QLabel(
            "Double-click a wallet to withdraw USDC. "
            "Each agent is linked to an address for signing payments."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(f"color: {Theme.CHARCOAL}; margin-top: 8px;")
        content_layout.addWidget(help_text)

        layout.addWidget(self.content_widget)

        # Initialize state
        self._update_display()

    def _wallet_exists(self) -> bool:
        """Check if the primer.wallet file exists."""
        return self._wallet_path.exists()

    def _is_wallet_encrypted(self) -> bool:
        """Check if the wallet file is encrypted."""
        if not self._wallet_exists():
            return True  # Assume encrypted for non-existent
        return MultiClawWallet.is_file_encrypted(self._wallet_path)

    def _update_display(self):
        """Update UI based on current state."""
        wallet_exists = self._wallet_exists()

        # Update wallet label (just filename, no prefix)
        if wallet_exists:
            self.wallet_label.setText(self._wallet_path.name)
        else:
            self.wallet_label.setText("")

        if not wallet_exists:
            # No wallet yet - show content with "+ Add Wallet" button
            self.lock_overlay.setVisible(False)
            self.content_widget.setVisible(True)
            self.add_btn.setText("+ Add Wallet")
            self.unencrypted_warning.setVisible(False)
            self.table.setRowCount(0)
            # Hide wallet management buttons
            self.detach_btn.setVisible(False)
            self.delete_wallet_btn.setVisible(False)
            self.sweep_btn.setVisible(False)
        elif not self._is_wallet_encrypted():
            # Unencrypted wallet - auto-unlock and show warning
            self.lock_overlay.setVisible(False)
            self.content_widget.setVisible(True)
            self.add_btn.setText("+ Add Address")
            self.unencrypted_warning.setVisible(True)
            # Show wallet management buttons
            self.detach_btn.setVisible(True)
            self.delete_wallet_btn.setVisible(True)
            self.sweep_btn.setVisible(True)
            if not self._is_unlocked:
                self._auto_unlock()
            else:
                # Already unlocked (e.g., just created) - still need to populate
                self.populate_table()
        elif self._is_unlocked:
            # Unlocked encrypted wallet
            self.lock_overlay.setVisible(False)
            self.content_widget.setVisible(True)
            self.add_btn.setText("+ Add Address")
            self.unencrypted_warning.setVisible(False)
            # Show wallet management buttons
            self.detach_btn.setVisible(True)
            self.delete_wallet_btn.setVisible(True)
            self.sweep_btn.setVisible(True)
            self.populate_table()
        else:
            # Locked encrypted wallet
            self.lock_overlay.setVisible(True)
            self.content_widget.setVisible(False)
            self.unencrypted_warning.setVisible(False)
            # Hide wallet management buttons when locked
            self.detach_btn.setVisible(False)
            self.delete_wallet_btn.setVisible(False)
            self.sweep_btn.setVisible(False)

    def _auto_unlock(self):
        """Auto-unlock an unencrypted wallet."""
        if not self.core:
            return

        result = self.core.load_wallet(str(self._wallet_path), NO_PASSWORD_SENTINEL)
        if result.get("success"):
            self._wallet = self.core.get_wallet()
            self._is_unlocked = True
            self.populate_table()
            self.wallet_unlocked.emit()
            self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])
        else:
            import logging
            logging.getLogger(__name__).warning(f"Failed to auto-unlock wallet: {result.get('error')}")

    @property
    def is_unlocked(self) -> bool:
        """Check if wallet is unlocked."""
        if not self._wallet_exists():
            return True  # No wallet = effectively unlocked (nothing to protect)
        if not self._is_wallet_encrypted():
            return True  # Unencrypted = always unlocked
        return self._is_unlocked

    @property
    def has_wallets(self) -> bool:
        """Check if any addresses exist."""
        if self._wallet:
            return len(self._wallet.addresses) > 0
        return self._wallet_exists()

    def set_agents_query_fn(self, fn):
        """Set callback function to query agents by wallet address.

        Args:
            fn: Function with signature (wallet_address: str) -> list[Agent]
        """
        self._get_agents_for_address = fn

    def set_wallet_path(self, path: str):
        """Set the wallet path (called from settings on startup)."""
        if path:
            from pathlib import Path
            self._wallet_path = Path(path)
            self._update_display()

    def get_wallet_path(self) -> str:
        """Get the current wallet path as string."""
        return str(self._wallet_path) if self._wallet_path else ""

    def _emit_path_changed(self):
        """Emit wallet path changed signal for settings persistence."""
        self.wallet_path_changed.emit(str(self._wallet_path))

    def sync_from_core(self):
        """Sync wallet state from core (called when core wallet state changes externally)."""
        if not self.core:
            return

        core_unlocked = self.core.is_wallet_unlocked()
        core_path = self.core.get_wallet_path()

        if core_unlocked and not self._is_unlocked:
            # Core has an unlocked wallet but we don't - sync our state
            self._wallet = self.core.get_wallet()
            self._is_unlocked = True
            if core_path:
                from pathlib import Path
                new_path = Path(core_path)
                if self._wallet_path != new_path:
                    self._wallet_path = new_path
                    self._emit_path_changed()

            self.password_input.clear()
            self.lock_error_label.setText("")
            self._update_display()
            self.wallet_unlocked.emit()
            self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])
            self.activity.emit("Wallet unlocked", False)

            # Start auto-lock timer if configured
            if self._auto_lock_minutes > 0:
                self._reset_auto_lock_timer()

            # Refresh balances
            QTimer.singleShot(500, self.refresh_all_balances)
        elif not core_unlocked and self._is_unlocked:
            # Core wallet is locked but we think it's unlocked - sync our state
            self._auto_lock_timer.stop()
            self._wallet = None
            self._is_unlocked = False
            self._update_display()
            self.wallet_locked.emit()

    def try_unlock(self):
        """Try to unlock the wallet with the entered password."""
        if not self.core:
            self.lock_error_label.setText("Error: Core not available")
            return

        # Empty password is allowed (wallets can have no password)
        password = self.password_input.text()

        result = self.core.load_wallet(str(self._wallet_path), password)

        if result.get("success"):
            self._wallet = self.core.get_wallet()  # Get reference for display
            self._is_unlocked = True

            self.password_input.clear()
            self.lock_error_label.setText("")
            self._update_display()
            self.wallet_unlocked.emit()
            self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])
            self.activity.emit("Wallet unlocked", False)

            # Start auto-lock timer if configured
            if self._auto_lock_minutes > 0:
                self._reset_auto_lock_timer()

            # Refresh balances
            QTimer.singleShot(500, self.refresh_all_balances)
        else:
            error = result.get("error", "Unknown error")
            if "password" in error.lower():
                self.lock_error_label.setText("Wrong password")
            elif "not found" in error.lower():
                self.lock_error_label.setText("Wallet file not found")
                self._update_display()
            else:
                self.lock_error_label.setText(f"Error: {error[:50]}")
            self.password_input.clear()
            self.password_input.setFocus()

    def lock(self):
        """Lock the wallet, clearing sensitive data from memory."""
        self._auto_lock_timer.stop()

        if self.core:
            self.core.lock_wallet()

        self._wallet = None
        self._is_unlocked = False
        self._update_display()
        self.wallet_locked.emit()

    def set_auto_lock_timeout(self, minutes: int):
        """Set the auto-lock timeout in minutes (0 = disabled)."""
        self._auto_lock_minutes = minutes
        if self._is_unlocked and minutes > 0:
            self._reset_auto_lock_timer()
        elif minutes == 0:
            self._auto_lock_timer.stop()

    def reset_activity(self):
        """Reset the auto-lock timer due to user activity."""
        if self._is_unlocked and self._auto_lock_minutes > 0:
            self._reset_auto_lock_timer()

    def _reset_auto_lock_timer(self):
        """Reset the auto-lock timer."""
        if self._auto_lock_minutes > 0:
            self._auto_lock_timer.start(self._auto_lock_minutes * 60 * 1000)

    def _on_auto_lock_timeout(self):
        """Handle auto-lock timer expiration."""
        if self._is_unlocked:
            self.activity.emit("Auto-locking wallet due to inactivity", False)
            self.lock()

    def get_unlocked_wallet(self, address: str) -> Optional[MultiClawWallet]:
        """Get the unlocked wallet if the address exists in it."""
        if self._wallet:
            entry = self._wallet.get_address_by_address(address)
            if entry:
                return self._wallet
        return None

    def populate_table(self):
        """Refresh the table with current addresses."""
        if not self._wallet:
            self.table.setRowCount(0)
            return

        addresses = self._wallet.addresses
        self.table.setRowCount(len(addresses))

        for row, addr in enumerate(addresses):
            # Seed column: show seed_id or "—" for imported
            seed_text = addr.seed_id if addr.seed_id else "—"
            if addr.seed_id and addr.index is not None:
                seed_text = f"{addr.seed_id} #{addr.index}"
            seed_item = QTableWidgetItem(seed_text)
            seed_item.setFont(QFont(Theme.MONO_FONT, 9))
            self.table.setItem(row, 0, seed_item)

            # Name
            name_item = QTableWidgetItem(addr.name)
            self.table.setItem(row, 1, name_item)

            # Address (truncated for display)
            addr_display = f"{addr.address[:10]}...{addr.address[-8:]}"
            addr_item = QTableWidgetItem(addr_display)
            addr_item.setFont(QFont(Theme.MONO_FONT, 9))
            addr_item.setToolTip(addr.address)
            addr_item.setData(Qt.ItemDataRole.UserRole, addr.address)  # Store full address
            self.table.setItem(row, 2, addr_item)

            # Balance
            balance_item = QTableWidgetItem("...")
            balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, balance_item)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.setSpacing(4)

            delete_btn = QPushButton("X")
            delete_btn.setFixedSize(28, 24)
            delete_btn.setToolTip("Remove address")
            delete_btn.setStyleSheet(f"font-size: 12px; font-weight: bold; background: {Theme.RUST}; color: {Theme.WHITE}; border-radius: 3px;")
            delete_btn.clicked.connect(lambda checked, aid=addr.id: self.delete_address(aid))
            actions_layout.addWidget(delete_btn)

            actions_layout.addStretch()
            self.table.setCellWidget(row, 4, actions_widget)

    def _on_table_double_click(self, index):
        """Handle double-click on a wallet row - open withdraw dialog."""
        if not self._wallet or not self._is_unlocked:
            return

        row = index.row()
        if row < 0 or row >= self.table.rowCount():
            return

        # Get the address from column 2 (Address column)
        addr_item = self.table.item(row, 2)
        if not addr_item:
            return

        full_address = addr_item.data(Qt.ItemDataRole.UserRole)
        if not full_address:
            return

        # Find the AddressEntry
        entry = self._wallet.get_address_by_address(full_address)
        if not entry:
            return

        # Get balance from table (full precision stored in UserRole)
        balance = 0.0
        balance_item = self.table.item(row, 3)
        if balance_item:
            stored_balance = balance_item.data(Qt.ItemDataRole.UserRole)
            if stored_balance is not None:
                balance = stored_balance
            else:
                # Fallback to parsing text if UserRole not set
                text = balance_item.text().replace("$", "").replace(",", "").replace("...", "0")
                try:
                    balance = float(text)
                except ValueError:
                    balance = 0.0

        # Open withdraw dialog
        from .dialogs import WithdrawUSDCDialog
        # Use core's method to get private keys
        get_key_fn = self.core.get_private_key_for_address if self.core else None
        dialog = WithdrawUSDCDialog(
            wallet_entry=entry,
            balance=balance,
            get_private_key_fn=get_key_fn,
            chain_id=self._selected_network_chain_id,
            parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh balances after successful withdrawal
            self.refresh_all_balances()
            self.activity.emit("USDC withdrawal completed", False)

    def on_add_button(self):
        """Handle the add button click."""
        if not self._wallet_exists():
            # Show choice dialog: Load or Create
            choice_dialog = AddWalletChoiceDialog(self)
            if choice_dialog.exec() != QDialog.DialogCode.Accepted:
                return

            if choice_dialog.choice == 'load':
                self._load_wallet()
            else:  # 'create'
                self._create_wallet()
        else:
            self._add_address()

    def _load_wallet(self):
        """Browse for and load an existing wallet file."""
        if not self.core:
            self.activity.emit("Error: Core not available", True)
            return

        # Start in the data directory
        start_dir = str(self.core.get_wallet_dir())

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Wallet",
            start_dir,
            "Wallet Files (*.wallet);;All Files (*)"
        )

        if not file_path:
            return

        from pathlib import Path
        wallet_path = Path(file_path)

        if not wallet_path.exists():
            QMessageBox.warning(self, "File Not Found", f"Wallet file not found:\n{file_path}")
            return

        # Check if encrypted
        if MultiClawWallet.is_file_encrypted(wallet_path):
            # Show unlock dialog - this prompts for password
            dialog = MultiClawWalletUnlockDialog(wallet_path, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            # Dialog already loaded the wallet, now load through core
            password = dialog.password if hasattr(dialog, 'password') else ""
            result = self.core.load_wallet(str(wallet_path), password)
        else:
            # Load unencrypted through core
            result = self.core.load_wallet(str(wallet_path), NO_PASSWORD_SENTINEL)

        if not result.get("success"):
            QMessageBox.warning(self, "Load Failed", f"Could not load wallet:\n{result.get('error')}")
            return

        # Update local state from core
        self._wallet = self.core.get_wallet()
        self._wallet_path = wallet_path
        self._is_unlocked = True
        self._update_display()
        self._emit_path_changed()
        self.wallet_unlocked.emit()
        self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])
        self.activity.emit(f"Loaded wallet: {wallet_path.name}", False)
        QTimer.singleShot(500, self.refresh_all_balances)

    def _create_wallet(self):
        """Show dialog to create a new wallet with custom filename."""
        if not self.core:
            self.activity.emit("Error: Core not available", True)
            return

        # First, get the filename
        filename_dialog = WalletFilenameDialog(self)
        if filename_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        wallet_filename = filename_dialog.filename
        new_wallet_path = self.core.get_wallet_dir() / wallet_filename

        # Check if file already exists
        if new_wallet_path.exists():
            reply = QMessageBox.question(
                self,
                "File Exists",
                f"A wallet named '{wallet_filename}' already exists.\n\nDo you want to overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Now run the wallet creation wizard
        dialog = CreateWalletWizard(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        password = dialog.password

        # Use core.create_wallet() - this creates, saves, and unlocks the wallet
        if dialog.method == 'import_pkey':
            # Private key import
            result = self.core.create_wallet(
                wallet_path=str(new_wallet_path),
                password=password,
                private_key=dialog.private_key,
                unlock=True
            )
        else:
            # Seed-based (new or imported)
            result = self.core.create_wallet(
                wallet_path=str(new_wallet_path),
                password=password,
                seed_phrase=dialog.seed_phrase,
                derivation_path=dialog.derivation_path,
                address_indices=dialog.selected_indices,
                address_names=dialog.selected_names,
                unlock=True
            )

        if result.get("success"):
            # Get the wallet reference from core (core already created and unlocked it)
            self._wallet = self.core.get_wallet()
            self._wallet_path = new_wallet_path
            self._is_unlocked = True
            self._update_display()
            self._emit_path_changed()
            self.wallet_unlocked.emit()
            self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])

            # Log activity
            addresses = result.get("addresses", [])
            if dialog.method == 'import_pkey':
                if addresses:
                    self.activity.emit(f"Imported private key: {format_address(addresses[0]['address'])}", False)
            else:
                action = "Created" if dialog.method == 'new_seed' else "Imported"
                self.activity.emit(f"{action} wallet with {len(addresses)} address(es)", False)

            self.activity.emit(f"Wallet created: {wallet_filename}", False)
            QTimer.singleShot(500, self.refresh_all_balances)
        else:
            self.activity.emit(f"Error: {result.get('error', 'Unknown error')}", True)
            self._wallet = None

    def _add_address(self):
        """Show dialog to add a new address to existing wallet."""
        if not self._wallet:
            return

        dialog = AddAddressDialog(self._wallet, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.choice == 'existing_seed':
            # Pass the selected seed from the dialog (avoids extra selection step)
            self._handle_existing_seed(dialog.selected_seed_id)
        elif dialog.choice == 'new_seed':
            self._handle_new_seed()
        elif dialog.choice == 'import_seed':
            self._handle_import_seed()
        elif dialog.choice == 'import_pkey':
            self._handle_import_pkey()

    def _handle_existing_seed(self, preselected_seed_id: str = None):
        """Handle deriving from an existing seed."""
        if not self._wallet:
            return

        # Use preselected seed if provided, otherwise show selection dialog
        if preselected_seed_id:
            seed_id = preselected_seed_id
        elif len(self._wallet.seeds) == 1:
            seed_id = self._wallet.seeds[0].id
        else:
            # Show seed selection dialog
            dialog = SeedSelectionDialog(self._wallet, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            seed_id = dialog.selected_seed_id

        # Show derivation browser
        browser = DerivationBrowserDialog(self._wallet, seed_id, self)
        if browser.exec() != QDialog.DialogCode.Accepted:
            return

        # Check if user requested to delete the entire seed
        if browser.delete_seed_requested:
            self._confirm_and_delete_seed(seed_id)
            return

        # Remove addresses that were unchecked
        removed = 0
        removed_addresses = []  # Track 0x addresses for agent cleanup
        for address_id in browser.removed_addresses:
            result = self.core.remove_address(address_id) if self.core else {"success": False}
            if result.get("success"):
                removed_addresses.append(result.get("removed_address"))
                removed += 1

        # Add selected addresses
        added = 0
        for index, name in browser.selected_addresses.items():
            result = self.core.add_address_from_seed(seed_id, index, name) if self.core else {"success": False}
            if result.get("success"):
                added += 1

        # Rename any existing addresses that were edited
        renamed = 0
        for address_id, new_name in browser.edited_existing.items():
            if self.core and self.core.rename_address(address_id, new_name):
                renamed += 1

        if added > 0 or renamed > 0 or removed > 0:
            self._wallet = self.core.get_wallet() if self.core else None  # Refresh local reference
            self.populate_table()
            self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])

            # Emit wallet_deleted for each removed address (for agent cleanup)
            for addr in removed_addresses:
                if addr:
                    self.wallet_deleted.emit(addr)

            if added > 0:
                self.activity.emit(f"Added {added} address{'es' if added > 1 else ''} from {seed_id}", False)
            if renamed > 0:
                self.activity.emit(f"Renamed {renamed} address{'es' if renamed > 1 else ''}", False)
            if removed > 0:
                self.activity.emit(f"Removed {removed} address{'es' if removed > 1 else ''}", False)
            QTimer.singleShot(500, self.refresh_all_balances)

    def _confirm_and_delete_seed(self, seed_id: str):
        """Delete a seed with agent decommission warning."""
        if not self.core or not self._wallet:
            return

        # Get all addresses from this seed
        seed_addresses = self._wallet.get_addresses_for_seed(seed_id)

        if not seed_addresses:
            # No addresses, just delete the seed
            result = self.core.remove_seed(seed_id, remove_addresses=True)
            if result.get("success"):
                self._wallet = self.core.get_wallet()
                self._update_display()
                self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])
                self.activity.emit(f"Deleted seed {seed_id} (no addresses)", False)
            return

        # Collect all linked agents across all addresses in the seed
        all_linked_agents = []
        address_0x_list = []  # For cleanup signals

        for addr in seed_addresses:
            address_0x_list.append(addr.address)
            if self._get_agents_for_address:
                linked = self._get_agents_for_address(addr.address)
                for agent in linked:
                    if agent not in all_linked_agents:
                        all_linked_agents.append(agent)

        # Build warning message
        warning_msg = (
            f"Delete seed '{seed_id}' and all {len(seed_addresses)} address(es)?\n\n"
        )

        if all_linked_agents:
            agent_names = [a.name for a in all_linked_agents]
            if len(agent_names) <= 5:
                agent_list = ", ".join(agent_names)
            else:
                agent_list = ", ".join(agent_names[:5]) + f" (+{len(agent_names) - 5} more)"
            warning_msg += f"The following agents will be DECOMMISSIONED:\n• {agent_list}\n\n"
        else:
            warning_msg += "No agents are linked to these addresses.\n\n"

        warning_msg += "This action cannot be undone."

        reply = QMessageBox.question(
            self,
            "Delete Seed",
            warning_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Delete the seed and all its addresses through core
            result = self.core.remove_seed(seed_id, remove_addresses=True)

            if result.get("success"):
                # Emit wallet_deleted for each address (for agent cleanup)
                for addr_0x in result.get("removed_addresses", []):
                    self.wallet_deleted.emit(addr_0x)

                # Refresh local reference
                self._wallet = self.core.get_wallet()

                # Check if wallet is now empty
                if self.core.is_wallet_empty():
                    self.core.delete_wallet_file()
                    self._wallet = None
                    self._is_unlocked = False

                self._update_display()
                self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])
                self.activity.emit(f"Deleted seed {seed_id} with {len(seed_addresses)} address(es)", False)

    def _handle_new_seed(self):
        """Handle creating a new seed phrase."""
        if not self.core or not self._wallet:
            return

        dialog = NewSeedDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = self.core.add_seed(dialog.seed_phrase)
        if result.get("success"):
            seed_id = result.get("seed_id")
            self._wallet = self.core.get_wallet()  # Refresh local reference
            self.activity.emit(f"Created new seed {seed_id}", False)
            # Open derivation browser for the new seed
            self._handle_existing_seed(seed_id)
        else:
            self.activity.emit(f"Error: {result.get('error')}", True)

    def _handle_import_seed(self):
        """Handle importing a seed phrase."""
        if not self.core or not self._wallet:
            return

        dialog = ImportSeedToWalletDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Check if seed already exists
        existing_seed_ids = {s.id for s in self._wallet.seeds}

        result = self.core.add_seed(dialog.seed_phrase)
        if not result.get("success"):
            self.activity.emit(f"Error: {result.get('error')}", True)
            return

        seed_id = result.get("seed_id")
        self._wallet = self.core.get_wallet()  # Refresh local reference

        if seed_id in existing_seed_ids:
            # Seed already exists - show message and open derivation browser
            QMessageBox.information(
                self,
                "Seed Already Exists",
                f"This seed phrase already exists as {seed_id}.\n\n"
                "Opening the derivation browser to manage addresses."
            )
        else:
            self.activity.emit(f"Imported seed as {seed_id}", False)

        # Open derivation browser for the seed (new or existing)
        self._handle_existing_seed(seed_id)

    def _handle_import_pkey(self):
        """Handle importing a private key."""
        if not self.core or not self._wallet:
            return

        dialog = ImportPrivateKeyToWalletDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = self.core.add_imported_key(dialog.private_key, dialog.name)
        if not result.get("success"):
            self.activity.emit(f"Error: {result.get('error')}", True)
            return

        self._wallet = self.core.get_wallet()  # Refresh local reference
        self.populate_table()
        self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])

        address = result.get("address")
        if address:
            self.activity.emit(f"Imported private key: {format_address(address)}", False)
        QTimer.singleShot(500, self.refresh_all_balances)

    def _on_sweep_clicked(self):
        """Open the sweep USDC dialog."""
        if not self._wallet or not self._is_unlocked:
            QMessageBox.warning(self, "Wallet Required", "Please unlock your wallet first.")
            return

        addresses = self._wallet.addresses
        if len(addresses) < 2:
            QMessageBox.information(
                self, "Not Enough Addresses",
                "Sweep requires at least 2 addresses (sponsor + donor or recipient)."
            )
            return

        from .dialogs import SweepUSDCDialog

        # Use core's method to get private keys
        get_key_fn = self.core.get_private_key_for_address if self.core else None
        dialog = SweepUSDCDialog(
            parent=self,
            addresses=addresses,
            get_private_key_fn=get_key_fn,
            chain_id=self._selected_network_chain_id
        )
        dialog.exec()

        # Refresh balances after sweep
        self.refresh_all_balances()

    def _on_detach_wallet(self):
        """Detach (unload) the current wallet without deleting the file."""
        if not self.core or not self._wallet:
            return

        # Collect all linked agents across all addresses
        all_linked_agents = []
        for addr in self._wallet.addresses:
            if self._get_agents_for_address:
                linked = self._get_agents_for_address(addr.address)
                for agent in linked:
                    if agent not in all_linked_agents:
                        all_linked_agents.append(agent)

        # Build warning message
        warning_msg = f"Detach wallet '{self._wallet_path.name}'?\n\n"
        warning_msg += "The wallet file will NOT be deleted.\n\n"

        if all_linked_agents:
            agent_names = [a.name for a in all_linked_agents]
            if len(agent_names) <= 5:
                agent_list = ", ".join(agent_names)
            else:
                agent_list = ", ".join(agent_names[:5]) + f" (+{len(agent_names) - 5} more)"
            warning_msg += f"The following agents will be DECOMMISSIONED:\n• {agent_list}\n\n"
            warning_msg += "Note: Agents will NOT auto-commission if you re-load this wallet."
        else:
            warning_msg += "No agents are currently linked to this wallet."

        reply = QMessageBox.question(
            self,
            "Detach Wallet",
            warning_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            wallet_name = self._wallet_path.name

            # Emit wallet_deleted for each address (for agent cleanup)
            for addr in self._wallet.addresses:
                self.wallet_deleted.emit(addr.address)

            # Detach through core
            self.core.detach_wallet()
            self._wallet = None
            self._is_unlocked = False
            self._wallet_path = self.core.get_wallet_dir() / MULTICLAW_WALLET_FILE  # Reset to default

            self._update_display()
            self._emit_path_changed()
            self.wallets_changed.emit([])
            self.wallet_locked.emit()
            self.activity.emit(f"Detached wallet: {wallet_name}", False)

    def _on_delete_wallet(self):
        """Delete the wallet file permanently."""
        if not self.core or not self._wallet:
            return

        # Collect all linked agents across all addresses
        all_linked_agents = []
        for addr in self._wallet.addresses:
            if self._get_agents_for_address:
                linked = self._get_agents_for_address(addr.address)
                for agent in linked:
                    if agent not in all_linked_agents:
                        all_linked_agents.append(agent)

        # Create custom confirmation dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Wallet")
        dialog.setModal(True)
        dialog.setFixedWidth(400)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        # Warning message with bold "permanently deleted"
        wallet_name = self._wallet_path.name
        warning_label = QLabel()
        warning_label.setWordWrap(True)
        warning_text = f"Delete wallet '<b>{wallet_name}</b>'?<br><br>"
        warning_text += "The wallet file will be <b>permanently deleted</b>.<br>"
        warning_text += "Make sure you have backed up your seed phrase(s)!<br><br>"

        if all_linked_agents:
            agent_names = [a.name for a in all_linked_agents]
            if len(agent_names) <= 5:
                agent_list = ", ".join(agent_names)
            else:
                agent_list = ", ".join(agent_names[:5]) + f" (+{len(agent_names) - 5} more)"
            warning_text += f"The following agents will be decommissioned:<br>• {agent_list}<br><br>"
        else:
            warning_text += "No agents are currently linked to this wallet.<br><br>"

        warning_text += "This action cannot be undone."
        warning_label.setText(warning_text)
        layout.addWidget(warning_label)

        layout.addSpacing(8)

        # Confirmation input
        confirm_label = QLabel("Type <b>delete my wallet</b> to confirm:")
        layout.addWidget(confirm_label)

        confirm_input = QLineEdit()
        confirm_input.setPlaceholderText("delete my wallet")
        layout.addWidget(confirm_input)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setEnabled(False)
        delete_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(delete_btn)

        layout.addLayout(btn_layout)

        # Enable delete button only when correct phrase is typed
        def on_text_changed(text):
            delete_btn.setEnabled(text.strip().lower() == "delete my wallet")
        confirm_input.textChanged.connect(on_text_changed)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Emit wallet_deleted for each address (for agent cleanup)
        for addr in self._wallet.addresses:
            self.wallet_deleted.emit(addr.address)

        # Delete through core
        self.core.delete_wallet_file()
        self._wallet = None
        self._is_unlocked = False

        # Clear the table immediately
        self.table.setRowCount(0)

        self._wallet_path = self.core.get_wallet_dir() / MULTICLAW_WALLET_FILE  # Reset to default

        self._update_display()
        self._emit_path_changed()
        self.wallets_changed.emit([])
        self.wallet_locked.emit()
        self.activity.emit(f"Deleted wallet: {wallet_name}", False)

    def _save_wallet(self):
        """Save the wallet to disk."""
        if self.core:
            self.core.save_wallet()

    def delete_address(self, address_id: str):
        """Delete an address after confirmation."""
        if not self.core or not self._wallet:
            return

        # Find the address
        addr = None
        for a in self._wallet.addresses:
            if a.id == address_id:
                addr = a
                break

        if not addr:
            return

        # Check for linked agents
        linked_agents = []
        if self._get_agents_for_address:
            linked_agents = self._get_agents_for_address(addr.address)

        warning_msg = (
            f"Remove address '{addr.name}'?\n\n"
            f"Address: {format_address(addr.address)}\n\n"
        )

        if addr.seed_id:
            warning_msg += "This address can be re-derived from the seed later.\n\n"
        else:
            warning_msg += "WARNING: This is an imported private key. Make sure you have a backup!\n\n"

        # Show linked agents if any
        if linked_agents:
            agent_names = [a.name for a in linked_agents]
            if len(agent_names) <= 3:
                agent_list = ", ".join(agent_names)
            else:
                agent_list = ", ".join(agent_names[:3]) + f" (+{len(agent_names) - 3} more)"
            warning_msg += f"The following agents will be DECOMMISSIONED:\n• {agent_list}"
        else:
            warning_msg += "No agents are linked to this address."

        reply = QMessageBox.question(
            self,
            "Remove Address",
            warning_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            result = self.core.remove_address(address_id)

            if result.get("success"):
                removed_address = result.get("removed_address")
                self.wallet_deleted.emit(removed_address)

                # Check if wallet is now empty
                if self.core.is_wallet_empty():
                    self.core.delete_wallet_file()
                    self._wallet = None
                    self._is_unlocked = False
                else:
                    self._wallet = self.core.get_wallet()

                self._update_display()
                self.wallets_changed.emit(self._wallet.addresses if self._wallet else [])
                self.activity.emit(f"Removed address: {format_address(removed_address)}", False)

    def refresh_all_balances(self):
        """Refresh balances for all addresses."""
        if not self._wallet:
            return
        for addr in self._wallet.addresses:
            self.refresh_address_balance(addr.address)

    def refresh_address_balance(self, address: str):
        """Refresh balance for a single address."""
        self.activity.emit(f"Fetching balance for {format_address(address)}...", False)

        thread = BalanceFetcherThread(address, self._custom_rpcs)
        thread.balances_updated.connect(lambda bal, addr=address: self.on_balance_updated(addr, bal))
        self._balance_threads.append(thread)
        thread.start()

    def set_custom_rpcs(self, rpcs: dict[int, str]):
        """Set custom RPC URLs for balance fetching."""
        self._custom_rpcs = rpcs.copy() if rpcs else {}

    def on_balance_updated(self, address: str, balances: dict):
        """Handle balance update for an address."""
        # Get USDC balance for selected network only
        selected_chain = self._selected_network_chain_id
        usdc_balance = 0.0
        if selected_chain in balances:
            for bal in balances[selected_chain]:
                if bal.symbol == "USDC":
                    usdc_balance = bal.formatted
                    break

        # Find row by address
        for row in range(self.table.rowCount()):
            addr_item = self.table.item(row, 2)
            if addr_item and addr_item.data(Qt.ItemDataRole.UserRole) == address:
                balance_item = self.table.item(row, 3)
                if balance_item:
                    balance_item.setText(f"${usdc_balance:.6f}")
                    # Store full precision balance for withdrawal dialog
                    balance_item.setData(Qt.ItemDataRole.UserRole, usdc_balance)
                break

        network_name = NETWORKS.get(selected_chain, {})
        network_display = network_name.display_name if hasattr(network_name, 'display_name') else str(selected_chain)
        self.activity.emit(f"Balance: {format_address(address)} = {usdc_balance:.6f} USDC ({network_display})", False)

    def _on_network_changed(self, index: int):
        """Handle network dropdown selection change."""
        chain_id = self.network_combo.currentData()
        if chain_id and chain_id != self._selected_network_chain_id:
            self._selected_network_chain_id = chain_id
            network = NETWORKS.get(chain_id)
            if network:
                self.activity.emit(f"Switched to {network.display_name}", False)
            # Refresh balances to show selected network
            self.refresh_all_balances()

    def get_wallet_list(self) -> list[AddressEntry]:
        """Get list of all address entries (for other components)."""
        if self._wallet:
            return self._wallet.addresses
        return []



# ============================================
# Network Tab
# ============================================

# Default locked port
DEFAULT_PORT = 9402


class NetworkTab(QWidget):
    """Tab for network settings - agent listener and blockchain networks."""

    server_toggled = pyqtSignal(bool)
    network_toggled = pyqtSignal(int, bool)
    activity = pyqtSignal(str, bool, bool)
    custom_port_changed = pyqtSignal(bool)  # Emitted when custom port setting changes
    verify_settlements_changed = pyqtSignal(bool)  # Emitted when verify settlements setting changes
    rpc_changed = pyqtSignal(int, str)  # chain_id, new_rpc_url (empty string means use default)
    allow_lan_changed = pyqtSignal(bool)  # Emitted when LAN access setting changes

    def __init__(self, core):
        """
        Args:
            core: MultiClaw core instance
        """
        super().__init__()
        self.core = core
        # Networks ordered by market cap: Ethereum > Base > SKALE
        self.network_enabled: dict[int, bool] = {
            1: False,            # Ethereum Mainnet
            11155111: True,      # Ethereum Sepolia (default enabled)
            8453: False,         # Base Mainnet
            84532: True,         # Base Sepolia (default enabled)
            1187947933: False,   # SKALE Base
            324705682: True,     # SKALE Base Sepolia (default enabled)
        }
        self._custom_port_enabled = False
        self._port = DEFAULT_PORT
        self._allow_lan = False
        self._custom_rpcs: dict[int, str] = {}

        layout = QVBoxLayout(self)

        # === TOP ROW: Agent Link | Blockchain Networks | Withdrawals ===
        top_row = QHBoxLayout()

        # --- Agent Link (left) ---
        listener_group = QGroupBox("Agent Link")
        listener_group.setFixedWidth(290)
        listener_layout = QFormLayout(listener_group)

        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(DEFAULT_PORT)
        self.port_input.setMaximumWidth(80)
        self.port_input.setEnabled(False)
        self.port_input.valueChanged.connect(self._on_port_changed)
        listener_layout.addRow("Port:", self.port_input)

        self.server_status_label = QLabel("● Stopped")
        self.server_status_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
        listener_layout.addRow("Status:", self.server_status_label)

        self.allow_lan_checkbox = QCheckBox("Allow LAN connections")
        self.allow_lan_checkbox.setToolTip("Bind to 0.0.0.0 to allow network access")
        self.allow_lan_checkbox.stateChanged.connect(self._on_allow_lan_toggled)
        listener_layout.addRow("", self.allow_lan_checkbox)

        endpoint_url = f"http://localhost:{DEFAULT_PORT}"
        self.endpoint_label = QLabel(f'<a href="{endpoint_url}" style="color: {Theme.LIME};">{endpoint_url}</a>')
        self.endpoint_label.setFont(QFont(Theme.MONO_FONT, 9))
        self.endpoint_label.setOpenExternalLinks(True)
        self.endpoint_label.setCursor(Qt.CursorShape.PointingHandCursor)
        listener_layout.addRow("Endpoint:", self.endpoint_label)

        self.server_toggle_btn = QPushButton("Start Server")
        listener_layout.addRow("", self.server_toggle_btn)
        self.server_toggle_btn.clicked.connect(self.toggle_server)

        top_row.addWidget(listener_group)

        # --- Blockchain Networks (middle - tabular layout) ---
        networks_group = QGroupBox("Blockchain Networks")
        networks_group.setFixedWidth(580)
        networks_layout = QVBoxLayout(networks_group)

        networks_desc = QLabel("Enable networks for signing. Disabled networks reject all requests.")
        networks_desc.setWordWrap(True)
        networks_desc.setStyleSheet(f"color: {Theme.CHARCOAL};")
        networks_layout.addWidget(networks_desc)

        # Create table-like grid: [Checkbox] [Network Name] [RPC Input]
        networks_grid = QGridLayout()
        networks_grid.setColumnStretch(2, 1)  # RPC column stretches
        networks_grid.setHorizontalSpacing(12)
        networks_grid.setVerticalSpacing(4)

        self.network_checkboxes: dict[int, QCheckBox] = {}
        self.rpc_inputs: dict[int, QLineEdit] = {}

        # Networks in display order (grouped by chain family)
        network_order = [
            (1, "Ethereum"),           # Ethereum Mainnet
            (11155111, None),          # Ethereum Sepolia
            (8453, "Base"),            # Base Mainnet
            (84532, None),             # Base Sepolia
            (1187947933, "SKALE"),     # SKALE Base
            (324705682, None),         # SKALE Base Sepolia
        ]

        row = 0
        for chain_id, group_label in network_order:
            if chain_id not in NETWORKS:
                continue
            network = NETWORKS[chain_id]

            # Add group separator label if this starts a new group
            if group_label:
                if row > 0:
                    # Add spacing between groups
                    spacer = QLabel("")
                    spacer.setFixedHeight(8)
                    networks_grid.addWidget(spacer, row, 0, 1, 3)
                    row += 1

            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(self.network_enabled.get(chain_id, False))
            checkbox.stateChanged.connect(lambda state, cid=chain_id: self.on_network_toggled(cid, state))
            self.network_checkboxes[chain_id] = checkbox
            networks_grid.addWidget(checkbox, row, 0)

            # Network name label (with testnet indicator)
            name_label = QLabel(network.display_name)
            name_label.setMinimumWidth(130)
            if network.is_testnet:
                name_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
            networks_grid.addWidget(name_label, row, 1)

            # RPC input
            rpc_input = QLineEdit()
            rpc_input.setPlaceholderText(network.rpc_url[:40] + "..." if len(network.rpc_url) > 40 else network.rpc_url)
            rpc_input.setFont(QFont(Theme.MONO_FONT, 9))
            rpc_input.setMinimumWidth(280)
            rpc_input.editingFinished.connect(
                lambda cid=chain_id: self._on_rpc_changed(cid)
            )
            self.rpc_inputs[chain_id] = rpc_input
            networks_grid.addWidget(rpc_input, row, 2)

            row += 1

        networks_layout.addLayout(networks_grid)
        networks_layout.addStretch()
        top_row.addWidget(networks_group)

        # Add stretch to push groups left, empty space expands on right
        top_row.addStretch()

        layout.addLayout(top_row)

        # === ADVANCED SETTINGS (two-column layout) ===
        advanced_group = QGroupBox("Advanced Settings")
        advanced_group.setMaximumWidth(880)  # Don't grow wider than min window width
        advanced_layout = QHBoxLayout(advanced_group)

        # --- Left column: Rate limiting ---
        left_col = QVBoxLayout()

        self.custom_port_checkbox = QCheckBox("Use Custom Port")
        self.custom_port_checkbox.setToolTip("Enable to change server port")
        self.custom_port_checkbox.stateChanged.connect(self._on_custom_port_toggled)
        left_col.addWidget(self.custom_port_checkbox)

        rate_desc = QLabel("Request rate limiting protects against runaway agent loops.")
        rate_desc.setWordWrap(True)
        rate_desc.setStyleSheet(f"color: {Theme.CHARCOAL};")
        left_col.addWidget(rate_desc)

        rate_form = QFormLayout()
        self.rate_limit_input = QSpinBox()
        self.rate_limit_input.setRange(0, 1000)
        self.rate_limit_input.setValue(300)
        self.rate_limit_input.setSuffix(" req/min")
        self.rate_limit_input.setToolTip("0 = unlimited")
        self.rate_limit_input.setMaximumWidth(120)
        self.rate_limit_input.valueChanged.connect(self._on_rate_limit_changed)
        rate_form.addRow("Rate limit:", self.rate_limit_input)

        left_col.addLayout(rate_form)

        self.verify_settlements_checkbox = QCheckBox("Verify settlements on-chain")
        self.verify_settlements_checkbox.setToolTip("Verify tx hashes on-chain")
        self.verify_settlements_checkbox.stateChanged.connect(self._on_verify_settlements_toggled)
        left_col.addWidget(self.verify_settlements_checkbox)

        left_col.addStretch()
        advanced_layout.addLayout(left_col)

        # Add stretch so empty space expands on right
        advanced_layout.addStretch()

        layout.addWidget(advanced_group)

        layout.addStretch()

        # Set up callbacks with Qt thread marshaling
        from PyQt6.QtCore import QTimer
        self.core.set_server_callbacks(
            on_started=lambda port: QTimer.singleShot(0, lambda: self.on_server_started(port)),
            on_stopped=lambda: QTimer.singleShot(0, self.on_server_stopped),
            on_error=lambda msg: QTimer.singleShot(0, lambda: self.on_server_error(msg))
        )

    def toggle_server(self):
        """Start or stop the agent server."""
        if self.core.is_server_running():
            self.core.stop_server()
        else:
            self.core.start_server(self._port, allow_lan=self._allow_lan)

    def _on_port_changed(self, value: int):
        """Handle port input value change."""
        self._port = value
        self._update_endpoint_label(value)

    def _update_endpoint_label(self, port: int):
        """Update the endpoint label with a clickable URL."""
        if self._allow_lan:
            # Show LAN IP when allow_lan is enabled
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                local_ip = "0.0.0.0"
            url = f"http://{local_ip}:{port}"
        else:
            url = f"http://localhost:{port}"
        self.endpoint_label.setText(f'<a href="{url}" style="color: {Theme.LIME};">{url}</a>')

    def set_custom_port_enabled(self, enabled: bool):
        """Enable or disable custom port editing."""
        self._custom_port_enabled = enabled
        self.custom_port_checkbox.setChecked(enabled)

        if enabled:
            # Enable editing (only if server not running)
            if not self.core.is_server_running():
                self.port_input.setEnabled(True)
        else:
            # Disable editing and reset to default
            self._port = DEFAULT_PORT
            self.port_input.setValue(DEFAULT_PORT)
            self.port_input.setEnabled(False)
            self._update_endpoint_label(DEFAULT_PORT)

    def _on_custom_port_toggled(self, state: int):
        """Handle custom port checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self._custom_port_enabled = enabled

        if enabled:
            if not self.core.is_server_running():
                self.port_input.setEnabled(True)
            self.activity.emit("Custom port enabled - update agent configurations if changing port", False, True)
        else:
            self._port = DEFAULT_PORT
            self.port_input.setValue(DEFAULT_PORT)
            self.port_input.setEnabled(False)
            self._update_endpoint_label(DEFAULT_PORT)
            self.activity.emit("Port locked to 9402", False, False)

        # Emit signal for settings persistence
        self.custom_port_changed.emit(enabled)

    def on_server_started(self, port: int):
        """Handle server started."""
        self._port = port
        self.server_status_label.setText("● Running")
        self.server_status_label.setStyleSheet(f"color: {Theme.LIME_DIM};")
        self.server_toggle_btn.setText("Stop Server")
        self._update_endpoint_label(port)
        self.port_input.setEnabled(False)
        self.activity.emit(f"Agent listener started on port {port}", False, False)
        self.server_toggled.emit(True)

    def on_server_stopped(self):
        """Handle server stopped."""
        self.server_status_label.setText("● Stopped")
        self.server_status_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
        self.server_toggle_btn.setText("Start Server")
        # Only enable editing if custom port mode is on
        if self._custom_port_enabled:
            self.port_input.setEnabled(True)
        self.activity.emit("Agent listener stopped", False, True)
        self.server_toggled.emit(False)

    def on_server_error(self, error: str):
        """Handle server error."""
        self.server_status_label.setText("● Error")
        self.server_status_label.setStyleSheet(f"color: {Theme.ERROR};")
        self.activity.emit(f"Server error: {error}", True, False)

    def on_network_toggled(self, chain_id: int, state: int):
        """Handle network checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.network_enabled[chain_id] = enabled
        network = NETWORKS.get(chain_id)
        if network:
            status = "enabled" if enabled else "disabled"
            self.activity.emit(f"{network.display_name} signing {status}", False, not enabled)
        self.network_toggled.emit(chain_id, enabled)

    def is_network_enabled(self, chain_id: int) -> bool:
        """Check if signing is enabled for a network."""
        return self.network_enabled.get(chain_id, False)

    def set_network_enabled(self, chain_id: int, enabled: bool):
        """Set network enabled state and update UI (used on load from settings)."""
        self.network_enabled[chain_id] = enabled
        # Update checkbox if it exists
        if hasattr(self, 'network_checkboxes') and chain_id in self.network_checkboxes:
            self.network_checkboxes[chain_id].setChecked(enabled)

    def _on_rate_limit_changed(self, value: int):
        """Handle rate limit change."""
        from ..services.server import rate_limiter
        rate_limiter.configure(requests_per_minute=value)

    def _on_verify_settlements_toggled(self, state: int):
        """Handle verify settlements checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        status = "enabled" if enabled else "disabled"
        self.activity.emit(f"On-chain settlement verification {status}", False, False)
        self.verify_settlements_changed.emit(enabled)

    def set_verify_settlements(self, enabled: bool):
        """Set the verify settlements checkbox state (used on load)."""
        self.verify_settlements_checkbox.setChecked(enabled)

    def _on_allow_lan_toggled(self, state: int):
        """Handle allow LAN checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self._allow_lan = enabled
        self._update_endpoint_label(self._port)
        if enabled:
            self.activity.emit("LAN connections enabled - restart server to apply", False, True)
        else:
            self.activity.emit("LAN connections disabled - restart server to apply", False, False)
        self.allow_lan_changed.emit(enabled)

    def set_allow_lan(self, enabled: bool):
        """Set the allow LAN checkbox state (used on load)."""
        self._allow_lan = enabled
        self.allow_lan_checkbox.setChecked(enabled)

    def _on_rpc_changed(self, chain_id: int):
        """Handle RPC endpoint change."""
        rpc_input = self.rpc_inputs.get(chain_id)
        if rpc_input:
            new_rpc = rpc_input.text().strip()
            if new_rpc:
                self._custom_rpcs[chain_id] = new_rpc
                network = NETWORKS.get(chain_id)
                name = network.display_name if network else str(chain_id)
                self.activity.emit(f"Custom RPC set for {name}", False, False)
            else:
                self._custom_rpcs.pop(chain_id, None)
            self.rpc_changed.emit(chain_id, new_rpc)

    def get_custom_rpcs(self) -> dict[int, str]:
        """Get dictionary of custom RPC URLs (chain_id -> url)."""
        return {k: v for k, v in self._custom_rpcs.items() if v}

    def set_custom_rpcs(self, rpcs: dict[int, str]):
        """Set custom RPC URLs (used on load)."""
        self._custom_rpcs = rpcs.copy() if rpcs else {}
        for chain_id, url in self._custom_rpcs.items():
            if chain_id in self.rpc_inputs:
                self.rpc_inputs[chain_id].setText(url)


# ============================================
# Settings Tab
# ============================================

class SettingsTab(QWidget):
    """Tab for application settings (notifications, startup, appearance)."""

    settings_changed = pyqtSignal(dict)  # Emitted when any setting changes
    auto_lock_changed = pyqtSignal(int)  # Emitted when auto-lock timeout changes (minutes)

    def __init__(self, settings: dict = None):
        super().__init__()
        self._settings = settings or {}

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
        self.auto_lock_input.valueChanged.connect(self._on_auto_lock_changed)
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

        # Version info at bottom
        version_label = QLabel("MultiClaw v1.0.0")
        version_label.setStyleSheet(f"color: {Theme.CHARCOAL};")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

    def set_settings(self, settings: dict):
        """Update all settings from dict (used on load)."""
        self._settings = settings

        # Block signals while updating to avoid triggering saves
        self.sound_checkbox.blockSignals(True)
        self.toast_checkbox.blockSignals(True)
        self.flash_checkbox.blockSignals(True)
        self.minimize_to_tray_checkbox.blockSignals(True)
        self.close_to_tray_checkbox.blockSignals(True)
        self.start_minimized_checkbox.blockSignals(True)
        self.auto_start_server_checkbox.blockSignals(True)
        self.auto_lock_input.blockSignals(True)
        self.replay_window_input.blockSignals(True)

        self.sound_checkbox.setChecked(settings.get("sound_enabled", True))
        self.toast_checkbox.setChecked(settings.get("toast_enabled", True))
        self.flash_checkbox.setChecked(settings.get("flash_taskbar", True))
        self.minimize_to_tray_checkbox.setChecked(settings.get("minimize_to_tray", False))
        self.close_to_tray_checkbox.setChecked(settings.get("close_to_tray", False))
        self.start_minimized_checkbox.setChecked(settings.get("start_minimized", False))
        self.auto_start_server_checkbox.setChecked(settings.get("auto_start_server", False))
        self.auto_lock_input.setValue(settings.get("auto_lock_minutes", 0))
        self.replay_window_input.setValue(settings.get("replay_window_seconds", 300))

        self.sound_checkbox.blockSignals(False)
        self.toast_checkbox.blockSignals(False)
        self.flash_checkbox.blockSignals(False)
        self.minimize_to_tray_checkbox.blockSignals(False)
        self.close_to_tray_checkbox.blockSignals(False)
        self.start_minimized_checkbox.blockSignals(False)
        self.auto_start_server_checkbox.blockSignals(False)
        self.auto_lock_input.blockSignals(False)
        self.replay_window_input.blockSignals(False)

    def get_settings(self) -> dict:
        """Get current settings as dict."""
        return {
            "sound_enabled": self.sound_checkbox.isChecked(),
            "toast_enabled": self.toast_checkbox.isChecked(),
            "flash_taskbar": self.flash_checkbox.isChecked(),
            "minimize_to_tray": self.minimize_to_tray_checkbox.isChecked(),
            "close_to_tray": self.close_to_tray_checkbox.isChecked(),
            "start_minimized": self.start_minimized_checkbox.isChecked(),
            "auto_start_server": self.auto_start_server_checkbox.isChecked(),
            "auto_lock_minutes": self.auto_lock_input.value(),
            "replay_window_seconds": self.replay_window_input.value(),
        }

    def _on_setting_changed(self, state: int):
        """Handle any setting checkbox change."""
        self._settings.update(self.get_settings())
        self.settings_changed.emit(self._settings)

    def _on_auto_lock_changed(self, value: int):
        """Handle auto-lock timeout change."""
        self._settings["auto_lock_minutes"] = value
        self.settings_changed.emit(self._settings)
        self.auto_lock_changed.emit(value)


# ============================================
# Log Tab
# ============================================

# ASCII art banner for console (using Theme colors)
MULTICLAW_ASCII = (
    f'<pre style="font-family: Consolas, monospace; font-size: 12px; line-height: 1.1; margin: 8px;">'
    '<br>'
    f'<span style="color: {Theme.LIME};">█▀▄▀█ █ █ █   ▀█▀ █</span><span style="color: #E94435;"> █▀▀ █   ▄▀█ █ █ █</span><br>'
    f'<span style="color: {Theme.LIME};">█ ▀ █ █▄█ █▄▄  █  █</span><span style="color: #E94435;"> █▄▄ █▄▄ █▀█ ▀▄▀▄▀</span><br>'
    '</pre>'
    '<span style="color: #888888;">Get a Grip on Your Agents</span><br><br>'
    f'<span style="color: {Theme.CHARCOAL};">═══════════════════════════════════════</span><br>'
    '<span style="color: #888888;"> x402 Agent Manifold</span>'
    f'  <span style="color: {Theme.CHARCOAL};">│</span>'
    f'  <span style="color: {Theme.LIME};">v1.0.0</span>'
    f'  <span style="color: {Theme.CHARCOAL};">│</span>'
    '<span style="color: #666666;">localhost:9402</span><br>'
    f'<span style="color: {Theme.CHARCOAL};">═══════════════════════════════════════</span><br>'
)




class LogTab(QWidget):
    """Tab showing real-time logs with hacker aesthetic."""

    def __init__(self):
        super().__init__()
        self._retention_days = 0  # Set by main_window from settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont(Theme.MONO_FONT, 10))

        # Dark terminal styling (using Theme colors)
        self.log_view.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BLACK};
                color: {Theme.LIME};
                border: none;
                padding: 12px;
                selection-background-color: {Theme.LIME_DIM};
            }}
        """)

        # Set initial content with ASCII banner
        self.log_view.setHtml(MULTICLAW_ASCII)

        layout.addWidget(self.log_view)

        # Control bar with dark styling
        controls = QHBoxLayout()
        controls.setContentsMargins(8, 4, 8, 8)

        # Button style using Theme colors
        btn_style = f"""
            QPushButton {{
                background-color: {Theme.BLACK_LIGHT};
                color: {Theme.LIME};
                border: 1px solid {Theme.CHARCOAL};
                padding: 4px 12px;
                font-family: {Theme.MONO_FONT};
            }}
            QPushButton:hover {{
                background-color: {Theme.CHARCOAL};
                border-color: {Theme.LIME};
            }}
        """

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(btn_style)
        clear_btn.clicked.connect(self.clear_logs)
        controls.addWidget(clear_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.setStyleSheet(btn_style)
        copy_btn.clicked.connect(self.copy_logs)
        controls.addWidget(copy_btn)

        controls.addStretch()
        layout.addLayout(controls)

    def set_retention_days(self, days: int):
        """Set log retention (0 = don't save to disk)."""
        self._retention_days = days

    def load_recent(self, max_lines: int):
        """Load recent logs from disk on startup."""
        if max_lines <= 0:
            return

        from ..services.logging import load_recent_logs, format_log_for_display

        lines = load_recent_logs(max_lines)
        if lines:
            # Keep banner, add historical logs
            for line in lines:
                display_line = format_log_for_display(line)
                self._append_colored(display_line)
            self._append_colored("--- Session started ---", color=Theme.CHARCOAL)

    def add_log(self, message: str):
        """Add a log entry with automatic color coding using Theme colors."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        plain = f"[{timestamp}] {message}"

        # Color code based on content (using Theme palette)
        if "error" in message.lower() or "failed" in message.lower():
            color = Theme.ERROR  # Red for errors
        elif "warning" in message.lower() or "denied" in message.lower() or "rejected" in message.lower():
            color = Theme.WARNING  # Orange for warnings
        elif "approved" in message.lower() or "success" in message.lower() or "signed" in message.lower():
            color = Theme.LIME  # Lime for success
        elif "request" in message.lower() or "received" in message.lower():
            color = "#5eead4"  # Teal for incoming (complements lime)
        elif "balance" in message.lower() or "usdc" in message.lower():
            color = Theme.LIME  # Lime for balance info
        else:
            color = "#888888"  # Gray for general

        self._append_colored(f"[{timestamp}] {message}", color)

        # Save to disk if retention is enabled (plain text)
        if self._retention_days > 0:
            from ..services.logging import append_log
            append_log(plain, self._retention_days)

    def _append_colored(self, text: str, color: str = "#00ff00"):
        """Append text with specified color."""
        import html
        escaped = html.escape(text)
        self.log_view.append(f'<span style="color: {color};">{escaped}</span>')

    def clear_logs(self):
        """Clear logs and restore the ASCII banner."""
        self.log_view.setHtml(MULTICLAW_ASCII)

    def copy_logs(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.log_view.toPlainText())
