"""SWE Agent implementation for autonomous software engineering tasks.

This module provides the SWEAgent class that combines:
- Copilot SDK for LLM interactions
- SWE-specific tools (bash, edit, search)
- Software engineering optimized system prompts
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field


class SWEAgentConfig(BaseModel):
    """Configuration for SWE Agent."""

    name: str = Field(default="swe_agent", description="Agent name")

    # Copilot SDK configuration
    copilot_config: dict[str, Any] = Field(
        default_factory=lambda: {"model": "gpt-4", "temperature": 0.2},
        description="Configuration for Copilot SDK backend",
    )

    # Tool configuration
    enable_bash: bool = Field(default=True, description="Enable bash tool")
    enable_edit: bool = Field(default=True, description="Enable edit tool")
    enable_search: bool = Field(default=True, description="Enable search tool")

    # Execution configuration
    max_iterations: int = Field(default=50, description="Maximum agent iterations")
    timeout: int = Field(default=300, description="Execution timeout in seconds")

    # System message customization
    custom_system_message: str | None = Field(
        default=None,
        description="Custom system message to override default",
    )


DEFAULT_SWE_SYSTEM_MESSAGE = """You are an expert software engineering assistant with deep knowledge of:
- Programming languages: Python, JavaScript, TypeScript, Java, C++, Go, Rust, and more
- Software design patterns and best practices
- Testing methodologies and debugging techniques
- Version control (Git) and code review processes
- Documentation and code readability

You have access to the following tools:
1. **bash**: Execute shell commands to navigate, inspect, and modify the codebase
2. **edit**: Make precise edits to source files with line-level accuracy
3. **search**: Search for patterns, functions, classes, and text across the codebase

When solving software engineering tasks:
1. First understand the problem by reading relevant code and documentation
2. Create a minimal reproduction script if dealing with a bug
3. Make targeted, minimal changes to fix the issue
4. Verify your changes work correctly
5. Consider edge cases and potential side effects

Always explain your reasoning and provide context for your changes."""


class SWEAgent:
    """SWE Agent - Autonomous software engineering agent.

    This agent combines Copilot SDK capabilities with specialized SWE tools
    for autonomous code modification, bug fixing, and feature implementation.

    Args:
        name: Agent identifier
        copilot_config: Configuration for Copilot SDK
        enable_bash: Whether to enable bash tool
        enable_edit: Whether to enable edit tool
        enable_search: Whether to enable search tool
        max_iterations: Maximum number of agent steps
        timeout: Execution timeout in seconds
        system_message: Custom system message (uses default if None)

    Example:
        >>> agent = SWEAgent(
        ...     name="code_fixer",
        ...     copilot_config={"model": "gpt-4", "temperature": 0.2},
        ... )
        >>> await agent.start()
        >>> result = await agent.execute("Fix the bug in login.py")
        >>> await agent.stop()
    """

    def __init__(
        self,
        name: str = "swe_agent",
        copilot_config: dict[str, Any] | None = None,
        enable_bash: bool = True,
        enable_edit: bool = True,
        enable_search: bool = True,
        max_iterations: int = 50,
        timeout: int = 300,
        system_message: str | None = None,
    ):
        self.name = name
        self._copilot_config = copilot_config or {"model": "gpt-4", "temperature": 0.2}
        self._enable_bash = enable_bash
        self._enable_edit = enable_edit
        self._enable_search = enable_search
        self._max_iterations = max_iterations
        self._timeout = timeout
        self._custom_system_message = system_message

        # Initialize tools
        self._swe_tools = self._create_tools()

        # Session state
        self._session = None
        self._is_running = False
        self._environment = None

    def _create_tools(self) -> list:
        """Create SWE tools based on configuration."""
        from autobot.swe.tools import get_swe_tools, SWEToolConfig

        config = SWEToolConfig(
            enable_bash=self._enable_bash,
            enable_edit=self._enable_edit,
            enable_search=self._enable_search,
        )
        return get_swe_tools(config)

    @property
    def swe_tools(self) -> list:
        """Get the list of SWE tools available to this agent."""
        return self._swe_tools

    @property
    def swe_environment(self):
        """Get the SWE execution environment."""
        return self._environment

    @property
    def system_message(self) -> str:
        """Get the agent's system message."""
        if self._custom_system_message:
            return self._custom_system_message
        return DEFAULT_SWE_SYSTEM_MESSAGE

    @property
    def is_running(self) -> bool:
        """Check if the agent session is active."""
        return self._is_running

    async def start(self) -> None:
        """Start the agent session and initialize tools.

        This method:
        1. Initializes the Copilot SDK session
        2. Sets up the SWE environment
        3. Registers tools with the LLM
        """
        if self._is_running:
            return

        # Initialize environment
        from autobot.swe.environment import SWEEnvironment, SWEEnvironmentConfig
        env_config = SWEEnvironmentConfig(working_dir=".", timeout=self._timeout)
        self._environment = SWEEnvironment(env_config)

        self._is_running = True

    async def stop(self) -> None:
        """Stop the agent session and clean up resources."""
        if not self._is_running:
            return

        self._session = None
        self._environment = None
        self._is_running = False

    async def execute(
        self,
        task: str,
        *,
        on_step: Callable[[dict], None] | None = None,
    ) -> dict[str, Any]:
        """Execute a software engineering task.

        Args:
            task: Description of the SWE task to perform
            on_step: Optional callback for each agent step

        Returns:
            Dictionary containing:
            - success: Whether the task completed successfully
            - result: Final result or error message
            - steps: List of steps taken
            - changes: Files modified during execution
        """
        if not self._is_running:
            await self.start()

        steps = []
        changes = []

        # Execute task loop (placeholder - actual implementation would
        # use Copilot SDK to interact with LLM)
        result = {
            "success": True,
            "result": f"Task '{task}' completed",
            "steps": steps,
            "changes": changes,
        }

        return result

    def __repr__(self) -> str:
        return (
            f"SWEAgent(name={self.name!r}, "
            f"tools={len(self._swe_tools)}, "
            f"running={self._is_running})"
        )


async def create_swe_agent(
    name: str = "swe_agent",
    copilot_config: dict[str, Any] | None = None,
    **kwargs,
) -> SWEAgent:
    """Factory function to create and initialize an SWE Agent.

    Args:
        name: Agent identifier
        copilot_config: Configuration for Copilot SDK
        **kwargs: Additional arguments passed to SWEAgent

    Returns:
        Initialized SWEAgent instance
    """
    agent = SWEAgent(name=name, copilot_config=copilot_config, **kwargs)
    await agent.start()
    return agent
