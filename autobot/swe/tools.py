"""SWE Tools for autonomous software engineering.

This module provides specialized tools for software engineering tasks:
- BashTool: Execute shell commands
- EditTool: Make precise file edits
- SearchTool: Search codebase for patterns
"""

from __future__ import annotations

import os
import subprocess
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class SWEToolConfig(BaseModel):
    """Configuration for SWE tools.

    Args:
        enable_bash: Enable bash/shell command execution
        enable_edit: Enable file editing capabilities
        enable_search: Enable code search capabilities
        working_dir: Base working directory for operations
        timeout: Default timeout for tool operations
        blocklist: Commands that are blocked from execution
    """

    enable_bash: bool = Field(default=True, description="Enable bash tool")
    enable_edit: bool = Field(default=True, description="Enable edit tool")
    enable_search: bool = Field(default=True, description="Enable search tool")

    working_dir: str = Field(default=".", description="Working directory")
    timeout: int = Field(default=30, description="Default timeout in seconds")

    blocklist: list[str] = Field(
        default_factory=lambda: [
            "vim", "vi", "emacs", "nano",  # Interactive editors
            "less", "more",  # Interactive pagers
            "gdb", "lldb",  # Interactive debuggers
            "python", "python3", "ipython",  # Interactive shells (standalone)
            "bash", "sh", "zsh",  # Shell spawning
            "rm -rf /",  # Dangerous commands
        ],
        description="Commands blocked from execution",
    )


class SWETool(ABC):
    """Base class for SWE tools."""

    def __init__(self, name: str, description: str):
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        """Tool name."""
        return self._name

    @property
    def description(self) -> str:
        """Tool description."""
        return self._description

    @abstractmethod
    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute the tool with given parameters."""
        pass

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._get_parameters_schema(),
            },
        }

    @abstractmethod
    def _get_parameters_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool-specific parameters."""
        pass


class BashTool(SWETool):
    """Execute bash commands in the SWE environment.

    This tool allows the agent to run shell commands for:
    - Navigating the filesystem
    - Running tests and scripts
    - Installing dependencies
    - Git operations
    - General system commands
    """

    def __init__(self, config: SWEToolConfig | None = None):
        super().__init__(
            name="bash",
            description="Execute a bash command in the current working directory",
        )
        self.config = config or SWEToolConfig()

    async def execute(
        self,
        command: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute a bash command.

        Args:
            command: The bash command to execute
            timeout: Optional timeout override

        Returns:
            Dictionary with stdout, stderr, and return_code
        """
        # Check blocklist
        for blocked in self.config.blocklist:
            if command.strip().startswith(blocked) or command.strip() == blocked:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Command '{blocked}' is blocked for safety",
                    "return_code": 1,
                }

        effective_timeout = timeout or self.config.timeout

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=self.config.working_dir,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Command timed out after {effective_timeout} seconds",
                "return_code": -1,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
            }

    def _get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout in seconds",
                },
            },
            "required": ["command"],
        }


class EditTool(SWETool):
    """Make precise edits to source files.

    This tool allows the agent to:
    - Replace specific lines in files
    - Insert new content
    - Delete lines
    - Create new files
    """

    def __init__(self, config: SWEToolConfig | None = None):
        super().__init__(
            name="edit",
            description="Edit a file by replacing content at specific lines",
        )
        self.config = config or SWEToolConfig()

    async def execute(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        *,
        create_if_missing: bool = False,
    ) -> dict[str, Any]:
        """Edit a file by replacing content.

        Args:
            file_path: Path to the file to edit
            old_content: Content to find and replace
            new_content: Content to insert in place of old_content
            create_if_missing: Create the file if it doesn't exist

        Returns:
            Dictionary with success status and details
        """
        full_path = Path(self.config.working_dir) / file_path

        try:
            if not full_path.exists():
                if create_if_missing:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(new_content)
                    return {
                        "success": True,
                        "message": f"Created new file: {file_path}",
                        "lines_changed": len(new_content.splitlines()),
                    }
                else:
                    return {
                        "success": False,
                        "message": f"File not found: {file_path}",
                        "lines_changed": 0,
                    }

            content = full_path.read_text()

            if old_content not in content:
                return {
                    "success": False,
                    "message": f"Content not found in {file_path}",
                    "lines_changed": 0,
                }

            # Replace content
            new_file_content = content.replace(old_content, new_content, 1)
            full_path.write_text(new_file_content)

            lines_changed = abs(
                len(new_content.splitlines()) - len(old_content.splitlines())
            ) + 1

            return {
                "success": True,
                "message": f"Successfully edited {file_path}",
                "lines_changed": lines_changed,
            }

        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "lines_changed": 0,
            }

    def _get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_content": {
                    "type": "string",
                    "description": "Content to find and replace",
                },
                "new_content": {
                    "type": "string",
                    "description": "New content to insert",
                },
                "create_if_missing": {
                    "type": "boolean",
                    "description": "Create file if it doesn't exist",
                    "default": False,
                },
            },
            "required": ["file_path", "old_content", "new_content"],
        }


class SearchTool(SWETool):
    """Search for patterns in the codebase.

    This tool allows the agent to:
    - Search for text patterns across files
    - Find function/class definitions
    - Locate files by name patterns
    - Grep-style searches with context
    """

    def __init__(self, config: SWEToolConfig | None = None):
        super().__init__(
            name="search",
            description="Search for patterns in files across the codebase",
        )
        self.config = config or SWEToolConfig()

    async def execute(
        self,
        pattern: str,
        *,
        file_pattern: str = "*",
        search_type: Literal["content", "filename"] = "content",
        context_lines: int = 2,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Search for patterns in the codebase.

        Args:
            pattern: Regex pattern to search for
            file_pattern: Glob pattern to filter files
            search_type: Search file content or filenames
            context_lines: Lines of context around matches
            max_results: Maximum number of results to return

        Returns:
            Dictionary with matches and metadata
        """
        working_path = Path(self.config.working_dir)
        matches = []

        try:
            if search_type == "filename":
                # Search for files by name
                for file_path in working_path.rglob(file_pattern):
                    if file_path.is_file() and re.search(pattern, file_path.name):
                        matches.append({
                            "file": str(file_path.relative_to(working_path)),
                            "type": "filename",
                        })
                        if len(matches) >= max_results:
                            break
            else:
                # Search file contents
                for file_path in working_path.rglob(file_pattern):
                    if not file_path.is_file():
                        continue
                    try:
                        content = file_path.read_text()
                        lines = content.splitlines()

                        for i, line in enumerate(lines):
                            if re.search(pattern, line):
                                # Get context
                                start = max(0, i - context_lines)
                                end = min(len(lines), i + context_lines + 1)
                                context = lines[start:end]

                                matches.append({
                                    "file": str(file_path.relative_to(working_path)),
                                    "line": i + 1,
                                    "content": line.strip(),
                                    "context": context,
                                })

                                if len(matches) >= max_results:
                                    break

                    except (UnicodeDecodeError, PermissionError):
                        continue

                    if len(matches) >= max_results:
                        break

            return {
                "success": True,
                "pattern": pattern,
                "matches": matches,
                "total_matches": len(matches),
                "truncated": len(matches) >= max_results,
            }

        except Exception as e:
            return {
                "success": False,
                "pattern": pattern,
                "matches": [],
                "error": str(e),
            }

    def _get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py')",
                    "default": "*",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["content", "filename"],
                    "description": "Search file content or filenames",
                    "default": "content",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of context around matches",
                    "default": 2,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 50,
                },
            },
            "required": ["pattern"],
        }


def get_swe_tools(config: SWEToolConfig | None = None) -> list[SWETool]:
    """Get the list of SWE tools based on configuration.

    Args:
        config: Tool configuration. If None, uses defaults.

    Returns:
        List of enabled SWE tools
    """
    config = config or SWEToolConfig()
    tools = []

    if config.enable_bash:
        tools.append(BashTool(config))
    if config.enable_edit:
        tools.append(EditTool(config))
    if config.enable_search:
        tools.append(SearchTool(config))

    return tools


__all__ = [
    "SWEToolConfig",
    "SWETool",
    "BashTool",
    "EditTool",
    "SearchTool",
    "get_swe_tools",
]
