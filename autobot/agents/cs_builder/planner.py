"""RequirementsPlannerAgent — normalizes free-form requirements into agent_spec.json.

Takes free-form requirements text or an existing repo and produces a
structured ``agent_spec.json`` conforming to the schema.

Integrated with CopilotLLMClient for LLM-powered spec generation:
- Analyzes free-form text to extract intents, data sources, actions
- Normalizes into structured topics with trigger phrases
- Maps data sources to knowledge source types
- Identifies connectors and authentication patterns
- Applies enterprise governance defaults

Falls back to heuristic extraction when the LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from autobot.agents.cs_builder._base import CopilotAgentMixin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class PlannerConfig(BaseModel):
    """Configuration for RequirementsPlannerAgent."""

    name: str = Field(default="requirements_planner", description="Agent name")
    copilot_config: dict[str, Any] = Field(
        default_factory=lambda: {"model": "gpt-5", "temperature": 0.3},
        description="Copilot SDK backend configuration",
    )
    schema_path: str = Field(
        default="",
        description="Path to agent_spec.schema.json for validation.",
    )


# ---------------------------------------------------------------------------
# System messages
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_MESSAGE = """\
You are an expert Microsoft Power Platform solution architect specializing in \
Copilot Studio agent design.

Your task is to analyze free-form requirements and produce a structured \
agent_spec.json that conforms to the Copilot Studio Agent Specification schema.

## Analysis Steps

1. **Identify Purpose & Audience**: What is the agent for? Who will use it?
2. **Extract Topics**: What conversational intents exist?  Produce 3-5 \
   trigger phrases per topic.
3. **Map Knowledge Sources**: Identify data backing (SharePoint sites, web \
   pages, files, Dataverse tables).  Use the correct type enum.
4. **Identify Actions**: Map to Power Platform connectors (ServiceNow, Teams, \
   HTTP, SQL, SharePoint, Office365Users, etc.).
5. **Determine Channels**: teams, m365_copilot, web, custom.
6. **Apply Security Defaults**: PII blocking, Entra ID auth, no external \
   access unless explicitly stated.
7. **ALM Configuration**: Managed solutions outside dev, environment variables \
   for all environment-specific settings.

## Output Format

Return ONLY a valid JSON object matching the agent_spec schema.  Do NOT \
include markdown fences or commentary — raw JSON only.

## Enterprise Rules (ALWAYS apply)

- auth for every action MUST be "connectionReference"
- alm.useEnvironmentVariables MUST be true
- alm.managedOutsideDev MUST be true
- security.authenticationMode MUST be "entra_id"
- security.allowExternal MUST be false unless user explicitly requests it
- publisher.prefix must be a short lowercase alphabetic string
"""

REVIEW_SYSTEM_MESSAGE = """\
You are a senior Power Platform reviewer.  Given an agent_spec.json, review it \
for completeness, security, and ALM best practices.  Return a JSON object with:

{
  "approved": true/false,
  "issues": [{"severity": "error"|"warning", "field": "$.path", "message": "..."}],
  "suggestions": ["..."],
  "revised_spec": { ... the fixed spec if issues found ... }
}

Only return raw JSON.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class RequirementsPlannerAgent(CopilotAgentMixin):
    """Converts free-form requirements into a structured agent_spec.json.

    Uses Copilot SDK LLM for intelligent analysis when available,
    falling back to heuristic extraction otherwise.

    Args:
        copilot_config: Copilot SDK backend configuration.
        config: Full planner configuration.

    Example::

        planner = RequirementsPlannerAgent()
        spec = await planner.generate_spec(
            requirements="Build an IT helpdesk agent that answers policy questions "
            "from our SharePoint wiki and can create ServiceNow tickets."
        )
    """

    def __init__(
        self,
        copilot_config: dict[str, Any] | None = None,
        config: PlannerConfig | None = None,
    ):
        self._config = config or PlannerConfig(
            **({"copilot_config": copilot_config} if copilot_config else {}),
        )
        self._copilot_config = self._config.copilot_config
        self.name = self._config.name
        self._is_running = False
        self._reasoning_trace: list[dict[str, Any]] = []

    @property
    def system_message(self) -> str:
        return PLANNER_SYSTEM_MESSAGE

    async def start(self) -> None:
        self._is_running = True
        await self._start_llm()

    async def stop(self) -> None:
        await self._stop_llm()
        self._is_running = False

    # -- LLM-powered spec generation ----------------------------------------

    async def generate_spec(
        self,
        requirements: str,
        *,
        repo_path: str | None = None,
        review: bool = True,
    ) -> dict[str, Any]:
        """Generate an agent_spec from free-form requirements.

        When the LLM is available, sends the requirements through a
        structured prompt and parses the JSON response.  When unavailable,
        falls back to heuristic keyword extraction.

        Args:
            requirements: Free-form description of the desired agent.
            repo_path: Optional path to an existing repo for context.
            review: If True and LLM available, run a self-review pass.

        Returns:
            A valid agent_spec dict.
        """
        # Augment prompt with repo context if provided
        context = ""
        if repo_path:
            context = self._scan_repo_context(repo_path)

        # Try LLM-powered generation
        if self.llm_available:
            return await self._generate_spec_llm(requirements, context, review=review)

        # Fallback: heuristic extraction
        logger.info("[%s] LLM unavailable, using heuristic extraction", self.name)
        return self._generate_spec_heuristic(requirements)

    async def _generate_spec_llm(
        self,
        requirements: str,
        context: str,
        *,
        review: bool = True,
    ) -> dict[str, Any]:
        """LLM-powered spec generation with optional self-review."""
        user_prompt = f"## Requirements\n\n{requirements}"
        if context:
            user_prompt += f"\n\n## Repository Context\n\n{context}"

        # Step 1: Generate initial spec
        raw = await self._llm_complete(
            system_message=PLANNER_SYSTEM_MESSAGE,
            user_message=user_prompt,
            temperature=0.3,
            expect_json=True,
        )

        try:
            spec = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[%s] LLM returned invalid JSON, falling back to heuristic", self.name)
            return self._generate_spec_heuristic(requirements)

        # Enforce enterprise invariants (LLM may deviate)
        spec = self._enforce_enterprise_defaults(spec)

        # Step 2: Self-review pass
        if review:
            spec = await self._review_spec(spec)

        return spec

    async def _review_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        """LLM-powered review pass: checks completeness and governance."""
        if not self.llm_available:
            return spec

        try:
            review_prompt = (
                "Review this agent_spec.json for completeness, security, "
                "and ALM best practices:\n\n"
                + json.dumps(spec, indent=2)
            )
            raw = await self._llm_complete(
                system_message=REVIEW_SYSTEM_MESSAGE,
                user_message=review_prompt,
                temperature=0.1,
                expect_json=True,
            )
            review = json.loads(raw)

            # If the reviewer produced a revised spec and found errors, use it
            if not review.get("approved", True) and review.get("revised_spec"):
                revised = review["revised_spec"]
                revised = self._enforce_enterprise_defaults(revised)
                logger.info(
                    "[%s] Review found %d issues, applying revised spec",
                    self.name, len(review.get("issues", [])),
                )
                return revised

        except (json.JSONDecodeError, RuntimeError) as exc:
            logger.debug("[%s] Review pass failed (%s), keeping original", self.name, exc)

        return spec

    async def review_existing_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Review an existing spec and return findings.

        Returns:
            Dict with 'approved', 'issues', 'suggestions', and optionally
            'revised_spec'.
        """
        if not self.llm_available:
            # Structural review only
            validation = await self.validate_spec(spec)
            return {
                "approved": validation["valid"],
                "issues": [
                    {"severity": "error", "field": "", "message": e}
                    for e in validation["errors"]
                ],
                "suggestions": [],
            }

        review_prompt = (
            "Review this agent_spec.json thoroughly:\n\n"
            + json.dumps(spec, indent=2)
        )
        raw = await self._llm_complete(
            system_message=REVIEW_SYSTEM_MESSAGE,
            user_message=review_prompt,
            temperature=0.1,
            expect_json=True,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"approved": True, "issues": [], "suggestions": []}

    # -- heuristic fallback -------------------------------------------------

    def _generate_spec_heuristic(self, requirements: str) -> dict[str, Any]:
        """Keyword-based extraction when LLM is unavailable."""
        spec: dict[str, Any] = {
            "name": "New Agent",
            "description": requirements[:200],
            "publisher": {
                "displayName": "Organization Publisher",
                "prefix": "org",
            },
            "environments": {
                "source": "dev",
                "targets": ["test", "prod"],
            },
            "knowledgeSources": [],
            "actions": [],
            "channels": ["teams"],
            "security": {
                "dataLossPrevention": ["pii-block"],
                "allowExternal": False,
                "authenticationMode": "entra_id",
            },
            "alm": {
                "managedOutsideDev": True,
                "useEnvironmentVariables": True,
                "solutionVersion": "1.0.0.0",
            },
            "telemetry": {
                "enable": True,
                "sampling": 0.25,
            },
            "topics": [],
        }

        req_lower = requirements.lower()

        if "sharepoint" in req_lower:
            spec["knowledgeSources"].append({
                "type": "sharepoint",
                "url": "https://TODO.sharepoint.com/sites/TODO",
                "scope": "site",
                "description": "SharePoint knowledge source (update URL)",
            })

        if "servicenow" in req_lower or "ticket" in req_lower:
            spec["actions"].append({
                "name": "CreateTicket",
                "connector": "ServiceNow",
                "auth": "connectionReference",
                "description": "Create support ticket",
            })

        if "teams" in req_lower:
            if "teams" not in spec["channels"]:
                spec["channels"].append("teams")

        if "copilot" in req_lower or "m365" in req_lower:
            spec["channels"].append("m365_copilot")

        return spec

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _enforce_enterprise_defaults(spec: dict[str, Any]) -> dict[str, Any]:
        """Guarantee enterprise ALM invariants regardless of LLM output."""
        alm = spec.setdefault("alm", {})
        alm["managedOutsideDev"] = True
        alm["useEnvironmentVariables"] = True

        sec = spec.setdefault("security", {})
        sec.setdefault("authenticationMode", "entra_id")
        sec.setdefault("allowExternal", False)
        sec.setdefault("dataLossPrevention", ["pii-block"])

        # Force connectionReference on all actions
        for action in spec.get("actions", []):
            action["auth"] = "connectionReference"

        spec.setdefault("environments", {"source": "dev", "targets": ["test", "prod"]})
        spec.setdefault("channels", ["teams"])
        return spec

    @staticmethod
    def _scan_repo_context(repo_path: str) -> str:
        """Scan a repo for context clues (README, package.json, etc.)."""
        p = Path(repo_path)
        context_parts: list[str] = []

        for name in ("README.md", "README.txt", "package.json", "pyproject.toml"):
            fp = p / name
            if fp.exists():
                text = fp.read_text(encoding="utf-8", errors="ignore")[:2000]
                context_parts.append(f"### {name}\n```\n{text}\n```")

        return "\n\n".join(context_parts) if context_parts else ""

    async def generate_spec_from_file(self, requirements_path: str) -> dict[str, Any]:
        """Read requirements from a file and generate a spec."""
        p = Path(requirements_path)
        if not p.exists():
            msg = f"Requirements file not found: {requirements_path}"
            raise FileNotFoundError(msg)
        text = p.read_text(encoding="utf-8")
        return await self.generate_spec(text)

    async def validate_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Validate a spec dict against required fields."""
        errors: list[str] = []

        for field in ("name", "publisher", "environments", "channels"):
            if field not in spec:
                errors.append(f"Missing required field: {field}")

        pub = spec.get("publisher", {})
        if not pub.get("displayName"):
            errors.append("publisher.displayName is required")
        if not pub.get("prefix"):
            errors.append("publisher.prefix is required")

        channels = spec.get("channels", [])
        if not channels:
            errors.append("At least one channel is required")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def __repr__(self) -> str:
        return f"RequirementsPlannerAgent(name={self.name!r}, llm={'yes' if self.llm_available else 'no'})"


__all__ = [
    "RequirementsPlannerAgent",
    "PlannerConfig",
]
