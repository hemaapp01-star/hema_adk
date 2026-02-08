"""
Root-level agent module for ADK CLI compatibility.

The ADK CLI expects to find a root agent or application at the root level.
This module defines a simple application class with a query method.
"""

import os
import logging
from typing import Dict, Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HemaReasoningEngineApp:
    """
    Application class for Vertex AI Reasoning Engine deployment.
    
    This class provides the query() method interface required by Reasoning Engine.
    """
    
    def query(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main query method called by Vertex AI Reasoning Engine.
        
        Args:
            input_data: Dictionary containing:
                - provider_id: Healthcare provider ID
                - request_id: Blood request ID
                - request: Blood request data
                
        Returns:
            Dictionary with status information
        """
        try:
            logger.info(f"Received query with input: {input_data}")
            
            # Extract parameters
            provider_id = input_data.get("provider_id")
            request_id = input_data.get("request_id")
            request_data = input_data.get("request")
            
            if not all([provider_id, request_id, request_data]):
                return {
                    "error": "Missing required fields: provider_id, request_id, request",
                    "status": "failed"
                }
            
            # For now, just acknowledge receipt
            # TODO: Implement actual coordination logic
            logger.info(f"Processing request {request_id} for provider {provider_id}")
            logger.info(f"Request data: {request_data}")
            
            return {
                "status": "acknowledged",
                "provider_id": provider_id,
                "request_id": request_id,
                "message": "Blood request received and acknowledged"
            }
            
        except Exception as e:
            logger.error(f"Error in query: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed"
            }


# Create the application instance that will be deployed
# This provides the query() method interface required by Reasoning Engine
root_agent = HemaReasoningEngineApp()

__all__ = ['root_agent']

