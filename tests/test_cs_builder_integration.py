"""Golden-path integration test for the CS Builder swarm.

Runs the full pipeline from agent_spec.example.json to a local solution
folder, exercising all agents and verifying the output structure.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from autobot.swarms.cs_builder import (
    create_cs_builder_swarm,
    run_build,
    run_scaffold_only,
)


@pytest.fixture
def example_spec_path() -> str:
    """Path to the example agent spec shipped with autobot."""
    p = Path(__file__).resolve().parent.parent / "autobot" / "specs" / "agent_spec.example.json"
    assert p.exists(), f"Example spec not found at {p}"
    return str(p)


@pytest.fixture
def output_dir(tmp_path) -> str:
    return str(tmp_path / "solutions")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCSBuilderSwarm:
    def test_create_swarm_returns_all_agents(self):
        swarm = create_cs_builder_swarm()
        expected_roles = {"planner", "scaffolder", "ingestor", "actions", "security", "publisher", "analytics"}
        assert set(swarm.keys()) == expected_roles

    @pytest.mark.asyncio
    async def test_dry_run_produces_plan(self, example_spec_path, output_dir):
        result = await run_build(
            example_spec_path,
            dry_run=True,
            output_root=output_dir,
        )
        assert result["success"] is True
        assert result["dry_run"] is True
        assert "scaffold_plan" in result
        assert "governance_report" in result
        assert "test_suite" in result
        assert "checkpoints" in result
        assert len(result["checkpoints"]) >= 5  # all stages ran

    @pytest.mark.asyncio
    async def test_dry_run_plan_is_json_serializable(self, example_spec_path, output_dir):
        result = await run_build(
            example_spec_path,
            dry_run=True,
            output_root=output_dir,
        )
        # Must be JSON-serializable for CI artifacts
        serialized = json.dumps(result, default=str)
        assert len(serialized) > 0

    @pytest.mark.asyncio
    async def test_governance_blocks_on_bad_spec(self, tmp_path, output_dir):
        """A bad spec should fail governance and block publish."""
        bad_spec = {
            "name": "Bad Agent",
            "publisher": {"displayName": "", "prefix": ""},
            "environments": {"source": "dev", "targets": ["prod"]},
            "channels": ["teams"],
            "actions": [{"name": "Risky", "connector": "HTTP", "auth": "apiKey"}],
            "security": {},
            "alm": {"managedOutsideDev": False, "useEnvironmentVariables": False},
        }
        spec_file = tmp_path / "bad_spec.json"
        spec_file.write_text(json.dumps(bad_spec))

        result = await run_build(str(spec_file), dry_run=True, output_root=output_dir)
        assert result["success"] is False
        assert result.get("blocked") is True
        assert "governance_report" in result


class TestScaffoldOnly:
    @pytest.mark.asyncio
    async def test_scaffold_dry_run(self, example_spec_path, output_dir):
        result = await run_scaffold_only(
            example_spec_path,
            apply=False,
            output_root=output_dir,
        )
        assert result["dry_run"] is True
        assert result["total_files"] > 0

    @pytest.mark.asyncio
    async def test_scaffold_apply_creates_files(self, example_spec_path, output_dir):
        result = await run_scaffold_only(
            example_spec_path,
            apply=True,
            output_root=output_dir,
        )
        assert result["success"] is True
        assert result["total_files"] > 0
        # Verify key files exist
        sol_dir = Path(result["output_dir"])
        assert (sol_dir / "solution.xml").exists()

    @pytest.mark.asyncio
    async def test_scaffold_solution_xml_content(self, example_spec_path, output_dir):
        result = await run_scaffold_only(
            example_spec_path,
            apply=True,
            output_root=output_dir,
        )
        sol_xml = Path(result["output_dir"]) / "solution.xml"
        content = sol_xml.read_text()
        assert "contit" in content
        assert "Contoso IT" in content

    @pytest.mark.asyncio
    async def test_scaffold_bot_json_content(self, example_spec_path, output_dir):
        result = await run_scaffold_only(
            example_spec_path,
            apply=True,
            output_root=output_dir,
        )
        # Find bot.json
        sol_dir = Path(result["output_dir"])
        bot_files = list(sol_dir.rglob("bot.json"))
        assert len(bot_files) == 1
        bot = json.loads(bot_files[0].read_text())
        assert bot["displayName"] == "Contoso IT Helpdesk Agent"
        assert len(bot["channels"]) == 2
        assert len(bot["topics"]) >= 1
        assert len(bot["knowledgeSources"]) >= 1


class TestFullApplyPipeline:
    @pytest.mark.asyncio
    async def test_full_apply_produces_solution(self, example_spec_path, output_dir):
        result = await run_build(
            example_spec_path,
            dry_run=False,
            output_root=output_dir,
        )
        assert result["success"] is True
        assert result["dry_run"] is False
        assert "scaffold_result" in result
        assert result["scaffold_result"]["total_files"] > 0
