# Copilot Studio Builder Swarm

A multi-agent swarm that takes a high-level `agent_spec.json` and produces a ready-to-import Power Platform solution containing a Copilot Studio agent skeleton.

## Architecture

```
agent_spec.json
      |
      v
[RequirementsPlannerAgent]   -- normalize requirements
      |
      v
[AgentScaffolderAgent]       -- generate solution skeleton
      |
      v
[KnowledgeSourceIngestorAgent] -- configure knowledge sources
      |
      v
[ActionsIntegratorAgent]     -- map actions to connectors/flows
      |
      v
[SecurityGovernanceAdvisorAgent] -- governance gate (blocks on failure)
      |
      v
[PublisherAgent]             -- channel publish (non-destructive by default)
      |
      v
[AnalyticsEvaluatorAgent]   -- test harness & readiness gate
```

## Quick Start

### End-to-end dry run

```bash
python -m autobot.swarms.cs_builder run autobot/specs/agent_spec.example.json --dry-run
```

### Materialize solution locally

```bash
python -m autobot.swarms.cs_builder scaffold autobot/specs/agent_spec.example.json --apply
```

### Python API

```python
from autobot.swarms.cs_builder import run_build

# Full pipeline (dry-run)
results = await run_build("autobot/specs/agent_spec.example.json", dry_run=True)

# Full pipeline (apply)
results = await run_build("autobot/specs/agent_spec.example.json", dry_run=False)
```

### Granular agent usage

```python
from autobot.agents.cs_builder.scaffolder import AgentScaffolderAgent

scaff = AgentScaffolderAgent(copilot_config={"model": "gpt-5", "temperature": 0.2})
plan = await scaff.plan("autobot/specs/agent_spec.example.json")   # preview
print(plan.to_json())
await scaff.apply(plan)                                             # materialize
```

## Inputs

### `agent_spec.json`

The spec defines everything about the agent:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Agent display name |
| `publisher` | Yes | `{displayName, prefix}` for solution publisher |
| `environments` | Yes | `{source, targets[]}` for ALM |
| `knowledgeSources` | No | SharePoint, web, file, Dataverse sources |
| `actions` | No | Connector-based actions with connection references |
| `channels` | Yes | `teams`, `m365_copilot`, `web`, `custom` |
| `security` | No | DLP, external access, auth mode, RBAC |
| `alm` | No | Managed solutions, env vars, pipelines |
| `telemetry` | No | App Insights configuration |
| `topics` | No | Conversation topics with trigger phrases |

See `autobot/specs/agent_spec.schema.json` for the full JSON Schema and `agent_spec.example.json` for a realistic example.

## Outputs

### Solution skeleton (`solutions/<AgentName>/`)

```
solutions/ContosoITHelpdeskAgent/
  solution.xml                          # Solution metadata
  Customizations.xml                    # Customizations container
  [Content_Types].xml                   # Package content types
  environmentvariabledefinitions/       # Env var definitions
    contit_AppInsightsConnectionString/
      environmentvariabledefinition.xml
  connectionreferences/                 # Connection ref placeholders
    contit_ServiceNow_cr.json
    contit_Teams_cr.json
  botcomponents/                        # Agent artifact stub
    contit_ContosoITHelpdeskAgent_bot/
      bot.json
  .pipelines/                           # ALM pipeline stubs
    build.yml
    release.yml
```

### Governance report

JSON + Markdown report with pass/warn/fail findings for:
- GOV-001: No embedded secrets
- GOV-002: Custom publisher required
- GOV-003: Valid solution prefix
- GOV-004: Environment variables enabled
- GOV-005: Connection references for all actions
- GOV-006: Managed solutions for non-dev targets
- GOV-007: Channel scope consistency
- GOV-008: DLP policies configured
- GOV-009: No secrets in generated artifacts
- GOV-010: Consistent prefix in solution.xml

### Readiness dashboard

Markdown + JSON dashboard with:
- Conversation test cases per topic/action
- Smoke tests for post-import validation
- Readiness score and pass/fail gate

## Tool Adapters

All adapters follow a `plan()`/`apply()` pattern:

| Adapter | Purpose |
|---------|---------|
| `autobot.tools.pac_cli` | Power Platform CLI operations |
| `autobot.tools.dataverse_api` | Dataverse Web API lookups |
| `autobot.tools.sharepoint_check` | SharePoint URL validation |
| `autobot.tools.teams_publish` | Teams/M365 Copilot channel steps |

## Extending the Schema

1. Add new fields to `autobot/specs/agent_spec.schema.json`.
2. Update agents that consume those fields.
3. Add governance rules in `security.py` if the field has compliance implications.
4. Update `agent_spec.example.json` with realistic values.

## Running Tests

```bash
python -m pytest tests/agents/cs_builder/ -v \
  --override-ini="asyncio_mode=auto" \
  -c tests/agents/cs_builder/pytest.ini \
  --confcutdir=tests/agents/cs_builder
```

## Governance Rules

The `SecurityGovernanceAdvisorAgent` enforces enterprise ALM best practices:

- **Work in solutions**: All customizations must be in a named solution with a custom publisher.
- **Use environment variables**: Environment-specific settings (URLs, connection strings) must be externalized.
- **Managed outside dev**: Non-dev environments must receive managed solution exports.
- **Connection references**: Actions must use connection references, not hardcoded credentials.
- **No secrets in source**: The agent scans specs and artifacts for embedded secrets.
