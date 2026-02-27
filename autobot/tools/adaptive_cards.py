"""Adaptive Cards builder, templates, and validator.

Generates Adaptive Card JSON payloads that render natively in Microsoft Teams,
Outlook, and web channels.  Follows the same builder-pattern conventions as
:mod:`autobot.tools.flow_definitions`.

Schema reference:
    http://adaptivecards.io/schemas/adaptive-card.json

Usage::

    card = (
        AdaptiveCardBuilder()
        .add_text_block("Hello!", size="Large", weight="Bolder")
        .add_fact_set([("Status", "Active"), ("Score", "92%")])
        .add_action_open_url("Docs", "https://example.com")
        .build()
    )
    print(AdaptiveCardValidator.validate(card))
"""

from __future__ import annotations

import json
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADAPTIVE_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ADAPTIVE_CARD_VERSION = "1.5"
CARD_SIZE_LIMIT_BYTES = 28 * 1024  # Teams limit

ELEMENT_CATALOG: dict[str, dict[str, Any]] = {
    "TextBlock": {"type": "TextBlock", "properties": ["text", "size", "weight", "color", "wrap", "isSubtle", "style", "separator", "spacing"]},
    "Image": {"type": "Image", "properties": ["url", "altText", "size", "style", "width", "height"]},
    "ColumnSet": {"type": "ColumnSet", "properties": ["columns"]},
    "Column": {"type": "Column", "properties": ["items", "width"]},
    "Container": {"type": "Container", "properties": ["items", "style", "bleed"]},
    "FactSet": {"type": "FactSet", "properties": ["facts"]},
    "ActionSet": {"type": "ActionSet", "properties": ["actions"]},
    "Table": {"type": "Table", "properties": ["columns", "rows", "firstRowAsHeader", "showGridLines"]},
    "Input.Text": {"type": "Input.Text", "properties": ["id", "placeholder", "label", "isMultiline", "isRequired"]},
    "Input.Number": {"type": "Input.Number", "properties": ["id", "placeholder", "label", "min", "max"]},
    "Input.Date": {"type": "Input.Date", "properties": ["id", "label", "min", "max"]},
    "Input.Toggle": {"type": "Input.Toggle", "properties": ["id", "title", "label", "valueOn", "valueOff"]},
    "Input.ChoiceSet": {"type": "Input.ChoiceSet", "properties": ["id", "choices", "label", "isMultiSelect", "style"]},
    "RichTextBlock": {"type": "RichTextBlock", "properties": ["inlines"]},
    "ImageSet": {"type": "ImageSet", "properties": ["images", "imageSize"]},
}

ACTION_TYPES: dict[str, dict[str, Any]] = {
    "Action.OpenUrl": {"type": "Action.OpenUrl", "properties": ["title", "url", "style"]},
    "Action.Submit": {"type": "Action.Submit", "properties": ["title", "data", "style"]},
    "Action.ShowCard": {"type": "Action.ShowCard", "properties": ["title", "card", "style"]},
    "Action.Execute": {"type": "Action.Execute", "properties": ["title", "verb", "data", "style"]},
    "Action.ToggleVisibility": {"type": "Action.ToggleVisibility", "properties": ["title", "targetElements"]},
}

# ---------------------------------------------------------------------------
# Expression helpers
# ---------------------------------------------------------------------------


def data_binding(prop: str) -> str:
    """Return an Adaptive Cards data-binding expression.

    Example::

        >>> data_binding("user.name")
        '${user.name}'
    """
    return f"${{{prop}}}"


def conditional_expression(condition: str, if_true: str, if_false: str) -> str:
    """Return an Adaptive Cards conditional expression.

    Example::

        >>> conditional_expression("score > 80", "Pass", "Fail")
        "${if(score > 80, 'Pass', 'Fail')}"
    """
    return f"${{if({condition}, '{if_true}', '{if_false}')}}"


# ---------------------------------------------------------------------------
# AdaptiveCardBuilder
# ---------------------------------------------------------------------------


class AdaptiveCardBuilder:
    """Fluent builder for Adaptive Card JSON payloads.

    All element and action methods return ``self`` to enable chaining.

    Args:
        version: Adaptive Card schema version (default ``"1.5"``).
    """

    def __init__(self, *, version: str = ADAPTIVE_CARD_VERSION) -> None:
        self._version = version
        self._body: list[dict[str, Any]] = []
        self._actions: list[dict[str, Any]] = []

    # -- element methods ----------------------------------------------------

    def add_text_block(
        self,
        text: str,
        *,
        size: str | None = None,
        weight: str | None = None,
        color: str | None = None,
        wrap: bool | None = None,
        is_subtle: bool | None = None,
        style: str | None = None,
        separator: bool | None = None,
        spacing: str | None = None,
    ) -> AdaptiveCardBuilder:
        el: dict[str, Any] = {"type": "TextBlock", "text": text}
        if size is not None:
            el["size"] = size
        if weight is not None:
            el["weight"] = weight
        if color is not None:
            el["color"] = color
        if wrap is not None:
            el["wrap"] = wrap
        if is_subtle is not None:
            el["isSubtle"] = is_subtle
        if style is not None:
            el["style"] = style
        if separator is not None:
            el["separator"] = separator
        if spacing is not None:
            el["spacing"] = spacing
        self._body.append(el)
        return self

    def add_image(
        self,
        url: str,
        *,
        alt_text: str | None = None,
        size: str | None = None,
        style: str | None = None,
        width: str | None = None,
        height: str | None = None,
    ) -> AdaptiveCardBuilder:
        el: dict[str, Any] = {"type": "Image", "url": url}
        if alt_text is not None:
            el["altText"] = alt_text
        if size is not None:
            el["size"] = size
        if style is not None:
            el["style"] = style
        if width is not None:
            el["width"] = width
        if height is not None:
            el["height"] = height
        self._body.append(el)
        return self

    def add_column_set(self, columns: list[dict[str, Any]]) -> AdaptiveCardBuilder:
        self._body.append({"type": "ColumnSet", "columns": columns})
        return self

    @staticmethod
    def build_column(items: list[dict[str, Any]], *, width: str = "auto") -> dict[str, Any]:
        return {"type": "Column", "width": width, "items": items}

    def add_container(
        self,
        items: list[dict[str, Any]],
        *,
        style: str | None = None,
        bleed: bool | None = None,
    ) -> AdaptiveCardBuilder:
        el: dict[str, Any] = {"type": "Container", "items": items}
        if style is not None:
            el["style"] = style
        if bleed is not None:
            el["bleed"] = bleed
        self._body.append(el)
        return self

    def add_fact_set(self, facts: list[tuple[str, str]]) -> AdaptiveCardBuilder:
        self._body.append({
            "type": "FactSet",
            "facts": [{"title": t, "value": v} for t, v in facts],
        })
        return self

    def add_table(
        self,
        columns: list[dict[str, Any]],
        rows: list[list[str]],
        *,
        first_row_as_header: bool = True,
        show_grid_lines: bool = True,
    ) -> AdaptiveCardBuilder:
        table_rows = []
        for row in rows:
            table_rows.append({
                "type": "TableRow",
                "cells": [{"type": "TableCell", "items": [{"type": "TextBlock", "text": cell, "wrap": True}]} for cell in row],
            })
        self._body.append({
            "type": "Table",
            "columns": columns,
            "rows": table_rows,
            "firstRowAsHeader": first_row_as_header,
            "showGridLines": show_grid_lines,
        })
        return self

    def add_action_set(self, actions: list[dict[str, Any]]) -> AdaptiveCardBuilder:
        self._body.append({"type": "ActionSet", "actions": actions})
        return self

    def add_input_text(
        self,
        id: str,
        *,
        placeholder: str | None = None,
        label: str | None = None,
        is_multiline: bool | None = None,
        is_required: bool | None = None,
    ) -> AdaptiveCardBuilder:
        el: dict[str, Any] = {"type": "Input.Text", "id": id}
        if placeholder is not None:
            el["placeholder"] = placeholder
        if label is not None:
            el["label"] = label
        if is_multiline is not None:
            el["isMultiline"] = is_multiline
        if is_required is not None:
            el["isRequired"] = is_required
        self._body.append(el)
        return self

    def add_input_choice_set(
        self,
        id: str,
        choices: list[dict[str, str]],
        *,
        label: str | None = None,
        is_multi_select: bool | None = None,
        style: str | None = None,
    ) -> AdaptiveCardBuilder:
        el: dict[str, Any] = {"type": "Input.ChoiceSet", "id": id, "choices": choices}
        if label is not None:
            el["label"] = label
        if is_multi_select is not None:
            el["isMultiSelect"] = is_multi_select
        if style is not None:
            el["style"] = style
        self._body.append(el)
        return self

    def add_input_toggle(
        self,
        id: str,
        title: str,
        *,
        label: str | None = None,
        value_on: str | None = None,
        value_off: str | None = None,
    ) -> AdaptiveCardBuilder:
        el: dict[str, Any] = {"type": "Input.Toggle", "id": id, "title": title}
        if label is not None:
            el["label"] = label
        if value_on is not None:
            el["valueOn"] = value_on
        if value_off is not None:
            el["valueOff"] = value_off
        self._body.append(el)
        return self

    # -- action methods -----------------------------------------------------

    def add_action_open_url(
        self,
        title: str,
        url: str,
        *,
        style: str | None = None,
    ) -> AdaptiveCardBuilder:
        action: dict[str, Any] = {"type": "Action.OpenUrl", "title": title, "url": url}
        if style is not None:
            action["style"] = style
        self._actions.append(action)
        return self

    def add_action_submit(
        self,
        title: str,
        data: dict[str, Any] | None = None,
        *,
        style: str | None = None,
    ) -> AdaptiveCardBuilder:
        action: dict[str, Any] = {"type": "Action.Submit", "title": title}
        if data is not None:
            action["data"] = data
        if style is not None:
            action["style"] = style
        self._actions.append(action)
        return self

    def add_action_show_card(
        self,
        title: str,
        card: dict[str, Any],
        *,
        style: str | None = None,
    ) -> AdaptiveCardBuilder:
        action: dict[str, Any] = {"type": "Action.ShowCard", "title": title, "card": card}
        if style is not None:
            action["style"] = style
        self._actions.append(action)
        return self

    def add_action_execute(
        self,
        title: str,
        verb: str,
        data: dict[str, Any] | None = None,
        *,
        style: str | None = None,
    ) -> AdaptiveCardBuilder:
        action: dict[str, Any] = {"type": "Action.Execute", "title": title, "verb": verb}
        if data is not None:
            action["data"] = data
        if style is not None:
            action["style"] = style
        self._actions.append(action)
        return self

    # -- utility ------------------------------------------------------------

    def add_raw_element(self, element: dict[str, Any]) -> AdaptiveCardBuilder:
        self._body.append(element)
        return self

    def add_raw_action(self, action: dict[str, Any]) -> AdaptiveCardBuilder:
        self._actions.append(action)
        return self

    def build(self) -> dict[str, Any]:
        """Return the complete Adaptive Card dict."""
        return {
            "type": "AdaptiveCard",
            "$schema": ADAPTIVE_CARD_SCHEMA,
            "version": self._version,
            "body": list(self._body),
            "actions": list(self._actions),
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the card to a JSON string."""
        return json.dumps(self.build(), indent=indent)

    def reset(self) -> AdaptiveCardBuilder:
        """Clear all elements and actions."""
        self._body.clear()
        self._actions.clear()
        return self


# ---------------------------------------------------------------------------
# AdaptiveCardTemplate
# ---------------------------------------------------------------------------


class AdaptiveCardTemplate:
    """Pre-built card templates for common CS Builder scenarios."""

    @staticmethod
    def welcome_card(
        agent_name: str,
        description: str,
        topics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Agent introduction with topic buttons."""
        builder = (
            AdaptiveCardBuilder()
            .add_text_block(agent_name, size="Large", weight="Bolder", wrap=True)
            .add_text_block(description, wrap=True, is_subtle=True)
        )
        if topics:
            builder.add_text_block("I can help with:", weight="Bolder", spacing="Medium")
            actions = []
            for topic in topics:
                actions.append({
                    "type": "Action.Submit",
                    "title": topic.get("name", "Topic"),
                    "data": {"action": "select_topic", "topic": topic.get("name", "")},
                })
            builder.add_action_set(actions)
        return builder.build()

    @staticmethod
    def governance_report_card(report_dict: dict[str, Any]) -> dict[str, Any]:
        """Security findings with pass/warn/fail summary."""
        summary = report_dict.get("summary", {})
        passed = report_dict.get("passed", False)
        status_color = "Good" if passed else "Attention"

        builder = (
            AdaptiveCardBuilder()
            .add_text_block("Governance Report", size="Large", weight="Bolder")
            .add_text_block(
                f"Agent: {report_dict.get('agent_name', 'Unknown')}",
                is_subtle=True,
                wrap=True,
            )
            .add_fact_set([
                ("Status", "PASSED" if passed else "FAILED"),
                ("Pass", str(summary.get("pass", 0))),
                ("Warn", str(summary.get("warn", 0))),
                ("Fail", str(summary.get("fail", 0))),
            ])
        )

        # Findings
        findings = report_dict.get("findings", [])
        if findings:
            builder.add_text_block("Findings", size="Medium", weight="Bolder", separator=True)
            for finding in findings:
                severity = finding.get("severity", "")
                icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}.get(severity, "?")
                builder.add_text_block(
                    f"[{icon}] {finding.get('rule_id', '')} — {finding.get('message', '')}",
                    wrap=True,
                    color="Good" if severity == "pass" else "Attention" if severity == "warn" else "Warning",
                )

        return builder.build()

    @staticmethod
    def readiness_dashboard_card(suite_dict: dict[str, Any]) -> dict[str, Any]:
        """Test coverage and readiness score."""
        score = suite_dict.get("readiness_score", 0)
        total = suite_dict.get("total_tests", 0)
        status = "PASSED" if score >= 0.8 else "FAILED"

        builder = (
            AdaptiveCardBuilder()
            .add_text_block("Readiness Dashboard", size="Large", weight="Bolder")
            .add_text_block(
                f"Agent: {suite_dict.get('agent_name', 'Unknown')}",
                is_subtle=True,
                wrap=True,
            )
            .add_fact_set([
                ("Score", f"{score:.0%}"),
                ("Status", status),
                ("Total Tests", str(total)),
            ])
        )

        # Coverage
        coverage = suite_dict.get("coverage", {})
        if coverage:
            builder.add_text_block("Coverage", size="Medium", weight="Bolder", separator=True)
            builder.add_fact_set([
                ("Overall", f"{coverage.get('overall_coverage', 0):.0%}"),
                ("Topics", f"{sum(coverage.get('topic_coverage', {}).values())}/{len(coverage.get('topic_coverage', {}))}"),
                ("Actions", f"{sum(coverage.get('action_coverage', {}).values())}/{len(coverage.get('action_coverage', {}))}"),
            ])

            gaps = coverage.get("gaps", [])
            if gaps:
                builder.add_text_block("Gaps", size="Medium", weight="Bolder", separator=True)
                for gap in gaps:
                    builder.add_text_block(f"- {gap}", wrap=True)

        return builder.build()

    @staticmethod
    def publish_approval_card(
        agent_name: str,
        channels: list[str],
        checklist: dict[str, Any],
    ) -> dict[str, Any]:
        """Admin approve/reject workflow."""
        builder = (
            AdaptiveCardBuilder()
            .add_text_block("Publish Approval", size="Large", weight="Bolder")
            .add_text_block(f"Agent: {agent_name}", is_subtle=True, wrap=True)
            .add_fact_set([
                ("Channels", ", ".join(channels)),
                ("Ready", "Yes" if checklist.get("ready") else "No"),
            ])
        )

        # Blocking items
        blocking = checklist.get("blocking_items", [])
        if blocking:
            builder.add_text_block("Blocking Items", size="Medium", weight="Bolder", separator=True, color="Attention")
            for item in blocking:
                builder.add_text_block(f"- {item}", wrap=True)

        # Checklist summary
        items = checklist.get("checklist", [])
        if items:
            builder.add_text_block("Checklist", size="Medium", weight="Bolder", separator=True)
            facts = []
            for item in items[:8]:
                status_icon = {"passed": "OK", "pending": "...", "blocked": "X"}.get(item.get("status", ""), "?")
                facts.append((f"[{status_icon}] {item.get('item', '')}", item.get("priority", "")))
            builder.add_fact_set(facts)

        # Approve/Reject actions
        builder.add_action_submit("Approve", {"action": "approve_publish", "agent": agent_name}, style="positive")
        builder.add_action_submit("Reject", {"action": "reject_publish", "agent": agent_name}, style="destructive")

        return builder.build()

    @staticmethod
    def knowledge_source_status_card(sources: list[dict[str, Any]]) -> dict[str, Any]:
        """SharePoint reachability per-source."""
        builder = (
            AdaptiveCardBuilder()
            .add_text_block("Knowledge Source Status", size="Large", weight="Bolder")
        )

        if not sources:
            builder.add_text_block("No knowledge sources configured.", is_subtle=True, wrap=True)
            return builder.build()

        for src in sources:
            valid = src.get("valid", False)
            icon = "OK" if valid else "FAIL"
            builder.add_fact_set([
                ("Source", src.get("reference", src.get("url", "unknown"))),
                ("Type", src.get("type", "unknown")),
                ("Status", f"[{icon}] {'Reachable' if valid else 'Unreachable'}"),
            ])

        return builder.build()

    @staticmethod
    def error_card(
        title: str,
        message: str,
        details: str = "",
        retry_action: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Structured error display."""
        builder = (
            AdaptiveCardBuilder()
            .add_text_block(title, size="Large", weight="Bolder", color="Attention")
            .add_text_block(message, wrap=True)
        )
        if details:
            builder.add_text_block(details, wrap=True, is_subtle=True, spacing="Small")
        if retry_action:
            builder.add_action_submit(
                retry_action.get("title", "Retry"),
                retry_action.get("data", {"action": "retry"}),
            )
        return builder.build()

    @staticmethod
    def action_confirmation_card(
        action_name: str,
        connector: str,
        result_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Connector action results."""
        success = result_summary.get("success", False)
        builder = (
            AdaptiveCardBuilder()
            .add_text_block("Action Result", size="Large", weight="Bolder")
            .add_fact_set([
                ("Action", action_name),
                ("Connector", connector),
                ("Status", "Success" if success else "Failed"),
            ])
        )
        msg = result_summary.get("message", "")
        if msg:
            builder.add_text_block(msg, wrap=True, is_subtle=True)
        return builder.build()

    @staticmethod
    def pipeline_progress_card(
        checkpoints: list[dict[str, Any]],
        agent_name: str,
    ) -> dict[str, Any]:
        """Swarm checkpoint status."""
        builder = (
            AdaptiveCardBuilder()
            .add_text_block("Pipeline Progress", size="Large", weight="Bolder")
            .add_text_block(f"Agent: {agent_name}", is_subtle=True, wrap=True)
        )

        for cp in checkpoints:
            status = cp.get("status", "unknown")
            icon = {"completed": "OK", "running": "...", "failed": "FAIL"}.get(status, "?")
            stage = cp.get("stage", "unknown")
            duration = cp.get("duration_s", "")
            dur_str = f" ({duration}s)" if duration else ""
            builder.add_text_block(f"[{icon}] {stage}{dur_str}", wrap=True)

        return builder.build()

    @staticmethod
    def pipeline_summary_card(results: dict[str, Any]) -> dict[str, Any]:
        """Final pipeline summary."""
        success = results.get("success", False)
        builder = (
            AdaptiveCardBuilder()
            .add_text_block("Pipeline Summary", size="Large", weight="Bolder")
            .add_text_block(
                f"Agent: {results.get('agent_name', 'Unknown')}",
                is_subtle=True,
                wrap=True,
            )
            .add_fact_set([
                ("Status", "SUCCESS" if success else "FAILED"),
                ("Dry Run", str(results.get("dry_run", True))),
                ("Duration", f"{results.get('duration_s', 0)}s"),
            ])
        )

        # Stage count
        checkpoints = results.get("checkpoints", [])
        completed = sum(1 for c in checkpoints if c.get("status") == "completed")
        failed = sum(1 for c in checkpoints if c.get("status") == "failed")
        builder.add_fact_set([
            ("Stages Completed", str(completed)),
            ("Stages Failed", str(failed)),
        ])

        if results.get("blocked"):
            builder.add_text_block(
                "Pipeline blocked by governance gate.",
                color="Attention",
                weight="Bolder",
                wrap=True,
            )

        return builder.build()


# ---------------------------------------------------------------------------
# AdaptiveCardValidator
# ---------------------------------------------------------------------------


class AdaptiveCardValidator:
    """Validates Adaptive Card payloads against schema and platform limits."""

    _VALID_ELEMENT_TYPES = set(ELEMENT_CATALOG.keys())
    _VALID_ACTION_TYPES = set(ACTION_TYPES.keys())

    @classmethod
    def validate(cls, card: dict[str, Any]) -> dict[str, Any]:
        """Validate a card dict.

        Returns:
            Dict with ``valid``, ``errors``, and ``warnings`` keys.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Required fields
        if card.get("type") != "AdaptiveCard":
            errors.append("Missing or invalid 'type' — must be 'AdaptiveCard'.")
        if "$schema" not in card:
            errors.append("Missing '$schema' field.")
        if "version" not in card:
            errors.append("Missing 'version' field.")
        if "body" not in card:
            errors.append("Missing 'body' field.")

        # Element type check
        for el in card.get("body", []):
            el_type = el.get("type", "")
            if el_type and el_type not in cls._VALID_ELEMENT_TYPES and not el_type.startswith("Input."):
                warnings.append(f"Unknown element type: {el_type}")

        # Action type check
        for action in card.get("actions", []):
            a_type = action.get("type", "")
            if a_type and a_type not in cls._VALID_ACTION_TYPES:
                warnings.append(f"Unknown action type: {a_type}")

        # Size check
        size_result = cls.check_size(card)
        if not size_result["within_limit"]:
            errors.append(f"Card exceeds Teams size limit: {size_result['size_bytes']} > {CARD_SIZE_LIMIT_BYTES} bytes.")

        # Accessibility check
        accessibility = cls.check_accessibility(card)
        warnings.extend(accessibility.get("warnings", []))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def check_size(card: dict[str, Any]) -> dict[str, Any]:
        """Check JSON byte size against Teams limit."""
        size = len(json.dumps(card).encode("utf-8"))
        return {
            "size_bytes": size,
            "limit_bytes": CARD_SIZE_LIMIT_BYTES,
            "within_limit": size <= CARD_SIZE_LIMIT_BYTES,
        }

    @staticmethod
    def check_accessibility(card: dict[str, Any]) -> dict[str, Any]:
        """Check accessibility best practices."""
        warnings: list[str] = []

        for el in card.get("body", []):
            # Images should have alt text
            if el.get("type") == "Image" and not el.get("altText"):
                warnings.append(f"Image missing altText: {el.get('url', 'unknown')}")
            # TextBlocks should have wrap enabled for readability
            if el.get("type") == "TextBlock" and not el.get("wrap"):
                text_preview = (el.get("text", "") or "")[:30]
                warnings.append(f"TextBlock missing wrap: '{text_preview}...'")

        return {"warnings": warnings}


# ---------------------------------------------------------------------------
# AdaptiveCardMetadata
# ---------------------------------------------------------------------------


class AdaptiveCardMetadata:
    """Metadata for a generated card, mirroring :class:`FlowMetadata`.

    Tracks registration info for Power Platform solution components.

    Args:
        name: Logical (schema) name of the card template.
        display_name: Human-readable display name.
        card_type: Card purpose (e.g. ``"welcome"``, ``"error"``, ``"report"``).
        definition: The complete card dict.
    """

    COMPONENT_TYPE_CODE = 10062  # Custom card component type

    def __init__(
        self,
        name: str,
        display_name: str,
        card_type: str,
        definition: dict[str, Any],
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.card_type = card_type
        self.definition = definition
        self.card_id = str(uuid.uuid4())

    def to_solution_component(self) -> dict[str, Any]:
        """Return the solution component registration entry."""
        return {
            "type": self.COMPONENT_TYPE_CODE,
            "schemaName": self.name,
            "displayName": self.display_name,
            "cardId": self.card_id,
            "cardType": self.card_type,
            "description": f"Adaptive Card template: {self.display_name}",
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the card definition to a JSON string."""
        return json.dumps(self.definition, indent=indent)

    def __repr__(self) -> str:
        return (
            f"AdaptiveCardMetadata(name={self.name!r}, display_name={self.display_name!r}, "
            f"card_type={self.card_type!r})"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "ADAPTIVE_CARD_SCHEMA",
    "ADAPTIVE_CARD_VERSION",
    "ACTION_TYPES",
    "AdaptiveCardBuilder",
    "AdaptiveCardMetadata",
    "AdaptiveCardTemplate",
    "AdaptiveCardValidator",
    "CARD_SIZE_LIMIT_BYTES",
    "ELEMENT_CATALOG",
    "conditional_expression",
    "data_binding",
]
