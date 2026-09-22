# Bloat exception — `shared/tests/test_review_attribution.py` raised above the 300-LOC limit (current: see `shipwright_bloat_baseline.json`)

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r3-review-diff-fix-test-review-attribution-bloat-exception.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r3-review-diff-fix`
  (campaign-dag-scheduler R3). Filed alongside its sibling
  `iterate-2026-09-22-r3-review-diff-fix-review-attribution-bloat-exception.md`
  in round 8, for the same reason: a fresh code-reviewer found this file
  (and the module it tests) crossed 300 LOC with no baseline entry while
  three smaller crossings in the same PR were already properly filed.

## Context

This is `review_attribution.py`'s own test suite: one file per reviewed
scenario in R3's spec's Test-strategy list — the red→green reproduction of
the old single-worktree diff misattribution, an untouched-branch pass, a
post-pin commit detected, a rebase detected, a review-skipped pin verified
at merge time, the shared-worktree pre-R5a fallback, `ship`'s clean
push-through, and `ship`'s STRICT-STOP on a bad parent — plus the
hardening probes added across review rounds (`_safe_segment` path-traversal
cases, `refs/heads/{branch}` tag-collision cases, `_single_parent`'s
merge-commit rejection, malformed-pin-file handling raising
`ReviewAttributionError` rather than leaking a raw `JSONDecodeError`/
`KeyError`).

## Ousterhout Argument

One deep test module for one deep implementation module — splitting the
tests would require either duplicating shared fixtures (a temp git repo,
a seeded `loop_state.json`) across files or extracting a shared conftest,
trading one large-but-organized file for two smaller ones plus a fixture
module, with no reduction in what a reader has to hold in mind to verify
`review_attribution.py`'s contract.

## YAGNI Check

Every test traces to either a named spec acceptance criterion or a
specific reviewer-found regression (see the sibling implementation ADR's
Context section for the list). No speculative coverage of unreachable
branches, no testing of hypothetical future modes.

## Chesterton's Fence

None removed — this is new test coverage for a new module, filed alongside
its implementation.

## Decision

`current` raised from unfiled to 470, `limit` 300, `state: "exception"`.

### Round 14 growth (470 -> 515)

Added four regression tests for `_resolve()`'s new
`ReviewAttributionError`-wrapping (sibling implementation ADR, round 14):
a missing state file, invalid JSON, a state file that parses but is not a
JSON object, and a unit entry that is not itself a dict — each previously
raised an uncaught Python exception instead of the documented BLOCK
message.

### Round 14b growth (515 -> 531)

A fresh code-reviewer pass on round 14's own diff found the `except
(OSError, json.JSONDecodeError)` tuple still missed `UnicodeError` (a
strict-mode `UnicodeDecodeError` from `durable_read_text` is a
`ValueError`, not an `OSError`) — the sibling reader of the same
`loop_state.json`, `lib/unit_lease.py`, already pairs `UnicodeError` with
the other two for this exact reason. Added one test writing invalid UTF-8
bytes into the state file, confirmed red against the pre-fix tuple, green
after widening it.

### Round 14c growth (531 -> 569)

Added two regression tests for `_check_pinned_worktree()` (sibling
implementation ADR, round 14c): one for `verify()`, one for `ship()`, each
pinning a unit, then changing the row's `worktree` field in
`loop_state.json` before calling `verify`/`ship` and asserting
`ReviewAttributionError` with `"worktree has moved"`. Confirmed red
against the pre-fix code (temporarily neutering the two call sites),
green after.

### Round 3 growth (569 -> 618)

Added three regression tests for round 3's genuine fixes (sibling
implementation ADR): `resolve_unit_identity`'s new type checks for a
non-string `worktree` and a non-string `branch` (unit-level), a
`pin()`-level integration test proving the whole call chain now fails
closed instead of raising an uncaught `TypeError` from a `subprocess.run`
call, and `_load_pin`'s widened except tuple (invalid-UTF-8
`review_pin.json`). Confirmed all four red-before/green-after by
temporarily reverting both fixes and re-running the affected tests.

## Consequences

`test_review_attribution.py` remains the authoritative regression suite
for pin/ship/verify; any future change to `review_attribution.py` runs
this file first.

## Rejected alternatives

- **Split by mode (`test_review_attribution_pin.py` /
  `_ship.py` / `_verify.py`)**: rejected — shared setup helpers (repo
  fixtures, `loop_state.json` seeding) would either duplicate across three
  files or need their own shared module, and several tests exercise
  cross-mode interaction (pin then ship then verify) that a per-mode split
  would awkwardly straddle.
- **Defer to a later Group H audit**: rejected for the same reason as the
  sibling implementation ADR — consistency with the three crossings this
  PR already filed properly.
