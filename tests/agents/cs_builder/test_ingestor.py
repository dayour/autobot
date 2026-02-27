"""Tests for KnowledgeSourceIngestorAgent."""

from __future__ import annotations

import pytest

from autobot.agents.cs_builder.ingestor import KnowledgeSourceIngestorAgent


@pytest.fixture
def ingestor() -> KnowledgeSourceIngestorAgent:
    return KnowledgeSourceIngestorAgent()


@pytest.fixture
def spec_with_sources() -> dict:
    return {
        "knowledgeSources": [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
            {"type": "web", "url": "https://docs.contoso.com/help", "depth": 2},
            {"type": "file", "path": "./knowledge/*.pdf"},
        ],
    }


class TestKnowledgeIngestor:
    @pytest.mark.asyncio
    async def test_plan_returns_all_sources(self, ingestor, spec_with_sources):
        plan = await ingestor.plan(spec_with_sources)
        assert plan["total_sources"] == 3
        assert len(plan["source_plans"]) == 3

    @pytest.mark.asyncio
    async def test_plan_validates_sharepoint(self, ingestor, spec_with_sources):
        plan = await ingestor.plan(spec_with_sources)
        sp = [s for s in plan["source_plans"] if s["type"] == "sharepoint"][0]
        assert sp["valid"] is True
        assert "Sites.Read.All" in sp["scopes_required"]

    @pytest.mark.asyncio
    async def test_plan_validates_web(self, ingestor, spec_with_sources):
        plan = await ingestor.plan(spec_with_sources)
        web = [s for s in plan["source_plans"] if s["type"] == "web"][0]
        assert web["valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_sharepoint_url(self, ingestor):
        spec = {"knowledgeSources": [{"type": "sharepoint", "url": "https://not-sharepoint.com/sites/IT"}]}
        plan = await ingestor.plan(spec)
        assert plan["success"] is False

    @pytest.mark.asyncio
    async def test_apply_runs_validation(self, ingestor, spec_with_sources):
        plan = await ingestor.plan(spec_with_sources)
        result = await ingestor.apply(plan)
        assert result["dry_run"] is False
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_empty_sources(self, ingestor):
        plan = await ingestor.plan({"knowledgeSources": []})
        assert plan["success"] is True
        assert plan["total_sources"] == 0
