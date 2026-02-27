"""Copilot SDK configuration and utilities for autobot."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class CopilotSDKConfig(BaseModel):
    """Configuration for GitHub Copilot SDK integration.
    
    This configuration controls how autobot interacts with the Copilot CLI
    when using the Copilot SDK backend for LLM interactions.
    """
    
    cli_path: str | None = Field(
        default=None,
        description="Path to the copilot CLI executable. If None, uses 'copilot' from PATH.",
    )
    
    cli_url: str | None = Field(
        default=None,
        description="URL to connect to an external Copilot CLI server (e.g., 'localhost:3000').",
    )
    
    use_stdio: bool = Field(
        default=True,
        description="Use stdio for communication with CLI. Set to False for TCP.",
    )
    
    log_level: str = Field(
        default="warn",
        description="Log level for Copilot CLI: debug, info, warn, error",
    )
    
    session_persistence_enabled: bool = Field(
        default=False,
        description="Enable session persistence to save/resume sessions.",
    )
    
    session_storage_path: Path | None = Field(
        default=None,
        description="Directory to store persisted sessions.",
    )
    
    enable_all_tools: bool = Field(
        default=True,
        description="Enable all first-party Copilot CLI tools by default.",
    )
    
    additional_cli_args: list[str] = Field(
        default_factory=list,
        description="Additional command-line arguments to pass to Copilot CLI.",
    )


def get_copilot_cli_path() -> str | None:
    """Get the path to the Copilot CLI executable.
    
    Returns:
        Path to copilot CLI or None if using default PATH lookup.
    """
    return os.getenv("COPILOT_CLI_PATH")


def is_copilot_cli_available() -> bool:
    """Check if the Copilot CLI is available.
    
    Returns:
        True if copilot CLI can be found, False otherwise.
    """
    import shutil
    
    cli_path = get_copilot_cli_path()
    if cli_path:
        return Path(cli_path).exists()
    
    # Check if 'copilot' is in PATH
    return shutil.which("copilot") is not None


__all__ = [
    "CopilotSDKConfig",
    "get_copilot_cli_path",
    "is_copilot_cli_available",
]
