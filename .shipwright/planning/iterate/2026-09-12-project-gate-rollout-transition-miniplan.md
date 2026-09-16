# Mini-Plan: project-gate-rollout-transition

- **Run ID:** iterate-2026-09-12-project-gate-rollout-transition

## Files to create/modify

Actual module layout ended up split four ways instead of one (each split at
the 300-LOC bloat-baseline guideline, same precedent as every other split in
this gate family — see each module's own docstring for why):

| File | Change |
|---|---|
| `shared/scripts/tools/verifiers/_project_gate_rollout.py` | new — commit resolution: `GATE_ROLLOUT_AT_EPOCH`/`_ISO`/`_COMMIT`, `_is_shallow`, `resolve_head_sha`, `resolve_rollout_commit`, `cached_rollout_sha` |
| `shared/scripts/tools/verifiers/_project_gate_rollout_snapshot.py` | new — snapshot reading: `_repo_relative_prefix` (git show/-C path fix), `RolloutSnapshot`, `build_rollout_snapshot` |
| `shared/scripts/tools/verifiers/_project_gate_grace.py` | new — pure comparators: `norm_title`, `_row_identity_matches`, `graced_criteria_for_row`, `split_name_from_path`, `split_predates_rollout` |
| `shared/scripts/tools/verifiers/_project_gate_extras.py` | edit — `GateResult` gains `severity`/`strict_exempt`; #5/#10 functions moved OUT (see below); keeps only #4/#15 + #11 |
| `shared/scripts/tools/verifiers/_project_gate_extras_rollout.py` | new — `criteria_free_of_implementation_detail` (#5) + `no_empty_split` (#10), moved from `_project_gate_extras.py`, both rollout-aware via an optional `rollout` param |
| `shared/scripts/tools/verifiers/_project_gate_wiring.py` | edit — `check_criteria_free_of_implementation_detail` + `check_no_empty_split` call the rollout-aware pass lazily, forward `severity`/`strict_exempt` via `_to_check_result` |
| `shared/tests/test_project_gate_rollout.py` | new — real-git resolver tests (before/at/after cutoff, shallow clone, empty ref, SHA cache) |
| `shared/tests/test_project_gate_rollout_snapshot.py` | new — real-git snapshot tests, incl. nested-`project_root` git show/-C regression coverage, manifest fallback, text cache |
| `shared/tests/test_project_gate_grace.py` | new — pure comparator matrix (identity match/refuse, membership, split declaration) |
| `shared/tests/test_project_gate_extras_rollout.py` | new — pure #5/#10 tests (rollout-unaware, carried over) + grace-path matrix via a fake snapshot |
| `shared/tests/test_project_gate_extras.py` | edit — #5/#10 tests removed (moved above), docstring updated |
| `shared/tests/test_project_gate_wiring_rollout.py` | new — real-git, end-to-end wiring tests proving the downgrade lands in the actual `CheckResult` for both gates |
| `.shipwright/planning/adr/iterate-2026-09-12-project-gate-rollout-transition.md` | new — ADR |
| `.shipwright/agent_docs/architecture.md` | edit — one bullet noting the new gate-family precedent |
| `CHANGELOG-unreleased.d/Fixed/iterate-2026-09-12-project-gate-rollout-transition_001.md` | new |
| `.shipwright/triage.jsonl` | append — mint four follow-up cards (adopt-miner conflict `trg-ac2ef362`; shared rollout-primitive extraction `trg-fcb3ee97`; `strict_exempt` not honored by `verify_phase.py --strict`, found in Stage-2 code review, `trg-b996bc21`; rollout-transition grace's timestamp trust boundary, found in Stage-3 doubt review, `trg-4380c61a`) now; append the `trg-9583d3a8` close event as a small follow-up once this run's own PR exists (mirrors the `trg-aedcfe7b` precedent — its close event postdates that PR's own diff, referencing `PR:721`) |

## Work breakdown

1. `_project_gate_rollout.py` + `_project_gate_rollout_snapshot.py`:
   commit resolution and historical-content reading, kept as two modules
   (resolve-which-commit vs. read-what-it-said) once the combined draft
   crossed 300 lines. Test: real-git resolver + snapshot behaviour
   (before/at/after cutoff, shallow clone, empty hash, nested `project_root`,
   caches).
2. `_project_gate_grace.py`: pure identity/membership comparators, split out
   once internal plan review's revisions (per-criterion membership instead
   of whole-row equality; `(Name, text)` identity instead of `Name` alone)
   grew the combined extras module past cap.
3. `_project_gate_extras.py` / `_project_gate_extras_rollout.py`: `GateResult`
   gains `severity`/`strict_exempt` (both optional, default off, defined in
   the former); `criteria_free_of_implementation_detail` + `no_empty_split`
   (moved to the latter) take an optional `rollout` snapshot and use
   `_project_gate_grace` to partition hits into hard vs. graced. Test:
   pure-function matrix (unchanged/edited/new criterion, repurposed id,
   no rollout at all) via a duck-typed fake snapshot — no git needed here.
4. `_project_gate_wiring.py`: both `check_*` wrappers run the rollout-unaware
   pass first; on any hit, lazily call `build_rollout_snapshot(project_root,
   "HEAD")` and re-run with it if resolved; `_to_check_result` forwards
   `severity`/`strict_exempt` from the `GateResult` onto the `CheckResult`.
   Test: real-git, wiring-level end-to-end (a `tmp_path` repo with a
   pre-rollout commit + a later commit, asserting the wrapper itself
   downgrades — and that a genuinely NEW post-rollout violation still hard
   blocks).
5. ADR + architecture.md bullet + CHANGELOG drop + close `trg-9583d3a8` +
   mint the two follow-up triage cards disclosed during build (the
   `/shipwright-adopt` producer-vs-gate-#5 conflict; the shared
   rollout-git-primitive extraction across the three gate families).

## Test strategy

Real-git tests (a `tmp_path` repo with `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`
pinned explicitly, mirroring the precedent's own real-git fixture style — no
ambient-clock dependency) for commit resolution, snapshot reading, and the
wiring-level end-to-end proof; duck-typed-fake-snapshot pure-function tests
(no git) for the grace comparators and the #5/#10 partition logic. No E2E
surface (Verification: none, per spec).

## Alternative approach — rejected

**Option B — a permanent `scope == "extension"` skip**, mirroring #4/#15/#11.
Rejected: #5/#10 are stated as universal rules in `fr_hygiene_detectors`/
`split-heuristics.md`, not greenfield-only — a permanent skip would exempt
every FUTURE extension-scope violation too, not just the legacy content
`trg-9583d3a8` actually names. Cheaper to build (no new module), but solves
a narrower problem than the one it creates. See Architecture Review in the
iterate spec for the full reasoning and both external reviewers' verdicts.
