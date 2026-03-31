#!/usr/bin/env python3
"""
MultiClaw Headless - Run daemon without GUI.

This is a convenience wrapper around `python -m daemon.app`.

Usage:
    python multiclaw_headless.py
    python multiclaw_headless.py --admin-port 9403 --agent-port 9402
    python multiclaw_headless.py --allow-lan
"""

from daemon.app import main

if __name__ == "__main__":
    main()
