"""Agent Chat module for autobot framework.

This module provides conversable agents with LLM backends:
- CopilotConversableAgent: Base conversable agent with Copilot backend
- CopilotAssistantAgent: Task-oriented assistant with Copilot backend
"""

from __future__ import annotations

from autobot.agentchat.copilot_agents import (
    CopilotConversableAgent,
    CopilotAssistantAgent,
)

__all__ = [
    "CopilotConversableAgent",
    "CopilotAssistantAgent",
]
