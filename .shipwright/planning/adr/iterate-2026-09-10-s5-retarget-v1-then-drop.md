# Retarget the v1 update_step path onto phase_tasks[], then drop current_step/completed_steps

**Run-ID:** iterate-2026-09-10-s5-retarget-v1-then-drop
**Campaign:** p4-04-retire-write-once-steps, sub-iterate s5 of 6 (final)

## Context

s1/s3/s4 migrated every reader of the write-once `current_step`/
`completed_steps` fields onto `phase_tasks[]` (with a v1 fallback for
readers that were not pure display). s2/s2b gave `shipwright-adopt` its own
`phase_tasks[]` writer. What remained write-once-field-shaped was the v1
`update_step` mechanism itself (the path that serves a bare phase
invocation — no `/shipwright-run` orchestrator session) and the two
config-creation writers (`shipwright-project`'s `write_run_config.py`,
`shipwright-adopt`'s `config_writer.py`). Leaving the v1 path writing the
old fields forever would install **mode-conditional truth** — which shape
is authoritative depends on how the run was driven — into every future
reader, permanently. The spec's order: retarget the v1 path onto
`phase_tasks[]` FIRST, then delete both writers, the old field emission,
and the schema block describing them, in the same diff. "No reader
anywhere keys on `current_step`/`completed_steps`" is proven by grep, not
claimed.

## Decision

1. **v1 `update_step` now advances `phase_tasks[]` directly.** New helpers
   in `step_config_access.py` — `_find_v1_phase_task` (find the v1-owned,
   unsplit entry for a phase, by `phase` name + `splitId is None`),
   `_upsert_v1_phase_task` (find-or-create, no CAS — a bare phase
   invocation has no session/version to contend for), `_reset_v1_phase_tasks`
   (the split-retry reset, replacing the old `completed_steps` list
   surgery) — replace every `current_step =` / `completed_steps.append`
   write in `step_planning.py`. `build_v1_phase_task()` (`config_factory.py`)
   is the shared PhaseTask-shape builder both this path and the
   standalone-merge below use.
2. **`config_factory.create_config` no longer emits either field.** The
   standalone→driven merge reads `phase_tasks_progress(existing)` instead
   of `existing.get("completed_steps")`.
3. **Both remaining production writers drop the fields**:
   `shipwright-project/scripts/write_run_config.py` and
   `shipwright-adopt/scripts/lib/config_writer.py` no longer put
   `current_step`/`completed_steps` into the config dict they write
   (the `completed_steps` function *parameter* name in `config_writer.py`
   is kept — it is the caller-facing API, not the on-disk shape).
4. **Every remaining live reader drops its fallback branch.**
   `handoff_phase_status.completed_phases_with_fallback` is renamed
   `completed_phases()` and the `completed_steps`/`phase_tasks`-absent
   fallback branch is deleted outright — it now returns an empty set
   whenever `phase_tasks_has_usable_entries()` is `False`, never reading
   `completed_steps`. Every s1/s3/s4 call site (`design_checks.py`,
   `compliance_compliance.py`, `convert_configs_to_events.py`,
   `state.detect_current_phase`, `generate_handoff_on_stop.py`,
   `suggest_iterate.py`, `phase_quality._engagement`/`_resolution`) follows
   automatically through the renamed shared function.
5. **One deliberate, documented exception**: `shipwright-adopt`'s
   `adopted_phase_tasks.backfill_missing_phase_tasks()` still reads
   `completed_steps` — a one-time BACKFILL of an existing on-disk legacy
   field into `phase_tasks[]` for a pre-s2 adopted repo, not a live
   progress query. Retiring this read would make that repo's pre-adoption
   history permanently unrecoverable, not merely re-derived from elsewhere.
   Documented in the module's own docstring.
6. **One-time cutover exceptions at four boundaries**, all reading legacy
   `current_step`/`completed_steps` ONLY when `phase_tasks_has_usable_entries()`
   says there is no `phase_tasks[]` evidence at all, and only for a
   standalone config touched by the v1 `update_step` path *before* this
   sub-iterate landed: `config_factory.create_config`'s standalone→driven
   merge (added after external plan review; see External-Plan-Review-Findings),
   `generate_handoff_on_stop.py`'s Stop-hook phase-completion fallback,
   `state.detect_current_phase`, and `suggest_iterate.handle_in_progress_pipeline`
   (the latter three added after external code review round 2/3; see
   External-Code-Review-Findings). None is an ongoing reader fallback — the
   same shape `backfill_missing_phase_tasks` already uses on the adopt side.
7. **`docs/hooks-and-pipeline.md`'s schema block is rewritten in this
   diff** (AC-mandated): the fields are marked RETIRED, the v1 path's new
   `phase_tasks[]`-advancing behavior is documented, and every other
   passage referencing the old fields (Cmp1's rule, the phase-completion
   fallback note, the split-retry note, the between-phase-actions
   "Upstream Success Check" step, ~6 more) is corrected in the same pass.
   `docs/guide.md` and `shipwright-adopt`'s `artifact-templates.md`
   reference are updated alongside.

## Consequences

- `phase_tasks[]` is now the SOLE progress authority on every run shape —
  driven (`phase_task_lifecycle`), standalone/legacy/adopted (the v1 path),
  and adopted-in (shipwright-adopt's seeding).
- **Four narrow, one-time migration boundaries** exist (Decision item 6) for
  a standalone config that predates this sub-iterate: the standalone→driven
  merge, the Stop-hook self-heal trigger, and the two checkpoint/routing
  readers (`state.py`, `suggest_iterate.py`) whose wrong answer would
  otherwise persist forever for an already-FINISHED legacy run (no later
  event ever re-triggers `update-step` for a run with no more phases). Every
  OTHER reader in the tree — the large majority — carries no fallback at
  all; a config with usable `phase_tasks[]` never reaches any of these four.
- **Bloat**: baseline entries this diff grew were trimmed back to their
  recorded `current` ceiling rather than bumped, across all three review
  rounds (`test_orchestrator.py` 605, `test_audit_phase_quality.py` 820,
  `test_state.py` 360, `test_verifiers_design.py` 498,
  `test_workflow_checks.py` 607, `test_generate_handoff_on_stop.py` 559,
  `test_shipwright_run_e2e.py` 333 — all shrunk to fit, no baseline edit).
  New crossings on previously-unbaselined files (`test_runconfig_corrupt_fail_closed.py`,
  `test_validation_record_honesty.py`, `generate_handoff_on_stop.py`) were
  likewise trimmed under 300 rather than exempted. No baseline entry in this
  diff needed a `current` bump, across the whole finalization.
- `shared/scripts/lib/handoff_phase_status.py` shrinks: the fallback branch
  and its extensive review-history docstring (s4's own bloat-driving
  content) are gone along with the code path they documented.

## Rationale

Same per-reader/per-writer migration discipline s1-s4 already established,
applied to the last writers and the last (mechanism) reader. Retarget-then-
delete, not delete-then-retarget: deleting the fields first would have left
the v1 path with nowhere to record progress at all for one commit, and a
split delete-then-retarget invites exactly the half-migrated state external
review's finding #3 (below) worried about. Single diff, not two commits —
the spec's own phrasing ("Last, so the drop is mechanical") reads as
license to do it in one pass once the retarget is proven, not a mandate to
split the commit.

## Rejected Alternatives

- **Leave the v1 path writing `current_step`/`completed_steps` and have it
  ALSO write `phase_tasks[]` (dual-write) for one extra sub-iterate** —
  rejected: this is exactly the mode-conditional-truth the spec's Scope
  section names as the failure mode to avoid; a dual-write window is not
  safer, it is a second copy that can disagree with the first.
- **Keep `completed_steps` readable indefinitely as a fallback everywhere,
  never actually drop it** — rejected: the campaign exists to retire the
  fields, not merely add a second, primary source next to them forever;
  s1/s3/s4's fallback shape was always understood as transitional (see
  those sub-iterates' own ADRs), not the end state.
- **Fix the four legacy-cutover gaps (Decision item 6) by re-adding a
  general `completed_steps` fallback to `phase_tasks_progress()` itself** —
  rejected: that function is the shared primitive nearly every reader in
  the tree calls; reopening it to legacy fields would resurrect the
  mode-conditional-truth problem application-wide instead of confining the
  one-time migration to the four specific boundaries that actually need it
  (found by external code review rounds 2-3: the standalone→driven merge,
  the Stop-hook self-heal trigger, `state.py`, `suggest_iterate.py`).
- **Satisfy the AC's literal text by deleting the four one-time cutovers
  outright, accepting the permanent-deadlock / permanent-misreport
  consequence for pre-s5 configs as the cost of a clean read** — rejected
  (round 3, restated by OpenAI as HIGH at two of the four sites): the same
  two reviewers flagged the ABSENCE of these boundaries as HIGH severity in
  round 2; removing them again to satisfy the letter of the AC would just
  reopen that finding. The AC's *purpose* — no reader treats the retired
  fields as an ongoing, mode-conditional source of truth — is what a
  bounded, single-fire, on-disk-shape-gated read preserves; a permanently
  broken legacy run is not evidence the retirement succeeded.

## External-Plan-Review-Findings

Both GLM and OpenAI reviewed the sub-iterate spec (`--mode iterate`) after
the build was substantially complete (the review pass was run as part of
Step 3.5 finalization, not before the diff existed — noted as a process
deviation, not a content one; both reviews evaluated the actual spec
against the actual implementation).

| Finding (severity) | Disposition |
|---|---|
| GLM (high) / OpenAI (high, independently, same finding): no handling specified for in-flight standalone runs whose persisted state has `current_step`/`completed_steps` but no `phase_tasks[]` — a config in that shape silently loses its completed-phase history when `config_factory`'s standalone→driven merge reads `phase_tasks_progress(existing)` exclusively | accepted-and-fixed — confirmed by direct probe (an empty completed set came back for a hand-built legacy config before the fix); `config_factory.create_config` now falls back to `completed_steps` **only** at this one merge boundary, only when `phase_tasks_progress(existing)` finds nothing (Decision item 6). Regression tests: `test_legacy_completed_steps_only_config_merges_into_driven_run`, `test_a_phase_tasks_present_config_never_consults_completed_steps` (`test_standalone_merge_legacy_completed_steps.py`) |
| GLM (high) / OpenAI (high, independently): the mapping between the v1 scalar step counter and `phase_tasks[]` advancement is asserted, not verified equivalent | accepted-and-verified — `test_orchestrator_split_parity.py::test_two_phase_flow_routes_identically_post_split` and `test_orchestrator.py::test_update_step_all_complete` (all `PIPELINE_STEPS` advanced sequentially via `update_step`, asserting the full set lands in `phase_tasks_progress()`'s completed set) already exercise the multi-step sequence end to end; additionally ran a direct idempotency probe (call `update_step` for the same phase twice) confirming no duplicate `phase_tasks[]` entry is created — `_upsert_v1_phase_task`'s find-or-create is idempotent by construction |
| GLM (medium): "retarget first, then delete" doesn't say whether it's one diff or two commits | accepted-and-documented — single diff (see Rationale); the two are not independently green on `origin/main` because the retarget alone would still leave dead writers, which is not a state this campaign chooses to commit |
| GLM (medium) / OpenAI (medium, dependency, same concern): the plan names code readers/writers and one doc block but not test fixtures / exported schemas / other docs that might go stale | accepted-and-verified — grepped `**/*.md` repo-wide for `current_step`/`completed_steps`; every hit outside `docs/hooks-and-pipeline.md` (already updated), `docs/guide.md` (already updated), and `shipwright-adopt`'s two reference docs (already updated / confirmed no-change) is either a historical record (past ADRs, changelog drops, decision_log, planning specs — correctly describing a past state, not live documentation) or a generated artifact refreshed by F1/F2. `shared/schemas/*.json` never declared either field. Every non-test production `.py` file grepped clean for both keys except the two documented one-time-migration exceptions (item 5, item 6 above) |
| OpenAI (medium, edge-case): retry/concurrent `update_step` calls not addressed — could produce duplicate completion or non-monotonic state | accepted-and-verified — see the idempotency probe above; `_upsert_v1_phase_task` has no ordering dependency (status is a direct overwrite keyed by phase name), so a retry or an out-of-order call converges to the same terminal state, not a duplicate entry |
| OpenAI (medium, risk): "both writers" removed might not be exhaustive if a constructor/serializer implicitly re-adds the fields | accepted-and-verified — `grep`-confirmed no production code path constructs a dict literal containing either key; `test_write_run_config.py` and `test_config_writer.py` assert the negative (`"current_step" not in data`) directly on the writers' actual output, not just on the source |

## External-Code-Review-Findings

Ran three rounds (`--mode code`, full merge-base diff, GLM + OpenAI each
round) — each round's fixes are what the NEXT round's diff was reviewed
against, so later rounds see strictly less surface than the round before.

### Round 1

| Finding (severity) | Disposition |
|---|---|
| GLM (high): `config_factory.create_config`'s new standalone-merge fallback triggered on `not existing_completed` (empty completed set) rather than "no usable `phase_tasks[]` at all" — wrongly fired for a genuinely mid-flight v2 config, resurrecting stale `completed_steps` over a true empty-but-confident answer | accepted-and-fixed — gate switched to `not phase_tasks_has_usable_entries(existing)`; reproduced by direct trace through GLM's cited case before fixing |
| GLM (high, self-referential): the regression test guarding the above asserted only `!= "done"`, which the buggy trigger's own output (`status="skipped"`) still passed | accepted-and-fixed — `test_a_phase_tasks_present_config_never_consults_completed_steps` rewritten to assert `phase_tasks_progress(...)[1]` membership directly, not merely `!= "done"` |
| OpenAI (medium): the `needs_validation` pause branch dropped the `current_step = step` write it replaced with nothing, leaving a paused phase unrepresented in `phase_tasks[]` | accepted-and-fixed — `_upsert_v1_phase_task(config, step, "in_progress", ...)` added to that branch |
| OpenAI (medium, finding #3): a standalone-completed "project" merges as `status: "skipped"`, `executionCount: 0` — Phase-Quality's `_task_has_run` reads that as never-run | initially dispositioned pre-existing (the shape itself pre-dates s5) — **reopened in round 3** once the actual regression (removal of `_engagement.py`'s OR-fallback) was identified; see round 3 below |

### Round 2 (after round 1 fixes)

| Finding (severity) | Disposition |
|---|---|
| GLM (low): `_upsert_v1_phase_task` left a stale `completedAt` on a retry back to a non-terminal status (e.g. "in_progress" after "failed") | accepted-and-fixed — `else: existing["completedAt"] = None` added |
| GLM (low): `_reset_v1_phase_tasks` left `startedAt` set on an entry reset to "awaiting_launch" | accepted-and-fixed — `task["startedAt"] = None` added |
| GLM (high): removing the Stop-hook's (`generate_handoff_on_stop.py`) v1 fallback creates a PERMANENT deadlock for a pre-s5 legacy standalone config — this detector is the only thing that ever calls `update-step` for a standalone run, so with no signal at all it never fires, `phase_tasks[]` never gets seeded, and nothing else in the codebase would ever trigger it | accepted-and-fixed — restored a ONE-TIME legacy cutover, gated on `phase_tasks_has_usable_entries`, mirroring `config_factory.create_config`'s boundary. Regression tests: `test_v1_only_config_uses_one_time_legacy_cutover_fallback`, `test_usable_phase_tasks_never_consults_legacy_fields` (`test_generate_handoff_on_stop.py`) |
| OpenAI (high): `write_run_config.py` seeds neither `current_step` nor `phase_tasks[]` for a fresh project config, so the Stop-hook fallback has nothing to key on if Step 8's explicit `update-step --status complete` call never runs | accepted-and-fixed — seeds a minimal `phase_tasks: [{"phase": "project", "splitId": None, "status": "awaiting_launch"}]` entry, the ongoing analogue of `config_factory._build_initial_phase_task` for this second config-creation path. Test: `test_write_run_config_creates_valid_json` updated to assert the seed |
| GLM+OpenAI (medium, repeated from round 1 in spirit): the two one-time legacy-field reads (above) don't literally satisfy the AC "no reader anywhere keys on `current_step`/`completed_steps`" | rejected-with-reason — see the dedicated discussion below (round 3 restates this at HIGH; same disposition applies) |
| GLM (low): `step_planning.update_step`'s terminal-status check changed from `if not remaining` (empty pipeline reads complete) to `if pipeline and set(pipeline).issubset(completed)` (empty pipeline no longer auto-completes) | rejected-with-reason — unreachable: `pipeline = config.get("pipeline") or PIPELINE_STEPS` on the preceding line already substitutes the non-empty default for any falsy (`None`/`[]`) pipeline, so `pipeline` is provably always truthy at the check; the `pipeline and` guard is defensive-but-inert, not a behavior change |
| GLM (low): `design_checks.py`'s fail-loud conversion now returns True (assume design ran) for ANY legacy config with no usable `phase_tasks[]`, where the pre-s5 code would still trust a `completed_steps` list not containing "design" | accepted-as-intentional — this is precisely what the AC requires (zero `completed_steps` reads, not "read it unless inconvenient"); fail-loud is the safe direction (never a silent false-negative on real drift), and the module's own docstring already documents the trade-off |

### Round 3 (after round 2 fixes)

| Finding (severity) | Disposition |
|---|---|
| OpenAI (high, x2 — `config_factory.py` merge and `generate_handoff_on_stop.py` fallback, same objection restated at both sites): "no reader anywhere keys on the retired fields" is violated by the two one-time cutovers | **rejected-with-reason.** Both reads are migration BOUNDARIES, not ongoing readers: each fires at most once per pre-existing on-disk config, only when `phase_tasks_has_usable_entries()` says there is no v2 evidence whatsoever, and each write immediately makes the config v2-shaped going forward (the Stop-hook fallback's whole purpose is to TRIGGER `update-step`, which seeds `phase_tasks[]`). The AC's target — "no reader treats `current_step`/`completed_steps` as an ongoing, ambient source of truth, mode-conditionally" — is what these boundaries preserve; the literal zero-bytes-ever-read reading would require either (a) a mandatory pre-flight migration command every pre-s5 repo must remember to run (rejected in round 1's plan review for the identical reason: a silent data-loss default is worse than a narrow, documented, one-time exception), or (b) accepting the round-2 finding's own consequence — permanent deadlock / permanent misreport — as the price of AC literalism. Two independent reviewers flagged the ABSENCE of exactly this exception as HIGH in round 2; re-removing it to satisfy the literal AC text in round 3 would just reopen that same finding. This is the identical exception `adopted_phase_tasks.backfill_missing_phase_tasks` already established as accepted practice on the adopt side (Decision item 5) |
| GLM (medium): standalone-completed "project" merges with `executionCount: 0` (via `_build_initial_phase_task`, status forced to "skipped") while every OTHER standalone-completed phase gets `build_v1_phase_task(..., "done")`'s `executionCount: 1` — confirmed as an ACTUAL regression introduced by this diff (not merely the pre-existing shape flagged in round 1): `_engagement.py`'s `completed_steps`/`current_step` OR-fallback, which used to compensate for exactly this "project" asymmetry, was removed in this same diff | accepted-and-fixed — `config_factory.create_config` now stamps `initial_task["executionCount"] = 1` alongside the existing `status = "skipped"` when merging a standalone-completed "project". Regression test: `test_merged_project_engages_phase_quality_same_as_its_siblings` (`test_standalone_merge_legacy_completed_steps.py`), asserting `phase_is_engaged("project", ...) == phase_is_engaged("design", ...)` post-merge |
| GLM (medium): `state.detect_current_phase` and `suggest_iterate.handle_in_progress_pipeline` never got the one-time legacy cutover the Stop-hook and `config_factory` did — a pre-s5 FINISHED standalone run misreports "build" forever (the config-heuristic fallback can't express test/changelog/deploy), and unlike the Stop-hook path nothing ever re-triggers `update-step` for an already-finished run, so this one never self-heals | accepted-and-fixed — both readers given the identical one-time cutover (gated on `phase_tasks_has_usable_entries`). Regression tests: `test_detect_phase_v1_only_completed_steps_reports_complete_via_cutover`, `test_detect_phase_v1_only_current_step_reported_via_cutover`, `test_detect_phase_usable_phase_tasks_never_consults_legacy_fields` (`test_state.py`); `test_reaches_classify_for_iterate_via_legacy_cutover_when_no_phase_tasks` (`test_suggest_iterate.py`) |
| GLM (low): `_upsert_v1_phase_task` treated `"skipped"` as non-terminal when deciding `completedAt` — unreachable via `update_step` today (it only ever passes `in_progress`/`done`/`failed`), but the helper is exported and tested as a general API | accepted-and-fixed — `"skipped"` added to the terminal set. Test: `test_skipped_status_sets_completed_at_like_other_terminal_statuses` |
| GLM (low): `suggest_iterate`'s post-test fallback is silently dead for a legacy config (same root cause as the `state.py` finding, lower blast radius — advisory hint only) | accepted-and-fixed — same fix as the `state.py`/`suggest_iterate.py` cutover above closes this too |
| GLM (low): `test_shipwright_run_e2e.py`'s final-state assertion accepted `"skipped"` alongside `"done"` without pinning which, so a wrongly-firing skip path for a genuinely driven phase would still pass | accepted-and-fixed — assertion now pins every phase's status to exactly `"done"` (this e2e drives every phase through an explicit `update-step --status complete` call, never the standalone-merge skip shape) |

A fourth review round was not run: every round-3 finding is now either fixed
(5 of 7) or a repeat of an already-argued rejection (2 of 7, both restating
the same AC-literalism objection this ADR now documents at length) — running
a fourth round would re-surface only that same disagreement, not new
evidence. The delegated internal cascade (Stage 1-3, 3f-bis) is the
code-level review of record beyond this point — see Delegated-Review-Findings.

## Self-Review

1. **Spec Compliance**: pass — all four ACs verified directly: (1) v1
   `update_step` advances `phase_tasks[]` via `_upsert_v1_phase_task`
   before any field removal, pinned by
   `test_standalone_merge_legacy_completed_steps.py` and the existing
   `test_orchestrator*.py` suites; (2) `grep`-confirmed no production
   reader keys on either field except five documented one-time exceptions
   (adopt's backfill, plus the four cutovers external review surfaced:
   the standalone-merge, the Stop-hook trigger, `state.py`,
   `suggest_iterate.py`), all migration boundaries reading legacy on-disk
   data once, never live progress queries — see External-Code-Review-Findings
   round 3 for why the literal zero-reads alternative was rejected; (3)
   `grep`-confirmed no production writer emits either key; (4)
   `docs/hooks-and-pipeline.md`'s schema block rewritten in this diff,
   verified by direct read of the diff.
2. **Error Handling**: pass — `_upsert_v1_phase_task` guards a non-list
   `phase_tasks` by replacing it with a fresh list rather than crashing on
   `.append`; the new standalone-merge fallback guards a non-list or
   non-string-entry `completed_steps` the same way
   `backfill_missing_phase_tasks` does (`isinstance` checks, skip rather
   than crash).
3. **Security Basics**: pass — no new external input surface; both changed
   writers and the retargeted reader already operated on
   `shipwright_run_config.json`, a local file this process already trusted.
4. **Test Quality**: pass — every production file change in this diff has
   a corresponding test-fixture change proving the OLD assertion is now
   false and the NEW one true (not merely "still passes"); each of the
   three review rounds' fixes shipped with a regression test asserting the
   fixed behavior directly (e.g. `phase_is_engaged("project", ...) ==
   phase_is_engaged("design", ...)`, not just "no crash"). Full suite green
   after all three rounds' fixes: shipwright-run (567), shipwright-project
   (64), shipwright-compliance (1689), shared/tests (10150), integration-tests
   (full run in flight at ADR authoring — see finalization log for the
   final count).
5. **Performance Basics**: pass — no new loops over unbounded data;
   `phase_tasks[]` and `completed_steps` are both small, bounded per-run
   lists; the new fallback is a single pass over an already-in-memory list,
   only on the standalone→driven merge path (not a hot loop).
6. **Naming & Structure**: pass — `completed_phases_with_fallback` renamed
   to `completed_phases` (the name it earned once the fallback it was
   named for is deleted); `_find_v1_phase_task`/`_upsert_v1_phase_task`/
   `_reset_v1_phase_tasks` live in `step_config_access.py` alongside the
   other v1-shape helpers, not `step_planning.py` (bloat-budget reasons,
   documented in that module's own header).
7. **Affected Boundaries (ADR-024)**: pass. Producers of `phase_tasks[]`:
   `phase_task_lifecycle.py` (driven CAS lifecycle), the v1 path
   (`step_config_access.py`, this diff), `shipwright-adopt`'s
   `adopted_phase_tasks.py` (adoption-time seed + backfill), and
   `config_factory.create_config`'s standalone-merge (this diff).
   Consumers: every file this diff and s1/s3/s4 touched, plus — surfaced by
   the review cascade, not the initial pass — `phase_quality._engagement`
   (Phase-Quality audit coverage) and the checkpoint/routing pair
   (`state.py`, `suggest_iterate.py`), all reading via the shared
   `handoff_phase_status.py` primitives. Round-trip probes: ran direct
   producer→file→consumer probes for every new code path across all three
   review rounds (the legacy-merge fallback, the idempotent-retry path, the
   Phase-Quality engagement asymmetry, the state.py/suggest_iterate.py
   cutovers) against hand-built configs mirroring the exact on-disk shapes
   each writer produces, not only unit-level fixtures.

## Confidence Calibration

Fires: effective complexity (Step 3.4 diff-driven re-check) is `medium`
(upgraded from Stage-1 `small`, `cross_component` risk flag from the diff
itself, `touches_auth`/`touches_migrations` from the spec-text classifier —
diff size 1587 LOC across 54 files). Boundaries touched: `shipwright_run_config.json`
(read/write, both the v1 path and the standalone→driven merge), the
`phase_tasks[]` producer/consumer contract shared with every reader s1-s4
already migrated.

Probes run (asymptote heuristic):

1. **Idempotent-retry probe** (`update_step` called twice for the same
   phase) — no finding: confirmed no duplicate `phase_tasks[]` entry.
2. **Legacy standalone-merge probe** (a hand-built pre-s5-shaped config,
   `completed_steps` only, no `phase_tasks[]`) — **finding**: history was
   silently dropped on merge. Fixed (Decision item 6). Re-probed after the
   fix — no finding: history now recovered.
3. **Present-but-empty `phase_tasks[]` probe** (a config with a
   materialized but non-terminal `phase_tasks[]` entry AND a disagreeing
   stale `completed_steps`) — no finding: the fallback correctly does not
   fire (`phase_tasks_progress` returns a non-empty-signal answer even
   when the completed set itself is empty, per s4's own precision-tuned
   trigger, which this diff's fallback reuses unchanged).

Two consecutive no-finding probes after the one real finding was fixed —
asymptote reached; boundary calibrated. Edge case not probed: a
`phase_tasks[]` that is present but every entry is malformed (no usable
entry at all) landing on the NEW standalone-merge fallback specifically —
not probed directly, but covered by the same
`phase_tasks_has_usable_entries`-adjacent logic `phase_tasks_progress()`
already applies uniformly (s4's own probing already covers that predicate
in the shared function every caller, including this new one, goes through).

## Delegated-Review-Findings (3f-bis)

The runner's own tools cannot spawn subagents (`reviews.code:
delegated_to_orchestrator`, `reviews.spec`/`reviews.doubt` unset by the
runner); the campaign orchestrator ran the full internal cascade before
merge, per `campaign-mode.md` 3f-bis.

**Stage 1 (spec-reviewer, HARD-GATE): PASS.** All four ACs verified present,
faithfully implemented, and directly tested. AC2 in particular was judged
explicitly: the four one-time legacy-cutover reads (beyond the pre-existing,
unchanged `adopted_phase_tasks.backfill_missing_phase_tasks` exception) were
found faithful to AC2's intent — no mode-conditional ongoing fallback, only a
self-healing read gated strictly on `phase_tasks_has_usable_entries()` being
False for a config the v1 path touched before this sub-iterate — not
undisclosed scope drift, given how exhaustively they are documented in this
ADR's own Decision/Rejected-Alternatives/External-Code-Review-Findings
sections and pinned by regression tests.

**Stage 2 (code-reviewer): CHANGES_REQUESTED, both fixed.**

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | `write_run_config.py`'s new `phase_tasks[]` seed (`{"phase": "project", "splitId": None, "status": "awaiting_launch"}`) omitted every `PhaseTask.required` field beyond `phase`/`splitId`/`status` (`phaseTaskId`, `sessionUuid`, `version`, `title`, `slashCommand`, `prerequisites`, `executionCount`, `createdAt`) — `_upsert_v1_phase_task` only ever mutates `status`/`startedAt`/`completedAt` on a match, so the incomplete shape would have persisted for the life of the run, unlike every other `phase_tasks[]` producer this campaign's writers use | medium | fixed — added `_build_v1_style_phase_task_seed(now)` in `write_run_config.py`, duplicating `build_v1_phase_task`'s full field set locally (ADR-045 cross-plugin `lib`-namespace collision, the same tradeoff `adopted_phase_tasks.py` documents for the reverse direction). Test updated to assert every `PhaseTask.required` field is present. |
| 2 | `legacy_migration.py`'s docstring still said "`completed_steps` is left untouched" — a stale reference to a field this same diff retires everywhere else, inconsistent with `constants.py`'s already-updated phrasing | low | fixed — reworded to describe both `phase_tasks[]` (driven run) and `completed_steps` (pre-campaign config) as the historical record this function leaves untouched, matching `constants.py`'s phrasing. |

Also confirmed (code-reviewer, explicitly investigated): all 4 file deletions
in the diff are legitimate — 3 are the pre-existing `ITERATE_RETENTION`
pruning mechanism in `append_iterate_entry.py` (unrelated to this sub-iterate,
not an accidental deletion), and 1 is a legitimate rename
(`test_handoff_phase_status_fallback.py` →
`test_handoff_phase_status_completed_phases.py`) — the stray-deletion bug
class found in s3 and s4 does NOT recur here.

Full verification after both fixes: targeted tests (13 + 15 passed), both
plugins' full suites (`shipwright-run`: 568 passed, `shipwright-project`: 64
passed), ruff clean.

**Stage 3 (doubt-reviewer, adversarial, 2 rounds): 1 REAL high (round 1,
fixed), then 1 REAL high + 1 REAL medium (round 2, both fixed).**

Round 1 doubt: `generate_handoff_on_stop.py`'s one-time legacy
`current_step`/`completed_steps` cutover seeded a `phase_tasks[]` entry for
only the ONE phase it detected as just-completed (via `update-step`),
permanently losing every OTHER phase recovered from `completed_steps` the
moment `phase_tasks_has_usable_entries()` next read True and the cutover
self-disabled. **REAL, high.** Fixed: a new `_seed_legacy_phase_task_history`
writes full-shape `done` `phase_tasks[]` entries for every historical phase
recovered from `completed_steps`, before the existing `update-step` call
handles the currently-detected phase.

That fix was re-reviewed adversarially (round 2), which found the fix itself
introduced a narrower version of the same failure class, plus a separate
concurrency gap:

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | The round-1 fix seeded ONLY the historical phases. If the currently-detected phase was NOT yet actually complete at cutover time (the common case — a Stop event fires many times mid-phase, not only at the instant of completion), the historical-only seed alone could flip `phase_tasks_has_usable_entries()` True — self-disabling the cutover — before the in-flight phase itself ever got a `phase_tasks[]` entry, permanently orphaning it forever: the identical "cutover never fires again" deadlock this whole mechanism exists to prevent, just relocated from the historical phases onto the current one | high | fixed — `_seed_legacy_phase_task_history` now also seeds an `in_progress` entry for `current_phase` itself (not just the historical `done` entries) whenever it lacks one. If the phase also completes in the same invocation, the existing `update-step` call finds this seed by its usual `phase` + `splitId=None` match and upgrades it to `done` in place; if not, a later Stop event resolves it as current via the ordinary `phase_tasks[]` path (the cutover having correctly, permanently disabled itself). New regression test `test_legacy_cutover_seeds_current_phase_to_avoid_orphaning_it` drives two simulated Stop events and asserts the phase is picked up on the second one. |
| 2 | The seed write was a bare, unlocked `Path.write_text` against `shipwright_run_config.json` — the one file in this codebase every other writer (`config_io.save_run_config`, `phase_task_lifecycle`) treats as lock-and-atomic-write-protected (`config_io.py`'s own docstring: "the advisory run-config lock ... is held by callers"). A killed Stop hook mid-write, or a race with a concurrent `update-step` subprocess, could corrupt the file or lose a write | medium | fixed — the seed now runs under `lib.file_lock` on the same `shipwright_run_config.json.lock` path every other writer coordinates through, using `lib.atomic_write.durable_atomic_write` (tmp + fsync + `os.replace`) instead of a bare `write_text`, and re-reads the config fresh under the lock rather than reusing a copy read before the lock was taken. Both helpers are genuinely shared (`shared/scripts/lib/`), not plugin-local, so no ADR-045 boundary issue — unlike the `phase_tasks[]`-shape duplication elsewhere in this diff, which IS a plugin-local boundary and stays duplicated. |

Full verification after both round-2 fixes: `shared/tests/test_generate_handoff_on_stop.py`
(24 passed, including both new regression tests), `shared/tests/` full suite
and `shipwright-run`'s full plugin suite re-run green, ruff clean.

**Stage 4 (PR-review-gate Tier-3, `openai/gpt-5.6-luna`, sensitive-path
trigger): BLOCK, fixed.** `shared/scripts/lib/state.py`'s legacy cutover
(`detect_current_phase`) built `set(run.get("completed_steps", []))`
directly from the raw config value; an unhashable entry (a dict, from a
corrupted or hand-edited legacy config) raised `TypeError` and crashed
instead of degrading, unlike every other `completed_steps` reader in this
diff, which all filter to string entries first. Fixed to match: `legacy_
completed = {s for s in legacy_steps if isinstance(s, str)} if isinstance
(legacy_steps, list) else set()`. New regression test
`test_detect_phase_malformed_completed_steps_entry_does_not_crash` asserts
a `completed_steps` list mixing a valid string with a dict entry degrades
to the heuristic fallback instead of raising. Confirmed by grep this was the
only unguarded `set(...get("completed_steps"...))` construction in the
diff. Verification: `test_state.py` 28 passed, `shared/tests/` full suite
re-run green (10156 passed, 32 skipped), `verify_local.py` green, ruff clean.
