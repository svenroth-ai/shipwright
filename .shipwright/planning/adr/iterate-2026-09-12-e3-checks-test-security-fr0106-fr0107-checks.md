# Mechanise FR-01.06/FR-01.07's 7 AC-evidence lines, or downgrade with a reason

**Run:** `iterate-2026-09-12-e3-checks-test-security` · campaign
`req3-06-enforcement-mono` · sub-iterate `e3`.

## Context

The AC-evidence ledger
(`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`)
named 7 `prompt-only (mechanisable)` lines as this sub-iterate's scope: 5 in
FR-01.06 (`/shipwright-test`) and 2 in FR-01.07 (`/shipwright-security`). Per
campaign decision D7, each must be **enforced with a real check, or
downgraded to `prompt-only (judgement)` with a documented reason** — never a
weaker gate that pretends an oracle exists when it does not.

## Decision

- **FR-01.06 #5** (recorded e2e counts are the tool's own) — enforced.
  `check_e2e_counts_reconciled` (`shared/scripts/tools/verifiers/
  _test_gate_extras.py`) reconciles `shipwright_test_results.json`'s `e2e`
  block against Playwright's own `e2e-results.json` `stats`.
- **FR-01.06 #6** (generation happens when journeys are planned) — enforced
  as a floor, split into **#6** (existence floor, closed) / **#6b**
  (per-journey matching, deferred — `trg-2f7a840a`). `check_e2e_specs_
  exist_when_journeys_planned` (`_test_gate_specs.py`).
- **FR-01.06 #7** (design-fidelity triage) — enforced (mechanisable half).
  `check_design_fidelity_triage_matches_recomputation`
  (`_test_gate_fidelity.py`) recomputes Resolved/Regression/Persistent/
  Unchecked as a pure function of two already-recorded values.
- **FR-01.06's 2 constitution-rule mentions** ("test every AC at the layer
  that can falsify it") — downgraded to `prompt-only (judgement)`. No
  per-phase oracle exists for a cross-cutting rule whose mechanical
  enforcement is a not-yet-built Phase-3 work unit; building one here would
  be the "weaker gate that pretends" D7 forbids. Drift-tested:
  `shared/tests/test_constitution_ac_layer_rule_drift.py`.
- **FR-01.07 #6/#7** ("fixed" means tests passed; a judgement finding
  carries decision+reason) — downgraded to `prompt-only (judgement)`.
  Grep-confirmed: `_remediation_status` is read (default `"open"`) but never
  written by any code path; no per-finding decision is ever recorded either.
  Drift-tested: `plugins/shipwright-security/tests/
  test_remediation_judgement_drift.py`.

## Consequences

Re-measured ledger totals (`measure_ac_evidence_ledger.py --json`, verified
after every edit): **14** prompt-only/mechanisable · **29**
prompt-only/judgement · **16** enforced-untested · **33** unimplemented ·
**80** enforced-tested. All 7 originally-scoped lines are now enforced or
downgraded with a reason; none left as a bare deferral note (an earlier
draft's mistake, caught by code review — see below).

## Rationale

`journey_coverage.py` (criterion 14) already closes the per-journey
name-matching half properly; wiring it into #6b needs relocating its shared
logic to `shared/scripts/lib/` first (ADR-045: a shared verifier never
imports a single plugin's own `scripts/lib`) — out of scope for a
checks-only sub-iterate, filed as `trg-2f7a840a`. The two FR-01.07 downgrades
and the two constitution mentions share one shape: reading comprehension
over free text / a rule with no oracle yet, the honest ceiling per D7 is a
drift test pinning the instruction, not a gate.

## Rejected

- **Building a `.06`-scoped check for the constitution rule directly** —
  would misattribute a cross-cutting, 5-phase rule to one FR and duplicate
  the named Phase-3 enforcement-register work unit.
- **A prose deferral note without flipping the status tag** (first draft) —
  code review (GLM, medium) correctly rejected this: the AC requires the
  TAG itself to change; a note alone leaves `measure_ac_evidence_ledger.py`
  still counting the line as open mechanisable.
- **Silently coercing malformed Playwright `stats` fields to 0** — hides
  exactly the format-drift the check exists to catch; changed to a distinct
  "malformed/unrecognized stats schema" FAIL, leaving genuinely-absent
  fields (some reporter versions omit zero-count fields) defaulting to 0.
- **SKIP on a missing `design_fidelity.triage` block, or on a missing whole
  `design_fidelity` block** — both let "regression"/"never-checked" screens
  evade the gate by omission; both are now FAILs when the recomputation
  (from the two source files) finds screens genuinely needing triage.

## Self-Review (Step 3.6, checklist)

1. **Spec Compliance** — pass. All 7 originally-scoped lines enforced or
   downgraded with a reason; the 4 REQ3.05 enforced-untested lines untouched.
2. **Error Handling** — pass. Every new check wraps JSON parsing in
   `try/except (JSONDecodeError, OSError)`; non-dict/non-list/malformed
   shapes handled defensively; nothing raises.
3. **Security Basics** — pass. Symlink-escape containment
   (`_is_within`/`_safe_project_file`) added for every fixed-name project
   file AND for globbed `e2e/**/*.spec.ts` discovery (round 2 finding).
4. **Test Quality** — pass. 70+ tests across pass/fail/skip paths per check,
   plus 4 symlink-escape regressions and 2 empirical boundary probes (BOM,
   contradiction-detection).
5. **Performance Basics** — pass. No DB access; globbing bounded to
   project-controlled directories; no N+1/unbounded-fetch patterns.
6. **Naming & Structure** — pass. `_test_gate_extras.py` (#5, 256 lines) /
   `_test_gate_specs.py` (#6, 145 lines) / `_test_gate_fidelity.py` (#7, 294
   lines) / `_test_gate_paths.py` (shared path-safety helpers, 80 lines) —
   split proactively to stay under the 300-line guideline, mirroring the
   `_project_gate_*.py` precedent. `_test_gate_paths.py` was split out of
   `_test_gate_extras.py` a second time (Tier-3 CI review round, below) once
   the escape/absence distinction pushed it back over 300 lines.
7. **Affected Boundaries** (ADR-024) — pass, WITH an empirical finding (see
   Confidence Calibration below): new READERS only over three pre-existing
   serialized formats (`shipwright_test_results.json`, `e2e-results.json`,
   `design-fidelity-report.json`) plus one human-edited one
   (`claude-plan-e2e.md`) — no new format introduced, no writer changed. The
   human-edited boundary got a REAL probe, not just reasoning, and it found
   a genuine bug (below).

## Confidence Calibration (Step 3.8 — fires: `touches_io_boundary` set)

Boundaries touched: 3 machine-written JSON artifacts (read-only,
`_safe_project_file` + `json.loads` inside `try/except`) and 1 human-edited
markdown plan (`claude-plan-e2e.md`, read by `check_e2e_specs_exist_when_
journeys_planned`).

- **Probe 1 (human-edited plan, BOM)** — wrote a plan whose `## User Flows`
  heading is the literal first line, prefixed with a UTF-8 BOM (as Notepad
  and some Windows editors do). **FINDING:** `read_text(encoding="utf-8")`
  keeps the BOM as part of the first line, so `^##` (anchored, `MULTILINE`)
  never matched — a real false-negative (the check silently SKIPped a
  project that had, in fact, declared a flow). **FIX:** switched to
  `encoding="utf-8-sig"`. **RE-PROBED:** same file now correctly reports
  "declares user flows" (`ok=False` when no spec exists yet, as expected).
- **Probe 2 (human-edited plan, CRLF / non-ASCII / trailing whitespace)** —
  no finding; `_plan_declares_a_flow` handled all three correctly (already
  covered by existing pytest fixtures too).
- **Probe 3 (machine-written JSON, BOM)** — `json.loads` on a BOM-prefixed
  machine-written file raises `json.JSONDecodeError`; every reader already
  wraps this in `try/except (JSONDecodeError, OSError)` and reports
  "malformed ...: <exc>" — a safe, explicit failure, not a silent wrong
  answer. No finding requiring a fix (the failure mode is already correct).

**Asymptote:** one finding (BOM on the human-edited boundary) → fixed → two
consecutive no-finding probes after (CRLF/non-ASCII/whitespace on the same
boundary; BOM on the machine-written boundary, safe by design) — the
human-edited boundary is calibrated. Not probed: permissions/unreadable
files on the plan path (already routed through the same `except OSError:
continue` as a missing file — same code path as the existing
`test_unreadable_plan_file_is_skipped_not_crashed` fixture, judged
acceptable to not duplicate empirically here).

## External-Plan-Review-Findings (Step 3.5)

12 findings (GLM: approve · openai: revise) — merged, medium+ dispositioned
below; low findings folded into the build directly.

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| 1 | high | Check #5 could SKIP while `e2e` counts are recorded but unverifiable | accepted-and-fixed — FAILs instead of SKIPping |
| 2 | medium | #6's existence check is a weak oracle vs. per-journey matching | accepted-with-reason — floor documented, `trg-2f7a840a` filed |
| 3 | medium | Fidelity recomputation assumes matching provenance/vocabulary between the two source artifacts | accepted-with-reason — documented as a known, accepted staleness-detection gap (no shared run id exists yet); failure message names both files |
| 4 | medium | Playwright `stats` reconciliation needs an executable schema contract for retries/flaky/interrupted | accepted-and-fixed — malformed-field detection added; existing retry semantics already covered by tests |
| 5 | medium | `check_e2e_counts_reconciled` duplicates `playwright_runner`'s formula instead of importing it | accepted-with-reason — ADR-045 forbids the import; a drift-note cross-reference was added to `playwright_runner.py`'s own docstring instead |
| 6 | low | Judgement drift tests pin full sentences, pressure to freeze doc wording | rejected-with-reason — the pinned sentences are short, normative, load-bearing clauses, not full paragraphs; churn risk judged acceptable |
| 7 | low | No explicit statement that the 4 REQ3.05 lines are unaffected | accepted-and-fixed — verified via `git log`/grep that no shared function was touched; self-review item 1 states it |
| 8 | low | Unreadable/symlinked plan files could raise instead of SKIP | accepted-and-fixed — `_is_within` + `except OSError: continue` |
| 9 | low | Oversized/symlinked JSON inputs | accepted-and-fixed — `_safe_project_file` symlink-escape containment added to every fixed-name read |
| 10-12 | low/medium | (duplicates of 2-4, GLM/openai overlap) | folded into the above |

## External-Code-Review-Findings (Step 3.7, two rounds)

Round 1 (5 findings) — all accepted-and-fixed: SKIP→FAIL on absent triage
block; symlink-escape hardening; ambiguous test assertion pinned; case
sensitivity/terminator on the heading regex; missing
`_categorize_fidelity_screen("skipped", "pass")` test.

Round 2 (7 findings, after round-1 fixes landed):

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| 1 | medium | #6 weak oracle (repeat) | accepted-with-reason — ledger split into #6/#6b, `trg-2f7a840a` |
| 2 | medium | Fidelity gate SKIPped when the WHOLE `design_fidelity` block (not just `triage`) is absent, while build declares screens | accepted-and-fixed — now FAILs "comparison step never ran" |
| 3 | low | Discovered `e2e/**/*.spec.ts` files not symlink-escape-checked | accepted-and-fixed — filtered through `_is_within` |
| 4 | medium | `e2e.skipped: true` claim not checked against contradicting Playwright evidence | accepted-and-fixed — FAILs when stats show non-zero activity |
| 5 | low | Ledger row #6 tagged bare `enforced, tested` despite the check's own weak-oracle caveat | accepted-and-fixed — split into #6/#6b, matching campaign's #8/#8b precedent |
| 6 | low | `test_passes_when_counts_match` pinned an unrelated severity-default implementation detail | accepted-and-fixed — assertion dropped |
| 7 | low | Heading regex `IGNORECASE` diverges from `journey_plan.py`'s real (case-sensitive) grammar | accepted-and-fixed — reverted to case-sensitive, exact mirror |

Round 3 (Tier-3 CI review on PR #748, required check, 3 findings after
rounds 1-2 landed):

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| 1 | high | Malformed/missing `screens` fields (build- and test-side) silently coerced to empty, letting a fabricated all-zero triage block pass without comparing any screens | accepted-and-fixed — both sides now FAIL on a present-but-wrong-type field; a declared-nonempty build side with a missing/empty test side also FAILs |
| 2 | high | An escaping symlink for `design-fidelity-report.json` was treated identically to "absent" (SKIP), letting a project-controlled symlink suppress the whole gate | accepted-and-fixed — new `_project_file_or_escape` (`_test_gate_paths.py`) distinguishes absent from escaping; the fidelity check now FAILs on escape |
| 3 | medium | `bool` is an `int` subclass in Python; recorded `total`/`passed`/`flaky` compared with plain `!=` let a malformed `total: true` reconcile against an expected value of 1 | accepted-and-fixed — validated as non-negative integers first, mirroring `_stat_field`'s existing discipline |

Round 3's own fix introduced a regression the Stage-2 code-reviewer caught on
re-review before merge: the round-3 fix #1 above did not honour
`design_fidelity`'s own documented boolean `skipped` flag (step-3.7-design-
fidelity.md's record template), so an honest could-not-run record now
false-failed as fabrication whenever the build side declared screens. Fixed
in the same PR: `skipped is True` now SKIPs (uncontradicted by real screens
or a recorded triage block, which still FAIL as a self-contradiction) before
the round-3 emptiness check runs; a related low finding (a non-empty
`screens` list holding only non-dict junk entries reconciling the same way
an empty list did) was closed in the same pass by measuring the obligation
over usable (dict) entries only.
