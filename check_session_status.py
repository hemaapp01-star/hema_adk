"""
Helper script to check the status of a Vertex AI session.

Usage:
    python check_session_status.py <session_id> <user_id>
"""

import sys
import asyncio
from google.adk.sessions import VertexAiSessionService

PROJECT_ID = "hema-63b81"
LOCATION = "us-central1"
AGENT_ENGINE_ID = "5294582794834411520"
APP_NAME = "hema_blood_coordinator"


async def check_session_status(session_id: str, user_id: str):
    """Check the status of a coordination session."""
    
    # Initialize session service
    session_service = VertexAiSessionService(
        PROJECT_ID,
        LOCATION,
        AGENT_ENGINE_ID
    )
    
    try:
        # Get session
        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id
        )
        
        if session:
            print(f"\n✅ Session found: {session_id}")
            print(f"User ID: {user_id}")
            print(f"\nSession State:")
            for key, value in session.state.items():
                print(f"  {key}: {value}")
            
            print(f"\nSession Events: {len(session.events)}")
            
            return session
        else:
            print(f"\n❌ Session not found: {session_id}")
            return None
            
    except Exception as e:
        print(f"\n❌ Error checking session: {str(e)}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python check_session_status.py <session_id> <user_id>")
        print("\nExample:")
        print("  python check_session_status.py abc123xyz provider_PROVIDER_ID")
        sys.exit(1)
    
    session_id = sys.argv[1]
    user_id = sys.argv[2]
    
    asyncio.run(check_session_status(session_id, user_id))
