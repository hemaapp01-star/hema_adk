# Deployment Instructions - ADK CLI Method

## Prerequisites

1. **Install ADK CLI** (if not already installed):
   ```bash
   pip install google-cloud-aiplatform[adk]
   ```

2. **Authenticate with Google Cloud**:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project hema-63b81
   ```

## Deploy to Vertex AI Agent Engine

### Option 1: Using the deployment script

```bash
cd ~/hema_adk
./deploy.sh
```

### Option 2: Manual deployment

```bash
cd ~/hema_adk

adk deploy agent_engine \
    --project=hema-63b81 \
    --region=us-central1 \
    --display_name="Hema Blood Request Coordinator" \
    .
```

## After Deployment

1. **Copy the Resource ID** from the deployment output (looks like: `751619551677906944`)

2. **Update Cloud Function** with the new Agent Engine ID:
   - Edit `/Users/abuamal/Desktop/hema firebase/functions/index.js`
   - Update line ~323:
     ```javascript
     const agentEngineId = "YOUR_NEW_RESOURCE_ID";
     ```

3. **Deploy Cloud Function**:
   ```bash
   cd ~/hema_firebase
   firebase deploy --only functions:onBloodRequestCreated
   ```

## Query URL Format

Your deployed agent will be accessible at:
```
https://us-central1-aiplatform.googleapis.com/v1/projects/hema-63b81/locations/us-central1/reasoningEngines/RESOURCE_ID:query
```

## Troubleshooting

- **ADK CLI not found**: Run `pip install google-cloud-aiplatform[adk]`
- **Authentication errors**: Run `gcloud auth application-default login`
- **Permission errors**: Ensure Vertex AI API and Cloud Resource Manager API are enabled
