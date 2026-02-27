# Copilot Studio Builder — Usage Guide

## Overview

The Copilot Studio Builder swarm automates the creation of enterprise-grade Copilot Studio agents. Starting from a declarative `agent_spec.json`, it produces:

1. A Power Platform solution skeleton ready for import
2. GitHub Actions / Azure DevOps pipeline stubs for ALM
3. Channel publish plans for Teams and M365 Copilot
4. Governance reports and readiness dashboards

## Prerequisites

- Python 3.11+
- `autobot` package installed
- Power Platform CLI (`pac`) for solution operations (optional for dry-run)
- GitHub Copilot CLI for LLM-powered features (optional for structural operations)

## Step-by-Step Walkthrough

### 1. Define your agent spec

Create an `agent_spec.json` describing your agent. Start from the example:

```bash
cp autobot/specs/agent_spec.example.json my_agent_spec.json
```

Edit the file to match your requirements. Key sections:

- **publisher**: Your organization's solution publisher name and prefix
- **knowledgeSources**: SharePoint sites, web pages, files, or Dataverse tables
- **actions**: Connectors your agent will use (ServiceNow, Teams, HTTP, etc.)
- **channels**: Where to publish (teams, m365_copilot)

### 2. Preview the build (dry run)

```bash
python -m autobot.swarms.cs_builder run my_agent_spec.json --dry-run
```

This runs the full pipeline without creating files, outputting a JSON plan showing:
- Solution files that would be created
- Knowledge source validation results
- Action connector mappings
- Governance check results
- Test suite and readiness assessment

### 3. Scaffold the solution

```bash
python -m autobot.swarms.cs_builder scaffold my_agent_spec.json --apply
```

This creates the solution folder at `solutions/<AgentName>/` with all artifacts.

### 4. Review the governance report

The dry run outputs a governance report. Fix any failures before proceeding:

```python
from autobot.agents.cs_builder.security import SecurityGovernanceAdvisorAgent

advisor = SecurityGovernanceAdvisorAgent()
report = await advisor.analyze("my_agent_spec.json")
print(report.to_markdown())
```

### 5. Import to Power Platform

Once the solution is scaffolded and governance passes:

```bash
# Using PAC CLI directly:
pac solution import --path solutions/MyAgent/

# Or use the autobot PAC CLI wrapper:
python -c "
from autobot.tools.pac_cli import PacCli
import asyncio

async def main():
    cli = PacCli()
    plan = await cli.plan_import_solution('dist/MyAgent_managed.zip', environment='test')
    print(plan)

asyncio.run(main())
"
```

### 6. Publish to channels

Review the publish plan (never auto-publishes):

```python
from autobot.agents.cs_builder.publisher import PublisherAgent

pub = PublisherAgent()
plan = await pub.plan_publish(spec)
print(plan)  # Review steps and approvals needed
```

### 7. Run readiness tests

```python
from autobot.agents.cs_builder.analytics import AnalyticsEvaluatorAgent

evaluator = AnalyticsEvaluatorAgent()
suite = await evaluator.generate_test_suite(spec)
print(suite.to_markdown())

readiness = await evaluator.evaluate_readiness(suite)
print(f"Score: {readiness['readiness_score']:.0%}")
```

## Python API Reference

### High-level

```python
from autobot.swarms.cs_builder import create_cs_builder_swarm, run_build

# One-shot pipeline
results = await run_build("spec.json", dry_run=True)

# Create swarm for custom orchestration
swarm = create_cs_builder_swarm(copilot_config={"model": "gpt-5"})
```

### Individual Agents

```python
from autobot.agents.cs_builder import (
    RequirementsPlannerAgent,
    AgentScaffolderAgent,
    KnowledgeSourceIngestorAgent,
    ActionsIntegratorAgent,
    SecurityGovernanceAdvisorAgent,
    PublisherAgent,
    AnalyticsEvaluatorAgent,
)
```

### Tool Adapters

```python
from autobot.tools.pac_cli import PacCli, MockRunner
from autobot.tools.dataverse_api import DataverseApi
from autobot.tools.sharepoint_check import SharePointChecker
from autobot.tools.teams_publish import TeamsPublisher
```

## Configuration

All agents accept a `copilot_config` dict:

```python
agent = AgentScaffolderAgent(copilot_config={
    "model": "gpt-5",
    "temperature": 0.2,
})
```

Or a typed config object:

```python
from autobot.agents.cs_builder.scaffolder import ScaffolderConfig

config = ScaffolderConfig(
    output_root="my_solutions",
    copilot_config={"model": "gpt-5"},
)
agent = AgentScaffolderAgent(config=config)
```

## Safety Guarantees

- **Dry-run by default**: All operations preview before executing
- **No secrets in source**: Governance agent scans for embedded credentials
- **Non-destructive publish**: Publisher never auto-publishes; requires explicit `--apply`
- **Managed solutions**: Enforced for non-dev environments
- **Connection references**: Required for all actions (no hardcoded credentials)
- **Signed reports**: Governance reports include integrity hashes
