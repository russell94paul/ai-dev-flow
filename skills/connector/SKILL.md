# SKILL: Prefect Connector Workflow

You are an expert engineer working on data connectors for this repository.
Follow the steps below in order. Do not skip steps or combine them.

---

## STEP 0 — Detect intent

Read the implementation plan provided at the end of this prompt, then ask the user:

> "What would you like to do?
> 1. Build a new connector (create module, deployment, tests, scripts)
> 2. Modify an existing connector (fix a bug, add a field, change behaviour)
> 3. Add a new deployment for an existing connector (new account or environment)
> 4. Diagnose a failing connector (trace errors, check blocks, inspect output)
>
> Reply with 1, 2, 3, or 4."

Wait for the answer before continuing. Then follow the path below that matches.

---

## PATH 1 — Build a new connector

### 1A — Read the plan

Identify from the plan:
- Connector name (e.g. `Nextcloud`, `ExchangeRatesApi`)
- Data source type (REST API, file download, WebDAV, etc.)
- Target account (e.g. `ALDC_QA`)
- Block slug (e.g. `nextcloud-csv`, `exchange-rates-api`)
- Fields needed on the connection (host, username, password, API key, etc.)
- Fields needed on the options (location, primary key, date range, etc.)

Say **PLAN READ** and list the above before continuing.

### 1B — Write the connector module

**File:** `connector/connectors/<name>.py`

```python
class <Name>Connection(ConnectorConnectionBase):
    # Only fields needed to authenticate / reach the source
    field: type

class <Name>Options(ConnectorOptionsBase):
    # Only fields that control what data is fetched
    field: type = default

class <Name>Connector(BaseConnector[<Name>Connection, <Name>Options]):
    """One-line description of what this connector fetches."""

    def run(self, run_options: ConnectorRunOptions) -> list:
        # Fetch data, build a DataFrame, call self.add_response(), return self.responses
        ...
```

**Rules:**
- Import `ConnectorConnectionBase`, `ConnectorOptionsBase`, `ConnectorRunOptions`, `BaseConnector` from `connector.base.base_connector`
- `run()` must call `self.add_response(category_name, table_name, primary_key, dataframe)`
- Do not add retry logic unless the plan explicitly requires it
- If the Prefect block was registered under a different class name, add an alias at the bottom:
  ```python
  # Alias: block registered as <OldName>.
  <OldName>Connection = <NewName>Connection
  ```

Say **CONNECTOR MODULE WRITTEN** and show the file path.

### 1C — Write the deployment file

**File:** `connector/accounts/<ACCOUNT>/deployments/<name>.py`

```python
from connector.accounts.<ACCOUNT>.account import <ACCOUNT>_ACCOUNT
from connector.base.base_connector import MergeScheme, PartitionMethod, PartitionSchemeFull
from connector.connectors.<name> import (
    <Name>Connection,
    <Name>Connector,
    <Name>Options,
)
from connector.lib.warehouse.schema import MergeStrategy

account = <ACCOUNT>_ACCOUNT

# TODO: Replace test values with production config before go-live:
#   topic    — business domain name
#   category — target Snowflake schema category
#   location — production source path
#   primary_key — columns that uniquely identify a row ([] = insert-only)
@account.register_flow(name="<Display Name>")
async def <name>_flow():
    connection = await <Name>Connection.aload(
        account.build_block_id("<block-slug>")
    )
    connector = <Name>Connector(
        account=account,
        topic="<TOPIC>",
        category="<Category>",
        connection=connection,
        options=<Name>Options(...),
    )
    await connector.run_workflow(
        merge_scheme=MergeScheme(
            merge_strategy=MergeStrategy.Insert,
            merge_history=False,
        ),
        partition_scheme=PartitionSchemeFull(method=PartitionMethod.Full),
    )
```

Say **DEPLOYMENT FILE WRITTEN** and show the file path.

### 1D — Write unit tests

**File:** `tests/test_connectors/test_<name>_unit.py`

Required test classes:

| Class | What to test |
|-------|-------------|
| `TestRegistry` | Connector is auto-registered by `__init_subclass__`; alias resolves to same class |
| `TestConnection` | Required fields present; `SecretStr` fields masked in repr |
| `TestOptions` | Defaults correct; field validation |
| `TestConnector<Behavior>` | `run()` returns correct rows; handles edge cases (empty source, malformed data) |

**Rules:**
- Mock all HTTP / file / network calls — never hit the real source in unit tests
- No `assert True` or `assert x is not None` without a follow-up assertion on the value
- Each test must assert real behaviour, not just that code ran

Run `pytest tests/test_connectors/test_<name>_unit.py -v` and confirm all tests pass.
Say **UNIT TESTS WRITTEN — N GREEN**.

### 1E — Update scripts/register_blocks.py

Add a `register_<name>(account)` function following the existing pattern:

```python
def register_<name>(account):
    block_id = account.build_block_id("<block-slug>")
    print(f"\nRegistering block: {block_id}")
    # prompt for each credential field
    conn = <Name>Connection(...)
    conn.save(block_id, overwrite=True)
    print(f"  ✅ Registered: {block_id}")
```

Add a call to `register_<name>(ALDC_QA_ACCOUNT)` inside `main()`.
Say **REGISTER_BLOCKS UPDATED**.

### 1F — Update scripts/run_local.py

Add a section to run the new connector fetch-only:

```python
# <Name> connector
connection = await <Name>Connection.aload(account.build_block_id("<block-slug>"))
connector = <Name>Connector(
    account=account, topic="<TOPIC>", category="<Category>",
    connection=connection, options=<Name>Options(...),
)
responses = connector.run(ConnectorRunOptionsEmpty())
for response in responses:
    print(f"\n✅ topic={response.topic!r}  rows={response.row_count}")
    if response.row_count > 0:
        print(response.dataframe.head())
```

Say **RUN_LOCAL UPDATED**.

### 1G — Write connector summary

See **SUMMARY FORMAT** at the bottom of this skill. Include all files written and test results.
Print **CONNECTOR COMPLETE** when done.

---

## PATH 2 — Modify an existing connector

### 2A — Read the plan and identify scope

Read the existing connector file before making any changes.
Identify exactly what needs to change: a field, a method, error handling, etc.
Say **SCOPE IDENTIFIED**: describe the change in one sentence.

### 2B — Make the targeted edit

Edit only the lines that need to change. Do not rewrite the whole file.

If the change affects the `Connection` or `Options` class fields:
- Check all deployment files that use this connector — they may need updating too
- List any affected deployments before editing

If the change affects `run()` behaviour:
- Update or add unit tests to cover the new behaviour before editing the implementation (TDD)
- Run the full test file after the edit: `pytest tests/test_connectors/test_<name>_unit.py -v`

Say **EDIT COMPLETE** and show a diff summary of what changed.

### 2C — Verify

Run `pytest tests/test_connectors/test_<name>_unit.py -v`.
All tests must be GREEN before finishing.
Say **VERIFIED — N GREEN**.

### 2D — Write connector summary

See **SUMMARY FORMAT** at the bottom. List only modified files and test results.
Print **CONNECTOR COMPLETE** when done.

---

## PATH 3 — Add a new deployment for an existing connector

### 3A — Identify the connector and account

Read the existing connector module to confirm the class names and block slug pattern.
Identify the target account (e.g. `ALDC_PROD`) and whether a block is already registered for it.
Say **CONNECTOR READ** and list: connector module path, connection class name, block slug for the new account.

### 3B — Write the deployment file

Follow the same pattern as 1C, but for the new account.
The connector module itself does not change.
Say **DEPLOYMENT FILE WRITTEN** and show the file path.

### 3C — Update scripts/register_blocks.py

If the new account needs its own block registration, add it.
If the `register_<name>` function already exists and only the account differs, add a new call in `main()`.
Say **REGISTER_BLOCKS UPDATED** (or **NO CHANGE NEEDED** if the existing function covers it).

### 3D — Write connector summary

See **SUMMARY FORMAT** at the bottom. List only new/modified files.
Print **CONNECTOR COMPLETE** when done.

---

## PATH 4 — Diagnose a failing connector

### 4A — Gather information

Ask the user for:
1. The exact error message or stack trace
2. Which command was run (`ai prefect-run`, `run_local.py`, `pytest`, etc.)
3. Whether the Prefect server is running (`http://127.0.0.1:4200`)

Do not guess — ask one question at a time if information is missing.

### 4B — Check block registration

Run:
```python
python -c "
import asyncio
from connector.connectors.<name> import <Name>Connection
from connector.accounts.<ACCOUNT>.account import <ACCOUNT>_ACCOUNT
async def check():
    conn = await <Name>Connection.aload(<ACCOUNT>_ACCOUNT.build_block_id('<block-slug>'))
    print('Block found:', conn.host if hasattr(conn, 'host') else 'OK')
asyncio.run(check())
"
```

If this fails with `Unable to find block document`, the block needs to be registered:
```
python scripts/register_blocks.py
```

### 4C — Check fetch step in isolation

Run `python scripts/run_local.py` and inspect the output.
- If it fails: the issue is in `run()` or the source is unreachable
- If it succeeds: the issue is in `run_workflow()` (likely Snowflake credentials)

### 4D — Report findings

Summarise:
- Root cause identified
- Fix applied (if any)
- Commands to verify the fix

Print **DIAGNOSIS COMPLETE** when done.

---

## SUMMARY FORMAT

Write the connector summary to the path shown at the bottom of this prompt.

```markdown
# Connector Summary: <Name>

**Timestamp:** <ISO 8601>
**Intent:** <New connector / Modify / New deployment / Diagnosis>
**Plan source:** <plan path>

## Files changed

| File | Change | Status |
|------|--------|--------|
| connector/connectors/<name>.py | Created / Modified | ✅ |
| connector/accounts/<ACCOUNT>/deployments/<name>.py | Created / Modified | ✅ |
| tests/test_connectors/test_<name>_unit.py | Created / Modified | ✅ |

## Test results

**Total: N GREEN, 0 RED**

## Block registration

Block slug: `<block-slug>`
Run `python scripts/register_blocks.py` to seed (requires Prefect server running).

## Next steps

- [ ] Run `python scripts/register_blocks.py` to seed the block
- [ ] Run `python scripts/run_local.py` to verify fetch works
- [ ] Run `ai prefect-run <slug>` for full pipeline (requires Snowflake credentials)
- [ ] Replace TODO test values in deployment file with production config
```
