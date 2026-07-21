# Iterate — Sub-iterate-runner finalization integrity (F3 + F5c + no-direct-decision_log)

- **Run ID:** `iterate-2026-07-20-runner-finalization-integrity`
- **Intent:** CHANGE (harden finalization contract + F11 verifier)
- **Complexity:** medium (history-calibrated; risk floor medium)
- **Risk flags:** `cross_component` (prose-derived: pipeline phase validator + campaign
  runner machinery; the F11 `check_integration_coverage` recomputes from the diff —
  see Confidence Calibration for the diff-recompute note)
- **Spec Impact:** NONE — framework/tooling change; no product FR or planning `spec.md`
  is affected (monorepo is library-scoped; this changes SDLC machinery, not app behavior).

## Problem (evidence)

WebUI campaign `2026-07-18-mission-artifacts` ran 4 sub-iterates via the
`sub-iterate-runner` subagent under campaign mode. All reported a clean F11
verifier, yet:

- decision-drop present for **2 of 4**,
- `iterates/<run_id>.json` record present for **only 1 of 4**,
- **one** sub-iterate wrote its ADR **directly into `decision_log.md`**, claiming a
  sequential `ADR-NNN` in its worktree — the exact collision `write_decision_drop`
  exists to prevent (two parallel worktrees each compute `max(ADR)+1`). No collision
  occurred, by luck.

**Root causes found (investigation):**

1. `sub-iterate-runner.md` Step 4 Finalization names F3 as **`write_decision_log.py`**
   (the direct-append, number-claiming path) instead of the canonical iterate F3
   **`write_decision_drop.py`**, and **omits F5c entirely** (`finalize_iterate.py`/F5b
   does NOT append the `iterates/<run_id>.json` entry — F5c is a separate step).
2. The runner contract has **no F11 self-verify step**, so it cannot detect its own
   missing F3/F5c — hence "clean F11" was never actually computed.
3. `references/reflection.md` "For decisions" still points iterates at
   `write_decision_log.py` (a second stale direct-write path).
4. The F11 `check_adr_in_iterate_history` run-id branch accepts a decision-drop that
   merely **exists** — an empty `{}` placeholder (ADR content lost) passes.

## Acceptance Criteria

- **AC1 (a):** `sub-iterate-runner.md` Step 4 executes **F3 = `write_decision_drop.py`
  keyed by run_id** and **F5c = `append_iterate_entry.py`**, both mandatory and as
  prominent as F5b, and self-runs `verify_iterate_finalization.py` (fail = fix before
  push). `result.json` records a `finalization` block (f3/f5c/verify outcomes).
- **AC2 (b):** `check_adr_in_iterate_history` accepts a run-id ADR identity **only**
  when a decision-drop **actually carries the ADR** (parses + non-empty `decision` +
  `run_id` match) **or** a `**Run-ID:**` line for the run is present in
  `decision_log.md`. Empty/placeholder drops no longer pass.
- **AC3 (c):** New diff-driven F11 gate `check_iterate_no_direct_decision_log` fails
  an iterate whose commit modified `.shipwright/agent_docs/decision_log.md` (recompute
  from `merge-base..HEAD`; ERROR; skip when git unavailable / no commit). Wired into
  `run_all_checks`. `reflection.md` no longer routes iterates to `write_decision_log.py`.
- **AC4 (secondary):** `append_iterate_entry.py` docstring + `F5c.md` make the 50-entry
  retention **consumer-explicit** (bounded window; full history = append-only
  `events.jsonl` + git history). A `kind:improvement` webui follow-up triage anchor is
  filed (Mission artifact should source full history from `events.jsonl`).
- **AC5:** `docs/hooks-and-pipeline.md` F11 validator registry lists the new check.

## Mini-Plan

1. Runner contract (`plugins/shipwright-iterate/agents/sub-iterate-runner.md`): rewrite
   Step 4 F3 → drop, insert F5c, insert F11 self-verify, extend `result.json` contract.
2. Verifier (`shared/scripts/tools/verifiers/iterate_checks.py`): tighten run-id
   drop-content check in `check_adr_in_iterate_history`; add
   `check_iterate_no_direct_decision_log`; wire into `run_all_checks`.
3. `references/reflection.md`: route "For decisions" through `write_decision_drop.py`.
4. Docs: `F5c.md` retention note (consumer-explicit); `append_iterate_entry.py`
   docstring; `docs/hooks-and-pipeline.md` validator registry; `F11.md` check list.
5. Tests: unit tests for (b) + (c); a real integration test proving F3→F5c→F11 compose
   (green happy path + red direct-decision_log path) — `category:integration`.
6. Triage anchor for the webui follow-up.

### Alternative considered (rejected)

Rip out the numbered-`ADR-NNN` acceptance branch in `check_adr_in_iterate_history`
entirely so run-id identity is the ONLY path. **Rejected:** numbered-ADR support is a
legitimate backward-compat path (post-aggregation / non-iterate phases) baked deeply
into `seed_project`, `test_verifiers_dual_mode`, and session-handoff rendering.
Removing it is high-churn and wrong — the actual violation (a *fresh* direct write) is
caught precisely by the diff-driven (c) gate, which does not disturb the legit path
(a pre-existing heading from a prior release is not in *this* commit's diff).

## Affected Boundaries

- **Producer/consumer — decision-drop JSON:** `write_decision_drop.py` (producer) ↔
  `check_adr_in_iterate_history` (consumer). The (b) change reads drop content.
- **Producer/consumer — iterate entry JSON:** `append_iterate_entry.py` (producer) ↔
  `find_entry_by_run_id` / verifier (consumer). Retention window is the boundary.
- **Producer/consumer — `decision_log.md`:** `write_decision_log.py` /
  `aggregate_decisions.py` (producers) ↔ new (c) diff gate (consumer of the commit
  diff). Guard must not false-positive on aggregation (release commit, not iterate).
- **Contract doc:** `sub-iterate-runner.md` (executed by the campaign subagent).

## Confidence Calibration
- **Boundaries touched:** decision-drop JSON (`write_decision_drop` producer ↔
  `check_adr_in_iterate_history` consumer); iterate-entry JSON (retention window);
  `decision_log.md` commit-diff (new gate); runner contract doc + result-JSON schema.
- **Empirical probes run:**
  - *Drop-content round-trip:* wrote a REAL drop via `write_decision_drop` and an
    empty `{}` placeholder; the verifier passes the real drop and fails the placeholder
    (test_adr_check_passes_with_pending_decision_drop / …empty_placeholder /
    …drop_decision_empty). Finding: "the drop exists" now means "the drop carries the ADR".
  - *Direct-decision_log commit probe:* built a real git repo, committed a
    `decision_log.md` write, and confirmed the gate FAILS (ERROR); a non-decision_log
    commit passes; a lookalike-named file does NOT trip it (4 git-backed tests). Finding:
    the diff-recompute catches the exact forbidden path regardless of self-report.
  - *cross_component diff-recompute:* confirmed the classifier's `cross_component` flag is
    PROSE-derived — the diff hits none of `CROSS_COMPONENT_FILE_PATTERNS`, so
    `check_integration_coverage` recomputes FALSE and does not require the integration
    behavior. Recorded in `degraded[]`; the integration test was written anyway.
  - *Producer→consumer composition:* the integration test drives the real tool chain end
    to end (F3→F5c→F11) — green on a proper run, red on the two forbidden shapes.
- **Test Completeness Ledger:** recorded in `shipwright_test_results.json.iterate_latest.test_completeness`
  — 13 behaviors, all `tested` with named evidence, 0 untested-testable, 1 `category:"integration"`.
- **Confidence-pattern check:**
  - *Asymptote (depth):* each probe that could fail was driven to a red AND a green
    (empty-drop red / real-drop green; direct-write red / clean-commit green); two
    consecutive no-finding probes on the numbered-ADR backward-compat branch (left intact)
    confirmed no regression there.
  - *Coverage (breadth):* the run-id branch (drop-carries / Run-ID-line / neither), the (c)
    gate (fail / pass / skip / path-scope / wiring), the runner contract (F3/F5c/gate name),
    and the schema (present / validates / optional) are each covered.
  - *Integration composition:* the three real producers/consumer compose in one scenario
    (category:integration), proving the pieces fit — not just each in isolation.

## Out of scope

- Raising / making the 50-entry retention configurable (YAGNI; `events.jsonl` is the
  full record). Confirmed intended, documented only.
- The webui-side Mission-artifact code change (separate repo → triage anchor).
- Removing numbered-ADR backward-compat (see rejected alternative).
