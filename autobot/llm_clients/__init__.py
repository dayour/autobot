"""LLM Clients for autobot framework.

This module provides LLM client implementations:
- CopilotLLMClient: GitHub Copilot SDK-based client
"""

from __future__ import annotations

from autobot.llm_clients.copilot_client import (
    COPILOT_SDK_AVAILABLE,
    CopilotClientConfig,
    CopilotLLMClient,
)

__all__ = [
    "COPILOT_SDK_AVAILABLE",
    "CopilotClientConfig",
    "CopilotLLMClient",
]
