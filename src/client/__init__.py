"""
Client module - Connects to the MultiClaw daemon.

Used by GUI and Console to interact with the core.
"""

from .core_client import CoreClient

__all__ = ['CoreClient']
