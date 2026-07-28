# Mini-Plan — IT-0b anchor + prose

Spec: `iterate-2026-07-28-it0-followup-anchor-prose.md`

## Chosen approach — stamp inline in the tool's `main()`, mirroring the sibling

1. `shared/scripts/tools/append_iterate_entry.py`
   - import `latest_event_dt` from `lib.events_log`
   - in `main()`: resolve `project_root` once, stamp
     `**({"event_at": event_dt.isoformat()} if event_dt is not None else {})`
     between `date` and `**extra`
   - docstring: the "reserved but deliberately not produced" paragraph becomes a
     statement of what it now produces
2. `shared/scripts/tools/finalize_bundle_lib.py` — add `event_at` to
   `_ITERATE_ENTRY_FORBIDDEN`. That set exists to mirror what the tool injects
   and rejects, and its comment says so; leaving it stale would let a bundle
   reach F5c with a forged anchor only to fail *after* F1/F3/F4 have written.
3. Delete the bound paragraph: `lib/phase_history.py`,
   `tools/verifiers/handoff_phase_canon.py`, `docs/hooks-and-pipeline.md`.
4. `shared/tests/_c3_fixtures.py` — `write_iterate_entry(…, anchored: bool = True)`
   stamps `event_at`, with `date` (the ledger's wall clock) strictly later,
   mirroring `history_entries`. `anchored=False` keeps the **pre-anchor** shape
   reachable, because every ledger entry written before this change has it and
   must keep taking the run-id branch.
5. `shared/tests/test_completion_writers.py` — flip the bound assertion, in
   place. **Amended during the build:** the new coverage does NOT go here. That
   file measured back at exactly 302 against a `current: 302` ceiling, so adding
   to it meant a second baseline bump *and* pushing a test file 22% past the
   constitution's 300-line rule. The five writer-driven tests — no-events
   companion, one-clock invariant, real F5c-before-F5b ordering, the now-caught
   true positive, and the CLI forge guard — plus the fixture-symmetry assertion
   live in a new `shared/tests/test_iterate_ledger_anchor.py` (222 lines, no
   entry needed), split along the seam the suite's own section comment draws:
   `append_phase_history` versus `append_iterate_entry`.
6. `shared/tests/test_c3_applicability.py` — a legacy, **unanchored** iterate
   ledger entry with a matching same-run marker still passes on the run id alone.
7. `shipwright_bloat_baseline.json` — raise `current` for the files that sit on
   their ceiling. Nothing else. **Measured:** exactly one entry moved,
   `append_iterate_entry.py` 425 → 436 (a single-line diff at line 686; the
   nearest other entry is hundreds of lines away, so no merge collision).
8. Prose: five one-line text edits (Part 2 of the spec).

**TDD order:** tests 5 first (red — the writer stamps nothing), then 1, then the
fixture 4, then the prose deletions 3, then the baseline 6 last (it must record
the *final* measured line counts).

## Alternative considered — split `append_iterate_entry.py` instead of bumping

Extract the one-shot legacy-migration state machine (`_migrate_legacy_array_to_dir`,
`_recover_migration`, `_write_quarantine_report`, ~110 lines) into
`shared/scripts/lib/iterate_entry_migration.py`, landing the tool at ~305 and
avoiding the bump.

**Rejected for this run.** It is not decision-free: the module boundary, whether
the recovery path stays CLI-reachable, and the import surface of
`shared/tests/test_append_iterate_entry.py` are all choices. That test file is
509 lines against a `current: 509` grandfathered entry — it sits on its own
ceiling too, so a split that moves imports around would need its own bump
regardless, and the "avoid a bump" argument collapses. Recorded as available to
the run that takes it deliberately.

## Round 1 external review — what it changed

| Finding | Verdict | Resolution |
|---|---|---|
| openai, medium: legacy unanchored ledgers must keep the run-id branch, and an always-anchored fixture would stop covering them | **valid** | steps 4 + 6 above: `anchored=False` mode plus a C3 test that drives it |
| openai, medium: `entry["event_at"] == marker["timestamp"]` is only sound if both serialize identically (`Z` vs `+00:00`) | **valid concern, already satisfied** | `canon_frontmatter.marker_timestamp` is `latest_event_dt(root).isoformat()` and this change is `latest_event_dt(root).isoformat()` — one function, one serialization. The reviewer's real ask (seed a realistic event ts) is met by driving `record_event.py` rather than hand-writing a log |
| openai, low: the symmetry test's key set is environment-dependent unless an event exists first | **valid** | step 5: record an event before invoking the real writer |
| gemini, high: `--entry-json` could forge `event_at` because `**extra` unpacks last | **refuted on the code** — `main()` already rejects `{"run_id","date","event_at"} & set(extra)` and returns 1 *before* the dict is built. **But the guard has no test**: `test_append_iterate_entry.py` exercises only the Python API, never `main()`. The claimed pre-existing test did not exist, so the guard is now covered (step 5) |

**Second alternative, also rejected:** put the stamp in
`shared/scripts/lib/iterate_entry.py` (which already owns `now_utc_iso` and the
validator). That file is 341 lines against `current: 341` — on its ceiling as
well, so it trades one bump for another while breaking the deliberate symmetry
with `append_phase_history.py`, where a future reader compares the two producers
side by side.

## External code review (round 1) — what it changed

Verdict `revise`, openai; gemini degraded (reply truncated by the provider).
All four findings were acted on; none were argued away.

| Finding | Resolution |
|---|---|
| medium, spec: `hooks-and-pipeline.md` **reworded** the Known-bounds item instead of removing it, keeping a closed bound documented as live | Right, and it exposed a duplicate: what survived the rewrite was already numbered item 3. The two are folded into one, the list is now **Two**, and the retired iterate bound is recorded *below* the list as history |
| medium, test: `written <= fixture` is one-sided; a fixture that invents a key still passes | Changed to **equality**, with the docstring stating why `_f5c` must keep passing the minimal `--entry-json` for that to be sound. Verified by mutation — an invented fixture key fails the test — not by reading the assertion |
| low, test: the no-events test claimed empty and unparseable logs but only drove an absent one | Parametrized over four log shapes (absent · empty · blank-lines · unparseable). Only the absent case short-circuits on `exists()`; the others take different branches inside the helper |
| low, edge-case: `at.replace("+00:00", "") + ".900000+00:00"` emits garbage for a `Z` suffix, a non-UTC offset or an existing fraction | Parsed with `fromisoformat` and re-serialised via `timedelta`. `history_entries` carries the same fragility and is **left alone** — it is a passing helper on many suites, and changing its output format is unrelated churn (G4) |
