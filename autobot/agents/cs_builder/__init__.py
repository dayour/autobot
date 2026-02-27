"""Copilot Studio Builder agents.

This package contains specialized agents that collaborate as a swarm to
create, configure, and ship Copilot Studio agents at enterprise scale.

Agents:
    RequirementsPlannerAgent   - Normalize requirements into agent_spec.json
    AgentScaffolderAgent       - Generate Power Platform solution skeleton
    KnowledgeSourceIngestorAgent - Configure knowledge sources
    ActionsIntegratorAgent     - Map actions to connectors and flows
    SecurityGovernanceAdvisorAgent - Static analysis and governance checks
    PublisherAgent             - Publish to Teams / M365 Copilot channels
    AnalyticsEvaluatorAgent    - Generate test harnesses and eval scenarios

Quick start::

    from autobot.swarms.cs_builder import run_build
    results = await run_build("specs/agent_spec.example.json", dry_run=True)
"""

from __future__ import annotations

from autobot.agents.cs_builder.planner import RequirementsPlannerAgent
from autobot.agents.cs_builder.scaffolder import AgentScaffolderAgent
from autobot.agents.cs_builder.ingestor import KnowledgeSourceIngestorAgent
from autobot.agents.cs_builder.actions import ActionsIntegratorAgent
from autobot.agents.cs_builder.security import SecurityGovernanceAdvisorAgent
from autobot.agents.cs_builder.publisher import PublisherAgent
from autobot.agents.cs_builder.analytics import AnalyticsEvaluatorAgent

__all__ = [
    "RequirementsPlannerAgent",
    "AgentScaffolderAgent",
    "KnowledgeSourceIngestorAgent",
    "ActionsIntegratorAgent",
    "SecurityGovernanceAdvisorAgent",
    "PublisherAgent",
    "AnalyticsEvaluatorAgent",
]
