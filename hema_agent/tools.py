import logging
from typing import Optional

# Set up logging to capture details in Cloud Run
logger = logging.getLogger(__name__)

# Set up logging to capture details in Cloud Run
logger = logging.getLogger(__name__)

def notify_hospital_subagent(donor_id: str, request_id: str, provider_id: str) -> str:
    """
    Alerts the healthcare provider by adding the donor to the matchedDonors sub-collection.
    """
    # Lazy import to avoid dependency issues during Vertex AI deployment
    import firebase_admin
    from firebase_admin import firestore
    
    # 1. Debug Log: See what the agent is actually sending
    logger.info(f"DEBUG: notify_hospital_subagent called with donor_id={donor_id}, request_id={request_id}, provider_id={provider_id}")
    
    if not firebase_admin._apps:
        return "System Error: Firebase connection not found. Please contact support."

    if not all([donor_id, request_id, provider_id]):
        return "System Error: One or more IDs are missing. Tool cannot proceed."

    try:
        db = firestore.client()

        # 2. Path Construction
        # Ensure there are no extra spaces or hidden characters
        p_id = str(provider_id).strip()
        r_id = str(request_id).strip()
        
        request_ref = db.collection('healthcare_providers') \
                        .document(p_id) \
                        .collection('requests') \
                        .document(r_id)
        
        logger.info(f"DEBUG: Attempting to update Firestore at path: {request_ref.path}")

        # 3. Use set with merge=True if you aren't 100% sure the document exists
        # This prevents the 'NOT_FOUND' error that .update() triggers
        request_ref.set({
            'matchedDonors': firestore.ArrayUnion([donor_id])
        }, merge=True)

        return "The healthcare provider has been alerted. They are now expecting your arrival."

    except Exception as e:
        logger.error(f"FIRESTORE FAILURE: {str(e)}")
        return f"I'm sorry, I had trouble notifying the hospital. Error: {str(e)}"