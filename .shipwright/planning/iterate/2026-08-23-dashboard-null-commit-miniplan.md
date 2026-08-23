# Mini-Plan: dashboard-null-commit

- **Run ID:** iterate-2026-08-23-dashboard-null-commit

## Files to create/modify
- `shared/scripts/tools/update_build_dashboard.py` (edit) — `commit` at
  both call sites in `_generate_from_events` (Recent Changes ~L385,
  Build History ~L487) guarded with an explicit `commit_raw is None`
  check (not `or` — see Confidence Calibration row 3 in the spec for why
  truthiness was rejected after the first attempt). Extended (post
  Internal Plan Review finding 2) to the sibling fields read from the
  same event dicts at both call sites: `ts`, `tests`, `review`,
  `affected_frs`, `description` — each guarded with `or` against its own
  empty-equivalent default (`{}`/`[]`/`""`/`"—"`), and the Build History
  synthetic-row `commit` default aligned from `"?"` to `None` (finding 7)
  so it flows through the one placeholder decision.
- `shared/scripts/tests/test_build_dashboard.py` (edit) — a
  `TestNullCommit` class: two regression tests for `commit: null` at
  each call site, one pinning `commit: ""` stays unchanged, and two more
  covering all-sibling-fields-null at each call site.

## Work breakdown
1. Write the two failing tests against the *unfixed* code (TDD red) —
   confirm both raise `TypeError` pre-fix (already reproduced manually
   in the F-debug Phase 2 probe; the persisted tests re-confirm it).
2. Apply the one-line fix at both call sites (`we.get("commit") or "—"`
   instead of `we.get("commit", "—")`) — `or` covers both the missing
   key and the explicit-`null` case in one expression, since both
   default to falsy (`None`/absent) the same way `dict.get`'s own
   default arg was intended to.
3. Re-run the two new tests — green.
4. Run the full `test_build_dashboard.py` suite — confirm no
   regression on the existing commit-handling assertions (missing,
   empty-string, and present commit values all still format correctly).

## Test strategy
- Unit tests only (`shared/scripts/tests/test_build_dashboard.py`,
  pytest). No E2E/UI surface — see spec `## Verification`.
- No new test *layer* needed; extends the existing suite for this exact
  module using its existing `tmp_project` fixture and event-writing
  convention (matches `TestFrColumnFallback` / `TestAliasIntent`
  patterns already in the file).

## Alternative approach
**Considered:** normalize `commit` to `""` at read time in
`shared/scripts/lib/config.py::read_events()` (or wherever events are
loaded), so every consumer of event dicts sees a guaranteed string and
never has to defend against `None` itself.
**Rejected because** (revised per Internal Plan Review finding 4 — the
original rationale below it replaced claimed two checked consumers
"deliberately distinguish" null from absent commit; both actually
already collapse the two via truthiness, e.g.
`event_context_index.py:124`'s `event.get("commit") or ... or ""`, so
that was not a real distinction to protect):
1. `read_events()` is the generic append-log reader shared by
   compliance, `fr_gates.py`, and `event_context_index.py`. Coercing a
   field's value there is a schema mutation in the wrong layer — it
   changes what every consumer sees, to fix one rendering call site.
2. Normalizing at the read boundary destroys the only forensic signal
   that some producer emitted an explicit `null` — exactly the signal
   that would matter later if someone wants to find and repair the
   producer that wrote it (this is how the leadwright case was traced
   in the first place).
