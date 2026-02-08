#!/bin/bash
# Deploy Hema ADK Agent to Vertex AI Agent Engine using ADK CLI

PROJECT_ID="hema-63b81"
LOCATION_ID="us-central1"
DISPLAY_NAME="Hema Blood Request Coordinator"

echo "🚀 Deploying Hema ADK Agent to Vertex AI Agent Engine"
echo "📍 Project: $PROJECT_ID"
echo "📍 Location: $LOCATION_ID"
echo ""
export GOOGLE_APPLICATION_CREDENTIALS=$(pwd)/hema-key.json


# Deploy using ADK CLI
/Library/Frameworks/Python.framework/Versions/3.12/bin/adk deploy agent_engine \
    --project=$PROJECT_ID \
    --region=$LOCATION_ID \
    --display_name="$DISPLAY_NAME" \
    .

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📝 IMPORTANT: Copy the RESOURCE_ID from the output above"
echo "🔧 Update your Cloud Function with the new Agent Engine ID"