"""Tests for SecurityGovernanceAdvisorAgent."""

from __future__ import annotations

import json
import pytest

from autobot.agents.cs_builder.security import (
    Finding,
    GovernanceReport,
    SecurityAdvisorConfig,
    SecurityGovernanceAdvisorAgent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def good_spec() -> dict[str, object]:
    """A spec that should pass all governance rules."""
    return {
        "name": "Contoso IT Helpdesk Agent",
        "publisher": {"displayName": "Contoso IT", "prefix": "contit"},
        "environments": {"source": "dev", "targets": ["test", "prod"]},
        "knowledgeSources": [
            {"type": "sharepoint", "url": "https://contoso.sharepoint.com/sites/IT", "scope": "site"},
        ],
        "actions": [
            {"name": "CreateTicket", "connector": "ServiceNow", "auth": "connectionReference"},
        ],
        "channels": ["teams", "m365_copilot"],
        "security": {
            "dataLossPrevention": ["pii-block"],
            "allowExternal": False,
        },
        "alm": {
            "managedOutsideDev": True,
            "useEnvironmentVariables": True,
        },
    }


@pytest.fixture
def bad_spec() -> dict[str, object]:
    """A spec that should fail multiple governance rules."""
    return {
        "name": "Bad Agent",
        "publisher": {"displayName": "", "prefix": ""},
        "environments": {"source": "dev", "targets": ["prod"]},
        "actions": [
            {"name": "Risky", "connector": "HTTP", "auth": "apiKey"},
        ],
        "channels": ["web"],
        "security": {"allowExternal": False},
        "alm": {
            "managedOutsideDev": False,
            "useEnvironmentVariables": False,
        },
    }


@pytest.fixture
def secret_spec() -> dict[str, object]:
    """A spec with an embedded secret."""
    return {
        "name": "Secret Agent",
        "publisher": {"displayName": "Test", "prefix": "tst"},
        "environments": {"source": "dev"},
        "channels": ["teams"],
        "actions": [
            {
                "name": "CallApi",
                "connector": "HTTP",
                "auth": "connectionReference",
                "inputs": {"apikey": "api_key: SUPER_SECRET_KEY_1234567890abcdef"},
            },
        ],
        "security": {"dataLossPrevention": ["pii-block"]},
        "alm": {"useEnvironmentVariables": True, "managedOutsideDev": True},
    }


@pytest.fixture
def advisor() -> SecurityGovernanceAdvisorAgent:
    return SecurityGovernanceAdvisorAgent()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGovernanceReport:
    """Tests for the GovernanceReport data structure."""

    def test_empty_report_passes(self):
        report = GovernanceReport("Test", "spec.json")
        assert report.passed is True
        assert report.summary == {"pass": 0, "warn": 0, "fail": 0}

    def test_report_with_failure(self):
        report = GovernanceReport("Test", "spec.json")
        report.findings.append(Finding("GOV-001", "fail", "bad"))
        assert report.passed is False
        assert report.summary["fail"] == 1

    def test_report_with_warning_passes(self):
        report = GovernanceReport("Test", "spec.json")
        report.findings.append(Finding("GOV-007", "warn", "check this"))
        assert report.passed is True

    def test_sign_produces_hash(self):
        report = GovernanceReport("Test", "spec.json")
        report.findings.append(Finding("GOV-001", "pass", "ok"))
        h = report.sign()
        assert len(h) == 64  # SHA-256 hex
        assert report._hash == h

    def test_to_json(self):
        report = GovernanceReport("Test", "spec.json")
        report.findings.append(Finding("GOV-001", "pass", "ok"))
        report.sign()
        data = json.loads(report.to_json())
        assert data["passed"] is True
        assert "integrity_hash" in data
        assert len(data["findings"]) == 1

    def test_to_markdown(self):
        report = GovernanceReport("Test", "spec.json")
        report.findings.append(Finding("GOV-001", "pass", "ok"))
        report.sign()
        md = report.to_markdown()
        assert "# Governance Report" in md
        assert "PASSED" in md


class TestSecurityAdvisor:
    """Tests for SecurityGovernanceAdvisorAgent rule enforcement."""

    @pytest.mark.asyncio
    async def test_good_spec_passes(self, advisor, good_spec):
        report = await advisor.analyze_spec_dict(good_spec)
        assert report.passed is True
        fail_findings = [f for f in report.findings if f.severity == "fail"]
        assert len(fail_findings) == 0, [f.to_dict() for f in fail_findings]

    @pytest.mark.asyncio
    async def test_bad_spec_fails(self, advisor, bad_spec):
        report = await advisor.analyze_spec_dict(bad_spec)
        assert report.passed is False
        fail_ids = {f.rule_id for f in report.findings if f.severity == "fail"}
        # Should fail: publisher name (GOV-002), prefix (GOV-003), env vars (GOV-004),
        # connection references (GOV-005)
        assert "GOV-002" in fail_ids
        assert "GOV-003" in fail_ids
        assert "GOV-004" in fail_ids
        assert "GOV-005" in fail_ids

    @pytest.mark.asyncio
    async def test_secret_detection(self, advisor, secret_spec):
        report = await advisor.analyze_spec_dict(secret_spec)
        secret_findings = [f for f in report.findings if f.rule_id == "GOV-001" and f.severity == "fail"]
        assert len(secret_findings) == 1

    @pytest.mark.asyncio
    async def test_managed_outside_dev_warning(self, advisor, bad_spec):
        report = await advisor.analyze_spec_dict(bad_spec)
        warn_findings = [f for f in report.findings if f.rule_id == "GOV-006"]
        assert len(warn_findings) == 1
        assert warn_findings[0].severity == "warn"

    @pytest.mark.asyncio
    async def test_channel_scope_warning(self, advisor, bad_spec):
        report = await advisor.analyze_spec_dict(bad_spec)
        channel_findings = [f for f in report.findings if f.rule_id == "GOV-007"]
        assert len(channel_findings) == 1
        assert channel_findings[0].severity == "warn"

    @pytest.mark.asyncio
    async def test_dlp_warning(self, advisor, bad_spec):
        report = await advisor.analyze_spec_dict(bad_spec)
        dlp_findings = [f for f in report.findings if f.rule_id == "GOV-008"]
        assert len(dlp_findings) == 1
        assert dlp_findings[0].severity == "warn"

    @pytest.mark.asyncio
    async def test_report_is_signed(self, advisor, good_spec):
        report = await advisor.analyze_spec_dict(good_spec)
        assert report._hash
        assert len(report._hash) == 64

    @pytest.mark.asyncio
    async def test_analyze_from_file(self, advisor, good_spec, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(good_spec))
        report = await advisor.analyze(str(spec_file))
        assert report.passed is True

    @pytest.mark.asyncio
    async def test_analyze_file_not_found(self, advisor):
        with pytest.raises(FileNotFoundError):
            await advisor.analyze("/nonexistent/spec.json")


class TestFinding:
    def test_finding_to_dict_minimal(self):
        f = Finding("GOV-001", "pass", "ok")
        d = f.to_dict()
        assert d == {"rule_id": "GOV-001", "severity": "pass", "message": "ok"}

    def test_finding_to_dict_full(self):
        f = Finding(
            "GOV-004", "fail", "bad",
            remediation="fix it",
            location="$.alm",
            diff="- old\n+ new",
        )
        d = f.to_dict()
        assert d["remediation"] == "fix it"
        assert d["location"] == "$.alm"
        assert d["diff"] == "- old\n+ new"
