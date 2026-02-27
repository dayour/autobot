"""Shared base mixin for CS Builder agents with Copilot LLM integration.

Provides a consistent pattern for all agents to:
- Initialize and manage a CopilotLLMClient session
- Send structured prompts with system messages
- Parse JSON or text responses from the LLM
- Handle retries and fallback gracefully
- Produce reasoning traces for observability
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)


class CopilotAgentMixin:
    """Mixin providing LLM interaction capabilities to CS Builder agents.

    Agents using this mixin must set ``self._copilot_config`` (dict) and
    ``self.name`` (str) before calling any mixin methods.

    The mixin lazily creates a ``CopilotLLMClient`` on first LLM call and
    manages its lifecycle through ``start()`` / ``stop()``.
    """

    _llm_client: Any = None
    _llm_session_active: bool = False
    _reasoning_trace: list[dict[str, Any]]

    def _ensure_trace(self) -> None:
        if not hasattr(self, "_reasoning_trace"):
            self._reasoning_trace = []

    async def _start_llm(self) -> None:
        """Initialize the LLM client if not already running."""
        if self._llm_session_active:
            return
        try:
            from autobot.llm_clients.copilot_client import CopilotLLMClient
            self._llm_client = CopilotLLMClient(self._copilot_config)
            await self._llm_client.start()
            self._llm_session_active = True
            logger.debug("[%s] LLM client started (model=%s)", self.name, self._copilot_config.get("model", "gpt-5"))
        except Exception as exc:
            logger.warning("[%s] LLM client unavailable, falling back to structural mode: %s", self.name, exc)
            self._llm_client = None
            self._llm_session_active = False

    async def _stop_llm(self) -> None:
        """Shut down the LLM client."""
        if self._llm_client and self._llm_session_active:
            try:
                await self._llm_client.stop()
            except Exception:
                pass
        self._llm_client = None
        self._llm_session_active = False

    @property
    def llm_available(self) -> bool:
        """Whether the LLM client is ready for inference."""
        return self._llm_session_active and self._llm_client is not None

    async def _llm_complete(
        self,
        *,
        system_message: str,
        user_message: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        expect_json: bool = False,
    ) -> str:
        """Send a prompt to the LLM and return the response text.

        Args:
            system_message: System prompt setting context and instructions.
            user_message: The user/task prompt.
            temperature: Override temperature (uses config default if None).
            max_tokens: Override max tokens.
            expect_json: If True, attempts to extract a JSON block from the
                         response and validates it parses.

        Returns:
            Response text (or extracted JSON string if expect_json=True).

        Raises:
            RuntimeError: If the LLM client is not available.
        """
        if not self.llm_available:
            await self._start_llm()
        if not self.llm_available:
            raise RuntimeError(f"[{self.name}] LLM client not available")

        self._ensure_trace()
        start = time.perf_counter()

        params: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
        }
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        response = await self._llm_client.create_async(params)
        content = response.content
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        # Record reasoning trace
        self._reasoning_trace.append({
            "agent": self.name,
            "system_message_excerpt": system_message[:120],
            "user_message_excerpt": user_message[:200],
            "response_excerpt": content[:300],
            "duration_ms": elapsed_ms,
            "model": response.model,
            "usage": response.usage,
        })

        if expect_json:
            content = self._extract_json(content)

        return content

    async def _llm_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a multi-turn conversation to the LLM.

        Args:
            messages: Full message list [{role, content}, ...].
            temperature: Override temperature.
            max_tokens: Override max tokens.

        Returns:
            Assistant response text.
        """
        if not self.llm_available:
            await self._start_llm()
        if not self.llm_available:
            raise RuntimeError(f"[{self.name}] LLM client not available")

        self._ensure_trace()
        start = time.perf_counter()

        params: dict[str, Any] = {"messages": messages}
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        response = await self._llm_client.create_async(params)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        self._reasoning_trace.append({
            "agent": self.name,
            "turn_count": len(messages),
            "response_excerpt": response.content[:300],
            "duration_ms": elapsed_ms,
            "model": response.model,
        })

        return response.content

    async def _llm_chain_of_thought(
        self,
        *,
        system_message: str,
        problem: str,
        steps: list[str],
        temperature: float = 0.1,
    ) -> list[dict[str, str]]:
        """Execute a multi-step chain-of-thought reasoning sequence.

        Each step builds on prior steps, accumulating context. This is the
        core reasoning pattern for deep analysis tasks.

        Args:
            system_message: System prompt.
            problem: Initial problem statement.
            steps: List of reasoning step instructions.

        Returns:
            List of {step, reasoning} dicts for each completed step.
        """
        self._ensure_trace()
        results: list[dict[str, str]] = []
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": problem},
        ]

        for i, step_instruction in enumerate(steps):
            step_prompt = f"Step {i + 1}/{len(steps)}: {step_instruction}\n\nBuild on your prior analysis. Be thorough and specific."
            messages.append({"role": "user", "content": step_prompt})

            reasoning = await self._llm_chat(messages, temperature=temperature)
            messages.append({"role": "assistant", "content": reasoning})

            results.append({
                "step": step_instruction,
                "step_number": i + 1,
                "reasoning": reasoning,
            })

        return results

    def get_reasoning_trace(self) -> list[dict[str, Any]]:
        """Return the full reasoning trace for observability."""
        self._ensure_trace()
        return list(self._reasoning_trace)

    def clear_reasoning_trace(self) -> None:
        """Clear the reasoning trace."""
        self._reasoning_trace = []

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract a JSON block from LLM response text.

        Handles common LLM response patterns:
        - Pure JSON
        - JSON inside ```json ... ``` fences
        - JSON mixed with explanation text
        """
        # Try direct parse first
        text = text.strip()
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Try fenced code block
        fenced = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        if fenced:
            candidate = fenced.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Try to find first { ... } or [ ... ] block
        for open_ch, close_ch in [("{", "}"), ("[", "]")]:
            start = text.find(open_ch)
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(text)):
                if text[i] == open_ch:
                    depth += 1
                elif text[i] == close_ch:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i + 1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except json.JSONDecodeError:
                            break

        return text


__all__ = ["CopilotAgentMixin"]
