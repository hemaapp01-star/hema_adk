# Deployment Instructions

## Quick Start

Follow these steps in order to deploy the fix:

### 1. Create Cloud Storage Bucket (if it doesn't exist)
```bash
gsutil mb -p hema-63b81 -l us-central1 gs://hema-63b81-reasoning-engine
```

### 2. Deploy Reasoning Engine
```bash
cd /Users/abuamal/Desktop/hema_adk
python deploy_reasoning_engine.py
```

### 3. Deploy Cloud Function
```bash
cd "/Users/abuamal/Desktop/hema firebase"
firebase deploy --only functions:onBloodRequestCreated
```

### 4. Test
Create a blood request in your app or Firebase Console and check the logs.

## What Was Fixed

- ❌ **Before**: Cloud Function tried to provide custom `session_id` → Error
- ✅ **After**: Let Vertex AI manage sessions automatically → Success

## Files Modified

1. **`/Users/abuamal/Desktop/hema_adk/reasoning_engine_app.py`** (NEW)
   - Reasoning Engine wrapper with `query()` method
   
2. **`/Users/abuamal/Desktop/hema_adk/deploy_reasoning_engine.py`** (NEW)
   - Deployment script for Reasoning Engine

3. **`/Users/abuamal/Desktop/hema firebase/functions/index.js`**
   - Removed custom session management
   - Simplified Reasoning Engine call

## Need Help?

Check the full walkthrough at:
`/Users/abuamal/.gemini/antigravity/brain/3b847b20-70c8-4563-a2df-3695e1ea4a70/walkthrough.md`
