"""Tests for PublisherAgent."""

from __future__ import annotations

import pytest

from autobot.agents.cs_builder.publisher import PublisherAgent, PublisherConfig


@pytest.fixture
def publisher() -> PublisherAgent:
    return PublisherAgent()


@pytest.fixture
def spec() -> dict:
    return {
        "name": "Contoso Agent",
        "channels": ["teams", "m365_copilot"],
        "security": {
            "allowExternal": False,
            "rbacRoles": ["IT-Users"],
        },
    }


class TestPublisher:
    @pytest.mark.asyncio
    async def test_plan_publish_returns_channels(self, publisher, spec):
        plan = await publisher.plan_publish(spec)
        assert len(plan["channels"]) == 2
        assert plan["dry_run"] is True

    @pytest.mark.asyncio
    async def test_plan_lists_approvals(self, publisher, spec):
        plan = await publisher.plan_publish(spec)
        assert len(plan["approvals_needed"]) >= 2  # Teams + M365

    @pytest.mark.asyncio
    async def test_plan_generates_org_notes(self, publisher, spec):
        plan = await publisher.plan_publish(spec)
        assert len(plan["org_approval_notes"]) > 0

    @pytest.mark.asyncio
    async def test_apply_respects_dry_run_default(self, publisher, spec):
        plan = await publisher.plan_publish(spec)
        result = await publisher.apply_publish(plan)
        # force_dry_run is True by default
        assert result["dry_run"] is True
        assert "force_dry_run" in result["message"]

    @pytest.mark.asyncio
    async def test_apply_executes_when_forced(self, spec):
        config = PublisherConfig(force_dry_run=False)
        pub = PublisherAgent(config=config)
        plan = await pub.plan_publish(spec)
        result = await pub.apply_publish(plan)
        assert result["dry_run"] is False
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_web_channel_scope_warning(self):
        spec = {
            "name": "Web Agent",
            "channels": ["web"],
            "security": {"allowExternal": False},
        }
        pub = PublisherAgent()
        plan = await pub.plan_publish(spec)
        assert any("web" in w.lower() for w in plan.get("warnings", []))
