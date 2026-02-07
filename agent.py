"""
Root-level agent module for ADK CLI compatibility.

The ADK CLI expects to find an agent at the root level.
This module re-exports the agent from hema_agent for compatibility.
"""

from hema_agent.agent import root_agent

__all__ = ['root_agent']
