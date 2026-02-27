"""Tests for AnalyticsEvaluatorAgent."""

from __future__ import annotations

import pytest

from autobot.agents.cs_builder.analytics import (
    AnalyticsConfig,
    AnalyticsEvaluatorAgent,
    ConversationTestCase,
    TestSuite,
)


@pytest.fixture
def evaluator() -> AnalyticsEvaluatorAgent:
    return AnalyticsEvaluatorAgent()


@pytest.fixture
def spec() -> dict:
    return {
        "name": "Test Agent",
        "topics": [
            {"name": "PasswordReset", "triggerPhrases": ["reset password", "forgot password"]},
            {"name": "DeviceSetup", "triggerPhrases": ["new laptop", "setup device"]},
        ],
        "actions": [
            {"name": "CreateTicket", "connector": "ServiceNow", "auth": "connectionReference",
             "description": "Create a support ticket"},
        ],
    }


class TestConversationTestCase:
    def test_to_dict(self):
        tc = ConversationTestCase("t1", "hello", "greeting")
        d = tc.to_dict()
        assert d["name"] == "t1"
        assert d["user_message"] == "hello"

    def test_to_dict_with_action(self):
        tc = ConversationTestCase("t2", "create ticket", "CreateTicket", expected_action="CreateTicket")
        d = tc.to_dict()
        assert d["expected_action"] == "CreateTicket"


class TestTestSuite:
    def test_empty_score(self):
        suite = TestSuite("Test")
        assert suite.score() == 0.0

    def test_score_with_results(self):
        suite = TestSuite("Test")
        suite.results = [{"passed": True}, {"passed": False}, {"passed": True}]
        assert abs(suite.score() - 2/3) < 0.01

    def test_to_markdown(self):
        suite = TestSuite("Test")
        suite.add_test(ConversationTestCase("t1", "hello", "greeting"))
        suite.add_smoke_test("basic", "Basic check", "check something")
        md = suite.to_markdown()
        assert "# Readiness Dashboard" in md
        assert "t1" in md


class TestAnalyticsEvaluator:
    @pytest.mark.asyncio
    async def test_generate_suite_from_spec(self, evaluator, spec):
        suite = await evaluator.generate_test_suite(spec)
        # 2 trigger phrases per topic (2 topics) + 1 action
        # + 1 auth_boundary + 2 adversarial + 1 fallback = 9
        assert len(suite.test_cases) == 9
        # 3 standard + 1 per channel (no channels in spec = 0 extra)
        assert len(suite.smoke_tests) == 3

    @pytest.mark.asyncio
    async def test_generate_suite_empty_spec(self, evaluator):
        suite = await evaluator.generate_test_suite({"name": "Empty"})
        # auth_boundary + 2 adversarial + 1 fallback = 4
        assert len(suite.test_cases) == 4

    @pytest.mark.asyncio
    async def test_readiness_passes_with_enough_tests(self, evaluator, spec):
        suite = await evaluator.generate_test_suite(spec)
        result = await evaluator.evaluate_readiness(suite)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_readiness_fails_with_few_tests(self):
        config = AnalyticsConfig(readiness_threshold=0.9)
        evaluator = AnalyticsEvaluatorAgent(config=config)
        suite = await evaluator.generate_test_suite({"name": "Tiny", "topics": []})
        result = await evaluator.evaluate_readiness(suite)
        # 1 test / 5 = 0.2 < 0.9
        assert result["passed"] is False
