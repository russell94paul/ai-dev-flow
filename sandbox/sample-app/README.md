# sample-app

Throwaway project for testing ai-dev-flow workflows.

This directory exists so you have a realistic-looking repo to run `ai feature`, `ai tdd`, and `ai new-project` against without touching a real project.

---

## What's here

- `src/app.js` — minimal hello-world module with a TODO comment to simulate pending work

---

## How to use

Run `scripts/devflow-smoke.sh` from the ai-dev-flow root. It copies this directory into `/tmp/devflow-smoke` and prints the exact commands to run from there.

```bash
bash scripts/devflow-smoke.sh
```

Then follow the printed instructions. Nothing in this directory is precious — `/tmp/devflow-smoke` is safe to delete at any time.
