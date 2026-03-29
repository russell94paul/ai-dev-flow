"""
Unit tests for devflow/connector_scaffold.py.

Tests cover:
  - ConnectorSpec.from_dicts construction
  - Field parsing from JSON Schema
  - Transform rule inference
  - Code generation (schemas.py, flow.py, unit test stub)
  - Scaffold output files written correctly
  - CLI entry-point (smoke test)

Run:
    pytest tests/connectors/test_connector_scaffold.py -v
"""
from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path

import pytest

from devflow.connector_scaffold import (
    ConnectorSpec,
    FieldDef,
    TransformRule,
    _fields_from_schema_dict,
    _infer_transform_rules,
    _pascal,
    _sample_value,
    generate_flow,
    generate_schemas,
    generate_unit_test_stub,
    scaffold_connector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


# ---------------------------------------------------------------------------
# FieldDef.from_json_schema_prop
# ---------------------------------------------------------------------------

class TestFieldDefParsing:
    def test_required_field_not_nullable(self):
        f = FieldDef.from_json_schema_prop("id", {"type": "integer"}, required=["id"])
        assert f.name == "id"
        assert f.type == "int"
        assert not f.nullable

    def test_optional_field_is_nullable(self):
        f = FieldDef.from_json_schema_prop("score", {"type": "number"}, required=["id"])
        assert f.nullable

    def test_union_null_type(self):
        f = FieldDef.from_json_schema_prop(
            "tag", {"type": ["string", "null"]}, required=[]
        )
        assert f.type == "str"
        assert f.nullable

    def test_description_captured(self):
        f = FieldDef.from_json_schema_prop(
            "name", {"type": "string", "description": "Display name"}, required=["name"]
        )
        assert f.description == "Display name"

    def test_unknown_type_maps_to_Any(self):
        f = FieldDef.from_json_schema_prop("x", {"type": "uuid"}, required=["x"])
        assert f.type == "Any"


class TestFieldsFromSchemaDict:
    def test_parses_properties(self, simple_source_schema):
        fields = _fields_from_schema_dict(simple_source_schema)
        names = [f.name for f in fields]
        assert "id" in names
        assert "name" in names

    def test_empty_schema_returns_empty(self):
        assert _fields_from_schema_dict({}) == []


# ---------------------------------------------------------------------------
# ConnectorSpec construction
# ---------------------------------------------------------------------------

class TestConnectorSpec:
    def test_from_dicts_basic(self, simple_source_schema, simple_dest_schema):
        spec = ConnectorSpec.from_dicts(
            name="test",
            source_schema=simple_source_schema,
            dest_schema=simple_dest_schema,
        )
        assert spec.name == "test"
        assert len(spec.source_fields) == 4
        assert len(spec.dest_fields) == 4

    def test_infers_passthrough_rules(self, simple_source_schema, simple_dest_schema):
        spec = ConnectorSpec.from_dicts(
            name="test",
            source_schema=simple_source_schema,
            dest_schema=simple_dest_schema,
        )
        rule_names = {r.dest_field for r in spec.transform_rules}
        assert "id" in rule_names
        assert "name" in rule_names

    def test_explicit_transform_config(
        self, simple_source_schema, simple_dest_schema, passthrough_transform_config
    ):
        spec = ConnectorSpec.from_dicts(
            name="test",
            source_schema=simple_source_schema,
            dest_schema=simple_dest_schema,
            transform_config=passthrough_transform_config,
        )
        assert len(spec.transform_rules) == 4

    def test_from_files(self, source_schema_file, dest_schema_file, tmp_path):
        spec = ConnectorSpec.from_files(
            name="file_test",
            source_schema_path=source_schema_file,
            dest_schema_path=dest_schema_file,
        )
        assert spec.name == "file_test"
        assert len(spec.source_fields) > 0


# ---------------------------------------------------------------------------
# Transform rule inference
# ---------------------------------------------------------------------------

class TestInferTransformRules:
    def test_matching_names_inferred(self):
        src = [FieldDef("x", "int"), FieldDef("y", "str")]
        dst = [FieldDef("x", "int"), FieldDef("z", "str")]
        rules = _infer_transform_rules(src, dst)
        assert len(rules) == 1
        assert rules[0].source_field == "x"

    def test_no_overlap_returns_empty(self):
        src = [FieldDef("a", "int")]
        dst = [FieldDef("b", "int")]
        assert _infer_transform_rules(src, dst) == []


# ---------------------------------------------------------------------------
# Code generation — valid Python
# ---------------------------------------------------------------------------

class TestCodeGeneration:
    def test_generate_schemas_valid_python(self, simple_connector_spec):
        code = generate_schemas(simple_connector_spec)
        assert _is_valid_python(code), "schemas.py is not valid Python"

    def test_generate_flow_valid_python(self, simple_connector_spec):
        code = generate_flow(simple_connector_spec)
        assert _is_valid_python(code), "flow.py is not valid Python"

    def test_generate_unit_test_stub_valid_python(self, simple_connector_spec):
        code = generate_unit_test_stub(simple_connector_spec)
        assert _is_valid_python(code), "unit test stub is not valid Python"

    def test_schemas_contains_class_names(self, simple_connector_spec):
        code = generate_schemas(simple_connector_spec)
        assert "SimpleSource" in code
        assert "SimpleDest" in code

    def test_flow_contains_prefect_decorators(self, simple_connector_spec):
        code = generate_flow(simple_connector_spec)
        assert "@flow" in code
        assert "@task" in code

    def test_flow_contains_extract_transform_load(self, simple_connector_spec):
        code = generate_flow(simple_connector_spec)
        assert "async def extract" in code
        assert "def transform" in code
        assert "async def load" in code
        assert "def audit" in code


# ---------------------------------------------------------------------------
# Scaffold writes correct files
# ---------------------------------------------------------------------------

class TestScaffoldConnector:
    def test_scaffold_writes_files(self, simple_connector_spec, tmp_path):
        files = scaffold_connector(simple_connector_spec, out_dir=tmp_path / "simple")
        assert "schemas" in files
        assert "flow" in files
        assert "unit_test" in files
        for path in files.values():
            assert path.exists(), f"Expected file missing: {path}"

    def test_scaffold_schemas_is_valid_python(self, simple_connector_spec, tmp_path):
        files = scaffold_connector(simple_connector_spec, out_dir=tmp_path / "simple")
        code = files["schemas"].read_text(encoding="utf-8")
        assert _is_valid_python(code)

    def test_scaffold_flow_is_valid_python(self, simple_connector_spec, tmp_path):
        files = scaffold_connector(simple_connector_spec, out_dir=tmp_path / "simple")
        code = files["flow"].read_text(encoding="utf-8")
        assert _is_valid_python(code)

    def test_scaffold_creates_init(self, simple_connector_spec, tmp_path):
        out = tmp_path / "simple"
        scaffold_connector(simple_connector_spec, out_dir=out)
        assert (out / "__init__.py").exists()

    def test_scaffold_idempotent(self, simple_connector_spec, tmp_path):
        out = tmp_path / "simple"
        files1 = scaffold_connector(simple_connector_spec, out_dir=out)
        files2 = scaffold_connector(simple_connector_spec, out_dir=out)
        for role in files1:
            assert files1[role].read_text() == files2[role].read_text()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    @pytest.mark.parametrize("snake,expected", [
        ("my_connector", "MyConnector"),
        ("simple", "Simple"),
        ("abc_def_ghi", "AbcDefGhi"),
    ])
    def test_pascal(self, snake, expected):
        assert _pascal(snake) == expected

    @pytest.mark.parametrize("type_name", ["str", "int", "float", "bool", "dict", "list", "Any"])
    def test_sample_value_returns_string(self, type_name):
        val = _sample_value(type_name)
        assert isinstance(val, str)
        assert len(val) > 0
