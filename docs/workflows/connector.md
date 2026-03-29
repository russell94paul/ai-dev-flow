# Connector Pipeline — End-to-End Guide

This document covers the full lifecycle of building, testing, and deploying a data connector with `ai-dev-flow v3`.

---

## Overview

A **connector** moves data from a source system to a destination system through a six-phase workflow:

```
Grill  →  PRD  →  Plan  →  Build  →  QA  →  Deploy
```

Each phase produces structured artifacts that feed the next phase. The workflow is defined in `workflows/connector.yaml` and executed by `devflow`.

---

## Prerequisites

```
pip install -e ".[test]"
pip install prefect httpx pydantic
```

Python 3.11+. All commands are Windows-compatible (PowerShell or Git Bash).

---

## Phase 1 — Grill

**Goal:** Surface hidden requirements before writing any spec.

The Grill phase opens an AI conversation that asks targeted questions about:
- Source schema, field types, and volumes
- Destination schema and write semantics (upsert / append / replace)
- Incremental vs. full-load strategy
- PII fields and masking rules
- SLA and retry/idempotency requirements
- Known edge cases

**Output:** `connectors/<name>/grill.md`
**Done signal:** file contains `GRILL COMPLETE`

---

## Phase 2 — PRD

**Goal:** Translate the grill Q&A into a formal connector spec.

The PRD includes:
- Source schema (field name, type, nullable)
- Destination schema
- Transform rules (field mappings, type coercions, derived fields)
- Error handling policy (retry counts, dead-letter strategy, alerting)
- Acceptance criteria (row counts, data integrity assertions)

**Output:** `connectors/<name>/prd.md`
**Done signal:** file contains `PRD COMPLETE`

---

## Phase 3 — Plan

**Goal:** Break the PRD into a concrete Prefect flow implementation plan.

The plan covers:
- Prefect task decomposition: extract / validate / transform / load / audit
- Schema validation strategy (Pydantic v2 models)
- Test plan: unit fixtures + integration mock servers
- Rollback and idempotency design

**Output:** `connectors/<name>/plan.md`
**Done signal:** file contains `PLAN COMPLETE`

---

## Phase 4 — Build

**Goal:** Scaffold and implement the Prefect flow, TDD-first.

### Scaffold a connector

```bash
python -m devflow.connector_scaffold \
    --name my_connector \
    --source-schema connectors/my_connector/source_schema.json \
    --dest-schema   connectors/my_connector/dest_schema.json \
    --transform-config connectors/my_connector/transform.yaml \
    --out-dir connectors/my_connector
```

Or programmatically:

```python
from devflow.connector_scaffold import ConnectorSpec, scaffold_connector
from pathlib import Path

spec = ConnectorSpec.from_dicts(
    name="my_connector",
    source_schema={
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id":   {"type": "integer"},
            "name": {"type": "string"},
        },
    },
    dest_schema={
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id":   {"type": "integer"},
            "name": {"type": "string"},
        },
    },
)
files = scaffold_connector(spec, out_dir=Path("connectors/my_connector"))
# files = {"schemas": Path(...), "flow": Path(...), "unit_test": Path(...)}
```

### Generated files

| File | Purpose |
|------|---------|
| `connectors/<name>/__init__.py` | Makes connector an importable package |
| `connectors/<name>/schemas.py` | Pydantic v2 models for source and destination rows |
| `connectors/<name>/flow.py` | Prefect flow: `extract` → `transform` → `load` → `audit` |
| `tests/connectors/test_<name>.py` | Unit test stub — fill in connector-specific assertions |

### Source / destination schema format

JSON Schema (draft-07 compatible):

```json
{
  "type": "object",
  "required": ["id", "amount"],
  "properties": {
    "id":     { "type": "integer", "description": "Primary key" },
    "amount": { "type": "number"  },
    "tag":    { "type": "string"  }
  }
}
```

Fields listed in `required` are non-nullable; all others get `Optional[T]`.

### Transform config format

```yaml
rules:
  - source: id
    dest: record_id
    transform: passthrough

  - source: amount
    dest: amount_usd
    transform: cast

  - source: tag
    dest: category
    transform: derive
    expression: "row.tag.upper() if row.tag else 'UNKNOWN'"
```

`transform` values: `passthrough` (default), `cast`, `derive`.

### Flow architecture

```
connector_flow(source_url, dest_url)
  └─ extract(source_url)          # GET /records → validate with SourceModel
  └─ transform(raw_rows)          # apply transform rules → validate with DestModel
  └─ load(rows, dest_url)         # POST /records → return row count
  └─ audit(raw_rows, loaded_count) # assert counts match
```

All tasks use Prefect's built-in retry semantics (`retries=3` for extract, `retries=2` for load).

**Done signal:** `pytest tests/connectors/test_<name>.py -x -q` exits 0

---

## Phase 5 — QA

**Goal:** Run end-to-end integration tests against mock HTTP servers.

```bash
pytest tests/connectors/test_integration.py -v
```

The integration suite:
1. Starts an in-process `MockHTTPServer` serving `GET /records` (source)
2. Starts a second `MockHTTPServer` accepting `POST /records` (dest)
3. Calls `connector_flow(source_url, dest_url)` directly
4. Asserts row counts and field integrity against PRD acceptance criteria

No Prefect Cloud, no Docker, no external services required.

### Key fixtures (tests/connectors/conftest.py)

| Fixture | What it provides |
|---------|-----------------|
| `mock_source_server` | Running `MockHTTPServer` pre-loaded with `sample_source_rows` |
| `mock_dest_server` | Running `MockHTTPServer` that captures POSTed rows in `.received` |
| `sample_source_rows` | 3-row list of dicts matching `simple_source_schema` |
| `simple_connector_spec` | `ConnectorSpec` for the simple passthrough connector |
| `source_schema_file` | Temp `source_schema.json` file (for CLI tests) |
| `dest_schema_file` | Temp `dest_schema.json` file |
| `transform_config_file` | Temp `transform.yaml` file |

### Assertion helpers

```python
from tests.connectors.conftest import assert_row_counts, assert_field_integrity

assert_row_counts(extracted, loaded, context="my_connector")
assert_field_integrity(dest_rows, "id", expected_ids)
```

**Done signal:** `pytest tests/connectors/test_integration.py -k <name> -q` exits 0

---

## Phase 6 — Deploy

**Goal:** Register the flow with Prefect and run it in production.

```bash
prefect deploy connectors/<name>/flow.py:connector_flow \
    --name <name> \
    --pool default-agent-pool
```

Verify the deployment:

```bash
prefect deployment run "<name>-connector/<name>"
```

Environment variables used by the flow at runtime:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SOURCE_URL` | `http://localhost:18801/records` | Source endpoint |
| `DEST_URL` | `http://localhost:18802/records` | Destination endpoint |

**Done signal:** `connectors/<name>/deploy.md` contains `DEPLOY COMPLETE`

---

## Running All Connector Tests

```bash
# Unit tests only (no external deps, fast)
pytest tests/connectors/test_connector_scaffold.py -v

# Integration tests (in-process mock servers)
pytest tests/connectors/test_integration.py -v

# Everything
pytest tests/connectors/ -v
```

---

## Adding a New Connector

1. Create `connectors/<name>/source_schema.json` and `connectors/<name>/dest_schema.json`
2. Optionally create `connectors/<name>/transform.yaml`
3. Run the scaffold generator (see Phase 4)
4. Edit `connectors/<name>/flow.py` to point `extract()` at your real source
5. Edit `connectors/<name>/flow.py` to point `load()` at your real destination
6. Run unit tests, fix failures, run integration tests
7. Deploy

---

## Windows Notes

- Use `python -m devflow.connector_scaffold` (not a bare `devflow-scaffold` entrypoint) on Windows
- All generated paths use forward slashes; `pathlib.Path` handles OS translation
- `MockHTTPServer` binds to `127.0.0.1` (not `localhost`) to avoid IPv6 resolution issues on Windows
