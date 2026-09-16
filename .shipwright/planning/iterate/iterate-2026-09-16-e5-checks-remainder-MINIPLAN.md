# Mini-Plan: e5-checks-remainder

## Problem

`sub-iterates/e5-checks-remainder.md`'s one acceptance criterion: "No
prompt-only (mechanisable) line is left unaddressed anywhere in the ledger"
(`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`).
The spec names "FR-01.14 plus the preamble and end-check strays" but is
deliberately thin — e0's own ledger accounting could have already moved some
of the named lines into another bucket, so investigation had to precede any
build.

## Investigation (done before writing code)

Ran `uv run shared/scripts/tools/measure_ac_evidence_ledger.py`: 4
`prompt-only (mechanisable)` occurrences document-wide. Grepped every one:

1. The legend's own definition line (§ "What this is for" table) — not a
   criterion row.
2. The historical 2026-07-26 end-check distribution table — superseded prose
   kept for the paragraph's own history, not a live criterion row.
3. FR-01.06 #6b — already explicitly downgraded-with-reason and filed as
   `trg-2f7a840a` by `e3-checks-test-security` (a producer-side ADR-045
   relocation this checks-only campaign does not own). Already addressed;
   verified, not re-litigated.
4. FR-01.14 #1's mechanisable half — "the producer contract has no gate, and
   a new producer calling the plain append writes duplicates freely." The
   only genuine, un-addressed row.

So the unit is one real closure (FR-01.14 #1), not a rebuild of FR-01.14
wholesale.

## Empirical check before building

AST-scanned every `.py` under `shared/scripts` and `plugins` for a call to
the plain, non-deduplicating `triage.append_triage_item` (as opposed to
`append_triage_item_idempotent`). Exactly one production call site:
`shared/scripts/tools/triage_add.py`, the manual operator CLI. Every
automated/background producer already calls the idempotent form. The
discipline already holds in the live tree; nothing enforces that it keeps
holding for a future producer.

## Decision

Build the row's own named oracle — "a meta-test over the call sites" — as an
allowlist-registry test, mirroring the exact shape
`shared/tests/test_triage_precondition_registry.py` already established for
the sibling `mark_status` flip-site concern (forward pin + reverse
drift-guard + a proof the guard can actually fail). New file:
`shared/tests/test_triage_append_producer_registry.py`.

- `ALLOWED_PLAIN_APPEND_CALLERS` — one entry, `triage_add.py`, with a test
  pinning that it still describes itself as manual (so the exception's own
  rationale can't silently widen).
- `find_plain_append_callers` — AST-based (not text/regex) scan, so a
  reformatted multi-line call is still found and the idempotent sibling call
  is never mistaken for the plain one.
- Reverse-drift test: any unregistered caller fails by name.
- Two false-positive guards: the idempotent call, and the module-qualified
  `triage.append_triage_item(...)` form.
- A guard-can-fail proof (same discipline as
  `test_adr_index_producers.py::test_drift_guard_actually_fails_on_a_stale_index`).

Flip FR-01.14 #1's status to `enforced, tested` in the ledger, citing the new
test file. Re-run the measurement script and update the campaign's
re-measurement paragraph (3 mechanisable rows remain: the two non-row
occurrences above; FR-01.06 #6b stays as its own already-addressed,
deliberately-deferred row).

## Out of scope

FR-01.06 #6b's actual mechanisation (wiring `journey_coverage.py` into
`.06`'s own gate) — that is `trg-2f7a840a`'s own future work, a producer-side
design change (ADR-045 relocation) outside this checks-only sub-iterate.

## Tests

`shared/tests/test_triage_append_producer_registry.py` (5 cases). Full
`shared/tests` suite re-run green (10958 passed, 43 skipped) to confirm no
regression.
