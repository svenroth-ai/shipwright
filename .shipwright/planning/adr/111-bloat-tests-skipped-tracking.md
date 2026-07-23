# ADR-111: Bloat exception — `record_event.py` + `update_build_dashboard.py` raised for first-class `tests.skipped`

- **Status:** accepted
- **Date:** 2026-07-23
- **Re-Review-Date:** 2026-10-23 _(retire when `record_event.py` splits its
  event-type branches per-concern and the dashboard renderer is decomposed —
  candidates for the B/C bloat-cleanup campaigns; the shared skip logic is
  already out (see Context), so what remains here is per-file wiring)._
- **Incident Reference:** iterate `iterate-2026-07-23-tests-skipped-tracking`
  (FR-01.10 — compliance evidence + cross-check accuracy). First crossing
  surfaced when a new `--tests-skipped` write path + its validation + the
  structured-error handling, and the dashboard's skip-disclosure wiring, pushed
  two already-oversize files past their grandfathered baselines.

## Context

The iterate adds first-class tracking of host-gated **skipped** tests to the
work_completed event so the detective audit (D4) and the test-evidence report
separate skips from genuine failures instead of reading the raw passed/total gap
(which had D4 disabled on this monorepo as stale-noise). The **skip-vs-fail
arithmetic was extracted to a new shared SSOT** `shared/scripts/tests_block.py`
(`validate_tests_block` / `skip_suffix` / `progression_result`), consumed by
record_event, the dashboard, and test-evidence — so `test_evidence.py` actually
**ratchets DOWN** (917 → 906) and only per-file *wiring* remains here.

Growth, per file:

- `record_event.py` 739 → 769 (+30): the `--tests-skipped` argparse arg
  (`_non_negative_int`) + its help; the `event_amended` `fields.tests`
  validation path (a corrupt block bypasses the flag guards otherwise) + the
  `--fields` help documenting the shallow-merge sharp edge; and a `main()`
  `try/except ValueError` that surfaces a corrupt block as the same structured
  `{"success": false}` + exit 1 the FR gates use (not a raw traceback). The
  shared `validate_tests_block` is imported, not re-implemented.
- `update_build_dashboard.py` 496 → 498 (+2): the `from tests_block import
  skip_suffix` import + the skip suffix in the Build-History cell. The logic
  itself lives in the SSOT; this is the irreducible call-site residual.

`group_d.py` (412 → 429) stays under **ADR-096**, which already blessed it at
465 — its current bump is within that envelope (baseline `current` updated, ADR
reference unchanged).

## Ousterhout Argument

`record_event.py` is a **deep module**: one narrow CLI (`main` / `build_event` /
`parse_args`) fronting a substantial, cohesive implementation — 14 event types,
the FR / spec-impact / existence gates, commit/phase dedup, a worktree-aware
atomic append, and amendment folding. `validate_tests_block` belongs at the
write chokepoint (it guards the invariant the readers trust); the flag,
amendment validation, and structured-error handling belong INSIDE the writer
they protect. Extracting them to dodge +30 would scatter the write-path's
fail-closed contract away from the CLI that owns it. `update_build_dashboard.py`
is a deep renderer (one `generate_dashboard` behind event- and config-mode
tables); its +2 is a call site, not logic — the logic was already extracted.

## YAGNI Check

Every added line backs behaviour shipped today: the flag records the skip count
that lets D4 stop false-flagging (re-enabled this iterate); the amendment
validation + structured error close the two reachable corrupt-write routes the
review found; the dashboard suffix discloses skips that a `passed == total`
recording would otherwise lose. No speculative scope — a general `--fields`
schema validator and a bool-skipped reader-exclusion were both consciously
scoped out (readers stay charitable; the write surface rejects).

## Chesterton-Fence Check

`record_event.py` is large because it centralises the single event-writer
contract with its "why" comments; the dashboard centralises one deterministic
render. The skip arithmetic that would have added the most weight was pulled OUT
to `tests_block.py` precisely to keep these files from carrying duplicated logic
— so this exception is the residue after the split, not an alternative to it.
