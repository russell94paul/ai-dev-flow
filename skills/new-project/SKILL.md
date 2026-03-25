---
name: new-project
description: Break a project idea into structured features through a scoping interview, feature decomposition, and stub file creation. Use when user wants to start a new project, decompose an idea into features, or runs 'ai new-project'.
---

# New Project Workflow

You will guide the user from a raw project idea to a structured feature list with stub files ready for `ai feature`.

---

## Phase 1: Scoping Interview

Interview the user to sharpen the project scope. Ask **one question at a time**. Do not proceed to the next question until the user has answered. Cover these four areas:

1. Who are the primary users and what problem does this solve for them?
2. What does success look like in 3 months? What is the simplest thing that would be valuable?
3. What are the hard constraints (tech stack, integrations, budget, timeline)?
4. What is explicitly out of scope for this version?

When you have clear answers to all four areas, say: **"SCOPE CONFIRMED"** and proceed.

---

## Phase 2: Feature Decomposition

Based on the confirmed scope, propose **3–8 features**. For each feature provide:

- **Slug**: kebab-case identifier (e.g. `coaching-engine`)
- **Name**: short human-readable title
- **Summary**: one sentence describing what it does
- **Why**: one sentence on why it's needed to achieve the project goal

Present the full list in a clear numbered format. Order by dependency (foundational features first).

---

## Phase 3: Confirmation Gate

Ask the user:

> "Does this feature breakdown look right? Should any features be merged, split, renamed, or removed?"

**Do NOT write any files until the user explicitly confirms the list.**

Iterate on the list until you receive a clear "yes", "confirmed", or equivalent approval. Keep track of any renames — use the final approved slug when writing files.

---

## Phase 4: Write Feature Stubs

For each confirmed feature, create `features/<feature-slug>.md` using this exact structure:

```markdown
# <Feature Name>

## Summary

<One-sentence description of what this feature does.>

## Why

<One sentence on why this feature is needed to achieve the project goal.>

## Open questions

- (To be resolved during the grill phase — run: ai feature "<feature-slug>")
```

Create the `features/` directory if it does not exist. After writing each file, confirm the exact path to the user.

---

## Phase 5: Next Steps

After all stubs are written, print a handoff message in this format:

```
Feature stubs written to features/.

Next: run each feature through the full lifecycle with:

  ai feature "<slug-1>"
  ai feature "<slug-2>"
  ...

Suggested order (foundational first):
  1. ai feature "<slug-1>"
  2. ai feature "<slug-2>"
  ...
```
