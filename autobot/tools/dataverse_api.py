"""Extensive Dataverse Web API integration for Power Platform operations.

Provides full CRUD operations, solution component queries, publisher
management, environment variable management, connection reference
queries, metadata introspection, batch operations, and a proper
OData query builder.

All public functions support the plan/apply pattern:
    plan(...)   -> dict   # dry-run: returns what *would* be queried
    apply(...)  -> dict   # execute: performs the HTTP call
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote


# ---------------------------------------------------------------------------
# HTTP client abstraction
# ---------------------------------------------------------------------------

@runtime_checkable
class HttpClient(Protocol):
    """Protocol for HTTP requests.  Swap with a mock in tests."""

    async def get(self, url: str, *, headers: dict[str, str] | None = None) -> HttpResponse: ...
    async def post(self, url: str, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> HttpResponse: ...
    async def patch(self, url: str, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> HttpResponse: ...
    async def delete(self, url: str, *, headers: dict[str, str] | None = None) -> HttpResponse: ...


class HttpResponse:
    """Minimal response wrapper."""

    def __init__(self, status: int, body: dict[str, Any], headers: dict[str, str] | None = None):
        self.status = status
        self.body = body
        self.headers = headers or {}

    @property
    def success(self) -> bool:
        return 200 <= self.status < 300


class MockHttpClient:
    """In-memory mock HTTP client for tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: dict[str, HttpResponse] = {}

    def set_response(self, url_fragment: str, response: HttpResponse) -> None:
        self.responses[url_fragment] = response

    def _find_response(self, url: str) -> HttpResponse:
        for frag, resp in self.responses.items():
            if frag in url:
                return resp
        return HttpResponse(200, {"value": []})

    async def get(self, url: str, *, headers: dict[str, str] | None = None) -> HttpResponse:
        self.calls.append({"method": "GET", "url": url})
        return self._find_response(url)

    async def post(self, url: str, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> HttpResponse:
        self.calls.append({"method": "POST", "url": url, "body": body})
        return self._find_response(url)

    async def patch(self, url: str, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> HttpResponse:
        self.calls.append({"method": "PATCH", "url": url, "body": body})
        return self._find_response(url)

    async def delete(self, url: str, *, headers: dict[str, str] | None = None) -> HttpResponse:
        self.calls.append({"method": "DELETE", "url": url})
        return HttpResponse(204, {})


# ---------------------------------------------------------------------------
# OData query builder
# ---------------------------------------------------------------------------

class ODataQuery:
    """Fluent OData query builder for Dataverse Web API.

    Example::

        query = (ODataQuery("solutions")
            .select("solutionid", "uniquename", "version")
            .filter("uniquename eq 'ContosoAgent'")
            .top(5)
            .order_by("createdon desc"))
        url = query.build("https://org.crm.dynamics.com")
    """

    def __init__(self, entity_set: str):
        self._entity_set = entity_set
        self._select: list[str] = []
        self._filter: str = ""
        self._expand: list[str] = []
        self._order_by: str = ""
        self._top: int | None = None
        self._skip: int | None = None
        self._count: bool = False
        self._entity_id: str = ""

    def select(self, *fields: str) -> ODataQuery:
        self._select.extend(fields)
        return self

    def filter(self, expr: str) -> ODataQuery:
        self._filter = expr
        return self

    def expand(self, *navprops: str) -> ODataQuery:
        self._expand.extend(navprops)
        return self

    def order_by(self, expr: str) -> ODataQuery:
        self._order_by = expr
        return self

    def top(self, n: int) -> ODataQuery:
        self._top = n
        return self

    def skip(self, n: int) -> ODataQuery:
        self._skip = n
        return self

    def count(self) -> ODataQuery:
        self._count = True
        return self

    def by_id(self, entity_id: str) -> ODataQuery:
        self._entity_id = entity_id
        return self

    def build(self, base_url: str) -> str:
        """Build the full URL."""
        base = base_url.rstrip("/")
        path = f"{base}/api/data/v9.2/{self._entity_set}"
        if self._entity_id:
            path += f"({self._entity_id})"

        params: list[str] = []
        if self._select:
            params.append(f"$select={','.join(self._select)}")
        if self._filter:
            params.append(f"$filter={self._filter}")
        if self._expand:
            params.append(f"$expand={','.join(self._expand)}")
        if self._order_by:
            params.append(f"$orderby={self._order_by}")
        if self._top is not None:
            params.append(f"$top={self._top}")
        if self._skip is not None:
            params.append(f"$skip={self._skip}")
        if self._count:
            params.append("$count=true")

        return path + ("?" + "&".join(params) if params else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_set": self._entity_set,
            "entity_id": self._entity_id or None,
            "select": self._select,
            "filter": self._filter or None,
            "expand": self._expand,
            "order_by": self._order_by or None,
            "top": self._top,
            "skip": self._skip,
            "count": self._count,
        }


# ---------------------------------------------------------------------------
# Dataverse API adapter
# ---------------------------------------------------------------------------

class DataverseApi:
    """Extensive async Dataverse Web API client.

    Provides full CRUD, solution management, publisher operations,
    environment variable management, connection reference queries,
    metadata introspection, and batch operations.

    Args:
        environment_url: Dataverse environment URL (e.g. https://org.crm.dynamics.com).
        http_client: Injectable HTTP client (default: MockHttpClient).
        access_token: Bearer token for auth.

    Example::

        api = DataverseApi("https://contoso.crm.dynamics.com", access_token="...")
        plan = await api.plan_query(ODataQuery("solutions").filter("uniquename eq 'Test'").top(5))
        result = await api.apply_query(plan)
    """

    API_VERSION = "v9.2"

    def __init__(
        self,
        environment_url: str = "",
        http_client: HttpClient | None = None,
        access_token: str = "",
    ):
        self._base = environment_url.rstrip("/")
        self._client = http_client or MockHttpClient()
        self._token = access_token

    def _headers(self, *, write: bool = False) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if write:
            h["Content-Type"] = "application/json"
        return h

    def _api_url(self, path: str) -> str:
        return f"{self._base}/api/data/{self.API_VERSION}/{path}"

    # -- generic query (OData builder) --------------------------------------

    async def plan_query(self, query: ODataQuery) -> dict[str, Any]:
        """Dry-run: preview an OData query."""
        url = query.build(self._base)
        return {
            "action": "query",
            "dry_run": True,
            "success": True,
            "details": {
                "url": url,
                "query": query.to_dict(),
            },
        }

    async def apply_query(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute an OData query."""
        url = plan["details"]["url"]
        start = time.perf_counter()
        resp = await self._client.get(url, headers=self._headers())
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "query",
            "dry_run": False,
            "success": resp.success,
            "status_code": resp.status,
            "data": resp.body,
            "duration_ms": round(elapsed, 2),
        }

    # -- entity lookup (legacy convenience) ---------------------------------

    async def plan_lookup_entity(
        self,
        entity_set: str,
        *,
        select: list[str] | None = None,
        filter: str | None = None,
        top: int = 50,
    ) -> dict[str, Any]:
        """Dry-run: preview a Dataverse entity query."""
        q = ODataQuery(entity_set)
        if select:
            q.select(*select)
        if filter:
            q.filter(filter)
        q.top(top)
        return await self.plan_query(q)

    async def apply_lookup(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute a previously planned entity lookup."""
        return await self.apply_query(plan)

    # -- CRUD: Create -------------------------------------------------------

    async def plan_create_record(
        self,
        entity_set: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Dry-run: preview creating a record."""
        url = self._api_url(entity_set)
        return {
            "action": "create_record",
            "dry_run": True,
            "success": True,
            "details": {
                "entity_set": entity_set,
                "url": url,
                "data": data,
            },
        }

    async def apply_create_record(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute record creation."""
        d = plan["details"]
        start = time.perf_counter()
        resp = await self._client.post(d["url"], headers=self._headers(write=True), body=d["data"])
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "create_record",
            "dry_run": False,
            "success": resp.success,
            "status_code": resp.status,
            "data": resp.body,
            "duration_ms": round(elapsed, 2),
        }

    # -- CRUD: Update -------------------------------------------------------

    async def plan_update_record(
        self,
        entity_set: str,
        entity_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Dry-run: preview updating a record."""
        url = self._api_url(f"{entity_set}({entity_id})")
        return {
            "action": "update_record",
            "dry_run": True,
            "success": True,
            "details": {
                "entity_set": entity_set,
                "entity_id": entity_id,
                "url": url,
                "data": data,
            },
        }

    async def apply_update_record(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute record update."""
        d = plan["details"]
        start = time.perf_counter()
        resp = await self._client.patch(d["url"], headers=self._headers(write=True), body=d["data"])
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "update_record",
            "dry_run": False,
            "success": resp.success,
            "status_code": resp.status,
            "data": resp.body,
            "duration_ms": round(elapsed, 2),
        }

    # -- CRUD: Delete -------------------------------------------------------

    async def plan_delete_record(
        self,
        entity_set: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """Dry-run: preview deleting a record."""
        url = self._api_url(f"{entity_set}({entity_id})")
        return {
            "action": "delete_record",
            "dry_run": True,
            "success": True,
            "details": {
                "entity_set": entity_set,
                "entity_id": entity_id,
                "url": url,
            },
        }

    async def apply_delete_record(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute record deletion."""
        d = plan["details"]
        start = time.perf_counter()
        resp = await self._client.delete(d["url"], headers=self._headers())
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "delete_record",
            "dry_run": False,
            "success": resp.success,
            "status_code": resp.status,
            "duration_ms": round(elapsed, 2),
        }

    # -- Solution operations ------------------------------------------------

    async def plan_check_solution_exists(self, unique_name: str) -> dict[str, Any]:
        """Dry-run: check if a solution already exists."""
        q = (ODataQuery("solutions")
             .select("solutionid", "uniquename", "version", "ismanaged", "createdon", "modifiedon")
             .filter(f"uniquename eq '{unique_name}'")
             .top(1))
        return await self.plan_query(q)

    async def plan_list_solution_components(self, solution_id: str) -> dict[str, Any]:
        """Dry-run: list all components in a solution."""
        q = (ODataQuery("solutioncomponents")
             .select("solutioncomponentid", "componenttype", "objectid", "rootcomponentbehavior")
             .filter(f"_solutionid_value eq '{solution_id}'")
             .top(500))
        return await self.plan_query(q)

    async def plan_get_solution_layers(self, solution_id: str) -> dict[str, Any]:
        """Dry-run: get solution layer information."""
        q = (ODataQuery("msdyn_solutionhistories")
             .select("msdyn_name", "msdyn_solutionversion", "msdyn_publishername", "msdyn_ismanaged")
             .filter(f"msdyn_solutionid eq '{solution_id}'")
             .order_by("msdyn_starttime desc")
             .top(20))
        return await self.plan_query(q)

    # -- Publisher operations -----------------------------------------------

    async def plan_lookup_publisher(self, prefix: str) -> dict[str, Any]:
        """Dry-run: look up a publisher by prefix."""
        q = (ODataQuery("publishers")
             .select("publisherid", "customizationprefix", "friendlyname", "uniquename", "description")
             .filter(f"customizationprefix eq '{prefix}'")
             .top(1))
        return await self.plan_query(q)

    async def plan_create_publisher(
        self,
        unique_name: str,
        friendly_name: str,
        prefix: str,
        *,
        description: str = "",
    ) -> dict[str, Any]:
        """Dry-run: create a new publisher."""
        return await self.plan_create_record("publishers", {
            "uniquename": unique_name,
            "friendlyname": friendly_name,
            "customizationprefix": prefix,
            "description": description,
        })

    # -- Environment Variable operations ------------------------------------

    async def plan_list_env_variable_definitions(
        self,
        *,
        solution_id: str | None = None,
        prefix: str | None = None,
    ) -> dict[str, Any]:
        """Dry-run: list environment variable definitions."""
        q = ODataQuery("environmentvariabledefinitions").select(
            "environmentvariabledefinitionid", "schemaname", "displayname",
            "type", "defaultvalue", "description",
        )
        filters: list[str] = []
        if prefix:
            filters.append(f"startswith(schemaname, '{prefix}')")
        if filters:
            q.filter(" and ".join(filters))
        q.top(100)
        return await self.plan_query(q)

    async def plan_get_env_variable_value(self, definition_id: str) -> dict[str, Any]:
        """Dry-run: get the current value of an environment variable."""
        q = (ODataQuery("environmentvariablevalues")
             .select("environmentvariablevalueid", "value", "schemaname")
             .filter(f"_environmentvariabledefinitionid_value eq '{definition_id}'")
             .top(1))
        return await self.plan_query(q)

    async def plan_create_env_variable(
        self,
        schema_name: str,
        display_name: str,
        var_type: int = 100000000,
        *,
        default_value: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Dry-run: create an environment variable definition."""
        return await self.plan_create_record("environmentvariabledefinitions", {
            "schemaname": schema_name,
            "displayname": display_name,
            "type": var_type,
            "defaultvalue": default_value,
            "description": description,
        })

    async def plan_set_env_variable_value(
        self,
        definition_id: str,
        value: str,
    ) -> dict[str, Any]:
        """Dry-run: set the value of an environment variable."""
        return await self.plan_create_record("environmentvariablevalues", {
            "value": value,
            "EnvironmentVariableDefinitionId@odata.bind":
                f"/environmentvariabledefinitions({definition_id})",
        })

    async def plan_update_env_variable_value(
        self,
        value_id: str,
        value: str,
    ) -> dict[str, Any]:
        """Dry-run: update an existing environment variable value."""
        return await self.plan_update_record("environmentvariablevalues", value_id, {
            "value": value,
        })

    # -- Connection Reference operations ------------------------------------

    async def plan_list_connection_references(
        self,
        *,
        prefix: str | None = None,
    ) -> dict[str, Any]:
        """Dry-run: list connection references."""
        q = ODataQuery("connectionreferences").select(
            "connectionreferenceid", "connectionreferencelogicalname",
            "connectorid", "connectionreferencedisplayname", "description",
        )
        if prefix:
            q.filter(f"startswith(connectionreferencelogicalname, '{prefix}')")
        q.top(100)
        return await self.plan_query(q)

    async def plan_get_connection_reference(self, reference_id: str) -> dict[str, Any]:
        """Dry-run: get a specific connection reference."""
        q = (ODataQuery("connectionreferences")
             .by_id(reference_id)
             .select("connectionreferenceid", "connectionreferencelogicalname",
                     "connectorid", "connectionreferencedisplayname",
                     "connectionid", "description"))
        return await self.plan_query(q)

    # -- Metadata introspection ---------------------------------------------

    async def plan_get_entity_metadata(self, logical_name: str) -> dict[str, Any]:
        """Dry-run: get entity metadata (schema, attributes)."""
        url = self._api_url(f"EntityDefinitions(LogicalName='{logical_name}')")
        return {
            "action": "get_entity_metadata",
            "dry_run": True,
            "success": True,
            "details": {
                "logical_name": logical_name,
                "url": url,
            },
        }

    async def apply_get_entity_metadata(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute entity metadata retrieval."""
        url = plan["details"]["url"]
        start = time.perf_counter()
        resp = await self._client.get(url, headers=self._headers())
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "get_entity_metadata",
            "dry_run": False,
            "success": resp.success,
            "status_code": resp.status,
            "data": resp.body,
            "duration_ms": round(elapsed, 2),
        }

    async def plan_list_entity_attributes(self, logical_name: str) -> dict[str, Any]:
        """Dry-run: list attributes for an entity."""
        url = self._api_url(
            f"EntityDefinitions(LogicalName='{logical_name}')/Attributes"
            f"?$select=LogicalName,DisplayName,AttributeType,RequiredLevel"
        )
        return {
            "action": "list_entity_attributes",
            "dry_run": True,
            "success": True,
            "details": {
                "logical_name": logical_name,
                "url": url,
            },
        }

    async def plan_list_global_option_sets(self) -> dict[str, Any]:
        """Dry-run: list global option sets."""
        url = self._api_url("GlobalOptionSetDefinitions?$select=Name,DisplayName,OptionSetType")
        return {
            "action": "list_global_option_sets",
            "dry_run": True,
            "success": True,
            "details": {"url": url},
        }

    # -- Batch operations ---------------------------------------------------

    async def plan_batch(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        """Dry-run: preview a batch of operations.

        Args:
            operations: List of plan dicts from other plan_* methods.
        """
        return {
            "action": "batch",
            "dry_run": True,
            "success": True,
            "details": {
                "operation_count": len(operations),
                "operations": operations,
            },
        }

    async def apply_batch(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute a batch of operations sequentially.

        In a production implementation, this would use the Dataverse
        $batch endpoint for atomic execution.
        """
        start = time.perf_counter()
        results: list[dict[str, Any]] = []

        for op in plan["details"]["operations"]:
            action = op.get("action", "")
            if action == "create_record":
                r = await self.apply_create_record(op)
            elif action == "update_record":
                r = await self.apply_update_record(op)
            elif action == "delete_record":
                r = await self.apply_delete_record(op)
            elif action in ("query", "lookup_entity"):
                r = await self.apply_query(op)
            else:
                r = {"action": action, "success": False, "error": f"Unknown action: {action}"}
            results.append(r)

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "batch",
            "dry_run": False,
            "success": all(r.get("success", False) for r in results),
            "results": results,
            "operation_count": len(results),
            "duration_ms": round(elapsed, 2),
        }

    # -- Bot component operations -------------------------------------------

    async def plan_list_bot_components(self, *, prefix: str | None = None) -> dict[str, Any]:
        """Dry-run: list Copilot Studio bot components."""
        q = ODataQuery("botcomponents").select(
            "botcomponentid", "name", "componenttype", "schemaname",
        )
        if prefix:
            q.filter(f"startswith(schemaname, '{prefix}')")
        q.top(100)
        return await self.plan_query(q)

    async def plan_get_bot_component(self, component_id: str) -> dict[str, Any]:
        """Dry-run: get a specific bot component."""
        q = (ODataQuery("botcomponents")
             .by_id(component_id)
             .select("botcomponentid", "name", "componenttype", "schemaname", "content"))
        return await self.plan_query(q)


__all__ = [
    "DataverseApi",
    "HttpClient",
    "HttpResponse",
    "MockHttpClient",
    "ODataQuery",
]
