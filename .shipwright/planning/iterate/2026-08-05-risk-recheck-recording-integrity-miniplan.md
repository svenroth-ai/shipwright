# Mini-Plan: risk-recheck-recording-integrity

- **Run ID:** iterate-2026-08-05-risk-recheck-recording-integrity

## Files to create/modify

| File | Change |
|---|---|
| `plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py` | edit — persist `recheck()` result to a per-run artifact when `--run-id` given |
| `shared/scripts/tools/verifiers/risk_recheck_recording.py` | new — `check_risk_recheck_recorded` F11 verifier + artifact reader |
| `shared/scripts/tools/verifiers/iterate_checks.py` | edit — import + register the new check in `run_all_checks` |
| `plugins/shipwright-iterate/agents/sub-iterate-runner.md` | edit — Step 3.4 prose: recording is now enforced |
| `plugins/shipwright-iterate/skills/iterate/references/F6.md` | edit — name `risk_recheck.json` in the directory-add note |
| `docs/hooks-and-pipeline.md` | edit — document the new F11 verifier |
| `plugins/shipwright-iterate/tests/test_diff_risk_recheck_persistence.py` | new — unit tests for the CLI's artifact-writing |
| `shared/tests/test_risk_recheck_recording.py` | new — unit tests for the new verifier |
| `integration-tests/test_risk_recheck_recording_integration.py` | new — the `category:"integration"` composition proof |

## Work breakdown

1. **Persist the artifact.** Add `write_recheck_record(project_root, run_id, result) -> Path` to
   `diff_risk_recheck.py`, mirroring `record_ci_supplychain_ack.py`'s envelope
   (`{"schema_version": 1, "run_id": ..., "risk_recheck": {...recheck() dict...}}`),
   written atomically (`.tmp` + `os.replace`) to
   `.shipwright/planning/iterate/<run_id>/risk_recheck.json`. Validate `run_id`
   is a single safe path component before writing (reuse
   `lib.review_record_schema.is_safe_run_id` — already the SSoT `ci_supplychain_ack_store`
   imports from). Call it from `main()` right after `recheck()` succeeds,
   before printing/returning, whenever `args.run_id` is truthy — on BOTH the
   `0` and `3` exit paths (the CI-escalation `3` still computed a real
   `effective_complexity` worth recording).
   Test: CLI writes the file with the right shape; no `--run-id` → no file;
   unsafe run-id → `SystemExit` before any write.

2. **New F11 verifier.** `risk_recheck_recording.py`:
   - `_COMPLEXITY_ORDER = ("trivial", "small", "medium", "large")` — a
     self-contained, drift-pinned copy (ADR-044: this shared verifier must not
     cross-plugin-import `plugins/shipwright-iterate/scripts/lib/complexity_vocabulary.py`).
     A sync test pins it against that module's `COMPLEXITY_ORDER`.
   - `read_recheck_record(project_root, run_id) -> tuple[dict | None, str | None]`
     reads `.shipwright/planning/iterate/<run_id>/risk_recheck.json` from the
     WORKING TREE (mirrors `check_integration_coverage`'s `_read_entry` — this
     is a same-run self-report read, not a diff computation, so no git-blob
     complexity is needed here unlike `ci_supplychain_ack`'s content-fingerprint
     concern, which doesn't apply: there is nothing to re-edit after the fact,
     just a classification decision to transcribe honestly).
   - `check_risk_recheck_recorded(project_root, run_id, commit_hash="") -> CheckResult`:
     - Artifact absent → `CheckResult(name, True, "skipped (no Step 3.4 risk re-check for this run — standalone iterate or pre-contract run)", severity=SKIPPED)`.
     - Artifact malformed / wrong schema_version / missing `effective_complexity` → FAIL, name the defect.
     - Artifact present, F5c entry absent/malformed (`find_entry_by_run_id`) → FAIL — "recorded complexity cannot be verified".
     - Both present: rank(F5c `complexity`) < rank(`effective_complexity`) → FAIL, naming both values + the run_id + the fix (re-run F5c with the correct complexity, or explain why Step 3.4's floor was wrong).
     - Otherwise → PASS.
   - `commit_hash` param kept for `run_all_checks` calling-convention uniformity; unused (matches other single-argument-need checks in that list).
   Test: 5 cases above, each its own unit test.

3. **Register in `run_all_checks`.** Import + add one line to the list in
   `iterate_checks.py`. Test: existing `test_iterate_checks_registry`-style
   test (if one enumerates the list) picks it up; otherwise a small assertion
   that the check name appears in `run_all_checks(...)` output for a fixture
   repo.

4. **Contract prose.** `sub-iterate-runner.md` Step 3.4 item 2: change
   "F5c MUST record this value... and check_integration_coverage reports an
   under-classified run against it" to name the new enforcement instead of the
   now-stale claim (P1.04 already made `check_integration_coverage` stop
   reading complexity at all).

5. **F6.md.** Extend the existing directory-add bullet/note to also name
   `risk_recheck.json`, alongside `reviews.json` + `ci_supplychain_ack.json` —
   no new `git add` line needed since the add is already directory-level.

6. **docs/hooks-and-pipeline.md.** Add the new verifier to whatever table/list
   documents the F11 verifier registry (read the file first to match its
   existing structure before editing).

7. **Integration test.** Real repo (tmp_path, like
   `test_campaign_risk_recheck_integration.py`): run the actual
   `diff_risk_recheck.py` CLI as a subprocess against a real git repo with a
   cross-component-shaped change and `--run-id`, assert the artifact file
   lands with the right shape; then write an F5c entry via
   `append_iterate_entry.py` (or hand-craft the entry file, whichever is
   cheaper and still real) recording a LOWER complexity than what the CLI
   computed; call `check_risk_recheck_recorded` directly against that repo and
   assert it FAILS. This is the "pieces compose" proof the `touches_io_boundary`
   / general finalization-gate confidence calibration requires — three
   individually-correct units (CLI, F5c writer, verifier) wired together for
   real, not mocked.

## Test strategy

Unit tests for the artifact writer, unit tests for the verifier's five
branches, one integration test proving composition end-to-end. No E2E/browser
surface (CLI-only). `uv run pytest plugins/shipwright-iterate/tests/ -v` and
`uv run pytest shared/tests/ -v` from their own roots (one test root per
process, per this repo's `conftest.py` rule), plus
`uv run pytest integration-tests/ -v` for the new integration test.

## External Plan Review Findings (openai + deepseek, both providers)

Both providers judged the approach sound (openai: revise; deepseek: approve).
Actioned:

1. **Step 3.4 already passes `--run-id`** (openai #1, high) — verified: the
   runner contract's own example command (Step 3.4, line ~61) already includes
   `--run-id "{run_id}"`. No new file to touch; add a prose-pinning test
   (mirrors the existing `test_step_3_4_requires_f5c_to_record_effective_complexity`)
   asserting the Step 3.4 command block still names `--run-id`, so a future
   edit can't silently drop it.
2. **Path safety** (both, medium) — `diff_risk_recheck.py` is plugin-lib code
   that **deliberately never imports `shared/` at runtime** (established
   precedent: `session_plan.py`'s `RUN_ID_STRICT` comment — the plugin cache
   does not guarantee `shared/` is reachable at a known relative path). So
   reusing `shared/scripts/lib/review_record_schema.is_safe_run_id` directly is
   not an option; write a **self-contained local copy** (`_is_safe_run_id`,
   same regex/length/`.`/`..` rules) with a behavioral sync test against the
   shared original (tests may cross-import; only production code may not).
   Full resolve+containment symlink-escape hardening was initially considered
   and rejected as out-of-scope, on the grounds that none of the three
   existing sibling artifacts in the same directory do it either and `run_id`
   is Shipwright-generated (not attacker-controlled) in this system's threat
   model. **Reversed after the external CODE review independently flagged the
   same class of gap a second time** (a symlinked `<run_id>` directory could
   make the writer/reader escape the planning tree): two independent findings
   on the same theme outweighs "no existing precedent does this" — the fix is
   cheap (`resolve()` + `relative_to()` containment on both writer and
   reader), so it is now implemented on this new artifact (the three existing
   siblings are unchanged; a broader retrofit is a separate, larger effort).
   What IS added (cheap, precedent-matching): reject a target path that
   **exists but is not a regular file** (mirrors `load_ack`'s exact
   `exists() and not is_file()` check) in both writer and reader.
3. **Strict reader validation** (both, medium) — every field is validated and
   converted to a named `CheckResult` failure, never left to raise: JSON
   parses, top-level dict, exact `schema_version`, envelope `run_id` matches
   the requested run_id, `risk_recheck` is a dict, `effective_complexity` is a
   string in the canonical order, F5c's `complexity` is a string in the
   canonical order. `_rank()` returns `None` (not an exception) for anything
   unrecognized, and the check FAILs on `None` rather than raising.
4. **F5c "duplicate entry" concern (openai #4) — not applicable.**
   `.shipwright/agent_docs/iterates/<run_id>.json` is a one-file-per-run_id
   store with a single writer (`append_iterate_entry.py`, F5c); there is no
   "duplicate F5c record" ambiguity in this data model the way there might be
   in an append-only log. What the finding correctly flags — a missing or
   type-invalid `complexity` field — is handled by the strict validation in
   point 3.
5. **"Nothing to re-edit after the fact" was an overclaim (both, risk) —
   corrected.** This gate proves **transcription integrity between two
   self-reported working-tree artifacts**, not independent re-verification: a
   runner could still lower the persisted `risk_recheck.json` itself before
   F6. Closing that would need an independently-reproducible fingerprint or a
   re-run of the diff-driven detectors at F11 (out of scope — see below); the
   verifier's docstring and this plan now say so explicitly rather than
   claiming "non-dodgeable." Consistent with the original finding's own
   framing: every runner-contract step is contract-enforced, not
   independently gated, and this is not a new category of that.
6. **Exit-3 (CI escalation) path must persist too, with its own test** (both) —
   confirmed in the design (write happens right after `recheck()` returns,
   before the exit-code branch) and added as an explicit subprocess-level test
   case (real repo, CI-boundary file, assert exit 3 AND artifact present with
   the computed `effective_complexity`).
7. **Registry composition must be asserted, not conditional** (openai #6) —
   the integration test calls `run_all_checks(...)` directly (not just the
   bare check function) and asserts the check's name appears and fails —
   proves both the logic AND that it's actually wired into the F11 path a
   real finalization run takes.
8. **Unrecognized `effective_complexity` must not crash the rank lookup**
   (deepseek) — covered by point 3's strict validation (`_rank` returns `None`
   instead of raising).
9. **Write-failure visibility on the exit-3 path** (deepseek/openai,
   low/medium) — `main()` wraps the persistence call in its own try/except and
   attaches a `recheck_record_error` field to the printed JSON on failure
   **without changing the original exit code** — a side-artifact write
   failure must not turn a real CI-boundary escalation (which the runner
   branches on by exit code) into a generic "re-check did not run" failure.

## Code Review Cascade Findings

- **Stage 1 (spec-reviewer), round 1: REJECT.** The Confidence Calibration
  claimed all 9 external-review findings were addressed, but finding #1's
  committed action (a `--run-id`-presence pinning test) was never actually
  added. Fixed: `test_step_3_4_example_command_still_passes_run_id` added to
  `test_sub_iterate_runner_step_3_4.py`. Round 2: PASS.
- **Stage 2 (code-reviewer): 2 findings, both fixed.** (1) A docstring claimed
  a `RECHECK_SCHEMA_VERSION` sync test existed when it didn't — added
  `test_recheck_schema_version_sync`, mirroring the existing
  `_COMPLEXITY_ORDER` sync test. (2) A test file's section header was
  orphaned — `test_is_safe_run_id_sync_with_shared_precedent` was misplaced at
  file-end instead of under its own header; moved into place.
- **Stage 3 (doubt-reviewer): 1 advisory finding, addressed then superseded by
  a stronger fix.** A write-time persistence failure is indistinguishable
  from genuine absence at the F11 gate — both SKIP identically, and the
  original SKIP message asserted a specific cause ("standalone iterate or a
  run that predates the recording contract") that is FALSE for the
  write-failure case. First fix: reworded the message to not claim a specific
  cause. **Superseded** by the external code review's finding #1 below, which
  changed `main()`'s exit code on write failure — that closes the underlying
  gap (Finalization/F5c is now unreachable on a write failure via a
  compliant runner), leaving the reworded message as defense-in-depth rather
  than the primary mitigation.

## External Code-Review Findings (openai + deepseek, both providers)

openai: revise. deepseek: approve. Actioned:

1. **Persistence failure silently bypassed the gate on the continue path**
   (openai, HIGH). `main()` attached `recheck_record_error` to the JSON but
   still returned exit 0 — so a write failure (unsafe run_id, permission
   error, a pre-existing non-file at the target) left the artifact absent
   while the runner sailed on to Finalization, where F11 would SKIP instead
   of enforcing anything. Fixed: on the CONTINUE path only, a write failure
   now returns exit 2 ("operational failure — the re-check did not run",
   the same contract semantics Step 3.4 already uses for every other
   non-zero/non-3 case), so the runner's own "STOP, never continue on a
   stale estimate" instruction keeps it out of Finalization entirely. The
   CI-ESCALATION (exit 3) path is unchanged on purpose — that run is already
   stopping for operator review regardless of the artifact, and downgrading
   it to a generic operational failure would erase the CI-boundary reason
   (this was the ORIGINAL external plan review's finding #9, and it still
   holds for that one path).
2. **Test only exercised `write_recheck_record()` directly, not the CLI
   bypass** (openai, medium). Added `test_main_fails_on_write_failure_on_the_continue_path`
   and `test_main_fails_on_unsafe_run_id_on_the_continue_path` — both assert
   exit 2 through the real `main()` entry point.
3. **Symlinked `<run_id>` directory could write outside the planning tree**
   (openai, medium) — the SAME class of concern the first external plan
   review raised and this plan initially scoped out. Reversed (see Path
   safety, item 2 above): both writer and reader now resolve the run
   directory and reject one that resolves outside
   `.shipwright/planning/iterate/`.
4. **Dangling/symlinked artifact path read as genuine absence** (openai,
   medium) — `path.exists()` alone follows a symlink and reports `False` for
   a dangling one, which the old code read as "nothing to see here" (a SKIP)
   rather than "something is wrong here" (a FAIL). Fixed: the reader checks
   `path.is_symlink()` before `path.exists()` and treats either a dangling or
   a valid symlink as malformed, never absent.
5. **Missing vs. unrecognized `effective_complexity` shared one misleading
   message** (deepseek, low). `None` (missing) was reported as
   `"unrecognized effective_complexity (None)"`. Fixed: the reader now
   distinguishes an absent field from an invalid value.

All five actioned; full test suites (plugin: 926 passed, 1 skipped;
integration: 5 passed; shared: re-run pending final confirmation) green after
the fixes, ruff clean.

## Alternative approach considered — and rejected

**Alternative: read `result.json.risk_recheck` (the runner's final output)
instead of a new dedicated artifact.** The card's candidate fix literally
names `risk_recheck.effective_complexity`, which lives in `result.json`'s
schema-documented field. But `result.json` is written at Step 6 — *after*
Step 4's Finalization, which includes the runner's own F6-verify call to the
same F11 verifier this change adds a check to. By the time F6-verify runs,
`result.json` does not exist yet (chicken-and-egg), and `result.json` itself
is never committed to git (it is local orchestrator state under
`.shipwright/runs/<loop_id>/<unit>/`, read by `autonomous_loop.py`'s
`cmd_record`, not part of the PR diff at all). Hooking the check into
`cmd_record`/`_validate_result` instead was considered, but that only runs in
campaign mode's own loop driver — the runner's OWN F6-verify (which the
contract explicitly calls "MANDATORY — do NOT skip", and which is what the
Stage-1 spec/code-review cascade at 3f-bis reviews before merge) would still
see nothing, and the PR could still merge with an under-recorded complexity
if the orchestrator step were ever skipped or the file inspected at the wrong
moment. A durable, committed, per-run artifact written by Step 3.4 itself
(before Finalization, alongside the sibling `ci_supplychain_ack.json`) is
available to the SAME F6-verify call the runner already treats as
non-negotiable, ships in the PR, and is inspectable after the fact —
consistent with how `check_ci_supplychain_ack` and `check_review_record`
already solved the identical "self-report needs a durable, git-shipped home"
problem for their own artifacts.
