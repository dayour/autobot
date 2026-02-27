"""Teams and M365 Copilot channel publishing with manifest generation.

Default mode is **report-only** — no destructive operations are performed
unless ``--apply`` is explicitly requested.  Every public function supports
the plan/apply pattern.

Includes:
- ``TeamsAppManifest`` — generates a valid Teams app manifest.json (v1.17)
- ``TeamsAppUploader`` — uploads manifests to the Teams app catalog via Graph API
- ``TeamsPublisher`` — orchestrates channel publishing, manifest generation, and upload
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from autobot.tools.dataverse_api import HttpClient, HttpResponse, MockHttpClient


# ---------------------------------------------------------------------------
# Channel definitions
# ---------------------------------------------------------------------------

CHANNEL_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "teams": {
        "display_name": "Microsoft Teams",
        "requires_admin_approval": True,
        "approval_scope": "Teams admin center",
        "steps": [
            "Register bot in Azure Bot Service (or verify existing registration).",
            "Configure Teams channel in Bot Framework.",
            "Upload app manifest to Teams admin center.",
            "Admin approves the app for the organization.",
            "Users discover the agent in the Teams app catalog.",
        ],
    },
    "m365_copilot": {
        "display_name": "Microsoft 365 Copilot",
        "requires_admin_approval": True,
        "approval_scope": "M365 admin center > Copilot extensions",
        "steps": [
            "Publish agent as a Copilot Studio plugin.",
            "Submit plugin for admin approval in M365 admin center.",
            "Admin enables the extension for target user groups.",
            "Users access the agent via M365 Copilot chat.",
        ],
    },
    "web": {
        "display_name": "Web Channel",
        "requires_admin_approval": False,
        "approval_scope": None,
        "steps": [
            "Enable web channel in Copilot Studio.",
            "Copy embed code or direct link.",
            "Add to target website or distribute link.",
        ],
    },
    "custom": {
        "display_name": "Custom Channel (Direct Line)",
        "requires_admin_approval": False,
        "approval_scope": None,
        "steps": [
            "Enable Direct Line channel.",
            "Generate Direct Line secret.",
            "Store secret as environment variable (never hardcode).",
            "Integrate via Direct Line API or SDK.",
        ],
    },
}


# ---------------------------------------------------------------------------
# UUID namespace for deterministic bot IDs
# ---------------------------------------------------------------------------

_TEAMS_BOT_NAMESPACE = uuid.UUID("a01e7f3c-6b2d-4a8f-9e5c-1d3b7f9a2c4e")


# ---------------------------------------------------------------------------
# Manifest generator
# ---------------------------------------------------------------------------

class TeamsAppManifest:
    """Generates a Teams app manifest.json for a Copilot Studio agent.

    Follows the Microsoft Teams app manifest schema v1.17.  The generated
    manifest is suitable for sideloading or uploading to the Teams admin
    center via Graph API.

    Args:
        spec: Agent specification dictionary.  Expected keys include:
            - ``name`` (str): Agent display name.
            - ``description`` (str): Agent description.
            - ``publisher`` (dict): Publisher info with ``prefix`` and ``name``.
            - ``alm`` (dict): ALM settings with ``solutionVersion``.
            - ``security`` (dict, optional): Security/auth configuration.

    Example::

        manifest = TeamsAppManifest(spec)
        data = manifest.generate()
        manifest.validate()
        json_str = manifest.to_json()
    """

    MANIFEST_VERSION = "1.17"
    SCHEMA_URL = (
        "https://developer.microsoft.com/en-us/json-schemas"
        "/teams/v1.17/MicrosoftTeams.schema.json"
    )

    # Constraints from the Teams manifest schema
    _NAME_SHORT_MAX = 30
    _NAME_FULL_MAX = 100
    _DESC_SHORT_MAX = 80
    _DESC_FULL_MAX = 4000

    def __init__(self, spec: dict[str, Any]):
        self._spec = spec

    # -- helpers ------------------------------------------------------------

    def _agent_name(self) -> str:
        return self._spec.get("name", "Unnamed Agent")

    def _publisher_prefix(self) -> str:
        pub = self._spec.get("publisher", {})
        return pub.get("prefix", "default")

    def _publisher_name(self) -> str:
        pub = self._spec.get("publisher", {})
        return pub.get("name", "Unknown Publisher")

    def _publisher_website(self) -> str:
        pub = self._spec.get("publisher", {})
        return pub.get("websiteUrl", "https://example.com")

    def _publisher_privacy(self) -> str:
        pub = self._spec.get("publisher", {})
        return pub.get("privacyUrl", "https://example.com/privacy")

    def _publisher_terms(self) -> str:
        pub = self._spec.get("publisher", {})
        return pub.get("termsOfUseUrl", "https://example.com/terms")

    def _solution_version(self) -> str:
        alm = self._spec.get("alm", {})
        return alm.get("solutionVersion", "1.0.0")

    def _description(self) -> str:
        return self._spec.get("description", "A Copilot Studio agent.")

    def _generate_bot_id(self) -> str:
        """Generate a deterministic bot ID using UUID v5.

        The ID is derived from the publisher prefix and agent name,
        ensuring the same spec always produces the same bot ID.
        """
        seed = f"{self._publisher_prefix()}:{self._agent_name()}"
        return str(uuid.uuid5(_TEAMS_BOT_NAMESPACE, seed))

    def _generate_app_id(self) -> str:
        """Generate a deterministic app ID using UUID v5.

        Uses a different seed suffix so app ID differs from bot ID.
        """
        seed = f"{self._publisher_prefix()}:{self._agent_name()}:app"
        return str(uuid.uuid5(_TEAMS_BOT_NAMESPACE, seed))

    def _entra_app_id(self) -> str:
        """Return the Entra ID (Azure AD) application ID for auth.

        Falls back to the generated app ID if not provided in spec.
        """
        security = self._spec.get("security", {})
        return security.get("entraAppId", self._generate_app_id())

    def _entra_resource(self) -> str:
        """Return the Entra ID resource URI for token audience."""
        security = self._spec.get("security", {})
        app_id = self._entra_app_id()
        return security.get("entraResource", f"api://{app_id}")

    # -- public API ---------------------------------------------------------

    def generate(self) -> dict[str, Any]:
        """Generate a complete Teams app manifest from the agent spec.

        Returns:
            A dictionary matching the Microsoft Teams manifest schema v1.17.
        """
        name = self._agent_name()
        bot_id = self._generate_bot_id()
        app_id = self._generate_app_id()

        short_name = name[:self._NAME_SHORT_MAX]
        full_name = name[:self._NAME_FULL_MAX]

        description = self._description()
        short_desc = description[:self._DESC_SHORT_MAX]
        full_desc = description[:self._DESC_FULL_MAX]

        manifest: dict[str, Any] = {
            "$schema": self.SCHEMA_URL,
            "manifestVersion": self.MANIFEST_VERSION,
            "version": self._solution_version(),
            "id": app_id,
            "developer": {
                "name": self._publisher_name(),
                "websiteUrl": self._publisher_website(),
                "privacyUrl": self._publisher_privacy(),
                "termsOfUseUrl": self._publisher_terms(),
            },
            "name": {
                "short": short_name,
                "full": full_name,
            },
            "description": {
                "short": short_desc,
                "full": full_desc,
            },
            "icons": {
                "color": "color.png",
                "outline": "outline.png",
            },
            "accentColor": "#FFFFFF",
            "bots": [
                {
                    "botId": bot_id,
                    "scopes": ["personal", "team", "groupChat"],
                    "supportsFiles": False,
                    "isNotificationOnly": False,
                    "commandLists": [
                        {
                            "scopes": ["personal", "team", "groupChat"],
                            "commands": [
                                {
                                    "title": "help",
                                    "description": f"Get help using {short_name}",
                                },
                            ],
                        },
                    ],
                },
            ],
            "permissions": [
                "identity",
                "messageTeamMembers",
            ],
            "validDomains": [
                "token.botframework.com",
                "*.botframework.com",
            ],
            "webApplicationInfo": {
                "id": self._entra_app_id(),
                "resource": self._entra_resource(),
            },
        }

        return manifest

    def validate(self) -> dict[str, Any]:
        """Validate the manifest against Teams requirements.

        Returns:
            A dict with keys ``valid`` (bool), ``errors`` (list[str]),
            and ``warnings`` (list[str]).
        """
        errors: list[str] = []
        warnings: list[str] = []

        manifest = self.generate()

        # --- Required top-level fields ---
        required_fields = [
            "$schema",
            "manifestVersion",
            "version",
            "id",
            "developer",
            "name",
            "description",
            "icons",
            "accentColor",
        ]
        for field in required_fields:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")

        # --- Validate id is a valid UUID ---
        try:
            uuid.UUID(manifest.get("id", ""))
        except (ValueError, AttributeError):
            errors.append("Field 'id' must be a valid UUID.")

        # --- Validate version format (semver-like: major.minor.patch) ---
        version = manifest.get("version", "")
        parts = version.split(".")
        if len(parts) < 2 or not all(p.isdigit() for p in parts):
            errors.append(
                f"Field 'version' must be a valid semver string, got '{version}'."
            )

        # --- Name length constraints ---
        name_obj = manifest.get("name", {})
        short_name = name_obj.get("short", "")
        full_name = name_obj.get("full", "")
        if not short_name:
            errors.append("name.short is required and cannot be empty.")
        elif len(short_name) > self._NAME_SHORT_MAX:
            errors.append(
                f"name.short exceeds {self._NAME_SHORT_MAX} characters "
                f"(got {len(short_name)})."
            )
        if full_name and len(full_name) > self._NAME_FULL_MAX:
            errors.append(
                f"name.full exceeds {self._NAME_FULL_MAX} characters "
                f"(got {len(full_name)})."
            )

        # --- Description length constraints ---
        desc_obj = manifest.get("description", {})
        short_desc = desc_obj.get("short", "")
        full_desc = desc_obj.get("full", "")
        if not short_desc:
            errors.append("description.short is required and cannot be empty.")
        elif len(short_desc) > self._DESC_SHORT_MAX:
            errors.append(
                f"description.short exceeds {self._DESC_SHORT_MAX} characters "
                f"(got {len(short_desc)})."
            )
        if full_desc and len(full_desc) > self._DESC_FULL_MAX:
            errors.append(
                f"description.full exceeds {self._DESC_FULL_MAX} characters "
                f"(got {len(full_desc)})."
            )

        # --- Developer info ---
        dev = manifest.get("developer", {})
        for dev_field in ("name", "websiteUrl", "privacyUrl", "termsOfUseUrl"):
            if not dev.get(dev_field):
                errors.append(f"developer.{dev_field} is required.")

        # --- Bots array ---
        bots = manifest.get("bots", [])
        if not bots:
            warnings.append("No bots defined in manifest. Agent may not function in Teams.")
        else:
            for i, bot in enumerate(bots):
                bot_id = bot.get("botId", "")
                try:
                    uuid.UUID(bot_id)
                except (ValueError, AttributeError):
                    errors.append(f"bots[{i}].botId must be a valid UUID, got '{bot_id}'.")
                scopes = bot.get("scopes", [])
                if not scopes:
                    warnings.append(f"bots[{i}].scopes is empty; bot won't be usable.")

        # --- Icons ---
        icons = manifest.get("icons", {})
        if not icons.get("color"):
            errors.append("icons.color is required.")
        if not icons.get("outline"):
            errors.append("icons.outline is required.")

        # --- webApplicationInfo ---
        web_app = manifest.get("webApplicationInfo", {})
        if web_app:
            wai_id = web_app.get("id", "")
            if not wai_id:
                warnings.append("webApplicationInfo.id is empty; SSO won't work.")
            else:
                try:
                    uuid.UUID(wai_id)
                except (ValueError, AttributeError):
                    warnings.append(
                        f"webApplicationInfo.id should be a valid UUID, got '{wai_id}'."
                    )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the manifest to a JSON string.

        Args:
            indent: Number of spaces for indentation (default 2).

        Returns:
            A JSON string of the manifest.
        """
        return json.dumps(self.generate(), indent=indent)


# ---------------------------------------------------------------------------
# Manifest uploader (Graph API)
# ---------------------------------------------------------------------------

class TeamsAppUploader:
    """Uploads Teams app manifests to the Teams app catalog via Graph API.

    Uses the Microsoft Graph API endpoints:
    - ``POST /appCatalogs/teamsApps`` to upload a new app.
    - ``PATCH /appCatalogs/teamsApps/{id}`` to update an existing app.
    - ``GET /appCatalogs/teamsApps`` to list apps and check for existing.

    Args:
        http_client: Injectable HTTP client (default: ``MockHttpClient``).
        access_token: OAuth 2.0 bearer token with the
            ``AppCatalog.ReadWrite.All`` permission.

    Example::

        uploader = TeamsAppUploader(access_token="eyJ...")
        plan = await uploader.plan_upload(manifest_dict)
        result = await uploader.apply_upload(plan)
    """

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        access_token: str = "",
    ):
        self._client: HttpClient = http_client or MockHttpClient()
        self._token = access_token

    def _headers(self, *, content_type: str = "application/json") -> dict[str, str]:
        h: dict[str, str] = {
            "Content-Type": content_type,
            "Accept": "application/json",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    # -- check existing -----------------------------------------------------

    async def plan_check_existing(self, external_id: str) -> dict[str, Any]:
        """Dry-run: plan a check for an existing app in the catalog.

        Args:
            external_id: The app ``id`` from the manifest.

        Returns:
            A plan dict describing the lookup query.
        """
        url = (
            f"{self.GRAPH_BASE}/appCatalogs/teamsApps"
            f"?$filter=externalId eq '{external_id}'"
        )
        return {
            "action": "check_existing_teams_app",
            "dry_run": True,
            "success": True,
            "details": {
                "external_id": external_id,
                "url": url,
            },
        }

    async def apply_check_existing(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute the check for an existing app.

        Returns:
            Result dict with ``exists`` (bool) and ``app_id`` if found.
        """
        url = plan["details"]["url"]
        start = time.perf_counter()
        resp = await self._client.get(url, headers=self._headers())
        elapsed = (time.perf_counter() - start) * 1000

        apps = resp.body.get("value", [])
        exists = len(apps) > 0
        app_id = apps[0].get("id", "") if exists else ""

        return {
            "action": "check_existing_teams_app",
            "dry_run": False,
            "success": resp.success,
            "status_code": resp.status,
            "exists": exists,
            "app_id": app_id,
            "duration_ms": round(elapsed, 2),
        }

    # -- upload / update ----------------------------------------------------

    async def plan_upload(
        self,
        manifest: dict[str, Any],
        *,
        update_existing: bool = True,
    ) -> dict[str, Any]:
        """Dry-run: plan the manifest upload.

        If *update_existing* is ``True`` (the default), the plan notes that
        an existing app with the same ``id`` would be updated rather than
        duplicated.

        Args:
            manifest: The full manifest dict (as produced by
                ``TeamsAppManifest.generate``).
            update_existing: Whether to PATCH if the app already exists.

        Returns:
            A plan dict with the upload action, URL, and manifest summary.
        """
        app_id = manifest.get("id", "")
        upload_url = f"{self.GRAPH_BASE}/appCatalogs/teamsApps"
        update_url = f"{self.GRAPH_BASE}/appCatalogs/teamsApps/{app_id}"

        return {
            "action": "upload_teams_app",
            "dry_run": True,
            "success": True,
            "details": {
                "app_id": app_id,
                "upload_url": upload_url,
                "update_url": update_url,
                "update_existing": update_existing,
                "manifest": manifest,
                "manifest_summary": {
                    "name": manifest.get("name", {}).get("short", ""),
                    "version": manifest.get("version", ""),
                    "bot_count": len(manifest.get("bots", [])),
                },
            },
        }

    async def apply_upload(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute the manifest upload via Graph API.

        Performs a ``POST`` to create a new app.  If ``update_existing``
        is set in the plan and the app already exists, performs a ``PATCH``
        instead.

        Returns:
            Result dict with status, created/updated flag, and response body.
        """
        details = plan["details"]
        manifest = details["manifest"]
        update_existing = details.get("update_existing", True)
        app_id = details["app_id"]

        start = time.perf_counter()

        # Check if app already exists when update_existing is True
        if update_existing and app_id:
            check_plan = await self.plan_check_existing(app_id)
            check_result = await self.apply_check_existing(check_plan)

            if check_result.get("exists"):
                # Update existing app
                catalog_app_id = check_result["app_id"]
                update_url = (
                    f"{self.GRAPH_BASE}/appCatalogs/teamsApps/{catalog_app_id}"
                )
                resp = await self._client.patch(
                    update_url,
                    headers=self._headers(),
                    body=manifest,
                )
                elapsed = (time.perf_counter() - start) * 1000
                return {
                    "action": "upload_teams_app",
                    "dry_run": False,
                    "success": resp.success,
                    "status_code": resp.status,
                    "operation": "updated",
                    "catalog_app_id": catalog_app_id,
                    "data": resp.body,
                    "duration_ms": round(elapsed, 2),
                }

        # Create new app
        upload_url = details["upload_url"]
        resp = await self._client.post(
            upload_url,
            headers=self._headers(),
            body=manifest,
        )
        elapsed = (time.perf_counter() - start) * 1000

        return {
            "action": "upload_teams_app",
            "dry_run": False,
            "success": resp.success,
            "status_code": resp.status,
            "operation": "created",
            "data": resp.body,
            "duration_ms": round(elapsed, 2),
        }


# ---------------------------------------------------------------------------
# Publisher adapter
# ---------------------------------------------------------------------------

class TeamsPublisher:
    """Publisher for Teams and M365 Copilot channels with manifest support.

    By default, every operation returns a **plan** describing what would
    happen.  Only ``apply_*()`` methods perform actual steps when explicitly
    invoked.

    Optionally integrates ``TeamsAppManifest`` for manifest generation and
    ``TeamsAppUploader`` for uploading to the Teams app catalog via Graph API.

    Args:
        http_client: Optional HTTP client for Graph API calls.
        access_token: OAuth 2.0 bearer token for Graph API.

    Example::

        pub = TeamsPublisher()
        plan = await pub.plan_publish(["teams", "m365_copilot"], agent_name="Contoso Agent")
        # Review the plan …
        result = await pub.apply_publish(plan)

        # With manifest generation and upload:
        plan = await pub.plan_publish_with_manifest(spec)
        result = await pub.apply_publish_with_manifest(plan)
    """

    def __init__(
        self,
        http_client: HttpClient | None = None,
        access_token: str = "",
    ):
        self._http_client = http_client
        self._access_token = access_token
        self._manifest_generator: TeamsAppManifest | None = None
        self._uploader: TeamsAppUploader | None = None

    @property
    def manifest_generator(self) -> TeamsAppManifest | None:
        """The current manifest generator, if one has been configured."""
        return self._manifest_generator

    @manifest_generator.setter
    def manifest_generator(self, value: TeamsAppManifest | None) -> None:
        self._manifest_generator = value

    @property
    def uploader(self) -> TeamsAppUploader | None:
        """The current uploader, if one has been configured."""
        return self._uploader

    @uploader.setter
    def uploader(self, value: TeamsAppUploader | None) -> None:
        self._uploader = value

    def _ensure_uploader(self) -> TeamsAppUploader:
        """Return the uploader, creating a default one if needed."""
        if self._uploader is None:
            self._uploader = TeamsAppUploader(
                http_client=self._http_client,
                access_token=self._access_token,
            )
        return self._uploader

    async def plan_publish(
        self,
        channels: list[str],
        *,
        agent_name: str = "",
        security: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dry-run: produce a detailed publish plan.

        Args:
            channels: List of channel identifiers from the spec.
            agent_name: Agent display name for reporting.
            security: Security config from the spec (for scope checks).

        Returns:
            Structured plan with per-channel steps and approval requirements.
        """
        channel_plans: list[dict[str, Any]] = []
        approvals_needed: list[str] = []
        warnings: list[str] = []

        for ch in channels:
            info = CHANNEL_REQUIREMENTS.get(ch)
            if info is None:
                warnings.append(f"Unknown channel '{ch}' — skipped.")
                continue

            plan_entry: dict[str, Any] = {
                "channel": ch,
                "display_name": info["display_name"],
                "steps": info["steps"],
                "requires_admin_approval": info["requires_admin_approval"],
            }

            if info["requires_admin_approval"]:
                approvals_needed.append(
                    f"{info['display_name']}: approval via {info['approval_scope']}"
                )

            # Security scope checks
            if security:
                allow_ext = security.get("allowExternal", False)
                if ch in ("web", "custom") and not allow_ext:
                    warnings.append(
                        f"Channel '{ch}' is publicly accessible but "
                        f"allowExternal=false in spec. Verify intent."
                    )

            channel_plans.append(plan_entry)

        return {
            "action": "publish_channels",
            "dry_run": True,
            "success": True,
            "agent_name": agent_name,
            "channels": channel_plans,
            "approvals_needed": approvals_needed,
            "warnings": warnings,
        }

    async def apply_publish(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute publish steps (stub — logs actions without side effects).

        In production, this would invoke PAC CLI or Graph API to configure
        channel registrations.  Currently returns the plan annotated with
        execution status.
        """
        start = time.perf_counter()
        results: list[dict[str, Any]] = []

        for ch_plan in plan.get("channels", []):
            # TODO: Implement actual publish via PAC / Graph API
            results.append({
                "channel": ch_plan["channel"],
                "status": "pending_implementation",
                "message": (
                    f"Channel '{ch_plan['display_name']}' publish steps recorded. "
                    "Manual execution required — see steps in plan."
                ),
            })

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "publish_channels",
            "dry_run": False,
            "success": True,
            "results": results,
            "warnings": plan.get("warnings", []),
            "approvals_needed": plan.get("approvals_needed", []),
            "duration_ms": round(elapsed, 2),
        }

    # -- manifest-aware publish flow ----------------------------------------

    async def plan_publish_with_manifest(
        self,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        """Dry-run: generate a manifest, validate it, and plan the upload.

        This combines manifest generation, validation, and upload planning
        into a single plan dict that can be reviewed before execution.

        Args:
            spec: Full agent specification dictionary.

        Returns:
            A combined plan dict containing the generated manifest,
            validation results, and upload plan.
        """
        # Build manifest generator from spec
        generator = TeamsAppManifest(spec)
        self._manifest_generator = generator

        manifest = generator.generate()
        validation = generator.validate()

        # Plan the upload
        uploader = self._ensure_uploader()
        upload_plan = await uploader.plan_upload(manifest)

        return {
            "action": "publish_with_manifest",
            "dry_run": True,
            "success": True,
            "manifest": manifest,
            "manifest_json": generator.to_json(),
            "validation": validation,
            "upload_plan": upload_plan,
            "warnings": (
                validation.get("warnings", [])
                + (
                    ["Manifest validation failed; upload may be rejected."]
                    if not validation.get("valid", False)
                    else []
                )
            ),
            "errors": validation.get("errors", []),
        }

    async def apply_publish_with_manifest(
        self,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the manifest upload from a previously generated plan.

        Args:
            plan: The plan dict produced by ``plan_publish_with_manifest``.

        Returns:
            Result dict with upload status, manifest summary, and
            validation info.
        """
        start = time.perf_counter()

        validation = plan.get("validation", {})
        if not validation.get("valid", False):
            elapsed = (time.perf_counter() - start) * 1000
            return {
                "action": "publish_with_manifest",
                "dry_run": False,
                "success": False,
                "error": "Manifest validation failed. Fix errors before uploading.",
                "validation": validation,
                "duration_ms": round(elapsed, 2),
            }

        upload_plan = plan.get("upload_plan", {})
        uploader = self._ensure_uploader()
        upload_result = await uploader.apply_upload(upload_plan)

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "action": "publish_with_manifest",
            "dry_run": False,
            "success": upload_result.get("success", False),
            "upload_result": upload_result,
            "manifest_summary": upload_plan.get("details", {}).get("manifest_summary", {}),
            "validation": validation,
            "duration_ms": round(elapsed, 2),
        }


__all__ = [
    "CHANNEL_REQUIREMENTS",
    "TeamsAppManifest",
    "TeamsAppUploader",
    "TeamsPublisher",
]
