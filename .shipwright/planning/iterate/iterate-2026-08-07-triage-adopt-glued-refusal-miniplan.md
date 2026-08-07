# Mini-Plan — iterate-2026-08-07-triage-adopt-glued-refusal

## Goal

Make the triage drift adoption gate's refusal escapable and honest about
*why* it refused, for the one shape the card names: a glued drift line the
sibling PROTECTION parser (`append_ids_of`) already recovers but adoption
still cannot move. No change to what is adopted or mutated.

## Chosen approach — recognise, don't move; name the tool

Mirror P2.19b/AC14's precedent rather than re-deciding it: adoption stays
line-granular and refuses a glued line, but the refusal now says so
explicitly and points at the fix.

### Step 1 — `shared/scripts/lib/sweep_drift_events.py`

Add `_is_glued_producer_line(line: str) -> bool`, a pure leaf predicate next
to `_is_producer_event` and `append_ids_of`, plus a small `_looks_like_
producer_record(obj)` helper it shares with the `is_record` argument below:

- Returns `False` immediately if `line` is blank or already a clean
  `_is_producer_event` (nothing to explain).
- Otherwise calls `lib.jsonl_records.split_records(stripped,
  is_record=_looks_like_producer_record)` — **with** backward resync
  enabled, unlike `append_ids_of`'s own (unchanged) call. `lib.jsonl_records`
  names a damaged PREFIX — a truncated write appended onto — the *primary*
  corruption shape it exists to recover, not only the two-complete-records
  case AC14 already fixed; missing it here would silently reproduce the
  exact unescapable stall this run exists to remove, while a false positive
  only costs message precision (adoption refuses either way). Bounded by
  the same `_MAX_RESYNC_ATTEMPTS` every other resync caller uses.
- Returns `True` iff any recovered record is `event in {"append","status"}`
  with a `str` id.

### Step 2 — `shared/scripts/lib/sweep_drift.py`

In `plan_main_tracked_drift`'s validation loop, when a drift line fails
`_is_producer_event`:

1. Compute one shared `hint` string naming
   `uv run shared/scripts/tools/triage_repair.py --project-root <root>`
   (report mode; `--apply --writers-quiesced` is the operator's call, not
   implied automatically). **`<root>` is a literal placeholder, not `.`** —
   matching `sweep_quarantine.py` / `triage_validate.py`'s existing
   convention for the identical hint, because `main_root` here is never the
   caller's cwd (see `_head_lines`'s own docstring).
2. If `_is_glued_producer_line(line)` — refuse with the new
   `main_tracked_glued_line: ...; {hint}` reason.
3. Otherwise — refuse with the existing `main_tracked_unparseable: ...`
   reason, now also carrying `{hint}`.

No change to `DriftPlan`'s shape, to `commit_main_tracked_drift`, or to what
gets moved: both branches still return `status="refused"`.

### Step 3 — tests

New `shared/tests/test_sweep_drift_glued_refusal.py` (split out so both this
and `test_sweep_drift_guards.py` stay under the 300-LOC guideline, matching
the `test_triage_id_identity.py` precedent):

- `test_a_glued_drift_line_refuses_but_names_the_repair_tool` — a glued
  drift line (two complete records) refuses, reason starts
  `main_tracked_glued_line`, names `triage_repair.py --project-root <root>`,
  tracked log byte-identical to before, outbox never created.
- `test_a_truncated_predecessor_glued_to_a_full_append_is_also_recognised` —
  the backward-resync widening actually recovers the truncated-prefix shape.
- `test_is_glued_producer_line_distinguishes_glue_from_corruption_and_from_clean`
  — direct unit test of the new predicate: fires on two-appends-glued and on
  append-glued-to-status, not on a clean event, not on `"{ BROKEN"` (nothing
  valid behind it either), not on `""`.
- `test_is_glued_producer_line_agrees_with_the_protection_universe` — AC5 as
  an actual composition: whatever `append_ids_of` recovers,
  `_is_glued_producer_line` also recognises.

In `test_sweep_drift_guards.py`: extend
`test_malformed_drift_is_never_copied_into_the_outbox` with an assertion
that its reason now also names `triage_repair.py --project-root <root>`.

Full existing suite (`test_sweep_drift.py`,
`test_sweep_outbox_dispositions_integration.py`) re-run unmodified otherwise,
to confirm the message-only change does not alter adoption or delivery
behavior.

## Files

| File | Change |
|---|---|
| `shared/scripts/lib/sweep_drift_events.py` | new `_is_glued_producer_line` + `_looks_like_producer_record` |
| `shared/scripts/lib/sweep_drift.py` | compose the two refusal reasons; import the predicate; docstring bullet updated |
| `shared/tests/test_sweep_drift_guards.py` | one extended assertion |
| `shared/tests/test_sweep_drift_glued_refusal.py` | new — the four glued-line behaviors |

`shared/scripts/lib/jsonl_records.py`, `sweep_drift_restore.py`, and
`churn_merge.py` are **not** touched — `split_records` (called with an
existing, documented parameter) and `_is_producer_event` are read, not
changed, and no other caller's contract moves. That also keeps
`cross_component` off this diff (confirmed by `classify_complexity`, which
found no `cross_split`).

## Risks

- **R1 — widening what adoption is willing to move.** Rejected explicitly
  (see spec, "Alternative considered and rejected"): the predicate only
  changes the refusal *message*, never the `status` or what gets mutated.
- **R2 — the new predicate disagrees with `append_ids_of` on some input**,
  making the "glued" label wrong on a line `append_ids_of` would not
  recognise either. The two do NOT use identical parsing power any more
  (this predicate additionally does backward resync, `append_ids_of` does
  not) or an identical event set (`append`-only vs. `append`-or-`status`),
  so agreement is asserted directionally, not as parity — pinned by a
  dedicated composition test in Step 3, not merely a "same call" argument.
- **R3 — `sweep_drift_restore.py`'s own `_is_producer_event` call (guarding
  a "late append" salvage window) needs the same treatment.** Out of scope:
  that call site decides whether a *salvaged* append is safe to re-adopt
  post-restore, a narrower and already-conservative check with no reported
  stall; widening it is a separate card if evidence for one shows up.
- **R4 (found by internal Opus plan review, fixed before external review)
  — the hint's `--project-root .` targeted the wrong tree.** `main_root` is
  never the caller's cwd. Fixed to the `<root>` placeholder convention
  already used by the two sibling call sites.

## Alternative (rejected)

Recover and re-serialize a glued line's records into the outbox, mirroring
`append_ids_of` fully rather than just its parsing technique. Rejected in the
spec: adoption has never re-serialized bytes, and doing so here would risk
the exact verbatim-comparison regressions the existing guard-test suite
exists to catch, for a defect whose severity is a stall, not data loss.
