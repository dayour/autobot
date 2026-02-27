"""Tests for agent-level Adaptive Card integration methods."""

from __future__ import annotations

import json
import pytest

from autobot.agents.cs_builder.security import GovernanceReport, Finding
from autobot.agents.cs_builder.analytics import TestSuite, CoverageReport, ConversationTestCase
from autobot.agents.cs_builder.publisher import PublisherAgent
from autobot.agents.cs_builder.ingestor import KnowledgeSourceIngestorAgent
from autobot.tools.adaptive_cards import AdaptiveCardValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def good_report() -> GovernanceReport:
    report = GovernanceReport("TestBot", "spec.json")
    report.findings.append(Finding("GOV-001", "pass", "No secrets found"))
    report.findings.append(Finding("GOV-002", "pass", "Custom publisher"))
    report.findings.append(Finding("GOV-003", "pass", "Valid prefix"))
    report.sign()
    return report


@pytest.fixture
def failed_report() -> GovernanceReport:
    report = GovernanceReport("BadBot", "bad_spec.json")
    report.findings.append(Finding("GOV-001", "fail", "Secret detected"))
    report.findings.append(Finding("GOV-002", "fail", "Default publisher"))
    report.findings.append(Finding("GOV-003", "warn", "Weak prefix"))
    report.sign()
    return report


@pytest.fixture
def test_suite() -> TestSuite:
    suite = TestSuite("TestBot")
    suite.add_test(ConversationTestCase("t1", "hello", "greeting"))
    suite.add_test(ConversationTestCase("t2", "reset pass", "PasswordReset"))
    suite.results = [{"passed": True}, {"passed": True}]
    suite.coverage = CoverageReport()
    suite.coverage.topic_coverage = {"greeting": True, "PasswordReset": True}
    suite.coverage.action_coverage = {"CreateTicket": True}
    return suite


@pytest.fixture
def coverage_report() -> CoverageReport:
    report = CoverageReport()
    report.topic_coverage = {"t1": True, "t2": False}
    report.action_coverage = {"a1": True}
    report.security_tests = ["sec_test_1"]
    report.edge_cases = ["edge_1"]
    report.gaps = ["Untested topics: t2"]
    return report


@pytest.fixture
def example_spec() -> dict:
    return {
        "name": "Contoso IT Bot",
        "channels": ["teams", "m365_copilot"],
        "security": {"authenticationMode": "entra_id", "dataLossPrevention": ["pii-block"]},
        "actions": [{"name": "CreateTicket", "connector": "ServiceNow", "auth": "connectionReference"}],
        "knowledgeSources": [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ],
    }


# ---------------------------------------------------------------------------
# GovernanceReport card
# ---------------------------------------------------------------------------

class TestGovernanceReportCard:
    def test_good_report_produces_card(self, good_report):
        card = good_report.to_adaptive_card()
        assert card["type"] == "AdaptiveCard"

    def test_failed_report_produces_card(self, failed_report):
        card = failed_report.to_adaptive_card()
        assert card["type"] == "AdaptiveCard"

    def test_card_contains_summary_facts(self, good_report):
        card = good_report.to_adaptive_card()
        fact_sets = [el for el in card["body"] if el.get("type") == "FactSet"]
        assert len(fact_sets) >= 1

    def test_card_contains_findings(self, failed_report):
        card = failed_report.to_adaptive_card()
        text_blocks = [el for el in card["body"] if el.get("type") == "TextBlock"]
        finding_blocks = [tb for tb in text_blocks if "GOV-" in tb.get("text", "")]
        assert len(finding_blocks) >= 2

    def test_card_validates(self, good_report):
        card = good_report.to_adaptive_card()
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# TestSuite card
# ---------------------------------------------------------------------------

class TestTestSuiteCard:
    def test_suite_produces_card(self, test_suite):
        card = test_suite.to_adaptive_card()
        assert card["type"] == "AdaptiveCard"

    def test_card_shows_score(self, test_suite):
        card = test_suite.to_adaptive_card()
        fact_sets = [el for el in card["body"] if el.get("type") == "FactSet"]
        all_facts = []
        for fs in fact_sets:
            all_facts.extend(fs.get("facts", []))
        score_facts = [f for f in all_facts if f.get("title") == "Score"]
        assert len(score_facts) == 1

    def test_card_validates(self, test_suite):
        card = test_suite.to_adaptive_card()
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# CoverageReport card
# ---------------------------------------------------------------------------

class TestCoverageReportCard:
    def test_coverage_produces_card(self, coverage_report):
        card = coverage_report.to_adaptive_card()
        assert card["type"] == "AdaptiveCard"

    def test_card_contains_gaps(self, coverage_report):
        card = coverage_report.to_adaptive_card()
        text_blocks = [el for el in card["body"] if el.get("type") == "TextBlock"]
        gap_blocks = [tb for tb in text_blocks if "Untested" in tb.get("text", "")]
        assert len(gap_blocks) >= 1

    def test_card_validates(self, coverage_report):
        card = coverage_report.to_adaptive_card()
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# Publisher approval card
# ---------------------------------------------------------------------------

class TestPublisherApprovalCard:
    @pytest.mark.asyncio
    async def test_generates_approval_card(self, example_spec):
        pub = PublisherAgent()
        card = await pub.generate_approval_card(example_spec)
        assert card["type"] == "AdaptiveCard"

    @pytest.mark.asyncio
    async def test_card_has_channels(self, example_spec):
        pub = PublisherAgent()
        card = await pub.generate_approval_card(example_spec)
        fact_sets = [el for el in card["body"] if el.get("type") == "FactSet"]
        all_facts = []
        for fs in fact_sets:
            all_facts.extend(fs.get("facts", []))
        channel_facts = [f for f in all_facts if f.get("title") == "Channels"]
        assert len(channel_facts) == 1
        assert "teams" in channel_facts[0]["value"]

    @pytest.mark.asyncio
    async def test_card_has_action_buttons(self, example_spec):
        pub = PublisherAgent()
        card = await pub.generate_approval_card(example_spec)
        assert len(card["actions"]) == 2
        titles = {a["title"] for a in card["actions"]}
        assert "Approve" in titles
        assert "Reject" in titles


# ---------------------------------------------------------------------------
# Ingestor status card
# ---------------------------------------------------------------------------

class TestIngestorStatusCard:
    @pytest.mark.asyncio
    async def test_plan_to_card(self, example_spec):
        ingestor = KnowledgeSourceIngestorAgent()
        plan = await ingestor.plan(example_spec)
        card = KnowledgeSourceIngestorAgent.plan_to_adaptive_card(plan)
        assert card["type"] == "AdaptiveCard"

    @pytest.mark.asyncio
    async def test_card_shows_sources(self, example_spec):
        ingestor = KnowledgeSourceIngestorAgent()
        plan = await ingestor.plan(example_spec)
        card = KnowledgeSourceIngestorAgent.plan_to_adaptive_card(plan)
        fact_sets = [el for el in card["body"] if el.get("type") == "FactSet"]
        assert len(fact_sets) >= 1

    def test_empty_sources_card(self):
        card = KnowledgeSourceIngestorAgent.plan_to_adaptive_card({"source_plans": []})
        assert card["type"] == "AdaptiveCard"
        text_blocks = [el for el in card["body"] if el.get("type") == "TextBlock"]
        assert any("No knowledge" in tb.get("text", "") for tb in text_blocks)

    @pytest.mark.asyncio
    async def test_card_validates(self, example_spec):
        ingestor = KnowledgeSourceIngestorAgent()
        plan = await ingestor.plan(example_spec)
        card = KnowledgeSourceIngestorAgent.plan_to_adaptive_card(plan)
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is True
