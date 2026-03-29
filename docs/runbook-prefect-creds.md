# Runbook: Prefect credentials for ai-dev-flow

This runbook explains how to configure Prefect credentials so the deploy stage
can publish deployments, trigger smoke-test flow runs, and report results back
to Paperclip without any hard-coded secrets.

---

## Environment variables

| Variable          | Required | Description |
|-------------------|----------|-------------|
| `PREFECT_API_URL` | **Yes**  | Base URL of the Prefect REST API. |
| `PREFECT_API_KEY` | No       | API key — required for Prefect Cloud; omit for a local self-hosted server. |

---

## Local Prefect server (development)

Start a local Prefect server with Docker Compose:

```bash
# From the repo root
docker compose -f scripts/prefect-sandbox.yml up -d
```

Then export:

```bash
export PREFECT_API_URL=http://localhost:4200/api
# No PREFECT_API_KEY needed for a local server
```

Or start Prefect directly (no Docker):

```bash
prefect server start
export PREFECT_API_URL=http://127.0.0.1:4200/api
```

---

## Prefect Cloud

1. Log in at [app.prefect.cloud](https://app.prefect.cloud).
2. Go to **Settings → API keys** and create a new key for the deploy agent.
3. Copy the workspace API URL from **Settings → Workspaces**:
   it looks like `https://api.prefect.cloud/api/accounts/<acct-id>/workspaces/<ws-id>`.

```bash
export PREFECT_API_URL=https://api.prefect.cloud/api/accounts/<acct-id>/workspaces/<ws-id>
export PREFECT_API_KEY=<your-api-key>
```

---

## Adding to your shell profile

Append to `~/.bashrc`, `~/.zshrc`, or `~/.bash_profile`:

```bash
# Prefect (ai-dev-flow deploy stage)
export PREFECT_API_URL=http://localhost:4200/api
# export PREFECT_API_KEY=<key>   # uncomment for Prefect Cloud
```

Reload:

```bash
source ~/.bashrc   # or source ~/.zshrc
```

---

## Windows (PowerShell / Git Bash)

**PowerShell (session):**

```powershell
$env:PREFECT_API_URL = "http://localhost:4200/api"
# $env:PREFECT_API_KEY = "<key>"
```

**PowerShell (permanent — current user):**

```powershell
[System.Environment]::SetEnvironmentVariable("PREFECT_API_URL","http://localhost:4200/api","User")
```

**Git Bash:**

```bash
export PREFECT_API_URL=http://localhost:4200/api
```

Add the exports to `~/.bash_profile` for persistence across sessions.

---

## Paperclip + Prefect credentials together

The deploy stage reads **both** Paperclip and Prefect variables:

```bash
# Paperclip (injected automatically during heartbeats)
export PAPERCLIP_API_URL=http://127.0.0.1:3100
export PAPERCLIP_API_KEY=<agent-jwt>
export PAPERCLIP_COMPANY_ID=<company-uuid>
export PAPERCLIP_RUN_ID=<run-uuid>

# Prefect
export PREFECT_API_URL=http://localhost:4200/api
# export PREFECT_API_KEY=<prefect-cloud-key>
```

For manual / emergency CLI runs, set the Paperclip vars by running:

```bash
npx paperclipai agent local-cli devflow-sre --company-id <company-id>
```

This prints the required `PAPERCLIP_*` exports.  Then add `PREFECT_API_URL`
and optionally `PREFECT_API_KEY`, and run:

```bash
devflow deploy <issue-uuid>
```

---

## Verifying the setup

```bash
# Check Prefect is reachable
curl $PREFECT_API_URL/health

# Dry-run the deploy stage (no Prefect calls, no Paperclip updates)
devflow deploy <issue-uuid> --dry-run
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `PREFECT_API_URL is not set` | Missing env var | Set it in your shell or `.env` |
| `Cannot find 'prefect' on PATH` | Prefect not installed or venv inactive | `pip install prefect` or activate venv |
| `prefect deploy` exits non-zero | Invalid YAML or Prefect server unreachable | Check server logs; validate YAML with `prefect deploy --help` |
| Smoke test times out | Long-running flow or stalled worker | Check Prefect UI → Flow Runs for the stuck run |
| 401 from Prefect API | Missing / expired `PREFECT_API_KEY` | Regenerate key in Prefect Cloud settings |
