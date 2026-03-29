"""
Shared fixtures for connector unit and integration tests.

Provides:
  - Schema fixture helpers (build_source_schema, build_dest_schema)
  - In-process mock HTTP server (MockSourceServer, MockDestServer)
  - ConnectorSpec factory fixture
  - Row-count assertion helper

Run all connector tests:
    pytest tests/connectors/ -v
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Generator, Any
from unittest.mock import patch

import pytest

from devflow.connector_scaffold import ConnectorSpec, FieldDef, TransformRule


# ---------------------------------------------------------------------------
# Schema / spec fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_source_schema() -> dict:
    """Minimal JSON Schema with a few primitive fields."""
    return {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id":    {"type": "integer", "description": "Primary key"},
            "name":  {"type": "string",  "description": "Display name"},
            "score": {"type": "number",  "description": "Optional score"},
            "active":{"type": "boolean", "description": "Active flag"},
        },
    }


@pytest.fixture
def simple_dest_schema() -> dict:
    return {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id":    {"type": "integer"},
            "name":  {"type": "string"},
            "score": {"type": "number"},
            "active":{"type": "boolean"},
        },
    }


@pytest.fixture
def passthrough_transform_config() -> dict:
    """Transform config that maps every field 1-to-1."""
    return {
        "rules": [
            {"source": "id",     "dest": "id"},
            {"source": "name",   "dest": "name"},
            {"source": "score",  "dest": "score"},
            {"source": "active", "dest": "active"},
        ]
    }


@pytest.fixture
def simple_connector_spec(
    simple_source_schema,
    simple_dest_schema,
    passthrough_transform_config,
) -> ConnectorSpec:
    return ConnectorSpec.from_dicts(
        name="simple",
        source_schema=simple_source_schema,
        dest_schema=simple_dest_schema,
        transform_config=passthrough_transform_config,
    )


@pytest.fixture
def sample_source_rows() -> list[dict]:
    return [
        {"id": 1, "name": "Alice", "score": 9.5,  "active": True},
        {"id": 2, "name": "Bob",   "score": 7.2,  "active": False},
        {"id": 3, "name": "Carol", "score": None,  "active": True},
    ]


@pytest.fixture
def sample_dest_rows() -> list[dict]:
    return [
        {"id": 1, "name": "Alice", "score": 9.5,  "active": True},
        {"id": 2, "name": "Bob",   "score": 7.2,  "active": False},
        {"id": 3, "name": "Carol", "score": None,  "active": True},
    ]


# ---------------------------------------------------------------------------
# Row-count assertion helper
# ---------------------------------------------------------------------------

def assert_row_counts(extracted: list, loaded: list, *, context: str = "") -> None:
    """
    Assert that extracted and loaded row counts match.
    Raises AssertionError with a helpful message when they differ.
    """
    tag = f" [{context}]" if context else ""
    assert len(extracted) == len(loaded), (
        f"Row count mismatch{tag}: extracted {len(extracted)} but loaded {len(loaded)}"
    )


def assert_field_integrity(rows: list[dict], field: str, expected_values: list) -> None:
    """Assert that `field` in each row matches the corresponding expected value."""
    for i, (row, exp) in enumerate(zip(rows, expected_values)):
        assert row.get(field) == exp, (
            f"Field '{field}' mismatch at row {i}: got {row.get(field)!r}, expected {exp!r}"
        )


# ---------------------------------------------------------------------------
# Schema-file fixtures (write temp JSON schema files for CLI tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def source_schema_file(tmp_path, simple_source_schema) -> Path:
    p = tmp_path / "source_schema.json"
    p.write_text(json.dumps(simple_source_schema), encoding="utf-8")
    return p


@pytest.fixture
def dest_schema_file(tmp_path, simple_dest_schema) -> Path:
    p = tmp_path / "dest_schema.json"
    p.write_text(json.dumps(simple_dest_schema), encoding="utf-8")
    return p


@pytest.fixture
def transform_config_file(tmp_path, passthrough_transform_config) -> Path:
    try:
        import yaml
        p = tmp_path / "transform.yaml"
        p.write_text(yaml.dump(passthrough_transform_config), encoding="utf-8")
        return p
    except ImportError:
        pytest.skip("pyyaml not installed")


# ---------------------------------------------------------------------------
# In-process mock HTTP servers
# ---------------------------------------------------------------------------

class _MockHTTPHandler(BaseHTTPRequestHandler):
    """Minimal handler — serves GET /records and accepts POST /records."""

    def log_message(self, *_):
        pass  # silence default stderr output during tests

    def do_GET(self):
        if self.path == "/records":
            payload = json.dumps({"records": self.server.rows}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/records":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            received = data.get("records", [])
            self.server.received.extend(received)
            resp = json.dumps({"written": len(received)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_response(404)
            self.end_headers()


class MockHTTPServer:
    """
    Lightweight in-process HTTP server for integration testing.

    Usage:
        with MockHTTPServer(rows=[...]) as srv:
            url = srv.url("/records")
            ...
        written = srv.received   # rows POSTed to /records
    """

    def __init__(self, rows: list[dict] | None = None, port: int = 0):
        self.rows: list[dict] = rows or []
        self.received: list[dict] = []
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "MockHTTPServer":
        self._server = HTTPServer(("127.0.0.1", self._port), _MockHTTPHandler)
        self._server.rows = self.rows          # type: ignore[attr-defined]
        self._server.received = self.received  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        if self._server:
            self._server.shutdown()

    @property
    def port(self) -> int:
        assert self._server, "Server not started"
        return self._server.server_address[1]

    def url(self, path: str = "") -> str:
        return f"http://127.0.0.1:{self.port}{path}"


@pytest.fixture
def mock_source_server(sample_source_rows) -> Generator[MockHTTPServer, None, None]:
    with MockHTTPServer(rows=sample_source_rows) as srv:
        yield srv


@pytest.fixture
def mock_dest_server() -> Generator[MockHTTPServer, None, None]:
    with MockHTTPServer() as srv:
        yield srv
