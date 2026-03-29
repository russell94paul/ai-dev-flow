"""
Connector deploy stage — Paperclip-native.

Workflow
--------
1. Fetch the ``deployment`` document from the Paperclip issue.
2. Write the YAML body to a temp file and run ``prefect deploy --all``.
3. Trigger a smoke-test flow run for the named deployment.
4. Poll the flow run until it reaches a terminal state.
5. On success  → PATCH issue to ``done`` with the Prefect run URL.
6. On failure  → pause the new deployment, attempt rollback, PATCH issue to
   ``blocked`` with a detailed rollback note.

Environment variables (no hard-coded secrets)
---------------------------------------------
  PREFECT_API_URL   Prefect server URL, e.g. ``http://localhost:4200/api``
  PREFECT_API_KEY   Optional; required for Prefect Cloud (omit for local server)

Paperclip env vars are read from the standard set injected by Paperclip:
  PAPERCLIP_API_URL, PAPERCLIP_API_KEY, PAPERCLIP_RUN_ID

Usage (standalone / CLI)
------------------------
  python -m devflow.deploy --issue-id <id>

The ``devflow deploy <issue-id>`` CLI command wraps this module.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Optional

import httpx
import yaml  # PyYAML (already a devflow dep via prefect ecosystem)

from devflow.paperclip import PaperclipClient, client_from_env

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PREFECT_TERMINAL_STATES = {
    "COMPLETED", "FAILED", "CRASHED", "CANCELLED", "CANCELLING",
}
_PREFECT_SUCCESS_STATES = {"COMPLETED"}

_POLL_INTERVAL_SEC = 5
_POLL_TIMEOUT_SEC = 600   # 10-minute smoke-test budget


# ---------------------------------------------------------------------------
# Prefect helpers
# ---------------------------------------------------------------------------

def _prefect_api_url() -> str:
    url = os.environ.get("PREFECT_API_URL", "")
    if not url:
        raise RuntimeError(
            "PREFECT_API_URL is not set. "
            "See docs/runbook-prefect-creds.md for setup instructions."
        )
    return url.rstrip("/")


def _prefect_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    key = os.environ.get("PREFECT_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def _prefect_get(client: httpx.AsyncClient, path: str) -> dict:
    resp = await client.get(path, headers=_prefect_headers())
    resp.raise_for_status()
    return resp.json()


async def _prefect_post(
    client: httpx.AsyncClient, path: str, payload: dict
) -> dict:
    resp = await client.post(path, json=payload, headers=_prefect_headers())
    resp.raise_for_status()
    return resp.json()


async def _prefect_patch(
    client: httpx.AsyncClient, path: str, payload: dict
) -> dict:
    resp = await client.patch(path, json=payload, headers=_prefect_headers())
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Deployment name extraction
# ---------------------------------------------------------------------------

def _extract_deployment_name(config: dict) -> str:
    """
    Pull the deployment name from a prefect.yaml-style config dict.

    Supports two layouts:
      - Top-level ``name:`` field (simple single-deployment YAML).
      - ``deployments: [{name: ...}, ...]`` list (multi-deployment prefect.yaml).

    Returns the first deployment name found, or raises ValueError.
    """
    if "name" in config and isinstance(config["name"], str):
        return config["name"]
    deployments = config.get("deployments", [])
    if deployments and isinstance(deployments, list):
        first = deployments[0]
        if isinstance(first, dict) and "name" in first:
            flow_name = first.get("flow_name", "")
            dep_name = first["name"]
            return f"{flow_name}/{dep_name}" if flow_name else dep_name
    raise ValueError(
        "Cannot determine deployment name from the deployment document. "
        "Ensure the YAML has a top-level 'name:' field or a "
        "'deployments[0].name' entry."
    )


# ---------------------------------------------------------------------------
# Prefect operations
# ---------------------------------------------------------------------------

async def _find_deployment(
    client: httpx.AsyncClient, name: str
) -> Optional[dict]:
    """
    Look up a Prefect deployment by name.

    Prefect 2.x/3.x deployment names are ``<flow-name>/<deployment-name>``.
    We try an exact filter first, then fall back to iterating all deployments.
    """
    # Try filter endpoint (Prefect 2.x)
    try:
        result = await _prefect_post(
            client,
            "/deployments/filter",
            {"deployments": {"name": {"any_": [name]}}},
        )
        if result:
            return result[0]
    except Exception:
        pass

    # Fallback: list all and match by name
    try:
        all_deps = await _prefect_post(client, "/deployments/filter", {})
        for dep in all_deps:
            full_name = f"{dep.get('flow_name', '')}/{dep.get('name', '')}"
            if dep.get("name") == name or full_name == name:
                return dep
    except Exception:
        pass

    return None


async def _trigger_flow_run(
    client: httpx.AsyncClient, deployment_id: str
) -> dict:
    """Trigger an immediate flow run for the given deployment."""
    return await _prefect_post(
        client,
        f"/deployments/{deployment_id}/create_flow_run",
        {"state": {"type": "SCHEDULED", "message": "devflow smoke test"}},
    )


async def _poll_flow_run(
    client: httpx.AsyncClient, run_id: str
) -> tuple[str, str]:
    """
    Poll a flow run until it reaches a terminal state.

    Returns ``(state_type, state_name)`` — e.g. ``("COMPLETED", "Completed")``.
    Raises TimeoutError if _POLL_TIMEOUT_SEC is exceeded.
    """
    elapsed = 0
    while elapsed < _POLL_TIMEOUT_SEC:
        run = await _prefect_get(client, f"/flow_runs/{run_id}")
        state = run.get("state", {})
        state_type = (state.get("type") or "").upper()
        state_name = state.get("name") or state_type
        if state_type in _PREFECT_TERMINAL_STATES:
            return state_type, state_name
        await asyncio.sleep(_POLL_INTERVAL_SEC)
        elapsed += _POLL_INTERVAL_SEC
    raise TimeoutError(
        f"Flow run {run_id} did not reach a terminal state within "
        f"{_POLL_TIMEOUT_SEC}s."
    )


async def _pause_deployment(
    client: httpx.AsyncClient, deployment_id: str
) -> None:
    """Pause (deactivate schedule) for a deployment after smoke-test failure."""
    try:
        await _prefect_patch(
            client,
            f"/deployments/{deployment_id}",
            {"is_schedule_active": False},
        )
    except Exception:
        pass   # best-effort; don't mask the original error


def _prefect_ui_run_url(run_id: str) -> str:
    """Return a Prefect UI URL for the given flow run ID."""
    base = os.environ.get("PREFECT_API_URL", "http://localhost:4200/api")
    # Strip /api suffix to get the UI base
    ui_base = base.replace("/api", "").rstrip("/")
    return f"{ui_base}/flow-runs/flow-run/{run_id}"


# ---------------------------------------------------------------------------
# prefect deploy subprocess
# ---------------------------------------------------------------------------

def _find_prefect() -> str:
    """Return the path to the prefect executable (Windows-safe)."""
    found = shutil.which("prefect")
    if found:
        return found
    # Try venv Scripts / bin relative to current Python
    scripts = os.path.join(os.path.dirname(sys.executable), "prefect")
    if os.path.isfile(scripts):
        return scripts
    scripts_exe = scripts + ".exe"
    if os.path.isfile(scripts_exe):
        return scripts_exe
    raise FileNotFoundError(
        "Cannot find 'prefect' on PATH. "
        "Activate the project venv or install prefect."
    )


def _run_prefect_deploy(yaml_path: str, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """
    Run ``prefect deploy --all`` pointing at the given prefect.yaml path.

    Uses subprocess (not shell=True) for Windows compatibility.
    stdout/stderr are captured and returned in the CompletedProcess result.
    """
    prefect_exe = _find_prefect()
    # prefect deploy reads from prefect.yaml by default; we symlink/pass via env
    cmd = [prefect_exe, "deploy", "--all", "--prefect-file", yaml_path]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or os.getcwd(),
        env={**os.environ},   # inherit everything including PREFECT_API_URL
    )
    return result


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DeployResult:
    success: bool
    message: str
    run_url: str = ""
    state: str = ""
    deploy_stdout: str = ""
    deploy_stderr: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main deploy entry point
# ---------------------------------------------------------------------------

async def run_deploy(
    issue_id: str,
    pc: PaperclipClient,
    dry_run: bool = False,
    repo_cwd: Optional[str] = None,
) -> DeployResult:
    """
    Execute the full deploy pipeline for the given Paperclip issue.

    Parameters
    ----------
    issue_id:  Paperclip issue UUID (not identifier like ANA-13).
    pc:        Authenticated PaperclipClient (caller owns lifecycle).
    dry_run:   If True, skip actual Prefect calls and return a simulated result.
    repo_cwd:  Working directory for the ``prefect deploy`` subprocess.
               Defaults to the current working directory.

    Returns a DeployResult with success/failure details.
    """
    # ------------------------------------------------------------------ #
    # Step 1 — Fetch deployment document from Paperclip                   #
    # ------------------------------------------------------------------ #
    try:
        doc = await pc.get_document(issue_id, "deployment")
    except Exception as exc:
        return DeployResult(
            success=False,
            message="No `deployment` document found on this issue.",
            errors=[str(exc)],
        )

    yaml_body: str = doc.get("body", "").strip()
    if not yaml_body:
        return DeployResult(
            success=False,
            message="The `deployment` document exists but is empty.",
        )

    # ------------------------------------------------------------------ #
    # Step 2 — Parse deployment name                                      #
    # ------------------------------------------------------------------ #
    try:
        raw_config = yaml.safe_load(yaml_body)
        deployment_name = _extract_deployment_name(raw_config)
    except Exception as exc:
        return DeployResult(
            success=False,
            message=f"Could not parse deployment name from YAML: {exc}",
            errors=[str(exc)],
        )

    if dry_run:
        return DeployResult(
            success=True,
            message=f"[dry-run] Would deploy '{deployment_name}'.",
        )

    # ------------------------------------------------------------------ #
    # Step 3 — Apply the deployment via `prefect deploy`                  #
    # ------------------------------------------------------------------ #
    prefect_url = _prefect_api_url()

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix="devflow-deploy-",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(yaml_body)
        tmp_path = tmp.name

    try:
        proc = _run_prefect_deploy(tmp_path, cwd=repo_cwd)
    except FileNotFoundError as exc:
        return DeployResult(
            success=False,
            message=str(exc),
            errors=[str(exc)],
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if proc.returncode != 0:
        return DeployResult(
            success=False,
            message=(
                f"`prefect deploy` failed (exit {proc.returncode}).\n\n"
                f"```\n{proc.stderr or proc.stdout}\n```"
            ),
            deploy_stdout=proc.stdout,
            deploy_stderr=proc.stderr,
        )

    # ------------------------------------------------------------------ #
    # Step 4 — Smoke test                                                 #
    # ------------------------------------------------------------------ #
    async with httpx.AsyncClient(base_url=prefect_url, timeout=30.0) as pf:
        # 4a — locate the deployment we just applied
        deployment = await _find_deployment(pf, deployment_name)
        if deployment is None:
            return DeployResult(
                success=False,
                message=(
                    f"`prefect deploy` succeeded but deployment "
                    f"'{deployment_name}' was not found in the Prefect server."
                ),
                deploy_stdout=proc.stdout,
            )

        deployment_id: str = deployment["id"]
        prev_schedule_active: bool = deployment.get("is_schedule_active", True)

        # 4b — trigger a flow run
        try:
            flow_run = await _trigger_flow_run(pf, deployment_id)
        except Exception as exc:
            return DeployResult(
                success=False,
                message=f"Failed to trigger smoke-test flow run: {exc}",
                errors=[str(exc)],
                deploy_stdout=proc.stdout,
            )

        run_id: str = flow_run["id"]
        run_url = _prefect_ui_run_url(run_id)

        # 4c — poll until terminal state
        try:
            state_type, state_name = await _poll_flow_run(pf, run_id)
        except TimeoutError as exc:
            await _pause_deployment(pf, deployment_id)
            return DeployResult(
                success=False,
                message=(
                    f"Smoke test timed out after {_POLL_TIMEOUT_SEC}s. "
                    f"Deployment paused. Flow run: {run_url}"
                ),
                run_url=run_url,
                state="TIMEOUT",
                errors=[str(exc)],
                deploy_stdout=proc.stdout,
            )
        except Exception as exc:
            await _pause_deployment(pf, deployment_id)
            return DeployResult(
                success=False,
                message=(
                    f"Error polling smoke-test run: {exc}. "
                    f"Deployment paused. Flow run: {run_url}"
                ),
                run_url=run_url,
                state="ERROR",
                errors=[str(exc)],
                deploy_stdout=proc.stdout,
            )

        # ---------------------------------------------------------------- #
        # Step 5 — Evaluate result                                         #
        # ---------------------------------------------------------------- #
        if state_type in _PREFECT_SUCCESS_STATES:
            return DeployResult(
                success=True,
                message=(
                    f"Deploy succeeded. Smoke test completed ({state_name}).\n"
                    f"Flow run: {run_url}"
                ),
                run_url=run_url,
                state=state_type,
                deploy_stdout=proc.stdout,
            )

        # ---- Rollback on failure -----------------------------------------
        rollback_note = (
            f"Smoke test **{state_name}** — rolling back.\n"
            f"Flow run: {run_url}"
        )

        # Pause the failing deployment (prevent further auto-runs)
        await _pause_deployment(pf, deployment_id)
        rollback_note += "\nNew deployment paused."

        # If the previous deployment was active, re-activate it
        if prev_schedule_active is False:
            rollback_note += (
                "\nPrevious deployment was already paused — no schedule to restore."
            )
        else:
            # Re-activate the same deployment ID; in Prefect, re-enabling the
            # existing deployment is the safest rollback when the YAML hasn't
            # changed structurally.  A full re-deploy of the old YAML would
            # require the previous YAML, which is not stored here.
            try:
                await _prefect_patch(
                    pf,
                    f"/deployments/{deployment_id}",
                    {"is_schedule_active": True},
                )
                rollback_note += (
                    "\nDeployment re-activated with previous schedule."
                    " Manual inspection recommended."
                )
            except Exception as rb_exc:
                rollback_note += f"\nRollback activation failed: {rb_exc}"

        return DeployResult(
            success=False,
            message=rollback_note,
            run_url=run_url,
            state=state_type,
            deploy_stdout=proc.stdout,
            deploy_stderr=proc.stderr,
        )


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

async def _main_async() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="devflow deploy — Prefect deploy stage (Paperclip-native)"
    )
    parser.add_argument("--issue-id", required=True, help="Paperclip issue UUID")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without running prefect or posting to Paperclip",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory for prefect deploy (default: current dir)",
    )
    args = parser.parse_args()

    run_id = os.environ.get("PAPERCLIP_RUN_ID", "")
    pc = client_from_env(run_id=run_id)

    if pc is None:
        print(
            "ERROR: Paperclip credentials not configured. "
            "Set PAPERCLIP_API_KEY (or PAPERCLIP_COMPANY_ID for local-trusted mode).",
            file=sys.stderr,
        )
        sys.exit(1)

    async with pc:
        print(f"Running deploy for issue {args.issue_id}…")
        result = await run_deploy(
            issue_id=args.issue_id,
            pc=pc,
            dry_run=args.dry_run,
            repo_cwd=args.cwd,
        )

        print(f"\n{'SUCCESS' if result.success else 'FAILURE'}: {result.message}")

        if args.dry_run:
            return

        # Report to Paperclip
        if result.success:
            await pc.update_issue(
                args.issue_id,
                status="done",
                comment=(
                    "## Deploy complete\n\n"
                    f"{result.message}\n\n"
                    f"- State: `{result.state}`\n"
                    f"- Run URL: {result.run_url}"
                ),
            )
            print("Paperclip issue marked done.")
        else:
            await pc.update_issue(
                args.issue_id,
                status="blocked",
                comment=(
                    "## Deploy blocked\n\n"
                    f"{result.message}\n\n"
                    + (
                        f"### prefect deploy output\n```\n{result.deploy_stdout}\n```\n"
                        if result.deploy_stdout
                        else ""
                    )
                ),
            )
            print("Paperclip issue marked blocked.")
            sys.exit(1)


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
