"""Copilot-backed Agent classes for autobot framework.

This module provides agent classes that use GitHub Copilot SDK
as the LLM backend for conversational AI interactions.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Literal

from autobot.llm_clients.copilot_client import (
    COPILOT_SDK_AVAILABLE,
    CopilotClientConfig,
    CopilotLLMClient,
)


DEFAULT_COPILOT_SYSTEM_MESSAGE = """You are a helpful AI assistant powered by GitHub Copilot.
You can assist with:
- Software development and coding tasks
- Code review and explanation
- Debugging and troubleshooting
- Documentation and technical writing
- General knowledge questions

Always provide clear, accurate, and helpful responses."""


COPILOT_ASSISTANT_SYSTEM_MESSAGE = """You are a GitHub Copilot-powered AI assistant specialized in software development.

Your capabilities include:
1. Writing and reviewing code in multiple programming languages
2. Explaining complex code and algorithms
3. Suggesting improvements and best practices
4. Debugging and fixing issues
5. Generating documentation and tests

When helping with code:
- Provide complete, working solutions
- Include comments for clarity
- Follow language-specific conventions
- Consider edge cases and error handling
- Suggest tests when appropriate

Be concise but thorough. Ask clarifying questions when needed."""


class CopilotConversableAgent:
    """Conversable agent with GitHub Copilot backend.

    This agent provides conversational AI capabilities using
    the GitHub Copilot SDK for LLM interactions.

    Args:
        name: Agent identifier
        copilot_config: Copilot client configuration
        system_message: System message for the agent
        human_input_mode: When to request human input
        max_consecutive_auto_reply: Max auto-replies before stopping

    Example:
        >>> agent = CopilotConversableAgent(
        ...     name="assistant",
        ...     copilot_config={"model": "gpt-4", "temperature": 0.7},
        ... )
        >>> await agent.start_copilot()
        >>> response = await agent.generate_reply(messages)
    """

    def __init__(
        self,
        name: str,
        copilot_config: CopilotClientConfig | dict | None = None,
        system_message: str = DEFAULT_COPILOT_SYSTEM_MESSAGE,
        human_input_mode: Literal["ALWAYS", "NEVER", "TERMINATE"] = "TERMINATE",
        max_consecutive_auto_reply: int | None = None,
        **kwargs,
    ):
        self.name = name
        self._system_message = system_message
        self.human_input_mode = human_input_mode
        self.max_consecutive_auto_reply = max_consecutive_auto_reply

        # Initialize Copilot configuration
        if isinstance(copilot_config, dict):
            self._copilot_config = CopilotClientConfig(**copilot_config)
        elif copilot_config is None:
            self._copilot_config = CopilotClientConfig()
        else:
            self._copilot_config = copilot_config

        # Client state
        self._copilot_client: CopilotLLMClient | None = None
        self._chat_history: list[dict[str, Any]] = []

    @property
    def copilot_config(self) -> CopilotClientConfig:
        """Get the Copilot configuration."""
        return self._copilot_config

    @property
    def system_message(self) -> str:
        """Get the agent's system message."""
        return self._system_message

    @system_message.setter
    def system_message(self, message: str) -> None:
        """Set the agent's system message."""
        self._system_message = message

    def get_copilot_client(self) -> CopilotLLMClient | None:
        """Get the underlying Copilot client.

        Returns:
            The Copilot client if started, None otherwise
        """
        return self._copilot_client

    async def start_copilot(self) -> None:
        """Start the Copilot client session."""
        if self._copilot_client is None:
            self._copilot_client = CopilotLLMClient(self._copilot_config)
        await self._copilot_client.start()

    async def stop_copilot(self) -> None:
        """Stop the Copilot client session."""
        if self._copilot_client is not None:
            await self._copilot_client.stop()

    async def generate_reply(
        self,
        messages: list[dict[str, str]] | None = None,
        sender: "CopilotConversableAgent | None" = None,
    ) -> str | None:
        """Generate a reply to messages.

        Args:
            messages: List of message dicts with role and content
            sender: The agent sending the messages

        Returns:
            Generated reply content
        """
        if not self._copilot_client or not self._copilot_client.is_running:
            await self.start_copilot()

        # Prepare messages with system message
        full_messages = [{"role": "system", "content": self._system_message}]
        if messages:
            full_messages.extend(messages)

        # Generate response
        response = await self._copilot_client.create_async({
            "messages": full_messages,
            "model": self._copilot_config.model,
            "temperature": self._copilot_config.temperature,
            "max_tokens": self._copilot_config.max_tokens,
        })

        return response.content

    def reset(self) -> None:
        """Reset the agent's chat history."""
        self._chat_history.clear()

    def __repr__(self) -> str:
        return (
            f"CopilotConversableAgent(name={self.name!r}, "
            f"model={self._copilot_config.model!r})"
        )


class CopilotAssistantAgent(CopilotConversableAgent):
    """Task-oriented assistant agent with GitHub Copilot backend.

    This agent is specialized for task-oriented interactions,
    with optimized settings for code assistance and development tasks.

    Args:
        name: Agent identifier
        copilot_config: Copilot client configuration
        system_message: System message (defaults to assistant-optimized)
        description: Agent description for multi-agent scenarios

    Example:
        >>> agent = CopilotAssistantAgent(
        ...     name="code_assistant",
        ...     copilot_config={"model": "gpt-4", "temperature": 0.3},
        ... )
        >>> await agent.start_copilot()
        >>> response = await agent.generate_reply([
        ...     {"role": "user", "content": "Write a Python function to sort a list"}
        ... ])
    """

    def __init__(
        self,
        name: str,
        copilot_config: CopilotClientConfig | dict | None = None,
        system_message: str = COPILOT_ASSISTANT_SYSTEM_MESSAGE,
        description: str | None = None,
        **kwargs,
    ):
        # Default to NEVER for assistant agents
        super().__init__(
            name=name,
            copilot_config=copilot_config,
            system_message=system_message,
            human_input_mode="NEVER",
            **kwargs,
        )
        self.description = description or f"A GitHub Copilot-powered assistant: {name}"

    def __repr__(self) -> str:
        return (
            f"CopilotAssistantAgent(name={self.name!r}, "
            f"model={self._copilot_config.model!r})"
        )


__all__ = [
    "CopilotConversableAgent",
    "CopilotAssistantAgent",
]
