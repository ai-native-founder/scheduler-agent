#!/usr/bin/env python
"""
Helper script to run the reminder agent with uv run.
This ensures the agent module can be found by temporarily adding the parent directory to sys.path.
"""
import os
import sys

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath("."))

# Import and run the reminder agent
from a2a_reminder_agent.agents.reminder.__main__ import main

if __name__ == "__main__":
    main()
