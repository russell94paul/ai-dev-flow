## How Skills Work

Each skill contains:

- a structured prompt
- a defined purpose
- integration into workflows

The CLI composes these skills into larger workflows.

# Agent Skills

ai-dev-flow is built on modular "skills".

Each skill is a reusable prompt module that defines a specific capability within the development workflow.

Skills are composed together to form workflows like:

- new-project → feature breakdown
- feature → grill → PRD → plan → TDD

These skills originate from mattpocock/skills and have been adapted for this system.

## Planning & Design

These skills help you think through problems before writing code.

- **write-a-prd** — Create a PRD through an interactive interview, codebase exploration, and module design. Filed as a GitHub issue.

- **prd-to-plan** — Turn a PRD into a multi-phase implementation plan using tracer-bullet vertical slices.

- **prd-to-issues** — Break a PRD into independently-grabbable GitHub issues using vertical slices.

- **grill-me** — Get relentlessly interviewed about a plan or design until every branch of the decision tree is resolved.

- **design-an-interface** — Generate multiple radically different interface designs for a module using parallel sub-agents.

- **request-refactor-plan** — Create a detailed refactor plan with tiny commits via user interview, then file it as a GitHub issue.


## Development

These skills help you write, refactor, and fix code.

- **tdd** — Test-driven development with a red-green-refactor loop. Builds features or fixes bugs one vertical slice at a time.

- **triage-issue** — Investigate a bug by exploring the codebase, identify the root cause, and file a GitHub issue with a TDD-based fix plan.

- **improve-codebase-architecture** — Explore a codebase for architectural improvement opportunities, focusing on deepening shallow modules and improving testability.

- **migrate-to-shoehorn** — Migrate test files from `as` type assertions to @total-typescript/shoehorn.

- **scaffold-exercises** — Create exercise directory structures with sections, problems, solutions, and explainers.


## Tooling & Setup

- **setup-pre-commit** — Set up Husky pre-commit hooks with lint-staged, Prettier, type checking, and tests.

- **git-guardrails-claude-code** — Set up Claude Code hooks to block dangerous git commands (push, reset --hard, clean, etc.) before they execute.

## Writing & Knowledge

- **write-a-skill** — Create new skills with proper structure, progressive disclosure, and bundled resources.


- **edit-article** — Edit and improve articles by restructuring sections, improving clarity, and tightening prose.

- **ubiquitous-language** — Extract a DDD-style ubiquitous language glossary from the current conversation.


- **obsidian-vault** — Search, create, and manage notes in an Obsidian vault with wikilinks and index notes.
