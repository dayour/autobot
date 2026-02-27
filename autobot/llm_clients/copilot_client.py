"""GitHub Copilot SDK LLM Client for autobot framework.

This module provides integration with GitHub Copilot SDK for LLM interactions,
enabling use of Copilot's models within the autobot framework.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

# Check for Copilot SDK availability
try:
    from github_copilot import create_client
    COPILOT_SDK_AVAILABLE = True
except ImportError:
    COPILOT_SDK_AVAILABLE = False
    create_client = None


class CopilotClientConfig(BaseModel):
    """Configuration for Copilot LLM Client.

    Args:
        model: Model identifier (e.g., 'gpt-4', 'claude-sonnet-4.5')
        temperature: Sampling temperature (0.0 to 2.0)
        max_tokens: Maximum tokens in response
        cli_path: Path to Copilot CLI (optional)
        cli_url: URL for Copilot CLI server (optional)
        use_stdio: Use stdio for communication
        log_level: Logging level for Copilot CLI
        enable_all_tools: Enable all Copilot tools by default
    """

    model: str = Field(default="gpt-5", description="Model identifier")
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        description="Maximum tokens in response",
    )

    # Copilot CLI configuration
    cli_path: str | None = Field(
        default=None,
        description="Path to Copilot CLI executable",
    )
    cli_url: str | None = Field(
        default=None,
        description="URL for Copilot CLI server",
    )
    use_stdio: bool = Field(
        default=True,
        description="Use stdio for CLI communication",
    )
    log_level: Literal["debug", "info", "warn", "error"] = Field(
        default="warn",
        description="Log level for Copilot CLI",
    )
    enable_all_tools: bool = Field(
        default=True,
        description="Enable all Copilot tools",
    )


@dataclass
class CopilotResponse:
    """Response from Copilot LLM."""

    content: str
    model: str
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)


class CopilotLLMClient:
    """LLM Client using GitHub Copilot SDK.

    This client provides integration with GitHub Copilot for use
    within the autobot framework, supporting both sync and async
    interfaces.

    Args:
        config: Client configuration

    Example:
        >>> config = CopilotClientConfig(model="gpt-4", temperature=0.7)
        >>> client = CopilotLLMClient(config)
        >>> await client.start()
        >>> response = await client.create_async({
        ...     "messages": [{"role": "user", "content": "Hello"}]
        ... })
        >>> await client.stop()
    """

    def __init__(self, config: CopilotClientConfig | dict | None = None):
        if isinstance(config, dict):
            self.config = CopilotClientConfig(**config)
        elif config is None:
            self.config = CopilotClientConfig()
        else:
            self.config = config

        self._client = None
        self._session = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Check if client is running."""
        return self._is_running

    async def start(self) -> None:
        """Start the Copilot client session."""
        if not COPILOT_SDK_AVAILABLE:
            raise RuntimeError(
                "GitHub Copilot SDK is not available. "
                "Install with: pip install github-copilot-sdk"
            )

        if self._is_running:
            return

        # Create Copilot client (placeholder - actual implementation
        # would initialize the real Copilot SDK client)
        self._is_running = True

    async def stop(self) -> None:
        """Stop the Copilot client session."""
        if not self._is_running:
            return

        self._client = None
        self._session = None
        self._is_running = False

    async def create_async(self, params: dict) -> CopilotResponse:
        """Create a completion asynchronously.

        Args:
            params: Request parameters including:
                - messages: List of message dicts with role and content
                - model: Optional model override
                - temperature: Optional temperature override
                - max_tokens: Optional max_tokens override

        Returns:
            CopilotResponse with the completion
        """
        if not self._is_running:
            await self.start()

        messages = params.get("messages", [])
        model = params.get("model", self.config.model)
        temperature = params.get("temperature", self.config.temperature)
        max_tokens = params.get("max_tokens", self.config.max_tokens)

        # Placeholder for actual Copilot SDK call
        # In real implementation, this would call the Copilot SDK
        response_content = f"[Copilot Response] Model: {model}"

        return CopilotResponse(
            content=response_content,
            model=model,
            finish_reason="stop",
            usage={
                "prompt_tokens": sum(len(m.get("content", "")) for m in messages),
                "completion_tokens": len(response_content),
                "total_tokens": 0,  # Would be calculated
            },
        )

    def create(self, params: dict) -> CopilotResponse:
        """Create a completion synchronously.

        Args:
            params: Request parameters (same as create_async)

        Returns:
            CopilotResponse with the completion
        """
        return asyncio.run(self.create_async(params))

    def message_retrieval(self, response: CopilotResponse) -> list[str]:
        """Extract message content from response.

        Args:
            response: CopilotResponse object

        Returns:
            List of message contents
        """
        return [response.content]

    def cost(self, response: CopilotResponse) -> float:
        """Calculate cost of the response.

        Args:
            response: CopilotResponse object

        Returns:
            Estimated cost (placeholder)
        """
        # Placeholder - actual cost calculation would depend on model
        return 0.0

    @staticmethod
    def get_usage(response: CopilotResponse) -> dict:
        """Get usage statistics from response.

        Args:
            response: CopilotResponse object

        Returns:
            Usage dictionary
        """
        return response.usage

    def __repr__(self) -> str:
        return (
            f"CopilotLLMClient(model={self.config.model!r}, "
            f"running={self._is_running})"
        )


__all__ = [
    "COPILOT_SDK_AVAILABLE",
    "CopilotClientConfig",
    "CopilotLLMClient",
    "CopilotResponse",
]
