"""Power Automate cloud flow definition builder.

Generates flow definitions that conform to the Azure Logic Apps / Power Automate
workflow definition schema.  The generated JSON can be imported directly into
Power Automate, Azure Logic Apps, or registered as Copilot Studio plugin actions
without modification.

Schema reference:
    https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#

Usage::

    builder = FlowDefinitionBuilder(prefix="contit", solution_name="ContosoIT")
    flow = builder.build_http_request_flow("CreateTicket", method="POST")
    meta = FlowMetadata(
        name="contit_CreateTicket_flow",
        display_name="Create Ticket",
        flow_type="http_request",
        definition=flow,
    )
    print(meta.to_json())
"""

from __future__ import annotations

import json
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Schema constant
# ---------------------------------------------------------------------------

LOGIC_APPS_SCHEMA = (
    "https://schema.management.azure.com/providers/"
    "Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#"
)

# ---------------------------------------------------------------------------
# Well-known connector operations catalog
# ---------------------------------------------------------------------------

CONNECTOR_OPERATIONS: dict[str, dict[str, Any]] = {
    "ServiceNow": {
        "api_id": "/providers/Microsoft.PowerApps/apis/shared_service-now",
        "operations": {
            "create_record": {"operationId": "PostRecord_V2", "method": "POST"},
            "get_record": {"operationId": "GetRecord_V2", "method": "GET"},
            "update_record": {"operationId": "PatchRecord_V2", "method": "PATCH"},
            "list_records": {"operationId": "GetRecords_V2", "method": "GET"},
        },
    },
    "SharePoint": {
        "api_id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
        "operations": {
            "get_item": {"operationId": "GetItem", "method": "GET"},
            "create_item": {"operationId": "PostItem", "method": "POST"},
            "update_item": {"operationId": "PatchItem", "method": "PATCH"},
            "get_items": {"operationId": "GetItems", "method": "GET"},
            "delete_item": {"operationId": "DeleteItem", "method": "DELETE"},
        },
    },
    "SQL": {
        "api_id": "/providers/Microsoft.PowerApps/apis/shared_sql",
        "operations": {
            "execute_query": {"operationId": "ExecutePassThroughNativeQuery_V2", "method": "POST"},
            "get_row": {"operationId": "GetItem_V2", "method": "GET"},
            "get_rows": {"operationId": "GetItems_V2", "method": "GET"},
            "insert_row": {"operationId": "PostItem_V2", "method": "POST"},
            "update_row": {"operationId": "PatchItem_V2", "method": "PATCH"},
            "delete_row": {"operationId": "DeleteItem_V2", "method": "DELETE"},
        },
    },
    "Teams": {
        "api_id": "/providers/Microsoft.PowerApps/apis/shared_teams",
        "operations": {
            "send_message": {"operationId": "PostMessageToChannel", "method": "POST"},
            "get_message": {"operationId": "GetMessage", "method": "GET"},
            "list_channels": {"operationId": "GetChannelsForGroup", "method": "GET"},
            "reply_to_message": {"operationId": "ReplyToMessage", "method": "POST"},
        },
    },
    "Office365Users": {
        "api_id": "/providers/Microsoft.PowerApps/apis/shared_office365users",
        "operations": {
            "get_user_profile": {"operationId": "UserProfile_V2", "method": "GET"},
            "search_users": {"operationId": "SearchUser_V2", "method": "GET"},
            "get_manager": {"operationId": "Manager_V2", "method": "GET"},
            "get_direct_reports": {"operationId": "DirectReports_V2", "method": "GET"},
        },
    },
    "HTTP": {
        "api_id": "/providers/Microsoft.PowerApps/apis/shared_http",
        "operations": {
            "invoke": {"operationId": "InvokeHttp", "method": "POST"},
        },
    },
}

# ---------------------------------------------------------------------------
# Default connector-to-operation mapping for build_flow_from_spec_action
# ---------------------------------------------------------------------------

_CONNECTOR_DEFAULT_OPS: dict[str, str] = {
    "ServiceNow": "create_record",
    "SharePoint": "get_item",
    "SQL": "execute_query",
    "Teams": "send_message",
    "Office365Users": "get_user_profile",
    "HTTP": "invoke",
}

# ---------------------------------------------------------------------------
# Expression helpers
# ---------------------------------------------------------------------------


def connection_ref_expression(ref_name: str) -> str:
    """Return the Power Automate expression for a connection reference.

    Power Platform resolves connection references at runtime via the
    ``$connections`` parameter bag.

    Example::

        >>> connection_ref_expression("contit_ServiceNow_cr")
        "@parameters('$connections')['contit_ServiceNow_cr']['connectionId']"
    """
    return f"@parameters('$connections')['{ref_name}']['connectionId']"


def env_var_expression(var_name: str) -> str:
    """Return the Power Automate expression for an environment variable.

    Environment variables are surfaced in the workflow as parameters whose
    names correspond to the schema name of the variable definition.

    Example::

        >>> env_var_expression("contit_BaseUrl")
        "@parameters('contit_BaseUrl')"
    """
    return f"@parameters('{var_name}')"


# ---------------------------------------------------------------------------
# Helper: deterministic metadata ID
# ---------------------------------------------------------------------------

def _operation_metadata_id() -> str:
    """Generate a deterministic-format GUID for operationMetadataId.

    Power Automate uses this field to track action metadata.  We generate a
    UUID-4 to guarantee uniqueness within a flow definition.
    """
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# FlowDefinitionBuilder
# ---------------------------------------------------------------------------


class FlowDefinitionBuilder:
    """Builds Power Automate cloud flow definitions adhering to the Logic Apps schema.

    Generates flows that are compatible with:

    - Power Automate cloud flows
    - Azure Logic Apps
    - Copilot Studio plugin actions

    Args:
        prefix: Publisher prefix used for naming (e.g. ``"contit"``).
        solution_name: Logical name of the owning solution.
    """

    def __init__(self, prefix: str, solution_name: str) -> None:
        self.prefix = prefix
        self.solution_name = solution_name

    # -- triggers -----------------------------------------------------------

    def build_http_request_flow(
        self,
        action_name: str,
        *,
        method: str = "POST",
        url_env_var: str = "",
        request_schema: dict[str, Any] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a flow triggered by an HTTP request (for Copilot Studio actions).

        The resulting definition uses a ``manual`` trigger of ``kind: Http`` and
        ``type: Request``.  An HTTP action invokes the target endpoint and a
        Response action returns the result to the caller.

        Args:
            action_name: Logical name of the action (used in display names).
            method: HTTP method for the downstream call (``GET``, ``POST``, etc.).
            url_env_var: Environment variable schema name that holds the base URL.
                         If empty a placeholder URL is used.
            request_schema: JSON Schema for the trigger request body.
            response_schema: JSON Schema for the Response action body.

        Returns:
            Complete workflow definition ``dict`` conforming to *LOGIC_APPS_SCHEMA*.
        """
        trigger_schema = request_schema or {
            "type": "object",
            "properties": {},
        }

        url_value: str
        if url_env_var:
            url_value = env_var_expression(url_env_var)
        else:
            url_value = f"https://placeholder.example.com/api/{action_name}"

        cr_name = f"{self.prefix}_HTTP_cr"

        # -- actions --------------------------------------------------------
        http_action = self.build_connector_action(
            connector="HTTP",
            operation="invoke",
            inputs={
                "method": method,
                "uri": url_value,
                "body": "@triggerBody()",
            },
            connection_reference=cr_name,
        )

        response_action = self.build_response_action(
            "Send_Response",
            status_code=200,
            body={"result": f"@body('{self.prefix}_{action_name}_Invoke_HTTP')"},
            schema=response_schema,
        )
        # Wire runAfter chain
        response_action["runAfter"] = {
            f"{self.prefix}_{action_name}_Invoke_HTTP": ["Succeeded"],
        }

        actions: dict[str, Any] = {
            f"{self.prefix}_{action_name}_Invoke_HTTP": http_action,
            "Send_Response": response_action,
        }

        return self._wrap_definition(
            triggers=self._http_request_trigger(trigger_schema, method),
            actions=actions,
        )

    def build_scheduled_flow(
        self,
        action_name: str,
        *,
        frequency: str = "Day",
        interval: int = 1,
    ) -> dict[str, Any]:
        """Build a flow with a recurrence (scheduled) trigger.

        Args:
            action_name: Logical name of the action.
            frequency: Recurrence frequency (``Minute``, ``Hour``, ``Day``,
                       ``Week``, ``Month``).
            interval: Number of *frequency* units between runs.

        Returns:
            Complete workflow definition ``dict``.
        """
        triggers: dict[str, Any] = {
            "Recurrence": {
                "type": "Recurrence",
                "recurrence": {
                    "frequency": frequency,
                    "interval": interval,
                },
            },
        }

        compose_action = self.build_compose_action(
            f"{self.prefix}_{action_name}_Placeholder",
            inputs={"status": "scheduled_run", "action": action_name},
        )

        actions: dict[str, Any] = {
            f"{self.prefix}_{action_name}_Placeholder": compose_action,
        }

        return self._wrap_definition(triggers=triggers, actions=actions)

    def build_automated_flow(
        self,
        action_name: str,
        *,
        trigger_connector: str,
        trigger_action: str,
    ) -> dict[str, Any]:
        """Build an automated flow triggered by a connector event.

        Args:
            action_name: Logical name of the action.
            trigger_connector: Connector name (must be in *CONNECTOR_OPERATIONS*
                               or a valid custom connector name).
            trigger_action: Operation ID of the trigger action on the connector.

        Returns:
            Complete workflow definition ``dict``.
        """
        catalog = CONNECTOR_OPERATIONS.get(trigger_connector)
        api_id = (
            catalog["api_id"]
            if catalog
            else f"/providers/Microsoft.PowerApps/apis/shared_{trigger_connector.lower()}"
        )

        cr_name = f"{self.prefix}_{trigger_connector}_cr"

        triggers: dict[str, Any] = {
            f"When_{trigger_action}": {
                "type": "OpenApiConnectionNotification",
                "inputs": {
                    "host": {
                        "connectionName": connection_ref_expression(cr_name),
                        "operationId": trigger_action,
                        "apiId": api_id,
                    },
                    "parameters": {},
                },
                "metadata": {
                    "operationMetadataId": _operation_metadata_id(),
                },
            },
        }

        compose_action = self.build_compose_action(
            f"{self.prefix}_{action_name}_Process",
            inputs={"trigger_body": "@triggerBody()"},
        )

        actions: dict[str, Any] = {
            f"{self.prefix}_{action_name}_Process": compose_action,
        }

        return self._wrap_definition(triggers=triggers, actions=actions)

    # -- individual actions -------------------------------------------------

    def build_connector_action(
        self,
        connector: str,
        operation: str,
        *,
        inputs: dict[str, Any] | None = None,
        connection_reference: str = "",
    ) -> dict[str, Any]:
        """Build a single connector action step.

        The action uses ``type: OpenApiConnection`` with the full Power Platform
        host block including ``connectionName``, ``operationId``, and ``apiId``.

        Args:
            connector: Connector name (key in *CONNECTOR_OPERATIONS*).
            operation: Operation key (e.g. ``"create_record"``).
            inputs: Additional parameters passed to the connector operation.
            connection_reference: Override connection reference logical name.
                                 Defaults to ``<prefix>_<connector>_cr``.

        Returns:
            Action definition ``dict`` (not a full workflow, just the action).
        """
        catalog = CONNECTOR_OPERATIONS.get(connector)
        if catalog:
            api_id = catalog["api_id"]
            op_entry = catalog["operations"].get(operation, {})
            operation_id = op_entry.get("operationId", operation)
        else:
            api_id = f"/providers/Microsoft.PowerApps/apis/shared_{connector.lower()}"
            operation_id = operation

        cr_name = connection_reference or f"{self.prefix}_{connector}_cr"

        action: dict[str, Any] = {
            "type": "OpenApiConnection",
            "inputs": {
                "host": {
                    "connectionName": connection_ref_expression(cr_name),
                    "operationId": operation_id,
                    "apiId": api_id,
                },
                "parameters": inputs or {},
            },
            "runAfter": {},
            "metadata": {
                "operationMetadataId": _operation_metadata_id(),
            },
        }
        return action

    def build_compose_action(self, name: str, inputs: Any) -> dict[str, Any]:
        """Build a Compose action for data transformation.

        Args:
            name: Display name (ignored for structure; caller uses it as key).
            inputs: Any JSON-serialisable value to store in the Compose step.

        Returns:
            Action definition ``dict``.
        """
        return {
            "type": "Compose",
            "inputs": inputs,
            "runAfter": {},
        }

    def build_condition_action(
        self,
        name: str,
        expression: str,
        *,
        if_true_actions: dict[str, Any] | None = None,
        if_false_actions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a conditional branching action.

        The *expression* should be a Power Automate expression string such as
        ``"@equals(triggerBody()?['status'], 'open')"``.

        Args:
            name: Display name (caller uses it as the action key).
            expression: Power Automate expression evaluating to ``true``/``false``.
            if_true_actions: Actions to run when the condition is true.
            if_false_actions: Actions to run when the condition is false.

        Returns:
            Action definition ``dict``.
        """
        return {
            "type": "If",
            "expression": expression,
            "actions": if_true_actions or {},
            "else": {
                "actions": if_false_actions or {},
            },
            "runAfter": {},
        }

    def build_response_action(
        self,
        name: str,
        *,
        status_code: int = 200,
        body: dict[str, Any] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an HTTP Response action (for request-triggered flows).

        Args:
            name: Display name (caller uses it as the action key).
            status_code: HTTP status code to return.
            body: Response body expression or literal.
            schema: JSON Schema describing the response body.

        Returns:
            Action definition ``dict``.
        """
        action: dict[str, Any] = {
            "type": "Response",
            "kind": "Http",
            "inputs": {
                "statusCode": status_code,
                "body": body or {},
            },
            "runAfter": {},
        }
        if schema:
            action["inputs"]["schema"] = schema
        return action

    # -- high-level: spec action -> complete flow ---------------------------

    def build_flow_from_spec_action(
        self,
        action: dict[str, Any],
        prefix: str,
    ) -> dict[str, Any]:
        """Build a complete flow definition from an agent_spec action entry.

        Maps the action's connector to appropriate trigger/action patterns:

        - **HTTP** connector: HTTP request trigger + HTTP action + response
        - **ServiceNow**: HTTP request trigger + ServiceNow create/update + response
        - **SQL**: HTTP request trigger + SQL execute query + response
        - **SharePoint**: HTTP request trigger + SharePoint get/create item + response
        - **Teams**: HTTP request trigger + Teams send message + response
        - **Others**: HTTP request trigger + generic OpenApiConnection + response

        Args:
            action: A single action entry from the agent spec, expected to
                    contain at minimum ``"name"`` and ``"connector"`` keys.
            prefix: Publisher prefix for naming.

        Returns:
            Complete workflow definition ``dict``.
        """
        action_name: str = action.get("name", "UnnamedAction")
        connector: str = action.get("connector", "HTTP")
        action_inputs: dict[str, Any] = action.get("inputs", {})

        # Determine the default operation for this connector
        default_op = _CONNECTOR_DEFAULT_OPS.get(connector, "invoke")

        # For HTTP connector, delegate to the purpose-built HTTP flow builder
        if connector == "HTTP":
            url_env_var = f"{prefix}_{action_name}_BaseUrl"
            method = action_inputs.get("method", "POST")
            return self.build_http_request_flow(
                action_name,
                method=method,
                url_env_var=url_env_var,
                request_schema=action_inputs.get("request_schema"),
                response_schema=action_inputs.get("response_schema"),
            )

        # -- Non-HTTP connectors: request trigger + connector action + response
        cr_name = f"{prefix}_{connector}_cr"

        trigger_schema: dict[str, Any] = action_inputs.get("request_schema", {
            "type": "object",
            "properties": {},
        })

        method = action_inputs.get("method", "POST")

        # Build the connector action step
        connector_step = self.build_connector_action(
            connector=connector,
            operation=default_op,
            inputs=action_inputs.get("parameters", {}),
            connection_reference=cr_name,
        )

        connector_step_name = f"{prefix}_{action_name}_{default_op}"

        # Build the response step
        response_action = self.build_response_action(
            "Send_Response",
            status_code=200,
            body={"result": f"@body('{connector_step_name}')"},
            schema=action_inputs.get("response_schema"),
        )
        response_action["runAfter"] = {
            connector_step_name: ["Succeeded"],
        }

        actions: dict[str, Any] = {
            connector_step_name: connector_step,
            "Send_Response": response_action,
        }

        return self._wrap_definition(
            triggers=self._http_request_trigger(trigger_schema, method),
            actions=actions,
        )

    # -- private helpers ----------------------------------------------------

    def _wrap_definition(
        self,
        *,
        triggers: dict[str, Any],
        actions: dict[str, Any],
    ) -> dict[str, Any]:
        """Wrap triggers and actions in a full workflow definition envelope."""
        return {
            "$schema": LOGIC_APPS_SCHEMA,
            "contentVersion": "1.0.0.0",
            "triggers": triggers,
            "actions": actions,
            "outputs": {},
        }

    def _http_request_trigger(
        self,
        schema: dict[str, Any],
        method: str = "POST",
    ) -> dict[str, Any]:
        """Return a manual HTTP request trigger block."""
        return {
            "manual": {
                "type": "Request",
                "kind": "Http",
                "inputs": {
                    "method": method,
                    "schema": schema,
                },
            },
        }


# ---------------------------------------------------------------------------
# FlowMetadata
# ---------------------------------------------------------------------------


class FlowMetadata:
    """Metadata for a generated flow, used for solution component registration.

    Instances track all the information needed to register the flow as a
    component inside a Power Platform solution and to serialise the flow
    definition to disk.

    Args:
        name: Logical (schema) name of the flow.
        display_name: Human-readable display name.
        flow_type: One of ``"http_request"``, ``"scheduled"``, ``"automated"``.
        definition: The complete workflow definition ``dict``.
    """

    COMPONENT_TYPE_CODE = 29  # Workflow component type in solution XML

    def __init__(
        self,
        name: str,
        display_name: str,
        flow_type: str,
        definition: dict[str, Any],
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.flow_type = flow_type
        self.definition = definition
        self.workflow_id = str(uuid.uuid4())

    def to_solution_component(self) -> dict[str, Any]:
        """Return the solution component registration entry.

        The returned ``dict`` contains the fields expected by the Power Platform
        solution packager for workflow components.
        """
        return {
            "type": self.COMPONENT_TYPE_CODE,
            "schemaName": self.name,
            "displayName": self.display_name,
            "workflowId": self.workflow_id,
            "flowType": self.flow_type,
            "category": 5,  # 5 = Modern Flow
            "description": f"Auto-generated {self.flow_type} flow: {self.display_name}",
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the flow definition to a JSON string.

        Args:
            indent: Number of spaces for JSON indentation.

        Returns:
            JSON string of the complete workflow definition.
        """
        return json.dumps(self.definition, indent=indent)

    def __repr__(self) -> str:
        return (
            f"FlowMetadata(name={self.name!r}, display_name={self.display_name!r}, "
            f"flow_type={self.flow_type!r})"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "CONNECTOR_OPERATIONS",
    "FlowDefinitionBuilder",
    "FlowMetadata",
    "LOGIC_APPS_SCHEMA",
    "connection_ref_expression",
    "env_var_expression",
]
