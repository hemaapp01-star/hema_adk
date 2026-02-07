"""
Root-level agent module for ADK CLI compatibility.

The ADK CLI expects to find an agent at the root level.
This module directly defines the root_agent following the official ADK pattern.
"""

from google.adk.agents import Agent

# Define root agent directly - following official ADK quickstart pattern
# This is a minimal agent definition for deployment compatibility
root_agent = Agent(
    name="hema_blood_coordinator",
    model="gemini-2.0-flash-exp",
    description="Blood donation coordination agent for Hema platform",
    instruction=(
        "You are Hema, an AI blood donation coordinator. "
        "You help coordinate blood requests between healthcare providers and donors. "
        "You assist with finding suitable donors, managing requests, and facilitating communication."
    ),
)

__all__ = ['root_agent']
