"""
Unit tests for devflow/paperclip.py.

Run from ~/ai-dev-flow:
    pip install -e ".[test]"
    pytest tests/test_paperclip.py -v

Uses respx to mock httpx calls — no live Paperclip server required.
"""
from __future__ import annotations

import pytest
import respx
import httpx

from devflow.paperclip import (
    PaperclipClient,
    PaperclipCheckoutConflict,
    PaperclipError,
    Agent,
    Issue,
    Budget,
    calculate_cost_cents,
    client_from_env,
)

# Async tests are marked individually; sync tests have no asyncio mark.

BASE = "http://localhost:3100"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client() -> PaperclipClient:
    return PaperclipClient(api_url=BASE, api_key="test-key", run_id="run-123")


def _issue_payload(**overrides) -> dict:
    base = {
        "id": "issue-1",
        "identifier": "REPO-1",
        "title": "Add OAuth",
        "status": "unstarted",
        "projectId": "proj-1",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# calculate_cost_cents
# ---------------------------------------------------------------------------

class TestCalculateCostCents:
    def test_opus_pricing(self):
        # 1M input + 1M output at $15/$75 per Mtok = $90 = 9000 cents
        assert calculate_cost_cents(1_000_000, 1_000_000, "claude-opus-4-6") == 9000

    def test_sonnet_pricing(self):
        # 1M input + 1M output at $3/$15 per Mtok = $18 = 1800 cents
        assert calculate_cost_cents(1_000_000, 1_000_000, "claude-sonnet-4-6") == 1800

    def test_unknown_model_falls_back_to_default(self):
        # Unknown model uses Opus pricing (conservative, not $0.00)
        result = calculate_cost_cents(1_000_000, 1_000_000, "gpt-99-ultra")
        assert result == 9000

    def test_minimum_one_cent(self):
        # Tiny usage still returns at least 1 cent
        assert calculate_cost_cents(1, 1, "claude-opus-4-6") >= 1

    def test_zero_tokens_minimum(self):
        assert calculate_cost_cents(0, 0, "claude-opus-4-6") >= 1

    def test_realistic_request(self):
        # 2000 input, 500 output on Opus → should be a small number > 0
        result = calculate_cost_cents(2000, 500, "claude-opus-4-6")
        assert result >= 1


# ---------------------------------------------------------------------------
# get_agent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetAgent:
    @respx.mock
    async def test_success(self):
        respx.get(f"{BASE}/api/agents/me").mock(return_value=httpx.Response(200, json={
            "id": "agent-1",
            "name": "devflow-feature",
            "companyId": "co-1",
            "role": "engineer",
        }))
        async with _client() as pc:
            agent = await pc.get_agent()

        assert isinstance(agent, Agent)
        assert agent.id == "agent-1"
        assert agent.company_id == "co-1"

    @respx.mock
    async def test_auth_failure_raises(self):
        respx.get(f"{BASE}/api/agents/me").mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        async with _client() as pc:
            with pytest.raises(httpx.HTTPStatusError):
                await pc.get_agent()


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCheckHealth:
    @respx.mock
    async def test_healthy(self):
        respx.get(f"{BASE}/api/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        async with _client() as pc:
            assert await pc.check_health() is True

    @respx.mock
    async def test_unhealthy(self):
        respx.get(f"{BASE}/api/health").mock(return_value=httpx.Response(503))
        async with _client() as pc:
            assert await pc.check_health() is False

    async def test_unreachable(self):
        pc = PaperclipClient(api_url="http://127.0.0.1:19999", api_key="x")
        async with pc:
            assert await pc.check_health() is False


# ---------------------------------------------------------------------------
# checkout_issue — 409 conflict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCheckoutIssue:
    @respx.mock
    async def test_success(self):
        respx.post(f"{BASE}/api/issues/issue-1/checkout").mock(
            return_value=httpx.Response(200, json=_issue_payload(status="in_progress"))
        )
        async with _client() as pc:
            issue = await pc.checkout_issue("issue-1")

        assert issue.status == "in_progress"

    @respx.mock
    async def test_conflict_raises_checkout_conflict(self):
        respx.post(f"{BASE}/api/issues/issue-1/checkout").mock(
            return_value=httpx.Response(409, json={"error": "already checked out"})
        )
        async with _client() as pc:
            with pytest.raises(PaperclipCheckoutConflict):
                await pc.checkout_issue("issue-1")

    @respx.mock
    async def test_conflict_does_not_retry(self):
        """409 must not be retried — only one request should be made."""
        route = respx.post(f"{BASE}/api/issues/issue-1/checkout").mock(
            return_value=httpx.Response(409, json={"error": "taken"})
        )
        async with _client() as pc:
            with pytest.raises(PaperclipCheckoutConflict):
                await pc.checkout_issue("issue-1")

        assert route.call_count == 1


# ---------------------------------------------------------------------------
# 5xx retry behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRetry:
    @respx.mock
    async def test_retries_on_500_then_succeeds(self):
        route = respx.get(f"{BASE}/api/agents/me").mock(side_effect=[
            httpx.Response(500, text="internal error"),
            httpx.Response(500, text="internal error"),
            httpx.Response(200, json={"id": "a1", "name": "bot", "companyId": "c1"}),
        ])

        # Patch asyncio.sleep so the test doesn't actually wait
        import unittest.mock as mock
        with mock.patch("devflow.paperclip.asyncio.sleep", return_value=None):
            async with _client() as pc:
                agent = await pc.get_agent()

        assert agent.id == "a1"
        assert route.call_count == 3

    @respx.mock
    async def test_raises_after_max_retries(self):
        respx.get(f"{BASE}/api/agents/me").mock(
            return_value=httpx.Response(503, text="service unavailable")
        )
        import unittest.mock as mock
        with mock.patch("devflow.paperclip.asyncio.sleep", return_value=None):
            async with _client() as pc:
                with pytest.raises(PaperclipError):
                    await pc.get_agent()


# ---------------------------------------------------------------------------
# create_issue (with parentId for sub-issues)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCreateIssue:
    @respx.mock
    async def test_creates_sub_issue_with_parent_id(self):
        route = respx.post(f"{BASE}/api/projects/proj-1/issues").mock(
            return_value=httpx.Response(200, json=_issue_payload(
                id="issue-2", title="Grill", parentId="issue-1"
            ))
        )
        async with _client() as pc:
            issue = await pc.create_issue(
                project_id="proj-1",
                title="Grill",
                parent_id="issue-1",
                assignee_id="agent-1",
            )

        assert issue.parent_id == "issue-1"
        sent = route.calls[0].request
        import json
        body = json.loads(sent.content)
        assert body["parentId"] == "issue-1"
        assert body["assigneeId"] == "agent-1"

    @respx.mock
    async def test_creates_top_level_issue_no_parent(self):
        route = respx.post(f"{BASE}/api/projects/proj-1/issues").mock(
            return_value=httpx.Response(200, json=_issue_payload())
        )
        async with _client() as pc:
            await pc.create_issue(project_id="proj-1", title="Feature X")

        import json
        body = json.loads(route.calls[0].request.content)
        assert "parentId" not in body


# ---------------------------------------------------------------------------
# report_cost
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReportCost:
    @respx.mock
    async def test_sends_correct_payload(self):
        route = respx.post(f"{BASE}/api/companies/co-1/cost-events").mock(
            return_value=httpx.Response(200, json={})
        )
        async with _client() as pc:
            await pc.report_cost(
                company_id="co-1",
                agent_id="agent-1",
                input_tokens=1000,
                output_tokens=500,
                model="claude-opus-4-6",
                cost_cents=42,
            )

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["agentId"] == "agent-1"
        assert body["inputTokens"] == 1000
        assert body["outputTokens"] == 500
        assert body["model"] == "claude-opus-4-6"
        assert body["costCents"] == 42
        assert "timestamp" in body

    @respx.mock
    async def test_run_id_header_included(self):
        route = respx.post(f"{BASE}/api/companies/co-1/cost-events").mock(
            return_value=httpx.Response(200, json={})
        )
        async with _client() as pc:
            await pc.report_cost("co-1", "agent-1", 100, 50, "claude-opus-4-6", 1)

        assert route.calls[0].request.headers.get("x-paperclip-run-id") == "run-123"


# ---------------------------------------------------------------------------
# client_from_env
# ---------------------------------------------------------------------------

class TestClientFromEnv:
    def test_returns_none_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
        assert client_from_env() is None

    def test_returns_client_when_key_set(self, monkeypatch):
        monkeypatch.setenv("PAPERCLIP_API_KEY", "sk-test")
        monkeypatch.setenv("PAPERCLIP_API_URL", "http://localhost:3100")
        pc = client_from_env()
        assert pc is not None
        assert isinstance(pc, PaperclipClient)

    def test_uses_custom_url(self, monkeypatch):
        monkeypatch.setenv("PAPERCLIP_API_KEY", "sk-test")
        monkeypatch.setenv("PAPERCLIP_API_URL", "http://myserver:4000")
        pc = client_from_env()
        assert pc._url == "http://myserver:4000"

    def test_run_id_from_env(self, monkeypatch):
        monkeypatch.setenv("PAPERCLIP_API_KEY", "sk-test")
        monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-xyz")
        pc = client_from_env()
        assert pc._run_id == "run-xyz"

    def test_run_id_parameter_overrides_env(self, monkeypatch):
        monkeypatch.setenv("PAPERCLIP_API_KEY", "sk-test")
        monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-from-env")
        pc = client_from_env(run_id="run-explicit")
        assert pc._run_id == "run-explicit"

    def test_returns_none_when_only_company_id_set(self, monkeypatch):
        """PAPERCLIP_COMPANY_ID alone is not sufficient — API key is required."""
        monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
        monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "co-123")
        assert client_from_env() is None


# ---------------------------------------------------------------------------
# get_document / put_document
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDocuments:
    @respx.mock
    async def test_get_document_success(self):
        respx.get(f"{BASE}/api/issues/issue-1/documents/plan").mock(
            return_value=httpx.Response(200, json={
                "id": "doc-1",
                "key": "plan",
                "title": "Plan",
                "body": "# Plan\n\nDo the thing.",
                "format": "markdown",
                "revisionId": "rev-abc",
            })
        )
        async with _client() as pc:
            doc = await pc.get_document("issue-1", "plan")

        assert doc["key"] == "plan"
        assert "# Plan" in doc["body"]
        assert doc["revisionId"] == "rev-abc"

    @respx.mock
    async def test_put_document_creates_new(self):
        route = respx.put(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(200, json={
                "id": "doc-2",
                "key": "state",
                "title": "State",
                "body": '{"phase": "tdd"}',
                "format": "json",
                "revisionId": "rev-1",
            })
        )
        async with _client() as pc:
            doc = await pc.put_document(
                issue_id="issue-1",
                key="state",
                title="State",
                body='{"phase": "tdd"}',
                format="json",
            )

        assert doc["key"] == "state"
        sent = route.calls[0].request
        import json
        body = json.loads(sent.content)
        assert body["title"] == "State"
        assert body["format"] == "json"
        assert body["baseRevisionId"] is None

    @respx.mock
    async def test_put_document_sends_base_revision_id(self):
        route = respx.put(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(200, json={"key": "state", "revisionId": "rev-2"})
        )
        async with _client() as pc:
            await pc.put_document(
                issue_id="issue-1",
                key="state",
                title="State",
                body="{}",
                base_revision_id="rev-1",
            )

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["baseRevisionId"] == "rev-1"


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestStateCheckpointing:
    @respx.mock
    async def test_load_state_parses_json(self):
        respx.get(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(200, json={
                "key": "state",
                "body": '{"phase": "qa", "done": true}',
                "revisionId": "rev-x",
            })
        )
        async with _client() as pc:
            state = await pc.load_state("issue-1")

        assert state == {"phase": "qa", "done": True}

    @respx.mock
    async def test_load_state_returns_empty_on_404(self):
        respx.get(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        async with _client() as pc:
            state = await pc.load_state("issue-1")

        assert state == {}

    @respx.mock
    async def test_save_state_fetches_revision_then_puts(self):
        respx.get(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(200, json={
                "key": "state",
                "body": "{}",
                "revisionId": "rev-99",
            })
        )
        put_route = respx.put(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(200, json={"key": "state", "revisionId": "rev-100"})
        )
        async with _client() as pc:
            await pc.save_state("issue-1", {"phase": "deploy"})

        import json
        body = json.loads(put_route.calls[0].request.content)
        assert json.loads(body["body"]) == {"phase": "deploy"}
        assert body["baseRevisionId"] == "rev-99"

    @respx.mock
    async def test_save_state_works_when_no_prior_doc(self):
        """save_state should succeed even if the state document doesn't exist yet."""
        respx.get(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        put_route = respx.put(f"{BASE}/api/issues/issue-1/documents/state").mock(
            return_value=httpx.Response(200, json={"key": "state", "revisionId": "rev-1"})
        )
        async with _client() as pc:
            await pc.save_state("issue-1", {"phase": "feature"})

        import json
        body = json.loads(put_route.calls[0].request.content)
        assert body["baseRevisionId"] is None


# ---------------------------------------------------------------------------
# upload_attachment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestUploadAttachment:
    @respx.mock
    async def test_uploads_file_and_returns_attachment(self):
        route = respx.post(f"{BASE}/api/companies/co-1/issues/issue-1/attachments").mock(
            return_value=httpx.Response(200, json={
                "id": "att-1",
                "filename": "evidence.md",
                "url": "http://localhost:3100/files/att-1",
            })
        )
        async with _client() as pc:
            result = await pc.upload_attachment(
                company_id="co-1",
                issue_id="issue-1",
                file_path="evidence.md",
                content=b"# Evidence\nAll tests pass.",
                content_type="text/markdown",
            )

        assert result["id"] == "att-1"
        assert route.call_count == 1

    @respx.mock
    async def test_upload_conflict_raises(self):
        respx.post(f"{BASE}/api/companies/co-1/issues/issue-1/attachments").mock(
            return_value=httpx.Response(409, json={"error": "conflict"})
        )
        async with _client() as pc:
            with pytest.raises(PaperclipCheckoutConflict):
                await pc.upload_attachment("co-1", "issue-1", "f.txt", b"data")
