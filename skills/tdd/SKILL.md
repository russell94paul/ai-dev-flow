---
name: tdd
description: Test-driven development with red-green-refactor loop. Use when user wants to build features or fix bugs using TDD, mentions "red-green-refactor", wants integration tests, or asks for test-first development.
---

# Test-Driven Development

## Philosophy

**Core principle**: Tests should verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't.

**Good tests** are integration-style: they exercise real code paths through public APIs. They describe _what_ the system does, not _how_ it does it. A good test reads like a specification - "user can checkout with valid cart" tells you exactly what capability exists. These tests survive refactors because they don't care about internal structure.

**Bad tests** are coupled to implementation. They mock internal collaborators, test private methods, or verify through external means (like querying a database directly instead of using the interface). The warning sign: your test breaks when you refactor, but behavior hasn't changed. If you rename an internal function and tests fail, those tests were testing implementation, not behavior.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Anti-Pattern: Horizontal Slices

**DO NOT write all tests first, then all implementation.** This is "horizontal slicing" - treating RED as "write all tests" and GREEN as "write all code."

This produces **crap tests**:

- Tests written in bulk test _imagined_ behavior, not _actual_ behavior
- You end up testing the _shape_ of things (data structures, function signatures) rather than user-facing behavior
- Tests become insensitive to real changes - they pass when behavior breaks, fail when behavior is fine
- You outrun your headlights, committing to test structure before understanding the implementation

**Correct approach**: Vertical slices via tracer bullets. One test → one implementation → repeat. Each test responds to what you learned from the previous cycle. Because you just wrote the code, you know exactly what behavior matters and how to verify it.

```
WRONG (horizontal):
  RED:   test1, test2, test3, test4, test5
  GREEN: impl1, impl2, impl3, impl4, impl5

RIGHT (vertical):
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  RED→GREEN: test3→impl3
  ...
```

## Workflow

### 1. Planning

Before writing any code:

- [ ] Confirm with user what interface changes are needed
- [ ] Confirm with user which behaviors to test (prioritize)
- [ ] Identify opportunities for [deep modules](deep-modules.md) (small interface, deep implementation)
- [ ] Design interfaces for [testability](interface-design.md)
- [ ] List the behaviors to test (not implementation steps)
- [ ] Get user approval on the plan

Ask: "What should the public interface look like? Which behaviors are most important to test?"

**You can't test everything.** Confirm with the user exactly which behaviors matter most. Focus testing effort on critical paths and complex logic, not every possible edge case.

### 2. Tracer Bullet

Write ONE test that confirms ONE thing about the system:

```
RED:   Write test for first behavior → test fails
GREEN: Write minimal code to pass → test passes
```

This is your tracer bullet - proves the path works end-to-end.

### 3. Incremental Loop

For each remaining behavior:

```
RED:   Write next test → fails
GREEN: Minimal code to pass → passes
```

Rules:

- One test at a time
- Only enough code to pass current test
- Don't anticipate future tests
- Keep tests focused on observable behavior

### 4. Refactor

After all tests pass, look for [refactor candidates](refactoring.md):

- [ ] Extract duplication
- [ ] Deepen modules (move complexity behind simple interfaces)
- [ ] Apply SOLID principles where natural
- [ ] Consider what new code reveals about existing code
- [ ] Run tests after each refactor step

**Never refactor while RED.** Get to GREEN first.

## Checklist Per Cycle

```
[ ] Test describes behavior, not implementation
[ ] Test uses public interface only
[ ] Test would survive internal refactor
[ ] Code is minimal for this test
[ ] No speculative features added
```

## Iron Law Checklist

Run this checklist after all cycles are GREEN, before writing `tdd-summary.md`. **All items must pass. The Iron Law cannot be waived.**

```
[ ] All tests pass — zero RED, zero errors
[ ] No `# type: ignore` or `# noqa` added without an inline explanation comment on the same line
[ ] No commented-out code blocks left in the diff
[ ] Every new function or class has ≥ 1 test covering it
[ ] No speculative code added (no unused functions, no TODO stubs shipped)
```

If any item is unchecked: fix it before writing the summary. Do not mark Iron Law as met until all boxes are checked.

## Cognitive Debt & git-blame Checks

Run after the Iron Law checklist:

```
[ ] Every function I cannot explain in one sentence → refactor or flag for reviewer
[ ] git log / git blame on every modified existing file:
      — no prior bug fix reverted by this diff
      — no logic silently removed that other callers depend on
[ ] No new abstraction introduced without ≥ 2 concrete use cases in this diff
```

These are recorded in the `## Design Notes` section of `tdd-summary.md`. Unresolved items are flagged for the Reviewer.

## Summary Output

When all cycles are complete:

### Console — one line only

Print this and nothing more:

```
TDD COMPLETE — summary saved to ./<feature-slug>/tdd-summary.md (tests: N GREEN)
```

Do NOT stream test tables, file diffs, or verbose output to the console unless the user asks.

### Write `build/tdd-summary.md`

Write `build/tdd-summary.md` (relative to the feature root) before printing the console line. Overwrite each run.

The `## Test Output` section **must contain verbatim test runner output** — copy-paste the exact terminal output. `devflow seal --completing build` validates this section against the Iron Law regex. Do not summarise or paraphrase it.

```markdown
# TDD Summary: <feature-slug>

**Timestamp:** <ISO 8601>
**Plan source:** plans/plan.md
**Iron Law:** PASS

## Phases completed

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | <title> | ✅ GREEN |

## Test results

| # | Test description | Status |
|---|-----------------|--------|
| 1 | <behavior tested> | ✅ GREEN |

## Test Output

```
<verbatim test runner output — e.g. "5 passed in 0.42s">
```

## Files touched

- `<path>` — created / modified

## Commands run

```
<exact test-runner commands used>
```

## Design notes

- <decisions, surprises, tradeoffs>
- <cognitive debt flags for reviewer, if any>
- <git-blame findings, if any>
```

Fill every section with real data. No placeholder text.
