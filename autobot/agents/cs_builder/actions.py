"""ActionsIntegratorAgent — maps spec actions to connectors, flows, and references.

For each action in the agent spec, this agent:
- Identifies the Power Platform connector
- Creates connection reference placeholders
- Generates environment variable definitions for URLs / config
- Emits Power Automate flow stubs or custom connector definitions
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from autobot.agents.cs_builder._base import CopilotAgentMixin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Well-known connector catalog (extensible)
# ---------------------------------------------------------------------------

CONNECTOR_CATALOG: dict[str, dict[str, Any]] = {
    "ServiceNow": {
        "connector_id": "/providers/Microsoft.PowerApps/apis/shared_service-now",
        "auth_types": ["connectionReference"],
        "requires_flow": False,
    },
    "Teams": {
        "connector_id": "/providers/Microsoft.PowerApps/apis/shared_teams",
        "auth_types": ["connectionReference"],
        "requires_flow": False,
    },
    "Office365Users": {
        "connector_id": "/providers/Microsoft.PowerApps/apis/shared_office365users",
        "auth_types": ["connectionReference"],
        "requires_flow": False,
    },
    "HTTP": {
        "connector_id": "/providers/Microsoft.PowerApps/apis/shared_http",
        "auth_types": ["connectionReference", "apiKey"],
        "requires_flow": True,
    },
    "SQL": {
        "connector_id": "/providers/Microsoft.PowerApps/apis/shared_sql",
        "auth_types": ["connectionReference"],
        "requires_flow": True,
    },
    "SharePoint": {
        "connector_id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
        "auth_types": ["connectionReference"],
        "requires_flow": False,
    },
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ActionsConfig(BaseModel):
    """Configuration for ActionsIntegratorAgent."""

    name: str = Field(default="actions_integrator", description="Agent name")
    copilot_config: dict[str, Any] = Field(
        default_factory=lambda: {"model": "gpt-5", "temperature": 0.2},
        description="Copilot SDK backend configuration",
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ActionsIntegratorAgent(CopilotAgentMixin):
    """Maps agent_spec actions to Power Platform connectors and flows.

    Uses Copilot SDK LLM for intelligent connector suggestions when
    available, falling back to catalog-based mapping otherwise.

    Args:
        copilot_config: Copilot SDK backend configuration.
        config: Full agent configuration.

    Example::

        integrator = ActionsIntegratorAgent()
        plan = await integrator.plan(spec)
        result = await integrator.apply(plan)
    """

    def __init__(
        self,
        copilot_config: dict[str, Any] | None = None,
        config: ActionsConfig | None = None,
    ):
        self._config = config or ActionsConfig(
            **({"copilot_config": copilot_config} if copilot_config else {}),
        )
        self._copilot_config = self._config.copilot_config
        self.name = self._config.name
        self._is_running = False
        self._reasoning_trace: list[dict[str, Any]] = []

    async def start(self) -> None:
        self._is_running = True
        await self._start_llm()

    async def stop(self) -> None:
        await self._stop_llm()
        self._is_running = False

    async def plan(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Dry-run: plan action integration.

        Args:
            spec: Parsed agent_spec dict.

        Returns:
            Structured plan with connector mappings, connection references,
            environment variables, and flow stubs.
        """
        prefix = spec.get("publisher", {}).get("prefix", "new")
        actions = spec.get("actions", [])
        action_plans: list[dict[str, Any]] = []
        connection_refs: list[dict[str, Any]] = []
        env_vars: list[dict[str, Any]] = []
        flow_stubs: list[dict[str, Any]] = []
        warnings: list[str] = []
        seen_connectors: set[str] = set()

        for action in actions:
            connector = action.get("connector", "")
            catalog_entry = CONNECTOR_CATALOG.get(connector)
            cr_name = f"{prefix}_{connector}_cr"

            plan_entry: dict[str, Any] = {
                "name": action["name"],
                "connector": connector,
                "auth": action.get("auth", "connectionReference"),
                "known_connector": catalog_entry is not None,
                "connection_reference": cr_name,
            }

            if catalog_entry:
                plan_entry["connector_id"] = catalog_entry["connector_id"]
                plan_entry["requires_flow"] = catalog_entry["requires_flow"]
            else:
                warnings.append(
                    f"Connector '{connector}' not in catalog. "
                    "A custom connector definition may be needed."
                )
                plan_entry["connector_id"] = f"/providers/Microsoft.PowerApps/apis/shared_{connector.lower()}"
                plan_entry["requires_flow"] = False

            # Connection reference (deduplicate by connector)
            if connector not in seen_connectors:
                seen_connectors.add(connector)
                connection_refs.append({
                    "schema_name": cr_name,
                    "connector": connector,
                    "connector_id": plan_entry["connector_id"],
                })

            # Environment variable for base URL if inputs present
            if action.get("inputs"):
                ev_name = f"{prefix}_{action['name']}_BaseUrl"
                env_vars.append({
                    "schema_name": ev_name,
                    "display_name": f"{action['name']} Base URL",
                    "type": "String",
                })

            # Flow stub if connector requires it
            if plan_entry.get("requires_flow"):
                flow_stubs.append({
                    "name": f"{prefix}_{action['name']}_flow",
                    "trigger": "automated",
                    "connector": connector,
                    "action_name": action["name"],
                })

            # Auth validation
            if action.get("auth") != "connectionReference":
                warnings.append(
                    f"Action '{action['name']}' uses '{action.get('auth')}' auth. "
                    "connectionReference is recommended for ALM."
                )

            action_plans.append(plan_entry)

        return {
            "action": "integrate_actions",
            "dry_run": True,
            "success": True,
            "total_actions": len(actions),
            "action_plans": action_plans,
            "connection_references": connection_refs,
            "environment_variables": env_vars,
            "flow_stubs": flow_stubs,
            "warnings": warnings,
        }

    async def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute action integration — generates artifacts on disk.

        Currently produces JSON stubs for connection references, env vars,
        and flow definitions.  A production implementation would call
        PAC CLI or Copilot Studio API.
        """
        start = time.perf_counter()
        artifacts: list[dict[str, Any]] = []

        for cr in plan.get("connection_references", []):
            artifacts.append({
                "type": "connection_reference",
                "name": cr["schema_name"],
                "status": "stub_generated",
            })

        for ev in plan.get("environment_variables", []):
            artifacts.append({
                "type": "environment_variable",
                "name": ev["schema_name"],
                "status": "stub_generated",
            })

        for flow in plan.get("flow_stubs", []):
            artifacts.append({
                "type": "flow_definition",
                "name": flow["name"],
                "status": "stub_generated",
            })

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "integrate_actions",
            "dry_run": False,
            "success": True,
            "artifacts": artifacts,
            "total_artifacts": len(artifacts),
            "duration_ms": round(elapsed, 2),
        }

    # -- LLM-powered connector suggestions -----------------------------------

    async def suggest_connectors(self, requirements: str) -> list[dict[str, Any]]:
        """Analyze requirements text and suggest connector mappings.

        When the LLM is available, uses natural language understanding to
        identify integrations mentioned in the requirements and map them to
        Power Platform connectors with appropriate configuration. Falls back
        to an empty list when the LLM is unavailable.

        Args:
            requirements: Free-form text describing the agent's requirements.

        Returns:
            List of suggested connector mapping dicts.
        """
        if not self.llm_available:
            logger.info("[%s] LLM unavailable, returning empty suggestions", self.name)
            return []

        system_message = (
            "You are a senior Power Platform integration architect specializing in "
            "connector configuration for Copilot Studio agents.\n\n"
            "Analyze the provided requirements text and identify all external systems "
            "or services that need to be integrated. For each integration:\n"
            "1. Map it to the correct Power Platform connector (standard or premium)\n"
            "2. Determine the authentication type (connectionReference, apiKey, OAuth2)\n"
            "3. Identify whether a Power Automate flow is needed as middleware\n"
            "4. List required actions/operations on the connector\n"
            "5. Recommend connection reference naming and sharing strategy\n"
            "6. Flag any licensing implications (premium connectors, per-flow plans)\n\n"
            "Return a JSON array where each entry has:\n"
            "[\n"
            "  {\n"
            '    "connector": "ConnectorName",\n'
            '    "connector_id": "/providers/Microsoft.PowerApps/apis/shared_...",\n'
            '    "auth_type": "connectionReference|apiKey|OAuth2",\n'
            '    "requires_flow": true|false,\n'
            '    "operations": ["operation1", "operation2"],\n'
            '    "description": "what this connector is used for",\n'
            '    "is_premium": true|false,\n'
            '    "notes": "licensing or configuration notes"\n'
            "  }\n"
            "]\n\n"
            "Return ONLY a valid JSON array."
        )

        user_message = f"Analyze these requirements for connector needs:\n\n{requirements}"

        try:
            raw = await self._llm_complete(
                system_message=system_message,
                user_message=user_message,
                temperature=0.2,
                expect_json=True,
            )
            result = json.loads(raw)
            if isinstance(result, list):
                return result
            return result.get("connectors", [])
        except (json.JSONDecodeError, RuntimeError) as exc:
            logger.debug("[%s] suggest_connectors LLM call failed (%s), returning empty", self.name, exc)
            return []

    def __repr__(self) -> str:
        return f"ActionsIntegratorAgent(name={self.name!r}, llm={'yes' if self.llm_available else 'no'})"


__all__ = [
    "ActionsIntegratorAgent",
    "ActionsConfig",
    "CONNECTOR_CATALOG",
]
