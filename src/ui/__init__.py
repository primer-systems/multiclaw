"""
UI package - PyQt6 user interface components.

Contains:
- Theme: Design system colors and fonts
- MainWindow: Main application window
- Tabs: All application tabs (Policies, Agents, History, Wallet, Network, Logs)
- Dialogs: Agent registration, policy editing, wallet management, settings
"""

from .theme import Theme, ask_question, show_warning, show_info
from .main_window import MainWindow
from .tabs import (
    PoliciesTab,
    AgentsTab,
    HistoryTab,
    WalletTab,
    NetworkTab,
    LogTab,
    BalanceFetcherThread,
)
from .dialogs import (
    AgentRegistrationDialog,
    CommissionDialog,
    NewPolicyDialog,
    AddWalletDialog,
    SettingsDialog,
)

__all__ = [
    # Theme
    "Theme",
    "ask_question",
    "show_warning",
    "show_info",
    # Main Window
    "MainWindow",
    # Tabs
    "PoliciesTab",
    "AgentsTab",
    "HistoryTab",
    "WalletTab",
    "NetworkTab",
    "LogTab",
    "BalanceFetcherThread",
    # Dialogs
    "AgentRegistrationDialog",
    "CommissionDialog",
    "NewPolicyDialog",
    "AddWalletDialog",
    "SettingsDialog",
]
