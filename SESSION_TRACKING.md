# Session Tracking with Vertex AI - Quick Guide

## How It Works

### 1. Cloud Function Calls Reasoning Engine
```javascript
// Cloud Function sends request
POST /reasoningEngines/{id}:query
{
  "input": {
    "provider_id": "ABC123",
    "request_id": "REQ456",
    "request": { ... }
  }
}
```

### 2. Reasoning Engine Creates Session & Returns ID
```javascript
// Response from Reasoning Engine
{
  "status": "started",
  "session_id": "auto-generated-by-vertex-ai",  // ✅ Auto-generated!
  "user_id": "provider_ABC123",
  "message": "Blood request coordination started successfully"
}
```

### 3. Cloud Function Stores Session Info
The session ID is stored in Firestore at:
```
healthcare_providers/{providerId}/requests/{requestId}
```

Fields added:
- `coordinationSessionId`: The auto-generated session ID
- `coordinationUserId`: User ID for session queries
- `coordinationStatus`: "started"
- `coordinationStartedAt`: Timestamp

### 4. Check Status Anytime

**From your app/frontend:**
```javascript
// Read from Firestore
const requestDoc = await db
  .collection('healthcare_providers')
  .doc(providerId)
  .collection('requests')
  .doc(requestId)
  .get();

const sessionId = requestDoc.data().coordinationSessionId;
const userId = requestDoc.data().coordinationUserId;
```

**From command line (for debugging):**
```bash
python check_session_status.py <session_id> <user_id>
```

## Session State Lifecycle

1. **started** → Coordination begins
2. **coordinating** → Searching/matching donors (updated by Reasoning Engine)
3. **completed** → Request fulfilled
4. **failed** → Error occurred

## Key Points

✅ **No custom session IDs** - Vertex AI generates them automatically
✅ **Session ID returned** in the query response
✅ **Stored in Firestore** for easy tracking
✅ **7-day TTL** - Sessions auto-delete after 7 days
✅ **State tracking** - Session state shows coordination progress

## Files Changed

1. `reasoning_engine_app.py` - Uses VertexAiSessionService, returns session ID
2. `index.js` - Stores session ID in Firestore
3. `check_session_status.py` - Helper to check status
