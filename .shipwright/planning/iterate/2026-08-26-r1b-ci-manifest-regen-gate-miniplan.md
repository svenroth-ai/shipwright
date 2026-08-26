# Mini-Plan: r1b-ci-manifest-regen-gate

- **Run ID:** iterate-2026-08-26-r1b-ci-manifest-regen-gate

## External Plan Review (openai + deepseek via external_review.py --mode iterate)

**Verdict: revise / revise.** Both reviewers independently caught the same
load-bearing bug in the post-internal-review design: the structural tier still
compared the `tests` map's KEY SET after only dropping the `status`/`executed`
leaves, which re-introduces the platform-selection false-positive AC1 was
supposed to eliminate. Both also flagged CI report-set completeness (nothing
verified the three existing pytest steps collectively cover every root),
run-completeness for staging (a fully-reported red F0 run could still get
staged as if it were complete evidence), and (deepseek) an explicit exit-code
contract for the comparator instead of a blanket `|| true`. All findings are
FIXED and folded into the iterate spec's Acceptance Criteria (AC1/AC2/AC3/AC4)
directly — that is now the authoritative, detailed source; the work breakdown
below is updated to match but does not repeat every clause. See the iterate
spec for exact wording.

## Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/tools/compare_traceability_manifest.py` | new — normalized compare, `--check` exits non-zero on drift |
| `shared/scripts/tools/tests/test_compare_traceability_manifest.py` | new — pins the exclusion set + a few drift scenarios |
| `shared/scripts/tools/run_test_suite.py` | edit — retain successful units' JUnit reports + write side-manifest |
| `shared/scripts/tools/tests/test_run_test_suite.py` (existing) | edit — cover the new retention path |
| `shared/scripts/tools/stage_f0_evidence.py` | new — reads F0's side-manifest, stages via `evidence_drop.stage_reports` |
| `shared/scripts/tools/tests/test_stage_f0_evidence.py` | new |
| `.github/workflows/ci.yml` | edit — `--junit-xml` on 3 existing steps + new advisory compare step |
| `shared/scripts/lib/ci_gate_allowlist.py` | edit — register the new advisory step |
| `shared/scripts/tools/check_ci_gate_coverage.py` tests (existing) | edit — cover the new allowlist entry doesn't regress guard behavior |
| `plugins/shipwright-iterate/skills/iterate/references/F0.md` | edit — document retention path |
| `plugins/shipwright-iterate/skills/iterate/references/F5.md` | edit — document `stage_f0_evidence.py` as the preferred path over a second full run |
| `docs/hooks-and-pipeline.md` | edit — CI step + artifact-write matrix entries |
| `Spec/design/2026-07-22-req3-campaign-SPEC.md` | edit — one-line note at §4 P0a (AC6) |
| `.shipwright/planning/campaigns/2026-08-23-req3-04-ac-identity-mono-BRIEF.md` | edit — mark R1b done, record what shipped |

## Work breakdown

**Revised after Internal Plan Review (opus-plan-reviewer, 14 findings, all
fixed — see the iterate spec's `## Internal Plan Review` section for the full
list). The steps below already reflect the fixes; do not re-derive the
rejected earlier design from the AC text alone.**

1. **`compare_traceability_manifest.py` + its pinning test.** Two-tier
   compare, not one flat diff (Finding 1/3 fix). Structural tier: drop
   `generated_at`/`source_commit`, then drop `tests[*].status`/`.executed`
   from a copy of each requirement's `tests` map, compare the rest
   structurally (`==` on parsed dicts, not text). Execution tier: for test ids
   present in BOTH manifests' `tests` maps, compare `status`/`executed` and
   report agreement/disagreement; for ids present in only one, report as a
   platform-selection difference. `--check`'s exit code reflects the
   structural tier only; both tiers print (`difflib`-style, mirroring
   `regen_golden.py`'s existing pattern). Test: identical manifests differing
   only in the two excluded top-level fields → exit 0; a changed
   non-execution field (e.g. `title`) → exit 1, named in the diff; a
   test-id-only-in-one-side case → exit 0, reported in the execution-tier
   section, not counted as failure.
2. **`run_test_suite.py` retention.** Extract `run_full_suite_evidence.py`'s
   `plan_root()` base logic to a location both tools can import (Finding 6
   fix — NOT a fresh `discover_test_roots` derivation, which has no base
   logic). Change `_exec`'s `report = tmp_dir / "r.xml"` handling to ALSO copy
   the file (on any outcome where it exists) into a stable per-run directory
   before `tmp_dir` is cleaned up — the existing `.shipwright/runs/<run_id>/`
   convention the failed-attempt diagnostics already write under, resolved to
   the MAIN repo root the same way. Retry rule (Finding 8 fix): when a unit
   was retried serially, the retry's report supersedes the initial parallel
   attempt's — never the reverse. Write one side-manifest JSON at the end of
   `run_suite()` listing every unit's `(unit_id, base, report_path, phase)`.
   Add a parity test (mirroring `test_f0_ci_parity.py`) asserting F0's unit
   set matches `discover_test_roots`'s root set — the SSoT gap Finding 6
   found. Prune retained run directories to the last N=5 (Finding 14 fix).
   Test: a green suite run leaves N report files + one side-manifest naming
   all N; a unit that was serially retried retains the retry's report, not
   the initial's (this is NEW behavior — correcting the earlier miniplan's
   false claim that failed-unit JUnit XML is "already retained" today; only
   tail *text* is, via `write_attempt_evidence`).
3. **`stage_f0_evidence.py`.** Reads the side-manifest from step 2, calls
   `evidence_drop.stage_reports` (the Python API `run_full_suite_evidence.py`
   already uses) once with all `(base, path)` pairs — no second pytest
   invocation. `--run-id`/`--head-commit` are REQUIRED, no defaults (Finding
   10 fix — an unset value must fail loud, not silently degrade F11's
   cross-layer gate to MISSING everywhere). Refuses to stage when the
   side-manifest shows any unit missing a report (Finding 9 fix — an
   incomplete F0 run must not produce evidence that looks complete). Test:
   given a fixture side-manifest + fixture XML files, asserts
   `junit-01.xml`..`junit-NN.xml` land with correct provenance bases; a
   missing-report fixture refuses to stage; a post-stage
   `evidence_drop.evidence_is_fresh(root, run_id)` check returns True.
4. **`ci.yml` — JUnit capture.** Add `--junit-xml <scratch-path>` to: the
   per-plugin loop, the shared-tier loop, and the integration-tests step,
   naming each report file by the SAME filename convention `plan_root()`
   produces (Finding 7 fix — no hand-typed base-to-path mapping in the YAML;
   a small Python helper recovers the base from the filename at staging time
   in step 5).
5. **`ci.yml` — advisory compare step, moved to the END of the job** (Finding
   12 fix — after "Sweep delivery surface (gate)", so a step that
   intentionally mutates tracked/gitignored state can't affect any other
   gate). In order: (a) `git show HEAD:.shipwright/compliance/test-
   traceability.json` to a scratch path — capture the committed baseline
   BEFORE it's overwritten (Finding 2 fix — `generate_file()` has no
   scratch-output param, confirmed against the real signature; the tracked
   file gets rewritten in place, and that's fine here because of the step's
   new position); (b) stage the scratch-dir reports via the same helper from
   step 4; (c) run `test_links.generate_file()`; (d) run
   `compare_traceability_manifest.py --check` between the captured baseline
   and the now-regenerated tracked file. Steps (a)-(c) run under `set -e`,
   fail-closed on any crash or zero-reports-staged condition (Finding 5 fix).
   Only the compare command in (d) is `|| true`-wrapped — this is what makes
   `check_ci_gate_coverage.py`'s `is_loose()` correctly classify the step as
   advisory (Finding 4 fix — matches its `_PIPE_SUPPRESS` regex), so the
   allowlist entry registered for it in step 6 is genuine, not stale.
6. **`ci_gate_allowlist.py`.** Register the step from step 5 in
   `LOOSE_GATE_ALLOWLIST` — it IS loose per the `|| true` in step 5(d), so
   this entry is required, not optional (Finding 4 corrected the earlier
   miniplan's "maybe not needed" framing). The reason names: the hardening
   trigger (N=5 consecutive green PRs, confirmed with the operator), AND the
   hardening prerequisite Finding 11 flagged — before this becomes a real
   block, the comparator must run from the PR's BASE revision (mirroring
   "Repair-PR safety (gate)", ci.yml:253-282) so a branch can't silence its
   own drift finding by editing the tool that judges it. Not built in this
   iterate — documented as a precondition for the follow-up that hardens it.
7. **Docs.** F0.md (retention + pruning), F5.md (`stage_f0_evidence.py` is the
   ONLY staging call for a run that went through F0 — replaces, not adds to,
   the existing generic multi-`--junit` example for that case, since
   `evidence_drop.stage_reports` clears the evidence dir first and two
   staging calls in one run would race each other, Finding 9), keep
   `run_full_suite_evidence.py` documented for the case of repo-wide evidence
   WITHOUT an F0 run, `docs/hooks-and-pipeline.md` (CI-step + artifact-write
   matrix rows), campaign brief + SPEC note.
8. **Full local proof.** Run `run_test_suite.py` on this repo's own tree,
   confirm retained reports + side-manifest + pruning, run
   `stage_f0_evidence.py` against them, confirm freshness, regenerate the
   manifest, run the compare tool against the pre-change committed manifest —
   the empirical AC1-AC3 proof this task itself demanded before believing
   anything works. This local run cannot exercise the execution-tier's real
   cross-OS behavior (Finding 3) — that data only exists once this PR's own
   CI run produces it, which is the intended empirical loop for the advisory
   period.

## Test strategy

- Unit tests for the new comparison tool (exclusion-set pinning is the
  load-bearing one — SPEC:202-206's landmine list didn't name these two
  fields, so a regression here is exactly the "gate red on PR 1" failure
  this whole unit exists to prevent).
- Unit tests for `run_test_suite.py`'s retention path (mock/fixture-scale,
  not a full 18-root run in the test itself).
- Unit tests for `stage_f0_evidence.py` against fixture data.
- No E2E — this is CLI/CI tooling, no `client/**` surface. F0.5 surface =
  `cli`, verified by actually running the tools against this repo's own
  tree (step 8 above) as the empirical evidence, not a synthetic fixture
  alone.
- Full local suite run (F0) is itself the integration proof for AC2/AC3 —
  `cross_component`? No: this touches CI/test-execution machinery but not
  the merge/churn/event-log/hook-fan-out/campaign-drain list the risk flag
  is scoped to (checked against SKILL.md's `cross_component` file-pattern
  list) — flag does not fire. `touches_ci_supplychain` DOES fire
  (`.github/workflows/ci.yml` edit) — acknowledgement required at F11.

## Alternative approach considered

**Alternative: have the new CI step re-run a dedicated `run_full_suite_evidence.py`
pass instead of retaining F0's own reports (i.e., build AC4 without AC2/AC3).**
This is simpler to build — `run_full_suite_evidence.py` already exists from
R1a and needs zero changes — and was the brief's original framing ("F5b faehrt
aber nicht alle 18 Roots" implicitly assumed CI would need its own pass too).

**Why rejected:** for the CI side this is actually necessary regardless —
`ci.yml` has no F0-equivalent single-runner to retain reports FROM, so CI's
own `--junit-xml` capture (step 4) is unavoidable either way. The rejected
part is specifically skipping AC2/AC3 and instead having the LOCAL side (what
produces the manifest that gets committed) trigger a second, redundant full
pytest pass via `run_full_suite_evidence.py` at finalize, on top of the one F0
already just ran.

**Corrected cost figure (Internal Plan Review, Finding 13).** The two tools
use different execution strategies, so they are not interchangeable at the
same cost: F0's `run_test_suite.py` runs the 18-unit pool in parallel
(F0.md: "~9.8 min serial, ~1.9 min now"), while `run_full_suite_evidence.py`
drives the same 18 roots one pytest process at a time, serially, by its own
R1a design (its own docstring: "a full-suite pass takes ~20 minutes",
"20-60 minute pass"). Both figures are independently correct for their
respective tool — this is not the same run measured twice. The rejected
alternative therefore costs an order of magnitude more (20-60 min) than
originally stated here, not the same ~1.9 min as AC2/AC3's approach — the
correction strengthens the case for AC2/AC3, it does not weaken it. This was
confirmed with the operator directly (this iterate's Interview) before
committing to the AC2/AC3 scope, and re-verified against both tools' own
source during Internal Plan Review.
