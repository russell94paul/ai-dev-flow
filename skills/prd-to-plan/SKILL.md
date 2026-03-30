---
name: prd-to-plan
description: Turn a PRD into a multi-phase implementation plan using tracer-bullet vertical slices, saved as plans/plan.md. Use when user wants to break down a PRD, create an implementation plan, plan phases from a PRD, or mentions "tracer bullets".
---

# PRD to Plan

Produces `plans/plan.md` (relative to the feature root). Called by `devflow-feature` during the Plan phase, after `write-a-prd` has produced `specs/prd.md`.

## Process

### 1. Confirm the PRD is available

Read `specs/prd.md`. If it isn't present, ask the user to paste it or run the `write-a-prd` skill first.

### 2. Explore the codebase

Understand the current architecture, existing patterns, and integration layers before proposing phases.

### 3. Identify durable architectural decisions (ADRs)

Before slicing into phases, identify high-level decisions that are unlikely to change throughout implementation:

- Route structures / URL patterns
- Database schema shape
- Key data models
- Authentication / authorization approach
- Third-party service boundaries
- Any significant tradeoffs made and why

Each decision that involved a non-obvious tradeoff should be recorded as an ADR entry. These go in the `## ADRs` section.

### 4. Draft vertical slices

Break the PRD into **tracer bullet** phases. Each phase is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
- Do NOT include specific file names or implementation details likely to change
- DO include durable decisions: route paths, schema shapes, data model names

### 5. Define rollback procedure

For each risky phase (database migrations, external API integrations, deploy steps), define how to undo it. At minimum, write one rollback step per phase that has irreversible side effects. The `## Rollback` section must contain ≥ 1 non-empty line — `devflow seal --completing plan` validates this.

### 6. Write verification commands

In `## Verification Commands`, list the exact shell commands that confirm the feature works correctly after deploy. These are used by:
- `devflow-sre` to verify the deploy succeeded
- `devflow seal --completing deploy` to validate the Verification Evidence section

### 7. Consult the user on phase breakdown

Present the proposed phases. Ask:
- Does the granularity feel right?
- Should any phases be merged or split?

Iterate until approved, then write the artifact.

### 8. Write `plans/plan.md`

Create `plans/` if it doesn't exist. Write `plans/plan.md`. Overwrite on each run.

Also upload to Paperclip: `PUT /api/issues/{id}/documents/plan`

---

## Output: `plans/plan.md`

`devflow seal --completing plan` validates that **all four required sections** are present. Do not omit any of them.

```markdown
# Plan: <Feature Name>

> Source PRD: specs/prd.md
> Feature type: <new_feature|bugfix|connector|refactor>

## Phases

Vertical slice phases. Each is end-to-end, demoable on its own.

### Phase 1: <Title>

**PRD criteria covered:** <list from specs/prd.md ## Acceptance Criteria>

**What to build:**
A concise description of this slice. Describe end-to-end behaviour, not layer-by-layer implementation.

**Phase acceptance criteria:**
- [ ] <criterion>

---

### Phase 2: <Title>

...

<!-- Repeat for each phase -->

## ADRs

Record each non-obvious architectural decision as an ADR entry. If no significant decisions were made, write "None — standard patterns applied."

| # | Decision | Alternatives considered | Reason chosen |
|---|---|---|---|
| 1 | <decision> | <alternatives> | <reason> |

## Rollback

Steps to undo this change if something goes wrong in production. At minimum one step per phase with irreversible side effects.

1. <rollback step>
2. <rollback step>

## Verification Commands

Exact shell commands to confirm the feature works correctly after deploy. The SRE agent runs these post-deploy.

```bash
# Example: confirm the new endpoint responds
curl -sf http://localhost:8000/api/<resource> | jq '.status'

# Example: confirm migration applied
python manage.py showmigrations | grep <migration-name>
```

## Diagrams — N/A

*(Remove this section and use the `architecture-diagrams` skill instead if ≥ 2 diagram types are applicable. Keep this section only if diagrams are genuinely not applicable — explain why.)*
```

**Fill all four required sections (Phases, ADRs, Rollback, Verification Commands) with real data.**

After writing `plans/plan.md`, invoke the `architecture-diagrams` skill to produce `ops/architecture.md`.
