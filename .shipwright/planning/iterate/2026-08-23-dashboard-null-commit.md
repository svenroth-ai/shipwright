# Iterate Spec: dashboard-null-commit

- **Run ID:** iterate-2026-08-23-dashboard-null-commit
- **Type:** bug
- **Complexity:** medium
- **Status:** implemented

## Goal
`update_build_dashboard.py`'s `_generate_from_events` crashes with
`TypeError: 'NoneType' object is not subscriptable` whenever a
`work_completed` event carries an explicit `"commit": null`, because
`we.get("commit", "—")[:7]` only substitutes the default on a *missing*
key, not on a present-but-`null` value. `finalize_iterate.py`'s F5b
`_update_dashboard` step calls `generate_dashboard` best-effort and only
logs the exception, so the failure is silent — but once one null-commit
event exists in a repo's `shipwright_events.jsonl`, **every** later run
re-raises on that same historical event and `build_dashboard.md` never
updates again. Observed in the adopted project leadwright
(`shipwright_events.jsonl` line 9, evt-e66849cc, 2026-08-17).

## Acceptance Criteria
- [x] `we.get("commit", "—")[:7]` (both call sites, `_generate_from_events`)
  treats an explicit JSON `null` the same as a missing key — renders
  the same placeholder instead of raising — while an explicit empty
  string (`""`, the normal F5b pre-commit state) keeps rendering the
  empty cell it always has, unchanged.
- [x] A regression test constructs a `work_completed` event with
  `"commit": null` and asserts `generate_dashboard` returns cleanly with
  the placeholder in the rendered row, at both call sites (Recent
  Changes and Build History).
- [x] A regression test pins that `"commit": ""` is NOT coerced to the
  null placeholder by the fix.
- [x] The same null-tolerance is applied to every sibling field
  `_generate_from_events` reads from a `work_completed` event dict
  (`ts`, `tests`, `review`, `affected_frs`, `description`) — added per
  Internal Plan Review finding 2 — each with a regression test proving
  a `null` value renders its placeholder instead of raising, at both
  call sites.
- [x] A historical null-commit event already present in
  `shipwright_events.jsonl` no longer permanently blocks the dashboard
  from regenerating on subsequent runs.

## Spec Impact
Internal tooling defect in a generated-artifact renderer; no
user-observable capability is added, changed, or removed — the fix
restores the tool's own implicit contract (never raise on a well-formed
event).
- **Classification:** none
- **NONE justification:** bug fix restores the dashboard generator's
  existing intended behavior (render every well-formed event without
  raising); no FR describes commit-cell formatting.

## Out of Scope
- `shared/scripts/tools/generate_session_handoff.py:449,469` (a
  different file, different function, different consumer of the event
  log) — left unchanged. Revised reasoning after Internal Plan Review
  (see below): the original "no producer writes null for this field
  today" argument is not a safety argument for a function that reads a
  third-party/adopted repo's event log — that argument is exactly what
  failed for `commit` (the null came from the adopted project
  leadwright, outside this monorepo's producer census). The real reason
  this file is out of scope is narrower: it is a *different* function
  outside the one function proven to consume foreign event data in this
  bug report, so widening the fix there is a separate, unvalidated
  hardening pass rather than a closure of the class this bug
  demonstrated.
- **Sibling fields WITHIN `update_build_dashboard.py::_generate_from_events`
  are IN scope, not out** (revised after Internal Plan Review — see
  below): `ts`, `tests`, `review`, `affected_frs`, `description` are all
  read from the same foreign `work_completed` event dicts as `commit`,
  in the same function, across every call site (Recent Changes, Test
  Status, Pipeline, Build History). Each had the identical landmine
  (`.get(key, default)` only substitutes on a *missing* key) and each is
  now guarded (`or {}` / `or []` / `or ""` / `or "—"` as the field's own
  empty-equivalent default, or the same explicit `commit_raw is None`
  guard for `commit` itself, which is the one field where an empty
  string is real, common, and must render differently from null — see
  Confidence Calibration).
- Auditing/repairing other producers that might emit `commit: null`
  (e.g. adopted-repo event backfills) — out of scope; this fix makes the
  *consumer* tolerant regardless of which producer wrote the null.
- **Nested-null tolerance** (a field present as a non-null container
  whose own sub-field is null, e.g. `"tests": {"total": null}`, or a
  wrong-typed top-level value, e.g. `"commit": 123`) is not covered —
  disclosed after Stage-2 code review confirmed the top-level-only scope
  boundary is defensible (matches what was actually observed in
  production) but flagged it was undisclosed. Three concrete sites
  remain reachable with the same silent-permanent-stall failure mode;
  named in the bloat-exception ADR's Known Limitations.
- The architectural gap that let this bug become *permanent* — F5b's
  `_update_dashboard` swallows any exception to a log line with no
  gated signal, and the F11 verifier `check_build_dashboard_has_run_id`
  (C2) SKIPs whenever an F5c per-run entry exists (the normal case), so
  a crashed F5b step is caught by nothing — is a real, valid finding
  (Internal Plan Review, severity: medium) but is **disclosed, not
  fixed, in this iterate**. Making it visible means changing
  `finalize_iterate.py`'s step-result contract and `iterate_checks.py`'s
  C2 SKIP condition, which is `cross_component`-flagged pipeline
  validator machinery (SKILL.md risk taxonomy) — a materially larger,
  separately-scoped change than a renderer null-guard. See `## Internal
  Plan Review` below and the ADR's Known Limitations.

## Design Notes
n/a — no UI/design surface; pure Python data-rendering fix.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| any `work_completed` event writer (`finalize_iterate.py` F5b, `record_event.py`, adopted-repo backfills) | `shared/scripts/tools/update_build_dashboard.py::_generate_from_events` | JSON (`shipwright_events.jsonl`, one event per line) |

## Confidence Calibration
- **Boundaries touched:** the `work_completed` event → dashboard-renderer
  boundary above (`touches_io_boundary`).
- **Empirical probes run:** reproduced the crash pre-fix with a
  synthetic `work_completed` event carrying `"commit": null` fed through
  `generate_dashboard()` — raised `TypeError: 'NoneType' object is not
  subscriptable`, confirming the root cause named above. Re-ran the same
  probe post-fix — returns cleanly.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `commit: null` in Recent Changes event row renders the placeholder instead of raising | tested | `TestNullCommit::test_recent_changes_null_commit_does_not_raise` PASSED |
  | 2 | `commit: null` in a Build History event row renders the placeholder instead of raising | tested | `TestNullCommit::test_build_history_null_commit_does_not_raise` PASSED |
  | 3 | `commit: ""` (the normal F5b pre-commit state, 471/543 real events in this repo's own log) keeps rendering the empty cell, NOT the null placeholder | tested | `TestNullCommit::test_recent_changes_empty_commit_still_renders_empty` PASSED — added specifically because the first fix attempt (`or "—"`) failed this exact behavior; the external reviewer (deepseek) and the empirical event-log count both caught it before the fix shipped |
  | 4 | `ts`/`tests`/`review`/`affected_frs`/`description` explicit-null in a Recent Changes event row render their placeholders instead of raising | tested | `TestNullCommit::test_sibling_null_fields_do_not_raise` PASSED |
  | 5 | same five fields explicit-null in a Build History event row render their placeholders instead of raising | tested | `TestNullCommit::test_build_history_sibling_null_fields_do_not_raise` PASSED |
  | 6 | Test Status section: `_test_status_from_iterate`'s flat-fallback branch (`tests: null`, no `shipwright_test_results.json`) renders cleanly instead of raising `AttributeError` | tested | `TestNullCommit::test_test_status_flat_fallback_null_tests_does_not_raise` PASSED — this is a SEPARATE function from `_generate_from_events`'s inline field reads; missed by the sibling-field pass (rows 4-5) and caught by the Stage-1 spec-reviewer HARD-GATE, which rejected the first version of this diff for it |
  | 7 | a normal (missing/present-string) commit value elsewhere is unaffected by the fix | tested | `covered-by-existing-test` (existing `TestFrColumnFallback`/`TestAliasIntent`/`TestRunIdEmbed` classes exercise missing + present commit values against the same code paths; full 48-test file green post-fix) |
  | 8 | `shared/tests` root (a separate pytest process — see repo's one-root rule) that also renders this function does not regress | tested | `shared/tests/test_build_dashboard_md_escaping.py` (3 tests) + `shared/tests/test_render_determinism.py` (6 tests, including the `build_dashboard` render target) — 9/9 PASSED |
  | 9 | `split: null` in a Build History event does not raise AND does not double-render the section under two headings (Stage-2 code review: a real correctness bug beyond the crash class) | tested | `TestNullCommit::test_build_history_null_split_does_not_duplicate_section` PASSED |

- **Confidence-pattern check:** asymptote — YES, this is exactly the
  pattern the calibration protocol exists to catch: the first
  implementation (`we.get("commit") or "—"`) looked obviously correct
  and was NOT — it silently reformats 471/543 real event rows from an
  empty cell to `—`. Caught by (a) the external plan review (deepseek,
  severity medium) and (b) an empirical count against this repo's own
  `shipwright_events.jsonl`, both run before F0, which is what this
  gate is for. A second probe (Internal Plan Review, opus-plan-reviewer)
  then caught the same class of bug still latent in five sibling fields
  of the same function — the ledger rows above are the additional
  probes that check required after that finding, not a restatement of
  row 1-3. Coverage — every ledger row is `tested`, 0 untested-testable;
  both original call sites plus all five sibling fields at both call
  sites are covered by dedicated regression tests.

## Verification (medium+)
- **Surface:** none
- **Justification:** pure Python library function with no startable
  dev server/CLI entry surface of its own; verified via the unit test
  suite (`shared/scripts/tests/test_build_dashboard.py`), which is the
  existing test harness for this exact module.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Root-cause diagnosis and two-site fix correct. Flagged
  that the first fix attempt (`or "—"`) silently changed rendering for
  the common empty-string-commit case, that the Out-of-Scope rationale
  for sibling null-tolerant fields used a producer census the bug itself
  disproved, and that the underlying silent-failure architecture
  (F5b swallows exceptions; C2 verifier SKIPs when an F5c entry exists)
  leaves the next unmodelled null just as permanently stuck.
- **Findings:**
  1. [completeness, medium] `or` flips every `commit: ""` row to `—` —
     **fix** (already applied independently before this pass returned,
     after the same finding from the external plan review; switched to
     an explicit `commit_raw is None` guard + a dedicated regression
     test — see Confidence Calibration row 3).
  2. [architecture, medium] sibling `ts`/`tests`/`review`/`affected_frs`/
     `description` reads in the same function have the identical
     landmine, reachable from the same foreign-event trust boundary —
     **fix** (all five guarded with the field's own empty-equivalent
     default; two new regression tests — Confidence Calibration rows
     4-5).
  3. [architecture, medium] F5b's silent exception-swallow + C2's SKIP
     mean the next unmodelled null repeats the same permanent stall —
     **disclose**. Fixing this means changing `finalize_iterate.py`'s
     step-result contract and `iterate_checks.py`'s C2 SKIP condition
     (`cross_component`-flagged pipeline validator machinery per SKILL.md's
     risk taxonomy) — a materially larger, separately-scoped change.
     Recorded as a known limitation; worth its own iterate.
  4. [architecture, low] the rejected read-boundary alternative (mini-plan)
     cited a wrong-but-plausible premise (claimed consumers "deliberately
     distinguish" null/absent commit, when the two checked consumers
     already collapse both via truthiness) — **fix**: mini-plan's
     rejection rationale corrected in place (see its `## Alternative
     approach` — the two real reasons are: `read_events` is a generic
     shared reader used by compliance/fr_gates/context-index, so coercing
     field values there is a schema mutation in the wrong layer; and
     normalizing at read time destroys the forensic signal that a
     producer emitted null in the first place).
  5. [completeness, medium] verification only ran one of the two pytest
     roots (`shared/scripts/tests` vs `shared/tests`) that render this
     function — **fix**: ran `shared/tests/test_build_dashboard_md_escaping.py`
     + `shared/tests/test_render_determinism.py` (9/9 passed, Confidence
     Calibration row 7).
  6. [completeness, low] the two original regression assertions
     (`"| — |" in block`) were column-free substring matches — **fix**:
     tightened to the full expected row.
  7. [architecture, low] Build History's synthetic merged-in rows used a
     different placeholder (`sec.get("commit", "?")`) than the
     event-sourced rows (`—`) in the same column — **fix**: changed to
     `sec.get("commit")` (no default) so it flows through the same
     placeholder decision as every other row in that column.
  8. [performance, low] a broadly-rewriting fix risks the derived-snapshot
     `git add -A` sweep landmine at F6 — **no_change_needed**: moot once
     finding 1 was fixed with `is None` instead of `or` — regeneration no
     longer changes any row this repo's own event log actually has (0
     null commits today; empty-string rows are pixel-identical to before).
- **Known limitations:** finding 3 above (silent F5b failure + C2 SKIP
  gap) — disclosed, not fixed this iterate.
- **Status:** 6 fixed, 1 disclosed, 1 no_change_needed

## Stage-1 Spec Review — first pass REJECTed, fixed same session
The first Stage-1 `spec-reviewer` pass (before Step 8's cascade recorded
its terminal result) returned **REJECT**: `_test_status_from_iterate` — a
separate function from `_generate_from_events`'s inline field reads,
reached via the Test Status section — still read
`latest_event.get('tests', {})` and `latest_event.get('ts', '')[:10]`
unguarded at lines 322/334/336. A `work_completed` event with
`tests: null` and no `shipwright_test_results.json` on disk raised
`AttributeError: 'NoneType' object has no attribute 'get'` — a fourth
call site the Out of Scope section (above) had claimed was covered and
was not. Neither new sibling-field regression test caught it (both force
`use_iterate=False` via `ts: None`). **Fixed same session:** all three
sites guarded with the same `or`-default idiom used elsewhere in this
diff; added `TestNullCommit::test_test_status_flat_fallback_null_tests_does_not_raise`
(Confidence Calibration row 6) reproducing the exact path the reviewer
named; bloat-exception ADR and baseline `current` updated to 733 for the
added test. Stage 1 re-run against the corrected diff below.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-23-dashboard-null-commit/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — normalize
  the falsy/missing/null commit value to the existing placeholder before
  slicing, at each existing call site. (Both reviewers were shown the
  three-line "adds nothing permanent" brief per protocol, not the mini-plan's
  reasoning — they independently landed on the same shape as the fix.)
- **Findings:** none from either reviewer.
- **Reconciliation:** n/a — no `reject`, no scope disagreement. Both
  confirmed this is machinery-level maintenance on an existing renderer,
  not a new standing mechanism; no alternative to reconcile against.
