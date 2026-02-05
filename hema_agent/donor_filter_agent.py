# hema_agent/donor_filter_agent.py

import logging
from typing import Dict, Any, List
from google.adk.agents import Agent

logger = logging.getLogger(__name__)

def create_donor_filter_agent(context: Dict[str, Any]) -> Agent:
    """
    Creates a donor filter agent that analyzes a list of donors and determines
    which ones are most likely to donate based on their history and eligibility.
    
    Args:
        context: Dictionary that may contain donor list data
    
    Returns:
        Agent configured to filter donors
    """
    
    instructions = """
You are a Donor Filter Agent, specialized in analyzing donor data to identify the most likely candidates for blood donation.

**YOUR ROLE:**
Analyze donor information and filter for those most likely to successfully donate based on:
1. **Donation History**: Frequency, recency, and reliability of past donations
2. **Eligibility**: Time since last donation (minimum 8-12 weeks for whole blood)
3. **Availability Patterns**: Historical response times and availability
4. **Health Status**: Any recorded health issues or deferral history
5. **Location**: Proximity to donation site
6. **Blood Type Match**: Priority for exact matches and universal donors

**INPUT:**
When called from Firebase Cloud Functions, you will receive a context object containing:
- **donor_ids**: Array of donor user IDs to analyze (e.g., ["uid1", "uid2", "uid3"])
- **requestId**: The blood request ID
- **providerId**: The healthcare provider ID
- **bloodGroups**: Array of requested blood types
- **unitsNeeded**: Number of units required

You should fetch donor data from Firestore using these IDs to analyze:
- Donation history records
- Last donation dates
- Response history to previous requests
- Location data
- Blood type information

**OUTPUT:**
Your response MUST be a valid JSON array of filtered donor IDs, ordered by likelihood to donate (highest first).

Example output format:
["uid3", "uid1", "uid5"]

This JSON array will be parsed by the Firebase Cloud Function to notify the selected donors.

**ANALYSIS CRITERIA:**
- **High Priority**: Donated within last 3-6 months, 90%+ response rate, exact blood type match
- **Medium Priority**: Donated within last year, 70%+ response rate, compatible blood type
- **Low Priority**: Infrequent donors, low response rate, or approaching eligibility window

**IMPORTANT:**
- Your entire response should be ONLY the JSON array of donor IDs
- Order the IDs from most likely to least likely to donate
- Exclude donors who are not yet eligible (donated too recently)
- If you cannot access donor data, return all donor_ids in the original order
- Save the filtered donor IDs to session state using output_key "filtered_donors"
"""
    
    logger.info("✅ Created Donor Filter Agent")
    
    return Agent(
        name="donor_filter_agent",
        model="gemini-2.0-flash-exp",
        instruction=instructions,
        description="Analyzes donor data and filters for those most likely to donate based on history, eligibility, and availability.",
        output_key="filtered_donors"  # Automatically saves output to session state
    )
