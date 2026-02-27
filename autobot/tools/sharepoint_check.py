"""Validates SharePoint URLs and permissions used as knowledge sources.

Provides reachability checks, auth scope mapping, and size estimation
for SharePoint sites, libraries, and folders referenced in an agent spec.

Includes a lightweight async Microsoft Graph API client for real
SharePoint reachability checks, permission validation, and item
enumeration.

All public functions support the plan/apply pattern.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

from autobot.tools.dataverse_api import HttpClient, HttpResponse, MockHttpClient


# ---------------------------------------------------------------------------
# SharePoint URL parser
# ---------------------------------------------------------------------------

def parse_sharepoint_url(url: str) -> dict[str, Any]:
    """Parse a SharePoint URL into structured components.

    Returns:
        Dictionary with tenant, site_path, library, folder, and is_valid.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")

    result: dict[str, Any] = {
        "url": url,
        "host": host,
        "is_valid": False,
        "tenant": "",
        "site_path": "",
        "library": None,
        "folder": None,
    }

    if not host.endswith(".sharepoint.com"):
        result["error"] = f"Host '{host}' is not a SharePoint Online domain."
        return result

    result["tenant"] = host.split(".")[0]

    # Extract site path
    site_match = re.match(r"(/sites/[^/]+)", path)
    if not site_match:
        result["error"] = "URL does not contain a valid /sites/<name> path."
        return result

    result["site_path"] = site_match.group(1)
    remainder = path[len(site_match.group(1)):]

    # Check for Shared Documents or other library
    if remainder:
        parts = [p for p in remainder.split("/") if p]
        if parts:
            result["library"] = parts[0]
        if len(parts) > 1:
            result["folder"] = "/".join(parts[1:])

    result["is_valid"] = True
    return result


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

class SharePointCheckResult:
    """Structured validation result for a single SharePoint knowledge source."""

    def __init__(
        self,
        url: str,
        *,
        reachable: bool = False,
        has_permission: bool = False,
        estimated_items: int = 0,
        estimated_size_mb: float = 0.0,
        scopes_required: list[str] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ):
        self.url = url
        self.reachable = reachable
        self.has_permission = has_permission
        self.estimated_items = estimated_items
        self.estimated_size_mb = estimated_size_mb
        self.scopes_required = scopes_required or []
        self.warnings = warnings or []
        self.errors = errors or []

    @property
    def success(self) -> bool:
        return self.reachable and len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "reachable": self.reachable,
            "has_permission": self.has_permission,
            "estimated_items": self.estimated_items,
            "estimated_size_mb": self.estimated_size_mb,
            "scopes_required": self.scopes_required,
            "warnings": self.warnings,
            "errors": self.errors,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# Graph API client
# ---------------------------------------------------------------------------

class GraphApiClient:
    """Lightweight async Microsoft Graph API client for SharePoint operations.

    Uses the same ``HttpClient`` / ``MockHttpClient`` abstraction from
    ``autobot.tools.dataverse_api`` so that production code can inject a
    real HTTP transport and tests can swap in a mock.

    Args:
        access_token: Bearer token with appropriate Graph scopes
            (e.g. ``Sites.Read.All``, ``Files.Read.All``).
        base_url: Graph API base URL.  Defaults to the v1.0 endpoint.
        http_client: Injectable HTTP transport.  When *None* a
            ``MockHttpClient`` is created automatically.

    Example::

        client = GraphApiClient(access_token="ey...", http_client=real_http)
        resp = await client.get_site("contoso", "/sites/HRHub")
    """

    DEFAULT_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        access_token: str = "",
        base_url: str = DEFAULT_BASE_URL,
        http_client: HttpClient | None = None,
    ) -> None:
        self._token = access_token
        self._base_url = base_url.rstrip("/")
        self._client: HttpClient = http_client or MockHttpClient()

    # -- internal helpers ---------------------------------------------------

    def _headers(self, *, content_type: str | None = None) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if content_type:
            h["Content-Type"] = content_type
        return h

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    @staticmethod
    def _wrap(resp: HttpResponse) -> dict[str, Any]:
        """Normalise every Graph response into a consistent envelope."""
        return {
            "success": resp.success,
            "status_code": resp.status,
            "data": resp.body if resp.success else None,
            "error": resp.body.get("error", {}).get("message", "") if not resp.success else None,
        }

    # -- Site operations ----------------------------------------------------

    async def get_site(self, tenant: str, site_path: str) -> dict[str, Any]:
        """GET /sites/{tenant}.sharepoint.com:{site_path}

        Retrieve basic metadata for a SharePoint site.

        Args:
            tenant: The tenant prefix (e.g. ``"contoso"``).
            site_path: The site-relative path (e.g. ``"/sites/HRHub"``).

        Returns:
            Structured dict with ``success``, ``status_code``, ``data``,
            and ``error`` keys.
        """
        path = site_path if site_path.startswith("/") else f"/{site_path}"
        url = self._url(f"sites/{tenant}.sharepoint.com:{path}")
        resp = await self._client.get(url, headers=self._headers())
        return self._wrap(resp)

    async def list_site_drives(self, site_id: str) -> dict[str, Any]:
        """GET /sites/{site_id}/drives

        Enumerate all document libraries (drives) for a site.

        Args:
            site_id: The Graph site-id (e.g. ``"contoso.sharepoint.com,<guid>,<guid>"``).

        Returns:
            Structured dict; ``data["value"]`` contains the list of drives.
        """
        url = self._url(f"sites/{site_id}/drives")
        resp = await self._client.get(url, headers=self._headers())
        return self._wrap(resp)

    async def get_drive_root_children(self, drive_id: str) -> dict[str, Any]:
        """GET /drives/{drive_id}/root/children

        List items at the root of a document library.

        Args:
            drive_id: The Graph drive-id.

        Returns:
            Structured dict; ``data["value"]`` contains the child items.
        """
        url = self._url(f"drives/{drive_id}/root/children")
        resp = await self._client.get(url, headers=self._headers())
        return self._wrap(resp)

    # -- Permissions --------------------------------------------------------

    async def list_site_permissions(self, site_id: str) -> dict[str, Any]:
        """GET /sites/{site_id}/permissions

        Retrieve permissions configured on a SharePoint site.

        Args:
            site_id: The Graph site-id.

        Returns:
            Structured dict; ``data["value"]`` contains permissions.
        """
        url = self._url(f"sites/{site_id}/permissions")
        resp = await self._client.get(url, headers=self._headers())
        return self._wrap(resp)

    # -- Content types ------------------------------------------------------

    async def get_site_content_types(self, site_id: str) -> dict[str, Any]:
        """GET /sites/{site_id}/contentTypes

        List content types registered on a SharePoint site.

        Args:
            site_id: The Graph site-id.

        Returns:
            Structured dict; ``data["value"]`` contains content types.
        """
        url = self._url(f"sites/{site_id}/contentTypes")
        resp = await self._client.get(url, headers=self._headers())
        return self._wrap(resp)

    # -- Search -------------------------------------------------------------

    async def search_site_items(self, site_id: str, query: str) -> dict[str, Any]:
        """POST /sites/{site_id}/search/query

        Execute a search query scoped to a specific SharePoint site.

        Args:
            site_id: The Graph site-id.
            query: Free-text search query string.

        Returns:
            Structured dict; ``data`` contains search results.
        """
        url = self._url(f"sites/{site_id}/search/query")
        body: dict[str, Any] = {
            "requests": [
                {
                    "entityTypes": ["driveItem", "listItem"],
                    "query": {"queryString": query},
                }
            ],
        }
        resp = await self._client.post(
            url,
            headers=self._headers(content_type="application/json"),
            body=body,
        )
        return self._wrap(resp)


# ---------------------------------------------------------------------------
# Mock Graph client (for tests)
# ---------------------------------------------------------------------------

class MockGraphClient(GraphApiClient):
    """A mock ``GraphApiClient`` pre-loaded with fake responses.

    Uses ``MockHttpClient`` internally so callers can inspect
    ``mock_http.calls`` after test execution.

    The constructor seeds realistic-looking responses for a fictional
    *contoso / HRHub* site.  Override or extend via
    ``mock_http.set_response(...)`` for custom scenarios.

    Example::

        mock = MockGraphClient()
        site = await mock.get_site("contoso", "/sites/HRHub")
        assert site["success"] is True
        assert site["data"]["displayName"] == "HR Hub"
    """

    _FAKE_SITE_ID = "contoso.sharepoint.com,site-guid-1234,web-guid-5678"
    _FAKE_DRIVE_ID = "drive-guid-abcd"

    def __init__(self) -> None:
        self.mock_http = MockHttpClient()
        super().__init__(
            access_token="mock-token-for-testing",
            http_client=self.mock_http,
        )
        self._seed_default_responses()

    def _seed_default_responses(self) -> None:
        """Pre-populate mock HTTP responses for common test scenarios."""

        # GET site
        self.mock_http.set_response(
            "sites/contoso.sharepoint.com:",
            HttpResponse(200, {
                "id": self._FAKE_SITE_ID,
                "displayName": "HR Hub",
                "name": "HRHub",
                "webUrl": "https://contoso.sharepoint.com/sites/HRHub",
            }),
        )

        # GET drives
        self.mock_http.set_response(
            f"sites/{self._FAKE_SITE_ID}/drives",
            HttpResponse(200, {
                "value": [
                    {
                        "id": self._FAKE_DRIVE_ID,
                        "name": "Documents",
                        "driveType": "documentLibrary",
                        "quota": {
                            "total": 27_917_287_424,
                            "used": 5_242_880,
                        },
                    },
                ],
            }),
        )

        # GET drive root children
        self.mock_http.set_response(
            f"drives/{self._FAKE_DRIVE_ID}/root/children",
            HttpResponse(200, {
                "value": [
                    {"name": "Benefits.docx", "size": 102_400, "file": {"mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}},
                    {"name": "Onboarding.pptx", "size": 2_048_000, "file": {"mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}},
                    {"name": "Policies", "folder": {"childCount": 12}},
                ],
            }),
        )

        # GET permissions
        self.mock_http.set_response(
            f"sites/{self._FAKE_SITE_ID}/permissions",
            HttpResponse(200, {
                "value": [
                    {"id": "perm-1", "roles": ["read"], "grantedToIdentities": [{"application": {"displayName": "CopilotAgent"}}]},
                ],
            }),
        )

        # GET content types
        self.mock_http.set_response(
            f"sites/{self._FAKE_SITE_ID}/contentTypes",
            HttpResponse(200, {
                "value": [
                    {"id": "0x0101", "name": "Document", "description": "Create a new document."},
                    {"id": "0x0120", "name": "Folder", "description": "Create a new folder."},
                ],
            }),
        )

        # POST search
        self.mock_http.set_response(
            f"sites/{self._FAKE_SITE_ID}/search/query",
            HttpResponse(200, {
                "value": [
                    {
                        "searchTerms": ["policy"],
                        "hitsContainers": [
                            {
                                "total": 3,
                                "moreResultsAvailable": False,
                                "hits": [
                                    {"hitId": "hit-1", "summary": "Company policy document"},
                                    {"hitId": "hit-2", "summary": "Security policy"},
                                    {"hitId": "hit-3", "summary": "Vacation policy"},
                                ],
                            },
                        ],
                    },
                ],
            }),
        )


# ---------------------------------------------------------------------------
# SharePoint checker
# ---------------------------------------------------------------------------

class SharePointChecker:
    """Validates SharePoint knowledge sources.

    When a ``graph_client`` is provided the checker performs live
    validation against the Microsoft Graph API (site reachability,
    drive enumeration, item counting).  Without one it falls back to
    structural-only validation.

    Args:
        access_token: Bearer token with Sites.Read.All or equivalent.
        graph_client: Optional ``GraphApiClient`` for live Graph calls.

    Example::

        checker = SharePointChecker()
        plan = await checker.plan_validate(sources)
        result = await checker.apply_validate(plan)

    Example with live Graph API::

        graph = GraphApiClient(access_token="ey...", http_client=real_http)
        checker = SharePointChecker(graph_client=graph)
        plan = await checker.plan_validate(sources)
        result = await checker.apply_validate(plan)
    """

    # Graph API scopes required per operation
    SCOPE_MAP: dict[str, list[str]] = {
        "site": ["Sites.Read.All"],
        "library": ["Sites.Read.All", "Files.Read.All"],
        "folder": ["Sites.Read.All", "Files.Read.All"],
    }

    def __init__(
        self,
        access_token: str = "",
        graph_client: GraphApiClient | None = None,
    ) -> None:
        self._token = access_token
        self._graph = graph_client

    async def plan_validate(
        self,
        knowledge_sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Dry-run: preview validation of SharePoint knowledge sources.

        Args:
            knowledge_sources: List of knowledge source dicts from agent_spec
                               (only SharePoint entries are processed).
        """
        sp_sources = [ks for ks in knowledge_sources if ks.get("type") == "sharepoint"]
        checks: list[dict[str, Any]] = []

        for src in sp_sources:
            url = src.get("url", "")
            scope = src.get("scope", "site")
            parsed = parse_sharepoint_url(url)
            scopes = self.SCOPE_MAP.get(scope, ["Sites.Read.All"])

            check: dict[str, Any] = {
                "url": url,
                "scope": scope,
                "parsed": parsed,
                "scopes_required": scopes,
                "errors": [],
                "warnings": [],
            }

            if not parsed["is_valid"]:
                check["errors"].append(parsed.get("error", "Invalid SharePoint URL"))

            if scope == "site" and parsed.get("library"):
                check["warnings"].append(
                    "URL points to a library/folder but scope is 'site'. "
                    "Consider using 'library' or 'folder' scope for narrower indexing."
                )

            checks.append(check)

        return {
            "action": "validate_sharepoint_sources",
            "dry_run": True,
            "success": all(len(c["errors"]) == 0 for c in checks),
            "total_sources": len(sp_sources),
            "checks": checks,
        }

    async def apply_validate(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute validation of SharePoint knowledge sources.

        When a ``GraphApiClient`` is available the checker calls the
        Microsoft Graph API to:

        * Verify the site exists (``get_site``).
        * Enumerate document libraries (``list_site_drives``).
        * Estimate item counts by listing root children of the first
          drive (``get_drive_root_children``).

        When no graph client is configured the method falls back to
        structural-only validation (no network calls).
        """
        start = time.perf_counter()
        results: list[dict[str, Any]] = []

        for check in plan.get("checks", []):
            parsed = check["parsed"]
            errors = list(check.get("errors", []))
            warnings = list(check.get("warnings", []))

            # Structural validation (no network required)
            if not parsed["is_valid"]:
                result = SharePointCheckResult(
                    url=check["url"],
                    errors=errors,
                    scopes_required=check["scopes_required"],
                )
                results.append(result.to_dict())
                continue

            # ----- Graph API path (live validation) -------------------------
            if self._graph is not None:
                result = await self._validate_via_graph(
                    check, parsed, errors, warnings,
                )
                results.append(result.to_dict())
                continue

            # ----- Structural-only path (no graph client) -------------------
            result = SharePointCheckResult(
                url=check["url"],
                reachable=True,  # Optimistic in structural-only mode
                has_permission=True,
                scopes_required=check["scopes_required"],
                warnings=warnings,
            )
            results.append(result.to_dict())

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "validate_sharepoint_sources",
            "dry_run": False,
            "success": all(r["success"] for r in results),
            "results": results,
            "duration_ms": round(elapsed, 2),
        }

    # -- internal: Graph-backed validation ----------------------------------

    async def _validate_via_graph(
        self,
        check: dict[str, Any],
        parsed: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> SharePointCheckResult:
        """Run live validation against Microsoft Graph for one source."""
        assert self._graph is not None  # guaranteed by caller

        tenant = parsed["tenant"]
        site_path = parsed["site_path"]
        estimated_items = 0
        estimated_size_mb = 0.0
        reachable = False
        has_permission = False

        # 1. Verify the site exists
        site_resp = await self._graph.get_site(tenant, site_path)
        if not site_resp["success"]:
            if site_resp["status_code"] == 403:
                errors.append(
                    f"Access denied to site '{site_path}' "
                    f"(HTTP {site_resp['status_code']}). "
                    "Ensure the app registration has Sites.Read.All consent."
                )
            elif site_resp["status_code"] == 404:
                errors.append(
                    f"Site '{site_path}' not found on tenant '{tenant}' "
                    f"(HTTP {site_resp['status_code']})."
                )
            else:
                errors.append(
                    f"Graph API error when checking site '{site_path}': "
                    f"HTTP {site_resp['status_code']} - {site_resp.get('error', 'Unknown error')}"
                )
            return SharePointCheckResult(
                url=check["url"],
                reachable=False,
                has_permission=False,
                errors=errors,
                warnings=warnings,
                scopes_required=check["scopes_required"],
            )

        reachable = True
        has_permission = True
        site_id = site_resp["data"].get("id", "")

        # 2. Enumerate drives (document libraries)
        drives_resp = await self._graph.list_site_drives(site_id)
        if drives_resp["success"]:
            drives = drives_resp["data"].get("value", [])
            if not drives:
                warnings.append("Site has no document libraries.")

            # 3. Estimate item count from the first drive's root
            if drives:
                first_drive_id = drives[0].get("id", "")
                children_resp = await self._graph.get_drive_root_children(first_drive_id)
                if children_resp["success"]:
                    children = children_resp["data"].get("value", [])
                    estimated_items = len(children)
                    total_bytes = sum(
                        item.get("size", 0)
                        for item in children
                        if "file" in item
                    )
                    # Add folder children counts as rough item estimates
                    for item in children:
                        folder_info = item.get("folder")
                        if folder_info:
                            estimated_items += folder_info.get("childCount", 0)
                    estimated_size_mb = round(total_bytes / (1024 * 1024), 2)
                else:
                    warnings.append(
                        "Could not enumerate drive root children "
                        f"(HTTP {children_resp['status_code']})."
                    )
        else:
            warnings.append(
                "Could not enumerate site drives "
                f"(HTTP {drives_resp['status_code']})."
            )

        return SharePointCheckResult(
            url=check["url"],
            reachable=reachable,
            has_permission=has_permission,
            estimated_items=estimated_items,
            estimated_size_mb=estimated_size_mb,
            scopes_required=check["scopes_required"],
            warnings=warnings,
            errors=errors,
        )

    # -- Source enumeration (plan / apply) ----------------------------------

    async def plan_enumerate_sources(
        self,
        knowledge_sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Dry-run: plan a full enumeration of SharePoint knowledge sources.

        This produces a plan dict that ``apply_enumerate_sources`` can
        execute to retrieve item counts, sizes, and permission info for
        every valid SharePoint source.

        Args:
            knowledge_sources: List of knowledge source dicts (only
                SharePoint entries are processed).

        Returns:
            Plan dict with ``action="enumerate_sharepoint_sources"`` and
            per-source enumeration entries.
        """
        sp_sources = [ks for ks in knowledge_sources if ks.get("type") == "sharepoint"]
        entries: list[dict[str, Any]] = []

        for src in sp_sources:
            url = src.get("url", "")
            parsed = parse_sharepoint_url(url)
            entry: dict[str, Any] = {
                "url": url,
                "parsed": parsed,
                "errors": [],
            }
            if not parsed["is_valid"]:
                entry["errors"].append(parsed.get("error", "Invalid SharePoint URL"))
            entries.append(entry)

        return {
            "action": "enumerate_sharepoint_sources",
            "dry_run": True,
            "success": all(len(e["errors"]) == 0 for e in entries),
            "total_sources": len(sp_sources),
            "entries": entries,
        }

    async def apply_enumerate_sources(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute enumeration of SharePoint knowledge sources.

        For each valid source, when a ``GraphApiClient`` is configured
        this method retrieves:

        * **Site metadata** via ``get_site``.
        * **Document libraries** (drives) via ``list_site_drives``.
        * **Root-level item counts and sizes** via
          ``get_drive_root_children``.
        * **Permissions** via ``list_site_permissions``.

        Without a graph client the method returns a structural summary
        only (no live data).

        Args:
            plan: The plan dict produced by ``plan_enumerate_sources``.

        Returns:
            Result dict with per-source ``item_count``, ``total_size_mb``,
            ``drives``, and ``permissions``.
        """
        start = time.perf_counter()
        source_results: list[dict[str, Any]] = []

        for entry in plan.get("entries", []):
            parsed = entry["parsed"]
            errors = list(entry.get("errors", []))

            if not parsed["is_valid"]:
                source_results.append({
                    "url": entry["url"],
                    "success": False,
                    "errors": errors,
                })
                continue

            if self._graph is None:
                # Structural-only: no live enumeration possible
                source_results.append({
                    "url": entry["url"],
                    "success": True,
                    "mode": "structural",
                    "item_count": 0,
                    "total_size_mb": 0.0,
                    "drives": [],
                    "permissions": [],
                    "errors": errors,
                })
                continue

            # ---- Live enumeration via Graph API ---------------------------
            tenant = parsed["tenant"]
            site_path = parsed["site_path"]
            drives_info: list[dict[str, Any]] = []
            permissions_info: list[dict[str, Any]] = []
            total_items = 0
            total_size_bytes = 0

            site_resp = await self._graph.get_site(tenant, site_path)
            if not site_resp["success"]:
                source_results.append({
                    "url": entry["url"],
                    "success": False,
                    "errors": errors + [
                        f"Graph API error: HTTP {site_resp['status_code']} - "
                        f"{site_resp.get('error', 'Unknown error')}"
                    ],
                })
                continue

            site_id = site_resp["data"].get("id", "")

            # Drives
            drives_resp = await self._graph.list_site_drives(site_id)
            if drives_resp["success"]:
                for drv in drives_resp["data"].get("value", []):
                    drive_id = drv.get("id", "")
                    drive_entry: dict[str, Any] = {
                        "id": drive_id,
                        "name": drv.get("name", ""),
                        "driveType": drv.get("driveType", ""),
                        "items": [],
                        "item_count": 0,
                    }
                    # Enumerate root children of each drive
                    children_resp = await self._graph.get_drive_root_children(drive_id)
                    if children_resp["success"]:
                        children = children_resp["data"].get("value", [])
                        drive_item_count = len(children)
                        for child in children:
                            size = child.get("size", 0)
                            if "file" in child:
                                total_size_bytes += size
                            folder_info = child.get("folder")
                            if folder_info:
                                drive_item_count += folder_info.get("childCount", 0)
                            drive_entry["items"].append({
                                "name": child.get("name", ""),
                                "size": size,
                                "is_folder": "folder" in child,
                            })
                        drive_entry["item_count"] = drive_item_count
                        total_items += drive_item_count
                    drives_info.append(drive_entry)

            # Permissions
            perm_resp = await self._graph.list_site_permissions(site_id)
            if perm_resp["success"]:
                for perm in perm_resp["data"].get("value", []):
                    permissions_info.append({
                        "id": perm.get("id", ""),
                        "roles": perm.get("roles", []),
                        "grantedToIdentities": perm.get("grantedToIdentities", []),
                    })

            source_results.append({
                "url": entry["url"],
                "success": True,
                "mode": "graph_api",
                "site_id": site_id,
                "item_count": total_items,
                "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
                "drives": drives_info,
                "permissions": permissions_info,
                "errors": errors,
            })

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "enumerate_sharepoint_sources",
            "dry_run": False,
            "success": all(r.get("success", False) for r in source_results),
            "results": source_results,
            "duration_ms": round(elapsed, 2),
        }


__all__ = [
    "GraphApiClient",
    "MockGraphClient",
    "SharePointCheckResult",
    "SharePointChecker",
    "parse_sharepoint_url",
]
