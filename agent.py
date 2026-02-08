"""
Root-level agent module for Vertex AI Reasoning Engine deployment.

Following ADK best practices with Agent and Runner pattern.
"""

import os
import logging
from typing import Dict, Any
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get configuration from environment
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "hema-63b81")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")


# Define the Hema Blood Request Coordinator Agent
hema_agent = Agent(
    name="hema_coordinator",
    model="gemini-2.0-flash",
    description="Agent specialized in coordinating blood donation requests between healthcare providers and potential donors.",
    instruction="""
    You are the Hema Blood Request Coordinator - an AI assistant that manages blood donation requests.
    
    Your Mission:
    Process incoming blood requests from healthcare providers and acknowledge receipt with request details.
    
    Guidelines:
    1. **Validate Input**: Ensure all required fields (provider_id, request_id, request data) are present.
    2. **Log Details**: Record the provider ID, request ID, and request specifics.
    3. **Acknowledge Receipt**: Confirm the request has been received and logged.
    
    FUTURE: This agent will coordinate with donors, send notifications, and track responses.
    """
)

# Initialize session service (in-memory for Reasoning Engine)
session_service = InMemorySessionService()


def query(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main query function called by Vertex AI Reasoning Engine.
    
    Args:
        input_data: Dictionary containing:
            - provider_id: Healthcare provider ID
            - request_id: Blood request ID
            - request: Blood request data
            
    Returns:
        Dictionary with status information
    """
    try:
        logger.info(f"Received query with input: {input_data}")
        
        # Extract parameters
        provider_id = input_data.get("provider_id")
        request_id = input_data.get("request_id")
        request_data = input_data.get("request")
        
        if not all([provider_id, request_id, request_data]):
            return {
                "error": "Missing required fields: provider_id, request_id, request",
                "status": "failed"
            }
        
        # Create a user ID for session management
        user_id = f"provider_{provider_id}"
        
        # Create a query message for the agent
        query_text = f"""
        New blood request received:
        - Provider ID: {provider_id}
        - Request ID: {request_id}
        - Request Details: {request_data}
        
        Please acknowledge receipt of this request.
        """
        
        # Initialize runner
        runner = Runner(
            agent=root_agent,
            session_service=session_service,
            app_name="hema_coordinator"
        )
        
        # Create session
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        session = loop.run_until_complete(
            session_service.create_session(
                app_name="hema_coordinator",
                user_id=user_id
            )
        )
        
        logger.info(f"Created session {session.id} for user {user_id}")
        
        # Run the agent query
        final_response = ""
        async def run_query():
            nonlocal final_response
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=types.Content(
                    parts=[types.Part(text=query_text)],
                    role="user"
                )
            ):
                logger.info(f"Event: {event}")
                if event.is_final_response():
                    final_response = event.content.parts[0].text
        
        loop.run_until_complete(run_query())
        
        return {
            "status": "acknowledged",
            "provider_id": provider_id,
            "request_id": request_id,
            "session_id": session.id,
            "message": final_response or "Blood request received and acknowledged"
        }
        
    except Exception as e:
        logger.error(f"Error in query: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "status": "failed"
        }


__all__ = ['query', 'hema_agent']

