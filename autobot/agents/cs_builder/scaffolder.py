"""AgentScaffolderAgent — generates a Power Platform solution skeleton.

Reads an ``agent_spec.json`` and emits a ready-to-import solution folder
at ``solutions/<agentName>/`` containing:

- solution.xml (metadata, publisher, version)
- Customizations.xml stub
- Environment variable definitions
- Connection reference placeholders
- Copilot Studio agent artifact stub
- Optional ALM pipeline templates (GitHub Actions / Azure DevOps)

Supports ``--dry-run`` (plan) and ``--apply`` (materialize) modes.
"""

from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from autobot.agents.cs_builder._base import CopilotAgentMixin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ScaffolderConfig(BaseModel):
    """Configuration for AgentScaffolderAgent."""

    name: str = Field(default="agent_scaffolder", description="Agent name")
    copilot_config: dict[str, Any] = Field(
        default_factory=lambda: {"model": "gpt-5", "temperature": 0.2},
        description="Copilot SDK backend configuration",
    )
    output_root: str = Field(
        default="solutions",
        description="Root directory for generated solutions.",
    )


# ---------------------------------------------------------------------------
# Plan data structure
# ---------------------------------------------------------------------------

class ScaffoldPlan:
    """A plan describing every file that will be created or modified."""

    def __init__(self, agent_name: str, output_dir: str):
        self.agent_name = agent_name
        self.output_dir = output_dir
        self.files: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def add_file(self, relative_path: str, content: str, *, description: str = "") -> None:
        self.files.append({
            "path": relative_path,
            "size_bytes": len(content.encode("utf-8")),
            "description": description,
            "_content": content,
        })

    @property
    def success(self) -> bool:
        return len(self.files) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": "scaffold_solution",
            "dry_run": True,
            "agent_name": self.agent_name,
            "output_dir": self.output_dir,
            "timestamp": self.timestamp,
            "total_files": len(self.files),
            "files": [
                {k: v for k, v in f.items() if k != "_content"}
                for f in self.files
            ],
            "warnings": self.warnings,
            "success": self.success,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentScaffolderAgent(CopilotAgentMixin):
    """Generates a Power Platform solution skeleton from an agent spec.

    Uses Copilot SDK LLM for intelligent scaffolding suggestions when
    available, falling back to structural generation otherwise.

    Args:
        copilot_config: Copilot SDK backend configuration.
        config: Full scaffolder configuration.

    Example::

        scaff = AgentScaffolderAgent(copilot_config={"model":"gpt-5","temperature":0.2})
        plan = await scaff.plan("specs/agent_spec.example.json")  # preview
        await scaff.apply(plan)                                    # materialize
    """

    def __init__(
        self,
        copilot_config: dict[str, Any] | None = None,
        config: ScaffolderConfig | None = None,
    ):
        self._config = config or ScaffolderConfig(
            **({"copilot_config": copilot_config} if copilot_config else {}),
        )
        self._copilot_config = self._config.copilot_config
        self.name = self._config.name
        self._is_running = False
        self._reasoning_trace: list[dict[str, Any]] = []

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._is_running = True
        await self._start_llm()

    async def stop(self) -> None:
        await self._stop_llm()
        self._is_running = False

    # -- public API ----------------------------------------------------------

    async def plan(self, spec_path: str) -> ScaffoldPlan:
        """Generate a scaffold plan (dry-run).

        Args:
            spec_path: Path to agent_spec.json.

        Returns:
            ScaffoldPlan listing every file that would be created.
        """
        spec = self._load_spec(spec_path)
        return self._build_plan(spec)

    async def plan_from_dict(self, spec: dict[str, Any]) -> ScaffoldPlan:
        """Generate a scaffold plan from an in-memory spec dict."""
        return self._build_plan(spec)

    async def apply(self, plan: ScaffoldPlan) -> dict[str, Any]:
        """Materialize a plan to disk.

        Args:
            plan: A previously generated ScaffoldPlan.

        Returns:
            Structured result with created file paths and timing.
        """
        start = time.perf_counter()
        output = Path(plan.output_dir)
        created: list[str] = []

        for entry in plan.files:
            fp = output / entry["path"]
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(entry["_content"], encoding="utf-8")
            created.append(str(fp))

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "scaffold_solution",
            "dry_run": False,
            "success": True,
            "output_dir": str(output),
            "files_created": created,
            "total_files": len(created),
            "duration_ms": round(elapsed, 2),
        }

    # -- plan builder --------------------------------------------------------

    def _build_plan(self, spec: dict[str, Any]) -> ScaffoldPlan:
        """Build a complete scaffold plan from a parsed spec."""
        agent_name = spec.get("name", "UnnamedAgent")
        safe_name = self._safe_name(agent_name)
        prefix = spec.get("publisher", {}).get("prefix", "new")
        publisher_name = spec.get("publisher", {}).get("displayName", "Default Publisher")
        version = spec.get("alm", {}).get("solutionVersion", "1.0.0.0")
        unique_name = f"{prefix}_{safe_name}"

        output_dir = str(Path(self._config.output_root) / safe_name)
        plan = ScaffoldPlan(agent_name, output_dir)

        # 1. solution.xml
        plan.add_file(
            "solution.xml",
            self._gen_solution_xml(unique_name, agent_name, prefix, publisher_name, version),
            description="Solution metadata (publisher, version, layer info)",
        )

        # 2. Customizations.xml stub
        plan.add_file(
            "Customizations.xml",
            self._gen_customizations_xml(unique_name),
            description="Customizations container for solution components",
        )

        # 3. [Content_Types].xml
        plan.add_file(
            "[Content_Types].xml",
            self._gen_content_types(),
            description="Content types for solution package",
        )

        # 4. Environment variable definitions
        env_vars = self._collect_env_vars(spec)
        for ev in env_vars:
            plan.add_file(
                f"environmentvariabledefinitions/{ev['schema_name']}/environmentvariabledefinition.xml",
                self._gen_env_var_xml(ev),
                description=f"Environment variable: {ev['display_name']}",
            )

        # 5. Connection reference placeholders
        conn_refs = self._collect_connection_refs(spec)
        for cr in conn_refs:
            plan.add_file(
                f"connectionreferences/{cr['schema_name']}.json",
                json.dumps(cr, indent=2),
                description=f"Connection reference: {cr['connector']}",
            )

        # 6. Copilot Studio agent artifact stub
        plan.add_file(
            f"botcomponents/{prefix}_{safe_name}_bot/bot.json",
            self._gen_bot_stub(spec, prefix, safe_name),
            description="Copilot Studio agent artifact stub",
        )

        # 7. Adaptive Card templates
        card_dir = f"botcomponents/{prefix}_{safe_name}_cards"
        card_files = self._gen_card_templates(spec, prefix, safe_name, card_dir)
        for rel_path, content, desc in card_files:
            plan.add_file(rel_path, content, description=desc)

        # 8. ALM pipeline stubs
        pipelines = spec.get("alm", {}).get("pipelines", {})
        if pipelines:
            provider = pipelines.get("provider", "github")
            templates = pipelines.get("templates", [])
            for tmpl in templates:
                content = self._gen_pipeline_stub(provider, tmpl, unique_name, spec)
                plan.add_file(
                    f".pipelines/{tmpl}",
                    content,
                    description=f"ALM pipeline: {provider}/{tmpl}",
                )

        return plan

    # -- generators ----------------------------------------------------------

    @staticmethod
    def _gen_solution_xml(
        unique_name: str,
        display_name: str,
        prefix: str,
        publisher_name: str,
        version: str,
    ) -> str:
        root = ET.Element("ImportExportXml")
        root.set("version", "9.2")

        sol = ET.SubElement(root, "SolutionManifest")
        ET.SubElement(sol, "UniqueName").text = unique_name
        names = ET.SubElement(sol, "LocalizedNames")
        name_el = ET.SubElement(names, "LocalizedName")
        name_el.set("description", display_name)
        name_el.set("languagecode", "1033")

        ver = ET.SubElement(sol, "Version")
        ver.text = version

        managed = ET.SubElement(sol, "Managed")
        managed.text = "0"

        pub = ET.SubElement(sol, "Publisher")
        ET.SubElement(pub, "UniqueName").text = f"{prefix}_publisher"
        pub_names = ET.SubElement(pub, "LocalizedNames")
        pub_name = ET.SubElement(pub_names, "LocalizedName")
        pub_name.set("description", publisher_name)
        pub_name.set("languagecode", "1033")
        ET.SubElement(pub, "CustomizationPrefix").text = prefix

        ET.SubElement(sol, "RootComponents")
        ET.SubElement(sol, "MissingDependencies")

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _gen_customizations_xml(unique_name: str) -> str:
        root = ET.Element("ImportExportXml")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        entities = ET.SubElement(root, "Entities")
        ET.SubElement(root, "Roles")
        ET.SubElement(root, "Workflows")
        ET.SubElement(root, "FieldSecurityProfiles")
        ET.SubElement(root, "Templates")
        ET.SubElement(root, "EntityMaps")
        languages = ET.SubElement(root, "Languages")
        lang = ET.SubElement(languages, "Language")
        lang.text = "1033"
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _gen_content_types() -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="xml" ContentType="application/xml" />\n'
            '  <Default Extension="json" ContentType="application/json" />\n'
            '</Types>'
        )

    @staticmethod
    def _gen_env_var_xml(ev: dict[str, Any]) -> str:
        root = ET.Element("environmentvariabledefinition")
        ET.SubElement(root, "schemaname").text = ev["schema_name"]
        ET.SubElement(root, "displayname").text = ev["display_name"]
        ET.SubElement(root, "type").text = str(ev.get("type_code", 100000000))
        ET.SubElement(root, "defaultvalue").text = ev.get("default_value", "")
        ET.SubElement(root, "description").text = ev.get("description", "")
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _gen_bot_stub(spec: dict[str, Any], prefix: str, safe_name: str) -> str:
        bot: dict[str, Any] = {
            "schemaName": f"{prefix}_{safe_name}_bot",
            "displayName": spec.get("name", safe_name),
            "description": spec.get("description", ""),
            "language": "en-us",
            "authenticationMode": spec.get("security", {}).get("authenticationMode", "entra_id"),
            "channels": spec.get("channels", []),
            "topics": [],
            "knowledgeSources": [],
            "actions": [],
        }

        for topic in spec.get("topics", []):
            bot["topics"].append({
                "name": topic["name"],
                "triggerPhrases": topic.get("triggerPhrases", []),
                "description": topic.get("description", ""),
            })

        for ks in spec.get("knowledgeSources", []):
            bot["knowledgeSources"].append({
                "type": ks["type"],
                "reference": ks.get("url") or ks.get("path") or ks.get("table", ""),
                "scope": ks.get("scope"),
            })

        for action in spec.get("actions", []):
            bot["actions"].append({
                "name": action["name"],
                "connector": action["connector"],
                "connectionReference": f"{prefix}_{action['connector']}_cr",
            })

        # Card template references
        card_refs = ["welcome_card.json", "error_card.json"]
        for topic in spec.get("topics", []):
            card_refs.append(f"{topic['name']}_card.json")
        bot["cardTemplates"] = card_refs

        return json.dumps(bot, indent=2)

    @staticmethod
    def _gen_pipeline_stub(
        provider: str,
        template: str,
        solution_name: str,
        spec: dict[str, Any],
    ) -> str:
        targets = spec.get("environments", {}).get("targets", ["test", "prod"])

        if provider == "github":
            if "build" in template.lower():
                return _GITHUB_BUILD_YML.format(solution_name=solution_name)
            if "release" in template.lower():
                envs = "\n".join(f"          - {t}" for t in targets)
                return _GITHUB_RELEASE_YML.format(
                    solution_name=solution_name,
                    environments=envs,
                )
        elif provider == "azure_devops":
            return (
                f"# Azure DevOps pipeline stub for {solution_name}\n"
                f"# Template: {template}\n"
                f"# TODO: Implement using Power Platform Build Tools\n"
                f"trigger:\n  - main\n\npool:\n  vmImage: 'windows-latest'\n\n"
                f"steps:\n"
                f"  - task: PowerPlatformToolInstaller@2\n"
                f"  - task: PowerPlatformExportSolution@2\n"
                f"    inputs:\n"
                f"      SolutionName: '{solution_name}'\n"
            )

        return f"# Pipeline stub: {provider}/{template} for {solution_name}\n"

    # -- card template generation --------------------------------------------

    @staticmethod
    def _gen_card_templates(
        spec: dict[str, Any],
        prefix: str,
        safe_name: str,
        card_dir: str,
    ) -> list[tuple[str, str, str]]:
        """Generate Adaptive Card template files for the solution.

        Returns:
            List of (relative_path, content_json, description) tuples.
        """
        from autobot.tools.adaptive_cards import AdaptiveCardTemplate

        files: list[tuple[str, str, str]] = []

        # Welcome card
        topics = spec.get("topics", [])
        welcome = AdaptiveCardTemplate.welcome_card(
            agent_name=spec.get("name", safe_name),
            description=spec.get("description", ""),
            topics=topics,
        )
        files.append((
            f"{card_dir}/welcome_card.json",
            json.dumps(welcome, indent=2),
            "Welcome card with topic buttons",
        ))

        # Error card
        error = AdaptiveCardTemplate.error_card(
            title="Something went wrong",
            message="An unexpected error occurred. Please try again.",
            details="",
            retry_action={"title": "Retry", "data": {"action": "retry"}},
        )
        files.append((
            f"{card_dir}/error_card.json",
            json.dumps(error, indent=2),
            "Error card template",
        ))

        # Per-topic cards
        for topic in topics:
            topic_name = topic.get("name", "topic")
            topic_card = (
                AdaptiveCardTemplate.welcome_card(
                    agent_name=topic_name,
                    description=topic.get("description", f"Help with {topic_name}"),
                    topics=[],
                )
            )
            files.append((
                f"{card_dir}/{topic_name}_card.json",
                json.dumps(topic_card, indent=2),
                f"Response template for topic: {topic_name}",
            ))

        return files

    # -- collection helpers --------------------------------------------------

    def _collect_env_vars(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect all environment variables needed from the spec."""
        prefix = spec.get("publisher", {}).get("prefix", "new")
        env_vars: list[dict[str, Any]] = []

        # Telemetry connection string
        telemetry = spec.get("telemetry", {})
        if telemetry.get("enable") and telemetry.get("appInsightsConnectionString"):
            env_vars.append({
                "schema_name": f"{prefix}_AppInsightsConnectionString",
                "display_name": "App Insights Connection String",
                "type_code": 100000000,  # String
                "default_value": "",
                "description": "Application Insights connection string for telemetry.",
            })

        # Action-specific env vars (e.g., API base URLs)
        for action in spec.get("actions", []):
            if action.get("inputs"):
                env_vars.append({
                    "schema_name": f"{prefix}_{action['name']}_BaseUrl",
                    "display_name": f"{action['name']} Base URL",
                    "type_code": 100000000,
                    "default_value": "",
                    "description": f"Base URL for the {action['connector']} connector used by {action['name']}.",
                })

        return env_vars

    def _collect_connection_refs(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect connection references needed from actions."""
        prefix = spec.get("publisher", {}).get("prefix", "new")
        seen: set[str] = set()
        refs: list[dict[str, Any]] = []

        for action in spec.get("actions", []):
            connector = action.get("connector", "")
            if connector in seen:
                continue
            seen.add(connector)
            refs.append({
                "schema_name": f"{prefix}_{connector}_cr",
                "connector": connector,
                "connectorId": f"/providers/Microsoft.PowerApps/apis/shared_{connector.lower()}",
                "displayName": f"{connector} Connection",
                "description": f"Connection reference for {connector} connector.",
            })

        return refs

    # -- LLM-powered suggestions --------------------------------------------

    async def suggest_improvements(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Analyze a spec and suggest scaffolding improvements using the LLM.

        When the LLM is available, reviews the spec to identify missing
        solution components, recommend additional environment variables,
        suggest pipeline optimizations, and flag potential structural issues.
        Falls back to an empty suggestions dict when the LLM is unavailable.

        Args:
            spec: Parsed agent_spec dict.

        Returns:
            Dict with improvement suggestions organized by category.
        """
        if not self.llm_available:
            logger.info("[%s] LLM unavailable, returning empty suggestions", self.name)
            return {"suggestions": [], "additional_components": [], "pipeline_improvements": []}

        system_message = (
            "You are a senior Power Platform solution architect specializing in "
            "Copilot Studio solution packaging and ALM.\n\n"
            "Analyze the provided agent specification and suggest improvements to the "
            "solution scaffold. Focus on:\n"
            "1. Missing solution components (security roles, sitemap entries, web resources)\n"
            "2. Additional environment variables needed for production readiness\n"
            "3. Connection reference optimizations (shared vs. dedicated)\n"
            "4. Pipeline improvements (caching, parallel jobs, environment approvals)\n"
            "5. Solution layering recommendations (base vs. extension solutions)\n"
            "6. Localization needs based on configured channels and audiences\n"
            "7. Bot component structure improvements (topic organization, fallback handling)\n\n"
            "Return a JSON object with:\n"
            "{\n"
            '  "suggestions": [\n'
            '    {"category": "component|env_var|pipeline|structure|localization", '
            '"description": "...", "priority": "high|medium|low"}\n'
            "  ],\n"
            '  "additional_components": [\n'
            '    {"type": "security_role|sitemap|web_resource|...", "name": "...", "reason": "..."}\n'
            "  ],\n"
            '  "pipeline_improvements": [\n'
            '    {"improvement": "...", "benefit": "..."}\n'
            "  ]\n"
            "}\n\n"
            "Return ONLY valid JSON."
        )

        user_message = f"Analyze this agent specification for scaffolding improvements:\n\n{json.dumps(spec, indent=2)}"

        try:
            raw = await self._llm_complete(
                system_message=system_message,
                user_message=user_message,
                temperature=0.2,
                expect_json=True,
            )
            return json.loads(raw)
        except (json.JSONDecodeError, RuntimeError) as exc:
            logger.debug("[%s] suggest_improvements LLM call failed (%s), returning empty", self.name, exc)
            return {"suggestions": [], "additional_components": [], "pipeline_improvements": []}

    # -- utilities -----------------------------------------------------------

    @staticmethod
    def _safe_name(name: str) -> str:
        """Convert a display name to a safe identifier."""
        safe = re.sub(r"[^A-Za-z0-9]+", "", name.replace(" ", ""))
        return safe or "Agent"

    @staticmethod
    def _load_spec(path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            msg = f"Spec file not found: {path}"
            raise FileNotFoundError(msg)
        return json.loads(p.read_text(encoding="utf-8"))

    def __repr__(self) -> str:
        return f"AgentScaffolderAgent(name={self.name!r}, llm={'yes' if self.llm_available else 'no'})"


# ---------------------------------------------------------------------------
# Pipeline templates
# ---------------------------------------------------------------------------

_GITHUB_BUILD_YML = """# GitHub Actions: Build & Export Solution
# Auto-generated by autobot CS Builder Swarm
name: Build {solution_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Power Platform CLI
        uses: microsoft/powerplatform-actions/install-pac@v1

      - name: Authenticate
        uses: microsoft/powerplatform-actions/who-am-i@v1
        with:
          environment-url: ${{{{ secrets.DEV_ENVIRONMENT_URL }}}}
          app-id: ${{{{ secrets.CLIENT_ID }}}}
          client-secret: ${{{{ secrets.CLIENT_SECRET }}}}
          tenant-id: ${{{{ secrets.TENANT_ID }}}}

      - name: Export Unmanaged Solution
        uses: microsoft/powerplatform-actions/export-solution@v1
        with:
          solution-name: {solution_name}
          solution-output-file: dist/{solution_name}_unmanaged.zip

      - name: Export Managed Solution
        uses: microsoft/powerplatform-actions/export-solution@v1
        with:
          solution-name: {solution_name}
          solution-output-file: dist/{solution_name}_managed.zip
          managed: true

      - name: Upload Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: solution-artifacts
          path: dist/
"""

_GITHUB_RELEASE_YML = """# GitHub Actions: Release to Target Environments
# Auto-generated by autobot CS Builder Swarm
name: Release {solution_name}

on:
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        required: true
        type: choice
        options:
{environments}

permissions:
  contents: read

jobs:
  deploy:
    runs-on: windows-latest
    environment: ${{{{ github.event.inputs.environment }}}}
    steps:
      - uses: actions/checkout@v4

      - name: Install Power Platform CLI
        uses: microsoft/powerplatform-actions/install-pac@v1

      - name: Download Solution Artifact
        uses: actions/download-artifact@v4
        with:
          name: solution-artifacts
          path: dist/

      - name: Import Managed Solution
        uses: microsoft/powerplatform-actions/import-solution@v1
        with:
          environment-url: ${{{{ secrets[format('{{0}}_ENVIRONMENT_URL', github.event.inputs.environment)] }}}}
          app-id: ${{{{ secrets.CLIENT_ID }}}}
          client-secret: ${{{{ secrets.CLIENT_SECRET }}}}
          tenant-id: ${{{{ secrets.TENANT_ID }}}}
          solution-file: dist/{solution_name}_managed.zip
"""


__all__ = [
    "AgentScaffolderAgent",
    "ScaffolderConfig",
    "ScaffoldPlan",
]
