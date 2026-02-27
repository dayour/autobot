"""Tests for CopilotAgentMixin integration across all agents.

Verifies that all 7 agents properly extend CopilotAgentMixin and expose
LLM-powered methods with structural fallbacks.
"""

from __future__ import annotations

import pytest
from typing import Any

from autobot.agents.cs_builder._base import CopilotAgentMixin
from autobot.agents.cs_builder.security import SecurityGovernanceAdvisorAgent
from autobot.agents.cs_builder.scaffolder import AgentScaffolderAgent
from autobot.agents.cs_builder.ingestor import KnowledgeSourceIngestorAgent
from autobot.agents.cs_builder.actions import ActionsIntegratorAgent
from autobot.agents.cs_builder.publisher import PublisherAgent
from autobot.agents.cs_builder.planner import RequirementsPlannerAgent
from autobot.agents.cs_builder.analytics import AnalyticsEvaluatorAgent


@pytest.fixture
def spec() -> dict[str, Any]:
    return {
        "name": "Test Agent",
        "description": "A test agent for unit tests.",
        "publisher": {"displayName": "Test Org", "prefix": "tst"},
        "environments": {"source": "dev", "targets": ["test", "prod"]},
        "knowledgeSources": [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ],
        "actions": [
            {"name": "CreateTicket", "connector": "ServiceNow", "auth": "connectionReference",
             "description": "Create a support ticket"},
        ],
        "channels": ["teams"],
        "security": {
            "dataLossPrevention": ["pii-block"],
            "allowExternal": False,
            "authenticationMode": "entra_id",
        },
        "alm": {
            "managedOutsideDev": True,
            "useEnvironmentVariables": True,
            "solutionVersion": "1.0.0.0",
        },
        "topics": [
            {"name": "ITHelp", "triggerPhrases": ["help with IT", "IT support"]},
        ],
    }


class TestAllAgentsExtendMixin:
    """Verify all agents are instances of CopilotAgentMixin."""

    def test_security_is_mixin(self):
        agent = SecurityGovernanceAdvisorAgent()
        assert isinstance(agent, CopilotAgentMixin)

    def test_scaffolder_is_mixin(self):
        agent = AgentScaffolderAgent()
        assert isinstance(agent, CopilotAgentMixin)

    def test_ingestor_is_mixin(self):
        agent = KnowledgeSourceIngestorAgent()
        assert isinstance(agent, CopilotAgentMixin)

    def test_actions_is_mixin(self):
        agent = ActionsIntegratorAgent()
        assert isinstance(agent, CopilotAgentMixin)

    def test_publisher_is_mixin(self):
        agent = PublisherAgent()
        assert isinstance(agent, CopilotAgentMixin)

    def test_planner_is_mixin(self):
        agent = RequirementsPlannerAgent()
        assert isinstance(agent, CopilotAgentMixin)

    def test_analytics_is_mixin(self):
        agent = AnalyticsEvaluatorAgent()
        assert isinstance(agent, CopilotAgentMixin)


class TestMixinProperties:
    """Verify mixin properties work correctly without LLM."""

    def test_llm_not_available_by_default(self):
        agent = SecurityGovernanceAdvisorAgent()
        assert agent.llm_available is False

    def test_reasoning_trace_initialized(self):
        agent = RequirementsPlannerAgent()
        assert hasattr(agent, "_reasoning_trace")
        assert isinstance(agent._reasoning_trace, list)

    def test_copilot_config_set(self):
        agent = ActionsIntegratorAgent(copilot_config={"model": "gpt-5", "temperature": 0.5})
        assert agent._copilot_config["model"] == "gpt-5"
        assert agent._copilot_config["temperature"] == 0.5


class TestAgentRepr:
    """Verify __repr__ shows LLM status."""

    def test_security_repr(self):
        r = repr(SecurityGovernanceAdvisorAgent())
        assert "llm=" in r
        assert "no" in r

    def test_scaffolder_repr(self):
        r = repr(AgentScaffolderAgent())
        assert "llm=" in r

    def test_ingestor_repr(self):
        r = repr(KnowledgeSourceIngestorAgent())
        assert "llm=" in r

    def test_actions_repr(self):
        r = repr(ActionsIntegratorAgent())
        assert "llm=" in r

    def test_publisher_repr(self):
        r = repr(PublisherAgent())
        assert "llm=" in r


class TestSecurityDeepReview:
    @pytest.mark.asyncio
    async def test_deep_review_fallback(self, spec):
        """Without LLM, deep_review should fall back to static analysis."""
        agent = SecurityGovernanceAdvisorAgent()
        report = await agent.deep_review(spec)
        assert report.passed is True
        assert len(report.findings) > 0
        # Should have static rule findings
        rule_ids = {f.rule_id for f in report.findings}
        assert "GOV-001" in rule_ids


class TestScaffolderSuggestImprovements:
    @pytest.mark.asyncio
    async def test_suggest_improvements_fallback(self, spec):
        """Without LLM, should return empty suggestions."""
        agent = AgentScaffolderAgent()
        result = await agent.suggest_improvements(spec)
        assert "suggestions" in result
        assert isinstance(result["suggestions"], list)


class TestIngestorSuggestKnowledgeSources:
    @pytest.mark.asyncio
    async def test_suggest_knowledge_sources_fallback(self):
        """Without LLM, should return empty list."""
        agent = KnowledgeSourceIngestorAgent()
        result = await agent.suggest_knowledge_sources("Build an IT helpdesk agent")
        assert isinstance(result, list)


class TestActionsSuggestConnectors:
    @pytest.mark.asyncio
    async def test_suggest_connectors_fallback(self):
        """Without LLM, should return empty list."""
        agent = ActionsIntegratorAgent()
        result = await agent.suggest_connectors("Need to create ServiceNow tickets")
        assert isinstance(result, list)


class TestPublisherGenerateChecklist:
    @pytest.mark.asyncio
    async def test_generate_publish_checklist_fallback(self, spec):
        """Without LLM, should return structural checklist."""
        agent = PublisherAgent()
        result = await agent.generate_publish_checklist(spec)
        assert "checklist" in result
        assert isinstance(result["checklist"], list)


class TestPlannerFallback:
    @pytest.mark.asyncio
    async def test_generate_spec_heuristic(self):
        """Without LLM, planner uses heuristic extraction."""
        planner = RequirementsPlannerAgent()
        spec = await planner.generate_spec(
            "Build an IT helpdesk agent that uses SharePoint for knowledge "
            "and creates ServiceNow tickets."
        )
        assert spec["name"] == "New Agent"
        # Should detect SharePoint and ServiceNow
        assert len(spec["knowledgeSources"]) > 0
        assert len(spec["actions"]) > 0

    @pytest.mark.asyncio
    async def test_validate_spec(self):
        planner = RequirementsPlannerAgent()
        good_spec = {
            "name": "Test",
            "publisher": {"displayName": "Org", "prefix": "org"},
            "environments": {"source": "dev", "targets": ["prod"]},
            "channels": ["teams"],
        }
        result = await planner.validate_spec(good_spec)
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_spec_detects_errors(self):
        planner = RequirementsPlannerAgent()
        bad_spec = {"name": "Test"}
        result = await planner.validate_spec(bad_spec)
        assert result["valid"] is False
        assert len(result["errors"]) > 0


class TestAnalyticsReasoning:
    @pytest.mark.asyncio
    async def test_coverage_report(self, spec):
        evaluator = AnalyticsEvaluatorAgent()
        suite = await evaluator.generate_test_suite(spec)
        assert suite.coverage is not None
        assert suite.coverage.overall_coverage > 0

    @pytest.mark.asyncio
    async def test_category_diversity(self, spec):
        evaluator = AnalyticsEvaluatorAgent()
        suite = await evaluator.generate_test_suite(spec)
        categories = {tc.category for tc in suite.test_cases}
        assert "functional" in categories
        assert "security" in categories
        assert "adversarial" in categories

    @pytest.mark.asyncio
    async def test_reasoning_trace_empty_without_llm(self, spec):
        evaluator = AnalyticsEvaluatorAgent()
        suite = await evaluator.generate_test_suite(spec)
        # Without LLM, no reasoning steps are generated
        assert len(suite.reasoning_steps) == 0
