"""
Integration tests for the connector pipeline.

These tests spin up lightweight in-process HTTP servers that act as mock
source and destination endpoints.  The connector flow is run directly
(not via Prefect Cloud) so the full extract → transform → load → audit
path is exercised with real HTTP I/O but zero external infrastructure.

Requirements:
    pip install -e ".[test]"   (adds pytest, respx, pyyaml)
    pip install httpx prefect pydantic  (runtime deps)

Run all integration tests:
    pytest tests/connectors/test_integration.py -v

Run only the "simple" connector integration suite:
    pytest tests/connectors/test_integration.py -k simple -v
"""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest

from devflow.connector_scaffold import ConnectorSpec, scaffold_connector
from tests.connectors.conftest import (
    MockHTTPServer,
    assert_row_counts,
    assert_field_integrity,
)


# ---------------------------------------------------------------------------
# Helpers — build and import a transient connector package
# ---------------------------------------------------------------------------

def _build_and_import_connector(spec: ConnectorSpec, tmp_path: Path):
    """
    Scaffold the connector into tmp_path, add it to sys.path, and
    return the imported flow module.
    """
    # Write connector package under tmp_path/connectors/<name>/
    connector_dir = tmp_path / "connectors" / spec.name
    scaffold_connector(spec, out_dir=connector_dir)

    # Make the connectors package importable
    connectors_init = tmp_path / "connectors" / "__init__.py"
    if not connectors_init.exists():
        connectors_init.write_text("", encoding="utf-8")

    # Prepend tmp_path to sys.path so `import connectors.<name>.flow` works
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))

    module_name = f"connectors.{spec.name}.flow"
    # Re-import each time (tests may scaffold different connectors)
    if module_name in sys.modules:
        del sys.modules[module_name]
    schemas_module = f"connectors.{spec.name}.schemas"
    if schemas_module in sys.modules:
        del sys.modules[schemas_module]

    return importlib.import_module(module_name)


# ---------------------------------------------------------------------------
# Integration: simple passthrough connector
# ---------------------------------------------------------------------------

class TestSimpleConnectorIntegration:
    """
    End-to-end integration test for a generated passthrough connector.

    Topology:
        MockSourceServer  →  extract()  →  transform()  →  load()  →  MockDestServer
                                                              ↓
                                                           audit()
    """

    @pytest.fixture
    def simple_spec(self, simple_source_schema, simple_dest_schema, passthrough_transform_config):
        return ConnectorSpec.from_dicts(
            name="simple",
            source_schema=simple_source_schema,
            dest_schema=simple_dest_schema,
            transform_config=passthrough_transform_config,
        )

    def test_full_pipeline_row_count(
        self,
        simple_spec,
        sample_source_rows,
        mock_source_server,
        mock_dest_server,
        tmp_path,
    ):
        flow_mod = _build_and_import_connector(simple_spec, tmp_path)

        result = asyncio.run(
            flow_mod.connector_flow(
                source_url=mock_source_server.url("/records"),
                dest_url=mock_dest_server.url("/records"),
            )
        )

        assert result["extracted"] == len(sample_source_rows)
        assert result["loaded"] == len(sample_source_rows)

    def test_full_pipeline_dest_received_all_rows(
        self,
        simple_spec,
        sample_source_rows,
        mock_source_server,
        mock_dest_server,
        tmp_path,
    ):
        flow_mod = _build_and_import_connector(simple_spec, tmp_path)

        asyncio.run(
            flow_mod.connector_flow(
                source_url=mock_source_server.url("/records"),
                dest_url=mock_dest_server.url("/records"),
            )
        )

        assert_row_counts(
            sample_source_rows,
            mock_dest_server.received,
            context="simple connector",
        )

    def test_full_pipeline_id_integrity(
        self,
        simple_spec,
        sample_source_rows,
        mock_source_server,
        mock_dest_server,
        tmp_path,
    ):
        flow_mod = _build_and_import_connector(simple_spec, tmp_path)

        asyncio.run(
            flow_mod.connector_flow(
                source_url=mock_source_server.url("/records"),
                dest_url=mock_dest_server.url("/records"),
            )
        )

        expected_ids = [r["id"] for r in sample_source_rows]
        assert_field_integrity(mock_dest_server.received, "id", expected_ids)

    def test_full_pipeline_name_integrity(
        self,
        simple_spec,
        sample_source_rows,
        mock_source_server,
        mock_dest_server,
        tmp_path,
    ):
        flow_mod = _build_and_import_connector(simple_spec, tmp_path)

        asyncio.run(
            flow_mod.connector_flow(
                source_url=mock_source_server.url("/records"),
                dest_url=mock_dest_server.url("/records"),
            )
        )

        expected_names = [r["name"] for r in sample_source_rows]
        assert_field_integrity(mock_dest_server.received, "name", expected_names)


# ---------------------------------------------------------------------------
# Integration: empty source
# ---------------------------------------------------------------------------

class TestEmptySource:
    @pytest.fixture
    def simple_spec(self, simple_source_schema, simple_dest_schema, passthrough_transform_config):
        return ConnectorSpec.from_dicts(
            name="simple",
            source_schema=simple_source_schema,
            dest_schema=simple_dest_schema,
            transform_config=passthrough_transform_config,
        )

    def test_empty_source_produces_zero_rows(
        self, simple_spec, mock_dest_server, tmp_path
    ):
        flow_mod = _build_and_import_connector(simple_spec, tmp_path)

        with MockHTTPServer(rows=[]) as empty_source:
            result = asyncio.run(
                flow_mod.connector_flow(
                    source_url=empty_source.url("/records"),
                    dest_url=mock_dest_server.url("/records"),
                )
            )

        assert result["extracted"] == 0
        assert result["loaded"] == 0
        assert mock_dest_server.received == []


# ---------------------------------------------------------------------------
# Integration: source server error triggers retry
# ---------------------------------------------------------------------------

class TestSourceErrorHandling:
    @pytest.fixture
    def simple_spec(self, simple_source_schema, simple_dest_schema, passthrough_transform_config):
        return ConnectorSpec.from_dicts(
            name="simple",
            source_schema=simple_source_schema,
            dest_schema=simple_dest_schema,
            transform_config=passthrough_transform_config,
        )

    def test_unreachable_source_raises(self, simple_spec, mock_dest_server, tmp_path):
        flow_mod = _build_and_import_connector(simple_spec, tmp_path)

        # Port 1 is reserved and should be unreachable
        with pytest.raises(Exception):
            asyncio.run(
                flow_mod.connector_flow(
                    source_url="http://127.0.0.1:1/records",
                    dest_url=mock_dest_server.url("/records"),
                )
            )


# ---------------------------------------------------------------------------
# Integration: row count mismatch triggers audit failure
# ---------------------------------------------------------------------------

class TestAuditTask:
    def test_audit_passes_on_matching_counts(self, simple_connector_spec, tmp_path):
        flow_mod = _build_and_import_connector(simple_connector_spec, tmp_path)
        rows = [{"id": 1, "name": "A", "score": 1.0, "active": True}]
        # audit() is a sync task — call it directly to avoid Prefect overhead
        flow_mod.audit(rows, 1)   # no exception

    def test_audit_raises_on_mismatch(self, simple_connector_spec, tmp_path):
        flow_mod = _build_and_import_connector(simple_connector_spec, tmp_path)
        rows = [{"id": 1}, {"id": 2}]
        with pytest.raises(ValueError, match="Row count mismatch"):
            flow_mod.audit(rows, 1)


# ---------------------------------------------------------------------------
# Integration: MockHTTPServer standalone
# ---------------------------------------------------------------------------

class TestMockHTTPServer:
    def test_get_records_returns_rows(self):
        rows = [{"id": 1, "name": "x"}]
        with MockHTTPServer(rows=rows) as srv:
            import httpx
            resp = httpx.get(srv.url("/records"))
            data = resp.json()
        assert data["records"] == rows

    def test_post_records_stores_rows(self):
        with MockHTTPServer() as srv:
            import httpx
            payload = {"records": [{"id": 1, "name": "y"}]}
            httpx.post(srv.url("/records"), json=payload)
        assert srv.received == payload["records"]

    def test_port_zero_assigns_free_port(self):
        with MockHTTPServer(port=0) as srv:
            assert srv.port > 0

    def test_404_on_unknown_path(self):
        with MockHTTPServer() as srv:
            import httpx
            resp = httpx.get(srv.url("/unknown"))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# assert_row_counts helper
# ---------------------------------------------------------------------------

class TestAssertHelpers:
    def test_assert_row_counts_passes(self):
        assert_row_counts([1, 2, 3], [4, 5, 6])

    def test_assert_row_counts_fails_on_mismatch(self):
        with pytest.raises(AssertionError, match="Row count mismatch"):
            assert_row_counts([1, 2], [3])

    def test_assert_field_integrity_passes(self):
        rows = [{"id": 1}, {"id": 2}]
        assert_field_integrity(rows, "id", [1, 2])

    def test_assert_field_integrity_fails(self):
        rows = [{"id": 1}, {"id": 99}]
        with pytest.raises(AssertionError, match="mismatch"):
            assert_field_integrity(rows, "id", [1, 2])
