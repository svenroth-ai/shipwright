# Iterate Spec: r1d-silent-gates

- **Run ID:** iterate-2026-11-28-r1d-silent-gates
- **Type:** change
- **Complexity:** medium. It touches the resolver, five historical git readers in `shared/`, the bloat anti-ratchet CLI, this repo's pre-commit hook and a required CI workflow (`bloat-check.yml`, CI supply chain).
- **Status:** implemented

## Goal
This is the sixth R1 PR of the root-files campaign (BRIEF `.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`, items 4.1, 11.7.4 and 14.4; split recorded as 12.14). R1c taught every reader on DISK to find a moving file in either place. Readers of a HISTORICAL commit still asked for the root name, because `rel_at(key, commit)` ignored the commit. After the move they would see "absent" and treat it as harmless. The bloat gate would diff against an empty baseline. The AC-baseline growth check would call a move a bootstrap and miss growth. The events-layout CI would read no layout, and the rollout snapshot no manifest. Separately, the bloat anti-ratchet skipped itself when no baseline was found, and the pre-commit hook only ran it if the root file existed. Moving or deleting the baseline turned the gate green without checking anything.

## Design
1. **`rel_at(key, commit, root)` answers per commit.** It gives the new path if it exists in that commit's tree, else the root path (`shipwright_layout.locate_at`, `git ls-tree --full-tree`, which tells "not in that tree" from "git could not answer"). With `commit=None` it checks the working tree. "Migrated?" is decided by the new path existing, never by the root blob missing, because after R3 the root holds a pointer stub (14.4). An unreadable repo or commit reads as "root", so the caller's own `git show` reports the real error. A file that does not move always answers its root path. `root` is required, and every caller already has its repo.
2. **Every historical reader passes its repo.** That covers the events-layout CI, the rollout snapshot's manifest (both keys), the supply-chain ack's legacy leg, and the test-results backfill check (commit and parent reads). The backfill check's working-tree status check now accepts either place.
3. **The AC-baseline growth check reads the parent where the baseline lived then.** When the given baseline is the registry's AC baseline (either place), the parent read uses `rel_at(..., parent)`. A baseline given at any other path is read as before.
4. **The bloat gate fails closed in this repo.** `anti_ratchet_check.py --require-baseline` exits 1 (JSON reason `missing-baseline`) when the baseline is in neither place. This repo's pre-commit hook always runs the check with it, and so does `bloat-check.yml`. The workflow reads the base commit's baseline where it lived at that commit, and the head baseline where it lives now, both through the new `shared/scripts/tools/shipwright_rel_at.py`, which is the same answer for YAML and bash. A consumer project with no baseline still skips (default unchanged).
5. **Docs.** The guide's bloat table and the hooks reference describe the required mode. The stale "twelve" derived-snapshot counts now read thirteen paths (R1c-3 added the new place of the test-results snapshot).

## Acceptance Criteria
- [x] AC1: `rel_at` answers the place a moving file has at each commit and in the working tree. "Migrated" means the new path exists, even with a root copy (stub) beside it. An unknown, empty or dash-led commit reads as the root. With `strict=True` it raises instead of guessing. A file that does not move stays at the root.
- [x] AC2: The CLI gives YAML and bash the same answer. It exits 2 on an unknown key and 3 when git cannot answer for the commit.
- [x] AC3: Growth of the AC baseline across a move is reported as growth, not as a bootstrap.
- [x] AC4: The events-layout CI and the rollout snapshot read a moved file at the commit they inspect.
- [x] AC5: With `--require-baseline`, a baseline missing from both places fails the anti-ratchet, and one in the new place is found. Without the flag a consumer repo still skips.
- [x] AC6: This repo's pre-commit hook and `bloat-check.yml` run the required mode, and the workflow no longer reads `<base>:shipwright_bloat_baseline.json` by its root name.

## Spec Impact
NONE. In an unmigrated repo the new path never exists at any commit, so every `rel_at` answer is the root path it was before. This repo always has its baseline, so `--require-baseline` changes nothing here either. Consumer projects keep the default skip.

## Out of Scope
- **R1d-2:** the `.gitignore` work (managed block, root re-includes for the unanchored `shipwright_*_config.json`, self-heal detecting basename rules, template lock/tmp rules, `git check-ignore --no-index` test), `inline_suppressions` in `SENSITIVE_PATH_RE`, the `pr-review-run.yml` regex and A4, and the workflow templates consumers copy.
- **R1e:** `LayoutError` handling per module.
- **R3:** the move itself.

## Affected Boundaries
Affected: the required `Bloat Check` workflow (CI supply chain) and this repo's git pre-commit hook. Also the F11 verifiers that read history: the supply-chain ack legacy leg, the test-results backfill check, the AC coverage ratchet's growth check and the project-gate rollout snapshot. The events-layout CI check is affected too.

## Confidence Calibration
- **Boundaries touched:** one resolver function's signature (all 6 production callers and 1 test updated), a required CI workflow, the git pre-commit hook and the anti-ratchet CLI.
- **Empirical probes run:**
  1. A search for every `rel_at(` caller.
  2. A negative control: the new tests on a copy of `origin/main` failed 7 of 7.
  3. The CLI run against this repo (root answer at HEAD and in the working tree, exit 2 on an unknown key).
  4. A check of the workflow step order: uv is installed before the base-capture step that now calls `uv run`.
  5. A full F0 run.
- **Test Completeness Ledger:**

| Behavior | Status | Evidence |
|---|---|---|
| AC1 rel_at per commit, working tree, unknown/empty/dash commit, strict mode, non-moving key | tested | test_shipwright_paths_silent_gates.py::test_rel_at_answers_the_place_the_file_has_at_each_commit |
| AC1 migrated = new path exists, even beside a root stub (14.4) | tested | ::test_migrated_means_the_new_path_exists_never_that_the_root_blob_is_missing |
| AC2 CLI parity, unknown key (2), unreadable commit (3) | tested | ::test_the_cli_gives_yaml_and_bash_the_same_answer |
| AC3 AC baseline growth across a move | tested | ::test_ac_baseline_growth_across_a_move_is_growth_not_a_bootstrap |
| AC4 events-layout CI and rollout snapshot read the moved file | tested | ::test_the_events_layout_ci_reads_the_sync_config_where_it_lives_at_the_commit, ::test_the_rollout_snapshot_reads_the_project_manifest_where_it_lives_at_the_commit |
| AC5 anti-ratchet fails closed, finds the new place, consumer default unchanged | tested | ::test_the_anti_ratchet_fails_closed_without_a_baseline_when_one_is_required |
| AC6 hook and workflow use the required, per-commit mode | tested | ::test_this_repos_bloat_gates_require_the_baseline_and_resolve_it_per_commit |
| integration: the anti-ratchet CLI runs in its own interpreter against a real directory; readers run against real git histories | tested | the subprocess cases above |

- **Confidence-pattern check:**
  - **Depth.** Each case drives the real reader against a real git history in which the file moved.
  - **Breadth.** Every `rel_at` caller has a case or shares a tested path. The ack store and the backfill check use the same function with their repo.
  - **Integration composition.** The anti-ratchet and the CLI run as subprocesses. The workflow and hook are pinned by a content test, because they are not Python.

## End-to-End Verification
- **Surface:** cli
- **Runner:** pytest over the silent-gates, resolver, guard, layout and anti-ratchet test files.

## Internal Plan Review (opus-plan-reviewer)
Verdict: approve with small revisions. Fixed: a test that a root stub beside the new file answers "new" (14.4 was untested because every test deleted the root blob); an empty or dash-led commit is no commit (an empty rev would read the index); "both copies at one commit answer new" is documented (a history reader reads, the on-disk lookup is where two copies are an error); the workflow's head lookup has its own `set -e` assignment and the base read warns before falling back to empty; the hook comment no longer overstates (a staged deletion with a copy on disk is caught by CI). Recorded in BRIEF 12.14 (b): staged-baseline read from the index and the two-copies traceback (R1e), `fork_run.py` and "R3 only after R1d-2" (R3), the webui vendored checker hash (webui card).

## Internal Architecture Review (architecture-internal-reviewer)
Verdict: approve. Two medium: "could not ask git" read as "root" (fixed: `strict=True` raises `GitReadError`, the CLI exits 3, the AC growth check warns), and the inline head lookup (fixed). Low: `rel_at(commit=None)` vs `path()`'s LayoutError (R1e), consumer templates as a hard prerequisite (BRIEF 12.14 (b)), an optional literal guard (R1e).

## External Plan Review
GPT revise, GLM revise. Fixed: the silent base fallback now warns, the unresolvable commit is a distinct exit (both converge with the internal reviews). Answered: a shallow checkout cannot hide the base commit (the job checks out with `fetch-depth: 0` and verifies the base with `cat-file -e`); the helper runs from the PR head like every other script in this `pull_request` job (read-only token, no secrets), so it adds no trust the PR did not already have; the pre-commit hook is this monorepo's own (`install-hooks.sh`), not shipped to consumers. Recorded: the staged-deletion edge (R1e).

## Architecture Review
External (`--mode architecture`): GPT approve with no findings; GLM approve with two low findings (the alternative is correctly rejected; the fail-closed flag lives in two non-Python places, pinned by a content test).

## Spec Review (spec-reviewer)
PASS. Low notes: the spec named `cat-file -e` where the code uses `ls-tree` (aligned); the JSON `missing-baseline` output was untested (now tested); the ack store and backfill check had no direct case (the backfill status check now has one).

## Code Review (code-reviewer)
Approve. Medium, fixed: `build_bloat_diff` rendered the new `error` status (missing or malformed baseline) as a green check while the job failed; it now says the gate could not run, with a test. Low, fixed: the "other place" wording with an explicit `--baseline`; the CLI writes LF on Windows (bash `$(...)` would keep a CR); `ls-tree --full-tree` so the answer matches `git show <sha>:<path>`; a backfill status test for both places.

## External Code Review
GPT revise, GLM approve. Fixed: a deleted checker no longer switches the pre-commit gate off (it blocks while the repo tracks a baseline in either place; a repo with neither has no bloat gate, which keeps the compliance hook tests' temp repos committing - caught by F0); strict mode now checks the commit for a file that does not move too (CLI exit 3); the workflow/hook test pins the commands, not comments. Recorded for R3 (BRIEF 12.14 (b)): the backfill status check rejects a staged move of the snapshot (two lines or a rename).

## Doubt Review (doubt-reviewer)
High, fixed: `test_shipwright_monorepo_profile.py` asserted the workflow spells the baseline by its root name; it now asserts the per-commit lookup. Low: `ls-tree` resolved paths from `-C root` while `git show` resolves from the top level (fixed with `--full-tree`); a commit on an old branch that has the checker but predates the baseline now blocks (accepted: the baseline was added before the checker's pre-commit wiring, and `--no-verify` is not the answer, the baseline is); a deleted checker (fixed: it blocks). Info: the webui vendored checker hash (BRIEF 12.14 (b)). Not disproved: unmigrated equivalence, the workflow on push/dispatch/first push, strict mode on tags, abbreviated SHAs, `HEAD~1` and refs with slashes.
