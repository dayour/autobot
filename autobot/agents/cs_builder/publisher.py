"""PublisherAgent — scripted publish steps for Teams and M365 Copilot channels.

**Never** performs destructive actions by default.  Supports ``--dry-run``
(plan) which produces a human-readable report of what would happen, and
``--apply`` which executes the steps when explicitly requested.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from autobot.agents.cs_builder._base import CopilotAgentMixin
from autobot.tools.teams_publish import TeamsPublisher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class PublisherConfig(BaseModel):
    """Configuration for PublisherAgent."""

    name: str = Field(default="publisher", description="Agent name")
    copilot_config: dict[str, Any] = Field(
        default_factory=lambda: {"model": "gpt-5", "temperature": 0.1},
        description="Copilot SDK backend configuration",
    )
    force_dry_run: bool = Field(
        default=True,
        description="If True, apply() still acts as dry-run. Set to False to enable real publish.",
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class PublisherAgent(CopilotAgentMixin):
    """Non-destructive publisher for Teams and M365 Copilot channels.

    Uses Copilot SDK LLM for intelligent publish readiness checklists
    when available, falling back to structural checks otherwise.

    Args:
        copilot_config: Copilot SDK backend configuration.
        config: Full publisher configuration.

    Example::

        pub = PublisherAgent()
        plan = await pub.plan_publish(spec)
        # Review plan...
        result = await pub.apply_publish(plan)
    """

    def __init__(
        self,
        copilot_config: dict[str, Any] | None = None,
        config: PublisherConfig | None = None,
    ):
        self._config = config or PublisherConfig(
            **({"copilot_config": copilot_config} if copilot_config else {}),
        )
        self._copilot_config = self._config.copilot_config
        self.name = self._config.name
        self._is_running = False
        self._reasoning_trace: list[dict[str, Any]] = []
        self._teams_pub = TeamsPublisher()

    async def start(self) -> None:
        self._is_running = True
        await self._start_llm()

    async def stop(self) -> None:
        await self._stop_llm()
        self._is_running = False

    async def plan_publish(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Produce a publish plan listing exactly what will happen.

        Args:
            spec: Parsed agent_spec dict.

        Returns:
            Structured plan with per-channel steps and approval requirements.
        """
        channels = spec.get("channels", [])
        agent_name = spec.get("name", "Unknown Agent")
        security = spec.get("security", {})

        plan = await self._teams_pub.plan_publish(
            channels,
            agent_name=agent_name,
            security=security,
        )

        # Add org approval notes
        plan["org_approval_notes"] = self._generate_approval_notes(spec)
        plan["agent_name"] = agent_name

        return plan

    async def apply_publish(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute publish steps (respects force_dry_run config).

        If ``force_dry_run`` is True (the default), this returns the plan
        annotated as a report rather than executing any actual changes.
        """
        if self._config.force_dry_run:
            return {
                "action": "publish_channels",
                "dry_run": True,
                "success": True,
                "message": (
                    "force_dry_run is enabled. Set config.force_dry_run=False "
                    "and call apply_publish() again to execute real publish steps."
                ),
                "plan": plan,
            }

        return await self._teams_pub.apply_publish(plan)

    def _generate_approval_notes(self, spec: dict[str, Any]) -> list[str]:
        """Generate organizational approval notes based on spec."""
        notes: list[str] = []
        channels = spec.get("channels", [])
        security = spec.get("security", {})

        if "teams" in channels:
            notes.append(
                "Teams: Requires Teams admin to approve the app in the "
                "Teams admin center before users can discover it."
            )

        if "m365_copilot" in channels:
            notes.append(
                "M365 Copilot: Requires admin approval in the M365 admin center "
                "under Copilot extensions. Submit the plugin for review."
            )

        if security.get("rbacRoles"):
            roles = ", ".join(security["rbacRoles"])
            notes.append(
                f"RBAC: Agent is restricted to these roles/groups: {roles}. "
                "Ensure these groups exist in Entra ID."
            )

        if not security.get("allowExternal", False):
            notes.append(
                "External access is disabled. Only authenticated internal "
                "users can interact with this agent."
            )

        return notes

    # -- Adaptive Card output -------------------------------------------------

    async def generate_approval_card(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Generate a publish approval Adaptive Card.

        Builds a checklist and delegates to the card template.

        Args:
            spec: Parsed agent_spec dict.

        Returns:
            Complete Adaptive Card dict for approval workflow.
        """
        from autobot.tools.adaptive_cards import AdaptiveCardTemplate

        checklist = await self.generate_publish_checklist(spec)
        return AdaptiveCardTemplate.publish_approval_card(
            agent_name=spec.get("name", "Unknown Agent"),
            channels=spec.get("channels", []),
            checklist=checklist,
        )

    # -- LLM-powered publish checklist ---------------------------------------

    async def generate_publish_checklist(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Produce a detailed publish readiness checklist using the LLM.

        When the LLM is available, analyzes the spec to generate a
        comprehensive checklist covering security review, admin approvals,
        testing gates, compliance requirements, and rollback planning.
        Falls back to a basic structural checklist when the LLM is unavailable.

        Args:
            spec: Parsed agent_spec dict.

        Returns:
            Dict with categorized checklist items and readiness assessment.
        """
        if not self.llm_available:
            logger.info("[%s] LLM unavailable, returning structural checklist", self.name)
            return self._structural_checklist(spec)

        system_message = (
            "You are a senior Microsoft 365 deployment architect specializing in "
            "Copilot Studio agent publishing and organizational rollout.\n\n"
            "Analyze the provided agent specification and produce a detailed publish "
            "readiness checklist. Cover these categories:\n"
            "1. **Security Review**: Authentication mode, DLP policies, external access, "
            "RBAC configuration, data residency compliance\n"
            "2. **Admin Approvals**: Teams admin center approval, M365 admin center "
            "review, Copilot extensions submission, security team sign-off\n"
            "3. **Testing Gates**: Functional test pass rate, adversarial test coverage, "
            "performance benchmarks, accessibility validation\n"
            "4. **Compliance**: Data classification labels, retention policies, audit "
            "logging configuration, GDPR/regional compliance\n"
            "5. **Rollback Plan**: Version pinning, unmanaged-to-managed migration, "
            "rollback triggers, communication plan\n"
            "6. **Post-Publish Monitoring**: Telemetry dashboards, error alerting, "
            "user feedback channels, SLA targets\n\n"
            "Return a JSON object with:\n"
            "{\n"
            '  "ready": true|false,\n'
            '  "blocking_items": ["item that must be resolved before publish"],\n'
            '  "checklist": [\n'
            "    {\n"
            '      "category": "security|approval|testing|compliance|rollback|monitoring",\n'
            '      "item": "checklist item description",\n'
            '      "status": "pending|passed|blocked",\n'
            '      "priority": "critical|high|medium|low",\n'
            '      "notes": "additional context"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Return ONLY valid JSON."
        )

        user_message = f"Generate a publish readiness checklist for this agent:\n\n{json.dumps(spec, indent=2)}"

        try:
            raw = await self._llm_complete(
                system_message=system_message,
                user_message=user_message,
                temperature=0.1,
                expect_json=True,
            )
            return json.loads(raw)
        except (json.JSONDecodeError, RuntimeError) as exc:
            logger.debug("[%s] generate_publish_checklist LLM call failed (%s), returning structural", self.name, exc)
            return self._structural_checklist(spec)

    @staticmethod
    def _structural_checklist(spec: dict[str, Any]) -> dict[str, Any]:
        """Build a basic structural publish checklist without LLM."""
        channels = spec.get("channels", [])
        security = spec.get("security", {})
        checklist: list[dict[str, Any]] = []
        blocking: list[str] = []

        # Security checks
        if not security.get("authenticationMode"):
            blocking.append("Authentication mode not configured")
        checklist.append({
            "category": "security",
            "item": "Authentication mode configured",
            "status": "passed" if security.get("authenticationMode") else "blocked",
            "priority": "critical",
            "notes": f"Mode: {security.get('authenticationMode', 'not set')}",
        })

        if not security.get("dataLossPrevention"):
            checklist.append({
                "category": "security",
                "item": "DLP policies configured",
                "status": "blocked",
                "priority": "high",
                "notes": "No DLP policies defined",
            })
            blocking.append("No DLP policies configured")
        else:
            checklist.append({
                "category": "security",
                "item": "DLP policies configured",
                "status": "passed",
                "priority": "high",
                "notes": f"Policies: {', '.join(security['dataLossPrevention'])}",
            })

        # Approval checks
        for channel in channels:
            if channel == "teams":
                checklist.append({
                    "category": "approval",
                    "item": "Teams admin center approval",
                    "status": "pending",
                    "priority": "critical",
                    "notes": "Requires Teams admin to approve in admin center",
                })
            elif channel == "m365_copilot":
                checklist.append({
                    "category": "approval",
                    "item": "M365 Copilot extensions review",
                    "status": "pending",
                    "priority": "critical",
                    "notes": "Submit for review in M365 admin center",
                })

        # Testing gate
        checklist.append({
            "category": "testing",
            "item": "Functional tests passed",
            "status": "pending",
            "priority": "high",
            "notes": "Run test suite before publishing",
        })

        return {
            "ready": len(blocking) == 0,
            "blocking_items": blocking,
            "checklist": checklist,
        }

    def __repr__(self) -> str:
        return f"PublisherAgent(name={self.name!r}, llm={'yes' if self.llm_available else 'no'})"


__all__ = [
    "PublisherAgent",
    "PublisherConfig",
]
