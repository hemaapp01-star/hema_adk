"""
Root-level agent module for ADK CLI compatibility.

The ADK CLI expects to find an agent at the root level.
This module directly defines the root_agent to avoid import issues.
"""

from google.adk.agents import Agent
from hema_agent.tools import notify_hospital_subagent

# Define root agent directly to avoid complex imports
root_agent = Agent(
    name="hema_agent",
    model="gemini-2.0-flash-exp",
    instruction="You are Hema, a blood donation coordinator. Context will be provided.",
    tools=[notify_hospital_subagent]
)

__all__ = ['root_agent']
