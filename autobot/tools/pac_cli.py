"""Thin wrapper around the Power Platform CLI (pac) for solution operations.

This adapter is used by the CS Builder swarm to create, export, and import
Power Platform solutions.  Every public function supports:

    plan(...)   -> dict   # dry-run: returns what *would* happen
    apply(...)  -> dict   # execute: performs the operation

A pluggable ``CommandRunner`` allows tests to swap in mocks without
touching the network or requiring a real PAC CLI installation.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Command runner abstraction
# ---------------------------------------------------------------------------

@runtime_checkable
class CommandRunner(Protocol):
    """Protocol for executing shell commands.  Swap with a mock in tests."""

    async def run(self, args: list[str], *, cwd: str | None = None) -> CommandResult: ...


@dataclass
class CommandResult:
    """Structured result from a CLI invocation."""

    return_code: int
    stdout: str
    stderr: str
    command: str
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.return_code == 0


class SubprocessRunner:
    """Default runner that shells out to the real PAC CLI."""

    def __init__(self, pac_path: str | None = None):
        self._pac = pac_path or shutil.which("pac") or "pac"

    async def run(self, args: list[str], *, cwd: str | None = None) -> CommandResult:
        cmd = [self._pac, *args]
        start = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_b, stderr_b = await proc.communicate()
        elapsed = (time.perf_counter() - start) * 1000
        return CommandResult(
            return_code=proc.returncode or 0,
            stdout=stdout_b.decode(errors="replace"),
            stderr=stderr_b.decode(errors="replace"),
            command=" ".join(cmd),
            duration_ms=round(elapsed, 2),
        )


class MockRunner:
    """In-memory mock runner for tests — records invocations."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.responses: dict[str, CommandResult] = {}

    def set_response(self, key: str, result: CommandResult) -> None:
        self.responses[key] = result

    async def run(self, args: list[str], *, cwd: str | None = None) -> CommandResult:
        self.calls.append(args)
        key = " ".join(args)
        if key in self.responses:
            return self.responses[key]
        return CommandResult(
            return_code=0,
            stdout=json.dumps({"status": "mock_ok"}),
            stderr="",
            command=key,
            duration_ms=1.0,
        )


# ---------------------------------------------------------------------------
# PAC CLI adapter
# ---------------------------------------------------------------------------

class PacCli:
    """High-level async wrapper around ``pac`` CLI commands.

    Args:
        runner: CommandRunner implementation (default: SubprocessRunner).

    Example::

        cli = PacCli()
        plan = await cli.plan_create_solution("ContosoAgent", "contit", "Contoso IT")
        if plan["success"]:
            result = await cli.apply_create_solution(plan)
    """

    def __init__(self, runner: CommandRunner | None = None):
        self._runner = runner or SubprocessRunner()

    # -- solution create ----------------------------------------------------

    async def plan_create_solution(
        self,
        solution_name: str,
        prefix: str,
        publisher_name: str,
        *,
        version: str = "1.0.0.0",
        output_dir: str = "solutions",
    ) -> dict[str, Any]:
        """Dry-run: preview a ``pac solution init`` invocation."""
        target = str(Path(output_dir) / solution_name)
        return {
            "action": "create_solution",
            "dry_run": True,
            "success": True,
            "details": {
                "solution_name": solution_name,
                "prefix": prefix,
                "publisher_name": publisher_name,
                "version": version,
                "output_path": target,
            },
            "commands": [
                f"pac solution init --publisher-name {publisher_name} "
                f"--publisher-prefix {prefix} --outputDirectory {target}",
            ],
        }

    async def apply_create_solution(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute a previously planned ``pac solution init``."""
        d = plan["details"]
        result = await self._runner.run([
            "solution", "init",
            "--publisher-name", d["publisher_name"],
            "--publisher-prefix", d["prefix"],
            "--outputDirectory", d["output_path"],
        ])
        return {
            "action": "create_solution",
            "dry_run": False,
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }

    # -- solution export ----------------------------------------------------

    async def plan_export_solution(
        self,
        solution_path: str,
        *,
        managed: bool = False,
        output_dir: str = "dist",
    ) -> dict[str, Any]:
        """Dry-run: preview a ``pac solution export``."""
        kind = "managed" if managed else "unmanaged"
        return {
            "action": "export_solution",
            "dry_run": True,
            "success": True,
            "details": {
                "solution_path": solution_path,
                "managed": managed,
                "output_dir": output_dir,
            },
            "commands": [
                f"pac solution export --path {solution_path} --{kind} --outputDirectory {output_dir}",
            ],
        }

    async def apply_export_solution(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute a previously planned solution export."""
        d = plan["details"]
        args = [
            "solution", "export",
            "--path", d["solution_path"],
            "--outputDirectory", d["output_dir"],
        ]
        if d["managed"]:
            args.append("--managed")
        result = await self._runner.run(args)
        return {
            "action": "export_solution",
            "dry_run": False,
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }

    # -- solution import ----------------------------------------------------

    async def plan_import_solution(
        self,
        zip_path: str,
        *,
        environment: str | None = None,
    ) -> dict[str, Any]:
        """Dry-run: preview a ``pac solution import``."""
        cmd = f"pac solution import --path {zip_path}"
        if environment:
            cmd += f" --environment {environment}"
        return {
            "action": "import_solution",
            "dry_run": True,
            "success": True,
            "details": {
                "zip_path": zip_path,
                "environment": environment,
            },
            "commands": [cmd],
        }

    async def apply_import_solution(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute a previously planned solution import."""
        d = plan["details"]
        args = ["solution", "import", "--path", d["zip_path"]]
        if d["environment"]:
            args.extend(["--environment", d["environment"]])
        result = await self._runner.run(args)
        return {
            "action": "import_solution",
            "dry_run": False,
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }

    # -- environment variables ----------------------------------------------

    async def plan_add_env_variable(
        self,
        solution_dir: str,
        name: str,
        display_name: str,
        var_type: str = "String",
        default_value: str = "",
    ) -> dict[str, Any]:
        """Dry-run: preview adding an environment variable component."""
        return {
            "action": "add_env_variable",
            "dry_run": True,
            "success": True,
            "details": {
                "solution_dir": solution_dir,
                "name": name,
                "display_name": display_name,
                "type": var_type,
                "default_value": default_value,
            },
            "commands": [
                f"pac solution add-reference --component environmentvariabledefinition "
                f"--name {name} --solutionRootFolder {solution_dir}",
            ],
        }

    async def apply_add_env_variable(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute adding an environment variable to a solution."""
        d = plan["details"]
        result = await self._runner.run([
            "solution", "add-reference",
            "--component", "environmentvariabledefinition",
            "--name", d["name"],
            "--solutionRootFolder", d["solution_dir"],
        ])
        return {
            "action": "add_env_variable",
            "dry_run": False,
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }

    # -- connection references ----------------------------------------------

    async def plan_add_connection_reference(
        self,
        solution_dir: str,
        name: str,
        connector_id: str,
    ) -> dict[str, Any]:
        """Dry-run: preview adding a connection reference."""
        return {
            "action": "add_connection_reference",
            "dry_run": True,
            "success": True,
            "details": {
                "solution_dir": solution_dir,
                "name": name,
                "connector_id": connector_id,
            },
            "commands": [
                f"pac solution add-reference --component connectionreference "
                f"--name {name} --connectorId {connector_id} "
                f"--solutionRootFolder {solution_dir}",
            ],
        }

    async def apply_add_connection_reference(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute adding a connection reference."""
        d = plan["details"]
        result = await self._runner.run([
            "solution", "add-reference",
            "--component", "connectionreference",
            "--name", d["name"],
            "--connectorId", d["connector_id"],
            "--solutionRootFolder", d["solution_dir"],
        ])
        return {
            "action": "add_connection_reference",
            "dry_run": False,
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }


__all__ = [
    "PacCli",
    "CommandRunner",
    "CommandResult",
    "SubprocessRunner",
    "MockRunner",
]
