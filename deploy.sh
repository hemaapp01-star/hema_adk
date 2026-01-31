#!/bin/bash

# Configuration
PROJECT_ID="amazing-pipe-482714-b1"
REGION="us-central1"
SERVICE_NAME="hema-agent-service"
KEY_FILE="hema-key.json"

echo "🚀 Starting deployment for project: $PROJECT_ID"

# 1. Pre-deployment check for the key file
if [ ! -f "$KEY_FILE" ]; then
    echo "❌ ERROR: $KEY_FILE not found in the current directory!"
    echo "Please ensure you have moved the key file here before running this script."
    exit 1
fi

# 2. Enable required APIs
echo "📦 Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  --project=$PROJECT_ID

# 3. Deploy to Cloud Run
# Note: Since we are using a JSON key in the code, we don't need to 
# specify a --service-account flag in the deploy command itself.
echo "🚢 Building and deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --project $PROJECT_ID \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=True,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION"

echo "✅ Deployment complete!"