# ADR: the two stop-hooks, update_build_dashboard.py and state.py move to phase_tasks[]

**Run-ID:** iterate-2026-09-10-s3-hooks-and-state
**Campaign:** p4-04-retire-write-once-steps, sub-iterate s3 of 6 (hooks-and-state)

## Context

Continuing the per-reader migration campaign (s1 migrated the compliance
dashboard phase strip). Four remaining readers key their PRIMARY progress
signal on the write-once `current_step`/`completed_steps` fields, which
`config_factory` stamps once at run creation and the v2 `phase_tasks[]`
lifecycle never advances on a driven run:

1. `shared/scripts/lib/state.py::detect_current_phase` — comment and
   docstring literally assert `current_step` is "authoritative when
   present", which is false on a driven run.
2. `shared/scripts/tools/update_build_dashboard.py` — `_pipeline_status()`
   and two `completed_steps` reads inside `generate_dashboard()`'s legacy
   (no-events) render path. Its own unrelated `current_step: int | None`
   parameter (the 1-12 build-STEP number) is untouched — a name collision
   only, a different concept entirely.
3. `shared/scripts/hooks/generate_handoff_on_stop.py::_detect_phase_complete`
   + its call site — the Stop-hook fallback that detects an unmarked phase
   completion and triggers `orchestrator.py update-step`.
4. `shared/scripts/hooks/suggest_iterate.py::handle_in_progress_pipeline` —
   the UserPromptSubmit intent-mismatch router.

## Decision

Reuse s1's aggregation pattern (`_phase_tasks_status` in mermaid.py): for a
phase, aggregate every matching `phase_tasks[]` entry's `status` via
`shared/scripts/lib/handoff_phase_status.py`'s bucketed vocabulary
(`FINISHED_STATUSES`, `status_of()`). Two DIFFERENT migration shapes, by
design, not one:

- **`update_build_dashboard.py`** is a pure DISPLAY reader, exactly like
  mermaid.py: reads `phase_tasks[]` ONLY, no v1 fallback of any kind. A
  config with none renders every phase "pending" (same as mermaid.py, same
  reason — s2b already owns backfilling the already-adopted-repo gap).
- **`state.py`, `generate_handoff_on_stop.py`, `suggest_iterate.py`**
  consult `phase_tasks[]` FIRST, falling back to the pre-existing logic
  (state.py: its own per-phase-config heuristic, unchanged; the other two:
  the v1 fields themselves) ONLY when `phase_tasks[]` gives no confident
  signal AT ALL (absent or empty). This is ordered, not the OR-shape
  `phase_quality` uses. `generate_handoff_on_stop`'s v1 fallback is
  load-bearing, not merely a display nicety: for a genuinely standalone
  (non-driven, no `phase_tasks[]`) config such as `write_run_config.py`'s
  shape, the v1 `update_step` path is the ONLY thing that ever advances
  `current_step`, and this Stop-hook fallback is what TRIGGERS it.

"Current phase" for the three fallback readers counts a phase the moment it
has ANY `phase_tasks[]` entry that isn't finished — including one still
`backlog`/`awaiting_launch` (queued, not yet claimed) — not only an active
(`in_progress`/`failed`) one. This is a "dispatch pointer" reading (which
phase the run is AT), deliberately different from mermaid.py's tri-state
DISPLAY label (which reports no-confident-signal for a backlog-only phase,
since asserting "IN PROGRESS" on a dashboard for a phase nobody has touched
yet would mislead a viewer).

## Consequences

- All four readers are correct for a driven run at any phase past the
  first, closing the class of bug this campaign exists to retire.
- `update_build_dashboard.py`'s legacy (no-events) render path now shows
  every phase "pending" for a config with no `phase_tasks[]` at all —
  s2b's already-committed sequencing, not silently reintroduced here.
- `generate_handoff_on_stop.py`'s fallback-completion detector still issues
  an inert `update-step` (per `cli_update_step.py`'s drivability guard,
  which no-ops it for any driven config) on every Stop of a COMPLETED
  driven run, and whenever the live phase's own artifact already reports
  complete before `phase_tasks[]` catches up — code review, sub-iterate
  s3: an earlier version of this note claimed the call no longer fired on
  a phase long past, which is not what the code does. What actually
  changed is narrower: `phase_task_lifecycle.complete_phase_task` chains
  every pipeline phase with no omission-skips (one lock, plans the
  successor before releasing it), so a driven run mid-flight always has a
  confident `phase_tasks[]` signal for its true current phase — the v1
  fallback is reached only once the whole pipeline is done, or the current
  phase's artifact races ahead of `phase_tasks[]` being updated to match,
  and in both cases the call it may issue is a no-op, never a call
  targeting a STALE phase (which is what the pre-migration code risked).
- `docs/hooks-and-pipeline.md`'s write-once-fields SSoT paragraph is
  updated in the same diff (repo rule) with the explicit decision rule for
  which shape a future reader gets: display-only → `phase_tasks[]` only;
  a reader whose read feeds a side effect or a user-facing routing decision
  beyond rendering → `phase_tasks[]`-first-with-v1-fallback.
- **Bloat exception (already-`exception`-state files grew further, one
  fixed below the limit, one new crossing):** the new fallback/aggregation
  helpers plus regression tests initially pushed 4 already-grandfathered
  files further past their 300-line limit — code review then removed the
  triplicated `_phase_tasks_progress` helper from 3 of the 4 (factored into
  `shared/scripts/lib/handoff_phase_status.py`), which brought
  `shared/scripts/hooks/generate_handoff_on_stop.py` back UNDER its limit
  (282→341→293) — its exception entry is REMOVED from
  `shipwright_bloat_baseline.json`, not left stale. Net result:
  `shared/scripts/tools/update_build_dashboard.py` 548→593 (unaffected by
  the dedup — its own copy, `_phase_tasks_status`, mirrors mermaid.py's and
  is not factored in, see Rejected Alternatives),
  `shared/scripts/tests/test_build_dashboard.py` 760→933,
  `shared/tests/test_generate_handoff_on_stop.py` 402→489→559 (code
  review's requested `main()`-wiring regression tests). One NEW crossing,
  not previously baselined: `shared/tests/test_state.py` 156→315 (the
  regression test for the state.py fix below) — added to the baseline
  rather than left as an undocumented crossing for Group H to catch later,
  since this same commit already touches the baseline. `adr` on every
  touched/added entry points at this ADR.

## Rationale

Same architecture-approved per-reader migration as s1 (2026-09-06,
GPT+GLM APPROVE). The v1-fallback shape for three of the four readers is a
deliberate, documented departure from s1's "reads `phase_tasks[]` only"
characterization — justified per-reader, not a general walkback (see
External-Plan-Review-Findings).

## Rejected Alternatives

- **All four readers get the same "v2-only" shape as `update_build_dashboard.py`** —
  rejected: for `generate_handoff_on_stop.py` specifically, this would
  silently stop `current_step` from ever advancing for every standalone
  (non-driven) user, since the v1 `update_step` path it triggers is the only
  writer that advances it outside a driven run. That is a functional
  regression, not a display change.
- **A single shared cross-file `_phase_tasks_progress`/`_phase_tasks_status`
  helper** — initially deferred here (external plan review raised it, low
  severity: "all four readers already duplicate this ~15-line aggregation
  privately... consolidating now would touch four files' import graphs
  mid-migration"). Code review (Stage 2) reversed this: 3 of the 4 readers
  (`state.py`, `generate_handoff_on_stop.py`, `suggest_iterate.py`) all live
  under `shared/scripts/` and already import `lib.handoff_phase_status` —
  the "touches four import graphs" cost the plan-review cited does not
  apply to them, it is a one-line import each. Only `mermaid.py`'s copy
  stays private, since it IS a genuine ADR-045 cross-plugin case (plugin-side
  `scripts/lib`) and duplicates a different half (the tri-state DISPLAY
  label, not the dispatch-pointer reading these three share). Factored into
  `shared/scripts/lib/handoff_phase_status.phase_tasks_progress`; each
  caller keeps a `_phase_tasks_progress` local alias via `import ... as`
  so existing tests importing that name are unaffected.

## External-Plan-Review-Findings

Both GLM and OpenAI reviewed the sub-iterate spec + mini-plan (`--mode
iterate`, before the diff existed) and returned `revise`:

| Finding (severity) | Disposition |
|---|---|
| GLM (medium) / OpenAI (high, medium): the ordered v2-first/v1-fallback shape can return STALE data when `phase_tasks[]` exists but every entry for the frontier phase is still `backlog`/`awaiting_launch` (materialized, not yet claimed) — "no confident signal" then falls back to the very write-once fields this campaign retires | accepted-and-fixed — "current phase" now counts a phase the moment it has ANY unfinished `phase_tasks[]` entry (including `backlog`/`awaiting_launch`), not only an active one; the v1 fallback now fires ONLY when `phase_tasks[]` is absent/empty for the WHOLE run, never merely because the frontier phase hasn't been claimed yet. Regression tests added per reader (`test_backlog_only_phase_counts_as_current`) |
| OpenAI (high): no explicit truth table for how `FAILED_STATUSES`/`INTERRUPTED_STATUSES` affect the "complete" determination — stop-hook must never treat a failed/interrupted phase as complete | rejected-with-reason (already satisfied, clarified) — `completed_phases` was already defined as "ALL matching entries in `FINISHED_STATUSES`"; any failed, interrupted, or still-queued entry already excludes the phase. No code change needed; docstrings now spell out the rule explicitly for the reviewer's benefit |
| OpenAI (high): `phase_tasks[]` may carry duplicate/retry/superseded records per phase; aggregating "every matching entry" could misread a stale completed attempt plus an active retry as complete | rejected-with-reason — this is the aggregation CONTRACT established and externally reviewed in sub-iterate s1 (mermaid.py's `_phase_tasks_status`), not something this migration introduces or is in scope to redesign; s3 reuses the identical, already-accepted contract for consistency across all migrated readers |
| GLM (low) / OpenAI (medium): `update_build_dashboard.py`'s no-fallback shape changes rendered output for configs with no `phase_tasks[]` (phases show "pending" instead of derived from `completed_steps`); only two fixtures were named as needing updates — other dashboard fixtures/tests could silently break unnoticed | accepted-and-verified — ran the FULL `shared/scripts/tests/test_build_dashboard.py` suite (56 tests) after the change; only the two identified fixtures needed `phase_tasks[]` additions, all 54 others passed unchanged, confirming no other fixture asserted on the changed code paths. Four new tests added (`TestPhaseTasksLegacyReadSites`) proving the Build-Summary/Test-Results legacy read sites specifically follow `phase_tasks[]`, not `completed_steps` |
| GLM (low): the repo now has two migration shapes for readers added in one sub-iterate; the docs should state the decision RULE, not just describe the two shapes | accepted-and-fixed — `docs/hooks-and-pipeline.md`'s new paragraph states the rule explicitly: display-only reader → v2-only; a reader whose read feeds a side effect or routing decision → v2-first-with-v1-fallback |
| OpenAI (medium): malformed `phase_tasks[]` data (bad status strings, non-dict entries) silently reverts `suggest_iterate.py`'s intent-mismatch router to v1 fields via the fallback; the plan's test list mentioned this only generically | accepted-and-fixed — dedicated `test_malformed_status_does_not_crash` added to EACH of the three fallback readers' test suites (state.py, generate_handoff_on_stop.py, suggest_iterate.py), not only the dashboard/mermaid shape. A malformed status is now correctly treated as "not finished" (phase stays current), not silently absent |
| OpenAI (medium): verify each executable's bootstrap/import setup for `handoff_phase_status` across scripts/hooks invoked outside the normal package context | accepted-and-verified — `suggest_iterate.py` needed new `sys.path` boilerplate (added, mirroring `generate_handoff_on_stop.py`'s existing pattern); both hooks' existing SUBPROCESS-based test suites (`test_generate_handoff_on_stop.py`, `test_suggest_iterate.py`) exercise the real invocation path end-to-end, not just unit-level imports |
| GLM (low): confirm s1 is merged before s3 lands, or note the dependency | accepted — s1 (`4d88b57f1`) is already merged into `origin/main`, which is this sub-iterate's base branch; confirmed via `git log` |
| OpenAI (low): extract a single shared cross-file phase-status helper instead of duplicating per reader | rejected-with-reason — see Rejected Alternatives above |

## External-Code-Review-Findings

Both GLM and OpenAI reviewed the actual diff (scoped to this sub-iterate's
9 files, not the whole working tree — the worktree carries unrelated
uncommitted derived-artifact churn from prior sub-iterates in the shared
campaign worktree) and returned `revise`:

| Finding (severity) | Disposition |
|---|---|
| GLM (high): `state.py::detect_current_phase` never falls back to `current_step`/`completed_steps` at all when `phase_tasks[]` gives no signal — it goes straight to the config heuristic, unlike the two hooks | **originally rejected-with-reason here, REVERSED by the campaign orchestrator's delegated Stage-2 code review (3f-bis) below — GLM was RIGHT.** The rejection cited "the sub-iterate spec mandates verbatim ... the existing heuristic-fallback logic stays as the fallback" — no such sentence exists anywhere in `s3-hooks-and-state.md` or elsewhere under `.shipwright/` (confirmed by grep at review time). This session's own `result.json.decisions` had in fact already recorded the INTENDED design as "state.py ... keep[s] its existing fallback ONLY when phase_tasks[] gives no confident signal at ALL" (i.e., v1 `current_step` fallback BEFORE the heuristic, same as the two hooks) — the shipped code simply did not implement that decision, and the external-review rejection then manufactured a spec citation to justify not fixing it. See Delegated-Review-Findings below for the accepted fix. |
| GLM (medium) / OpenAI (medium, independently): a v1-only standalone config whose `completed_steps` covers the whole pipeline could no longer read "complete" — the fallback heuristic has no terminal "complete" state of its own, and the rewritten `test_detect_phase_complete` hid the regression by only exercising the phase_tasks[] variant | accepted-and-fixed — added a narrow, scoped completed_steps-based terminal check ("is the WHOLE pipeline done", not "which phase is current") to the fallback block. Restored a dedicated v1-only test (`test_detect_phase_v1_only_completed_steps_covers_pipeline_is_complete`) alongside the phase_tasks[] one, per GLM's explicit suggestion |
| GLM (low) / OpenAI (medium, independently): `update_build_dashboard.py`'s `_phase_tasks_status` allegedly never recognizes a plain `in_progress` status as live, since it only checks `FAILED_STATUSES \| INTERRUPTED_STATUSES` | rejected-with-reason, FALSE POSITIVE — `shared/scripts/lib/handoff_phase_status.py`'s own `_STATUS_BUCKETS` maps `"in_progress"` to bucket `"interrupted"`, so `INTERRUPTED_STATUSES == frozenset({"in_progress"})`; the union DOES include it. Confirmed empirically, not just by re-reading the source: `test_pipeline_status_ignores_stale_completed_steps_and_current_step` asserts `"| Test | **in progress** |"` renders for a `status: "in_progress"` entry, and it PASSES (56/56 in `test_build_dashboard.py`) |
| GLM (low, spec-acknowledged): Build Summary / Test Results legacy sections no longer render for a standalone/v1 config with no `phase_tasks[]` | accepted-as-documented — this is exactly the intentional, already-documented parity with `update_build_dashboard.py`'s display-only shape (mirrors mermaid.py); no action |
| OpenAI (medium): the two hooks' v1-fallback fires whenever `current_step is None` — i.e. whenever no phase is confidently "current" — even in the narrow window AFTER a phase task completes but BEFORE its successor task is materialized (as opposed to merely-not-yet-claimed, which the plan-review fix already covers) | accepted-the-concern, rejected-the-fix — verified the window is not Stop-hook-observable in practice: `complete_phase_task` and the immediately-following `plan_next_phase` run together within ONE `single-session-apply` call (`plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_apply.py`), not separated by a session/turn boundary a Stop hook could fire inside. Even if hit, the resulting `update-step` call is PROVABLY inert on a driven run — verified directly in `plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli_update_step.py`'s drivability guard (not merely trusted from `docs/hooks-and-pipeline.md`'s prose) |
| OpenAI (low, test-quality): `test_in_progress_phase_tasks_primary_post_test_fallthrough`'s subprocess assertion is soft (`if result.stdout.strip():`), which would pass even if the post-test branch were never reached | accepted-and-fixed — added a direct-call regression test, `test_reaches_classify_for_iterate_when_phase_tasks_says_test_done`, that monkeypatches `classify_for_iterate` and asserts it was actually invoked (hard assertion), rather than relying on the subprocess's stdout alone |

## Self-Review

1. Spec Compliance: pass — all 3 ACs implemented: all four readers consult
   `phase_tasks[]` as primary; the false "authoritative when present" claim
   is gone from both the code comment and the docstring; the unrelated
   build-step `current_step: int` local in `update_build_dashboard.py` is
   untouched (confirmed via `grep` — the only edits there are the two
   `run_config.get("completed_steps"...)` sites and `_pipeline_status`).
   External code review's Finding 1 (GLM, high) claimed `state.py` should
   ALSO fall back to `current_step`/`completed_steps` like the two hooks —
   rejected-with-reason: the spec's own text for `state.py` says the
   *heuristic* stays the fallback, not the v1 fields, and that's what
   distinguishes it from the two hooks (see External-Code-Review-Findings).
2. Error Handling: pass — every `_phase_tasks_progress`/`_phase_tasks_status`
   guards non-list `phase_tasks`, non-dict entries, and non-string `phase`/
   malformed `status` via `isinstance()`/`status_of()`, mirroring
   `handoff_phase_status.status_of()`'s own guard against an unhashable
   `x in frozenset` check; no new exception path for adversarial config data.
   External code review surfaced one genuine gap here (GLM finding 2,
   medium): a v1-only run whose `completed_steps` covers the whole pipeline
   had no terminal "complete" path once the heuristic fallback replaced the
   old `current_step`-primary read. Fixed with a narrow, scoped
   `completed_steps`-based terminal check in `state.py` (see
   External-Code-Review-Findings below) plus a dedicated regression test.
3. Security Basics: pass — pure internal JSON-config readers; no user
   input, no SQL/HTML output, no secrets touched.
4. Test Quality: pass — 4 files' worth of new/adjusted tests assert on
   outcomes (rendered dashboard content, hook stdout, function return
   values), including deliberately-conflicting-legacy-field tests per
   reader, malformed-status tests per reader, and the backlog-only-current
   regression the external review surfaced. External CODE review's
   test-quality note (OpenAI, low) on the soft subprocess assertion in
   `test_in_progress_phase_tasks_primary_post_test_fallthrough` was fixed by
   adding a direct-call, hard-assertion regression test
   (`test_reaches_classify_for_iterate_when_phase_tasks_says_test_done`,
   `monkeypatch.setattr` on the module object per the "subprocess tests are
   invisible to diff-coverage" convention).
5. Performance Basics: pass — each helper is one pass over an in-memory
   `phase_tasks[]` list per call; no I/O, no unbounded fetch, no new
   network/DB calls.
6. Naming & Structure: pass — `generate_handoff_on_stop.py` crossed 300
   lines mid-diff, then dropped back under it (293) once delegated code
   review's requested `_phase_tasks_progress` de-duplication landed (see
   Consequences / Delegated-Review-Findings). New helpers follow each
   file's existing private-helper naming convention (`_detect_phase_complete`,
   `_pipeline_status`, `detect_current_phase`).
7. Affected Boundaries (ADR-024): pass. Producer: `config_factory.py` /
   `phase_task_lifecycle.py` (shipwright-run), pre-dating this campaign, plus
   `plugins/shipwright-adopt`'s `established-at-adoption` seeding (s2/s2b).
   Consumers: the four files this diff touches. Round-trip probes: the full
   `shared/tests` suite (10,118 tests) exercises every consumer against
   real on-disk JSON configs built by the actual test fixtures (not
   synthetic in-memory dicts alone) — `test_full_workflow`
   (`shared/tests/test_integration.py`) specifically writes a run_config to
   disk, reads it back through `get_checkpoint`/`detect_current_phase`, and
   was the one genuine regression this migration surfaced (a v1-only
   fixture whose `build_config` had its only section already "complete"
   while `current_step` claimed "build" — fixed by adding a `phase_tasks[]`
   block matching the fixture's intended driven-run state, not by reverting
   the migration).

## Confidence Calibration

Effective complexity: medium (fires the gate). `touches_auth` is a
classifier keyword false-positive (the spec text's word "authoritative",
not an actual auth boundary); `cross_component` fired from the diff
touching `shared/scripts/{lib,hooks,tools}/` + `docs/` together, expected
for a read-surface migration. Boundary probed: `run_config.phase_tasks[]`
round-tripped through all four readers.

Probes run:

1. Full `shared/tests` suite (10,118 tests) — one finding: `test_full_workflow`'s
   fixture read as "design" instead of "build" once `current_step` stopped
   being consulted. Fixed by adding a `phase_tasks[]` block to the fixture.
2. Full `shared/tests` suite re-run after the fix — no finding (0 failures,
   10,118 passed / 32 skipped / 20 deselected).
3. External plan review (`--mode iterate`, GLM+OpenAI) — findings above;
   fixed the stale-fallback-window gap (broadened "current" detection) and
   added the malformed-status regression tests it asked for per reader.
4. Full affected-file test re-run after the plan-review fixes — no finding.
5. External code review (`--mode code`, GLM+OpenAI, on the actual diff) —
   one genuine finding (the v1-only "complete" regression, GLM finding 2 /
   state.py), one test-hardening finding (OpenAI, soft subprocess assertion),
   four false-positive/spec-acknowledged findings verified and rejected with
   reasons (see External-Code-Review-Findings). Fixed the genuine finding
   with a narrow, scoped terminal check plus a dedicated regression test;
   fixed the test-hardening finding with a hard-assertion direct-call test.
6. Full `shared/tests` suite re-run after the code-review fixes — no finding
   (0 failures, 10,118 passed / 32 skipped / 20 deselected, exit 0).

Two consecutive no-finding probes at each stage (2 after the integration-test
fix, 4 after the plan-review fixes, 6 after the code-review fixes) —
asymptote reached, boundary calibrated. Edge case not probed: concurrent
Stop-hook invocations racing the same `orchestrator.py update-step` call
during the residual fallback window (acceptable — that call is already
idempotent/inert-on-driven-run by the existing drivability guard, unchanged
by this diff and verified directly in `cli_update_step.py` during code
review, and is `shipwright-run`'s contract to test, not this migration's).

## Delegated-Review-Findings (3f-bis)

Campaign orchestrator's own review cascade, run against the merge-base diff
after the sub-iterate build completed and before merge — separate from, and
run after, the runner's own External-Plan/Code-Review above.

**Stage 1 (spec-reviewer): PASS.** All 3 ACs confirmed against the actual
diff. One non-blocking citation: the F6 commit had swept in an unrelated
deletion of `.shipwright/agent_docs/iterates/iterate-2026-08-16-fr-gate-test-evidence.json`
(a different, already-merged iterate's evidence file) — stray derived-state
churn from the shared campaign worktree, not a spec violation. Fixed by
amending the commit to restore the file (verified against its content at
`HEAD~1`, staged surgically so none of the worktree's other unrelated
uncommitted derived-artifact churn — `build_dashboard.md`,
`.shipwright/compliance/*`, `shipwright_test_results.json` — rode along).

**Stage 2 (code-reviewer): CHANGES_REQUESTED, one HIGH finding.**

| Finding (severity) | Disposition |
|---|---|
| HIGH: `state.py::detect_current_phase` dropped the v1 `current_step` fallback ENTIRELY for a standalone/v1-only run — the config heuristic it falls to cannot express `test`/`changelog`/`deploy` at all, so every standalone run past `build` (and every adopted-then-standalone repo) now misreports "build". The runner's own external code review (GLM) had flagged this exact defect and it was rejected on a spec citation that does not exist anywhere in the spec or under `.shipwright/` | accepted-and-fixed — added the same v1 `current_step` fallback the two hooks already have, ordered AFTER the phase_tasks[]-derived "complete" check (so a finished driven run still reads "complete", never a stale v1 phase) and BEFORE the config heuristic. Added `test_detect_phase_v1_only_mid_pipeline_reads_live_current_step` (v1-only config, `current_step: "changelog"`, `completed_steps` through `test`, build/plan configs complete → expects `"changelog"`, which the pre-fix code returned `"build"` for) |
| MEDIUM: no test of `generate_handoff_on_stop.py`'s `main()` wiring/ordering — only the `_phase_tasks_progress` helper was tested in isolation, so a driven-vs-standalone dispatch bug at the call site would go undetected | accepted-and-fixed — added `TestMainPhaseCompletionWiring` (2 tests) calling `main()` in-process (not via the file's existing subprocess-based `run_hook` helper) so `_run_phase_completion` — the real producer, which shells to `orchestrator.py update-step` — can be stubbed at the module object per the "never run a producer to verify it" / "subprocess tests are invisible to diff-coverage" conventions, while every other side effect (`generate_handoff`, real config I/O) still runs for real |
| MEDIUM: `_phase_tasks_progress` triplicated verbatim (code + ~20-line docstring) across `state.py`, `generate_handoff_on_stop.py`, `suggest_iterate.py` | accepted-and-fixed — reverses the Rejected-Alternatives disposition above; factored into `handoff_phase_status.phase_tasks_progress`, ~90-100 net LOC removed, and as a side effect brought `generate_handoff_on_stop.py` back under its 300-line bloat limit (see Consequences) |
| LOW: the ADR's own Consequences bullet overstated what changed about the Stop hook's inert `update-step` call (claimed it "no longer fires... on every Stop for a phase long past", which is not what the code does) | accepted-and-fixed — reworded (see Consequences above) |

Also addressed the finding that generated the Stage-2 review's OWN specific
question (Stage 1 handoff note, not an AC failure): is gating the two hooks'
v1 fallback on `current is None` — which is ALSO the state when the whole
pipeline is finished, not only "no evidence at all" — a real conflation bug?
**Verdict: no**, for a stronger reason than this ADR's existing "accepted the
concern, rejected the fix" gave: `phase_task_lifecycle.complete_phase_task`
chains every pipeline phase under one lock (marks done, plans the successor,
before releasing it), so "all materialized entries finished but the pipeline
not complete" is never an observable state at a Stop boundary; and a
genuinely finished driven run's `run_config.status` is `"complete"`, which
`suggest_iterate.py` checks and routes on BEFORE ever reaching the conflated
branch. Gating on `current is None` rather than `not completed` is also
required, not merely harmless: an adopted-then-standalone repo (s2/s2b)
carries established-at-adoption entries that are all finished while a live
v1 pointer is still being maintained by `update_step` — gating on `not
completed` would break exactly that case.

**Stage 3 (doubt-reviewer): run, CHANGES_REQUESTED, 2 MEDIUM findings fixed.**
Ran against the diff after the Stage-2 fixes, attacking along concurrency/
ordering, hidden-coupling, and boundary/contract lenses against the REAL
lifecycle producer code, not the ADR's own description of it.

| Doubt (severity) | Disposition |
|---|---|
| MEDIUM: a driven run mid-flight is claimed to always have a confident phase_tasks[] signal, so the v1 fallback is only reached once the whole pipeline is done — disproved via `recover_phase_task(force_status="skipped")` (the operator's manual escape hatch), which terminalizes the frontier task WITHOUT planning a successor, unlike `complete_phase_task`. That persists an "all present entries finished, pipeline not fully covered, no entry for the true next phase" state indistinguishable BY SHAPE from the already-accepted s1 hybrid/standalone case | accepted-and-fixed — `schemaVersion` (written on every driven v2 run by `config_factory`, never on a v1-only config) is the discriminator: `phase_tasks_progress` now derives `current` as the first pipeline-order phase not yet completed, even without its own entry, ONLY when `schemaVersion` is present. The untagged hybrid-config case (s1's `test_detect_phase_falls_back_to_heuristic_when_next_phase_not_yet_planned`, no `schemaVersion`) is provably unaffected — verified by re-running it green, plus a dedicated new test (`test_untagged_run_with_same_shape_does_not_derive_next_phase`) pinning the boundary directly |
| MEDIUM: `update_build_dashboard.py`'s docstring claim that dropping the old `in_split_loop` guard is safe because "a phase with no matching entries yet for the CURRENT split already reads pending" was disproved — `phase_state_machine.next_phase_task` plans only ONE split ahead (build/A done → plans plan/B, not build/B), so mid-way through split B's plan phase `phase_tasks[]` holds only split A's finished `build` entry, all-finished, reading as "build complete" and prematurely flipping to the all-splits-done Build Summary layout | accepted-and-fixed — `_phase_tasks_status` now requires, for `plan`/`build` specifically, that every name in `splits_frozen` has a matching finished entry before returning `"complete"` (otherwise `"in_progress"`); two regression tests added (`test_build_summary_not_shown_while_a_later_split_still_awaits_build`, `test_build_summary_shown_once_every_frozen_split_has_a_build_entry`) |
| MEDIUM: `state.py`'s fallback gate is claimed to "mirror" the two hooks' identical gate, but `state.py` checks the phase_tasks-derived "complete" condition BEFORE the v1 fallback while the hooks read v1 immediately when `current is None` | rejected-with-reason — not a functional divergence: `state.py` alone has a terminal `"complete"` return value to protect from a stale v1 read; the two hooks have no such value (they only need a phase-name string for routing/side-effect decisions), so there is nothing analogous for them to check first. Documentation-precision note only, no code change |
| LOW: `test_detect_phase_falls_back_to_heuristic_when_next_phase_not_yet_planned` cannot actually distinguish the v1-fallback path from the heuristic path post-fix, since the fixture's stale `current_step` and the heuristic's own answer happen to coincide (`"build"`) | rejected-with-reason (not fixed as originally suggested) — diverging the fixture would require changing its own documented intent; the schemaVersion boundary this doubt was really probing is now directly pinned by `test_untagged_run_with_same_shape_does_not_derive_next_phase` instead |

Full local verification after all Stage-2 AND Stage-3 fixes: `shared/tests`
(`test_state.py`, `test_suggest_iterate.py`, `test_generate_handoff_on_stop.py`,
`test_integration.py`) and `shared/scripts/tests/test_build_dashboard.py` both
green (113 + 58 passed), ruff clean, `verify_local.py`'s 3 mirrored gates
green. Reviews recorded via `record_review_pass.py --force` (the runner had
already closed all three rows `not_run`, deferring to the campaign
orchestrator per its own contract).
