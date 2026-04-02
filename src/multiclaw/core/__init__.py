"""
Core module - UI-agnostic business logic.

This module must NEVER import PyQt6 or any UI framework.
"""

from .multiclaw import MultiClaw
from .events import Event, EventBus, EventType
from .interfaces import ApprovalHandler
from .settings import SettingsManager, AppSettings

__all__ = ['MultiClaw', 'Event', 'EventBus', 'EventType', 'ApprovalHandler', 'SettingsManager', 'AppSettings']
