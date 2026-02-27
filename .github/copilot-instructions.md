# Copilot Instructions for autobot

## Project Overview
autobot is an AG2/AutoGen-based autonomous SWE agent swarm framework. It integrates GitHub Copilot SDK as an LLM client, enabling autonomous software engineering workflows.

## Architecture
- `autobot/` - Core package: Copilot LLM client, SWE agent, swarm manager
- `sweagent/` - SWE-agent tools (bash, edit, search) and environment management
- `copilot-sdk-main/` - Copilot SDK integration layer
- `tests/` - Pytest test suite
- `config/` - YAML-based agent configuration
- `docs/` - MkDocs documentation

## Code Style
- Python 3.10+, async-first design, type hints throughout
- Follow AG2 conventions for agent and tool registration
- pre-commit hooks enforced; test with pytest
- See pyproject.toml for dependencies
