# hema_agent/agent.py

import logging
from typing import Dict, Any
from google.adk.agents import Agent
from .tools import notify_hospital_subagent
from .donor_filter_agent import create_donor_filter_agent
from .donor_chat_agent import create_donor_chat_agent

logger = logging.getLogger(__name__)



def create_orchestrator_agent(context: Dict[str, Any]) -> Agent:
    """
    Creates the orchestrator agent that coordinates between donor chat and donor filter sub-agents.
    
    Args:
        context: Dictionary containing bloodRequest, providerLocation, and potentially donor list data
    
    Returns:
        Orchestrator agent with donor_chat_agent and donor_filter_agent as sub-agents
    """
    # Create the two sub-agents
    donor_chat = create_donor_chat_agent(context)
    donor_filter = create_donor_filter_agent(context)
    
    orchestrator_instructions = """
You are the Hema Orchestrator, coordinating blood donation operations.

**YOUR ROLE:**
Route requests to the appropriate specialized agent:

1. **donor_chat_agent**: Use for:
   - Conversations with individual donors
   - Assessing donor availability and eligibility
   - Coordinating hospital notifications
   - Follow-up on donation requests

2. **donor_filter_agent**: Use for:
   - Analyzing lists of potential donors
   - Filtering donors by likelihood to donate
   - Prioritizing donors based on history and eligibility
   - Generating ranked donor lists

**ROUTING LOGIC:**
- If the message is "Filter donors for blood request" AND context contains donor_ids → IMMEDIATELY transfer to donor_filter_agent
- If the request involves chatting with a specific donor → transfer to donor_chat_agent
- If the request involves analyzing/filtering a donor list → transfer to donor_filter_agent

**IMPORTANT:**
Always transfer to the appropriate sub-agent immediately. Do not attempt to handle requests yourself.
When you receive donor filtering requests from the system, pass the donor_ids list directly to the donor_filter_agent.
"""
    
    logger.info("✅ Created Orchestrator agent with donor_chat and donor_filter sub-agents")
    
    return Agent(
        name="hema_orchestrator",
        model="gemini-2.0-flash-exp",
        instruction=orchestrator_instructions,
        description="Orchestrates blood donation operations by routing to specialized donor chat and donor filter agents.",
        sub_agents=[donor_chat, donor_filter]
    )


# For backwards compatibility
def create_hema_agent(context: Dict[str, Any]) -> Agent:
    """Backwards compatibility wrapper - now returns orchestrator."""
    return create_orchestrator_agent(context)


# Legacy root agent for backwards compatibility
root_agent = Agent(
    name="hema_agent",
    model="gemini-2.0-flash-exp",
    instruction="You are Hema, a blood donation coordinator. Context will be provided.",
    tools=[notify_hospital_subagent]
)