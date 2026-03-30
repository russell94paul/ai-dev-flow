---
name: connector-build
description: Build a Paperclip connector feature following the connector contract: schema, idempotency, contract test, logging, retries, observability, and README. Use when state.feature_type = "connector" and the build phase begins.
---

# Connector Build

Implements the connector contract and produces `build/connector-checklist.md`. Called by `devflow-builder` when `state.feature_type = "connector"` during the Build phase.

This skill runs **alongside** the `tdd` skill — not instead of it. The standard TDD workflow still applies (Red → Green → Refactor, Iron Law). This skill specifies the connector-specific components that must be present and tested.

## Inputs

1. `specs/prd.md` — connector name, source API, destination, schedule, schema requirements
2. `plans/plan.md` — implementation phases, ADRs, Prefect flow design
3. `devflow.yaml` — project config (Python version, test runner, coverage command)

Derive `<name>` (connector name, lowercase, underscored) from the PRD. All paths below use this name.

## Connector contract

Every connector feature must implement all nine components. Each is validated by `devflow seal --completing build` for connector features.

---

### Component 1: Schema definition

**File:** `connectors/<name>/schemas.py`

Define Pydantic models for source records and destination records.

```python
# connectors/<name>/schemas.py
from pydantic import BaseModel
from typing import Optional

class SourceRecord(BaseModel):
    id: str
    # ... fields from source API

class DestinationRecord(BaseModel):
    source_id: str
    # ... transformed fields
```

**Seal check:** file exists and contains a Pydantic `BaseModel` import.

---

### Component 2: Schema Gate (first Prefect task)

The **first task** in the Prefect flow must validate the source schema before any data is processed. If schema validation fails, raise `SchemaValidationError` — do not process the record.

```python
from prefect import task, flow
from pydantic import ValidationError

class SchemaValidationError(Exception):
    pass

@task
def validate_source_schema(raw_record: dict) -> SourceRecord:
    try:
        return SourceRecord(**raw_record)
    except ValidationError as exc:
        raise SchemaValidationError(f"Source schema mismatch: {exc}") from exc
```

**Seal check:** `SchemaValidationError` raise pattern is present in the connector module.

---

### Component 3: Idempotency key

Each extract/load task must carry a deterministic `idempotency_key`. The key must be a hash of stable inputs — running the same flow twice with the same source data must produce the same key and must not create duplicate rows.

```python
import hashlib

def make_idempotency_key(source_id: str, run_date: str) -> str:
    return hashlib.sha256(f"{source_id}:{run_date}".encode()).hexdigest()
```

**Seal check:** `idempotency_key` identifier is present in the connector module.

---

### Component 4: Idempotency test

**File:** `tests/connectors/test_<name>_idempotency.py` (or a function matching `*idempotency*` in the contract test file)

The test must run the flow (or the load task) twice with identical input and assert that the result count equals a single run.

```python
def test_load_is_idempotent(mock_destination):
    records = [{"id": "abc", ...}]
    load_records(records, run_date="2026-01-01")
    load_records(records, run_date="2026-01-01")  # second run
    assert mock_destination.row_count() == len(records)  # not doubled
```

**Seal check:** test file exists and contains a test matching the `*idempotency*` name pattern.

---

### Component 5: Contract test

**File:** `tests/connectors/test_<name>_contract.py`

Verifies that the source API still returns the fields the flow depends on. This test runs against a recorded fixture or a sandboxed API — not production.

```python
def test_source_api_contract():
    # Fetch a sample record from the fixture / sandbox
    raw = fetch_sample_record()
    # Verify all fields the flow depends on are present
    record = SourceRecord(**raw)  # Pydantic validation — raises if field missing
    assert record.id is not None
    assert hasattr(record, "created_at")
    # Add assertions for every field used in the transform step
```

**Seal check:** `tests/connectors/test_<name>_contract.py` exists.

---

### Component 6: Structured logging

The connector must log at extract, transform, and load stages. At minimum, log the source record count after extract and the loaded record count after load.

```python
import logging
logger = logging.getLogger(__name__)

@task
def extract(source_client) -> list[dict]:
    records = source_client.fetch_all()
    logger.info("extracted %d source records", len(records))
    return records

@task
def load(records: list[DestinationRecord], destination_client) -> None:
    destination_client.bulk_insert(records)
    logger.info("loaded %d records to destination", len(records))
```

**Seal check:** `logging` import and a count log (`%d` or `len(`) present in the connector module.

---

### Component 7: Retry configuration

The Prefect flow must declare retry config on at minimum the extract and load tasks. Use ≥ 1 retry with ≥ 1 second delay to avoid hammering a failing API.

```python
from datetime import timedelta
from prefect import task

@task(retries=3, retry_delay_seconds=10)
def extract(source_client) -> list[dict]:
    ...

@task(retries=2, retry_delay_seconds=5)
def load(records, destination_client) -> None:
    ...
```

**Seal check:** `retries=` is present in the flow module.

---

### Component 8: Observability artifacts

The Prefect flow must emit at minimum three metrics as Prefect artifacts or result metadata:
- `records_extracted` — count after extract
- `records_loaded` — count after load
- `errors_skipped` — count of records that failed schema validation and were skipped

```python
from prefect.artifacts import create_markdown_artifact

@flow
def connector_flow(run_date: str):
    raw = extract(source_client)
    valid, skipped = validate_all(raw)
    loaded = load(valid, destination_client)
    create_markdown_artifact(
        key="run-summary",
        markdown=f"| Metric | Value |\n|---|---|\n"
                 f"| records_extracted | {len(raw)} |\n"
                 f"| records_loaded | {len(loaded)} |\n"
                 f"| errors_skipped | {len(skipped)} |",
    )
```

**Seal check:** `records_extracted`, `records_loaded`, and `errors_skipped` identifiers (or equivalent string literals) are present in the flow module.

---

### Component 9: Connector README

**File:** `connectors/<name>/README.md`

Must contain at least three of the following sections:

| Section | Content |
|---|---|
| Source | What system is being read from; API version; authentication method |
| Destination | What system is being written to; table/endpoint name |
| Schedule | Cron expression or trigger condition |
| Schema | Field names and types; note on optional fields |
| Run instructions | How to run the flow manually (`prefect deployment run ...`) |

**Seal check:** file exists and contains ≥ 3 markdown `## ` sections.

---

## Process

Work through the components in order. For each:

1. Implement the component
2. Write the corresponding test(s)
3. Confirm the test passes (Red → Green)
4. Check the box in the checklist

Do not move to the next component until the current one is green.

## Output artifact: `build/connector-checklist.md`

Write this file (relative to the feature root) after all components are complete. Overwrite on each run.

```markdown
# Connector Build Checklist: <feature-slug>

**Connector name:** <name>
**Timestamp:** <ISO 8601>

| Component | Status | Notes |
|---|---|---|
| Schema definition (schemas.py) | PASS/FAIL | |
| Schema Gate (first Prefect task) | PASS/FAIL | |
| Idempotency key | PASS/FAIL | |
| Idempotency test | PASS/FAIL | |
| Contract test | PASS/FAIL | |
| Structured logging | PASS/FAIL | |
| Retry config | PASS/FAIL | |
| Observability artifacts | PASS/FAIL | |
| Connector README | PASS/FAIL | |

**Overall:** PASS / FAIL
```

**Overall is PASS only when all rows are PASS.** If any row is FAIL, investigate and fix before writing the checklist — do not record known failures as PASS.

## Seal validation

`devflow seal --completing build` (connector) runs standard Iron Law checks **plus**:

| Check | What is validated |
|---|---|
| `connectors/<name>/schemas.py` exists | Pydantic `BaseModel` import present |
| `SchemaValidationError` pattern | Found in connector module |
| `idempotency_key` identifier | Found in connector module |
| Idempotency test file | Exists; test matches `*idempotency*` |
| Contract test file | `tests/connectors/test_<name>_contract.py` exists |
| `logging` + count log | Present in connector module |
| `retries=` | Present in flow module |
| Observability identifiers | `records_extracted`, `records_loaded`, `errors_skipped` present |
| `connectors/<name>/README.md` | Exists with ≥ 3 `## ` sections |
| `build/connector-checklist.md` | All rows = PASS; Overall = PASS |

## Connector gate/seal interactions

| Command | Extra check for connectors |
|---|---|
| `devflow gate --entering build` | `connectors/` directory exists under feature root |
| `devflow seal --completing build` | All 9 components validated (above) |
| `devflow gate --entering deploy` | QA evidence contains `## Connector QA` section; contract test = PASS |
