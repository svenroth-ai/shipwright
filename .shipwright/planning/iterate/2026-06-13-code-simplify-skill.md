# Iterate Spec: code-simplify-skill (OS1 / P3.2)

- **Run ID:** iterate-2026-06-13-code-simplify-skill
- **Type:** feature (sub-mode: simplify) — framework capability
- **Complexity:** medium (locked; prior_source: keyword)
- **Status:** draft
- **Spec source:** `Spec/external-frameworks-integration.md` §2 (OS1), §6 (P3.2 bundle), triage `trg-6289f9a6`
- **Variant:** A+ (sub-skill `F-simplify.md` + non-dodgeable `behavior_snapshot.py`), per user decision 2026-06-13

## Goal

Add a standalone, behavior-preserving **Simplify** workflow to `/shipwright-iterate`:
`Behavior-Snapshot → Simplify (Five Principles + Chesterton-Fence) → Behavior-Verify`,
rejecting on any behavior diff or removed test coverage. Make the snapshot/verify
gate **mechanical** (a recomputed verifier, like `check_integration_coverage`), not a
prose honor-system.

## Acceptance Criteria

- [ ] AC1 — `classify_intent` recognises simplify vocabulary (`simplify`, `clean up`,
  `cleanup`, `declutter`, `streamline`, `tidy`, `untangle`) and returns an **additive**
  `mode: "simplify"` with `type: "change"` (the F5c `_VALID_TYPES` enum is untouched).
  `refactor`/`restructure`/`redesign` stay plain CHANGE (mode `None`) — the existing
  `test_change_keywords` stays green. A `fix`/bug keyword present → type `bug`, no simplify mode.
- [ ] AC2 — `references/F-simplify.md` exists (≤400 LOC), carries the **Five Osmani
  Principles** (Preserve Behavior, Follow Conventions, Clarity over Cleverness, Maintain
  Balance, Scope to What Changed), the **Chesterton-Fence** pre-flight ("before deleting/
  changing, state WHY this exists"), the "**fewer lines is not the goal**" rule, and an
  MIT attribution footer to addyosmani/agent-skills (© Addy Osmani).
- [ ] AC3 — The iterate Kern (`SKILL.md`) routes simplify intent through `F-simplify.md`
  (a `## Path D: SIMPLIFY` section + Phase Index link), states the behavior-preserving
  reviewer gate (reject on behavior diff / removed coverage), and forces `spec_impact = none`.
- [ ] AC4 — `behavior_snapshot.py snapshot` runs the suite and stores a green-state record
  (collected test-node-id set + pass/fail counts + exit_code + source LOC baseline) at the
  gitignored `.shipwright/runs/<run_id>/behavior_snapshot.json`.
- [ ] AC5 — `behavior_snapshot.py verify` re-runs and **STOPs** (non-zero exit) if any test
  flips green→red, a previously-collected test id disappeared (removed coverage), the test
  count dropped, OR source LOC dropped **while** test count dropped. A clean green→green
  with preserved coverage exits 0.
- [ ] AC6 — Round-trip (Boundary Probe): the green-state record survives
  write→file→read byte-faithfully and `compute_verdict` on the deserialized record
  reproduces the live verdict.
- [ ] AC7 — Probe-iterate: simplify a known-fixable function → green; simplify a function
  with a hidden side effect (a test flips, or a covering test is removed) → rejected.
- [ ] AC8 — `docs/guide.md` documents the simplify path (Intent Paths + the snapshot wrap;
  the existing NONE spec-impact note at :1601 already covers behavior-preserving refactors).

## Spec Impact

- **Classification:** NONE
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** This is shipwright-monorepo **framework tooling** — a new iterate
  sub-skill + helper script + classifier mode + guide docs. It maps to no user-application FR
  in `spec.md`; documented in `docs/guide.md`, not a product requirement. FR-gate (ADR-059)
  branch: `change_type = tooling` + none_reason.

## Out of Scope

- **Variant B** (`/shipwright-simplify` mini-plugin) — explicitly rejected this iterate;
  A+ leaves a thin-shell migration path open if discoverability is later wanted.
- Touching `README.md` / `CLAUDE.md` structure lists — Variant A+ doesn't add a plugin.
- Stealing the `refactor` keyword for simplify (would break `test_change_keywords`).
- Auto-invoking simplify from the `suggest_iterate` hook — routing lives in SKILL.md, not the hook.
- Per-line pytest output parsing — the gate compares collected node-id SETS + counts + exit
  code, which is robust and dependency-free.

## Design Notes

No UI. `behavior_snapshot.py` is split pure/impure for testability:
- impure: `run_test_suite()`, `collect_test_ids()`, `measure_loc()` (subprocess/git)
- pure: `build_snapshot()`, `compute_verdict()` (the gate logic — unit-tested with synthetic inputs)
- I/O boundary: `write_snapshot()` / `read_snapshot()` (round-trip tested)

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `behavior_snapshot.py::write_snapshot` (snapshot subcommand) | `behavior_snapshot.py::read_snapshot` (verify subcommand) | JSON (`.shipwright/runs/<run_id>/behavior_snapshot.json`) |

`touches_io_boundary` fires from the diff (`json.dump`/`json.load` in `behavior_snapshot.py`)
→ Boundary Probe + producer→file→consumer round-trip test (AC6). Single consumer (verify),
so no duplicated-consumer drift test required.

## Confidence Calibration

- **Boundaries touched:** the behavior-snapshot JSON store (producer
  `behavior_snapshot.py snapshot`, consumer `behavior_snapshot.py verify`).
- **Empirical probes run:**
  - *Round-trip* (`test_snapshot_roundtrip_reproduces_verdict`): write→file→read is
    byte-faithful and the deserialized record reproduces the live verdict. No finding.
  - *Clean simplify* (integration `test_clean_simplify_stays_green`): LOC drop with
    intact green coverage → `verify` exit 0. No finding.
  - *Behavior drift in a covered path* (integration `test_hidden_side_effect_rejected`):
    **FINDING** — my first probe mutated an *un-covered* path (`is_even`→`True`) and
    `verify` PASSED. That exposed the honest limit: the gate is only as strong as
    coverage. Fixed the probe to mutate a covered path (`add`→`*`) → rejected;
    documented the limit in F-simplify.md "Honest limit". (Asymptote: a finding here
    forced ≥1 more probe.)
  - *Removed coverage* (integration `test_removed_coverage_rejected`): deleting a test →
    `verify` rejects. No finding.
  - *Red baseline* (integration `test_snapshot_refuses_red_baseline`): `snapshot` exits 2
    on a non-green suite. No finding. → **asymptote reached** (last two probes clean).
- **Test Completeness Ledger:** see the F5 `iterate_latest.test_completeness` block; every
  AC behavior is `tested` (0 untested-testable). Mirrored into `shipwright_test_results.json`.
- **Confidence-pattern check:** depth — the one yes-then-finding (drift probe) was followed
  by two clean probes (asymptote). Breadth — 8/8 ACs covered by named tests; AC8 (guide doc)
  pinned by `test_guide_documents_simplify_submode`. No `cross_component` machinery touched,
  so no integration-composition behavior is required (the added CLI integration test is a
  bonus, not the `check_integration_coverage` gate).

## Verification (medium+)

- **Surface:** none
- **Runner command:** n/a (no startable web/cli/api surface — this is iterate-internal
  framework tooling; the behavior is proven by the unit/integration probe suite in
  `tests/test_behavior_snapshot.py` + `tests/test_f_simplify_routing.py`, run at F0).
- **Evidence path:** F0 full-suite output + F5 `shipwright_test_results.json`.
- **Justification (surface=none):** A code-simplify *skill* has no runnable HTTP/CLI surface
  of its own; its contract is the snapshot/verify gate, exercised mechanically by the probe
  tests (AC7) rather than by a booted stack.
