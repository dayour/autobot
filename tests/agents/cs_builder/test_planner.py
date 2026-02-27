"""Tests for RequirementsPlannerAgent."""

from __future__ import annotations

import pytest

from autobot.agents.cs_builder.planner import RequirementsPlannerAgent


@pytest.fixture
def planner() -> RequirementsPlannerAgent:
    return RequirementsPlannerAgent()


class TestRequirementsPlanner:
    @pytest.mark.asyncio
    async def test_generate_spec_returns_valid_structure(self, planner):
        spec = await planner.generate_spec("Build an IT helpdesk agent")
        assert "name" in spec
        assert "publisher" in spec
        assert "environments" in spec
        assert "channels" in spec

    @pytest.mark.asyncio
    async def test_spec_detects_sharepoint(self, planner):
        spec = await planner.generate_spec("Use SharePoint wiki as knowledge base")
        sp_sources = [ks for ks in spec["knowledgeSources"] if ks["type"] == "sharepoint"]
        assert len(sp_sources) == 1

    @pytest.mark.asyncio
    async def test_spec_detects_servicenow(self, planner):
        spec = await planner.generate_spec("Create ServiceNow tickets for issues")
        sn_actions = [a for a in spec["actions"] if a["connector"] == "ServiceNow"]
        assert len(sn_actions) == 1

    @pytest.mark.asyncio
    async def test_spec_detects_m365_copilot(self, planner):
        spec = await planner.generate_spec("Deploy to M365 Copilot")
        assert "m365_copilot" in spec["channels"]

    @pytest.mark.asyncio
    async def test_validate_spec_good(self, planner):
        spec = await planner.generate_spec("Simple agent")
        result = await planner.validate_spec(spec)
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_spec_missing_fields(self, planner):
        result = await planner.validate_spec({})
        assert result["valid"] is False
        assert len(result["errors"]) >= 4  # name, publisher, environments, channels

    @pytest.mark.asyncio
    async def test_defaults_are_enterprise_safe(self, planner):
        spec = await planner.generate_spec("Any agent")
        assert spec["alm"]["managedOutsideDev"] is True
        assert spec["alm"]["useEnvironmentVariables"] is True
        assert spec["security"]["allowExternal"] is False
