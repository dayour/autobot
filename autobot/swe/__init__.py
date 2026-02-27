"""SWE (Software Engineering) module for autobot.

This module provides autonomous software engineering capabilities including:
- SWEAgent: An agent specialized for software engineering tasks
- SWE Tools: Bash, edit, and search tools for code manipulation
- SWE Environment: Execution environment for SWE tasks
- SWE Swarms: Multi-agent collaboration for complex SWE tasks
"""

from __future__ import annotations

from autobot.swe.agent import SWEAgent
from autobot.swe.tools import (
    SWEToolConfig,
    get_swe_tools,
    SWETool,
    BashTool,
    EditTool,
    SearchTool,
)
from autobot.swe.environment import (
    SWEEnvironment,
    SWEEnvironmentConfig,
)
from autobot.swe.swarms import (
    SWESwarmConfig,
    SWESwarmManager,
    create_code_review_swarm,
    create_debug_swarm,
    create_test_swarm,
)

__all__ = [
    # Agent
    "SWEAgent",
    # Tools
    "SWEToolConfig",
    "get_swe_tools",
    "SWETool",
    "BashTool",
    "EditTool",
    "SearchTool",
    # Environment
    "SWEEnvironment",
    "SWEEnvironmentConfig",
    # Swarms
    "SWESwarmConfig",
    "SWESwarmManager",
    "create_code_review_swarm",
    "create_debug_swarm",
    "create_test_swarm",
]
