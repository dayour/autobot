"""Tests for tool adapters (pac_cli, dataverse_api, sharepoint_check, teams_publish)."""

from __future__ import annotations

import json
import pytest

from autobot.tools.pac_cli import PacCli, MockRunner, CommandResult
from autobot.tools.dataverse_api import DataverseApi, MockHttpClient, HttpResponse
from autobot.tools.sharepoint_check import SharePointChecker, parse_sharepoint_url
from autobot.tools.teams_publish import TeamsPublisher, CHANNEL_REQUIREMENTS


# ---------------------------------------------------------------------------
# PAC CLI
# ---------------------------------------------------------------------------

class TestPacCli:
    @pytest.fixture
    def cli(self) -> PacCli:
        return PacCli(runner=MockRunner())

    @pytest.mark.asyncio
    async def test_plan_create_solution(self, cli):
        plan = await cli.plan_create_solution("TestAgent", "tst", "Test Publisher")
        assert plan["dry_run"] is True
        assert plan["success"] is True
        assert plan["details"]["solution_name"] == "TestAgent"

    @pytest.mark.asyncio
    async def test_apply_create_solution(self, cli):
        plan = await cli.plan_create_solution("TestAgent", "tst", "Test Publisher")
        result = await cli.apply_create_solution(plan)
        assert result["dry_run"] is False
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_plan_export_solution(self, cli):
        plan = await cli.plan_export_solution("solutions/Test", managed=True)
        assert "managed" in plan["commands"][0]

    @pytest.mark.asyncio
    async def test_plan_import_solution(self, cli):
        plan = await cli.plan_import_solution("dist/Test.zip", environment="test")
        assert plan["details"]["environment"] == "test"

    @pytest.mark.asyncio
    async def test_plan_add_env_variable(self, cli):
        plan = await cli.plan_add_env_variable("solutions/Test", "tst_ApiUrl", "API URL")
        assert plan["action"] == "add_env_variable"

    @pytest.mark.asyncio
    async def test_plan_add_connection_reference(self, cli):
        plan = await cli.plan_add_connection_reference(
            "solutions/Test", "tst_ServiceNow_cr", "/providers/Microsoft.PowerApps/apis/shared_service-now"
        )
        assert plan["action"] == "add_connection_reference"

    @pytest.mark.asyncio
    async def test_mock_runner_records_calls(self):
        runner = MockRunner()
        cli = PacCli(runner=runner)
        plan = await cli.plan_create_solution("X", "x", "X")
        await cli.apply_create_solution(plan)
        assert len(runner.calls) == 1


# ---------------------------------------------------------------------------
# Dataverse API
# ---------------------------------------------------------------------------

class TestDataverseApi:
    @pytest.fixture
    def api(self) -> DataverseApi:
        return DataverseApi("https://test.crm.dynamics.com")

    @pytest.mark.asyncio
    async def test_plan_lookup_entity(self, api):
        plan = await api.plan_lookup_entity("solutions", filter="uniquename eq 'Test'")
        assert plan["dry_run"] is True
        assert "solutions" in plan["details"]["url"]

    @pytest.mark.asyncio
    async def test_apply_lookup(self, api):
        plan = await api.plan_lookup_entity("solutions")
        result = await api.apply_lookup(plan)
        assert result["dry_run"] is False
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_plan_check_solution_exists(self, api):
        plan = await api.plan_check_solution_exists("TestSolution")
        assert "uniquename" in plan["details"]["query"]["filter"]


# ---------------------------------------------------------------------------
# SharePoint Check
# ---------------------------------------------------------------------------

class TestSharePointCheck:
    def test_parse_valid_url(self):
        result = parse_sharepoint_url("https://contoso.sharepoint.com/sites/IT")
        assert result["is_valid"] is True
        assert result["tenant"] == "contoso"
        assert result["site_path"] == "/sites/IT"

    def test_parse_url_with_library(self):
        result = parse_sharepoint_url("https://contoso.sharepoint.com/sites/IT/Shared Documents/FAQ")
        assert result["is_valid"] is True
        assert result["library"] == "Shared Documents"
        assert result["folder"] == "FAQ"

    def test_parse_invalid_host(self):
        result = parse_sharepoint_url("https://example.com/sites/IT")
        assert result["is_valid"] is False

    def test_parse_missing_site(self):
        result = parse_sharepoint_url("https://contoso.sharepoint.com/teams/IT")
        assert result["is_valid"] is False

    @pytest.mark.asyncio
    async def test_plan_validate(self):
        checker = SharePointChecker()
        sources = [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ]
        plan = await checker.plan_validate(sources)
        assert plan["total_sources"] == 1
        assert plan["success"] is True

    @pytest.mark.asyncio
    async def test_plan_validate_invalid_url(self):
        checker = SharePointChecker()
        sources = [
            {"type": "sharepoint", "url": "https://bad.example.com/sites/X", "scope": "site"},
        ]
        plan = await checker.plan_validate(sources)
        assert plan["success"] is False

    @pytest.mark.asyncio
    async def test_apply_validate(self):
        checker = SharePointChecker()
        sources = [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ]
        plan = await checker.plan_validate(sources)
        result = await checker.apply_validate(plan)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Teams Publish
# ---------------------------------------------------------------------------

class TestTeamsPublish:
    @pytest.fixture
    def pub(self) -> TeamsPublisher:
        return TeamsPublisher()

    @pytest.mark.asyncio
    async def test_plan_publish(self, pub):
        plan = await pub.plan_publish(["teams", "m365_copilot"], agent_name="Test")
        assert len(plan["channels"]) == 2
        assert len(plan["approvals_needed"]) == 2

    @pytest.mark.asyncio
    async def test_plan_unknown_channel(self, pub):
        plan = await pub.plan_publish(["unknown_channel"])
        assert len(plan["warnings"]) >= 1

    @pytest.mark.asyncio
    async def test_apply_publish(self, pub):
        plan = await pub.plan_publish(["teams"])
        result = await pub.apply_publish(plan)
        assert result["success"] is True

    def test_channel_requirements_complete(self):
        assert "teams" in CHANNEL_REQUIREMENTS
        assert "m365_copilot" in CHANNEL_REQUIREMENTS
        assert "web" in CHANNEL_REQUIREMENTS
        for ch in CHANNEL_REQUIREMENTS.values():
            assert "steps" in ch
            assert len(ch["steps"]) > 0
