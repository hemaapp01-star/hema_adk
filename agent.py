"""
Root-level agent module for ADK CLI compatibility.

The ADK CLI expects to find a root agent or application at the root level.
This module exports the HemaReasoningEngineApp which provides the query() method
required by Vertex AI Reasoning Engine.
"""

import os
import logging
from reasoning_engine_app import HemaReasoningEngineApp

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the application instance that will be deployed
# This provides the query() method interface required by Reasoning Engine
root_agent = HemaReasoningEngineApp()

__all__ = ['root_agent']

