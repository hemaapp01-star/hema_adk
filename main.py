# main.py

import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ADK Core Imports
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types  # Required for structuring the user message

# Import the agent creator function
from hema_agent.agent import create_hema_agent

import firebase_admin
from firebase_admin import credentials

# Initialize Firebase using your existing service account key
if not firebase_admin._apps:
    cred = credentials.Certificate("hema-key.json")
    firebase_admin.initialize_app(cred)

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = "amazing-pipe-482714-b1"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "hema-key.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session service
memory_service = InMemorySessionService()

# ─────────────────────────────────────────────
# CHAT ENDPOINT
# ─────────────────────────────────────────────
@app.post("/chat")
async def chat_with_context(request: Request):
    """
    Expects JSON body with user_id, session_id, message, and context.
    """
    data = await request.json()
    
    user_id = data.get("user_id", "default_user")
    session_id = data.get("session_id", "default_session")
    user_message = data.get("message", "")
    context = data.get("context", {})

    logger.info(f"📨 Message from user {user_id}, session {session_id}")
    
    # 1. Initialize the agent and runner
    agent = create_hema_agent(context)
    runner = Runner(
        agent=agent, 
        session_service=memory_service, 
        app_name="hema_agent"
    )
    
    # 2. FIX: Explicitly handle session existence to prevent ValueError
    session = await memory_service.get_session(
        app_name="hema_agent",
        user_id=user_id,
        session_id=session_id
    )
    
    if not session:
        logger.info(f"🆕 Creating new session: {session_id}")
        await memory_service.create_session(
            app_name="hema_agent",
            user_id=user_id,
            session_id=session_id
        )
    else:
        logger.info(f"♻️ Resuming session with {len(session.events)} events")

    # 3. FIX: Structure the message as an ADK Content object
    user_content = types.Content(
        role="user",
        parts=[types.Part(text=user_message)]
    )
    
    # 4. FIX: Use 'new_message' keyword and 'is_final_response' event check
    final_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=user_content
    ):
        # Using is_final_response avoids capturing thought traces or partial chunks
        if event.is_final_response() and event.content:
            final_text = "".join([p.text for p in event.content.parts if p.text])

    logger.info(f"✅ Response: {len(final_text)} chars")
    
    return {
        "reply": final_text,
        "status": "success",
        "session_id": session_id
    }

@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "hema-agent-custom"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)