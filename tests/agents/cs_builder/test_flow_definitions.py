"""Tests for Power Automate flow definition generation."""

from __future__ import annotations

import json
import pytest

from autobot.tools.flow_definitions import (
    CONNECTOR_OPERATIONS,
    FlowDefinitionBuilder,
    FlowMetadata,
    LOGIC_APPS_SCHEMA,
    connection_ref_expression,
    env_var_expression,
)


class TestExpressionHelpers:
    def test_connection_ref_expression(self):
        expr = connection_ref_expression("contit_ServiceNow_cr")
        assert "$connections" in expr
        assert "contit_ServiceNow_cr" in expr
        assert "connectionId" in expr

    def test_env_var_expression(self):
        expr = env_var_expression("contit_BaseUrl")
        assert "contit_BaseUrl" in expr
        assert "@parameters" in expr


class TestConnectorOperations:
    def test_catalog_has_standard_connectors(self):
        for name in ("ServiceNow", "SharePoint", "SQL", "Teams", "Office365Users", "HTTP"):
            assert name in CONNECTOR_OPERATIONS, f"Missing connector: {name}"

    def test_connector_has_api_id(self):
        for name, entry in CONNECTOR_OPERATIONS.items():
            assert "api_id" in entry, f"{name} missing api_id"
            assert entry["api_id"].startswith("/providers/Microsoft.PowerApps/apis/")

    def test_connector_has_operations(self):
        for name, entry in CONNECTOR_OPERATIONS.items():
            assert "operations" in entry, f"{name} missing operations"
            assert len(entry["operations"]) > 0, f"{name} has empty operations"


class TestFlowDefinitionBuilder:
    @pytest.fixture
    def builder(self) -> FlowDefinitionBuilder:
        return FlowDefinitionBuilder(prefix="contit", solution_name="ContosoIT")

    def test_http_request_flow_schema(self, builder):
        flow = builder.build_http_request_flow("CreateTicket")
        assert flow["$schema"] == LOGIC_APPS_SCHEMA
        assert flow["contentVersion"] == "1.0.0.0"

    def test_http_request_flow_trigger(self, builder):
        flow = builder.build_http_request_flow("CreateTicket", method="POST")
        assert "manual" in flow["triggers"]
        trigger = flow["triggers"]["manual"]
        assert trigger["type"] == "Request"
        assert trigger["kind"] == "Http"

    def test_http_request_flow_actions(self, builder):
        flow = builder.build_http_request_flow("CreateTicket")
        assert "Send_Response" in flow["actions"]
        # Should have at least the HTTP invoke and response actions
        assert len(flow["actions"]) >= 2

    def test_http_request_flow_run_after_chain(self, builder):
        flow = builder.build_http_request_flow("CreateTicket")
        response = flow["actions"]["Send_Response"]
        # Response must run after some action
        assert len(response["runAfter"]) > 0

    def test_scheduled_flow(self, builder):
        flow = builder.build_scheduled_flow("DailySync", frequency="Day", interval=1)
        assert flow["$schema"] == LOGIC_APPS_SCHEMA
        assert "Recurrence" in flow["triggers"]
        recurrence = flow["triggers"]["Recurrence"]
        assert recurrence["recurrence"]["frequency"] == "Day"
        assert recurrence["recurrence"]["interval"] == 1

    def test_automated_flow(self, builder):
        flow = builder.build_automated_flow(
            "OnNewTicket",
            trigger_connector="ServiceNow",
            trigger_action="WhenRecordCreated",
        )
        assert flow["$schema"] == LOGIC_APPS_SCHEMA
        # Should have a trigger with OpenApiConnectionNotification type
        trigger_key = list(flow["triggers"].keys())[0]
        trigger = flow["triggers"][trigger_key]
        assert trigger["type"] == "OpenApiConnectionNotification"

    def test_connector_action_type(self, builder):
        action = builder.build_connector_action("ServiceNow", "create_record")
        assert action["type"] == "OpenApiConnection"
        assert "operationMetadataId" in action["metadata"]

    def test_connector_action_host(self, builder):
        action = builder.build_connector_action("ServiceNow", "create_record")
        host = action["inputs"]["host"]
        assert "$connections" in host["connectionName"]
        assert host["operationId"] == "PostRecord_V2"
        assert host["apiId"] == "/providers/Microsoft.PowerApps/apis/shared_service-now"

    def test_connector_action_unknown_connector(self, builder):
        action = builder.build_connector_action("CustomCRM", "do_thing")
        assert action["type"] == "OpenApiConnection"
        assert "shared_customcrm" in action["inputs"]["host"]["apiId"]

    def test_compose_action(self, builder):
        action = builder.build_compose_action("Transform", {"key": "value"})
        assert action["type"] == "Compose"
        assert action["inputs"] == {"key": "value"}

    def test_condition_action(self, builder):
        action = builder.build_condition_action(
            "CheckStatus",
            "@equals(triggerBody()?['status'], 'open')",
            if_true_actions={"DoSomething": {"type": "Compose", "inputs": "yes", "runAfter": {}}},
        )
        assert action["type"] == "If"
        assert "actions" in action
        assert "else" in action

    def test_response_action(self, builder):
        action = builder.build_response_action("Respond", status_code=201, body={"id": 123})
        assert action["type"] == "Response"
        assert action["kind"] == "Http"
        assert action["inputs"]["statusCode"] == 201

    def test_response_action_with_schema(self, builder):
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
        action = builder.build_response_action("Respond", schema=schema)
        assert action["inputs"]["schema"] == schema


class TestBuildFlowFromSpecAction:
    @pytest.fixture
    def builder(self) -> FlowDefinitionBuilder:
        return FlowDefinitionBuilder(prefix="contit", solution_name="ContosoIT")

    def test_http_connector(self, builder):
        action = {"name": "CallAPI", "connector": "HTTP", "inputs": {"method": "GET"}}
        flow = builder.build_flow_from_spec_action(action, "contit")
        assert flow["$schema"] == LOGIC_APPS_SCHEMA
        assert "manual" in flow["triggers"]

    def test_servicenow_connector(self, builder):
        action = {"name": "CreateIncident", "connector": "ServiceNow"}
        flow = builder.build_flow_from_spec_action(action, "contit")
        assert flow["$schema"] == LOGIC_APPS_SCHEMA
        # Should have a ServiceNow connector action
        action_keys = list(flow["actions"].keys())
        sn_action = [k for k in action_keys if "CreateIncident" in k]
        assert len(sn_action) >= 1

    def test_unknown_connector(self, builder):
        action = {"name": "DoStuff", "connector": "CustomCRM"}
        flow = builder.build_flow_from_spec_action(action, "contit")
        assert flow["$schema"] == LOGIC_APPS_SCHEMA

    def test_flow_is_json_serializable(self, builder):
        action = {"name": "Test", "connector": "Teams"}
        flow = builder.build_flow_from_spec_action(action, "contit")
        text = json.dumps(flow, indent=2)
        parsed = json.loads(text)
        assert parsed["$schema"] == LOGIC_APPS_SCHEMA


class TestFlowMetadata:
    def test_to_solution_component(self):
        flow_def = {"$schema": LOGIC_APPS_SCHEMA, "contentVersion": "1.0.0.0"}
        meta = FlowMetadata("contit_flow", "My Flow", "http_request", flow_def)
        comp = meta.to_solution_component()
        assert comp["type"] == 29  # Workflow component type
        assert comp["schemaName"] == "contit_flow"
        assert comp["category"] == 5  # Modern Flow

    def test_to_json(self):
        flow_def = {"$schema": LOGIC_APPS_SCHEMA, "contentVersion": "1.0.0.0"}
        meta = FlowMetadata("contit_flow", "My Flow", "http_request", flow_def)
        text = meta.to_json()
        parsed = json.loads(text)
        assert parsed["$schema"] == LOGIC_APPS_SCHEMA

    def test_workflow_id_is_uuid(self):
        import uuid
        flow_def = {"$schema": LOGIC_APPS_SCHEMA}
        meta = FlowMetadata("test", "Test", "scheduled", flow_def)
        uuid.UUID(meta.workflow_id)  # Should not raise
