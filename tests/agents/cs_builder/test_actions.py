"""Tests for ActionsIntegratorAgent."""

from __future__ import annotations

import pytest

from autobot.agents.cs_builder.actions import ActionsIntegratorAgent, CONNECTOR_CATALOG


@pytest.fixture
def integrator() -> ActionsIntegratorAgent:
    return ActionsIntegratorAgent()


@pytest.fixture
def spec_with_actions() -> dict:
    return {
        "publisher": {"prefix": "contit"},
        "actions": [
            {"name": "CreateTicket", "connector": "ServiceNow", "auth": "connectionReference",
             "inputs": {"table": "incident"}},
            {"name": "PostToTeams", "connector": "Teams", "auth": "connectionReference"},
        ],
    }


class TestActionsIntegrator:
    @pytest.mark.asyncio
    async def test_plan_returns_all_actions(self, integrator, spec_with_actions):
        plan = await integrator.plan(spec_with_actions)
        assert plan["total_actions"] == 2
        assert len(plan["action_plans"]) == 2

    @pytest.mark.asyncio
    async def test_plan_creates_connection_refs(self, integrator, spec_with_actions):
        plan = await integrator.plan(spec_with_actions)
        assert len(plan["connection_references"]) == 2

    @pytest.mark.asyncio
    async def test_plan_creates_env_vars(self, integrator, spec_with_actions):
        plan = await integrator.plan(spec_with_actions)
        # Only CreateTicket has inputs
        assert len(plan["environment_variables"]) == 1

    @pytest.mark.asyncio
    async def test_unknown_connector_warns(self, integrator):
        spec = {
            "publisher": {"prefix": "tst"},
            "actions": [{"name": "Custom", "connector": "UnknownCRM", "auth": "connectionReference"}],
        }
        plan = await integrator.plan(spec)
        assert len(plan["warnings"]) >= 1
        assert "UnknownCRM" in plan["warnings"][0]

    @pytest.mark.asyncio
    async def test_non_cr_auth_warns(self, integrator):
        spec = {
            "publisher": {"prefix": "tst"},
            "actions": [{"name": "Risky", "connector": "HTTP", "auth": "apiKey"}],
        }
        plan = await integrator.plan(spec)
        assert any("apiKey" in w for w in plan["warnings"])

    @pytest.mark.asyncio
    async def test_apply_produces_artifacts(self, integrator, spec_with_actions):
        plan = await integrator.plan(spec_with_actions)
        result = await integrator.apply(plan)
        assert result["success"] is True
        assert result["total_artifacts"] > 0

    def test_connector_catalog_has_common_connectors(self):
        assert "ServiceNow" in CONNECTOR_CATALOG
        assert "Teams" in CONNECTOR_CATALOG
        assert "HTTP" in CONNECTOR_CATALOG
        assert "SharePoint" in CONNECTOR_CATALOG
