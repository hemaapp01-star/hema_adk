# main.py

import os
import logging
import asyncio
from queue import Queue
from typing import Dict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ADK Core Imports
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types  # Required for structuring the user message

# Import the agent creator function
from hema_agent.agent import create_hema_agent

# Import new dual-agent architecture
from hema_agent.request_coordinator_agent import create_request_coordinator_agent
from hema_agent.donor_match_agent import create_donor_match_agent

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

# Message queues for Request Coordinator agents
coordinator_queues: Dict[str, Queue] = {}
coordinator_tasks: Dict[str, asyncio.Task] = {}

# ─────────────────────────────────────────────
# CHAT ENDPOINT
# ─────────────────────────────────────────────
@app.post("/session/create")
async def create_session(request: Request):
    """
    Create a new session for Request Coordinator Agent.
    Session ID format: healthcare_providers-{providerId}-requests-{requestId}
    """
    data = await request.json()
    session_id = data.get("session_id")
    
    if not session_id:
        return {"error": "session_id required"}, 400
    
    logger.info(f"📋 Creating session: {session_id}")
    
    # Create session in memory service
    await memory_service.create_session(
        app_name="hema_agent",
        user_id="coordinator",
        session_id=session_id
    )
    
    # Initialize message queue for this coordinator
    coordinator_queues[session_id] = Queue()
    
    return {
        "status": "created",
        "session_id": session_id
    }


@app.post("/coordinator/start")
async def start_coordinator(request: Request):
    """
    Start Request Coordinator Agent for a blood request.
    This is a long-running task that monitors the entire request lifecycle.
    """
    data = await request.json()
    session_id = data.get("session_id")
    request_data = data.get("request")
    
    if not session_id or not request_data:
        return {"error": "session_id and request required"}, 400
    
    logger.info(f"🚀 Starting Request Coordinator for {session_id}")
    
    # Create coordinator agent
    coordinator = create_request_coordinator_agent(session_id, request_data)
    
    # Start coordination in background
    task = asyncio.create_task(coordinator.coordinate_request())
    coordinator_tasks[session_id] = task
    
    return {
        "status": "started",
        "session_id": session_id
    }


@app.post("/coordinator/message")
async def receive_coordinator_message(request: Request):
    """
    Receive donor response updates from Cloud Functions.
    Messages are queued for processing by Request Coordinator.
    """
    data = await request.json()
    request_id = data.get("request_id")
    provider_id = data.get("provider_id")
    
    if not request_id or not provider_id:
        return {"error": "request_id and provider_id required"}, 400
    
    session_id = f"healthcare_providers-{provider_id}-requests-{request_id}"
    
    # Get or create queue for this session
    if session_id not in coordinator_queues:
        coordinator_queues[session_id] = Queue()
    
    # Add message to queue
    coordinator_queues[session_id].put(data)
    
    logger.info(f"📬 Queued message for coordinator {session_id}")
    
    return {"status": "queued"}


@app.post("/donor/chat")
async def donor_chat(request: Request):
    """
    Handle chat with individual donor via Donor Match Agent.
    """
    data = await request.json()
    
    donor_uid = data.get("donor_uid")
    provider_id = data.get("provider_id")
    request_id = data.get("request_id")
    request_data = data.get("request")
    message = data.get("message", "")
    
    if not all([donor_uid, provider_id, request_id, request_data]):
        return {"error": "donor_uid, provider_id, request_id, and request required"}, 400
    
    logger.info(f"💬 Donor chat: {donor_uid} for request {request_id}")
    
    # Create Donor Match Agent
    agent = create_donor_match_agent(
        provider_id=provider_id,
        request_id=request_id,
        request=request_data,
        donor_uid=donor_uid
    )
    
    # Create runner
    runner = Runner(
        agent=agent,
        session_service=memory_service,
        app_name="hema_donor_chat"
    )
    
    # Create or get session for this donor
    donor_session_id = f"donor_{donor_uid}_request_{request_id}"
    
    session = await memory_service.get_session(
        app_name="hema_donor_chat",
        user_id=donor_uid,
        session_id=donor_session_id
    )
    
    if not session:
        await memory_service.create_session(
            app_name="hema_donor_chat",
            user_id=donor_uid,
            session_id=donor_session_id
        )
    
    # Structure message
    user_content = types.Content(
        role="user",
        parts=[types.Part(text=message)]
    )
    
    # Run agent
    final_text = ""
    async for event in runner.run_async(
        user_id=donor_uid,
        session_id=donor_session_id,
        new_message=user_content
    ):
        if event.is_final_response() and event.content:
            final_text = "".join([p.text for p in event.content.parts if p.text])
    
    return {
        "reply": final_text,
        "status": "success"
    }


@app.post("/chat")
async def chat_with_context(request: Request):
    """
    Legacy endpoint for backwards compatibility.
    Expects JSON body with user_id, session_id, message, and context.
    """
    data = await request.json()
    
    user_id = data.get("user_id", "default_user")
    session_id = data.get("session_id", "default_session")
    user_message = data.get("message", "")
    context = data.get("context", {})

    logger.info(f"📨 Message from user {user_id}, session {session_id}")
    
    # 1. Initialize the orchestrator agent and runner
    # Note: create_hema_agent now returns the orchestrator for backwards compatibility
    agent = create_hema_agent(context)
    logger.info(f"🎭 Using agent: {agent.name} with {len(agent.sub_agents) if hasattr(agent, 'sub_agents') and agent.sub_agents else 0} sub-agents")
    
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