# Baseline package P3 (spec chain): measure

Date: 2026-10-31 · unit P3 of `2026-10-31-baseline-package-BRIEF.md` · run `iterate-2026-10-31-p3-spec-chain` · tool: `shared/scripts/tools/spec_chain_cli.py` (read-only). Every number below was produced by that tool on this branch. Nothing here was checked by a human.

## Verdict, plainly

| Bar (from the brief) | Result |
|---|---|
| Lookup "which specs shaped AC X" answers for at least 10 ACs with history | **Met.** 39 ACs have history; for all 39 the lookup returns at least one run with a plan or a PR; for 32 of the 39 at least one run has both. |
| Replay of the 20-iterate sample (seed 20261031) resolves 20 of 20 for runs recorded after the change | **Not measurable yet, so not met.** No run was recorded after the change when this was measured (this run is the first). The mechanism is built and tested, the number is not available. |

## 1. Lookup

`spec_chain_cli.py coverage` lists the ACs that have any history; `lookup --ac X` returns, per run: how the run was tied to the AC (`spec-text` = the run id written in the AC's text in `spec.md`; `event` = `affected_acs` on a recorded event), the run's plan file and its kind (`field`, `convention`, `legacy`, `adr`), and the PR number.

- 39 ACs with history. All 39 come from the run ids that the catalog already carries in AC text. That is the same ~13% of 289 ACs the spec-chain measurement found: the tool makes that history queryable and joins it to plans and PRs, it does not create AC history that was never recorded. New AC-level history accrues from `affected_acs` (P1) on recorded events.
- Lookup answers with a plan or PR: 39 of 39. With both: 32 of 39 (the 7 others lack a PR number found through git, or a plan file).
- `lookup --fr FR-xx.yy` (runs by `affected_frs`, each with plan and PR) covers the other 87% of ACs at requirement level only.
- Honest limit: for older runs the plan is found by naming fallbacks, labelled `legacy` or `adr`; the answer "no plan" is returned as `null`, never guessed.

## 2. Replay of the 20-iterate sample

`spec_chain_cli.py replay --seed 20261031 --n 20` draws 20 `work_completed` iterate events that name an FR. Two caveats: the event log has grown since the earlier measurement (pool 231 now, 216 then), so the same seed cannot give the same 20 runs; and the measurement script of the earlier report is not in the repository.

Backfilled picture, runs recorded before the change (not the bar, shown for scale):

| | earlier report | this tool |
|---|---|---|
| FR to plan to PR resolves | 14 of 20 | 14 of 20 |
| tied to a specific AC | 1 of 20 | 1 of 20 |

Unresolved are old runs: legacy `ADR-0xx` ids with no plan file, and runs with no plan document. The tool does not invent a plan for them.

Post-change cohort (the bar): `replay --since <timestamp>` takes runs recorded at or after a boundary, samples 20 with the seed, and counts a run as resolved only if its event carries `plan_path`, the plan file is found, a PR is found, and `affected_acs` or `catalog_gap` is present. A run that forgot the field is counted as a failure, not left out. Measured with the boundary at the start of today: 4 eligible runs, all recorded before this change (P1, P5, the campaign brief, a dependency bump), 0 resolved, `enough_for_n: false`. That is the correct answer for them and says nothing about the new mechanism.

This run, the first one recorded after the change: `plan_path` is on its event (stamped by F5b from the stub), the stub is the full kind (it declares a catalog gap), `catalog_gap` is on the event. Its PR number resolves only after the squash merge (or sooner if added with an `event_amended`); at measure time it is not found, so even this one run is 0 of 1 on the full chain until merge.

## 3. What the operator needs to decide

- The 20-of-20 bar can only be tested after 20 runs are recorded after merge. Proposal: re-run `replay --since <merge time>` once 20 such runs exist (about a week at the current rate), and judge then. Until then P3 is "built and tested, bar pending".
- Campaign order puts P5 before P4; P5 is already merged. Stopping for the operator on a failed measure is the brief's rule; this bar is pending rather than failed, so the work is delivered and the decision is left open.

## 4. What was not done

- The traceability matrix is not regenerated on a schedule. It is regenerated at each release by the existing changelog step (`refresh_compliance_docs.py`); it was stale because no release ran in three weeks. The matrix still links events, not plan files or PRs.
- A run-id to PR map is not cached; `lookup` runs one `git log` per run. Fine for a command-line lookup.
- `pr` is not written automatically on the event: the PR number exists only after the push. The documented route is an `event_amended`; otherwise git (the `Run-ID:` trailer of the squash commit) is the source.
