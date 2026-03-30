---
name: security-review
description: Perform an OWASP-based security review of the feature diff and produce qa/security-review.md. Use when the security phase is triggered, the user asks for a security review, or devflow gate reports security_triggered=true.
---

# Security Review

Produces `qa/security-review.md` for the current feature. Called by `devflow-qa` during the Security phase.

**Model tier:** Opus — security analysis requires deep reasoning. Set `model_tier: opus` and `model_tier_justification: "Security review analysis"` in Paperclip state before running this skill.

## When to run

Security review is **triggered automatically** when any of the following conditions apply. Check `state.security_triggered` — if `true`, this skill is required before the Deploy gate will pass.

### Default trigger patterns

| Category | File patterns / conditions |
|---|---|
| Auth / identity | `*auth*`, `*login*`, `*password*`, `*token*`, `*jwt*`, `*session*`, `*permission*`, `*credential*` |
| Middleware / guards | `*middleware*`, `*interceptor*`, `*guard*`, `*policy*` |
| Data model / schema | `migrations/`, `*/models.py`, `*.sql`, `*schema*`, `*/entities/*` |
| New API endpoints | Files containing `@app.route`, `router.get`, `router.post`, `path(` |
| External integrations | `*webhook*`, `*integration*`, `*connector*`, `*callback*` |
| Data migrations | `*/migrations/*`, `*migrate*`, `*seed*`, `*fixtures*` |
| PRD keywords | `auth`, `PII`, `payment`, `credentials`, `secret` appearing in `specs/prd.md` body |

Projects can extend or narrow these patterns via `devflow.yaml`:

```yaml
security:
  trigger_patterns:
    add:
      - "src/payments/**"
    remove:
      - "*webhook*"
```

## Process

### Step 1: Establish scope

```
[ ] Read specs/prd.md — note any auth, PII, payment, or external API concerns
[ ] Run: git diff <base-branch>..HEAD --name-only
[ ] Identify which changed files match trigger patterns
[ ] Confirm security_triggered = true in state before proceeding
```

### Step 2: OWASP Top 10 scan

For each changed file in scope, check each OWASP category. Mark N/A only when the category is genuinely not applicable to this file's purpose.

| # | Category | Check |
|---|---|---|
| A01 | Broken Access Control | Are new endpoints/resources properly authorised? Is any role check missing or bypassable? |
| A02 | Cryptographic Failures | Are secrets/tokens stored securely (not in source, not in logs)? Are hashes using bcrypt/argon2, not MD5/SHA1? |
| A03 | Injection | Are user inputs parameterised (SQL, NoSQL, OS commands, LDAP)? No string concatenation in queries? |
| A04 | Insecure Design | Are threat models present for sensitive flows? Is there rate limiting where needed? |
| A05 | Security Misconfiguration | Are debug endpoints disabled? Are default credentials removed? Are error messages non-verbose in prod? |
| A06 | Vulnerable Components | Are new dependencies pinned? Do any have known CVEs (`pip audit`, `npm audit`)? |
| A07 | Auth and Session Mgmt | Are session tokens invalidated on logout? Is MFA considered for privileged actions? |
| A08 | Software Integrity | Are CI/CD steps integrity-checked? Are serialised data payloads validated before deserialisation? |
| A09 | Logging / Monitoring | Are security events (failed auth, privilege escalation attempts) logged without exposing PII? |
| A10 | SSRF | Are outbound URL destinations validated? Is user input used to construct target URLs? |

### Step 3: Assign max_severity

Assign the single highest severity finding across all checks:

| Severity | Criteria |
|---|---|
| `none` | No security issues found |
| `low` | Informational findings; no direct exploitability |
| `medium` | Exploitable with significant attacker effort or limited impact |
| `high` | Directly exploitable; confidentiality/integrity/availability impact |
| `critical` | Directly exploitable; data exfiltration, auth bypass, or full system compromise possible |

### Step 4: Apply severity gate logic

| max_severity | Gate effect | Required action |
|---|---|---|
| none / low | Deploy gate passes | No action needed |
| medium | Deploy gate passes with comment | Post findings to Paperclip issue |
| high | **Deploy gate blocks** | Post findings; notify human `@<waiver-authority>`; set issue to blocked |
| critical | **Hard block — cannot be waived** | Post findings; escalate to team via `devflow /msg <team>`; requires PATCH from human |

### Step 5: Write the artifact

Write `qa/security-review.md` (relative to the feature root). Overwrite on each run.

## Output artifact: `qa/security-review.md`

```markdown
# Security Review: <feature-slug>

**max_severity:** <none|low|medium|high|critical>
**sign_off:** <your agent name or "human-required" if severity = critical>
**Timestamp:** <ISO 8601>
**Scope:** <list of files reviewed>
**Model tier used:** opus

## Trigger Conditions

| Pattern matched | File |
|---|---|
| <pattern> | <file> |

## OWASP Checklist

| # | Category | Status | Findings |
|---|---|---|---|
| A01 | Broken Access Control | PASS/FAIL/N/A | <detail or N/A> |
| A02 | Cryptographic Failures | PASS/FAIL/N/A | <detail or N/A> |
| A03 | Injection | PASS/FAIL/N/A | <detail or N/A> |
| A04 | Insecure Design | PASS/FAIL/N/A | <detail or N/A> |
| A05 | Security Misconfiguration | PASS/FAIL/N/A | <detail or N/A> |
| A06 | Vulnerable Components | PASS/FAIL/N/A | <detail or N/A> |
| A07 | Auth and Session Mgmt | PASS/FAIL/N/A | <detail or N/A> |
| A08 | Software Integrity | PASS/FAIL/N/A | <detail or N/A> |
| A09 | Logging / Monitoring | PASS/FAIL/N/A | <detail or N/A> |
| A10 | SSRF | PASS/FAIL/N/A | <detail or N/A> |

## Findings

| # | File:Line | Category | Severity | Description | Remediation |
|---|---|---|---|---|---|
| 1 | <file>:<line> | <OWASP #> | <severity> | <description> | <fix> |

*(Leave table empty if no findings — do not omit the table.)*

## Remediation Status

| Finding # | Status | Notes |
|---|---|---|
| 1 | Open / Resolved | <detail> |

## Escalation (if max_severity ≥ high)

- [ ] Findings posted to Paperclip issue
- [ ] Human waiver-authority notified
- [ ] Issue set to blocked
```

**Fill every section with real data. Do not leave placeholder text.**

## Seal validation

`devflow seal --completing security` checks:
- `**max_severity:**` field is present and value is one of: `none`, `low`, `medium`, `high`, `critical`
- `**sign_off:**` field is present and non-empty

If seal fails: fix the missing field(s) and re-run seal.

## Interaction with Deploy gate

`devflow gate --entering deploy` reads `state.max_severity`. Ensure the seal writes `max_severity` to state (the seal command does this automatically from the `**max_severity:**` field value).
