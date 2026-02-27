"""Copilot Studio Builder Swarm — end-to-end orchestration.

Wires the CS Builder agents in a pipeline with checkpoints and rollbacks:

    Planner -> Scaffolder -> Ingestor -> Actions -> Security -> Publisher -> Analytics

A failing SecurityGovernanceAdvisorAgent **blocks** the Publisher stage.

Usage:

    # High-level one-shot
    from autobot.swarms.cs_builder import run_build
    results = await run_build("specs/agent_spec.example.json", dry_run=True)

    # CLI
    python -m autobot.swarms.cs_builder run specs/agent_spec.example.json --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from autobot.agents.cs_builder.planner import RequirementsPlannerAgent
from autobot.agents.cs_builder.scaffolder import AgentScaffolderAgent
from autobot.agents.cs_builder.ingestor import KnowledgeSourceIngestorAgent
from autobot.agents.cs_builder.actions import ActionsIntegratorAgent
from autobot.agents.cs_builder.security import SecurityGovernanceAdvisorAgent
from autobot.agents.cs_builder.publisher import PublisherAgent
from autobot.agents.cs_builder.analytics import AnalyticsEvaluatorAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkpoint tracking
# ---------------------------------------------------------------------------

class SwarmCheckpoint:
    """Tracks the state of each pipeline stage."""

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []
        self._current: str = ""

    def begin(self, stage: str) -> None:
        self._current = stage
        self.stages.append({
            "stage": stage,
            "status": "running",
            "start_time": time.time(),
        })
        logger.info("Stage [%s] started", stage)

    def complete(self, result: dict[str, Any] | None = None) -> None:
        if self.stages:
            entry = self.stages[-1]
            entry["status"] = "completed"
            entry["duration_s"] = round(time.time() - entry["start_time"], 2)
            entry["result_summary"] = _summarize(result) if result else None
        logger.info("Stage [%s] completed", self._current)

    def fail(self, error: str) -> None:
        if self.stages:
            entry = self.stages[-1]
            entry["status"] = "failed"
            entry["duration_s"] = round(time.time() - entry["start_time"], 2)
            entry["error"] = error
        logger.error("Stage [%s] FAILED: %s", self._current, error)

    def to_dict(self) -> list[dict[str, Any]]:
        return self.stages


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    """Extract a small summary from a result dict."""
    return {
        k: v for k, v in result.items()
        if k in ("success", "action", "dry_run", "total_files", "total_actions",
                  "total_sources", "passed", "readiness_score", "message")
    }


# ---------------------------------------------------------------------------
# Swarm factory
# ---------------------------------------------------------------------------

def create_cs_builder_swarm(
    copilot_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create all CS Builder agents wired for the pipeline.

    Args:
        copilot_config: Shared Copilot SDK configuration for all agents.

    Returns:
        Dictionary with agent instances keyed by role name.
    """
    cfg = copilot_config or {"model": "gpt-5", "temperature": 0.2}
    return {
        "planner": RequirementsPlannerAgent(copilot_config=cfg),
        "scaffolder": AgentScaffolderAgent(copilot_config=cfg),
        "ingestor": KnowledgeSourceIngestorAgent(copilot_config=cfg),
        "actions": ActionsIntegratorAgent(copilot_config=cfg),
        "security": SecurityGovernanceAdvisorAgent(copilot_config=cfg),
        "publisher": PublisherAgent(copilot_config=cfg),
        "analytics": AnalyticsEvaluatorAgent(copilot_config=cfg),
    }


# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

async def run_build(
    spec_path: str,
    *,
    dry_run: bool = True,
    copilot_config: dict[str, Any] | None = None,
    output_root: str = "solutions",
) -> dict[str, Any]:
    """Execute the full CS Builder pipeline.

    Args:
        spec_path: Path to agent_spec.json.
        dry_run: If True, only plan; do not materialize artifacts.
        copilot_config: Shared Copilot SDK config.
        output_root: Root directory for generated solutions.

    Returns:
        Pipeline results with checkpoint log and per-stage outputs.
    """
    start_time = time.time()
    checkpoint = SwarmCheckpoint()
    agents = create_cs_builder_swarm(copilot_config)
    results: dict[str, Any] = {"spec_path": spec_path, "dry_run": dry_run}

    # Load spec
    spec = _load_spec(spec_path)
    results["agent_name"] = spec.get("name", "unknown")

    # Start all agents
    for agent in agents.values():
        await agent.start()

    try:
        # --- Stage 1: Scaffold ---
        checkpoint.begin("scaffold")
        scaffolder: AgentScaffolderAgent = agents["scaffolder"]
        scaffolder._config.output_root = output_root
        scaffold_plan = await scaffolder.plan(spec_path)
        results["scaffold_plan"] = scaffold_plan.to_dict()

        if not dry_run:
            scaffold_result = await scaffolder.apply(scaffold_plan)
            results["scaffold_result"] = scaffold_result
        checkpoint.complete(results.get("scaffold_result") or results["scaffold_plan"])

        # --- Stage 2: Knowledge Ingest ---
        checkpoint.begin("ingest_knowledge")
        ingestor: KnowledgeSourceIngestorAgent = agents["ingestor"]
        ingest_plan = await ingestor.plan(spec)
        results["ingest_plan"] = ingest_plan

        if not dry_run:
            ingest_result = await ingestor.apply(ingest_plan)
            results["ingest_result"] = ingest_result
        checkpoint.complete(results.get("ingest_result") or ingest_plan)

        # --- Stage 3: Actions Integration ---
        checkpoint.begin("integrate_actions")
        actions_agent: ActionsIntegratorAgent = agents["actions"]
        actions_plan = await actions_agent.plan(spec)
        results["actions_plan"] = actions_plan

        if not dry_run:
            actions_result = await actions_agent.apply(actions_plan)
            results["actions_result"] = actions_result
        checkpoint.complete(results.get("actions_result") or actions_plan)

        # --- Stage 4: Security Governance (GATE) ---
        checkpoint.begin("security_governance")
        security: SecurityGovernanceAdvisorAgent = agents["security"]
        report = await security.analyze_spec_dict(spec, spec_path=spec_path)
        results["governance_report"] = report.to_dict()

        if not report.passed:
            checkpoint.fail("Governance check FAILED — publish is blocked.")
            results["blocked"] = True
            results["governance_markdown"] = report.to_markdown()
            # Return early — publisher is blocked
            results["checkpoints"] = checkpoint.to_dict()
            results["duration_s"] = round(time.time() - start_time, 2)
            results["success"] = False
            results.update(_generate_pipeline_cards(results))
            return results

        checkpoint.complete(report.to_dict())

        # --- Stage 5: Publish ---
        checkpoint.begin("publish")
        publisher: PublisherAgent = agents["publisher"]
        publish_plan = await publisher.plan_publish(spec)
        results["publish_plan"] = publish_plan

        if not dry_run:
            publish_result = await publisher.apply_publish(publish_plan)
            results["publish_result"] = publish_result
        checkpoint.complete(results.get("publish_result") or publish_plan)

        # --- Stage 6: Analytics & Readiness ---
        checkpoint.begin("analytics")
        evaluator: AnalyticsEvaluatorAgent = agents["analytics"]
        test_suite = await evaluator.generate_test_suite(spec)
        readiness = await evaluator.evaluate_readiness(test_suite)
        results["test_suite"] = test_suite.to_dict()
        results["readiness"] = readiness
        results["readiness_dashboard"] = test_suite.to_markdown()
        checkpoint.complete(readiness)

    except Exception as e:
        checkpoint.fail(str(e))
        results["error"] = str(e)
        results["success"] = False
    else:
        results["success"] = True
    finally:
        # Stop all agents
        for agent in agents.values():
            await agent.stop()

    results["checkpoints"] = checkpoint.to_dict()
    results["duration_s"] = round(time.time() - start_time, 2)

    # Generate card-based reporting
    results.update(_generate_pipeline_cards(results))

    return results


async def run_scaffold_only(
    spec_path: str,
    *,
    apply: bool = False,
    output_root: str = "solutions",
    copilot_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run only the scaffold stage.

    Args:
        spec_path: Path to agent_spec.json.
        apply: If True, materialize the solution on disk.
        output_root: Root directory for output.
        copilot_config: Copilot SDK configuration.

    Returns:
        Scaffold plan or result.
    """
    from autobot.agents.cs_builder.scaffolder import AgentScaffolderAgent, ScaffolderConfig

    config = ScaffolderConfig(output_root=output_root)
    if copilot_config:
        config.copilot_config = copilot_config

    scaffolder = AgentScaffolderAgent(config=config)
    await scaffolder.start()

    try:
        plan = await scaffolder.plan(spec_path)
        if apply:
            result = await scaffolder.apply(plan)
            return result
        return plan.to_dict()
    finally:
        await scaffolder.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_pipeline_cards(results: dict[str, Any]) -> dict[str, Any]:
    """Generate Adaptive Card representations for pipeline reporting."""
    from autobot.tools.adaptive_cards import AdaptiveCardTemplate

    cards: dict[str, Any] = {}
    agent_name = results.get("agent_name", "Unknown")

    # Pipeline progress card — always generated when checkpoints exist
    checkpoints = results.get("checkpoints", [])
    if checkpoints:
        cards["pipeline_progress_card"] = AdaptiveCardTemplate.pipeline_progress_card(
            checkpoints, agent_name,
        )

    # Pipeline summary card — always generated
    cards["pipeline_summary_card"] = AdaptiveCardTemplate.pipeline_summary_card(results)

    # Governance card — when governance report exists
    gov_report = results.get("governance_report")
    if gov_report:
        cards["governance_card"] = AdaptiveCardTemplate.governance_report_card(gov_report)

    # Readiness card — when test suite exists
    test_suite = results.get("test_suite")
    if test_suite:
        cards["readiness_card"] = AdaptiveCardTemplate.readiness_dashboard_card(test_suite)

    return cards


def _load_spec(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        msg = f"Spec file not found: {path}"
        raise FileNotFoundError(msg)
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for the CS Builder swarm."""
    parser = argparse.ArgumentParser(
        prog="cs_builder",
        description="Copilot Studio Builder Swarm — build agents from spec files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    run_parser = sub.add_parser("run", help="Run the full build pipeline")
    run_parser.add_argument("spec", help="Path to agent_spec.json")
    run_parser.add_argument("--dry-run", action="store_true", default=True, help="Preview only (default)")
    run_parser.add_argument("--apply", action="store_true", help="Materialize artifacts")
    run_parser.add_argument("--output", default="solutions", help="Output root directory")

    # scaffold
    scaffold_parser = sub.add_parser("scaffold", help="Run scaffold stage only")
    scaffold_parser.add_argument("spec", help="Path to agent_spec.json")
    scaffold_parser.add_argument("--apply", action="store_true", help="Materialize solution on disk")
    scaffold_parser.add_argument("--output", default="solutions", help="Output root directory")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.command == "run":
        dry_run = not args.apply
        result = asyncio.run(run_build(args.spec, dry_run=dry_run, output_root=args.output))
    elif args.command == "scaffold":
        result = asyncio.run(run_scaffold_only(args.spec, apply=args.apply, output_root=args.output))
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))

    if not result.get("success", True):
        sys.exit(1)


if __name__ == "__main__":
    main()


__all__ = [
    "create_cs_builder_swarm",
    "run_build",
    "run_scaffold_only",
]
