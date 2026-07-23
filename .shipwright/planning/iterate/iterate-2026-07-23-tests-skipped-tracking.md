# Iterate: First-class `tests.skipped` tracking + failure-keyed D4

- **Run ID:** `iterate-2026-07-23-tests-skipped-tracking`
- **Intent:** CHANGE (framework tooling — event schema + compliance readers)
- **Complexity:** medium (classifier: `estimate=medium`, `prior_source=keyword`, no risk flags)
- **Spec Impact:** MODIFY — `affected_frs = FR-01.10` (`/shipwright-compliance`:
  *"produce audit-ready evidence … and run an on-demand cross-check that reports
  where that evidence disagrees with reality"*). This iterate improves the
  accuracy of that evidence (test-evidence report) and that cross-check (detective
  audit D4). Not FR-01.15 — the change is additive to the event log + markdown
  reports, and touches none of the versioned cross-repo WebUI payloads.
- **Precedent:** #427 (D1/D3 detective-accuracy fix) → `affected_frs=[FR-01.10,…]`,
  `spec_impact=modify`, `intent=change`. This iterate mirrors it (subset scope).

## Problem

`record_event.py` builds a `work_completed` `tests` block from
`--tests-passed / --tests-total / --tests-new / --tests-modified / --e2e-run`
only — there is **no `--tests-skipped`**, and nothing under `shared/scripts` or
the compliance plugin reads `tests.skipped`. Consequences:

1. A host-gated skipped test (e.g. a symlink guard that degrades to `it.skip` on
   Windows without Developer Mode) must be folded into the collected total →
   `passed < total` on a **green** run.
2. The detective audit's **D4** ("latest covering event has `tests.passed <
   tests.total`") then reports every FR whose latest covering event looks like it
   landed in a failing build — a false positive. **Verified live:** on this repo
   D4 flags `FR-01.07 (4955/4967)` (12 host-gated skips, long green). D4 is in
   fact **disabled** for this monorepo via `audit_config.disabled_checks` with the
   reason *"D4 can only ever surface STALE historical snapshots"* — a workaround
   for exactly this bug.
3. Recording *executed* totals instead (so `passed == total`) is correct for D4
   but loses information the other way: `test_evidence.py` renders the shortfall
   as `PASS (N skipped)` from the `total - passed` gap, so once `passed == total`
   that disclosure disappears — while the skip count would land in a field no
   consumer reads.

Secondary sharp edge: `events_amend.apply_amendments` merges **shallowly**, so an
`event_amended` carrying `fields.tests` REPLACES the whole `tests` block and
silently drops sibling keys such as `e2e_run` (which `test_evidence` uses to
classify a work event's layer).

## Design decisions

**Arithmetic convention (the crux).** `total` includes skips (pytest-native):
`total = passed + failed + skipped`. Therefore `failed = total - passed - skipped`.
- **Explicit skip count recorded** → `failed = max(0, total - passed - skipped)`
  is exact. Green-with-skips ⇒ `failed = 0`.
- **No `skipped` field (all legacy events, and this is the only kind on the wire
  today)** → a `work_completed` event is green-at-merge by the Iron Law, so a
  `passed < total` gap is *skips, not failures* → `failed = 0` (charitable). This
  matches the long-standing `test_evidence` renderer interpretation and is what
  makes the fix eliminate the **live** false positives (all 43 gap-events have no
  `skipped` field) rather than only future ones.

This makes D4 a precise, low-noise check: it flags an FR only when its latest
covering event records an **explicit** skip count that still leaves a residual
(`total - passed - skipped > 0`) — the only in-band evidence of an Iron-Law
violation. Every legacy gap is treated as skips.

**Re-enable D4 on this monorepo.** The disable rationale ("D4 can only surface
stale snapshots") is obsoleted by this fix. `disabled_checks` only suppresses
*failing* findings, so a passing D4 renders identically whether listed or not;
removing `"D4"` restores it as a live cross-check that would surface a *future*
genuine explicit-skip residual instead of hiding it. Contingent on the full
audit staying green after the fix (verified at F0).

**Deep-merge is opt-in.** `apply_amendments(events, deep=False)` — default is
byte-identical shallow merge (all existing callers unchanged, parity tests
unaffected). `deep=True` recursively merges nested dicts so a `fields.tests`
correction preserves untouched siblings. Plus a documented warning at the write
surface (`record_event` `--fields` help + `event_amended` branch).

## Acceptance Criteria

- **AC1** `record_event.py` accepts `--tests-skipped N`; a `work_completed` event
  carries `tests.skipped = N`. Cross-field guard: `passed + skipped > total`
  raises `ValueError` at the CLI boundary (mirrors the `test_run` H3/M2 guards).
- **AC2** `WorkEvent.from_dict` reads `tests.skipped` (`int | None`; `None` when
  absent — the present/absent distinction is load-bearing).
- **AC3** `test_evidence` Test Progression Result: explicit skip count is rendered
  as `PASS (N skipped)` **even when `passed == total`**; explicit-skip residual
  renders `FAIL (k failed[, N skipped])`; legacy (no `skipped`) rendering is
  unchanged.
- **AC4** `update_build_dashboard` renders the skip count in the Recent Changes
  and flat Test Status views when `tests.skipped` is present.
- **AC5** D4 keys on failures (`total - passed - skipped`, charitable when
  `skipped` absent). Legacy gap ⇒ pass; explicit green-with-skips ⇒ pass;
  explicit residual ⇒ fail.
- **AC6** `apply_amendments(..., deep=True)` deep-merges nested dicts; default
  shallow behaviour unchanged; write surface documents the sharp edge.
- **AC7** D4 removed from `audit_config.disabled_checks`; full detective audit
  green on this repo.

## Affected Boundaries

- **Event log wire format** (`shipwright_events.jsonl`, `work_completed.tests`):
  additive optional `skipped` key. `SCHEMA_VERSION` stays 1 (consistent with the
  prior additive keys `new`/`modified`/`e2e_run`). Round-trip test: write via
  `record_event` → read back via `read_events` + `WorkEvent.from_dict`.
- **`audit_config.json`** (`*_config.json` → io-boundary): one-line list edit.

## Confidence Calibration

- **Boundaries touched:** event-log `tests` block (`shipwright_events.jsonl`);
  `audit_config.json`.
- **Empirical probes run:**
  - Live D4 pre-change: `_check_d4` → `fail`, flags `FR-01.07 (4955/4967)`
    (host-gated skips). Post-change target: `pass`.
  - Event-log census: 355 `work_completed` events, 43 with a `passed<total` gap,
    **all** `skipped=None` → all must render charitably (no regression).
- **Test Completeness Ledger:** every AC → a `tested` row (below); 0
  untested-testable.
- **Confidence-pattern check:** depth — round-trip write/read of the new field +
  the exact D4/renderer arithmetic across legacy / explicit-green / explicit-
  residual. Breadth — writer (`record_event`), model (`WorkEvent`), two renderers
  (`test_evidence`, `update_build_dashboard`), detective (`group_d` D4), amendment
  SSOT (`events_amend`), config (`audit_config`). No `cross_component` machinery
  touched (verified against `CROSS_COMPONENT_FILE_PATTERNS`), so no integration-
  coverage gate; the round-trip test covers the one real boundary.

### Test Completeness Ledger

New tests live in **sibling modules** so the grandfathered `test_test_evidence.py`
/ `test_record_event.py` / `test_data_collector.py` / `test_audit_groups_a_d.py`
are not ratcheted (extraction + net-zero reverts).

| Behavior | Disposition | Evidence |
|---|---|---|
| AC1 flag → `tests.skipped` written + CLI round-trip | tested | `test_record_event_skipped.py::TestTestsSkippedFlag` |
| AC1 `passed+skipped>total` / negative / non-int rejected | tested | `test_tests_block.py::TestValidateTestsBlock` + `TestTestsSkippedFlag` |
| AC2 `WorkEvent.from_dict` skipped present/absent/zero | tested | `test_skipped_tracking.py::TestWorkEventSkipped` |
| AC3 explicit skipped rendered at `passed==total`; residual→FAIL (incl. baseline) | tested | `test_skipped_tracking.py::TestExplicitSkipRender` + `test_tests_block.py::TestProgressionResult` |
| AC3 legacy rendering unchanged | tested | `test_test_evidence.py::TestSkipAwareResult` (4 cases, skipped absent) |
| AC4 dashboard renders skipped (iterate + build sites) | tested | `test_update_build_dashboard_skipped.py` |
| AC5 D4 charitable / green-with-skips / residual / non-int | tested | `test_skipped_tracking.py::TestD4KeysOnFailures` + `test_audit_groups_a_d.py::test_d4_*` |
| AC6 deep-merge preserves siblings; default unchanged; write-surface warning | tested | `test_events_amend_deep_merge.py` |
| AC7 audit green with D4 re-enabled | tested | full audit probe (D4 pass; only pre-existing H1 remains) |
| Reader-consistency: 3 readers share `isinstance(int)` predicate (no non-int crash/divergence) | tested | `test_tests_block.py` + `test_skipped_tracking.py::*non_int*` |
| `event_amended` `fields.tests` validated (Finding 2); structured error (Finding 3) | tested | `test_record_event_skipped.py::TestAmendmentTestsBlockValidation` + `test_main_rejects_corrupt_block_with_structured_error` |

## Out of scope

- Threading `--tests-skipped` through the smoke/E2E `test_run` layers (they
  already carry explicit per-layer `failed`; the request is scoped to
  `work_completed`).
- Flipping any existing `apply_amendments` caller to `deep=True` (cross-impl
  parity work; the option + write-surface warning is the requested deliverable).
