"""
Connector scaffold generator.

Given a source schema, destination schema, and transform config, emits
a ready-to-run Prefect 3.x connector flow plus Pydantic models and a
matching pytest unit test stub.

CLI usage (Windows-compatible):
    python -m devflow.connector_scaffold \\
        --name my_connector \\
        --source-schema connectors/my_connector/source_schema.json \\
        --dest-schema   connectors/my_connector/dest_schema.json \\
        --transform-config connectors/my_connector/transform.yaml \\
        --out-dir connectors/my_connector

Programmatic usage:
    from devflow.connector_scaffold import ConnectorSpec, scaffold_connector
    spec = ConnectorSpec.from_files(name="sales", ...)
    scaffold_connector(spec, out_dir=Path("connectors/sales"))
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# yaml is in the test extra; guard so the module can be imported without it
try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass
class FieldDef:
    name: str
    type: str                   # python type name: str, int, float, bool, …
    nullable: bool = False
    description: str = ""

    @classmethod
    def from_json_schema_prop(cls, name: str, prop: dict, required: list[str]) -> "FieldDef":
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "object": "dict",
            "array": "list",
        }
        raw_type = prop.get("type", "string")
        if isinstance(raw_type, list):
            # ["string", "null"] → nullable str
            non_null = [t for t in raw_type if t != "null"]
            raw_type = non_null[0] if non_null else "string"
            nullable = True
        else:
            nullable = name not in required
        return cls(
            name=name,
            type=type_map.get(raw_type, "Any"),
            nullable=nullable,
            description=prop.get("description", ""),
        )


@dataclass
class TransformRule:
    source_field: str
    dest_field: str
    transform: str = "passthrough"   # passthrough | cast | derive
    expression: str = ""             # Python expression string for "derive"


@dataclass
class ConnectorSpec:
    name: str
    source_fields: list[FieldDef] = field(default_factory=list)
    dest_fields: list[FieldDef] = field(default_factory=list)
    transform_rules: list[TransformRule] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Factories                                                            #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_files(
        cls,
        name: str,
        source_schema_path: Path,
        dest_schema_path: Path,
        transform_config_path: Path | None = None,
    ) -> "ConnectorSpec":
        source_fields = _parse_json_schema(source_schema_path)
        dest_fields = _parse_json_schema(dest_schema_path)
        transform_rules = (
            _parse_transform_config(transform_config_path)
            if transform_config_path and transform_config_path.exists()
            else _infer_transform_rules(source_fields, dest_fields)
        )
        return cls(
            name=name,
            source_fields=source_fields,
            dest_fields=dest_fields,
            transform_rules=transform_rules,
        )

    @classmethod
    def from_dicts(
        cls,
        name: str,
        source_schema: dict,
        dest_schema: dict,
        transform_config: dict | None = None,
    ) -> "ConnectorSpec":
        source_fields = _fields_from_schema_dict(source_schema)
        dest_fields = _fields_from_schema_dict(dest_schema)
        transform_rules = (
            _rules_from_config_dict(transform_config)
            if transform_config
            else _infer_transform_rules(source_fields, dest_fields)
        )
        return cls(
            name=name,
            source_fields=source_fields,
            dest_fields=dest_fields,
            transform_rules=transform_rules,
        )


# ---------------------------------------------------------------------------
# Schema parsers
# ---------------------------------------------------------------------------

def _parse_json_schema(path: Path) -> list[FieldDef]:
    with path.open(encoding="utf-8") as f:
        schema = json.load(f)
    return _fields_from_schema_dict(schema)


def _fields_from_schema_dict(schema: dict) -> list[FieldDef]:
    props = schema.get("properties", {})
    required = schema.get("required", [])
    return [
        FieldDef.from_json_schema_prop(name, prop, required)
        for name, prop in props.items()
    ]


def _parse_transform_config(path: Path) -> list[TransformRule]:
    if not _HAS_YAML:
        raise ImportError("pyyaml is required to parse transform configs. pip install pyyaml")
    with path.open(encoding="utf-8") as f:
        cfg = _yaml.safe_load(f)
    return _rules_from_config_dict(cfg or {})


def _rules_from_config_dict(cfg: dict) -> list[TransformRule]:
    rules = []
    for rule in cfg.get("rules", []):
        rules.append(TransformRule(
            source_field=rule["source"],
            dest_field=rule["dest"],
            transform=rule.get("transform", "passthrough"),
            expression=rule.get("expression", ""),
        ))
    return rules


def _infer_transform_rules(
    source_fields: list[FieldDef],
    dest_fields: list[FieldDef],
) -> list[TransformRule]:
    """Best-effort: match source→dest fields by name."""
    source_names = {f.name for f in source_fields}
    rules = []
    for df in dest_fields:
        if df.name in source_names:
            rules.append(TransformRule(source_field=df.name, dest_field=df.name))
    return rules


# ---------------------------------------------------------------------------
# Code generators
# ---------------------------------------------------------------------------

def _pydantic_model(class_name: str, fields: list[FieldDef]) -> str:
    """Emit a Pydantic v2 BaseModel class."""
    lines = [f"class {class_name}(BaseModel):"]
    if not fields:
        lines.append("    pass")
    for f in fields:
        opt = f"Optional[{f.type}]" if f.nullable else f.type
        default = " = None" if f.nullable else ""
        comment = f"  # {f.description}" if f.description else ""
        lines.append(f"    {f.name}: {opt}{default}{comment}")
    return "\n".join(lines)


def _transform_body(rules: list[TransformRule]) -> str:
    """Emit the body of the transform task."""
    if not rules:
        return "        return {}"
    lines = ["        return {"]
    for rule in rules:
        if rule.transform == "derive" and rule.expression:
            val = rule.expression.replace("row.", "row.")
        elif rule.transform == "cast":
            # simple cast using dest field name as type hint
            val = f"row.{rule.source_field}"
        else:
            val = f"row.{rule.source_field}"
        lines.append(f'            "{rule.dest_field}": {val},')
    lines.append("        }")
    return "\n".join(lines)


def generate_flow(spec: ConnectorSpec) -> str:
    """Return the full text of the Prefect flow module."""
    name = spec.name
    cls_src = f"{_pascal(name)}Source"
    cls_dst = f"{_pascal(name)}Dest"
    transform_body = _transform_body(spec.transform_rules)

    optional_imports = (
        "from typing import Optional, Any\n" if _uses_optional(spec) else "from typing import Any\n"
    )

    return textwrap.dedent(f"""\
        \"\"\"
        Prefect connector flow: {name}

        Auto-generated by devflow.connector_scaffold.
        Edit extract(), transform(), and load() to match your environment.
        \"\"\"
        from __future__ import annotations

        import os
        from typing import Any, Optional

        import httpx
        from prefect import flow, task
        from prefect.logging import get_run_logger
        from pydantic import BaseModel

        from .schemas import {cls_src}, {cls_dst}


        # ---------------------------------------------------------------------------
        # Extract
        # ---------------------------------------------------------------------------

        @task(name="extract-{name}", retries=3, retry_delay_seconds=10)
        async def extract(source_url: str) -> list[dict]:
            \"\"\"
            Pull raw records from the source endpoint.
            Replace with your actual source client (database cursor, S3 reader, etc.)
            \"\"\"
            logger = get_run_logger()
            logger.info("Extracting from %s", source_url)
            async with httpx.AsyncClient() as client:
                resp = await client.get(source_url, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            # Validate each row against the source schema
            records = data if isinstance(data, list) else data.get("records", [])
            return [{cls_src}(**r).model_dump() for r in records]


        # ---------------------------------------------------------------------------
        # Transform
        # ---------------------------------------------------------------------------

        @task(name="transform-{name}")
        def transform(raw_rows: list[dict]) -> list[dict]:
            \"\"\"
            Apply field mappings and type coercions defined in transform config.
            \"\"\"
            result = []
            for raw in raw_rows:
                row = {cls_src}(**raw)
                mapped = _apply_transform(row)
                result.append({cls_dst}(**mapped).model_dump())
            return result


        def _apply_transform(row: {cls_src}) -> dict:
        {transform_body}


        # ---------------------------------------------------------------------------
        # Load
        # ---------------------------------------------------------------------------

        @task(name="load-{name}", retries=2, retry_delay_seconds=5)
        async def load(rows: list[dict], dest_url: str) -> int:
            \"\"\"
            Write transformed rows to the destination endpoint.
            Replace with your actual destination client.
            \"\"\"
            logger = get_run_logger()
            logger.info("Loading %d rows to %s", len(rows), dest_url)
            async with httpx.AsyncClient() as client:
                resp = await client.post(dest_url, json={{\"records\": rows}}, timeout=60)
                resp.raise_for_status()
            logger.info("Load complete — %d rows written", len(rows))
            return len(rows)


        # ---------------------------------------------------------------------------
        # Audit
        # ---------------------------------------------------------------------------

        @task(name="audit-{name}")
        def audit(extracted: list[dict], loaded_count: int) -> None:
            \"\"\"Assert row counts match so we catch silent data loss.\"\"\"
            logger = get_run_logger()
            if loaded_count != len(extracted):
                raise ValueError(
                    f"Row count mismatch: extracted {{len(extracted)}} but loaded {{loaded_count}}"
                )
            logger.info("Audit passed — %d rows", loaded_count)


        # ---------------------------------------------------------------------------
        # Flow entry-point
        # ---------------------------------------------------------------------------

        @flow(name="{name}-connector")
        async def connector_flow(
            source_url: str = os.environ.get("SOURCE_URL", "http://localhost:18801/records"),
            dest_url: str = os.environ.get("DEST_URL", "http://localhost:18802/records"),
        ) -> dict:
            raw_rows = await extract(source_url)
            transformed = transform(raw_rows)
            loaded_count = await load(transformed, dest_url)
            audit(raw_rows, loaded_count)
            return {{"extracted": len(raw_rows), "loaded": loaded_count}}


        if __name__ == "__main__":
            import asyncio
            asyncio.run(connector_flow())
    """)


def generate_schemas(spec: ConnectorSpec) -> str:
    """Return the full text of the schemas module."""
    name = spec.name
    cls_src = f"{_pascal(name)}Source"
    cls_dst = f"{_pascal(name)}Dest"

    src_model = _pydantic_model(cls_src, spec.source_fields)
    dst_model = _pydantic_model(cls_dst, spec.dest_fields)

    lines = [
        f'"""',
        f"Pydantic schemas for {name} connector.",
        "Auto-generated by devflow.connector_scaffold.",
        '"""',
        "from __future__ import annotations",
        "",
        "from typing import Any, Optional",
        "",
        "from pydantic import BaseModel",
        "",
        "",
        src_model,
        "",
        "",
        dst_model,
        "",
    ]
    return "\n".join(lines)


def generate_unit_test_stub(spec: ConnectorSpec) -> str:
    """Return a pytest unit-test stub for this connector."""
    name = spec.name
    cls_src = f"{_pascal(name)}Source"
    cls_dst = f"{_pascal(name)}Dest"

    # Build a minimal valid source row dict from field defs
    sample_src = ", ".join(
        f'{f.name}=None' if f.nullable else f'{f.name}={_sample_value(f.type)}'
        for f in spec.source_fields
    )

    return textwrap.dedent(f"""\
        \"\"\"
        Unit tests for the {name} connector.
        Auto-generated by devflow.connector_scaffold — extend as needed.
        \"\"\"
        from __future__ import annotations

        import pytest

        from connectors.{name}.schemas import {cls_src}, {cls_dst}
        from connectors.{name}.flow import transform, _apply_transform


        # ---------------------------------------------------------------------------
        # Schema validation
        # ---------------------------------------------------------------------------

        class TestSchemas:
            def test_source_schema_valid(self, sample_source_row):
                row = {cls_src}(**sample_source_row)
                assert row is not None

            def test_source_schema_rejects_wrong_types(self, sample_source_row):
                bad = dict(sample_source_row)
                # Inject a wrong-type value into the first non-nullable field
                first_field = next(
                    (k for k, v in bad.items() if v is not None), None
                )
                if first_field:
                    bad[first_field] = object()  # definitely not a valid type
                    with pytest.raises(Exception):
                        {cls_src}(**bad)

            def test_dest_schema_valid(self, sample_dest_row):
                row = {cls_dst}(**sample_dest_row)
                assert row is not None


        # ---------------------------------------------------------------------------
        # Transform
        # ---------------------------------------------------------------------------

        class TestTransform:
            def test_transform_preserves_row_count(self, source_rows):
                result = transform(source_rows)
                assert len(result) == len(source_rows)

            def test_transform_output_validates_dest_schema(self, source_rows):
                result = transform(source_rows)
                for row in result:
                    {cls_dst}(**row)   # raises on invalid schema

            def test_transform_handles_empty_input(self):
                assert transform([]) == []

            def test_apply_transform_returns_dict(self, sample_source_row):
                src = {cls_src}(**sample_source_row)
                out = _apply_transform(src)
                assert isinstance(out, dict)
    """)


# ---------------------------------------------------------------------------
# Fixture module (conftest extension)
# ---------------------------------------------------------------------------

def generate_conftest_fixtures(spec: ConnectorSpec) -> str:
    """Return connector-specific fixtures to add to tests/connectors/conftest.py."""
    name = spec.name
    cls_src = f"{_pascal(name)}Source"

    # Build sample row dict
    src_row = {
        f.name: (None if f.nullable else _sample_value_py(f.type))
        for f in spec.source_fields
    }

    return textwrap.dedent(f"""\
        # Fixtures for {name} connector — appended by scaffold generator

        @pytest.fixture
        def sample_source_row_{name}():
            return {json.dumps(src_row, indent=4)}


        @pytest.fixture
        def source_rows_{name}(sample_source_row_{name}):
            return [sample_source_row_{name}] * 3
    """)


# ---------------------------------------------------------------------------
# Main scaffold entry-point
# ---------------------------------------------------------------------------

def scaffold_connector(spec: ConnectorSpec, out_dir: Path) -> dict[str, Path]:
    """
    Write all generated files for a connector into out_dir.

    Returns a dict mapping role -> Path for each file written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Make the connector package importable
    init = out_dir / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")

    files: dict[str, Path] = {}

    schemas_path = out_dir / "schemas.py"
    schemas_path.write_text(generate_schemas(spec), encoding="utf-8")
    files["schemas"] = schemas_path

    flow_path = out_dir / "flow.py"
    flow_path.write_text(generate_flow(spec), encoding="utf-8")
    files["flow"] = flow_path

    test_path = out_dir.parent.parent / "tests" / "connectors" / f"test_{spec.name}.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(generate_unit_test_stub(spec), encoding="utf-8")
    files["unit_test"] = test_path

    return files


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a Prefect connector flow from schema specs."
    )
    parser.add_argument("--name", required=True, help="Connector name (snake_case)")
    parser.add_argument("--source-schema", required=True, type=Path)
    parser.add_argument("--dest-schema", required=True, type=Path)
    parser.add_argument("--transform-config", type=Path, default=None)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    spec = ConnectorSpec.from_files(
        name=args.name,
        source_schema_path=args.source_schema,
        dest_schema_path=args.dest_schema,
        transform_config_path=args.transform_config,
    )
    files = scaffold_connector(spec, args.out_dir)
    for role, path in files.items():
        print(f"  {role}: {path}")
    print("Scaffold complete.")


if __name__ == "__main__":
    _main()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pascal(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def _uses_optional(spec: ConnectorSpec) -> bool:
    return any(f.nullable for f in spec.source_fields + spec.dest_fields)


def _sample_value(type_name: str) -> str:
    """Return a Python literal string for a sample value of type_name."""
    mapping = {
        "str": '"example"',
        "int": "1",
        "float": "1.0",
        "bool": "True",
        "dict": "{}",
        "list": "[]",
        "Any": "None",
    }
    return mapping.get(type_name, "None")


def _sample_value_py(type_name: str) -> Any:
    """Return a Python value (not a string literal) for JSON serialisation."""
    mapping: dict[str, Any] = {
        "str": "example",
        "int": 1,
        "float": 1.0,
        "bool": True,
        "dict": {},
        "list": [],
    }
    return mapping.get(type_name, None)
