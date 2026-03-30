---
name: write-a-prd
description: Create a PRD through user interview, codebase exploration, and module design, then write specs/prd.md. Use when user wants to write a PRD, create a product requirements document, or plan a new feature.
---

# Write a PRD

Produces `specs/prd.md` (relative to the feature root). Called by `devflow-feature` during the PRD phase.

You may skip steps if you don't consider them necessary for simpler requests.

## Process

### 1. Gather requirements

Ask the user for a long, detailed description of the problem they want to solve and any potential ideas for solutions.

### 2. Explore the codebase

Verify the user's assertions and understand the current state of the codebase before proposing scope.

### 3. Interview until shared understanding

Interview the user relentlessly about every aspect of this plan. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one.

### 4. Sketch modules

Identify the major modules to build or modify. Actively look for opportunities to extract **deep modules** — small interface, deep implementation, testable in isolation.

Check with the user that the modules match their expectations and which ones need tests.

### 5. Determine feature type and security triggers

**Feature type** — classify before writing the PRD (used by all downstream gates):
- `connector` — data pipeline, ETL, integration, webhook, or external API sync
- `bugfix` — fixing a defect; not adding new behaviour
- `refactor` — restructuring without behaviour change
- `new_feature` — everything else

**Security trigger** — set `security_triggered: true` if any of the following are true:
- PRD body mentions: `auth`, `PII`, `payment`, `credentials`, `secret`
- Feature touches: authentication, session management, permissions, data migrations, new API endpoints, external integrations
- Feature type is `connector` (always triggers security review)

Record both in the Paperclip state document if running in a Paperclip heartbeat.

### 6. Write `specs/prd.md`

Create `specs/` if it doesn't exist. Write `specs/prd.md` using the template below. Overwrite on each run.

Also upload to Paperclip: `PUT /api/issues/{id}/documents/prd`

---

## Output: `specs/prd.md`

`devflow seal --completing prd` validates that **all five required sections** are present. Do not omit any of them.

```markdown
# PRD: <Feature Name>

**Feature type:** <new_feature|bugfix|connector|refactor>
**Security triggered:** <true|false>

## Goal

One sentence: what user outcome does this feature deliver?

## Background

Why is this feature needed? What problem does it solve? What is the current state that makes this painful?

## Scope

**In scope:**
- <bullet>

**Out of scope:**
- <bullet>

## Acceptance Criteria

Numbered, testable criteria. Each must be verifiable by a test or a manual check.

1. <criterion>
2. <criterion>

## API Contracts

*(Include this section when the feature creates or changes any API endpoints. Omit only if no endpoints are touched.)*

| Endpoint | Method | Request | Response | Auth required |
|---|---|---|---|---|
| `/api/<resource>` | POST | `{field: type}` | `{id: string}` | Yes |

## Security Scope

State whether a security review is triggered and why. This section is required even when security is not triggered — write "Not triggered: <reason>" in that case.

Examples:
- "Triggered: feature adds auth endpoints and handles user credentials."
- "Not triggered: read-only config change with no user input or external API calls."

## User Stories

Numbered list. Each: "As a <actor>, I want <feature>, so that <benefit>."

1. As a ...

## Testing Decisions

- What makes a good test for this feature (external behaviour, not implementation)
- Which modules will need tests
- Any prior art in the codebase for similar tests

## Further Notes

Any constraints, open questions, or dependencies not covered above.
```

**Fill every required section (Goal, Background, Scope, Acceptance Criteria, Security Scope) with real data. Do not leave placeholder text in these sections.**
