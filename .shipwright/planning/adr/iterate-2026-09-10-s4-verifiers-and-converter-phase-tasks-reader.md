# ADR: design_checks.py, compliance_compliance.py, and convert_configs_to_events.py move to phase_tasks[]

**Run-ID:** iterate-2026-09-10-s4-verifiers-and-converter
**Campaign:** p4-04-retire-write-once-steps, sub-iterate s4 of 6 (verifiers-and-converter)

## Context

Continuing the per-reader migration campaign (s1 migrated the dashboard
phase strip; s3 migrated the two stop-hooks, `update_build_dashboard.py`,
and `state.py`). Three remaining readers key their progress signal on the
write-once `current_step`/`completed_steps` fields, which `config_factory`
stamps once at run creation and the v2 `phase_tasks[]` lifecycle never
advances on a driven run:

1. `shared/scripts/tools/verifiers/design_checks.py::_design_phase_ran` —
   the adopted-repo design-skip gate: reads `"design" in completed_steps`
   to decide whether a missing design manifest is structural (design never
   ran, e.g. an adopted repo) or real drift (design ran, manifest lost).
2. `shared/scripts/tools/verifiers/compliance_compliance.py::check_cmp1_dashboard_covers_phases`
   (Cmp1) — a Tier-2 heuristic comparing `completed_steps` against
   `.shipwright/compliance/dashboard.md`'s text.
3. `shared/scripts/tools/convert_configs_to_events.py::convert` — the
   one-time config→events migration tool, which emits a `phase_completed`
   event per pipeline phase found in `completed_steps`.

The spec's one hard constraint: since sub-iterate s2/s2b,
`shipwright-adopt` seeds `phase_tasks[]` with a terminal (`done`/`skipped`)
entry per `project`/`plan`/`build`/`test` — never `design` — so
`design_checks.py`'s adopted-repo skip must still fire once it reads
`phase_tasks[]` instead of `completed_steps` alone.

## Decision

All three now read `phase_tasks[]` first, falling back to
`completed_steps` only when `phase_tasks[]` is absent or malformed — the
same phase_tasks[]-primary + v1-fallback shape s3 established for
`state.py`/`generate_handoff_on_stop.py`/`suggest_iterate.py` (none of
these three is a pure display reader like `mermaid.py`/
`update_build_dashboard.py`, so the "reads `phase_tasks[]` only" shape does
not apply — see `docs/hooks-and-pipeline.md`'s updated SSoT paragraph).

The precise fallback TRIGGER was revised mid-sub-iterate after external
plan review (GLM + OpenAI, independently, same finding, HIGH severity): the
original mini-plan triggered the `completed_steps` fallback whenever
`phase_tasks_progress()`'s completed set was **empty**, which conflates two
different states — "no usable `phase_tasks[]` data at all" (genuinely no
signal) and "a valid, present `phase_tasks[]` where nothing has finished
YET" (a driven run mid-flight, where the empty set IS the authoritative
answer). The fix: the fallback now triggers only when the `phase_tasks`
key itself is absent or not a list — never merely because its derived
completed set happens to be empty.

All three call sites route through one new shared function,
`shared/scripts/lib/handoff_phase_status.py::completed_phases_with_fallback`
— consolidating what the mini-plan had proposed as three separate private
`_completed_phases()` helpers, per a second independent finding from both
reviewers (medium: three copies of the same rule risk drifting).

A phase counts as completed here when EVERY matching `phase_tasks[]` entry
is `done` OR `skipped` (`FINISHED_STATUSES`) — `skipped` folds in exactly
like it already did in `completed_steps` pre-migration (`config_factory`
lists a standalone-skipped phase, e.g. `test` with no CI, in
`completed_steps` the same as one that actually ran), so none of these
three readers becomes stricter than before the migration.

## Consequences

- `design_checks.py`'s adopted-repo design-skip fires from `phase_tasks[]`
  alone for a post-s2/s2b adopted repo, without ever reading
  `completed_steps` — the adopted seed's `completed` set is `{project,
  plan, build, test}`, non-empty and confident, and `design` is absent
  from it by construction (adopt never seeds a `design` entry).
- Cmp1 (`compliance_compliance.py`) and the one-time migration tool
  (`convert_configs_to_events.py`) no longer under-report a driven run's
  real progress against a stale, inert `completed_steps` snapshot.
- `docs/hooks-and-pipeline.md`'s write-once-fields SSoT paragraph is
  updated in the same diff (repo rule): the "reader migrated by this
  campaign reads `phase_tasks[]` only" generalization is corrected — that
  shape is reserved for the two pure-display readers (s1, s3's
  `update_build_dashboard.py`); every other migrated reader (s3's other
  three, s4's three) keeps the v1 fallback, now precision-tuned per the
  Decision above.
- **Bloat: two already-grandfathered test files this diff grew further
  bump their baseline `current`** (no new file crossed a limit for the
  first time): `shared/tests/test_verifiers_design.py` 405→479,
  `shared/tests/test_workflow_checks.py` 563→607.

## Rationale

Same architecture-approved per-reader migration as s1/s3 (2026-09-06,
GPT+GLM APPROVE). The fallback-trigger precision fix is not a design
reversal — it makes the already-intended "no confident signal" condition
match what s3 itself actually needed (s3's own three fallback readers
already require `phase_tasks[]` to be materialized before treating a
frontier phase as "current"; this sub-iterate's fix makes the analogous
"is anything finished yet" question equally precise for a plain completed-
phases *set*, not just a *current phase* pointer).

## Rejected Alternatives

- **Skip only when `phase_tasks[]` contains a terminal `design` entry with
  status `skipped`, per GLM's literal suggested fix** — not adopted as
  worded: an adopted repo's `phase_tasks[]` never contains a `design` entry
  AT ALL (not even a `skipped` one), so requiring one would break the AC
  this sub-iterate exists to preserve. The adopted implemented rule —
  "design" absent from the phase_tasks[]-derived completed set — already
  covers both cases GLM's finding actually cared about (mid-flight pending
  vs. genuinely never-seeded), once the fallback-trigger fix (below) closed
  the real gap GLM's example depended on.
- **Construct the adopted-repo regression test by importing
  `shipwright-adopt`'s actual `build_adopted_phase_task`** (external plan
  review, low-severity dependency finding) — rejected-with-reason:
  cross-plugin import would collide under the ADR-045 `lib`-namespace rule
  (`adopted_phase_tasks.py`'s own docstring already documents this
  constraint for the reverse direction). The test fixture instead
  hand-builds the exact documented shape (`phase`/`status`/
  `establishedAtAdoption`); a shape drift in a future adopt change would
  already be caught by s2/s2b's own tests pinning that shape, which this
  migration does not own.
- **Treat malformed `phase_tasks[]`/`completed_steps` entries (non-dict,
  non-string) as a NEW risk this sub-iterate must design for** (external
  plan review, low-severity edge-case finding) — rejected-with-reason,
  already covered: `phase_tasks_progress()`'s existing guards (`status_of()`,
  `isinstance()` checks) predate this sub-iterate and are unchanged;
  documented explicitly rather than silently relied upon.

## External-Plan-Review-Findings

Both GLM and OpenAI reviewed the sub-iterate spec + mini-plan (`--mode
iterate`, before the diff existed) and returned `revise`:

| Finding (severity) | Disposition |
|---|---|
| GLM (high) / OpenAI (high, independently, same finding): the mini-plan's "fall back to completed_steps when phase_tasks[]'s completed set is empty" conflates "no usable phase_tasks[] data" with "a valid driven run mid-flight where nothing has finished yet" — the latter's emptiness is itself authoritative, and falling back there resurrects a stale completed_steps read | accepted-and-fixed — added `completed_phases_with_fallback()`, whose fallback now triggers only when `phase_tasks` is absent/not-a-list, never on an empty derived completed set. Regression tests added in all three consumers plus the shared helper itself (`test_trusts_an_empty_completed_set_when_phase_tasks_is_present`, `test_trusts_an_explicitly_empty_phase_tasks_list`) |
| GLM (medium) / OpenAI (medium, independently): three private `_completed_phases()` helpers with identical semantics risk drifting apart over time | accepted-and-fixed — consolidated into one shared `shared/scripts/lib/handoff_phase_status.py::completed_phases_with_fallback`, called from all three sites |
| GLM (medium): the plan didn't state whether `skipped` phases count as completed for `convert_configs_to_events.py`'s event emission | accepted-and-documented-and-tested — `skipped` folds into completed exactly as `completed_steps` already treated it pre-migration; `test_convert_emits_phase_completed_for_a_skipped_phase` pins it |
| OpenAI (medium) / GLM (medium, same concern): whether `done`/`skipped` should both count as completed for dashboard-coverage and event-emission purposes, not only the adopted-repo design gate, needed confirming and testing per consumer | accepted-and-tested — added a `skipped`-phase test to `convert_configs_to_events.py`'s suite specifically (design_checks.py's adopted-repo test already exercised a `skipped` `test` entry) |
| GLM/OpenAI (low, edge-case): malformed `phase_tasks[]` entries (missing keys, non-string statuses) not addressed in the plan | rejected-with-reason, already covered — `phase_tasks_progress()`'s pre-existing guards (unchanged by this sub-iterate) already handle this; documented in the shared helper's docstring rather than re-implemented |
| GLM (low, dependency): construct the adopted-repo test fixture from the real adopt code path, not a hand-rolled approximation | rejected-with-reason — see Rejected Alternatives (ADR-045 cross-plugin import collision) |
| OpenAI (low, dependency): verify the converter's import bootstrapping resolves outside pytest, in its normal CLI invocation | accepted-and-verified — ran `uv run shared/scripts/tools/convert_configs_to_events.py --project-root <fixture> --dry-run` directly against a hand-built config matching the real schema; confirmed the shared-lib import resolves in the production invocation path, not just under pytest |
| OpenAI (low, edge-case): add a test for the complementary case — a terminal `design` phase_tasks[] entry, where the skip gate must read False | accepted-and-tested — `test_fr_coverage_fails_when_manifest_missing_but_design_ran_per_phase_tasks` exercises exactly this (terminal `design` entry present → skip gate False → real-drift FAIL path) |

## External-Code-Review-Findings

Both GLM and OpenAI reviewed the actual diff after the plan-review fixes
landed:

| Finding (severity) | Disposition |
|---|---|
| GLM: approve, no concrete defects found; one non-blocking note that a driven run where design's `phase_tasks[]` entry is `in_progress` and its manifest was subsequently deleted would skip rather than fail loud — noted as an inherent limitation of the "appended on completion" model shared with the pre-migration `completed_steps` path, not a regression | accepted-as-noted, no code change — same limitation pre-existed |
| OpenAI (medium, regression): `completed_phases_with_fallback`'s `completed_steps` fallback branch did `set(steps)` eagerly, which raises `TypeError` when `completed_steps` contains an unhashable entry (a stray dict/list from a hand-edited or corrupted config) — the pre-migration `step in completed_steps` list-membership check tolerated this; the new set-based fallback did not | accepted-and-fixed — changed to `{step for step in steps if isinstance(step, str)}`, mirroring `adopted_phase_tasks.backfill_missing_phase_tasks`'s identical guard for the same shape. Added `test_completed_steps_fallback_skips_unhashable_entries` |

## Self-Review

1. Spec Compliance: pass — all three files (`design_checks.py`,
   `compliance_compliance.py`, `convert_configs_to_events.py`) read
   `phase_tasks[]` via the shared `completed_phases_with_fallback()`; the
   adopted-repo design-skip gate is verified directly by
   `test_fr_coverage_skips_for_adopted_repo_via_phase_tasks`, reproducing
   s2/s2b's actual seeded shape (terminal entries for
   project/plan/build/test, none for design).
2. Error Handling: pass — malformed/absent `shipwright_run_config.json`,
   a non-dict payload, and a non-list `phase_tasks`/`completed_steps` all
   fall back to the pre-existing fail-loud behavior in each of the three
   consumers. External code review's one genuine finding (unhashable
   `completed_steps` entries crashing the fallback set-comprehension) is
   fixed — see External-Code-Review-Findings.
3. Security Basics: pass — no new external input surface; all three
   consumers already read `shipwright_run_config.json` locally before this
   change. No secrets, no network calls added.
4. Test Quality: pass — targeted regression tests added for the exact
   mid-flight edge case both external reviewers independently flagged
   (`phase_tasks[]` present, nothing terminal, a disagreeing stale
   `completed_steps`) in all three consumers plus the shared helper
   directly. Full `shared/tests` (10,144), `shared/scripts/tools/tests`
   (810), and `integration-tests` (534) suites green after every fix round.
5. Performance Basics: pass — `phase_tasks[]` is a small, bounded per-run
   list; no new loops over large data, no N+1 file reads, no new I/O.
6. Naming & Structure: pass — external review (GLM + OpenAI,
   independently) flagged three near-duplicate `_completed_phases()`
   helpers as a drift risk; consolidated into one shared
   `completed_phases_with_fallback()` in the existing SSOT module for
   phase_tasks[] status vocabulary, and all three call sites now use it.
7. Affected Boundaries (ADR-024): pass. Producers:
   `plugins/shipwright-adopt/scripts/lib/config_writer.py` +
   `adopted_phase_tasks.py` (adopted-config seeding) and
   `plugins/shipwright-run`'s `config_factory.py`/`phase_task_lifecycle.py`
   (driven-run lifecycle), both documented in
   `docs/hooks-and-pipeline.md`'s schema block. Consumers: the three files
   this diff touches. Round-trip probes: test fixtures mirror the
   documented/actual producer shape (`phase`/`status`/
   `establishedAtAdoption`) rather than importing plugin-side code
   directly (ADR-045 cross-plugin collision, same constraint
   `adopted_phase_tasks.py`'s own docstring notes for the reverse
   direction); additionally ran `convert_configs_to_events.py`'s actual CLI
   entry point (`uv run ... --dry-run`) against a hand-built config
   matching the real schema, confirming the shared-lib import resolves in
   the production invocation path, not only under pytest.

## Confidence Calibration

Not fired: effective complexity (Step 3.4 diff-driven re-check) is
`small`, with no canonical risk flag (`touches_io_boundary` not set,
`risk_flags: []`) — the Step 3.8 gate condition (medium+ OR
`touches_io_boundary`) does not hold. Self-Review (above) is the only
mandatory review pass beyond the plan/code cascades. Empirical probing was
still done where cheap: the external CLI dry-run in item 7 above, and the
full three-suite re-run (shared/tests, shared/scripts/tools/tests,
integration-tests) after each of the two external-review fix rounds — no
finding on the final pass.

## Delegated-Review-Findings (3f-bis)

The runner's own tools cannot spawn subagents (`reviews.code: delegated_to_orchestrator`,
`reviews.spec`/`reviews.doubt` unset by the runner); the campaign orchestrator ran the
full internal cascade before merge, per `campaign-mode.md` 3f-bis.

**Stage 1 (spec-reviewer, HARD-GATE): PASS.** Both ACs (all three consumers read
`phase_tasks[]`; the adopted-repo design skip still fires) verified present, faithful,
and directly tested. The new shared `completed_phases_with_fallback()` helper judged a
recorded, minimal shared-touch (ADR + decision-drop + architecture.md +
hooks-and-pipeline.md, all attributed to s4), not scope creep.

**Stage 2 (code-reviewer): CHANGES_REQUESTED, both fixed.**

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | Two already-`grandfathered` baseline entries (`test_verifiers_design.py` 405→479, `test_workflow_checks.py` 563→607) had `current` bumped without becoming `state: exception` — an undocumented ratchet per the repo's Anti-Ratchet rule | high | fixed — both set to `state: exception`, `adr: "ADR-pending: .shipwright/planning/adr/iterate-2026-09-10-s4-verifiers-and-converter-phase-tasks-reader.md"` (this file), matching the exact convention s3 already established for its own analogous bumps |
| 2 | `design_checks.py`'s SKIP message/docstring still said "no 'design' in completed_steps" though the check now reads `phase_tasks[]` first | low | fixed — reworded to "no 'design' among completed phases", matching `_design_phase_ran`'s own already-updated docstring |

Also caught while amending (not a code-reviewer finding, an incidental discovery): the
runner's original F6 commit accidentally deleted two unrelated, already-merged evidence
files (`iterate-2026-08-16-fr-gate-test-evidence.json`, `iterate-2026-08-17-vite-hono-floor.json`)
— the same stray-deletion class found in s3. Restored via `git checkout origin/main --
<paths>`, confirmed both exist on `origin/main` and are unrelated to this diff's scope.

**Stage 3 (doubt-reviewer, adversarial): CHANGES_REQUESTED, fixed.**

| # | Claim under doubt | Severity | Disposition |
|---|---|---|---|
| 1 | The campaign's two sibling helpers — `phase_tasks_progress()` (s3, 4 callers) and `completed_phases_with_fallback()` (s4, 3 callers) — share one coherent "when is `phase_tasks[]` confident" contract | high | **real, confirmed**: for `phase_tasks: []` (a bare empty list), s3's callers (via `phase_tasks_progress`'s `current is None` trigger) fell back to `completed_steps`/`current_step`, while s4's helper (checking only `isinstance(tasks, list)`) treated the same shape as confident zero-completions — same on-disk config, two different answers. Fixed: `completed_phases_with_fallback` now requires `tasks` to be a non-empty list before trusting it (`isinstance(tasks, list) and tasks`), matching `phase_tasks_progress`'s existing threshold; does not reopen the mid-flight bug this sub-iterate's external review fixed (a mid-flight run always has ≥1 materialized task — `config_factory` seeds every v2 run with one at creation — so only a hand-edited/degenerate config is ever a bare empty list). Test `test_trusts_an_explicitly_empty_phase_tasks_list` renamed to `test_falls_back_when_phase_tasks_is_a_bare_empty_list` and its assertion inverted to match. |
| 2 | `convert_configs_to_events.py`'s one-time, irreversible nature means trusting `phase_tasks[]` over `completed_steps` risks a permanently under-reported event count | medium | no gap found — the converter's pre-existing "refuse if `shipwright_events.jsonl` already exists" guard is untouched, and the live orchestrator's own `record_event`/`_emit_phase_end` path independently re-records every phase it actually completes going forward, so an under-reported one-time snapshot does not lose that information permanently |
| 3 | The adopted-repo design-skip fix has a gap for a repo adopted before s2/s2b existed (no `phase_tasks[]` at all, or an older shape) | low | no gap found — `_design_phase_ran` gates on `isinstance(..., list)` first and falls through unchanged to the pre-migration `completed_steps` branch when absent; the skip decision never reads `establishedAtAdoption`, only `phase`/`status`, so any older phase_tasks shape lacking that marker is still read correctly |

**Stage 4 (PR-review-gate Tier-3, `openai/gpt-5.6-luna`, sensitive-path trigger): BLOCK ×4, all fixed — each pass ran automatically on the push that fixed the previous one.**

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | `completed_phases_with_fallback` trusted any *truthy* `phase_tasks` list without checking it held a usable entry — a non-empty but malformed list (e.g. `[{}]` or `["not-a-task"]`, no dict with a string `phase`) passed the "non-empty list" gate, so `phase_tasks_progress` returned an empty completed set that this function then treated as authoritative-zero instead of falling back to `completed_steps` — silently under-reporting already-completed phases a stale `completed_steps` still remembered | high (blocking) | fixed — the function now checks for at least one dict entry with a string `phase` before trusting the list (`has_usable_entry`), falling back to `completed_steps` otherwise; this is a third "no confident evidence" shape alongside "absent" and "bare empty list", closed the same way. Regression test `test_falls_back_when_phase_tasks_is_a_non_empty_list_with_no_usable_entries` added. |
| 2 | Fixing #1 exposed a second, distinct gap in `_design_phase_ran` itself (`design_checks.py`): it gated on `isinstance(phase_tasks, list)` alone (true even for `[]` or a malformed non-empty list), then unconditionally trusted whatever `completed_phases_with_fallback` returned — but that function's own empty-set answer is indistinguishable, by value alone, from "confidently zero". When `completed_steps` was ALSO absent/malformed (zero evidence from either source), this silently read as "design never ran" (SKIP) instead of the function's own documented fail-loud contract (assume design ran; a missing manifest is real drift) | high (blocking) | fixed — extracted the "has a usable entry" check into a new shared predicate `phase_tasks_has_usable_entries` (`handoff_phase_status.py`) used by both `completed_phases_with_fallback` and `_design_phase_ran`; `_design_phase_ran` now gates on that predicate and falls through to a *local* fail-loud `completed_steps` check (not the shared function) when it says no. Regression test `test_fr_coverage_fails_loud_when_neither_source_has_confident_data` added (`phase_tasks: []`, no `completed_steps` key at all → manifest-missing still fails, not skips). |

| 3 | `phase_tasks_has_usable_entries` (added in fix #2) required only a string `phase`, not a recognized `status` — an entry like `{"phase": "design"}` (no `status` key) or `{"phase": "design", "status": "???"}` counted as "usable" even though `status_of()` reads it as `None`/unclassifiable, so `phase_tasks_progress` silently excludes it from `completed` for a reason unrelated to whether it actually finished — trusting that as confident-zero would ignore a valid, non-stale `completed_steps` | high (blocking) | fixed — the predicate now also requires `status_of(task) in KNOWN_STATUSES`, agreeing with what `phase_tasks_progress` can actually classify, not merely parse. Regression tests `test_falls_back_when_phase_task_entry_has_no_status` and `test_falls_back_when_phase_task_entry_has_a_malformed_status` added. |

| 4 | `phase_tasks_has_usable_entries` used `any(...)`, so a list mixing one valid entry with one malformed entry (e.g. `[{"phase": "project", "status": "done"}, {"phase": "design"}]`) was trusted wholesale — `phase_tasks_progress` then silently excluded the malformed phase from `completed` instead of falling back to `completed_steps` for it. Non-blocking comment (same pass): the extensive review-history docstrings on this predicate and `completed_phases_with_fallback` were what pushed `handoff_phase_status.py` past the 300-line bloat guideline; the reviewer suggested moving that history to the ADR | high (blocking) + low (non-blocking) | fixed — switched to `all(...)` (guarded with `bool(tasks)` so an empty list, vacuously `all`-true in Python, still reads as not-usable); both docstrings trimmed to a concise behavioral contract pointing here for full rationale, which incidentally brought the file back under 300 lines (235) without needing a baseline exception at all. Regression test `test_falls_back_when_phase_tasks_mixes_valid_and_malformed_entries` added. |

Full `shared/tests` re-run after all four fixes: 10,148+ passed, `verify_local.py` 3/3 gates green, ruff clean. `test_verifiers_design.py`'s already-`exception` baseline entry bumped 479→498 for the regression tests added across fixes #1-#2; `adr` reference unchanged (this file). `handoff_phase_status.py` briefly crossed 300 lines (305) between fixes #2-#4; the docstring trim in fix #4 brought it back to 235, so no baseline entry was needed for it.
