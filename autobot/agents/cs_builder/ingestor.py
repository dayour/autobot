"""KnowledgeSourceIngestorAgent — configures knowledge sources per spec.

Handles SharePoint URLs/folders, public web sites, uploaded files, and
Dataverse tables.  Generates configuration assets, validation checks
(reachability, auth scope mapping), and a verification plan describing
what will be indexed, estimated size, and required permissions.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from autobot.agents.cs_builder._base import CopilotAgentMixin
from autobot.tools.sharepoint_check import SharePointChecker, parse_sharepoint_url

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class IngestorConfig(BaseModel):
    """Configuration for KnowledgeSourceIngestorAgent."""

    name: str = Field(default="knowledge_ingestor", description="Agent name")
    copilot_config: dict[str, Any] = Field(
        default_factory=lambda: {"model": "gpt-5", "temperature": 0.1},
        description="Copilot SDK backend configuration",
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class KnowledgeSourceIngestorAgent(CopilotAgentMixin):
    """Configures and validates knowledge sources for a Copilot Studio agent.

    Uses Copilot SDK LLM for intelligent knowledge source suggestions
    when available, falling back to structural validation otherwise.

    Args:
        copilot_config: Copilot SDK backend configuration.
        config: Full ingestor configuration.

    Example::

        ingestor = KnowledgeSourceIngestorAgent()
        plan = await ingestor.plan(spec)
        result = await ingestor.apply(plan)
    """

    def __init__(
        self,
        copilot_config: dict[str, Any] | None = None,
        config: IngestorConfig | None = None,
    ):
        self._config = config or IngestorConfig(
            **({"copilot_config": copilot_config} if copilot_config else {}),
        )
        self._copilot_config = self._config.copilot_config
        self.name = self._config.name
        self._is_running = False
        self._reasoning_trace: list[dict[str, Any]] = []
        self._sp_checker = SharePointChecker()

    async def start(self) -> None:
        self._is_running = True
        await self._start_llm()

    async def stop(self) -> None:
        await self._stop_llm()
        self._is_running = False

    async def plan(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Dry-run: produce a verification plan for all knowledge sources.

        Args:
            spec: Parsed agent_spec dict.

        Returns:
            Structured plan with per-source validation details.
        """
        sources = spec.get("knowledgeSources", [])
        source_plans: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []

        for src in sources:
            src_type = src.get("type", "unknown")
            entry: dict[str, Any] = {
                "type": src_type,
                "reference": src.get("url") or src.get("path") or src.get("table", ""),
                "description": src.get("description", ""),
            }

            if src_type == "sharepoint":
                parsed = parse_sharepoint_url(src.get("url", ""))
                entry["parsed_url"] = parsed
                entry["scope"] = src.get("scope", "site")
                entry["scopes_required"] = SharePointChecker.SCOPE_MAP.get(
                    src.get("scope", "site"), ["Sites.Read.All"]
                )
                if not parsed["is_valid"]:
                    errors.append(f"Invalid SharePoint URL: {src.get('url', '')}")
                    entry["valid"] = False
                else:
                    entry["valid"] = True

            elif src_type == "web":
                url = src.get("url", "")
                depth = src.get("depth", 2)
                entry["depth"] = depth
                entry["estimated_pages"] = depth * 10  # rough estimate
                entry["valid"] = bool(url.startswith("http"))
                if not entry["valid"]:
                    errors.append(f"Invalid web URL: {url}")

            elif src_type == "file":
                file_path = src.get("path", "")
                entry["glob_pattern"] = file_path
                # Check if local files exist
                p = Path(file_path)
                if p.is_absolute() and not p.parent.exists():
                    warnings.append(f"Directory not found for file source: {file_path}")
                entry["valid"] = bool(file_path)

            elif src_type == "dataverse":
                table = src.get("table", "")
                entry["table"] = table
                entry["valid"] = bool(table)
                entry["scopes_required"] = ["user_impersonation"]
                if not table:
                    errors.append("Dataverse source missing table name.")

            else:
                errors.append(f"Unknown knowledge source type: {src_type}")
                entry["valid"] = False

            source_plans.append(entry)

        return {
            "action": "ingest_knowledge_sources",
            "dry_run": True,
            "success": len(errors) == 0,
            "total_sources": len(sources),
            "source_plans": source_plans,
            "warnings": warnings,
            "errors": errors,
        }

    async def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute knowledge source configuration.

        Currently generates configuration assets and runs structural
        validation.  A production implementation would call the
        Copilot Studio API to register knowledge sources.
        """
        start = time.perf_counter()
        results: list[dict[str, Any]] = []

        for src_plan in plan.get("source_plans", []):
            result: dict[str, Any] = {
                "type": src_plan["type"],
                "reference": src_plan["reference"],
                "status": "configured" if src_plan.get("valid") else "failed",
            }

            if src_plan["type"] == "sharepoint" and src_plan.get("valid"):
                # Run SharePoint validation
                sp_plan = await self._sp_checker.plan_validate(
                    [{"type": "sharepoint", "url": src_plan["reference"], "scope": src_plan.get("scope", "site")}]
                )
                sp_result = await self._sp_checker.apply_validate(sp_plan)
                result["sharepoint_validation"] = sp_result

            results.append(result)

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "ingest_knowledge_sources",
            "dry_run": False,
            "success": all(r["status"] == "configured" for r in results),
            "results": results,
            "duration_ms": round(elapsed, 2),
        }

    # -- Adaptive Card output -------------------------------------------------

    @staticmethod
    def plan_to_adaptive_card(plan: dict[str, Any]) -> dict[str, Any]:
        """Render an ingestion plan as a knowledge source status card.

        Args:
            plan: Plan dict from :meth:`plan`.

        Returns:
            Adaptive Card dict showing per-source status.
        """
        from autobot.tools.adaptive_cards import AdaptiveCardTemplate

        return AdaptiveCardTemplate.knowledge_source_status_card(plan.get("source_plans", []))

    # -- LLM-powered knowledge source suggestions ----------------------------

    async def suggest_knowledge_sources(self, requirements: str) -> list[dict[str, Any]]:
        """Analyze requirements text and suggest knowledge source configurations.

        When the LLM is available, uses natural language understanding to
        identify data sources mentioned in the requirements and map them to
        Copilot Studio knowledge source types (sharepoint, web, file,
        dataverse). Falls back to an empty list when the LLM is unavailable.

        Args:
            requirements: Free-form text describing the agent's requirements.

        Returns:
            List of suggested knowledge source configuration dicts.
        """
        if not self.llm_available:
            logger.info("[%s] LLM unavailable, returning empty suggestions", self.name)
            return []

        system_message = (
            "You are a Microsoft Power Platform data architect specializing in "
            "Copilot Studio knowledge source configuration.\n\n"
            "Analyze the provided requirements text and identify all data sources "
            "that should be configured as knowledge sources. For each source:\n"
            "1. Determine the type: 'sharepoint', 'web', 'file', or 'dataverse'\n"
            "2. Extract or infer the URL, path, or table name\n"
            "3. Recommend the appropriate scope (site, library, folder, page)\n"
            "4. Estimate indexing complexity and size\n"
            "5. Identify required permissions and Graph API scopes\n"
            "6. Flag any potential access or compliance concerns\n\n"
            "Return a JSON array where each entry has:\n"
            "[\n"
            "  {\n"
            '    "type": "sharepoint|web|file|dataverse",\n'
            '    "reference": "URL, path, or table name",\n'
            '    "scope": "site|library|folder|page",\n'
            '    "description": "what this source provides",\n'
            '    "estimated_size": "small|medium|large",\n'
            '    "permissions": ["scope1", "scope2"],\n'
            '    "notes": "any concerns or recommendations"\n'
            "  }\n"
            "]\n\n"
            "Return ONLY a valid JSON array."
        )

        user_message = f"Analyze these requirements for knowledge source needs:\n\n{requirements}"

        try:
            raw = await self._llm_complete(
                system_message=system_message,
                user_message=user_message,
                temperature=0.1,
                expect_json=True,
            )
            result = json.loads(raw)
            if isinstance(result, list):
                return result
            return result.get("sources", [])
        except (json.JSONDecodeError, RuntimeError) as exc:
            logger.debug("[%s] suggest_knowledge_sources LLM call failed (%s), returning empty", self.name, exc)
            return []

    def __repr__(self) -> str:
        return f"KnowledgeSourceIngestorAgent(name={self.name!r}, llm={'yes' if self.llm_available else 'no'})"


__all__ = [
    "KnowledgeSourceIngestorAgent",
    "IngestorConfig",
]
