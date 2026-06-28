# Iterate Spec — AR-10: Surface CI security in the compliance dashboard

- **Run ID:** `iterate-2026-06-28-ci-security-dashboard`
- **Intent:** FEATURE (new dashboard capability)
- **Complexity:** medium
- **Spec source:** `Spec/course-launch-compliance-control-coverage.md` → **AR-10** (MUST)
- **Risk flags:** `touches_io_boundary` (reads CI `findings.json` via `json.load`,
  `.trivyignore.yaml` via `yaml.safe_load`, writes `ci-security.json`) — F11 authoritative.

## Problem

`security.yml` (Semgrep + Trivy + Gitleaks + prompt-injection) and `codeql.yml` run
**fail-closed in CI** for both repos, but their results are **not rendered** in the
compliance dashboard. Security therefore *looks absent* — and the Control Grade's
Security dimension renders **n/a** ("no trustworthy local scan"), excluded from the
denominator. The local `.shipwright/securityreports/latest.md` is stale (2026-04-28)
and FP-laden; wiring it would produce a **false CRITICAL** (explicitly forbidden by the
spec handoff). webui has *no* local `securityreports/` at all, so security is fully
invisible there.

## Goal (AR-10 MUST)

Ingest the **CI** security outcome into the dashboard — public-safe, from the
workflow's `findings.json`/SARIF:
1. **Scan date** (from the security.yml run).
2. **Findings by severity** (critical/high/medium/low).
3. **Critical-gate pass/fail** (the merge-blocking gate = 0 critical).
4. **Accepted-via-`.trivyignore` with expiry** (the documented risk register).
5. **Light the grader** Security dimension — flip `security_measurable` +
   populate `security_open_high_critical` so the 10% dimension scores honestly.

## Affected Boundaries

- **Read:** CI `findings.json` / `prompt_risks.json` (GitHub artifact, via existing
  `shared/scripts/github_api.py` helpers — `latest_security_workflow_run`,
  `download_security_findings`, `download_prompt_risks`); repo-root `.trivyignore.yaml`
  (YAML accepted-risk register); committed `.shipwright/compliance/ci-security.json`.
- **Write:** `.shipwright/compliance/ci-security.json` (NEW, **tracked**, public-safe
  summary — this is what makes security visible on the public repo / webui);
  `.shipwright/compliance/dashboard.md` (regenerated).

## Architecture (mini-plan)

**Chosen — decoupled producer + deterministic renderer (mirrors `github_triage`):**
- `lib/ci_security.py` (PURE, offline, fully unit-testable): `summarize_ci_security`
  (finding arrays → public-safe dict), `parse_accepted_risks` (`.trivyignore.yaml` →
  ids + expiry + expired-flag vs a passed `now`), `load_ci_security` / `write_ci_security`
  (read/write the committed JSON, round-trip-safe), `grade_security_signal`
  (summary → `(measurable, open_high_critical)`), `render_ci_security` (dashboard md).
- `tools/refresh_ci_security.py` (network producer CLI): fetch latest run + findings via
  `github_api` → `summarize_ci_security` → `write_ci_security`. **Fail-soft**: gh missing
  / offline / no fresh run / fetch returns `None` → leave the existing committed summary
  untouched (never clobber a good summary with empty; never fabricate a green scan).
- `_control_block.build_grade_inputs`: replace hardcoded `security_measurable=False`
  with `load_ci_security` + `grade_security_signal`.
- `compliance_report.generate`: insert `render_ci_security` block under the Control Verdict.
- `update_compliance.py`: best-effort `refresh_ci_security` before dashboard regen for
  phases that touch the dashboard (iterate/compliance/security/adopt/changelog).

**Rejected alternative — live fetch inside `generate()`:** would make dashboard
rendering do network I/O (non-deterministic, breaks offline tests/CI, slow). Decoupling
the fetch (producer) from the render (reads a committed file) is the established pattern
(`github_triage` producer → triage.jsonl → dashboard reads it) and keeps `generate()`
pure. **Rejected — read the local `securityreports/latest.md`:** stale + FP-laden →
false CRITICAL (spec-forbidden).

**Determinism:** `generate()` reads only the committed `ci-security.json` (frozen
counts/date) + `.trivyignore.yaml` (static); expiry computed against `data.timestamp`.
No network at render time. Same inputs → byte-identical dashboard.

**Grade fit (verified against live data):** all six non-security dims currently score
1.0 → grade A 100/100 with Security n/a. The latest green run (`27950188761`, 2026-06-22)
reports `critical:0, high:3, medium:1` → `open_high_critical = 3` → Security dimension
score `max(0, 1-0.34·3) = 0.0` → grade = 0.90/1.00 = **A 90/100**, "Under full control.
Primarily capped by security." Still an A; honestly reflects 3 open highs. Suppressing
them to hold a vanity 100 would violate the constitution (fix-don't-suppress) and AR-10's
whole purpose. The seam was purpose-built for exactly this — clean fit, no scorer change.

## Acceptance Criteria

- **AC1** `summarize_ci_security` produces a public-safe dict: `scan_date`,
  `by_severity{critical,high,medium,low}`, `total`, `critical_gate` (pass/fail),
  `open_high_critical`, `prompt_injection` count, `source`, `degraded` — **no** finding
  detail (no file paths, code, secrets, exploit hints).
- **AC2** `parse_accepted_risks` reads `.trivyignore.yaml` → one row per entry with
  `id`, `expired_at`, `expired` (bool vs `now`); tolerant of a missing/empty register.
- **AC3** `grade_security_signal` returns `(False, None)` when no/degraded summary
  (→ dimension stays n/a, never a false CRITICAL); `(True, n)` with `n = critical+high`
  when a trustworthy summary exists. Round-trips through `write`/`load`.
- **AC4** `render_ci_security` emits a dashboard section with scan date, the severity
  table, the critical-gate badge, and the accepted-risk register (expired rows flagged).
- **AC5** `build_grade_inputs` lights Security from the committed summary; the dashboard
  Security dimension renders the honest count (✅ when 0 open high/critical, ⚠️ otherwise).
- **AC6** `refresh_ci_security` is fail-soft: returns a status without raising when gh is
  unavailable / no fresh run; never clobbers an existing summary with empty data.

## Confidence Calibration
- **Boundaries touched:** CI `findings.json` / `prompt_risks.json` (read via
  `github_api.download_security_findings` — JSON array); repo-root
  `.trivyignore.yaml` (`yaml.safe_load`); `.shipwright/compliance/ci-security.json`
  (json read/write); the grader seam (`security_measurable` +
  `security_open_high_critical`); the dashboard markdown render.
- **Empirical probes run:**
  - Downloaded the **real** live artifact for the latest green run
    (`security.yml#27950188761`, 2026-06-22) → envelope `by_severity:
    {critical:0, high:3, medium:1}`; confirmed the finding `severity` field +
    that the trivyignore-registered OTel CVE is a *medium* (doesn't hit the
    high/critical seam). Designed the summarizer to these real shapes.
  - Ran the producer against **real GitHub** → wrote the actual
    `ci-security.json` (open_high_critical=3, gate pass).
  - Ran the full `update_compliance.py --phase iterate` → output carried
    `ci_security: {status: written}`; dashboard regenerated to **A (90/100)
    — "Primarily capped by security"**, Security ⚠️ "3 open high/critical",
    plus the new CI Security section. Matches the hand-computed grade
    (0.90/1.00·100). Re-render after the bloat-extraction = byte-identical
    (determinism confirmed).
  - Round-trip probe: `write_ci_security` → `load_ci_security` identity test.
  - Gate probe: ran `anti_ratchet_check.py` (exit 0) after ratcheting
    `compliance_report.py` 413→357 in the baseline.
- **Test Completeness Ledger:** (every testable behavior → tested; 0 untested-testable)

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | `summarize_ci_security` severity/gate/public-safe/prompt | tested | `TestSummarize` (5) |
  | `grade_security_signal` measurable/n-a guards (never false CRITICAL) | tested | `TestGradeSignal` (5) |
  | `write`/`load` round-trip + None root + corrupt | tested | `TestRoundTrip` (5) |
  | `parse_accepted_risks` ids/expiry/tolerant/no-id | tested | `TestAcceptedRisks` (4) |
  | `render_ci_security` date/gate/table/register/expired/not-ingested | tested | `TestRender` (4) |
  | `render_date` ISO/bare/garbage | tested | `TestRenderDate` (3) |
  | `build_grade_inputs` lights Security from committed summary | tested | `TestGraderIntegration` (2) |
  | producer happy-path + every fail-soft branch (no clobber) | tested | `test_refresh_ci_security` (7) |
  | `update_compliance` runs the refresh before the dashboard regen | untestable: `covered-by-existing-test` | thin fail-soft glue over the unit-tested producer; also empirically verified by the real `--phase iterate` run above |
- **Confidence-pattern check:**
  - *Asymptote (depth):* fed the producer the **real** CI artifact, not a
    fixture — the live `by_severity` (3 high) drives the committed summary +
    grade, so this is end-to-end against production data, not a mock.
  - *Coverage (breadth):* pure core (offline, deterministic) covered by
    `test_ci_security.py` (28); network producer covered by injected-`api`
    fail-soft branches (7); no `cross_component` machinery touched → no
    integration-composition behavior required (the F11 `check_integration_coverage`
    recompute will find no `cross_component` files in the diff).
