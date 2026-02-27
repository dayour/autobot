"""Tests for Teams app manifest generation and upload."""

from __future__ import annotations

import json
import uuid

import pytest

from autobot.tools.teams_publish import (
    TeamsAppManifest,
    TeamsAppUploader,
    TeamsPublisher,
)
from autobot.tools.dataverse_api import MockHttpClient, HttpResponse


@pytest.fixture
def spec() -> dict:
    return {
        "name": "Contoso IT Helpdesk Agent",
        "description": "An AI agent that helps with IT support issues.",
        "publisher": {
            "name": "Contoso IT",
            "prefix": "contit",
            "websiteUrl": "https://contoso.com",
            "privacyUrl": "https://contoso.com/privacy",
            "termsOfUseUrl": "https://contoso.com/terms",
        },
        "channels": ["teams", "m365_copilot"],
        "security": {
            "authenticationMode": "entra_id",
            "entraAppId": "00000000-1111-2222-3333-444444444444",
        },
        "alm": {"solutionVersion": "1.2.3.0"},
    }


class TestTeamsAppManifest:
    def test_generate_produces_valid_manifest(self, spec):
        gen = TeamsAppManifest(spec)
        manifest = gen.generate()
        assert manifest["$schema"] == TeamsAppManifest.SCHEMA_URL
        assert manifest["manifestVersion"] == TeamsAppManifest.MANIFEST_VERSION

    def test_manifest_has_name_and_description(self, spec):
        manifest = TeamsAppManifest(spec).generate()
        assert manifest["name"]["short"] == "Contoso IT Helpdesk Agent"
        assert "IT support" in manifest["description"]["short"]

    def test_manifest_has_developer_info(self, spec):
        manifest = TeamsAppManifest(spec).generate()
        assert manifest["developer"]["name"] == "Contoso IT"
        assert manifest["developer"]["websiteUrl"] == "https://contoso.com"

    def test_manifest_has_bot(self, spec):
        manifest = TeamsAppManifest(spec).generate()
        assert len(manifest["bots"]) == 1
        bot = manifest["bots"][0]
        assert "personal" in bot["scopes"]
        # Bot ID should be a valid UUID
        uuid.UUID(bot["botId"])

    def test_manifest_has_web_app_info(self, spec):
        manifest = TeamsAppManifest(spec).generate()
        assert manifest["webApplicationInfo"]["id"] == "00000000-1111-2222-3333-444444444444"

    def test_deterministic_bot_id(self, spec):
        """Bot ID should be deterministic (UUID v5) from agent name."""
        m1 = TeamsAppManifest(spec).generate()
        m2 = TeamsAppManifest(spec).generate()
        assert m1["bots"][0]["botId"] == m2["bots"][0]["botId"]

    def test_validate_passes_on_good_spec(self, spec):
        validation = TeamsAppManifest(spec).validate()
        assert validation["valid"] is True
        assert len(validation["errors"]) == 0

    def test_validate_catches_empty_name(self):
        bad_spec = {"name": "", "description": ""}
        validation = TeamsAppManifest(bad_spec).validate()
        # Empty name and description should trigger validation errors
        assert validation["valid"] is False
        assert len(validation["errors"]) > 0

    def test_to_json_is_valid_json(self, spec):
        gen = TeamsAppManifest(spec)
        text = gen.to_json()
        parsed = json.loads(text)
        assert parsed["manifestVersion"] == TeamsAppManifest.MANIFEST_VERSION

    def test_version_from_alm(self, spec):
        manifest = TeamsAppManifest(spec).generate()
        assert manifest["version"] == "1.2.3.0"


class TestTeamsAppUploader:
    @pytest.fixture
    def mock_http(self) -> MockHttpClient:
        return MockHttpClient()

    @pytest.fixture
    def uploader(self, mock_http) -> TeamsAppUploader:
        return TeamsAppUploader(http_client=mock_http, access_token="test-token")

    @pytest.mark.asyncio
    async def test_plan_check_existing(self, uploader):
        plan = await uploader.plan_check_existing("app-id-123")
        assert plan["action"] == "check_existing_teams_app"
        assert plan["dry_run"] is True
        assert "externalId" in plan["details"]["url"]

    @pytest.mark.asyncio
    async def test_apply_check_existing(self, uploader):
        plan = await uploader.plan_check_existing("app-id-123")
        result = await uploader.apply_check_existing(plan)
        assert result["dry_run"] is False
        assert "exists" in result

    @pytest.mark.asyncio
    async def test_plan_upload(self, uploader, spec):
        manifest = TeamsAppManifest(spec).generate()
        plan = await uploader.plan_upload(manifest)
        assert plan["action"] == "upload_teams_app"
        assert plan["dry_run"] is True
        assert "manifest_summary" in plan["details"]

    @pytest.mark.asyncio
    async def test_apply_upload_creates_new(self, uploader, spec):
        manifest = TeamsAppManifest(spec).generate()
        plan = await uploader.plan_upload(manifest)
        result = await uploader.apply_upload(plan)
        assert result["dry_run"] is False
        assert result["success"] is True
        assert result["operation"] == "created"


class TestTeamsPublisherWithManifest:
    @pytest.mark.asyncio
    async def test_plan_publish_with_manifest(self, spec):
        pub = TeamsPublisher()
        plan = await pub.plan_publish_with_manifest(spec)
        assert plan["action"] == "publish_with_manifest"
        assert plan["dry_run"] is True
        assert "manifest" in plan
        assert "validation" in plan
        assert "upload_plan" in plan

    @pytest.mark.asyncio
    async def test_apply_publish_with_manifest(self, spec):
        pub = TeamsPublisher()
        plan = await pub.plan_publish_with_manifest(spec)
        result = await pub.apply_publish_with_manifest(plan)
        assert result["dry_run"] is False
        assert result["success"] is True
        assert "upload_result" in result
