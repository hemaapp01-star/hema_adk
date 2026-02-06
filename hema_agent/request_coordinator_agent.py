"""
Request Coordinator Agent - Vertex AI Long-Running Task

Orchestrates complete blood request lifecycle:
1. Search donors via Cloud Function
2. Filter/rank by urgency and likelihood
3. Match donors (triggers FCM)
4. Monitor responses via subcollection
5. Expand search if needed
6. Intervene when necessary
"""

import asyncio
import logging
from typing import Dict, List, Optional
from google.adk.agents import Agent
from google.genai import types

from .firebase_tools import (
    get_provider_location,
    call_donor_search,
    update_matched_donors,
    read_donor_responses,
    send_intervention_message,
    get_request_details,
    send_status_update
)

logger = logging.getLogger(__name__)


class RequestCoordinatorAgent:
    """
    Long-running agent that coordinates entire blood request lifecycle.
    Runs on Vertex AI for multi-hour operation.
    """
    
    def __init__(self, session_id: str, request: Dict):
        """
        Initialize Request Coordinator.
        
        Args:
            session_id: Format "healthcare_providers-{providerId}-requests-{requestId}"
            request: Blood request document from Firebase
        """
        self.session_id = session_id
        self.request = request
        
        # Parse session ID
        parts = session_id.split('-')
        self.provider_id = parts[1]
        self.request_id = parts[3]
        
        self.matched_donors = []
        self.search_radius = 50  # km
        self.is_running = True
        
        logger.info(f"Initialized Request Coordinator for request {self.request_id}")
    
    async def coordinate_request(self):
        """Main coordination loop - runs until request filled or closed"""
        try:
            logger.info(f"Starting coordination for request {self.request_id}")
            
            # Send initial status update
            send_status_update(
                self.provider_id,
                self.request_id,
                "Starting coordination for blood request. Searching for compatible donors..."
            )
            
            # Phase 1: Search donors
            provider_geo = get_provider_location(self.provider_id)
            if not provider_geo:
                logger.error("Failed to get provider location")
                return
            
            donors = await self.search_donors(provider_geo)
            if not donors:
                logger.warning("No donors found in initial search")
                send_status_update(
                    self.provider_id,
                    self.request_id,
                    "No compatible donors found in the initial search area. Please check back later."
                )
                return
            
            # Send search results update
            send_status_update(
                self.provider_id,
                self.request_id,
                f"Found {len(donors)} potential donors within {self.search_radius}km radius. Analyzing and ranking by likelihood to donate."
            )
            
            # Phase 2: Filter and rank
            ranked_donors = await self.filter_rank_donors(donors)
            
            # Phase 3: Match donors (triggers FCM)
            await self.match_donors(ranked_donors[:10])  # Top 10
            
            # Phase 4: Monitor responses (long-running)
            await self.monitor_donor_responses()
            
            logger.info(f"Coordination complete for request {self.request_id}")
            
        except Exception as e:
            logger.error(f"Error in coordination: {str(e)}")
    
    async def search_donors(self, provider_geo: Dict) -> List[Dict]:
        """
        Call onBloodRequestCreated Cloud Function for donor search.
        
        Args:
            provider_geo: Provider's geo location
            
        Returns:
            List of donor dicts with uid, bloodGroup, distance_km, etc.
        """
        logger.info(f"Searching donors within {self.search_radius}km")
        
        result = await call_donor_search(
            provider_geo=provider_geo,
            blood_types=self.request["bloodGroup"],
            radius_km=self.search_radius,
            time_period="both"  # Search both daytime and nighttime
        )
        
        donors = result.get("donors", [])
        logger.info(f"Found {len(donors)} potential donors")
        
        return donors
    
    async def filter_rank_donors(self, donors: List[Dict]) -> List[str]:
        """
        Use sub-agent with Deep Thinking to rank donors by likelihood.
        
        Args:
            donors: List of donor dicts from search
            
        Returns:
            List of donor UIDs ranked from most to least likely
        """
        logger.info(f"Filtering and ranking {len(donors)} donors")
        
        # Create filtering agent with Deep Thinking
        filter_instructions = self._get_filter_instructions(donors)
        
        filter_agent = Agent(
            name="donor_filter",
            model="gemini-2.0-flash-exp",
            instruction=filter_instructions,
            thinking_config=types.ThinkingConfig(thinking_level="deep")
        )
        
        # TODO: Implement agent execution to get ranked list
        # For now, return all donor UIDs
        ranked_uids = [d["uid"] for d in donors]
        
        logger.info(f"Ranked {len(ranked_uids)} donors")
        return ranked_uids
    
    async def match_donors(self, donor_uids: List[str]):
        """
        Update matchedDonors in Firebase (triggers FCM).
        
        Args:
            donor_uids: List of donor UIDs to match
        """
        logger.info(f"Matching {len(donor_uids)} donors")
        
        success = update_matched_donors(
            provider_id=self.provider_id,
            request_id=self.request_id,
            donor_uids=donor_uids
        )
        
        if success:
            self.matched_donors.extend(donor_uids)
            logger.info(f"Successfully matched {len(donor_uids)} donors")
            
            # Send status update about matched donors
            send_status_update(
                self.provider_id,
                self.request_id,
                f"Successfully contacted {len(donor_uids)} matched donors. Notifications sent via FCM."
            )
        else:
            logger.error("Failed to update matched donors")
    
    async def monitor_donor_responses(self):
        """
        Monitor responses subcollection and process donor updates.
        Runs until request is filled or closed.
        """
        logger.info("Starting response monitoring")
        
        while self.is_running:
            try:
                # Refresh request status
                request = get_request_details(self.provider_id, self.request_id)
                if not request:
                    logger.error("Failed to get request details")
                    break
                
                # Check if request closed
                if request.get("status") != "open":
                    logger.info(f"Request status changed to: {request.get('status')}")
                    break
                
                # Read all donor responses
                responses = read_donor_responses(
                    provider_id=self.provider_id,
                    request_id=self.request_id
                )
                
                # Count willing donors
                willing_count = sum(
                    1 for r in responses.values() 
                    if r.get("status") == "willing"
                )
                
                logger.info(f"Progress: {willing_count}/{self.request['quantity']} donors willing")
                
                # Send progress update if there are willing donors
                if willing_count > 0:
                    responded_count = sum(
                        1 for r in responses.values()
                        if r.get("status") in ["willing", "declined", "responded"]
                    )
                    send_status_update(
                        self.provider_id,
                        self.request_id,
                        f"Progress update: {willing_count} donor(s) have confirmed they are available and willing to donate. {responded_count} total responses received."
                    )
                
                # Check if request fulfilled
                if willing_count >= self.request["quantity"]:
                    logger.info("Request fulfilled!")
                    send_status_update(
                        self.provider_id,
                        self.request_id,
                        f"Request fulfilled! {willing_count} donors confirmed and are on their way."
                    )
                    break
                
                # Check if need to expand search
                responded_count = len(responses)
                if responded_count == len(self.matched_donors):
                    # All matched donors responded, but not enough willing
                    if willing_count < self.request["quantity"]:
                        logger.info("Expanding search - insufficient willing donors")
                        await self.expand_search()
                
                # Check for donors who need intervention
                await self.check_for_interventions(responses)
                
                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(30)
        
        logger.info("Response monitoring complete")
    
    async def expand_search(self):
        """Expand search radius and match more donors"""
        self.search_radius += 25  # Increase by 25km
        logger.info(f"Expanding search to {self.search_radius}km")
        
        # Send expansion status update
        send_status_update(
            self.provider_id,
            self.request_id,
            f"Expanding search radius to {self.search_radius}km to find additional donors."
        )
        
        provider_geo = get_provider_location(self.provider_id)
        if not provider_geo:
            logger.error("Failed to get provider location for expansion")
            return
        
        donors = await self.search_donors(provider_geo)
        
        # Filter out already matched donors
        new_donors = [
            d for d in donors 
            if d["uid"] not in self.matched_donors
        ]
        
        if new_donors:
            logger.info(f"Found {len(new_donors)} new donors in expanded search")
            send_status_update(
                self.provider_id,
                self.request_id,
                f"Found {len(new_donors)} additional donors in expanded search area. Contacting top candidates."
            )
            ranked = await self.filter_rank_donors(new_donors)
            await self.match_donors(ranked[:5])  # Match top 5 new donors
        else:
            logger.warning("No new donors found in expanded search")
            send_status_update(
                self.provider_id,
                self.request_id,
                f"No additional donors found within {self.search_radius}km radius. Continuing to monitor current matches."
            )
    
    async def check_for_interventions(self, responses: Dict):
        """
        Check if any donors need intervention from coordinator.
        
        Args:
            responses: Dict of donor responses from Firebase
        """
        # Example: Intervene if donor hasn't responded in 30 minutes
        # This is a placeholder - implement actual intervention logic
        pass
    
    def _get_filter_instructions(self, donors: List[Dict]) -> str:
        """
        Generate instructions for donor filtering agent.
        
        Args:
            donors: List of donor dicts
            
        Returns:
            Instruction string for filtering agent
        """
        urgency = self.request.get("urgency", "medium")
        
        return f"""
You are analyzing {len(donors)} potential donors for this blood request:

**Request Details:**
- Blood Type Needed: {self.request['bloodGroup']}
- Quantity: {self.request['quantity']} units
- Urgency: {urgency}
- Required By: {self.request.get('requireBy', 'Not specified')}
- Title: {self.request.get('title', 'Blood donation request')}

**Urgency-Based Strategy:**
- **critical/high**: Prioritize donors closest to hospital with fastest response times
- **medium**: Balance proximity with donor reliability
- **low**: OPPORTUNITY to onboard new donors - include those with 0-1 donations

**Ranking Criteria:**
1. Blood type compatibility (exact match vs. universal donor)
2. Distance from hospital (closer is better)
3. Time period (daytime vs nighttime based on current time)
4. For LOW urgency: Prioritize donors with fewer donations (onboarding)
5. For HIGH urgency: Prioritize experienced donors

**Donor Data:**
{self._format_donors_for_agent(donors)}

**Output Format:**
Return ONLY a JSON array of donor UIDs ranked from most to least likely:
["uid1", "uid2", "uid3", ...]

Use Deep Thinking to carefully analyze each donor's suitability.
"""
    
    def _format_donors_for_agent(self, donors: List[Dict]) -> str:
        """Format donor data for agent instructions"""
        formatted = []
        for d in donors[:20]:  # Limit to 20 for context size
            formatted.append(
                f"- UID: {d['uid']}, Blood: {d['bloodGroup']}, "
                f"Distance: {d.get('distance_km', 'N/A')}km, "
                f"Period: {d.get('timePeriod', 'N/A')}"
            )
        return "\n".join(formatted)
    
    def stop(self):
        """Stop the coordination loop"""
        self.is_running = False
        logger.info("Request Coordinator stopped")


def create_request_coordinator_agent(session_id: str, request: Dict) -> RequestCoordinatorAgent:
    """
    Factory function to create Request Coordinator Agent.
    
    Args:
        session_id: Format "healthcare_providers-{providerId}-requests-{requestId}"
        request: Blood request document from Firebase
        
    Returns:
        RequestCoordinatorAgent instance
    """
    return RequestCoordinatorAgent(session_id, request)
