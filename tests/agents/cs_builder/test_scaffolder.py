"""Tests for AgentScaffolderAgent."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from autobot.agents.cs_builder.scaffolder import (
    AgentScaffolderAgent,
    ScaffolderConfig,
    ScaffoldPlan,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def example_spec() -> dict[str, object]:
    return {
        "name": "Contoso IT Helpdesk Agent",
        "description": "An enterprise IT helpdesk agent.",
        "publisher": {"displayName": "Contoso IT", "prefix": "contit"},
        "environments": {"source": "dev", "targets": ["test", "prod"]},
        "knowledgeSources": [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ],
        "actions": [
            {"name": "CreateTicket", "connector": "ServiceNow", "auth": "connectionReference",
             "inputs": {"table": "incident"}},
            {"name": "PostToTeams", "connector": "Teams", "auth": "connectionReference"},
        ],
        "channels": ["teams", "m365_copilot"],
        "security": {"dataLossPrevention": ["pii-block"], "allowExternal": False, "authenticationMode": "entra_id"},
        "alm": {
            "managedOutsideDev": True,
            "useEnvironmentVariables": True,
            "solutionVersion": "1.0.0.0",
            "pipelines": {"provider": "github", "templates": ["build.yml", "release.yml"]},
        },
        "telemetry": {"enable": True, "sampling": 0.25, "appInsightsConnectionString": "CONTOSO_APPINSIGHTS_CS"},
        "topics": [
            {"name": "PasswordReset", "triggerPhrases": ["reset password"], "description": "Password reset help"},
        ],
    }


@pytest.fixture
def spec_file(example_spec, tmp_path) -> Path:
    fp = tmp_path / "agent_spec.json"
    fp.write_text(json.dumps(example_spec))
    return fp


@pytest.fixture
def scaffolder(tmp_path) -> AgentScaffolderAgent:
    config = ScaffolderConfig(output_root=str(tmp_path / "solutions"))
    return AgentScaffolderAgent(config=config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScaffoldPlan:
    @pytest.mark.asyncio
    async def test_plan_produces_files(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        assert plan.success
        assert plan.agent_name == "Contoso IT Helpdesk Agent"
        assert len(plan.files) > 0

    @pytest.mark.asyncio
    async def test_plan_contains_solution_xml(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        assert "solution.xml" in paths

    @pytest.mark.asyncio
    async def test_plan_contains_bot_stub(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        bot_paths = [p for p in paths if "bot.json" in p]
        assert len(bot_paths) == 1

    @pytest.mark.asyncio
    async def test_plan_contains_env_vars(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        env_paths = [p for p in paths if "environmentvariabledefinition" in p]
        assert len(env_paths) > 0

    @pytest.mark.asyncio
    async def test_plan_contains_connection_refs(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        cr_paths = [p for p in paths if "connectionreferences" in p]
        assert len(cr_paths) >= 2  # ServiceNow + Teams

    @pytest.mark.asyncio
    async def test_plan_contains_pipeline_stubs(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        pipeline_paths = [p for p in paths if ".pipelines" in p]
        assert len(pipeline_paths) == 2  # build.yml + release.yml

    @pytest.mark.asyncio
    async def test_plan_to_json(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        j = json.loads(plan.to_json())
        assert j["dry_run"] is True
        assert j["total_files"] > 0

    @pytest.mark.asyncio
    async def test_plan_from_dict(self, scaffolder, example_spec):
        plan = await scaffolder.plan_from_dict(example_spec)
        assert plan.success


class TestScaffoldApply:
    @pytest.mark.asyncio
    async def test_apply_creates_files(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        result = await scaffolder.apply(plan)
        assert result["success"] is True
        assert result["total_files"] > 0
        # Verify files exist on disk
        for fp in result["files_created"]:
            assert Path(fp).exists()

    @pytest.mark.asyncio
    async def test_solution_xml_valid(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        result = await scaffolder.apply(plan)
        sol_files = [f for f in result["files_created"] if f.endswith("solution.xml")]
        assert len(sol_files) == 1
        content = Path(sol_files[0]).read_text()
        assert "contit" in content
        assert "Contoso IT" in content
        assert "contit_ContosoITHelpdeskAgent" in content

    @pytest.mark.asyncio
    async def test_bot_json_valid(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        result = await scaffolder.apply(plan)
        bot_files = [f for f in result["files_created"] if f.endswith("bot.json")]
        assert len(bot_files) == 1
        bot = json.loads(Path(bot_files[0]).read_text())
        assert bot["displayName"] == "Contoso IT Helpdesk Agent"
        assert len(bot["topics"]) == 1
        assert len(bot["knowledgeSources"]) == 1
        assert len(bot["actions"]) == 2


class TestScaffoldCardTemplates:
    @pytest.mark.asyncio
    async def test_plan_contains_welcome_card(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        welcome_paths = [p for p in paths if "welcome_card.json" in p]
        assert len(welcome_paths) == 1

    @pytest.mark.asyncio
    async def test_plan_contains_error_card(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        error_paths = [p for p in paths if "error_card.json" in p]
        assert len(error_paths) == 1

    @pytest.mark.asyncio
    async def test_plan_contains_per_topic_cards(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        paths = [f["path"] for f in plan.files]
        topic_paths = [p for p in paths if "PasswordReset_card.json" in p]
        assert len(topic_paths) == 1

    @pytest.mark.asyncio
    async def test_apply_creates_valid_card_files(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        result = await scaffolder.apply(plan)
        card_files = [f for f in result["files_created"] if f.endswith("_card.json")]
        assert len(card_files) >= 3  # welcome + error + 1 topic
        for fp in card_files:
            card = json.loads(Path(fp).read_text())
            assert card["type"] == "AdaptiveCard"

    @pytest.mark.asyncio
    async def test_bot_json_references_card_templates(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        result = await scaffolder.apply(plan)
        bot_files = [f for f in result["files_created"] if f.endswith("bot.json")]
        assert len(bot_files) == 1
        bot = json.loads(Path(bot_files[0]).read_text())
        assert "cardTemplates" in bot
        assert "welcome_card.json" in bot["cardTemplates"]
        assert "error_card.json" in bot["cardTemplates"]

    @pytest.mark.asyncio
    async def test_card_templates_count_matches_bot_refs(self, scaffolder, spec_file):
        plan = await scaffolder.plan(str(spec_file))
        result = await scaffolder.apply(plan)
        bot_files = [f for f in result["files_created"] if f.endswith("bot.json")]
        bot = json.loads(Path(bot_files[0]).read_text())
        card_files = [f for f in result["files_created"] if "_card.json" in f and "bot.json" not in f]
        assert len(card_files) == len(bot["cardTemplates"])


class TestScaffolderHelpers:
    def test_safe_name(self):
        assert AgentScaffolderAgent._safe_name("Contoso IT Helpdesk Agent") == "ContosoITHelpdeskAgent"
        assert AgentScaffolderAgent._safe_name("  spaces  ") == "spaces"
        assert AgentScaffolderAgent._safe_name("a-b_c!d") == "abcd"
        assert AgentScaffolderAgent._safe_name("") == "Agent"

    @pytest.mark.asyncio
    async def test_file_not_found(self, scaffolder):
        with pytest.raises(FileNotFoundError):
            await scaffolder.plan("/nonexistent/spec.json")
