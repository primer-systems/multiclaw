"""
UI package - PyQt6 user interface components.

Contains:
- Theme: Design system colors and fonts
- MainWindow: Main application window
- Tabs: All application tabs (Policies, Agents, History, Wallet, Network, Logs)
- Dialogs: Agent registration, policy editing, wallet management, settings
"""

from .theme import Theme, LIGHT, DARK, build_qss, set_role, ask_question, show_warning, show_info, FramelessDialog
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
    SettingsDialog,
)
from .console import ConsoleWindow

__all__ = [
    # Theme
    "Theme",
    "LIGHT",
    "DARK",
    "build_qss",
    "set_role",
    "ask_question",
    "show_warning",
    "show_info",
    "FramelessDialog",
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
    "SettingsDialog",
    # Console
    "ConsoleWindow",
]
