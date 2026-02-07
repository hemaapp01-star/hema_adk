#!/usr/bin/env python3
"""
Deploy Hema ADK agent to Vertex AI Reasoning Engine.

This script creates a new Reasoning Engine on Vertex AI for long-running task execution.
"""

import vertexai
from reasoning_engine_app import app

# Configuration
PROJECT_ID = "hema-63b81"
LOCATION = "us-central1"
STAGING_BUCKET = "gs://hema-63b81-reasoning-engine"

def deploy_reasoning_engine():
    """Create a new Reasoning Engine."""
    
    # Initialize Vertex AI client
    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION
    )
    
    print(f"🚀 Deploying Hema Reasoning Engine to project: {PROJECT_ID}")
    print(f"📍 Location: {LOCATION}")
    print(f"📦 Staging Bucket: {STAGING_BUCKET}")
    
    try:
        print(f"\n🔨 Creating new Reasoning Engine...")
        print(f"📦 Using staging bucket: {STAGING_BUCKET}")
        
        # Create new Reasoning Engine
        agent_engine = client.agent_engines.create(
            agent=app,
            staging_bucket=STAGING_BUCKET
        )
        
        # Extract the agent engine ID
        agent_engine_id = agent_engine.api_resource.name.split("/")[-1]
        
        print("\n✅ Reasoning Engine created successfully!")
        print(f"\n📝 IMPORTANT: Save this Agent Engine ID:")
        print(f"   {agent_engine_id}")
        print(f"\n🔧 Update your Cloud Function with this ID:")
        print(f"   const agentEngineId = \"{agent_engine_id}\";")
        print(f"\n🔗 Resource name:")
        print(f"   {agent_engine.api_resource.name}")
        
    except Exception as e:
        print(f"\n❌ Error deploying Reasoning Engine: {str(e)}")
        print(f"\n💡 Make sure:")
        print(f"   1. The staging bucket exists: {STAGING_BUCKET}")
        print(f"   2. You have the required permissions")
        print(f"   3. Agent Engine API is enabled")
        raise


if __name__ == "__main__":
    deploy_reasoning_engine()
