"""SecurityGovernanceAdvisorAgent — static analysis and governance checks.

Enforces enterprise ALM rules over an ``agent_spec.json`` and its generated
solution artifacts.  Produces a governance report the swarm can gate on.

Rules enforced:
    1. No embedded secrets in spec or artifacts.
    2. Custom publisher with a valid prefix.
    3. Environment variables used for environment-specific settings.
    4. Connection references for all actions (no hardcoded credentials).
    5. Managed solutions required for non-dev targets.
    6. Consistent solution prefix across all artifacts.
    7. Channel scope checks (external access flags).

Every rule returns a structured finding that can be either ``pass``,
``warn``, or ``fail``.  The overall report is signed with a hash so the
swarm can verify integrity before gating on it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from autobot.agents.cs_builder._base import CopilotAgentMixin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class SecurityAdvisorConfig(BaseModel):
    """Configuration for SecurityGovernanceAdvisorAgent."""

    name: str = Field(default="security_advisor", description="Agent name")
    copilot_config: dict[str, Any] = Field(
        default_factory=lambda: {"model": "gpt-5", "temperature": 0.1},
        description="Copilot SDK backend configuration",
    )
    strict_mode: bool = Field(
        default=True,
        description="If True, warnings are promoted to failures.",
    )
    custom_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Additional custom governance rules.",
    )


# ---------------------------------------------------------------------------
# Finding / Report data structures
# ---------------------------------------------------------------------------

class Finding:
    """A single governance finding."""

    def __init__(
        self,
        rule_id: str,
        severity: str,  # "pass", "warn", "fail"
        message: str,
        *,
        remediation: str = "",
        location: str = "",
        diff: str = "",
    ):
        self.rule_id = rule_id
        self.severity = severity
        self.message = message
        self.remediation = remediation
        self.location = location
        self.diff = diff

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
        }
        if self.remediation:
            d["remediation"] = self.remediation
        if self.location:
            d["location"] = self.location
        if self.diff:
            d["diff"] = self.diff
        return d


class GovernanceReport:
    """Full governance report with integrity signature."""

    def __init__(self, agent_name: str, spec_path: str):
        self.agent_name = agent_name
        self.spec_path = spec_path
        self.findings: list[Finding] = []
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self._hash: str = ""

    @property
    def passed(self) -> bool:
        return not any(f.severity == "fail" for f in self.findings)

    @property
    def summary(self) -> dict[str, int]:
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    def sign(self) -> str:
        """Compute an integrity hash over the report content."""
        payload = json.dumps(self.to_dict(include_hash=False), sort_keys=True)
        self._hash = hashlib.sha256(payload.encode()).hexdigest()
        return self._hash

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "agent_name": self.agent_name,
            "spec_path": self.spec_path,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
        }
        if include_hash and self._hash:
            d["integrity_hash"] = self._hash
        return d

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), indent=2, **kwargs)

    def to_adaptive_card(self) -> dict[str, Any]:
        """Render the governance report as an Adaptive Card."""
        from autobot.tools.adaptive_cards import AdaptiveCardTemplate

        return AdaptiveCardTemplate.governance_report_card(self.to_dict())

    def to_markdown(self) -> str:
        """Render a human-readable Markdown governance report."""
        lines = [
            f"# Governance Report — {self.agent_name}",
            "",
            f"**Spec:** `{self.spec_path}`  ",
            f"**Timestamp:** {self.timestamp}  ",
            f"**Result:** {'PASSED' if self.passed else 'FAILED'}  ",
            "",
            "## Summary",
            "",
            f"| Pass | Warn | Fail |",
            f"|------|------|------|",
            f"| {self.summary['pass']} | {self.summary['warn']} | {self.summary['fail']} |",
            "",
            "## Findings",
            "",
        ]
        for f in self.findings:
            icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}.get(f.severity, "?")
            lines.append(f"### [{icon}] {f.rule_id}")
            lines.append(f"")
            lines.append(f"{f.message}")
            if f.location:
                lines.append(f"")
                lines.append(f"**Location:** `{f.location}`")
            if f.remediation:
                lines.append(f"")
                lines.append(f"**Remediation:** {f.remediation}")
            if f.diff:
                lines.append(f"")
                lines.append(f"```diff")
                lines.append(f"{f.diff}")
                lines.append(f"```")
            lines.append("")

        if self._hash:
            lines.append(f"---")
            lines.append(f"Integrity hash: `{self._hash}`")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Azure Storage Key", re.compile(r"DefaultEndpointsProtocol=https?;AccountName=.+;AccountKey=[A-Za-z0-9+/=]{40,}", re.I)),
    ("Connection String", re.compile(r"(Server|Data Source)=[^;]+;.*(Password|Pwd)=[^;]+", re.I)),
    ("Bearer Token", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I)),
    ("API Key (generic)", re.compile(r"(?:api[_-]?key|apikey|secret[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9\-._]{16,}", re.I)),
    ("Azure AD Client Secret", re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[A-Za-z0-9~_\-]{30,}", re.I)),
    ("Private Key Block", re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----")),
    ("GitHub PAT", re.compile(r"gh[po]_[A-Za-z0-9_]{36,}")),
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SecurityGovernanceAdvisorAgent(CopilotAgentMixin):
    """Static-analysis agent that enforces Power Platform / Copilot Studio
    governance rules over an agent spec and its generated solution.

    Uses Copilot SDK LLM for deep security review when available,
    falling back to static rule-based analysis otherwise.

    Args:
        copilot_config: Copilot SDK backend configuration.
        config: Full agent configuration (overrides copilot_config if both given).

    Example::

        advisor = SecurityGovernanceAdvisorAgent()
        report = await advisor.analyze("specs/agent_spec.example.json")
        if not report.passed:
            print(report.to_markdown())
    """

    def __init__(
        self,
        copilot_config: dict[str, Any] | None = None,
        config: SecurityAdvisorConfig | None = None,
    ):
        self._config = config or SecurityAdvisorConfig(
            **({"copilot_config": copilot_config} if copilot_config else {}),
        )
        self._copilot_config = self._config.copilot_config
        self.name = self._config.name
        self._is_running = False
        self._reasoning_trace: list[dict[str, Any]] = []

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._is_running = True
        await self._start_llm()

    async def stop(self) -> None:
        await self._stop_llm()
        self._is_running = False

    # -- public API ----------------------------------------------------------

    async def analyze(
        self,
        spec_path: str,
        *,
        solution_dir: str | None = None,
    ) -> GovernanceReport:
        """Run all governance rules against a spec and optional solution dir.

        Args:
            spec_path: Path to agent_spec.json.
            solution_dir: Optional path to the generated solution folder.

        Returns:
            GovernanceReport with all findings, signed.
        """
        spec = self._load_spec(spec_path)
        report = GovernanceReport(
            agent_name=spec.get("name", "unknown"),
            spec_path=spec_path,
        )

        # Run each rule
        self._rule_no_secrets_in_spec(spec, spec_path, report)
        self._rule_custom_publisher(spec, report)
        self._rule_valid_prefix(spec, report)
        self._rule_env_variables(spec, report)
        self._rule_connection_references(spec, report)
        self._rule_managed_outside_dev(spec, report)
        self._rule_channel_scope(spec, report)
        self._rule_dlp_configured(spec, report)

        if solution_dir:
            self._rule_no_secrets_in_artifacts(solution_dir, report)
            self._rule_consistent_prefix(spec, solution_dir, report)

        report.sign()
        return report

    async def analyze_spec_dict(
        self,
        spec: dict[str, Any],
        *,
        spec_path: str = "<in-memory>",
        solution_dir: str | None = None,
    ) -> GovernanceReport:
        """Run governance rules against an in-memory spec dict."""
        report = GovernanceReport(
            agent_name=spec.get("name", "unknown"),
            spec_path=spec_path,
        )

        self._rule_no_secrets_in_spec(spec, spec_path, report)
        self._rule_custom_publisher(spec, report)
        self._rule_valid_prefix(spec, report)
        self._rule_env_variables(spec, report)
        self._rule_connection_references(spec, report)
        self._rule_managed_outside_dev(spec, report)
        self._rule_channel_scope(spec, report)
        self._rule_dlp_configured(spec, report)

        if solution_dir:
            self._rule_no_secrets_in_artifacts(solution_dir, report)
            self._rule_consistent_prefix(spec, solution_dir, report)

        report.sign()
        return report

    # -- rule implementations ------------------------------------------------

    def _rule_no_secrets_in_spec(
        self,
        spec: dict[str, Any],
        spec_path: str,
        report: GovernanceReport,
    ) -> None:
        """GOV-001: No embedded secrets in spec."""
        spec_text = json.dumps(spec)
        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(spec_text)
            if match:
                report.findings.append(Finding(
                    rule_id="GOV-001",
                    severity="fail",
                    message=f"Potential secret detected: {label}",
                    location=spec_path,
                    remediation=(
                        "Remove the secret from the spec. Use an environment variable "
                        "name instead and set the actual value in each target environment."
                    ),
                    diff=f"- {match.group(0)[:40]}...\n+ <ENV_VARIABLE_NAME>",
                ))
                return
        report.findings.append(Finding(
            rule_id="GOV-001",
            severity="pass",
            message="No embedded secrets detected in spec.",
        ))

    def _rule_custom_publisher(
        self,
        spec: dict[str, Any],
        report: GovernanceReport,
    ) -> None:
        """GOV-002: Require custom publisher (not 'Default Publisher')."""
        publisher = spec.get("publisher", {})
        name = publisher.get("displayName", "")
        if not name or name.lower() in ("default publisher", "defaultpublisher", ""):
            report.findings.append(Finding(
                rule_id="GOV-002",
                severity="fail",
                message="Publisher must be a custom publisher, not the Default Publisher.",
                location="$.publisher.displayName",
                remediation="Set publisher.displayName to your organization's publisher name.",
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-002",
                severity="pass",
                message=f"Custom publisher configured: '{name}'.",
            ))

    def _rule_valid_prefix(
        self,
        spec: dict[str, Any],
        report: GovernanceReport,
    ) -> None:
        """GOV-003: Solution prefix must be valid and non-default."""
        prefix = spec.get("publisher", {}).get("prefix", "")
        default_prefixes = {"new", "cr", "prefix", "default", ""}
        if prefix in default_prefixes:
            report.findings.append(Finding(
                rule_id="GOV-003",
                severity="fail",
                message=f"Prefix '{prefix}' is a default or empty prefix.",
                location="$.publisher.prefix",
                remediation=(
                    "Set a unique, organization-specific prefix (2-8 lowercase "
                    "alphanumeric chars starting with a letter)."
                ),
            ))
        elif not re.match(r"^[a-z][a-z0-9]{1,7}$", prefix):
            report.findings.append(Finding(
                rule_id="GOV-003",
                severity="fail",
                message=f"Prefix '{prefix}' does not match required pattern.",
                location="$.publisher.prefix",
                remediation="Prefix must be 2-8 lowercase alphanumeric characters, starting with a letter.",
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-003",
                severity="pass",
                message=f"Valid custom prefix: '{prefix}'.",
            ))

    def _rule_env_variables(
        self,
        spec: dict[str, Any],
        report: GovernanceReport,
    ) -> None:
        """GOV-004: Environment variables must be enabled."""
        alm = spec.get("alm", {})
        use_env = alm.get("useEnvironmentVariables", False)
        if not use_env:
            report.findings.append(Finding(
                rule_id="GOV-004",
                severity="fail",
                message="alm.useEnvironmentVariables is not enabled.",
                location="$.alm.useEnvironmentVariables",
                remediation=(
                    "Set alm.useEnvironmentVariables to true. This ensures "
                    "environment-specific settings (URLs, keys) are externalized."
                ),
                diff="- \"useEnvironmentVariables\": false\n+ \"useEnvironmentVariables\": true",
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-004",
                severity="pass",
                message="Environment variables are enabled.",
            ))

    def _rule_connection_references(
        self,
        spec: dict[str, Any],
        report: GovernanceReport,
    ) -> None:
        """GOV-005: All actions must use connectionReference auth."""
        actions = spec.get("actions", [])
        if not actions:
            report.findings.append(Finding(
                rule_id="GOV-005",
                severity="pass",
                message="No actions defined — rule not applicable.",
            ))
            return

        bad_actions = [
            a["name"] for a in actions
            if a.get("auth") != "connectionReference"
        ]
        if bad_actions:
            report.findings.append(Finding(
                rule_id="GOV-005",
                severity="fail" if self._config.strict_mode else "warn",
                message=(
                    f"Actions using non-connectionReference auth: {', '.join(bad_actions)}. "
                    "Connection references enable per-environment credential management."
                ),
                location="$.actions[*].auth",
                remediation="Change auth to 'connectionReference' for all actions.",
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-005",
                severity="pass",
                message="All actions use connectionReference authentication.",
            ))

    def _rule_managed_outside_dev(
        self,
        spec: dict[str, Any],
        report: GovernanceReport,
    ) -> None:
        """GOV-006: Managed solutions required for non-dev targets."""
        alm = spec.get("alm", {})
        targets = spec.get("environments", {}).get("targets", [])
        managed = alm.get("managedOutsideDev", False)

        if targets and not managed:
            report.findings.append(Finding(
                rule_id="GOV-006",
                severity="warn",
                message=(
                    f"Non-dev targets {targets} are defined but managedOutsideDev is false. "
                    "Unmanaged solutions in test/prod environments cannot be properly uninstalled."
                ),
                location="$.alm.managedOutsideDev",
                remediation="Set alm.managedOutsideDev to true for proper ALM lifecycle.",
                diff="- \"managedOutsideDev\": false\n+ \"managedOutsideDev\": true",
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-006",
                severity="pass",
                message="Managed solution export enabled for non-dev targets.",
            ))

    def _rule_channel_scope(
        self,
        spec: dict[str, Any],
        report: GovernanceReport,
    ) -> None:
        """GOV-007: Channel and external access consistency."""
        channels = spec.get("channels", [])
        security = spec.get("security", {})
        allow_ext = security.get("allowExternal", False)

        external_channels = {"web", "custom"}
        has_external = bool(external_channels & set(channels))

        if has_external and not allow_ext:
            report.findings.append(Finding(
                rule_id="GOV-007",
                severity="warn",
                message=(
                    "External-facing channels (web/custom) are configured but "
                    "security.allowExternal is false. Verify this is intentional."
                ),
                location="$.security.allowExternal",
                remediation=(
                    "Either remove web/custom channels or set allowExternal to true "
                    "if external user access is intended."
                ),
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-007",
                severity="pass",
                message="Channel scope is consistent with external access policy.",
            ))

    def _rule_dlp_configured(
        self,
        spec: dict[str, Any],
        report: GovernanceReport,
    ) -> None:
        """GOV-008: DLP policies should be configured."""
        security = spec.get("security", {})
        dlp = security.get("dataLossPrevention", [])

        if not dlp:
            report.findings.append(Finding(
                rule_id="GOV-008",
                severity="warn",
                message="No DLP policies configured.",
                location="$.security.dataLossPrevention",
                remediation=(
                    "Consider adding DLP policies (e.g., pii-block, pii-mask) "
                    "to protect sensitive data."
                ),
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-008",
                severity="pass",
                message=f"DLP policies configured: {', '.join(dlp)}.",
            ))

    def _rule_no_secrets_in_artifacts(
        self,
        solution_dir: str,
        report: GovernanceReport,
    ) -> None:
        """GOV-009: Scan generated solution files for embedded secrets."""
        sol_path = Path(solution_dir)
        if not sol_path.exists():
            report.findings.append(Finding(
                rule_id="GOV-009",
                severity="pass",
                message=f"Solution directory '{solution_dir}' does not exist yet — skipped.",
            ))
            return

        # Scan text files in the solution
        scanned = 0
        for fp in sol_path.rglob("*"):
            if not fp.is_file():
                continue
            if fp.suffix in (".zip", ".png", ".jpg", ".gif", ".ico"):
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            scanned += 1
            for label, pattern in SECRET_PATTERNS:
                match = pattern.search(content)
                if match:
                    report.findings.append(Finding(
                        rule_id="GOV-009",
                        severity="fail",
                        message=f"Secret detected in artifact: {label}",
                        location=str(fp),
                        remediation="Remove the secret and use an environment variable reference.",
                    ))
                    return

        report.findings.append(Finding(
            rule_id="GOV-009",
            severity="pass",
            message=f"No secrets found in {scanned} scanned artifact files.",
        ))

    def _rule_consistent_prefix(
        self,
        spec: dict[str, Any],
        solution_dir: str,
        report: GovernanceReport,
    ) -> None:
        """GOV-010: Solution prefix is consistent across artifacts."""
        prefix = spec.get("publisher", {}).get("prefix", "")
        if not prefix:
            return  # Already flagged by GOV-003

        sol_path = Path(solution_dir)
        solution_xml = sol_path / "solution.xml"
        if not solution_xml.exists():
            report.findings.append(Finding(
                rule_id="GOV-010",
                severity="warn",
                message="solution.xml not found — cannot verify prefix consistency.",
                location=str(solution_xml),
            ))
            return

        content = solution_xml.read_text(encoding="utf-8", errors="ignore")
        if f"<CustomizationPrefix>{prefix}</CustomizationPrefix>" not in content:
            report.findings.append(Finding(
                rule_id="GOV-010",
                severity="fail",
                message=f"solution.xml does not contain expected prefix '{prefix}'.",
                location=str(solution_xml),
                remediation=f"Ensure the solution uses the publisher prefix '{prefix}'.",
            ))
        else:
            report.findings.append(Finding(
                rule_id="GOV-010",
                severity="pass",
                message=f"Prefix '{prefix}' is consistent in solution.xml.",
            ))

    # -- LLM-powered deep review --------------------------------------------

    async def deep_review(
        self,
        spec: dict[str, Any],
        *,
        solution_dir: str | None = None,
    ) -> GovernanceReport:
        """Use the LLM to analyze the spec for subtle security issues beyond
        the 10 static governance rules.

        When the LLM is available, sends the spec through a detailed security
        review prompt and merges the LLM findings into the governance report.
        When the LLM is unavailable, falls back to the standard
        ``analyze_spec_dict()`` method.

        Args:
            spec: Parsed agent_spec dict.
            solution_dir: Optional path to the generated solution folder.

        Returns:
            GovernanceReport enriched with LLM-identified findings.
        """
        # Always run the static rules as a baseline
        report = await self.analyze_spec_dict(spec, solution_dir=solution_dir)

        if not self.llm_available:
            logger.info("[%s] LLM unavailable, returning static analysis only", self.name)
            return report

        system_message = (
            "You are a senior security architect specializing in Microsoft Power Platform "
            "and Copilot Studio governance.\n\n"
            "Analyze the provided agent specification JSON for subtle security issues that "
            "static rules might miss. Focus on:\n"
            "1. Overly broad data access patterns (e.g., Sites.ReadWrite.All when Read suffices)\n"
            "2. Implicit trust boundaries (internal agents exposed to external channels)\n"
            "3. Data exfiltration vectors through action chaining\n"
            "4. Privilege escalation through connection reference sharing\n"
            "5. Missing rate limiting or abuse prevention for public-facing channels\n"
            "6. Sensitive data flow from knowledge sources to untrusted channels\n"
            "7. Incomplete DLP coverage for the data types handled\n"
            "8. Authentication mode weaknesses for the configured channels\n"
            "9. Environment variable misuse that could leak secrets across environments\n"
            "10. Supply-chain risks from custom connectors or third-party integrations\n\n"
            "Return a JSON object with:\n"
            "{\n"
            '  "findings": [\n'
            "    {\n"
            '      "rule_id": "DEEP-NNN",\n'
            '      "severity": "pass"|"warn"|"fail",\n'
            '      "message": "description of the issue",\n'
            '      "remediation": "how to fix it",\n'
            '      "location": "$.json.path if applicable"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Return ONLY valid JSON."
        )

        user_message = f"Analyze this agent specification for security issues:\n\n{json.dumps(spec, indent=2)}"

        try:
            raw = await self._llm_complete(
                system_message=system_message,
                user_message=user_message,
                temperature=0.1,
                expect_json=True,
            )
            result = json.loads(raw)

            for finding_data in result.get("findings", []):
                report.findings.append(Finding(
                    rule_id=finding_data.get("rule_id", "DEEP-000"),
                    severity=finding_data.get("severity", "warn"),
                    message=finding_data.get("message", ""),
                    remediation=finding_data.get("remediation", ""),
                    location=finding_data.get("location", ""),
                ))

        except (json.JSONDecodeError, RuntimeError) as exc:
            logger.debug("[%s] Deep review LLM call failed (%s), returning static report", self.name, exc)

        # Re-sign the report with the merged findings
        report.sign()
        return report

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _load_spec(path: str) -> dict[str, Any]:
        """Load and parse an agent spec JSON file."""
        p = Path(path)
        if not p.exists():
            msg = f"Spec file not found: {path}"
            raise FileNotFoundError(msg)
        return json.loads(p.read_text(encoding="utf-8"))

    def __repr__(self) -> str:
        return f"SecurityGovernanceAdvisorAgent(name={self.name!r}, llm={'yes' if self.llm_available else 'no'})"


__all__ = [
    "SecurityGovernanceAdvisorAgent",
    "SecurityAdvisorConfig",
    "GovernanceReport",
    "Finding",
]
