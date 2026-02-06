"""
Donor Match Agent - Individual Donor Conversations

Handles one-on-one conversations with donors about blood donation requests.
Stores conversation in requests/{requestId}/responses/{donorUid} subcollection.
"""

import logging
from typing import Dict
from google.adk.agents import Agent
from google.genai import types

from .firebase_tools import (
    get_donor_profile,
    check_eligibility,
    update_donor_status,
    store_donor_message
)

logger = logging.getLogger(__name__)


def create_donor_match_agent(
    provider_id: str,
    request_id: str,
    request: Dict,
    donor_uid: str
) -> Agent:
    """
    Creates agent for individual donor conversation.
    
    Args:
        provider_id: Healthcare provider ID
        request_id: Blood request ID
        request: Full request document from Firebase
        donor_uid: Donor's user ID
        
    Returns:
        Agent configured for this specific donor conversation
    """
    # Load donor profile
    donor_profile = get_donor_profile(donor_uid)
    if not donor_profile:
        logger.error(f"Failed to load donor profile for {donor_uid}")
        # Return basic agent without profile
        donor_profile = {
            "firstName": "there",
            "bloodType": "Unknown",
            "totalDonations": 0
        }
    
    # Determine conversation strategy
    urgency = request.get("urgency", "medium")
    is_onboarding = donor_profile.get("totalDonations", 0) <= 1
    
    # Generate instructions
    instructions = _get_donor_match_instructions(
        request=request,
        donor_profile=donor_profile,
        urgency=urgency,
        is_onboarding=is_onboarding
    )
    
    # Create tools with context
    tools = [
        _create_check_eligibility_tool(donor_profile),
        _create_update_status_tool(provider_id, request_id, donor_uid),
        _create_store_message_tool(provider_id, request_id, donor_uid)
    ]
    
    logger.info(f"Created Donor Match Agent for {donor_uid} (onboarding: {is_onboarding})")
    
    return Agent(
        name=f"donor_match_agent_{donor_uid}",
        model="gemini-3-pro-preview",
        instruction=instructions,
        tools=tools,
        thinking_config=types.ThinkingConfig(thinking_level="medium")
    )


def _get_donor_match_instructions(
    request: Dict,
    donor_profile: Dict,
    urgency: str,
    is_onboarding: bool
) -> str:
    """Generate instructions for donor match agent"""
    
    # Build onboarding context
    onboarding_note = ""
    if is_onboarding:
        onboarding_note = f"""
**ONBOARDING MODE ACTIVATED**
This donor has only donated {donor_profile.get('totalDonations', 0)} time(s). 
Be extra encouraging, educational, and patient. This is an opportunity to:
- Build their confidence in the donation process
- Address any fears or concerns thoroughly
- Explain what to expect step-by-step
- Create a positive first impression that increases future likelihood
"""
    
    # Build urgency context
    urgency_note = ""
    if urgency == "critical":
        urgency_note = "**CRITICAL URGENCY**: Be direct and emphasize time sensitivity. Patient's life may depend on quick response."
    elif urgency == "high":
        urgency_note = "**HIGH URGENCY**: Emphasize importance while being respectful of donor's time."
    elif urgency == "low":
        urgency_note = "**LOW URGENCY OPPORTUNITY**: Use this as a relationship-building opportunity. No pressure - focus on education and encouragement."
    
    return f"""
You are Hema, a compassionate blood donation coordinator chatting with {donor_profile.get('firstName', 'a potential donor')}.

**Request Context:**
- Hospital: {request.get('title', 'Blood donation request')}
- Blood Type Needed: {', '.join(request.get('bloodGroup', []))}
- Patient Blood Type: {request.get('patientBloodGroup', 'Not specified')}
- Quantity: {request.get('quantity', 1)} unit(s)
- Urgency: {urgency}
- Required By: {request.get('requireBy', 'As soon as possible')}

**Donor Profile:**
- Name: {donor_profile.get('firstName', 'Friend')} {donor_profile.get('surname', '')}
- Blood Type: {donor_profile.get('bloodType', 'Unknown')}
- Total Donations: {donor_profile.get('totalDonations', 0)}
- Last Donation: {donor_profile.get('lastDonationDate', 'Never donated before')}
- Location: {donor_profile.get('city', 'Not specified')}

{onboarding_note}

{urgency_note}

**Your Conversation Approach:**

1. **Warm Greeting**
   - Thank them for responding to the notification
   - Show genuine appreciation for their willingness to help

2. **Explain the Request**
   - Clearly explain what's needed and why
   - For onboarding donors: Explain the process simply
   - For urgent requests: Emphasize time sensitivity respectfully

3. **Assess Eligibility**
   - Use `check_eligibility` tool to verify donation eligibility
   - Ask about:
     * Current health status (feeling well?)
     * Recent meals (should have eaten within 3-4 hours)
     * Availability (can they donate within required timeframe?)
     * Any recent illnesses or medications

4. **If Eligible and Willing**
   - Call `update_status` tool with status="willing"
   - Provide hospital details and directions
   - Explain what to expect when they arrive
   - Offer encouragement and support

5. **If Hesitant or Concerned**
   - Listen to their concerns empathetically
   - Provide accurate, reassuring information
   - For onboarding donors: Extra patience and education
   - For low urgency: No pressure - focus on building relationship
   - Address common fears (pain, time commitment, safety)

6. **If Ineligible or Declined**
   - Thank them graciously for considering
   - Call `update_status` tool with status="declined"
   - Explain when they'll be eligible again (if applicable)
   - Keep the door open for future requests

**Important Guidelines:**
- Be warm, empathetic, and professional
- Never pressure or guilt-trip donors
- Provide accurate medical information
- Respect their decision either way
- For onboarding: This is about building long-term relationship, not just this one donation
- Use `store_message` tool to save important conversation points

**Tools Available:**
- `check_eligibility`: Verify if donor is eligible based on last donation date
- `update_status`: Update donor's status in Firebase (willing/declined/responded)
- `store_message`: Save conversation messages to Firebase

Remember: Every interaction shapes their future willingness to donate. Be kind, patient, and supportive.
"""


def _create_check_eligibility_tool(donor_profile: Dict):
    """Create check_eligibility tool with donor context"""
    def check_eligibility_wrapper() -> str:
        """Check if donor is eligible to donate based on last donation date"""
        last_donation = donor_profile.get("lastDonationDate")
        result = check_eligibility(last_donation)
        
        if result["eligible"]:
            return f"✅ Donor is eligible! {result['reason']}"
        else:
            return f"❌ Donor is not currently eligible. {result['reason']}"
    
    return check_eligibility_wrapper


def _create_update_status_tool(provider_id: str, request_id: str, donor_uid: str):
    """Create update_status tool with request context"""
    def update_status_wrapper(status: str) -> str:
        """
        Update donor's status in Firebase.
        
        Args:
            status: One of "contacted", "responded", "willing", "declined"
        """
        valid_statuses = ["contacted", "responded", "willing", "declined"]
        if status not in valid_statuses:
            return f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        
        success = update_donor_status(provider_id, request_id, donor_uid, status)
        
        if success:
            logger.info(f"Updated donor {donor_uid} status to: {status}")
            return f"Status updated to: {status}"
        else:
            return "Failed to update status in Firebase"
    
    return update_status_wrapper


def _create_store_message_tool(provider_id: str, request_id: str, donor_uid: str):
    """Create store_message tool with request context"""
    def store_message_wrapper(content: str, role: str = "hema") -> str:
        """
        Store message in Firebase for this conversation.
        
        Args:
            content: Message text
            role: "hema" or "user" (default: "hema")
        """
        import time
        from datetime import datetime
        
        message = {
            "content": {"text": content},
            "role": role,
            "timestamp": datetime.now().isoformat()
        }
        
        success = store_donor_message(provider_id, request_id, donor_uid, message)
        
        if success:
            return "Message stored successfully"
        else:
            return "Failed to store message"
    
    return store_message_wrapper
