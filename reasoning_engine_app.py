"""
Reasoning Engine Application for Vertex AI Agent Engine deployment.

This module provides a query interface using the standard ADK Agent/Runner pattern.
It wraps the query function in a simple class for deployment compatibility.
"""

import os
import logging
from typing import Dict, Any
import firebase_admin
from firebase_admin import credentials
from google.adk.sessions import VertexAiSessionService
from google.adk.runners import Runner
from google.adk.agents import Agent

# Setup logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase - conditional for deployment vs runtime
try:
    if not firebase_admin._apps:
        # Try to use service account key if available
        if os.path.exists("hema-key.json"):
            cred = credentials.Certificate("hema-key.json")
            firebase_admin.initialize_app(cred)
        else:
            # Use Application Default Credentials (works on Vertex AI)
            firebase_admin.initialize_app()
            logger.info("Using Application Default Credentials for Firebase")
except Exception as e:
    # During deployment, Firebase may not be needed
    logger.warning(f"Firebase initialization deferred: {e}")

from hema_agent.request_coordinator_agent import create_request_coordinator_agent

# Get configuration from environment
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "hema-63b81")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
AGENT_ENGINE_ID = os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID", "5294582794834411520")


# Create a simple coordinator agent for the Reasoning Engine
coordinator_agent = Agent(
    name="hema_blood_coordinator",
    model="gemini-2.0-flash",
    description="Agent that coordinates blood donation requests between healthcare providers and donors.",
    instruction="""
    You are the Hema Blood Request Coordinator.
    
    Your role is to:
    1. Receive blood requests from healthcare providers
    2. Acknowledge receipt and log the request details
    3. Coordinate with the request coordinator to find suitable donors
    
    When you receive a blood request, extract and confirm:
    - Provider ID
    - Request ID  
    - Blood group requirements
    - Quantity needed
    - Urgency level
    - Location/address
    
    Acknowledge the request professionally and confirm that coordination has begun.
    """
)


class HemaReasoningEngine:
    """
    Simple wrapper class for Vertex AI Reasoning Engine deployment.
    
    This class wraps the query logic to make it compatible with the
    Reasoning Engine deployment requirements.
    """
    
    def __init__(self):
        """Initialize the Reasoning Engine."""
        logger.info("Initializing Hema Reasoning Engine")
    
    def query(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main query method called by Vertex AI Reasoning Engine.
        
        This is a synchronous method that handles blood request coordination.
        It creates a session, runs the coordinator agent, and returns the result.
        
        Args:
            input_data: Dictionary containing:
                - provider_id: Healthcare provider ID
                - request_id: Blood request ID
                - request: Blood request data
                
        Returns:
            Dictionary with status and session information
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
            
            # Initialize session service
            session_service = VertexAiSessionService(
                PROJECT_ID,
                LOCATION,
                AGENT_ENGINE_ID
            )
            
            # Create user ID for session management
            user_id = f"provider_{provider_id}"
            app_name = "hema_blood_coordinator"
            
            # Create a formatted message for the agent
            blood_groups = ", ".join(request_data.get("bloodGroup", []))
            message = f"""
            New blood request received:
            
            Provider ID: {provider_id}
            Request ID: {request_id}
            Blood Group(s): {blood_groups}
            Quantity: {request_data.get('quantity', 'N/A')} units
            Urgency: {request_data.get('urgency', 'N/A')}
            Organization: {request_data.get('organisationName', 'N/A')}
            Required By: {request_data.get('requireBy', 'N/A')}
            Address: {request_data.get('address', 'N/A')}
            
            Please acknowledge this request and confirm that coordination has begun.
            """
            
            # Initialize runner with the coordinator agent
            runner = Runner(
                agent=coordinator_agent,
                session_service=session_service,
                app_name=app_name
            )
            
            # Run the agent synchronously
            import asyncio
            
            async def run_agent():
                # Create session
                session = await session_service.create_session(
                    app_name=app_name,
                    user_id=user_id,
                    ttl="604800s"  # 7 days
                )
                
                session_id = session.id
                logger.info(f"Created session {session_id} for user {user_id}")
                
                # Store request metadata in session
                await session_service.update_session(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id,
                    state={
                        "provider_id": provider_id,
                        "request_id": request_id,
                        "status": "coordinating"
                    }
                )
                
                # Run the agent
                response_text = ""
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=message
                ):
                    if event.is_final_response():
                        response_text = event.content.parts[0].text
                        logger.info(f"Agent response: {response_text}")
                
                return {
                    "status": "acknowledged",
                    "session_id": session_id,
                    "user_id": user_id,
                    "provider_id": provider_id,
                    "request_id": request_id,
                    "message": response_text or "Blood request received and acknowledged"
                }
            
            # Run the async function synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(run_agent())
                return result
            finally:
                loop.close()
            
        except Exception as e:
            logger.error(f"Error in query: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed"
            }


# Create the application instance for deployment
app = HemaReasoningEngine()

# Export both the app and query method
__all__ = ['app', 'query']

# Standalone query function for backward compatibility
def query(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone query function that delegates to the app instance."""
    return app.query(input_data)
