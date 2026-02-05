"""
Firebase integration tools for Request Coordinator and Donor Match agents.

Provides tools for:
- Donor search via Cloud Functions
- Response management in requests/{requestId}/responses subcollection
- Intervention messaging to users/{uid}/messages
- Provider location retrieval
"""

import os
import logging
import requests
from typing import Dict, List, Optional
from firebase_admin import firestore
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Initialize Firestore client
db = firestore.client()


def get_provider_location(provider_id: str) -> Dict:
    """
    Get provider geo location from healthcare_providers/{provider_id}/geo
    
    Args:
        provider_id: Healthcare provider document ID
        
    Returns:
        {
            "geohash": "s1t78dsyy",
            "geopoint": {
                "latitude": 9.067655499999999,
                "longitude": 7.411566100000001
            }
        }
    """
    try:
        doc = db.collection("healthcare_providers").document(provider_id).get()
        
        if not doc.exists:
            logger.error(f"Provider {provider_id} not found")
            return None
            
        geo = doc.get("geo")
        logger.info(f"Retrieved location for provider {provider_id}: {geo.get('geohash')}")
        return geo
        
    except Exception as e:
        logger.error(f"Error getting provider location: {str(e)}")
        return None


async def call_donor_search(
    provider_geo: Dict,
    blood_types: List[str],
    radius_km: int = 50,
    time_period: str = "both"
) -> Dict:
    """
    HTTP call to onBloodRequestCreated Cloud Function for donor search.
    
    Args:
        provider_geo: Provider's geo location {geohash, geopoint}
        blood_types: List of compatible blood types (e.g., ["B-", "O-"])
        radius_km: Search radius in kilometers (default: 50)
        time_period: "daytime" | "nighttime" | "both" (default: "both")
        
    Returns:
        {
            "donors": [
                {
                    "uid": "6uRLh6QzoAQQAgMIWiXY5V3oW572",
                    "bloodGroup": "O+",
                    "distance_km": 12.5,
                    "timePeriod": "daytime",
                    "geo": {...}
                },
                ...
            ]
        }
    """
    try:
        # Get Cloud Function URL from environment
        function_url = os.getenv("DONOR_SEARCH_FUNCTION_URL")
        
        if not function_url:
            logger.error("DONOR_SEARCH_FUNCTION_URL not set in environment")
            return {"donors": []}
        
        payload = {
            "provider_geo": provider_geo,
            "blood_types": blood_types,
            "radius_km": radius_km,
            "time_period": time_period
        }
        
        logger.info(f"Calling donor search: {len(blood_types)} blood types, {radius_km}km radius")
        
        response = requests.post(function_url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Found {len(result.get('donors', []))} donors")
        
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling donor search function: {str(e)}")
        return {"donors": []}
    except Exception as e:
        logger.error(f"Unexpected error in donor search: {str(e)}")
        return {"donors": []}


def update_matched_donors(
    provider_id: str,
    request_id: str,
    donor_uids: List[str]
) -> bool:
    """
    Update request.matchedDonors in Firebase.
    This triggers Cloud Function to send FCM notifications to donors.
    
    Args:
        provider_id: Healthcare provider ID
        request_id: Blood request ID
        donor_uids: List of donor UIDs to match
        
    Returns:
        True if successful, False otherwise
    """
    try:
        request_ref = db.collection("healthcare_providers") \
            .document(provider_id) \
            .collection("requests") \
            .document(request_id)
        
        # Add donors to matchedDonors with timestamp
        matched_donors = {
            uid: firestore.SERVER_TIMESTAMP 
            for uid in donor_uids
        }
        
        request_ref.update({
            "matchedDonors": matched_donors
        })
        
        logger.info(f"Updated matchedDonors for request {request_id}: {len(donor_uids)} donors")
        return True
        
    except Exception as e:
        logger.error(f"Error updating matched donors: {str(e)}")
        return False


def read_donor_responses(provider_id: str, request_id: str) -> Dict:
    """
    Read all responses from requests/{requestId}/responses subcollection.
    
    Args:
        provider_id: Healthcare provider ID
        request_id: Blood request ID
        
    Returns:
        {
            "donor_uid1": {
                "messages": [...],
                "status": "willing" | "declined" | "responded" | "contacted",
                "lastMessage": "I can help!",
                "updatedAt": timestamp
            },
            ...
        }
    """
    try:
        responses_ref = db.collection("healthcare_providers") \
            .document(provider_id) \
            .collection("requests") \
            .document(request_id) \
            .collection("responses")
        
        docs = responses_ref.stream()
        
        responses = {
            doc.id: doc.to_dict() 
            for doc in docs
        }
        
        logger.info(f"Read {len(responses)} donor responses for request {request_id}")
        return responses
        
    except Exception as e:
        logger.error(f"Error reading donor responses: {str(e)}")
        return {}


def send_intervention_message(donor_uid: str, message: str) -> bool:
    """
    Request Coordinator sends direct message to donor.
    Writes to users/{uid}/messages with role: "session"
    
    Args:
        donor_uid: Donor's user ID
        message: Message text to send
        
    Returns:
        True if successful, False otherwise
    """
    try:
        messages_ref = db.collection("users") \
            .document(donor_uid) \
            .collection("messages")
        
        messages_ref.add({
            "content": {"text": message},
            "role": "session",
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        
        logger.info(f"Sent intervention message to donor {donor_uid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending intervention message: {str(e)}")
        return False


def update_donor_status(
    provider_id: str,
    request_id: str,
    donor_uid: str,
    status: str
) -> bool:
    """
    Update donor status in responses subcollection.
    
    Args:
        provider_id: Healthcare provider ID
        request_id: Blood request ID
        donor_uid: Donor's user ID
        status: "contacted" | "responded" | "willing" | "declined"
        
    Returns:
        True if successful, False otherwise
    """
    try:
        response_ref = db.collection("healthcare_providers") \
            .document(provider_id) \
            .collection("requests") \
            .document(request_id) \
            .collection("responses") \
            .document(donor_uid)
        
        response_ref.set({
            "status": status,
            "updatedAt": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        logger.info(f"Updated donor {donor_uid} status to: {status}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating donor status: {str(e)}")
        return False


def store_donor_message(
    provider_id: str,
    request_id: str,
    donor_uid: str,
    message: Dict
) -> bool:
    """
    Store message in responses/{donorUid}/messages array.
    Also updates users/{uid}/messages for Flutter UI.
    
    Args:
        provider_id: Healthcare provider ID
        request_id: Blood request ID
        donor_uid: Donor's user ID
        message: Message dict with {content, role, timestamp}
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Update responses subcollection
        response_ref = db.collection("healthcare_providers") \
            .document(provider_id) \
            .collection("requests") \
            .document(request_id) \
            .collection("responses") \
            .document(donor_uid)
        
        response_ref.update({
            "messages": firestore.ArrayUnion([message]),
            "lastMessage": message.get("content"),
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        
        # Also write to users/{uid}/messages for Flutter UI
        db.collection("users") \
            .document(donor_uid) \
            .collection("messages") \
            .add(message)
        
        logger.info(f"Stored message for donor {donor_uid}")
        return True
        
    except Exception as e:
        logger.error(f"Error storing donor message: {str(e)}")
        return False


def get_donor_profile(donor_uid: str) -> Optional[Dict]:
    """
    Get donor profile from users collection.
    
    Args:
        donor_uid: Donor's user ID
        
    Returns:
        User document dict or None if not found
    """
    try:
        doc = db.collection("users").document(donor_uid).get()
        
        if not doc.exists:
            logger.error(f"Donor {donor_uid} not found")
            return None
            
        profile = doc.to_dict()
        logger.info(f"Retrieved profile for donor {donor_uid}")
        return profile
        
    except Exception as e:
        logger.error(f"Error getting donor profile: {str(e)}")
        return None


def check_eligibility(last_donation_date: Optional[str]) -> Dict:
    """
    Check if donor is eligible based on last donation date.
    Donors must wait at least 8 weeks (56 days) between whole blood donations.
    
    Args:
        last_donation_date: ISO format date string or None
        
    Returns:
        {
            "eligible": bool,
            "reason": str,
            "days_since_last_donation": int | None
        }
    """
    try:
        if not last_donation_date:
            return {
                "eligible": True,
                "reason": "No previous donation recorded",
                "days_since_last_donation": None
            }
        
        # Parse last donation date
        last_donation = datetime.fromisoformat(last_donation_date.replace('Z', '+00:00'))
        days_since = (datetime.now(last_donation.tzinfo) - last_donation).days
        
        if days_since >= 56:  # 8 weeks
            return {
                "eligible": True,
                "reason": f"Last donation was {days_since} days ago",
                "days_since_last_donation": days_since
            }
        else:
            days_remaining = 56 - days_since
            return {
                "eligible": False,
                "reason": f"Must wait {days_remaining} more days (last donation was {days_since} days ago)",
                "days_since_last_donation": days_since
            }
            
    except Exception as e:
        logger.error(f"Error checking eligibility: {str(e)}")
        return {
            "eligible": False,
            "reason": f"Error checking eligibility: {str(e)}",
            "days_since_last_donation": None
        }


def get_request_details(provider_id: str, request_id: str) -> Optional[Dict]:
    """
    Get blood request details from Firebase.
    
    Args:
        provider_id: Healthcare provider ID
        request_id: Blood request ID
        
    Returns:
        Request document dict or None if not found
    """
    try:
        doc = db.collection("healthcare_providers") \
            .document(provider_id) \
            .collection("requests") \
            .document(request_id) \
            .get()
        
        if not doc.exists:
            logger.error(f"Request {request_id} not found")
            return None
            
        request = doc.to_dict()
        logger.info(f"Retrieved request {request_id}")
        return request
        
    except Exception as e:
        logger.error(f"Error getting request details: {str(e)}")
        return None
