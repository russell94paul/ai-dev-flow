#!/usr/bin/env bash
# devflow-smoke.sh
# Prepares a throwaway workspace at /tmp/devflow-smoke so you can exercise
# ai-dev-flow commands without touching a real project.
# Safe to run repeatedly — it refreshes the workspace each time.

set -euo pipefail

SMOKE_DIR="/tmp/devflow-smoke"
SANDBOX_SRC="$(cd "$(dirname "$0")/.." && pwd)/sandbox/sample-app"

# -----------------------------
# Verify sandbox source exists
# -----------------------------
if [[ ! -d "$SANDBOX_SRC" ]]; then
  echo "❌ Sandbox not found at: $SANDBOX_SRC"
  echo "   Make sure you're running this from the ai-dev-flow repo."
  exit 1
fi

# -----------------------------
# Refresh smoke workspace
# -----------------------------
echo "🧹 Refreshing $SMOKE_DIR ..."
rm -rf "$SMOKE_DIR"
cp -r "$SANDBOX_SRC" "$SMOKE_DIR"

echo "✅ Workspace ready at $SMOKE_DIR"
echo ""

# -----------------------------
# Print test instructions
# -----------------------------
cat <<'INSTRUCTIONS'
========================================
 ai-dev-flow smoke test — manual steps
========================================

Notes root for this smoke test:
  /tmp/devflow-notes

Artifacts land at:
  /tmp/devflow-notes/devflow-smoke/detached/features/<slug>/

1. Set notes root and cd into the workspace:

     export AI_DEV_FLOW_NOTES_ROOT=/tmp/devflow-notes
     cd /tmp/devflow-smoke

2. Test: feature workflow (GRILL / PRD / PLAN)

     ai feature "sample sync"

   Expected outcomes:
   - Claude GUI opens with the GRILL/PRD/PLAN prompt
   - After PLAN phase, Claude writes:
       /tmp/devflow-notes/devflow-smoke/<branch>/features/sample-sync/specs/prd.md
       /tmp/devflow-notes/devflow-smoke/<branch>/features/sample-sync/plans/plan.md
   - Claude prints: PLAN COMPLETE. To begin TDD run: ai tdd "sample-sync"

3. Test: TDD handoff (requires plan.md from step 2)

     ai tdd "sample-sync"

   Expected outcomes:
   - Prompt written to /tmp/devflow-tdd-sample-sync.md
   - @/tmp/devflow-tdd-sample-sync.md copied to clipboard
   - A new Claude Code window opens (outside VS Code)
   - AutoHotkey pastes the @file message automatically after ~6 s
   - Claude Code loads guardrails + TDD skill + plan and begins TDD
   - On completion, summary written to:
       /tmp/devflow-notes/devflow-smoke/<branch>/features/sample-sync/build/tdd-summary.md

   Fallback (if AHK misses):
   - The original terminal prints the prompt path
   - Paste manually in Claude Code: @/tmp/devflow-tdd-sample-sync.md

   If plan.md is missing, you see:
       ❌ No plan found at: /tmp/devflow-notes/devflow-smoke/<branch>/features/sample-sync/plans/plan.md

   To test the error path before running step 2:
     ai tdd "no-such-feature"

4. Test: new-project workflow

     ai new-project "Sample AI app"

   Expected outcomes:
   - Claude GUI opens with the new-project scoping skill
   - After confirmation, Claude writes feature stubs to:
       /tmp/devflow-smoke/features/<slug>.md

5. Test: single-skill dispatch

     ai grill-me "review my sync design"

   Expected: Claude GUI opens with the grill-me skill and your context.

========================================
 Cleanup
========================================

When done, the workspace is throwaway:

     rm -rf /tmp/devflow-smoke

INSTRUCTIONS
