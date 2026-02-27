"""SWE Environment for autonomous software engineering.

This module provides the execution environment for Autobots:
- SWEEnvironmentConfig: Configuration for the environment
- SWEEnvironment: Runtime environment for executing SWE tasks
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class SWEEnvironmentConfig(BaseModel):
    """Configuration for SWE execution environment.

    Args:
        working_dir: Base working directory for operations
        timeout: Default command timeout in seconds
        shell: Shell to use for command execution
        env_vars: Additional environment variables
        cleanup_on_exit: Clean up temporary files on exit
    """

    working_dir: str = Field(default=".", description="Working directory")
    timeout: int = Field(default=30, description="Default timeout in seconds")
    shell: str = Field(default="/bin/bash", description="Shell for command execution")

    env_vars: dict[str, str] = Field(
        default_factory=lambda: {
            "PAGER": "cat",
            "MANPAGER": "cat",
            "LESS": "-R",
            "GIT_PAGER": "cat",
            "PIP_PROGRESS_BAR": "off",
        },
        description="Environment variables for execution",
    )

    cleanup_on_exit: bool = Field(
        default=True,
        description="Clean up temporary files on environment close",
    )

    # Repository settings
    repo_path: str | None = Field(
        default=None,
        description="Path to repository (if working with a repo)",
    )
    base_commit: str | None = Field(
        default=None,
        description="Base commit to reset to on environment start",
    )


class SWEEnvironment:
    """Execution environment for SWE tasks.

    Provides a sandboxed environment for executing software engineering
    operations including:
    - Shell command execution
    - File system operations
    - Git operations
    - Process management

    Args:
        config: Environment configuration

    Example:
        >>> config = SWEEnvironmentConfig(working_dir="/path/to/repo")
        >>> env = SWEEnvironment(config)
        >>> env.start()
        >>> result = env.run_command("ls -la")
        >>> env.close()
    """

    def __init__(self, config: SWEEnvironmentConfig | None = None):
        self.config = config or SWEEnvironmentConfig()
        self._working_dir = Path(self.config.working_dir).resolve()
        self._is_running = False
        self._process = None
        self._history: list[dict[str, Any]] = []

    @property
    def working_dir(self) -> Path:
        """Get the current working directory."""
        return self._working_dir

    @property
    def is_running(self) -> bool:
        """Check if the environment is active."""
        return self._is_running

    @property
    def history(self) -> list[dict[str, Any]]:
        """Get command execution history."""
        return self._history.copy()

    def start(self) -> None:
        """Start the execution environment.

        This method:
        1. Validates the working directory
        2. Sets up environment variables
        3. Optionally resets to base commit
        """
        if self._is_running:
            return

        # Ensure working directory exists
        self._working_dir.mkdir(parents=True, exist_ok=True)

        # Set up environment
        self._env = os.environ.copy()
        self._env.update(self.config.env_vars)

        # Reset to base commit if specified
        if self.config.repo_path and self.config.base_commit:
            self._reset_repository()

        self._is_running = True

    def _reset_repository(self) -> None:
        """Reset repository to base commit."""
        if not self.config.base_commit:
            return

        repo_path = Path(self.config.repo_path or self.config.working_dir)
        try:
            subprocess.run(
                ["git", "checkout", self.config.base_commit],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            pass  # Ignore errors if not a git repo

    def run_command(
        self,
        command: str,
        *,
        timeout: int | None = None,
        capture_output: bool = True,
    ) -> dict[str, Any]:
        """Execute a command in the environment.

        Args:
            command: Shell command to execute
            timeout: Optional timeout override
            capture_output: Whether to capture stdout/stderr

        Returns:
            Dictionary with stdout, stderr, return_code
        """
        if not self._is_running:
            self.start()

        effective_timeout = timeout or self.config.timeout

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=capture_output,
                text=True,
                timeout=effective_timeout,
                cwd=self._working_dir,
                env=self._env,
            )

            output = {
                "success": result.returncode == 0,
                "stdout": result.stdout if capture_output else "",
                "stderr": result.stderr if capture_output else "",
                "return_code": result.returncode,
                "command": command,
            }

        except subprocess.TimeoutExpired:
            output = {
                "success": False,
                "stdout": "",
                "stderr": f"Command timed out after {effective_timeout}s",
                "return_code": -1,
                "command": command,
            }
        except Exception as e:
            output = {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "command": command,
            }

        self._history.append(output)
        return output

    def read_file(self, path: str) -> dict[str, Any]:
        """Read a file from the environment.

        Args:
            path: Path to file (relative to working_dir)

        Returns:
            Dictionary with content and metadata
        """
        full_path = self._working_dir / path

        try:
            content = full_path.read_text()
            return {
                "success": True,
                "content": content,
                "path": str(full_path),
                "size": len(content),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "content": "",
                "error": f"File not found: {path}",
            }
        except Exception as e:
            return {
                "success": False,
                "content": "",
                "error": str(e),
            }

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        """Write content to a file in the environment.

        Args:
            path: Path to file (relative to working_dir)
            content: Content to write

        Returns:
            Dictionary with success status
        """
        full_path = self._working_dir / path

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            return {
                "success": True,
                "path": str(full_path),
                "size": len(content),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def change_directory(self, path: str) -> dict[str, Any]:
        """Change the working directory.

        Args:
            path: New working directory (relative or absolute)

        Returns:
            Dictionary with new working directory
        """
        try:
            if Path(path).is_absolute():
                new_dir = Path(path)
            else:
                new_dir = self._working_dir / path

            new_dir = new_dir.resolve()

            if not new_dir.exists():
                return {
                    "success": False,
                    "error": f"Directory not found: {path}",
                }

            if not new_dir.is_dir():
                return {
                    "success": False,
                    "error": f"Not a directory: {path}",
                }

            self._working_dir = new_dir
            return {
                "success": True,
                "working_dir": str(self._working_dir),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def get_state(self) -> dict[str, Any]:
        """Get current environment state.

        Returns:
            Dictionary with environment state information
        """
        return {
            "working_dir": str(self._working_dir),
            "is_running": self._is_running,
            "env_vars": self.config.env_vars,
            "command_count": len(self._history),
        }

    def reset(self) -> None:
        """Reset the environment to initial state."""
        self._history.clear()
        self._working_dir = Path(self.config.working_dir).resolve()

        if self.config.repo_path and self.config.base_commit:
            self._reset_repository()

    def close(self) -> None:
        """Close the environment and clean up resources."""
        if not self._is_running:
            return

        if self.config.cleanup_on_exit:
            # Clean up temporary files if any
            pass

        self._is_running = False
        self._history.clear()

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def __repr__(self) -> str:
        return (
            f"SWEEnvironment(working_dir={self._working_dir!r}, "
            f"running={self._is_running})"
        )


__all__ = [
    "SWEEnvironmentConfig",
    "SWEEnvironment",
]
