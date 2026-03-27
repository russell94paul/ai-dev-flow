#!/usr/bin/env bash
# devflow-smoke.sh
# Prepares a throwaway workspace at /tmp/devflow-smoke so you can exercise
# all ai-dev-flow commands without touching a real project.
# Safe to run repeatedly — refreshes the workspace each time.

set -euo pipefail

SMOKE_DIR="/tmp/devflow-smoke"
NOTES_DIR="/tmp/devflow-notes"
SANDBOX_SRC="$(cd "$(dirname "$0")/.." && pwd)/sandbox/sample-app"

# -----------------------------
# Verify sandbox source exists
# -----------------------------
if [[ ! -d "$SANDBOX_SRC" ]]; then
  echo "❌ Sandbox not found at: $SANDBOX_SRC"
  echo "   Make sure you're running from outside the smoke directory."
  exit 1
fi

# -----------------------------
# Refresh smoke workspace
# On Windows the directory itself may be locked (Device or resource busy)
# so we wipe the contents rather than the directory.
# -----------------------------
echo "🧹 Refreshing $SMOKE_DIR ..."
if rm -rf "$SMOKE_DIR" 2>/dev/null; then
  mkdir -p "$SMOKE_DIR"
else
  # Directory is locked — clear contents instead
  find "$SMOKE_DIR" -mindepth 1 -delete 2>/dev/null || true
fi

cp -r "$SANDBOX_SRC"/. "$SMOKE_DIR"/

# Initialise a git repo so branch/slug detection works
cd "$SMOKE_DIR"
git init -q
git add -A
git commit -q --allow-empty -m "smoke: initial commit"

echo "✅ Workspace ready at $SMOKE_DIR"
echo ""

# -----------------------------
# Clean previous notes output
# -----------------------------
rm -rf "$NOTES_DIR"
echo "🗑️  Cleared previous notes at $NOTES_DIR"
echo ""

# -----------------------------
# Print test instructions
# -----------------------------
cat <<INSTRUCTIONS
========================================
 ai-dev-flow smoke test — manual steps
========================================

Workspace:   $SMOKE_DIR
Notes vault: $NOTES_DIR  (set via AI_DEV_FLOW_NOTES_ROOT)

Run this once to point artifacts at the smoke notes dir:

     export AI_DEV_FLOW_NOTES_ROOT=$NOTES_DIR
     cd $SMOKE_DIR

--- Manifest & Prep ---

1. Create the project manifest (interactive wizard):

     ai init

   Expected: prompts detect requirements.txt + pytest + Prefect,
   writes $NOTES_DIR/devflow-smoke/main/devflow.yaml

2. Bootstrap the environment:

     ai prep "sample-sync"

   Expected: runs pip install, writes intake/prep.md, updates state.json

--- Feature Workflow ---

3. Run the feature lifecycle (GRILL → PRD → DIAGRAM → PLAN):

     ai feature "sample sync"

   Expected: Claude GUI opens, guides through 4 phases, writes:
     $NOTES_DIR/devflow-smoke/main/features/sample-sync/specs/prd.md
     $NOTES_DIR/devflow-smoke/main/features/sample-sync/specs/diagram.md
     $NOTES_DIR/devflow-smoke/main/features/sample-sync/plans/plan.md
   Prints: PLAN COMPLETE. To begin TDD run: ai tdd "sample-sync"

4. TDD handoff (requires plan.md from step 3):

     ai tdd "sample-sync"

   Expected: new Claude Code window opens with guardrails + TDD + plan,
   writes $NOTES_DIR/devflow-smoke/main/features/sample-sync/build/tdd-summary.md

--- QA, Prefect & Deploy ---

5. Run QA suites:

     ai qa "sample-sync"

   Expected: runs pytest tests/unit, writes qa/unit.md, generates qa/evidence.md

6. Run Prefect flow:

     ai prefect-run "sample-sync"

   Expected: starts prefect sandbox (Docker), runs prefect.run_command,
   executes assertions, writes:
     $NOTES_DIR/devflow-smoke/main/features/sample-sync/qa/prefect-run.md
     $NOTES_DIR/devflow-smoke/main/features/sample-sync/qa/assertions.md
   Refreshes qa/evidence.md with updated Prefect run status

7. Run deploy steps:

     ai deploy "sample-sync"

   Expected: runs deploy.steps from manifest, writes build/deploy.md

--- New Project ---

8. Decompose a new project idea:

     ai new-project "Sample AI app"

   Expected: Claude GUI opens, writes:
     $NOTES_DIR/devflow-smoke/main/features/<slug>/intake/stub.md

--- State ---

9. Inspect state:

     cat $NOTES_DIR/devflow-smoke/main/features/sample-sync/state.json

10. Reset state for a feature:

     ai state clean "sample-sync"

   Expected: removes state.json

========================================
 Cleanup
========================================

When done:

     rm -rf $NOTES_DIR

(The workspace at $SMOKE_DIR is reused across runs — just re-run this script to reset it.)

INSTRUCTIONS
