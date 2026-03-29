"""
Paperclip API adapter.

Wraps the Paperclip REST API (github.com/paperclipai/paperclip).
All Paperclip calls are isolated here — if the API changes, only this
module needs updating.

No Paperclip SDK dependency — plain httpx for async compatibility.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PaperclipError(Exception):
    """Base exception for Paperclip API errors."""


class PaperclipCheckoutConflict(PaperclipError):
    """
    409 — issue already checked out by another agent.
    Per Paperclip spec: never retry on 409.
    """


class PaperclipBudgetExceeded(PaperclipError):
    """Agent monthly budget hard-stop reached."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Agent:
    id: str
    name: str
    company_id: str
    role: str = ""


@dataclass
class Issue:
    id: str
    identifier: str       # human-readable, e.g. "REPO-42"
    title: str
    status: str           # unstarted | in_progress | completed | cancelled | blocked
    assignee_id: Optional[str] = None
    parent_id: Optional[str] = None
    project_id: str = ""


@dataclass
class Budget:
    agent_id: str
    monthly_limit: int    # tokens
    used: int             # tokens used this month

    @property
    def percent_used(self) -> float:
        if self.monthly_limit == 0:
            return 0.0
        return self.used / self.monthly_limit * 100

    @property
    def is_soft_alert(self) -> bool:
        return self.percent_used >= 80.0

    @property
    def is_exceeded(self) -> bool:
        return self.used >= self.monthly_limit > 0


@dataclass
class Approval:
    id: str
    status: str           # pending | approved | rejected
    issue_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

# Anthropic pricing per model (USD per million tokens).
# Update when Anthropic changes pricing.
_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6":             {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":           {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":            {"input":  0.80, "output":  4.00},
    "claude-haiku-4-5-20251001":   {"input":  0.80, "output":  4.00},
    # fallback for unknown/future models — use Opus pricing (conservative)
    "_default":                    {"input": 15.00, "output": 75.00},
}


def calculate_cost_cents(input_tokens: int, output_tokens: int, model: str) -> int:
    """
    Return cost in US cents (integer, minimum 1) for the given token counts.
    Falls back to _default pricing for unrecognised models so Paperclip never
    shows $0.00 for unknown models (addresses Paperclip issue #212).
    """
    rates = _PRICING.get(model, _PRICING["_default"])
    cost_usd = (
        input_tokens  * rates["input"] +
        output_tokens * rates["output"]
    ) / 1_000_000
    return max(1, round(cost_usd * 100))


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_RETRY_STATUSES = {500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0   # seconds; doubles each attempt


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class PaperclipClient:
    """
    Async HTTP adapter for the Paperclip REST API.

    Must be used as an async context manager:

        async with PaperclipClient(api_url, api_key, run_id) as pc:
            agent = await pc.get_agent()
    """

    def __init__(self, api_url: str, api_key: str, run_id: str = ""):
        self._url = api_url.rstrip("/")
        self._api_key = api_key
        self._run_id = run_id
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "PaperclipClient":
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._run_id:
            headers["X-Paperclip-Run-Id"] = self._run_id
        self._http = httpx.AsyncClient(
            base_url=self._url,
            headers=headers,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """
        Make an HTTP request with exponential backoff on 5xx.

        - 409 → PaperclipCheckoutConflict (never retry)
        - 5xx → retry up to _MAX_RETRIES times
        - Other 4xx → httpx.HTTPStatusError (caller handles)
        """
        if self._http is None:
            raise PaperclipError("PaperclipClient must be used as async context manager")

        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._http.request(method, path, **kwargs)
            except httpx.RequestError as exc:
                last_exc = PaperclipError(f"Network error talking to Paperclip: {exc}")
                await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                continue

            if resp.status_code == 409:
                raise PaperclipCheckoutConflict(
                    "Issue already checked out by another agent (409). "
                    "Per Paperclip spec: do not retry."
                )

            if resp.status_code in _RETRY_STATUSES:
                last_exc = PaperclipError(
                    f"Paperclip server error {resp.status_code} "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}): {resp.text[:200]}"
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                raise last_exc

            resp.raise_for_status()
            return resp.json() if resp.content else {}

        raise last_exc

    # ------------------------------------------------------------------
    # Identity / health
    # ------------------------------------------------------------------

    async def get_agent(self) -> Agent:
        """Confirm this agent's identity, company, and role."""
        data = await self._request("GET", "/api/agents/me")
        return Agent(
            id=data["id"],
            name=data.get("name", ""),
            company_id=data.get("companyId", ""),
            role=data.get("role", ""),
        )

    async def check_health(self) -> bool:
        """Return True if the Paperclip server is reachable."""
        if self._http is None:
            return False
        try:
            resp = await self._http.get("/api/health")
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    async def list_issues(
        self,
        company_id: str,
        status: str = "todo,unstarted,in_progress",
        limit: int = 50,
    ) -> list[Issue]:
        """Fetch open issues for a company. Filtered and capped for performance."""
        data = await self._request(
            "GET",
            f"/api/companies/{company_id}/issues",
            params={"status": status, "limit": limit},
        )
        rows = data if isinstance(data, list) else data.get("issues", [])
        return [_parse_issue(r) for r in rows]

    async def get_issue(self, issue_id: str) -> Issue:
        data = await self._request("GET", f"/api/issues/{issue_id}")
        return _parse_issue(data)

    async def checkout_issue(self, issue_id: str) -> Issue:
        """
        Atomically lock this issue for the current agent.
        Raises PaperclipCheckoutConflict if already taken — NEVER retry.
        """
        data = await self._request("POST", f"/api/issues/{issue_id}/checkout")
        return _parse_issue(data)

    async def update_issue(
        self,
        issue_id: str,
        status: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Issue:
        """
        Update issue status and/or post a comment.

        The Paperclip PATCH endpoint accepts an optional ``comment`` field
        so both the status update and the comment land in the same atomic
        request.  A separate POST to /comments is only used as a fallback
        when we want to add a comment without changing status.
        """
        payload: dict = {}
        if status:
            payload["status"] = status
        if comment:
            payload["comment"] = comment

        data = await self._request("PATCH", f"/api/issues/{issue_id}", json=payload)
        return _parse_issue(data)

    async def post_comment(self, issue_id: str, body: str) -> None:
        """Post a standalone comment without changing issue status."""
        await self._request(
            "POST",
            f"/api/issues/{issue_id}/comments",
            json={"body": body},
        )

    async def create_issue(
        self,
        project_id: str,
        title: str,
        body: str = "",
        assignee_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Issue:
        """Create a new issue (or sub-issue via parent_id)."""
        payload: dict = {"title": title}
        if body:
            payload["description"] = body
        if assignee_id:
            payload["assigneeId"] = assignee_id
        if parent_id:
            payload["parentId"] = parent_id

        data = await self._request(
            "POST",
            f"/api/projects/{project_id}/issues",
            json=payload,
        )
        return _parse_issue(data)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def get_document(self, issue_id: str, key: str) -> dict:
        """
        Fetch an issue document by key (e.g. "plan", "state").
        Returns the raw document dict. Raises httpx.HTTPStatusError on 404.
        """
        return await self._request("GET", f"/api/issues/{issue_id}/documents/{key}")

    async def put_document(
        self,
        issue_id: str,
        key: str,
        title: str,
        body: str,
        format: str = "markdown",
        base_revision_id: Optional[str] = None,
    ) -> dict:
        """
        Create or update an issue document.
        Fetch the existing document first and pass its revision ID to avoid conflicts.
        """
        payload: dict = {
            "title": title,
            "format": format,
            "body": body,
            "baseRevisionId": base_revision_id,
        }
        return await self._request(
            "PUT",
            f"/api/issues/{issue_id}/documents/{key}",
            json=payload,
        )

    # ------------------------------------------------------------------
    # State checkpointing
    # ------------------------------------------------------------------

    async def load_state(self, issue_id: str) -> dict:
        """
        Read the JSON state document (key: "state") from an issue.
        Returns an empty dict when no state document exists yet.
        """
        try:
            doc = await self.get_document(issue_id, "state")
            body = doc.get("body", "{}")
            import json
            return json.loads(body) if body else {}
        except Exception:
            return {}

    async def save_state(self, issue_id: str, state: dict) -> None:
        """
        Persist phase progress to the issue's "state" document so it survives restarts.
        Fetches the current revision ID first to avoid conflict errors.
        """
        import json
        base_revision_id: Optional[str] = None
        try:
            existing = await self.get_document(issue_id, "state")
            base_revision_id = existing.get("revisionId")
        except Exception:
            pass

        body = json.dumps(state, indent=2)
        await self.put_document(
            issue_id=issue_id,
            key="state",
            title="State",
            body=body,
            format="json",
            base_revision_id=base_revision_id,
        )

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------

    async def upload_attachment(
        self,
        company_id: str,
        issue_id: str,
        file_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        """
        Upload a file attachment to an issue.
        Returns the created attachment dict with at least {"id": ..., "url": ...}.
        """
        if self._http is None:
            raise PaperclipError("PaperclipClient must be used as async context manager")

        files = {"file": (file_path, content, content_type)}
        resp = await self._http.post(
            f"/api/companies/{company_id}/issues/{issue_id}/attachments",
            files=files,
        )
        if resp.status_code == 409:
            raise PaperclipCheckoutConflict("Attachment conflict (409).")
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------
    # Approvals
    # ------------------------------------------------------------------

    async def get_approval(self, approval_id: str) -> Approval:
        data = await self._request("GET", f"/api/approvals/{approval_id}")
        issue_ids = [i["id"] for i in data.get("issues", [])]
        return Approval(
            id=data["id"],
            status=data.get("status", "pending"),
            issue_ids=issue_ids,
        )

    # ------------------------------------------------------------------
    # Budget & cost reporting
    # ------------------------------------------------------------------

    async def get_budget(self, agent_id: str) -> Budget:
        data = await self._request("GET", f"/api/agents/{agent_id}/budget")
        return Budget(
            agent_id=agent_id,
            monthly_limit=data.get("monthlyLimit", 0),
            used=data.get("used", 0),
        )

    async def report_cost(
        self,
        company_id: str,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        model: str,
        cost_cents: int,
    ) -> None:
        """
        Report actual token usage to Paperclip so budget dashboards show
        real numbers instead of $0.00.

        Endpoint: POST /api/companies/{id}/cost-events
        """
        await self._request(
            "POST",
            f"/api/companies/{company_id}/cost-events",
            json={
                "agentId": agent_id,
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "model": model,
                "costCents": cost_cents,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def client_from_env(run_id: str = "") -> Optional[PaperclipClient]:
    """
    Build a PaperclipClient from environment variables.
    Returns None when PAPERCLIP_API_KEY is not set (degraded / no-Paperclip mode).

    Env vars read:
      PAPERCLIP_API_KEY   — required for Paperclip integration
      PAPERCLIP_API_URL   — default http://localhost:3100
      PAPERCLIP_RUN_ID    — injected by Paperclip during heartbeat runs
    """
    api_key = os.environ.get("PAPERCLIP_API_KEY", "")
    if not api_key:
        return None
    api_url = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")
    effective_run_id = run_id or os.environ.get("PAPERCLIP_RUN_ID", "")
    return PaperclipClient(api_url=api_url, api_key=api_key, run_id=effective_run_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_issue(data: dict) -> Issue:
    return Issue(
        id=data["id"],
        identifier=data.get("identifier", data["id"]),
        title=data.get("title", ""),
        status=data.get("status", "unstarted"),
        assignee_id=data.get("assigneeId"),
        parent_id=data.get("parentId"),
        project_id=data.get("projectId", ""),
    )
