"""
Eval test suite for the connector builder workflow.

This eval validates that the connector builder (devflow.connector_scaffold)
consistently produces connectors that follow the exchange rates reference
pattern — regardless of which connector is being built.

Pattern reference: ~/connector/connector/exchangeratesapi.py
Scaffold reference: devflow/connector_scaffold.py

Run:
    pytest tests/connectors/test_eval_connector_builder.py -v

What this eval checks
---------------------
1. Pattern conformance — generated flow.py structurally matches the exchange
   rates reference pattern (Prefect decorators, task signatures, retry config,
   ETL task names, async/sync contract).
2. Schema conformance — generated schemas.py defines Pydantic BaseModel classes
   with the correct field names and Python types.
3. Exchange rates end-to-end — a spec mirroring the real exchangeratesapi schema
   runs the full pipeline and preserves all primary-key fields (base, date, target)
   and the conversion rate through extract → transform → load → audit.
4. Scaffold idempotency — scaffolding the same spec twice produces byte-for-byte
   identical output; running the pipeline twice on the same data loads the same
   row count each time.
5. Multi-connector regression — pattern and syntax checks run across N different
   connector specs so new connectors cannot silently break the reference pattern
   (add entries to ADDITIONAL_SPECS to extend coverage).
"""
from __future__ import annotations

import ast
import asyncio
import importlib
import sys
from pathlib import Path

import pytest

from devflow.connector_scaffold import (
    ConnectorSpec,
    generate_flow,
    generate_schemas,
    scaffold_connector,
)
from tests.connectors.conftest import (
    MockHTTPServer,
    assert_field_integrity,
    assert_row_counts,
)


# ---------------------------------------------------------------------------
# Reference data — exchange rates (mirrors ~/connector/connector/exchangeratesapi.py)
# Primary key: (base, date, target)
# ---------------------------------------------------------------------------

EXCHANGERATES_SOURCE_SCHEMA = {
    "type": "object",
    "required": ["base", "date", "target", "conversion"],
    "properties": {
        "base":       {"type": "string", "description": "Base currency code (e.g. USD)"},
        "date":       {"type": "string", "description": "Rate date (YYYY-MM-DD)"},
        "target":     {"type": "string", "description": "Target currency code"},
        "conversion": {"type": "number", "description": "Conversion rate from base to target"},
    },
}

EXCHANGERATES_DEST_SCHEMA = {
    "type": "object",
    "required": ["base", "date", "target", "conversion"],
    "properties": {
        "base":       {"type": "string"},
        "date":       {"type": "string"},
        "target":     {"type": "string"},
        "conversion": {"type": "number"},
    },
}

EXCHANGERATES_SAMPLE_ROWS = [
    {"base": "USD", "date": "2024-02-19", "target": "CAD", "conversion": 1.3456},
    {"base": "USD", "date": "2024-02-19", "target": "EUR", "conversion": 0.9234},
    {"base": "USD", "date": "2024-02-19", "target": "JPY", "conversion": 150.12},
    {"base": "EUR", "date": "2024-02-19", "target": "USD", "conversion": 1.0831},
    {"base": "EUR", "date": "2024-02-19", "target": "CAD", "conversion": 1.4567},
]

# Additional specs used in multi-connector regression coverage.
# These do not need to be real connectors — they exercise the scaffold on
# different schemas to guard against pattern drift.
ADDITIONAL_SPECS = [
    ConnectorSpec.from_dicts(
        name="openweather",
        source_schema={
            "type": "object",
            "required": ["city_id", "timestamp", "temperature"],
            "properties": {
                "city_id":     {"type": "integer", "description": "City identifier"},
                "timestamp":   {"type": "string",  "description": "ISO-8601 timestamp"},
                "temperature": {"type": "number",  "description": "Celsius"},
                "humidity":    {"type": "number",  "description": "Relative humidity %"},
            },
        },
        dest_schema={
            "type": "object",
            "required": ["city_id", "timestamp", "temperature"],
            "properties": {
                "city_id":     {"type": "integer"},
                "timestamp":   {"type": "string"},
                "temperature": {"type": "number"},
                "humidity":    {"type": "number"},
            },
        },
    ),
    ConnectorSpec.from_dicts(
        name="hubspot_contacts",
        source_schema={
            "type": "object",
            "required": ["contact_id", "email"],
            "properties": {
                "contact_id": {"type": "integer", "description": "HubSpot contact ID"},
                "email":      {"type": "string",  "description": "Primary email"},
                "first_name": {"type": "string"},
                "last_name":  {"type": "string"},
                "created_at": {"type": "string"},
            },
        },
        dest_schema={
            "type": "object",
            "required": ["contact_id", "email"],
            "properties": {
                "contact_id": {"type": "integer"},
                "email":      {"type": "string"},
                "first_name": {"type": "string"},
                "last_name":  {"type": "string"},
                "created_at": {"type": "string"},
            },
        },
    ),
]

# Full list used in parameterised regression tests.
ALL_SPECS = [
    ConnectorSpec.from_dicts(
        name="exchangeratesapi",
        source_schema=EXCHANGERATES_SOURCE_SCHEMA,
        dest_schema=EXCHANGERATES_DEST_SCHEMA,
    ),
    *ADDITIONAL_SPECS,
]


# ---------------------------------------------------------------------------
# Helper — scaffold and import a transient connector module
# ---------------------------------------------------------------------------

def _scaffold_and_import(spec: ConnectorSpec, tmp_path: Path):
    """
    Scaffold the connector under tmp_path/connectors/<name>/ and return
    the imported flow module.

    Each call evicts any previously-registered `connectors` root from
    sys.path and sys.modules so different tmp_path values (used by
    different test functions) never collide.
    """
    connector_dir = tmp_path / "connectors" / spec.name
    scaffold_connector(spec, out_dir=connector_dir)

    connectors_init = tmp_path / "connectors" / "__init__.py"
    if not connectors_init.exists():
        connectors_init.write_text("", encoding="utf-8")

    # Remove stale sys.path entries that contain a "connectors" package so
    # Python does not resolve `import connectors` against a different tmp_path.
    sys.path[:] = [
        p for p in sys.path
        if not (Path(p) / "connectors").is_dir() or Path(p) == tmp_path
    ]
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))

    # Evict the connectors root package and all submodules so Python
    # re-discovers them from the (possibly new) sys.path entry above.
    stale = [k for k in sys.modules if k == "connectors" or k.startswith("connectors.")]
    for mod in stale:
        del sys.modules[mod]

    importlib.invalidate_caches()
    return importlib.import_module(f"connectors.{spec.name}.flow")


# ---------------------------------------------------------------------------
# Static analysis helper — parse generated flow.py with AST
# ---------------------------------------------------------------------------

class _FlowPatternChecker:
    """
    Inspect the structure of generated flow.py without executing it.

    All checks use AST analysis so they run without Prefect installed,
    making the eval fast and CI-friendly.
    """

    def __init__(self, code: str) -> None:
        self.tree = ast.parse(code)
        self._funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
            n.name: n
            for n in ast.walk(self.tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    # ---- presence / shape ----

    def has_function(self, name: str) -> bool:
        return name in self._funcs

    def is_async(self, name: str) -> bool:
        return isinstance(self._funcs.get(name), ast.AsyncFunctionDef)

    def decorators_of(self, name: str) -> list[str]:
        node = self._funcs.get(name)
        if node is None:
            return []
        return [ast.unparse(d) for d in node.decorator_list]

    def has_decorator_matching(self, func_name: str, fragment: str) -> bool:
        """Return True if any decorator string for func_name contains fragment."""
        return any(fragment in d for d in self.decorators_of(func_name))

    def has_retries_on(self, func_name: str) -> bool:
        return self.has_decorator_matching(func_name, "retries")

    # ---- import checks ----

    def imports_from_prefect(self) -> bool:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("prefect"):
                return True
        return False


# ---------------------------------------------------------------------------
# 1 — Pattern conformance (static, no Prefect/httpx execution)
# ---------------------------------------------------------------------------

class TestPatternConformance:
    """
    Every generated flow.py must structurally match the exchange rates reference
    pattern.  Tests run across all specs in ALL_SPECS to prevent drift.
    """

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_has_extract_task(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).has_function("extract")

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_has_transform_task(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).has_function("transform")

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_has_load_task(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).has_function("load")

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_has_audit_task(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).has_function("audit")

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_has_connector_flow_entrypoint(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).has_function("connector_flow")

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_extract_is_async(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).is_async("extract"), \
            "extract must be an async function (I/O-bound)"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_load_is_async(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).is_async("load"), \
            "load must be an async function (I/O-bound)"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_connector_flow_is_async(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).is_async("connector_flow"), \
            "connector_flow must be async to await extract and load"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_extract_has_retries(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).has_retries_on("extract"), \
            "extract must declare retries — source APIs are unreliable"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_load_has_retries(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).has_retries_on("load"), \
            "load must declare retries — destination writes can be transient"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_connector_flow_has_flow_decorator(self, spec: ConnectorSpec) -> None:
        checker = _FlowPatternChecker(generate_flow(spec))
        assert checker.has_decorator_matching("connector_flow", "flow"), \
            "connector_flow must carry Prefect @flow decorator"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_imports_prefect(self, spec: ConnectorSpec) -> None:
        assert _FlowPatternChecker(generate_flow(spec)).imports_from_prefect(), \
            "flow.py must import from prefect"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_flow_is_valid_python(self, spec: ConnectorSpec) -> None:
        code = generate_flow(spec)
        try:
            ast.parse(code)
        except SyntaxError as exc:
            pytest.fail(f"[{spec.name}] generated flow.py is not valid Python: {exc}")


# ---------------------------------------------------------------------------
# 2 — Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Generated schemas.py must define Pydantic BaseModel classes with the
    correct field names and Python types for the exchange rates pattern."""

    @pytest.fixture
    def er_spec(self) -> ConnectorSpec:
        return ConnectorSpec.from_dicts(
            name="exchangeratesapi",
            source_schema=EXCHANGERATES_SOURCE_SCHEMA,
            dest_schema=EXCHANGERATES_DEST_SCHEMA,
        )

    def test_source_class_name_convention(self, er_spec: ConnectorSpec) -> None:
        assert "ExchangeratesapiSource" in generate_schemas(er_spec)

    def test_dest_class_name_convention(self, er_spec: ConnectorSpec) -> None:
        assert "ExchangeratesapiDest" in generate_schemas(er_spec)

    def test_extends_basemodel(self, er_spec: ConnectorSpec) -> None:
        assert "BaseModel" in generate_schemas(er_spec)

    def test_all_source_fields_present(self, er_spec: ConnectorSpec) -> None:
        code = generate_schemas(er_spec)
        for field_name in ("base", "date", "target", "conversion"):
            assert field_name in code, f"Source schema missing field: {field_name}"

    def test_conversion_typed_as_float(self, er_spec: ConnectorSpec) -> None:
        assert "conversion: float" in generate_schemas(er_spec)

    def test_string_fields_typed_correctly(self, er_spec: ConnectorSpec) -> None:
        code = generate_schemas(er_spec)
        for field_name in ("base", "date", "target"):
            assert f"{field_name}: str" in code, \
                f"Expected '{field_name}: str' in schemas.py"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_schemas_is_valid_python(self, spec: ConnectorSpec) -> None:
        code = generate_schemas(spec)
        try:
            ast.parse(code)
        except SyntaxError as exc:
            pytest.fail(f"[{spec.name}] generated schemas.py is not valid Python: {exc}")

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_source_and_dest_classes_present(self, spec: ConnectorSpec) -> None:
        from devflow.connector_scaffold import _pascal
        code = generate_schemas(spec)
        assert f"{_pascal(spec.name)}Source" in code
        assert f"{_pascal(spec.name)}Dest" in code


# ---------------------------------------------------------------------------
# 3 — Exchange rates end-to-end pipeline eval
# ---------------------------------------------------------------------------

class TestExchangeRatesPipelineEval:
    """
    Full ETL run using exchange-rates-like data and in-process mock HTTP servers.

    Verifies that the connector builder output:
    - extracts the correct row count
    - preserves all primary-key fields (base, date, target) through the pipeline
    - preserves the conversion rate
    - fires an audit error when loaded_count != extracted_count
    - handles an empty source gracefully
    """

    @pytest.fixture
    def er_spec(self) -> ConnectorSpec:
        return ConnectorSpec.from_dicts(
            name="exchangeratesapi_eval",
            source_schema=EXCHANGERATES_SOURCE_SCHEMA,
            dest_schema=EXCHANGERATES_DEST_SCHEMA,
        )

    def test_row_count(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        with MockHTTPServer(rows=EXCHANGERATES_SAMPLE_ROWS) as src, \
             MockHTTPServer() as dst:
            flow_mod = _scaffold_and_import(er_spec, tmp_path)
            result = asyncio.run(
                flow_mod.connector_flow(
                    source_url=src.url("/records"),
                    dest_url=dst.url("/records"),
                )
            )
        assert result["extracted"] == len(EXCHANGERATES_SAMPLE_ROWS)
        assert result["loaded"] == len(EXCHANGERATES_SAMPLE_ROWS)

    def test_base_currency_preserved(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        with MockHTTPServer(rows=EXCHANGERATES_SAMPLE_ROWS) as src, \
             MockHTTPServer() as dst:
            flow_mod = _scaffold_and_import(er_spec, tmp_path)
            asyncio.run(
                flow_mod.connector_flow(
                    source_url=src.url("/records"),
                    dest_url=dst.url("/records"),
                )
            )
        assert_field_integrity(
            dst.received, "base", [r["base"] for r in EXCHANGERATES_SAMPLE_ROWS]
        )

    def test_target_currency_preserved(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        with MockHTTPServer(rows=EXCHANGERATES_SAMPLE_ROWS) as src, \
             MockHTTPServer() as dst:
            flow_mod = _scaffold_and_import(er_spec, tmp_path)
            asyncio.run(
                flow_mod.connector_flow(
                    source_url=src.url("/records"),
                    dest_url=dst.url("/records"),
                )
            )
        assert_field_integrity(
            dst.received, "target", [r["target"] for r in EXCHANGERATES_SAMPLE_ROWS]
        )

    def test_date_preserved(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        with MockHTTPServer(rows=EXCHANGERATES_SAMPLE_ROWS) as src, \
             MockHTTPServer() as dst:
            flow_mod = _scaffold_and_import(er_spec, tmp_path)
            asyncio.run(
                flow_mod.connector_flow(
                    source_url=src.url("/records"),
                    dest_url=dst.url("/records"),
                )
            )
        assert_field_integrity(
            dst.received, "date", [r["date"] for r in EXCHANGERATES_SAMPLE_ROWS]
        )

    def test_conversion_rate_preserved(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        with MockHTTPServer(rows=EXCHANGERATES_SAMPLE_ROWS) as src, \
             MockHTTPServer() as dst:
            flow_mod = _scaffold_and_import(er_spec, tmp_path)
            asyncio.run(
                flow_mod.connector_flow(
                    source_url=src.url("/records"),
                    dest_url=dst.url("/records"),
                )
            )
        assert_field_integrity(
            dst.received, "conversion", [r["conversion"] for r in EXCHANGERATES_SAMPLE_ROWS]
        )

    def test_audit_catches_row_drop(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        """audit() must raise when loaded count is less than extracted count."""
        flow_mod = _scaffold_and_import(er_spec, tmp_path)
        rows = EXCHANGERATES_SAMPLE_ROWS[:3]
        with pytest.raises(ValueError, match="Row count mismatch"):
            flow_mod.audit(rows, 2)  # 3 extracted, 2 reported loaded

    def test_empty_source_produces_zero_rows(
        self, er_spec: ConnectorSpec, tmp_path: Path
    ) -> None:
        with MockHTTPServer(rows=[]) as src, MockHTTPServer() as dst:
            flow_mod = _scaffold_and_import(er_spec, tmp_path)
            result = asyncio.run(
                flow_mod.connector_flow(
                    source_url=src.url("/records"),
                    dest_url=dst.url("/records"),
                )
            )
        assert result["extracted"] == 0
        assert result["loaded"] == 0
        assert dst.received == []

    def test_unreachable_source_raises(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        """A bad source URL must propagate an error (not silently produce 0 rows)."""
        flow_mod = _scaffold_and_import(er_spec, tmp_path)
        with pytest.raises(Exception):
            asyncio.run(
                flow_mod.connector_flow(
                    source_url="http://127.0.0.1:1/records",  # port 1 is always refused
                    dest_url="http://127.0.0.1:1/records",
                )
            )


# ---------------------------------------------------------------------------
# 4 — Scaffold idempotency
# ---------------------------------------------------------------------------

class TestScaffoldIdempotency:
    """
    Scaffold idempotency: calling scaffold_connector twice on the same spec must
    produce byte-for-byte identical files.  Non-determinism in the builder
    makes diffs noisy and regression catches unreliable.
    """

    @pytest.fixture
    def er_spec(self) -> ConnectorSpec:
        return ConnectorSpec.from_dicts(
            name="exchangeratesapi_idem",
            source_schema=EXCHANGERATES_SOURCE_SCHEMA,
            dest_schema=EXCHANGERATES_DEST_SCHEMA,
        )

    def test_flow_py_idempotent(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        out = tmp_path / "connectors" / er_spec.name
        files1 = scaffold_connector(er_spec, out_dir=out)
        content1 = files1["flow"].read_text(encoding="utf-8")
        files2 = scaffold_connector(er_spec, out_dir=out)
        content2 = files2["flow"].read_text(encoding="utf-8")
        assert content1 == content2, "flow.py scaffold output is not idempotent"

    def test_schemas_py_idempotent(self, er_spec: ConnectorSpec, tmp_path: Path) -> None:
        out = tmp_path / "connectors" / er_spec.name
        files1 = scaffold_connector(er_spec, out_dir=out)
        content1 = files1["schemas"].read_text(encoding="utf-8")
        files2 = scaffold_connector(er_spec, out_dir=out)
        content2 = files2["schemas"].read_text(encoding="utf-8")
        assert content1 == content2, "schemas.py scaffold output is not idempotent"

    def test_two_runs_load_same_row_count(
        self, er_spec: ConnectorSpec, tmp_path: Path
    ) -> None:
        """Re-running the pipeline on identical input must load the same number of rows."""
        rows = EXCHANGERATES_SAMPLE_ROWS[:3]
        flow_mod = _scaffold_and_import(er_spec, tmp_path)

        with MockHTTPServer(rows=rows) as src1, MockHTTPServer() as dst1:
            r1 = asyncio.run(
                flow_mod.connector_flow(
                    source_url=src1.url("/records"),
                    dest_url=dst1.url("/records"),
                )
            )

        with MockHTTPServer(rows=rows) as src2, MockHTTPServer() as dst2:
            r2 = asyncio.run(
                flow_mod.connector_flow(
                    source_url=src2.url("/records"),
                    dest_url=dst2.url("/records"),
                )
            )

        assert r1["loaded"] == r2["loaded"], \
            "Re-running with identical input must load the same row count"


# ---------------------------------------------------------------------------
# 5 — Multi-connector regression suite
# ---------------------------------------------------------------------------

class TestMultiConnectorRegression:
    """
    All specs in ALL_SPECS must pass full pattern + pipeline checks.
    Extend ADDITIONAL_SPECS to add coverage for new connectors.
    """

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_all_etl_tasks_present(self, spec: ConnectorSpec) -> None:
        checker = _FlowPatternChecker(generate_flow(spec))
        missing = [
            t for t in ("extract", "transform", "load", "audit", "connector_flow")
            if not checker.has_function(t)
        ]
        assert not missing, f"[{spec.name}] Missing ETL tasks: {missing}"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_resilience_decorators(self, spec: ConnectorSpec) -> None:
        checker = _FlowPatternChecker(generate_flow(spec))
        assert checker.has_retries_on("extract"), f"[{spec.name}] extract missing retries"
        assert checker.has_retries_on("load"), f"[{spec.name}] load missing retries"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=[s.name for s in ALL_SPECS])
    def test_pipeline_end_to_end(self, spec: ConnectorSpec, tmp_path: Path) -> None:
        """Scaffold each connector and run a minimal 2-row pipeline end-to-end."""
        sample_row = {
            f.name: (
                "test_value" if f.type == "str"
                else (42 if f.type == "int"
                      else (1.0 if f.type in ("float", "number")
                            else True))
            )
            for f in spec.source_fields
        }
        rows = [sample_row, dict(sample_row)]

        with MockHTTPServer(rows=rows) as src, MockHTTPServer() as dst:
            flow_mod = _scaffold_and_import(spec, tmp_path)
            result = asyncio.run(
                flow_mod.connector_flow(
                    source_url=src.url("/records"),
                    dest_url=dst.url("/records"),
                )
            )

        assert result["extracted"] == 2, f"[{spec.name}] expected 2 rows extracted"
        assert result["loaded"] == 2, f"[{spec.name}] expected 2 rows loaded"
        assert_row_counts(rows, dst.received, context=spec.name)
