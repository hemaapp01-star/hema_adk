#!/usr/bin/env python3
"""
Deploy or update Hema ADK agent to Vertex AI Reasoning Engine.

This script deploys the Request Coordinator Agent as a Reasoning Engine
on Vertex AI for long-running task execution.
"""

import vertexai
from reasoning_engine_app import app

# Configuration
PROJECT_ID = "hema-63b81"
LOCATION = "us-central1"
AGENT_ENGINE_ID = "5294582794834411520"  # Your existing Reasoning Engine ID
STAGING_BUCKET = "gs://hema-63b81-reasoning-engine"  # Update with your bucket

def deploy_reasoning_engine():
    """Deploy or update the Reasoning Engine."""
    
    # Initialize Vertex AI client
    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION
    )
    
    print(f"🚀 Deploying Hema Reasoning Engine to project: {PROJECT_ID}")
    print(f"📍 Location: {LOCATION}")
    print(f"🆔 Agent Engine ID: {AGENT_ENGINE_ID}")
    
    try:
        # Update existing Reasoning Engine
        resource_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ENGINE_ID}"
        
        print(f"\n📦 Updating Reasoning Engine: {resource_name}")
        
        client.agent_engines.update(
            resource_name=resource_name,
            agent=app,  # The HemaReasoningEngineApp instance
            config={
                "display_name": "Hema Blood Request Coordinator",
                "requirements": [
                    "google-cloud-aiplatform[adk,agent_engine]>=1.75.0",
                    "google-cloud-firestore>=2.19.0",
                    "firebase-admin>=6.5.0",
                    "requests>=2.32.0",
                ],
                "staging_bucket": STAGING_BUCKET,
            },
        )
        
        print("\n✅ Reasoning Engine updated successfully!")
        print(f"\n📝 The engine now exposes a query() method that accepts:")
        print("   - provider_id: Healthcare provider ID")
        print("   - request_id: Blood request ID")
        print("   - request: Blood request data dictionary")
        print(f"\n🔗 Call it from your Cloud Function using:")
        print(f"   POST https://{LOCATION}-aiplatform.googleapis.com/v1/{resource_name}:query")
        
    except Exception as e:
        print(f"\n❌ Error deploying Reasoning Engine: {str(e)}")
        print(f"\n💡 If the Reasoning Engine doesn't exist, create it first:")
        print(f"   agent_engine = client.agent_engines.create()")
        print(f"   print(agent_engine.api_resource.name.split('/')[-1])")
        raise


if __name__ == "__main__":
    deploy_reasoning_engine()
