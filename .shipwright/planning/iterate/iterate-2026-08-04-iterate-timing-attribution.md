# Iterate Spec: iterate-timing-attribution

- **Run ID:** iterate-2026-08-04-iterate-timing-attribution
- **Type:** change
- **Complexity:** medium (operator-directed; classifier returned `small` at
  confidence 0.6 from the history-prior fall-through — under-classified for a
  change that instruments producers across five separate scripts plus a new
  durable event field and report. Medium buys the rigor this scope actually
  needs: spec, external plan review, full code review, Test Completeness
  Ledger, Confidence Calibration.)
- **Status:** in progress

## Goal

Instrument the complete Iterate wall-clock in one measurement-only change,
replacing the near-empty `phase_timings` history (4 of 5 recent runs recorded
exactly one of five marks) with hierarchical spans that distinguish real
producer-owned boundaries from agent-emitted marks, and report both
per-run and rolling throughput — without changing any verdict, gate, retry
decision, review cascade, CI requirement, or delivery outcome.

## Acceptance Criteria

- [x] Additive, best-effort hierarchical timing spans across the full
  Iterate lifecycle: 7 top-level groups + 14 nested spans.
- [x] Every span carries name, parent, source, UTC start/end, monotonic
  duration where a single process owns it, attempt/round, and outcome
  (completed/incomplete/cancelled/unavailable). Parent and child durations
  are never summed; exclusive time is computed and never double-counted.
- [x] Real producer boundaries are stamped by the owning process itself —
  F0's leak-guard, host-lease queue/active split, external LLM review call,
  and the F11 delivery ladder — not by an agent remembering a shell command.
- [x] Boundaries with no owning process stay agent-emitted, and their
  absence is reported as `unattributed` with a reason, never zero.
- [x] No follow-up limits, caching, fingerprint reuse, review skipping, new
  CI jobs, or timing-based policy decisions were added.
- [x] No prompts, findings, source contents, console logs, test output,
  credentials, or unbounded payloads are recorded (closed-vocabulary
  `extra` allowlist enforces this by construction).
- [x] Transient marks live in a gitignored per-run sidecar,
  `<run_id>.iterate_timings.jsonl`; the durable copy folds into
  `work_completed.iterate_timings` at F5b.
- [x] Malformed timing data (bad name, invalid parent, negative duration,
  impossible ordering, unbounded field) is rejected **per-entry** before
  persistence — never all-or-nothing, so one bad mark cannot zero a run.
- [x] The human-readable report at `.shipwright/compliance/performance/iterate-throughput.md`
  is reproducible entirely from `shipwright_events.jsonl`, is never loaded
  as agent startup context, and identifies partial/pre-instrumentation runs
  plainly.

## Spec Impact

- **Classification:** none
- **NONE justification:** This is internal measurement tooling for the
  Shipwright framework's own iterate lifecycle — it adds no product-facing
  functional requirement (FR) and changes no user-observable behavior of any
  target project. It is infrastructure in the same class as the existing
  `phase_timings` system (iterate-2026-07-11-iterate-phase-timing) and the
  F0 host-resource lease (iterate-2026-08-03-f0-host-resource-lease), both
  of which also classified `none`.

## Out of Scope

- Any optimization of a measured phase (the card is explicit: "measures
  only"). No optimization item is pre-created; the operator decides after at
  least three normal instrumented runs.
- Follow-up limits, caching, fingerprint reuse, review skipping, new CI jobs.
- Re-opening the F0 host-lease weight-22 design (ruled out by the operator
  as a bottleneck — honest saturation, not miscalibration) or re-diagnosing
  the 01.08 34-hour-run gap (out of scope for a measurement-only card; noted
  as a candidate follow-up once instrumented runs exist to look at).
- Instrumenting `shared/scripts/lib/llm_review.py` — verified against the
  code that this is the `shipwright-adopt` plugin's own review path
  (`plugins/shipwright-adopt/scripts/lib/review_runner.py`), not iterate's.
  Iterate uses `external_review.py` exclusively; only that script was
  instrumented.
- Instrumenting `finalize_bundle.py`'s internal per-step (F1/F3/F4/F5c)
  timing — it is an optional speed path; the `finalization` top-level group
  stays agent-emitted like the existing `phase_timings` "finalize" mark, to
  keep this change's surface matched to what the card's nested-span list
  actually names.
- Deriving `post_ci_remediation` automatically from the gap between
  consecutive `ci_wait` spans — considered, but the diagnose→fix→re-push
  work has no process boundary Shipwright's own scripts observe (a human or
  an agent edits code and re-pushes outside any `deliver_pr.py` call), so it
  stays an explicit agent-emitted span rather than an inferred one.
- **Durable delivery-phase attribution** (external plan review, both
  reviewers, high severity). F6 stages the F5b-recorded event and F11 pushes
  that commit before CI/delivery wait time is knowable — embedding
  `ci_wait`/`delivery_wait`/`post_ci_remediation` into the SAME immutable,
  already-pushed commit is not achievable without either racing an async
  host auto-merge with a follow-up commit (rung 2 — genuinely unsafe: GitHub
  can merge before any amendment lands) or a new post-merge write mechanism
  (itself a new card; this one explicitly rules out new CI jobs and policy
  decisions). These three spans DO reach the sidecar (useful for diagnosing
  a stuck F11 within the current run) but not `work_completed.iterate_timings`
  or the cross-run rolling report. Documented prominently in
  `iterate-timings.md` and `hooks-and-pipeline.md` rather than silently
  shipped as solved. Fixed instead this iterate: `deliver()` now
  self-records ci_wait/delivery_wait's own `delivery` top-level parent
  (removing a fragile agent-mark dependency the same review flagged),
  exclusive-time computation was changed from summing children's raw
  durations to an interval UNION (a second finding — overlapping siblings
  would otherwise double-count), the parent-resolution tiebreak now prefers
  the most-recently-opened candidate (a third finding — two open-ended
  top-level groups previously resolved alphabetically, not by plausibility),
  and sidecar writes now take the same `FileLock` `record_event.py`/
  `triage.py` use for JSONL append-logs (a fourth finding — unlocked
  concurrent appends, especially on Windows).

  **Round 2 (code review, both fixed):** `deliver()` used to wrap `watch`
  unconditionally before the ladder chose a rung, so `self_merge()`'s own
  internal retry loop (rung 3) each recorded its own `ci_wait` on top of the
  outer one — up to 4 overlapping, mislabeled spans for one self-merged
  delivery; fixed by wrapping `watch` only at the rung-2 call site.
  `run_stat`'s top-level dict comprehension silently kept whichever of two
  same-named top-level spans sorted last (e.g. a redundant agent mark over
  the real producer span), skewing `total_ms`; fixed with a
  producer-over-agent, bounded-over-open-ended, longest-duration selection
  rule (`_select_top_level`).

  **Round 3 (doubt review, all three fixed):** the durable/report path
  cannot durably capture just the 3 nested delivery children as originally
  documented — the entire top-level `delivery` group and `finalization`'s
  own duration are ALSO structurally unreachable at fold time, in every run,
  which pinned `degraded` to True forever with zero discriminating power;
  fixed by measuring coverage/degraded against `FOLD_TIME_CAPTURABLE_SPANS`
  (the 5 groups that genuinely can close by F5b), not all 7. A cross-process
  clock regression between two agent `start`/`end` marks (NTP correction,
  suspend/resume) silently clamped to a fabricated 0ms "completed" span,
  directly contradicting the "never a fabricated zero" acceptance criterion;
  fixed by detecting `end_dt < start_dt` and marking that entry `unavailable`
  with no duration, AND by removing an unnecessary timestamp re-sort in
  `pair_agent_events` that this fix exposed (pairing now trusts real
  file/append order, not each mark's own — potentially skewed — embedded
  timestamp). The F0 `f0_queue` warmup span's timestamps were reconstructed
  AFTER `ensure_xdist_available`/`warm_up()` had already run, shifting the
  reported queue-wait window later than reality by however long those took;
  fixed by recording immediately on lease grant, before that work runs.

  **Round 4 (external code review, 4 fixed, 1 declined):** `_attach_parents`
  picked a child's containing-parent candidate from ALL entries, not just
  ones that themselves survived validation, so a child could attach to a
  parent instance that was independently rejected, leaving a durable span
  whose claimed parent does not exist in the output; fixed with
  `_cascade_reject_orphans` (fixed-point iteration removing any child whose
  chosen parent was itself removed — a rejected grandparent can orphan a
  grandchild in turn). `run_stat`'s `covered_ms` unioned intervals from ALL
  spans including duplicates `_select_top_level` had already discarded for
  `total_ms`, so `covered_ms` could exceed its own envelope; fixed by
  clipping each interval to `[min(starts), max(ends)]` before the union.
  `_record_f0_queue_span`'s canonical-run-id gate used a bare
  `run_id.startswith("iterate-")`, which a malformed id like
  `iterate-not-canonical` also satisfies; fixed by importing and matching
  the actual `RUN_ID_STRICT` regex `iterate_timing.py`'s own CLI already
  enforces. The `extra` metadata's string fields were type- and
  length-checked but not pattern-checked, so up to 200 chars of arbitrary
  prose (a prompt fragment, a finding) could ride under an allowed key;
  fixed with a closed `_EXTRA_STR_PATTERN` (`[A-Za-z0-9 ._:/-]*`) and the max
  cut to 80. **Initially declined, then fixed at F5:** a request to prove the
  sidecar's `FileLock` safe under real multi-*process* concurrency, not just
  the thread-based test already added
  (`test_concurrent_producer_writers_never_corrupt_the_sidecar`, 40 threads).
  First judged out of scope on the reasoning that `file_lock.py` — the same
  primitive `record_event.py`/`triage.py` already rely on — carries no
  cross-process test of its own anywhere in the codebase, so holding this
  module alone to a stricter bar seemed unwarranted; reversed once F5's Test
  Completeness Ledger gate revealed the closed `UNTESTABLE_REASON_CODES`
  vocabulary (`shared/scripts/tools/verifiers/iterate_checks.py`) has no
  code for "an existing lower-bar primitive isn't tested either" — the
  gate's own design treats that as not a legitimate exemption, only "test
  it, or cite a structural reason." Added
  `test_concurrent_writers_across_real_OS_processes_never_corrupt_the_sidecar`
  (8 genuine `python -c` subprocesses, sharing nothing but the filesystem)
  instead of forcing a vocabulary mismatch.

  **Round 5 (external code review re-run, 3 fixed):** a fresh
  `external_review.py --mode code` pass against the full staged diff (GPT via
  OpenRouter; DeepSeek returned an empty reply and is recorded `degraded` —
  not treated as a second independent vote) found three real gaps. (a)
  `run_stat`'s coverage count treated a top-level span as "captured" purely
  by presence in `phases`, regardless of whether it had closed — a run
  containing only `start` marks for all five fold-time-capturable groups
  read as `5/5`, non-degraded, indistinguishable from a genuinely complete
  run; fixed by requiring both a non-null `duration_ms` AND an outcome
  outside `{incomplete, unavailable}` before counting a group as covered,
  and by rendering an explicit `*{outcome}* (started, not closed)` cell for
  a present-but-unclosed phase instead of a bare "—" that reads the same as
  *not captured*. (b) the closed `extra` vocabulary bounded string values
  but left every numeric field unbounded — a CLI-supplied `--extra-json`
  could carry an arbitrarily large `weight`/`polls`/`checks_observed` or a
  non-finite `waited_seconds` (`NaN`/`Infinity`) straight into the durable
  event; fixed with a per-field numeric bound registry
  (`_EXTRA_NUMERIC_BOUNDS`, fail-closed — a numeric field with no registered
  bound is rejected outright, not passed through) and `math.isfinite`
  rejection for floats, with a forward+reverse SSoT meta-test pinning that
  every numeric `EXTRA_FIELD_TYPES` entry has a bound. (c) a producer span's
  `duration_ms` (`time.monotonic()`) and its `start_utc`/`end_utc`
  (`datetime.now()`) are two independent clock readings that `validate_entry`
  never cross-checked — a corrupted record could claim a one-minute interval
  with a multi-hour duration, silently producing impossible exclusive-time
  percentages instead of being rejected; fixed with a tolerance check (2% of
  the larger value, 5s floor — generous enough to absorb real wall/monotonic
  drift on this project's own 34-hour-class runs, tight enough to catch a
  ~60x mismatch) in `iterate_timings_pairing.validate_entry`. Extracting the
  `extra`-validation block into a new `iterate_timings_extra.py` leaf module
  (needed to keep `iterate_timings.py` under the 300-line guideline once the
  numeric-bounds registry was added) surfaced no behavior change — re-
  exported from `iterate_timings.py` for existing callers, verified under
  both `lib.X` and `scripts.lib.X` import conventions.

  **Round 6 (external code review re-re-run, 3 fixed):** a second follow-up
  pass against the updated diff found three more gaps. (a)
  `canonical_f0_active` was only recorded on `run_suite()`'s successful
  return — an exception skipped the recording entirely, losing the one
  producer boundary most useful during exactly the failed runs it exists to
  explain; fixed by wrapping the call in `_run_host_leased_suite` with a
  try/except that records `outcome="incomplete"` (a new
  `record_canonical_f0_active_span_failed` in `suite_timing.py`, mirroring
  `span()`'s own incomplete-on-exception contract) before re-raising
  unchanged. (b) a missing fold-time-capturable top-level span rendered as a
  bare `*not captured*` — visible, but not the "unattributed WITH REASON"
  the card's own acceptance criteria require, and indistinguishable from
  `finalization`/`delivery`'s expected structural absence; fixed by labeling
  the two cases separately (`*unattributed — no agent start/end marks
  recorded*` vs `*not reached before F5b fold (structural)*`). (c)
  `deliver_pr_timing.py`'s `checks_observed` extraction used a bare
  `isinstance(value, int)` check — since `bool` is an `int` subclass in
  Python, a host result with `checks_observed=True` would pass this guard,
  get rejected by the closed-vocabulary validator's stricter bool-vs-int
  distinction, and (caught by `span()`'s broad exception guard) silently
  drop the ENTIRE `ci_wait` span rather than just the one bad field; fixed
  with an explicit `not isinstance(value, bool)` guard alongside it.

  **Round 7 (external code review final pass — 2 fixed, 1 declined false-
  positive):** GPT gave `revise` (DeepSeek independently gave `approve` with
  no findings). (a) **Declined as a false positive:** GPT reported a HIGH
  finding that `external_review.py`'s `_KNOWN_PLACEHOLDERS` tuple contained
  a pasted multiline spec causing a syntax error. Verified false: the actual
  line is `_KNOWN_PLACEHOLDERS = ("{PLAN}", "{DIFF}", "{SPEC}")` (unchanged,
  3-item tuple), `ast.parse()` on the file succeeds, and the file is 409
  lines with 8 docstring markers — no embedded spec anywhere. Most likely
  explanation: this diff includes the full iterate spec .md as a NEW FILE,
  and the reviewer's diff-context window misattributed those added lines to
  a nearby hunk in `external_review.py`. Not fixed because there was nothing
  to fix. **This recurred identically in a Round 8 verification pass**
  (GPT `reject`, citing the same claim at the same line; DeepSeek `approve`,
  explicitly flagging its own uncertainty and deferring to direct
  verification) — confirmed false a second way by reading the diff hunk
  itself: `_KNOWN_PLACEHOLDERS = ("{PLAN}", "{DIFF}", "{SPEC}")` appears as
  unchanged CONTEXT (no `+`/`-` prefix) in `git diff`'s own output, with
  nothing resembling spec text anywhere in the file's ~114-line hunk.
  Working theory: this diff's largest single addition is the full iterate
  spec .md landing as a new file a few thousand diff-lines before
  `external_review.py`'s own hunk, and a reviewer whose job IS "read specs
  against diffs" may be more prone than usual to conflating "this diff
  contains a large spec block" with "this file contains one." Treated as
  resolved, not re-submitted a third time chasing a reproducible phantom
  once verified two independent ways. (b) **Fixed:** `validate_entry` accepted structurally contradictory
  records — `outcome="completed"` with `end_utc=None` and/or
  `duration_ms=None` — which the render layer then displayed as the
  nonsensical "*completed* (started, not closed)"; fixed by rejecting
  `outcome == "completed"` unless both fields are present, at the same write
  boundary as every other structural check. (c) **Fixed:** the existing
  `test_resume_across_separate_processes_appends` called the writer
  functions twice in the SAME Python process, so its name overclaimed what
  it verified; renamed to `test_sidecar_is_append_only_across_sequential_calls`
  with an honest docstring, and a NEW genuine two-subprocess test
  (`test_resume_across_real_separate_os_processes`, spawning real
  `python iterate_timing.py` processes) now proves the actual cross-OS-
  process claim the acceptance criteria make.

  **Post-review hardening:** the Stop-hook's bloat gate fired a second time
  after `RUN_ID_STRICT` (Round 4's fix, above) pushed `run_test_suite.py`
  from the 538 lines ADR-123 had just documented to 542. ADR-123's own
  Decision section had already committed to the answer for exactly this —
  "if the timing instrumentation ... has grown it more, extract a
  `suite_timing.py` sibling" — so `_record_f0_queue_span` and the
  `canonical_f0_active` recording moved into a new
  `shared/scripts/tools/suite_timing.py` (63 lines), landing
  `run_test_suite.py` at 508, below even the pre-Round-4 baseline. That
  extraction surfaced a real latent bug the original inline code had been
  silently swallowing: the `canonical_f0_active` block read
  `result.duration`, an attribute `SuiteResult` has never had (the field is
  `seconds`) — every real invocation was hitting `AttributeError` and being
  caught by the deliberately broad `except Exception` that exists so a
  timing fault can never break F0 itself, so the span was silently skipped
  on every run rather than recorded. The two full-suite integration tests
  that actually exercise `_run_host_leased_suite` end to end
  (`test_suite_host_resources.py`, `test_f0_cli_diff_coverage_e2e.py`) were
  the ones that caught it, once the attribute access was correctly hoisted
  where a test double's mismatched return shape could surface it; the
  synthetic weight-22 unit test (Confidence Calibration probe 2) could not,
  because it calls `iterate_timings.record_producer_span` directly and never
  goes through `run_suite()`'s real return value. Fixed to `result.seconds`,
  and re-designed `record_canonical_f0_active_span` to take the raw `result`
  object and read `.seconds` INSIDE its own try/except, restoring the
  original safety property that the extraction had briefly broken (the
  attribute access must stay inside the guard, not move to the call site).

  **F6 registry consistency:** `iterate-throughput.md` is fully reproducible
  from `shipwright_events.jsonl` alone (`test_report_is_deterministic_given_the_same_events`)
  — the same property that puts the 5 existing compliance MDs on the
  `DERIVED_SNAPSHOTS` exclusion list (iterate-2026-07-27-derived-snapshots-off-branch:
  committing a branch-local derivation reads that branch's own git history,
  which goes stale/wrong the moment another iterate merges). Registered it
  as its own constant (`THROUGHPUT_REPORT` in `churn_merge.py`, alongside
  `CI_SECURITY_SUMMARY`/`TEST_TRACEABILITY` — a different producer than
  `_update_compliance`, so not folded into `COMPLIANCE_MDS` itself) and
  excluded it from this run's own F6 commit, matching the other 5. Four
  forward-drift tests (`test_doc_table_matches_churn_allowlist_both_directions`,
  `test_registry_covers_every_derived_md_plus_the_two_json_snapshots`,
  `test_every_derived_snapshot_carries_a_classification`,
  `test_every_non_refreshed_snapshot_is_excluded_by_name_with_a_reason`)
  caught every registry this needed touching before a single manual review
  would have.

  **F11 verification (2 fixed):** `verify_iterate_finalization.py` found two
  real gaps once run against the correct project-root (the WORKTREE root —
  an earlier F11 step had been run against `shared/` by mistake, producing
  false failures that were re-diagnosed and corrected first). (a) touching
  `shared/scripts/lib/churn_merge.py` is cross-component machinery (the
  `cross_component` risk flag's own file patterns), which the F11 verifier
  `check_integration_coverage` recomputes from the diff at every complexity
  and requires ≥1 Test Completeness behavior marked `category:"integration"`
  — added `test_the_two_components_agree_on_the_throughput_report` to
  `test_derived_definition_integration.py` (real git, the same "two
  components that never call each other" pattern its existing campaign-board
  test already used) proving `THROUGHPUT_REPORT`'s `CHURN_ALLOWLIST`
  membership and the F11 silent-revert gate's exemption agree. (b) the
  conventions.md Learnings bullet (Round 7's own note, above) had been
  appended to the END OF THE FILE, which is actually inside the LATER
  `## Convention Updates` section (canonical-anchor shape-governed) rather
  than `## Learnings` (date-first grammar, exempt) — moved it to the correct
  section, right after the last genuine Learnings entry.

  **Delivery-time findings (2 fixed):** the real `deliver_pr.py` run against
  a live PR surfaced what synthetic tests could not. (a) **A live production
  bug:** `deliver_pr.py`'s own `ci_wait` span carries `timed_out` (a
  bool-typed `extra` field) — Round 5's numeric-bounds fix added
  `elif isinstance(value, (int, float)):` to `validate_extra`, and since
  `bool` is an `int` subclass in Python, `timed_out` fell into that branch,
  found no registered numeric bound (bools aren't numeric), and the
  fail-closed check silently dropped the ENTIRE span — the exact
  `checks_observed` bug class fixed in Round 6, just missed in this OTHER
  new branch added one round later. Fixed with the same
  `not isinstance(value, bool)` guard, plus a direct regression test
  (`test_bool_typed_field_does_not_fall_into_the_numeric_bounds_branch`) —
  no synthetic ledger case had exercised a bool-typed field through the
  numeric branch specifically. (b) CodeQL flagged 4 real findings on the
  live PR: 3 "implicit string concatenation in a list" (a multi-line string
  literal inside a list is syntactically ambiguous with a missing comma to
  CodeQL's heuristic, even though correct here) — fixed by wrapping each in
  explicit parens, a zero-risk clarification; 1 "unreachable code" — a known
  CodeQL Python limitation, not a real defect: its control-flow analysis
  does not model `pytest.raises()` as exception-catching, only a direct
  `try`/`except`, so it read the assertion after
  `with pytest.raises(ValueError): with it.span(...): raise ValueError(...)`
  as dead code. Fixed by moving the `raise` into a called helper (`_boom()`)
  rather than an inline literal — same behavior, avoids the pattern CodeQL
  mis-analyzes, no CodeQL-config exclusion needed (an existing
  `.github/codeql/codeql-config.yml` query-filter precedent exists for
  exactly this kind of tailoring, but a query-level exclusion would also
  silence real unreachable-code bugs repo-wide; the targeted code fix does
  not carry that cost).

## Design Notes

Non-UI change; no mockups or design tokens involved.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/scripts/lib/iterate_timings.py` (writers) + `shared/scripts/tools/iterate_timing.py` (agent CLI) | `shared/scripts/lib/iterate_timings_normalize.py` | JSONL sidecar |
| `finalize_iterate.py::_record_event` (`_fold_iterate_timings`) | `work_completed.iterate_timings` readers (report, future WebUI) | JSON (event field) |
| `shared/scripts/tools/iterate_throughput_report.py` | operator / WebUI (never agent context) | Markdown |

Boundary Probe sub-step run (`touches_io_boundary` — new JSONL sidecar +
JSON event field): round-trip probes exercise write→read→normalize for both
producer (`span()`) and agent (`start`/`end` pair) shapes, across process
boundaries (separate CLI invocations, proving resume), and the full
write→fold→report chain end to end. See Confidence Calibration below.

## Confidence Calibration

- **Boundaries touched:** the iterate-timings JSONL sidecar (write by
  `iterate_timings.py`/`iterate_timing.py`, read by
  `iterate_timings_normalize.py`), and the new `work_completed.iterate_timings`
  JSON field (write by `finalize_iterate.py`, read by
  `iterate_throughput_report.py`).

- **Empirical probes run:**
  1. Manual end-to-end smoke test (spans → fold → event → report) before any
     test was written — caught a real bug: "unattributed" time was computed
     from only top-level exclusive durations, so a fully-covered nested
     phase (e.g. `verification` with F0 children accounting for 100% of its
     span) read as 100% unattributed. Fixed to sum exclusive time across
     **every** span in the tree, not just top-level.
  2. Synthetic weight-22 F0 blocker case (matching the P1.16 rollout shape:
     18.0 min queued, 5.4 min active) — proved `f0_queue` and
     `canonical_f0_active` are correctly distinguished and `verification`'s
     own exclusive time is exactly 0 (fully accounted by children, no
     double-count).
  3. Real subprocess run of `external_review.py` with `--run-id` against a
     temp project root — confirmed the span lands in the sidecar with the
     correct `parent` (`review` for `--mode code`) and `provider` extra,
     using the actual argparse/CLI path, not a mocked call.
  4. Full existing `deliver_pr` test suite (47 tests, 4 files) re-run after
     wiring `record_timing` — caught a real hazard: those tests pass
     `project_root=Path("/tmp/wt")` with no `tmp_path` sandbox; unconditional
     instrumentation would have written real files to `/tmp/wt` on every
     test run. Fixed by making `record_timing` explicit opt-in (default
     `False`), verified `/tmp/wt` was never created after the fix, and all
     47 pre-existing tests still pass unmodified.
  5. Two containment-resolution bugs found and fixed via a dedicated
     `ci_wait`/`delivery_wait` test: (a) a nested span whose two candidate
     parents (top-level `delivery` and nested `delivery_wait`) share
     identical bounds resolved non-deterministically (frozenset iteration
     order) — fixed to pick the tightest-fitting, most-specific candidate
     deterministically; (b) `deliver_pr.py` never emits the top-level
     `delivery` span itself, so `delivery_wait`/`ci_wait` are only
     attachable once the SKILL marks `start delivery` first — documented
     explicitly as a coordination contract in `iterate-timings.md`, and the
     unit test simulates that mark rather than assuming it.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Producer span recorded via `span()` context manager | tested | `test_iterate_timings.py::test_span_context_manager_records_on_success` PASSED |
  | 2 | Span marked incomplete on exception, exception still propagates | tested | `test_span_context_manager_marks_incomplete_on_exception` PASSED |
  | 3 | Agent start/end pairing across separate process invocations (resume) | tested | `test_iterate_timing_cli.py::test_resume_across_real_separate_os_processes` (genuine subprocess pair) PASSED; `test_sidecar_is_append_only_across_sequential_calls` (same-process isolation of the append-only property) PASSED |
  | 4 | Malformed entry dropped without voiding the rest of the run | tested | `test_malformed_entry_is_dropped_without_voiding_the_run` PASSED |
  | 5 | Negative duration rejected | tested | `test_negative_duration_rejected` PASSED |
  | 6 | Child outside parent's time bounds rejected (impossible ordering) | tested | `test_child_outside_parent_bounds_is_impossible_ordering` PASSED |
  | 7 | Nested spans not double-counted (exclusive-time computation) | tested | `test_nested_spans_are_not_double_counted` PASSED |
  | 8 | Partial child coverage leaves parent's own exclusive time visible | tested | `test_partial_coverage_leaves_parent_exclusive_time_visible` PASSED |
  | 9 | F0 queue vs active execution distinguishable (synthetic weight-22) | tested | `test_f0_queue_and_active_execution_are_distinguishable_weight22` PASSED |
  | 10 | Multiple `ci_wait` attempts individually attributed | tested | `test_ci_wait_attempts_are_individually_attributed` PASSED |
  | 11 | F5b folds `iterate_timings` alongside (not instead of) `phase_timings` | tested | `test_finalize_folds_iterate_timings_alongside_phase_timings` PASSED |
  | 12 | No sidecar → field omitted, not zero | tested | `test_finalize_without_sidecar_omits_iterate_timings` PASSED |
  | 13 | Pre-existing `iterate_timings` field on the event is never overwritten | tested | `test_finalize_never_overwrites_a_preexisting_field` PASSED |
  | 14 | Interrupted/cancelled run persists `incomplete`, never a fabricated zero | tested | `test_incomplete_span_persists_as_incomplete_not_zero` PASSED |
  | 15 | Malformed span rejected at the event-write boundary; rest still persists | tested | `test_malformed_span_is_rejected_the_rest_still_persists` PASSED |
  | 16 | Existing gate/verdict behavior (FR-gate) unchanged by the timing fold | tested | `test_gate_ordering_and_verdict_unchanged_by_timing_fold` PASSED |
  | 17 | Agent CLI `start`/`end` round-trip through normalize | tested | `test_start_then_end_round_trips_through_normalize` PASSED |
  | 18 | Non-canonical run_id refused (no stray sidecar written) | tested | `test_non_canonical_run_id_is_refused` PASSED |
  | 19 | Unknown span name rejected at the CLI (argparse choices) | tested | `test_unknown_span_name_is_an_argparse_error` PASSED |
  | 20 | Malformed `--extra-json` refused | tested | `test_end_with_malformed_extra_json_is_refused` PASSED |
  | 21 | F0 `f0_queue` span recorded for a canonical run_id, gated for a non-canonical one | tested | `test_f0_queue_span_recorded_for_canonical_run_id`, `test_f0_queue_span_skipped_for_non_canonical_run_id` PASSED |
  | 22 | F0 timing span recording never raises (best-effort) | tested | `test_f0_queue_span_never_raises_on_bad_project_root` PASSED |
  | 23 | `deliver()`'s timing instrumentation is opt-in; default touches no filesystem | tested | `test_record_timing_off_by_default_writes_nothing` PASSED |
  | 24 | `deliver()` records `delivery_wait`/`ci_wait` with correct rung/extras when opted in | tested | `test_record_timing_on_records_delivery_wait_and_ci_wait` PASSED |
  | 25 | Report: empty state with no events | tested | `test_report_is_empty_state_with_no_events` PASSED |
  | 26 | Report: pre-instrumentation run identified plainly, never as zero | tested | `test_pre_instrumentation_run_identified_plainly_not_as_zero` PASSED |
  | 27 | Report: degraded coverage surfaced, not hidden | tested | `test_degraded_coverage_surfaced_not_hidden` PASSED |
  | 28 | Report: deterministic given the same events | tested | `test_report_is_deterministic_given_the_same_events` PASSED |
  | 29 | Report: written to the documented path | tested | `test_write_report_creates_the_documented_path` PASSED |
  | 30 | Report: CI-retry attribution visible in the rendered nested table | tested | `test_ci_retry_attribution_visible_in_nested_table` PASSED |
  | 31 | Report: rolling stats appear once enough instrumented runs exist | tested | `test_rolling_stats_appear_with_enough_instrumented_runs` PASSED |
  | 32 | External-review producer span records `provider`/`parent` correctly | tested | manual end-to-end subprocess run (real CLI, temp project root) — see probe 3 above |
  | 33 | Real GitHub-backed delivery ladder timing (live `gh` calls) | untestable | requires-external-nondeterministic-service |
  | 34 | Real concurrent sibling-worktree F0 host-lease contention under this instrumentation | untestable | covered-by-existing-test (the lease mechanism itself is P1.12/P1.16's own coverage; this card only persists what it already computes, verified via the synthetic weight-22 case above rather than re-proving the lease) |
  | 35 | A child attached to a parent instance that is itself rejected cascades the rejection | tested | `test_iterate_timings_hierarchy.py::test_a_child_attached_to_a_rejected_parent_cascades_the_rejection` PASSED |
  | 36 | `covered_ms` never exceeds the selected top-level envelope (duplicate-span clipping) | tested | `test_iterate_throughput_report.py::test_covered_ms_never_exceeds_the_selected_envelope` PASSED |
  | 37 | `f0_queue` gating uses the actual `RUN_ID_STRICT` regex, not a loose prefix | tested | `test_run_test_suite_timing.py::test_f0_queue_span_skipped_for_a_run_id_that_only_LOOKS_canonical` PASSED |
  | 38 | `extra` string field rejected when it contains disallowed characters (prompt/finding-shaped prose) | tested | `test_iterate_throughput_report.py::test_extra_with_pipe_or_newline_is_rejected_at_validation` PASSED |
  | 39 | A pipe/newline in already-validated `extra` data does not break the rendered table (defense in depth) | tested | `test_iterate_throughput_report.py::test_extra_field_pipe_character_does_not_break_the_table` PASSED |
  | 40 | Concurrent producer writers never corrupt the sidecar | tested | `test_iterate_timings_concurrency.py::test_concurrent_producer_writers_never_corrupt_the_sidecar` (40 threads) PASSED |
  | 41 | Overlapping sibling spans use interval union, not raw-duration sum | tested | `test_iterate_timings_hierarchy.py::test_overlapping_siblings_use_interval_union_not_sum` PASSED |
  | 42 | An ambiguous open-ended top-level parent resolves to the most-recently-opened candidate | tested | `test_iterate_timings_hierarchy.py::test_most_recently_opened_open_ended_parent_wins_ties` PASSED |
  | 43 | `canonical_f0_active` is recorded from the real `SuiteResult.seconds` field | tested | `test_run_test_suite_timing.py::test_canonical_f0_active_span_recorded_from_the_real_result_shape` PASSED |
  | 44 | A `result` whose shape doesn't match degrades to a skipped span, never raises | tested | `test_run_test_suite_timing.py::test_canonical_f0_active_span_never_raises_when_result_lacks_seconds` PASSED |
  | 45 | Cross-process multi-*process* (not just multi-thread) safety of the sidecar `FileLock` | tested | `test_iterate_timings_concurrency.py::test_concurrent_writers_across_real_OS_processes_never_corrupt_the_sidecar` (8 genuine subprocesses) PASSED |
  | 46 | A present-but-unclosed (bare-start) top-level span does not count toward coverage | tested | `test_iterate_throughput_stats.py::test_present_but_incomplete_top_level_span_does_not_count_toward_coverage` PASSED |
  | 47 | A run of bare start marks for all 5 capturable groups reads as DEGRADED 0/5, not a clean complete | tested | `test_iterate_throughput_report.py::test_bare_start_marks_for_every_capturable_group_read_as_degraded_not_complete` PASSED |
  | 48 | Every numeric `extra` field has a registered bound (SSoT forward+reverse) | tested | `test_iterate_timings_extra.py::test_every_numeric_extra_field_has_a_registered_bound` PASSED |
  | 49 | An out-of-range numeric `extra` value is rejected | tested | `test_iterate_timings_extra.py::test_numeric_field_over_its_bound_is_rejected`, `test_negative_number_below_its_bound_is_rejected` PASSED |
  | 50 | A non-finite (`NaN`/`Infinity`) float `extra` value is rejected | tested | `test_iterate_timings_extra.py::test_nan_float_is_rejected`, `test_infinite_float_is_rejected` PASSED |
  | 51 | `duration_ms` grossly inconsistent with its own start/end interval is rejected | tested | `test_iterate_timings_hierarchy.py::test_duration_grossly_inconsistent_with_its_own_interval_is_rejected` PASSED |
  | 52 | `duration_ms` within legitimate wall/monotonic drift tolerance of its interval is accepted | tested | `test_iterate_timings_hierarchy.py::test_duration_within_tolerance_of_its_interval_is_accepted` PASSED |
  | 53 | `run_suite()` raising still records an incomplete `canonical_f0_active` span, exception propagates | tested | `test_suite_host_resources.py::test_run_suite_exception_still_records_an_incomplete_canonical_f0_active_span` PASSED |
  | 54 | A missing fold-time-capturable group renders as unattributed with a reason, distinct from finalization/delivery's structural absence | tested | `test_iterate_throughput_report.py::test_missing_agent_group_reads_unattributed_with_a_reason` PASSED |
  | 55 | `checks_observed=True` (bool) drops only the one field, not the whole `ci_wait` span | tested | `test_deliver_pr_timing.py::test_bool_checks_observed_does_not_break_the_whole_ci_wait_span` PASSED |
  | 56 | `outcome="completed"` with a missing `end_utc` or `duration_ms` is rejected | tested | `test_iterate_timings_hierarchy.py::test_completed_outcome_with_no_end_utc_is_rejected`, `test_completed_outcome_with_end_utc_but_no_duration_is_rejected` PASSED |
  | 57 | Agent start/end resume works across REAL separate OS processes (not just sequential in-process calls) | tested | `test_iterate_timing_cli.py::test_resume_across_real_separate_os_processes` (genuine `subprocess.run` pair) PASSED |
  | 58 | (category: integration) The `THROUGHPUT_REPORT` churn-registry addition composes correctly across `classify()` and the F11 silent-revert gate — two components that never call each other, on real git | tested | `test_derived_definition_integration.py::test_the_two_components_agree_on_the_throughput_report` PASSED |
  | 59 | A bool-typed `extra` field (e.g. `timed_out`) does not fall into the numeric-bounds validation branch and drop the whole span | tested | `test_iterate_timings_extra.py::test_bool_typed_field_does_not_fall_into_the_numeric_bounds_branch` PASSED |

- **Confidence-pattern check:** asymptote — the "unattributed time" bug
  (probe 1) and the two containment-resolution bugs (probe 5) were each
  found by running real code against realistic synthetic data BEFORE writing
  the corresponding test, then pinned with a regression test; no
  "are-you-confident" pass produced a second finding after the fixes.
  Coverage — every Test Completeness Ledger row above is `tested` or
  `untestable` with a valid reason_code; 0 rows are untested-testable.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest tests/test_iterate_timings.py tests/test_iterate_timings_hierarchy.py tests/test_iterate_timings_extra.py tests/test_iterate_timings_finalize.py tests/test_iterate_timings_concurrency.py tests/test_iterate_timings_gitignore.py tests/test_iterate_timing_cli.py tests/test_iterate_throughput_report.py tests/test_iterate_throughput_stats.py tests/test_deliver_pr_timing.py -v` (run from `{project_root}` = the `shared/` worktree, i.e. `shared/tests` — this is the actual F0.5 CLI surface runner: 64 tests, exit 0). The `scripts/tools/tests` root's timing tests (`test_run_test_suite_timing.py`, `test_suite_host_resources.py`, `test_suite_parallel_progress.py`) cannot join the same pytest process per the one-root rule — they run as F0's own `shared/scripts/tools/tests` unit instead, already green in the F0 pass this run records.
- **Evidence path:** pytest stdout / `shipwright_test_results.json`
- **Justification:** This is a pure Python tooling change with no `dev_url`/
  UI surface — F0.5's web/browser runner does not apply; the CLI test suite
  above is the surface that can actually falsify the acceptance criteria.
- **This run's own F5b fold, honestly reported:** the `external_review.py`
  and F0 CLI calls made directly during this session's own finalization
  (round 5-8 review + the F0 gate above) recorded 6 real producer spans into
  this run's own sidecar — but since they were invoked directly rather than
  through the full SKILL flow (which opens `planning`/`review`/
  `verification` top-level marks before any nested call), none had a live
  parent to attach to at fold time, and all 6 were correctly REJECTED as
  orphaned rather than mis-attributed. This run's own entry in the
  throughput report therefore reads `pre-instrumentation` — the honest,
  by-design outcome for exactly this case (`test_pre_instrumentation_run_identified_plainly_not_as_zero`
  covers it), not a defect. The pipeline's correctness is demonstrated by
  the 57-row Test Completeness Ledger's synthetic and real end-to-end
  cases above, not by this run's own (atypically-operated) fold.
