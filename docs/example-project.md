# Example Project: AI Trading Coach

This example demonstrates how ai-dev-flow is used to go from an idea → structured features → implemented feature.

---

## 🧠 Initial Idea

Build an AI-powered trading coach that:

* teaches technical setups
* analyzes user trades
* identifies mistakes
* provides personalized feedback

---

## 🟢 Step 1: Break into Features

Command:

```bash
ai new-project "AI trading coach"
```

---

### Output (simplified)

```text
features/
  knowledge-schema.md
  ingestion-pipeline.md
  coaching-engine.md
  trade-journal.md
  psychology-module.md
```

---

## 🧩 Example Feature Breakdown

### 1. Knowledge Schema

Define structured objects for:

* concepts
* rules
* setups
* psychology principles

---

### 2. Ingestion Pipeline

Process mentor content into structured data:

* extract rules
* tag concepts
* create examples

---

### 3. Coaching Engine

Core system that:

* answers user questions
* analyzes trades
* recommends improvements

---

## 🟣 Step 2: Execute a Feature (GRILL / PRD / PLAN)

Command:

```bash
ai feature "Design knowledge schema"
```

This runs in Claude chat and produces:

```text
knowledge-schema/
  PRD.md     ← written after PRD phase
  plan.md    ← written after PLAN phase
```

---

## 🔍 What Happens Internally

### 1. Grill

* clarifies requirements one question at a time
* identifies edge cases
* explores existing codebase

---

### 2. PRD

* defines feature goals
* outlines constraints
* specifies behavior
* writes `knowledge-schema/PRD.md`

---

### 3. Plan

* breaks work into vertical slices with acceptance criteria
* confirms with user
* writes `knowledge-schema/plan.md`
* prints: `PLAN COMPLETE. To begin TDD run: ai tdd "knowledge-schema"`

---

## 🔵 Step 3: Implement via TDD (Claude Code CLI)

Command:

```bash
ai tdd "knowledge-schema"
```

This hands off to the Claude Code CLI with:

* git guardrails active (Claude must confirm before any git operation)
* the TDD skill (red → green → refactor, one vertical slice at a time)
* the contents of `knowledge-schema/plan.md` as the implementation blueprint

---

### 4. TDD

* implements feature incrementally
* writes failing test first, then minimal code to pass
* validates each slice before moving on

---

## 🧠 Result

You now have:

* a clearly defined feature
* structured documentation
* an implementation plan
* test-driven code

---

## 🔁 Iteration

Repeat for each feature:

```text
feature → PRD → plan → implementation
```

---

## 📚 Knowledge Persistence

All outputs can be stored in an Obsidian vault:

* features become folders
* documents become linked notes
* decisions become traceable

---

## 🚀 Final Outcome

The project evolves from:

```text
idea → vague concept
```

into:

```text
structured features → implemented system → persistent knowledge base
```

---

## 💡 Key Insight

ai-dev-flow is not just executing code.

It is:

> structuring thinking, capturing knowledge, and improving development over time.
