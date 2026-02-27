"""Tests for Graph API SharePoint integration."""

from __future__ import annotations

import pytest

from autobot.tools.sharepoint_check import (
    GraphApiClient,
    MockGraphClient,
    SharePointChecker,
    parse_sharepoint_url,
)


class TestGraphApiClient:
    @pytest.fixture
    def mock_graph(self) -> MockGraphClient:
        return MockGraphClient()

    @pytest.mark.asyncio
    async def test_get_site(self, mock_graph):
        result = await mock_graph.get_site("contoso", "/sites/IT")
        assert result["success"] is True
        assert "id" in result["data"]

    @pytest.mark.asyncio
    async def test_list_site_drives(self, mock_graph):
        result = await mock_graph.list_site_drives(mock_graph._FAKE_SITE_ID)
        assert result["success"] is True
        assert len(result["data"]["value"]) >= 1

    @pytest.mark.asyncio
    async def test_get_drive_root_children(self, mock_graph):
        result = await mock_graph.get_drive_root_children(mock_graph._FAKE_DRIVE_ID)
        assert result["success"] is True
        assert len(result["data"]["value"]) >= 1

    @pytest.mark.asyncio
    async def test_list_site_permissions(self, mock_graph):
        result = await mock_graph.list_site_permissions(mock_graph._FAKE_SITE_ID)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_site_content_types(self, mock_graph):
        result = await mock_graph.get_site_content_types(mock_graph._FAKE_SITE_ID)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_site_items(self, mock_graph):
        result = await mock_graph.search_site_items(mock_graph._FAKE_SITE_ID, "policy")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_mock_records_calls(self, mock_graph):
        await mock_graph.get_site("contoso", "/sites/IT")
        await mock_graph.list_site_drives("site-id")
        assert len(mock_graph.mock_http.calls) >= 2


class TestSharePointCheckerWithGraph:
    @pytest.fixture
    def checker_with_graph(self) -> SharePointChecker:
        return SharePointChecker(graph_client=MockGraphClient())

    @pytest.fixture
    def checker_no_graph(self) -> SharePointChecker:
        return SharePointChecker()

    @pytest.mark.asyncio
    async def test_apply_validate_with_graph(self, checker_with_graph):
        sources = [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ]
        plan = await checker_with_graph.plan_validate(sources)
        result = await checker_with_graph.apply_validate(plan)
        assert result["success"] is True
        r = result["results"][0]
        assert r["reachable"] is True
        assert r["has_permission"] is True
        assert r["estimated_items"] > 0

    @pytest.mark.asyncio
    async def test_apply_validate_without_graph(self, checker_no_graph):
        sources = [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ]
        plan = await checker_no_graph.plan_validate(sources)
        result = await checker_no_graph.apply_validate(plan)
        assert result["success"] is True
        # Structural only — no item count
        assert result["results"][0]["estimated_items"] == 0

    @pytest.mark.asyncio
    async def test_plan_enumerate_sources(self, checker_with_graph):
        sources = [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ]
        plan = await checker_with_graph.plan_enumerate_sources(sources)
        assert plan["success"] is True
        assert plan["total_sources"] == 1

    @pytest.mark.asyncio
    async def test_apply_enumerate_sources_with_graph(self, checker_with_graph):
        sources = [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ]
        plan = await checker_with_graph.plan_enumerate_sources(sources)
        result = await checker_with_graph.apply_enumerate_sources(plan)
        assert result["success"] is True
        r = result["results"][0]
        assert r["mode"] == "graph_api"
        assert r["item_count"] > 0
        assert len(r["drives"]) >= 1

    @pytest.mark.asyncio
    async def test_apply_enumerate_sources_structural(self, checker_no_graph):
        sources = [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ]
        plan = await checker_no_graph.plan_enumerate_sources(sources)
        result = await checker_no_graph.apply_enumerate_sources(plan)
        assert result["results"][0]["mode"] == "structural"

    @pytest.mark.asyncio
    async def test_invalid_url_with_graph(self, checker_with_graph):
        sources = [
            {"type": "sharepoint", "url": "https://bad.example.com/foo", "scope": "site"},
        ]
        plan = await checker_with_graph.plan_validate(sources)
        assert plan["success"] is False
        result = await checker_with_graph.apply_validate(plan)
        assert result["success"] is False
