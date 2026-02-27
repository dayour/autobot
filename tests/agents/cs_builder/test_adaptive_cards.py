"""Tests for autobot.tools.adaptive_cards."""

from __future__ import annotations

import json
import pytest

from autobot.tools.adaptive_cards import (
    ADAPTIVE_CARD_SCHEMA,
    ADAPTIVE_CARD_VERSION,
    ACTION_TYPES,
    AdaptiveCardBuilder,
    AdaptiveCardMetadata,
    AdaptiveCardTemplate,
    AdaptiveCardValidator,
    CARD_SIZE_LIMIT_BYTES,
    ELEMENT_CATALOG,
    conditional_expression,
    data_binding,
)


# ---------------------------------------------------------------------------
# Expression helpers
# ---------------------------------------------------------------------------

class TestExpressionHelpers:
    def test_data_binding(self):
        assert data_binding("user.name") == "${user.name}"

    def test_data_binding_nested(self):
        assert data_binding("order.items[0].price") == "${order.items[0].price}"

    def test_conditional_expression(self):
        result = conditional_expression("score > 80", "Pass", "Fail")
        assert result == "${if(score > 80, 'Pass', 'Fail')}"


# ---------------------------------------------------------------------------
# Element catalog
# ---------------------------------------------------------------------------

class TestElementCatalog:
    def test_catalog_has_all_element_types(self):
        expected = {
            "TextBlock", "Image", "ColumnSet", "Column", "Container",
            "FactSet", "ActionSet", "Table", "Input.Text", "Input.Number",
            "Input.Date", "Input.Toggle", "Input.ChoiceSet", "RichTextBlock",
            "ImageSet",
        }
        assert expected == set(ELEMENT_CATALOG.keys())

    def test_each_element_has_type_field(self):
        for name, entry in ELEMENT_CATALOG.items():
            assert entry["type"] == name

    def test_each_element_has_properties(self):
        for name, entry in ELEMENT_CATALOG.items():
            assert isinstance(entry["properties"], list)
            assert len(entry["properties"]) > 0

    def test_action_types_catalog(self):
        expected = {
            "Action.OpenUrl", "Action.Submit", "Action.ShowCard",
            "Action.Execute", "Action.ToggleVisibility",
        }
        assert expected == set(ACTION_TYPES.keys())


# ---------------------------------------------------------------------------
# AdaptiveCardBuilder
# ---------------------------------------------------------------------------

class TestAdaptiveCardBuilder:
    def test_build_empty_card(self):
        card = AdaptiveCardBuilder().build()
        assert card["type"] == "AdaptiveCard"
        assert card["$schema"] == ADAPTIVE_CARD_SCHEMA
        assert card["version"] == ADAPTIVE_CARD_VERSION
        assert card["body"] == []
        assert card["actions"] == []

    def test_custom_version(self):
        card = AdaptiveCardBuilder(version="1.3").build()
        assert card["version"] == "1.3"

    def test_add_text_block(self):
        card = AdaptiveCardBuilder().add_text_block("Hello").build()
        assert len(card["body"]) == 1
        assert card["body"][0]["type"] == "TextBlock"
        assert card["body"][0]["text"] == "Hello"

    def test_add_text_block_with_options(self):
        card = (
            AdaptiveCardBuilder()
            .add_text_block(
                "Title",
                size="Large",
                weight="Bolder",
                color="Good",
                wrap=True,
                is_subtle=True,
                separator=True,
                spacing="Medium",
            )
            .build()
        )
        tb = card["body"][0]
        assert tb["size"] == "Large"
        assert tb["weight"] == "Bolder"
        assert tb["color"] == "Good"
        assert tb["wrap"] is True
        assert tb["isSubtle"] is True
        assert tb["separator"] is True
        assert tb["spacing"] == "Medium"

    def test_add_image(self):
        card = AdaptiveCardBuilder().add_image("https://example.com/img.png", alt_text="Logo").build()
        img = card["body"][0]
        assert img["type"] == "Image"
        assert img["url"] == "https://example.com/img.png"
        assert img["altText"] == "Logo"

    def test_add_image_with_dimensions(self):
        card = (
            AdaptiveCardBuilder()
            .add_image("https://example.com/img.png", size="Medium", style="Person", width="100px", height="100px")
            .build()
        )
        img = card["body"][0]
        assert img["size"] == "Medium"
        assert img["style"] == "Person"
        assert img["width"] == "100px"

    def test_add_column_set(self):
        col1 = AdaptiveCardBuilder.build_column([{"type": "TextBlock", "text": "A"}], width="1")
        col2 = AdaptiveCardBuilder.build_column([{"type": "TextBlock", "text": "B"}], width="1")
        card = AdaptiveCardBuilder().add_column_set([col1, col2]).build()
        cs = card["body"][0]
        assert cs["type"] == "ColumnSet"
        assert len(cs["columns"]) == 2

    def test_build_column_helper(self):
        col = AdaptiveCardBuilder.build_column([{"type": "TextBlock", "text": "X"}], width="stretch")
        assert col["type"] == "Column"
        assert col["width"] == "stretch"
        assert len(col["items"]) == 1

    def test_add_container(self):
        card = (
            AdaptiveCardBuilder()
            .add_container([{"type": "TextBlock", "text": "Inside"}], style="emphasis", bleed=True)
            .build()
        )
        c = card["body"][0]
        assert c["type"] == "Container"
        assert c["style"] == "emphasis"
        assert c["bleed"] is True

    def test_add_fact_set(self):
        card = (
            AdaptiveCardBuilder()
            .add_fact_set([("Name", "Alice"), ("Role", "Admin")])
            .build()
        )
        fs = card["body"][0]
        assert fs["type"] == "FactSet"
        assert len(fs["facts"]) == 2
        assert fs["facts"][0] == {"title": "Name", "value": "Alice"}

    def test_add_table(self):
        card = (
            AdaptiveCardBuilder()
            .add_table(
                [{"width": 1}, {"width": 1}],
                [["A", "B"], ["C", "D"]],
                first_row_as_header=True,
                show_grid_lines=False,
            )
            .build()
        )
        table = card["body"][0]
        assert table["type"] == "Table"
        assert len(table["rows"]) == 2
        assert table["firstRowAsHeader"] is True
        assert table["showGridLines"] is False

    def test_add_action_set(self):
        card = (
            AdaptiveCardBuilder()
            .add_action_set([{"type": "Action.Submit", "title": "Go"}])
            .build()
        )
        assert card["body"][0]["type"] == "ActionSet"

    def test_add_input_text(self):
        card = (
            AdaptiveCardBuilder()
            .add_input_text("name", placeholder="Enter name", label="Name", is_multiline=False, is_required=True)
            .build()
        )
        inp = card["body"][0]
        assert inp["type"] == "Input.Text"
        assert inp["id"] == "name"
        assert inp["isRequired"] is True

    def test_add_input_choice_set(self):
        choices = [{"title": "Red", "value": "red"}, {"title": "Blue", "value": "blue"}]
        card = (
            AdaptiveCardBuilder()
            .add_input_choice_set("color", choices, label="Pick color", is_multi_select=True)
            .build()
        )
        inp = card["body"][0]
        assert inp["type"] == "Input.ChoiceSet"
        assert len(inp["choices"]) == 2
        assert inp["isMultiSelect"] is True

    def test_add_input_toggle(self):
        card = (
            AdaptiveCardBuilder()
            .add_input_toggle("agree", "I agree", value_on="yes", value_off="no")
            .build()
        )
        inp = card["body"][0]
        assert inp["type"] == "Input.Toggle"
        assert inp["valueOn"] == "yes"

    def test_add_action_open_url(self):
        card = AdaptiveCardBuilder().add_action_open_url("Docs", "https://example.com").build()
        assert len(card["actions"]) == 1
        assert card["actions"][0]["type"] == "Action.OpenUrl"
        assert card["actions"][0]["url"] == "https://example.com"

    def test_add_action_submit(self):
        card = AdaptiveCardBuilder().add_action_submit("Send", {"key": "val"}, style="positive").build()
        action = card["actions"][0]
        assert action["type"] == "Action.Submit"
        assert action["data"] == {"key": "val"}
        assert action["style"] == "positive"

    def test_add_action_show_card(self):
        inner = AdaptiveCardBuilder().add_text_block("Inner").build()
        card = AdaptiveCardBuilder().add_action_show_card("Details", inner).build()
        action = card["actions"][0]
        assert action["type"] == "Action.ShowCard"
        assert action["card"]["body"][0]["text"] == "Inner"

    def test_add_action_execute(self):
        card = AdaptiveCardBuilder().add_action_execute("Run", "doStuff", {"x": 1}).build()
        action = card["actions"][0]
        assert action["type"] == "Action.Execute"
        assert action["verb"] == "doStuff"

    def test_add_raw_element(self):
        card = AdaptiveCardBuilder().add_raw_element({"type": "Custom", "data": "x"}).build()
        assert card["body"][0]["type"] == "Custom"

    def test_add_raw_action(self):
        card = AdaptiveCardBuilder().add_raw_action({"type": "Action.Custom", "title": "X"}).build()
        assert card["actions"][0]["type"] == "Action.Custom"

    def test_chaining(self):
        card = (
            AdaptiveCardBuilder()
            .add_text_block("A")
            .add_text_block("B")
            .add_action_open_url("C", "https://x.com")
            .build()
        )
        assert len(card["body"]) == 2
        assert len(card["actions"]) == 1

    def test_reset(self):
        builder = AdaptiveCardBuilder().add_text_block("A").add_action_open_url("B", "https://x.com")
        builder.reset()
        card = builder.build()
        assert card["body"] == []
        assert card["actions"] == []

    def test_to_json(self):
        j = AdaptiveCardBuilder().add_text_block("Hello").to_json()
        parsed = json.loads(j)
        assert parsed["type"] == "AdaptiveCard"
        assert parsed["body"][0]["text"] == "Hello"


# ---------------------------------------------------------------------------
# AdaptiveCardTemplate
# ---------------------------------------------------------------------------

class TestAdaptiveCardTemplate:
    def test_welcome_card(self):
        card = AdaptiveCardTemplate.welcome_card(
            "IT Bot",
            "Helps with IT stuff",
            [{"name": "Password"}, {"name": "VPN"}],
        )
        assert card["type"] == "AdaptiveCard"
        assert any(el.get("text") == "IT Bot" for el in card["body"])
        # Topic buttons in action set
        action_sets = [el for el in card["body"] if el.get("type") == "ActionSet"]
        assert len(action_sets) == 1
        assert len(action_sets[0]["actions"]) == 2

    def test_welcome_card_no_topics(self):
        card = AdaptiveCardTemplate.welcome_card("Bot", "A bot", [])
        assert card["type"] == "AdaptiveCard"
        action_sets = [el for el in card["body"] if el.get("type") == "ActionSet"]
        assert len(action_sets) == 0

    def test_governance_report_card_passed(self):
        report = {
            "agent_name": "TestBot",
            "passed": True,
            "summary": {"pass": 5, "warn": 1, "fail": 0},
            "findings": [
                {"rule_id": "GOV-001", "severity": "pass", "message": "No secrets"},
            ],
        }
        card = AdaptiveCardTemplate.governance_report_card(report)
        assert card["type"] == "AdaptiveCard"
        facts = [el for el in card["body"] if el.get("type") == "FactSet"]
        assert len(facts) >= 1

    def test_governance_report_card_failed(self):
        report = {
            "agent_name": "BadBot",
            "passed": False,
            "summary": {"pass": 2, "warn": 0, "fail": 3},
            "findings": [
                {"rule_id": "GOV-001", "severity": "fail", "message": "Secret found"},
            ],
        }
        card = AdaptiveCardTemplate.governance_report_card(report)
        assert card["type"] == "AdaptiveCard"

    def test_readiness_dashboard_card(self):
        suite = {
            "agent_name": "TestBot",
            "readiness_score": 0.85,
            "total_tests": 10,
            "coverage": {
                "overall_coverage": 0.9,
                "topic_coverage": {"t1": True, "t2": True},
                "action_coverage": {"a1": True},
                "gaps": [],
            },
        }
        card = AdaptiveCardTemplate.readiness_dashboard_card(suite)
        assert card["type"] == "AdaptiveCard"

    def test_readiness_dashboard_card_with_gaps(self):
        suite = {
            "agent_name": "TestBot",
            "readiness_score": 0.5,
            "total_tests": 3,
            "coverage": {
                "overall_coverage": 0.5,
                "topic_coverage": {"t1": True, "t2": False},
                "action_coverage": {},
                "gaps": ["Untested topics: t2"],
            },
        }
        card = AdaptiveCardTemplate.readiness_dashboard_card(suite)
        text_blocks = [el for el in card["body"] if el.get("type") == "TextBlock"]
        gap_blocks = [tb for tb in text_blocks if "Untested" in tb.get("text", "")]
        assert len(gap_blocks) == 1

    def test_publish_approval_card(self):
        checklist = {
            "ready": False,
            "blocking_items": ["No DLP configured"],
            "checklist": [
                {"item": "Auth configured", "status": "passed", "priority": "critical"},
                {"item": "DLP configured", "status": "blocked", "priority": "high"},
            ],
        }
        card = AdaptiveCardTemplate.publish_approval_card("MyBot", ["teams"], checklist)
        assert card["type"] == "AdaptiveCard"
        assert len(card["actions"]) == 2  # Approve + Reject

    def test_publish_approval_card_ready(self):
        checklist = {"ready": True, "blocking_items": [], "checklist": []}
        card = AdaptiveCardTemplate.publish_approval_card("MyBot", ["teams", "web"], checklist)
        assert card["type"] == "AdaptiveCard"

    def test_knowledge_source_status_card(self):
        sources = [
            {"type": "sharepoint", "reference": "https://contoso.sharepoint.com/sites/IT", "valid": True},
            {"type": "web", "reference": "https://docs.example.com", "valid": False},
        ]
        card = AdaptiveCardTemplate.knowledge_source_status_card(sources)
        assert card["type"] == "AdaptiveCard"
        fact_sets = [el for el in card["body"] if el.get("type") == "FactSet"]
        assert len(fact_sets) == 2

    def test_knowledge_source_status_card_empty(self):
        card = AdaptiveCardTemplate.knowledge_source_status_card([])
        assert card["type"] == "AdaptiveCard"

    def test_error_card(self):
        card = AdaptiveCardTemplate.error_card("Error", "Something broke", "Stack trace...")
        assert card["type"] == "AdaptiveCard"
        texts = [el.get("text", "") for el in card["body"] if el.get("type") == "TextBlock"]
        assert "Error" in texts
        assert "Something broke" in texts

    def test_error_card_with_retry(self):
        card = AdaptiveCardTemplate.error_card(
            "Timeout", "Request timed out",
            retry_action={"title": "Retry", "data": {"action": "retry"}},
        )
        assert len(card["actions"]) == 1

    def test_action_confirmation_card(self):
        card = AdaptiveCardTemplate.action_confirmation_card(
            "CreateTicket", "ServiceNow", {"success": True, "message": "Ticket created"},
        )
        assert card["type"] == "AdaptiveCard"

    def test_pipeline_progress_card(self):
        checkpoints = [
            {"stage": "scaffold", "status": "completed", "duration_s": 0.1},
            {"stage": "ingest", "status": "completed", "duration_s": 0.2},
            {"stage": "security", "status": "running"},
        ]
        card = AdaptiveCardTemplate.pipeline_progress_card(checkpoints, "TestBot")
        assert card["type"] == "AdaptiveCard"

    def test_pipeline_summary_card(self):
        results = {
            "agent_name": "TestBot",
            "success": True,
            "dry_run": True,
            "duration_s": 1.5,
            "checkpoints": [
                {"stage": "scaffold", "status": "completed"},
                {"stage": "security", "status": "completed"},
            ],
        }
        card = AdaptiveCardTemplate.pipeline_summary_card(results)
        assert card["type"] == "AdaptiveCard"

    def test_pipeline_summary_card_blocked(self):
        results = {
            "agent_name": "TestBot",
            "success": False,
            "dry_run": True,
            "duration_s": 0.8,
            "blocked": True,
            "checkpoints": [
                {"stage": "scaffold", "status": "completed"},
                {"stage": "security", "status": "failed"},
            ],
        }
        card = AdaptiveCardTemplate.pipeline_summary_card(results)
        texts = [el.get("text", "") for el in card["body"] if el.get("type") == "TextBlock"]
        assert any("blocked" in t.lower() for t in texts)


# ---------------------------------------------------------------------------
# AdaptiveCardValidator
# ---------------------------------------------------------------------------

class TestAdaptiveCardValidator:
    def test_valid_card(self):
        card = AdaptiveCardBuilder().add_text_block("Hello", wrap=True).build()
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_invalid_card_missing_type(self):
        card = {"$schema": ADAPTIVE_CARD_SCHEMA, "version": "1.5", "body": []}
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is False
        assert any("type" in e for e in result["errors"])

    def test_invalid_card_missing_fields(self):
        card = {"type": "AdaptiveCard"}
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is False
        assert len(result["errors"]) >= 2  # missing schema, version, body

    def test_oversized_card(self):
        builder = AdaptiveCardBuilder()
        # Add enough text blocks to exceed 28KB
        for i in range(500):
            builder.add_text_block("X" * 100, wrap=True)
        card = builder.build()
        result = AdaptiveCardValidator.validate(card)
        assert result["valid"] is False
        assert any("size" in e.lower() for e in result["errors"])

    def test_accessibility_warnings(self):
        card = (
            AdaptiveCardBuilder()
            .add_image("https://example.com/img.png")  # no alt text
            .add_text_block("No wrap")  # no wrap
            .build()
        )
        result = AdaptiveCardValidator.validate(card)
        assert len(result["warnings"]) >= 2


# ---------------------------------------------------------------------------
# AdaptiveCardMetadata
# ---------------------------------------------------------------------------

class TestAdaptiveCardMetadata:
    def test_metadata_creation(self):
        card = AdaptiveCardBuilder().add_text_block("Hello").build()
        meta = AdaptiveCardMetadata("contit_welcome", "Welcome Card", "welcome", card)
        assert meta.name == "contit_welcome"
        assert meta.display_name == "Welcome Card"
        assert meta.card_type == "welcome"

    def test_card_id_is_uuid(self):
        card = AdaptiveCardBuilder().build()
        meta = AdaptiveCardMetadata("test", "Test", "test", card)
        # UUID format: 8-4-4-4-12 hex
        parts = meta.card_id.split("-")
        assert len(parts) == 5

    def test_to_solution_component(self):
        card = AdaptiveCardBuilder().build()
        meta = AdaptiveCardMetadata("contit_welcome", "Welcome", "welcome", card)
        comp = meta.to_solution_component()
        assert comp["type"] == AdaptiveCardMetadata.COMPONENT_TYPE_CODE
        assert comp["schemaName"] == "contit_welcome"
        assert comp["cardId"] == meta.card_id

    def test_to_json(self):
        card = AdaptiveCardBuilder().add_text_block("Hello").build()
        meta = AdaptiveCardMetadata("test", "Test", "test", card)
        j = json.loads(meta.to_json())
        assert j["type"] == "AdaptiveCard"
        assert j["body"][0]["text"] == "Hello"
