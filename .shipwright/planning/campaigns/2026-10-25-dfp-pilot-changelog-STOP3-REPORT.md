# Changelog pilot, stop 3: full model runs of the converted plugin (2026-11-26/27)

Two rounds of runs were made. Each round played every scenario with an Opus subagent. The subagent followed the thin `SKILL.md` and called `release.py` in a throwaway project, with a local bare remote and a `gh` stub. The plugin came from a `git archive` export, never from the installed cache. The harness was the same as at stop 2 (`runscenario.py` build and collect), copied into the session scratchpad.

- **Round 1:** tree `t-2e023947` (`main` at 2e0239474), 43 runs.
- **Round 2:** after fix PR #1112, tree `t-c2ff04d5` (`main` at c2ff04d57), the 16 affected runs.

Every run was compared with the pinned replay trace of the same scenario and with its stop-2 run.

## Result in one paragraph

The model drives the converted plugin as well as it drove the old prose. Round 1 found one new defect, F-S3-1 (D109): the release guard blocked the prescribed tag push after the PR merge. It also showed that three stop-2 pinned failures were never fixed (D21, D22, D23), because no unit had taken them. The golden freeze kept CI green on those defects. All four, plus operator decision D25, were fixed in #1112. In round 2 all 16 runs reach the outcome the replay or the prose expects:
- the autonomous merge runs push the tag after the merge;
- drops-layout releases finish from a clean tree, including Step 7;
- a project without decision or ADR folders releases;
- consumed tracked drops are committed;
- unrelated files stop the release before any commit.

There were no model errors against clear prose.

Limits:
- One run per scenario.
- Exit codes are self-reported. Only the outcome is evidence: refs, tags, PRs, release pages, gh calls and the tree.
- S11b, S12c and S16f inject their fault differently from the replay (stop-2 class B).
- Single-step replays show the model's later steps as extras.
- There is no fork sample, because P2-op made none. So the fork comparison of programme P23 is skipped.
- S14d, S18c, Q5 and `pr-body` (D107) are not in the harness modules yet, so they have no model run. The re-pin adds their frozen traces.

## Round 1 (43 runs, tree t-2e023947)

- **Full release flow, outcome same (11):** S1l, S2gl, S11al, S13l, S14al, S14bl, S14cl, S18bl, S19l, S10d, S16el.
- **Correct stop, outcome same (27):** S1d, S1dl, S1tl, S2ad, S2gd, S2ud, S3d, S3bd, S4d, S5ad, S5bd, S6d, S7ad, S7bd, S7cd, S8d, S9d, S11bl, S15l, S16al, S16bl, S16cl, S16dl, S16fl, S17al, S17bl, S18al. Several of these "correct stops" are the replay's pinned defects:
  - D23 in every drops run that reached Step 6;
  - D21 in S1dl;
  - D22 in S1tl;
  - D25 in S15l and S16cl.
- **Real defect F-S3-1 / D109 (5):** S2al, S2ul, S12al, S12bl, S12cl. After `gh pr merge` HEAD is the merge commit. The guard parsed `git push origin refs/tags/vX` (also `tag vX` and `--tags`) as a push with no refs. It fell back to the current branch (`main`), called it a trunk push and judged HEAD instead of the tag, so the push was denied.
- **Harness:** S2gl-1 was blocked by the auto-mode classifier before the push was authorised. It was re-run as S2gl-2, with the same outcome.

Stop-2 fixes confirmed live:
- D12/F2: the preview writes nothing (S18a, S18b).
- D24/F5: a `master` trunk (S14c).
- D7/F4: the branch is pushed before the PR.
- F8: the content floor (S16b).
- D9/F11: `--from` is gone (S19).

## Fix #1112 (merged 2026-11-27)

- **D109:** a push that sends only tags is judged by the tag's commit. Branch, combined and `--follow-tags` pushes, `HEAD:refs/tags/vX`, and a `:` refspec next to a tag are still judged by HEAD.
- **D21:** Step 6 names only paths that git knows about.
- **D22:** the consumed drop deletions are committed with the release.
- **D23:** the event files written by Step 5.5 are committed with the release.
- **D25** (operator, 2026-11-26, "stop first"): unrelated changes stop Step 6 with `unrelated_changes` before anything is staged.
- **Golden traces:** eight traces changed. They are recorded as approved deltas that cite FINDINGS, and there is no repin.
- **CI:** the first run failed on the event-log reference registry, because the new `release_sync.py` named the log in a docstring. The file was registered as prose. After that, everything except PR Review was green, and the PR was admin-merged.

## Round 2 (16 re-runs, tree t-c2ff04d5)

- **Full release flow, outcome same:**
  - S2al, S2ul, S12al, S12bl: D109 fixed live.
  - S2ad, S2ud: drops layout plus autonomous merge.
  - S1d, S2gd: drops layout, guided, through Step 7.
  - S1dl: D21.
  - S1tl: D22.
- **Correct stop, outcome same:** S15l, S16cl. D25 stops with the paths named, before any commit.
- **S12cl:** the guard now lets the tag push through, and the remote refuses it as the scenario intends, so the release stops. The only difference from the replay is in the gh calls. This is known class B: the replay skips the push and fails the release page instead.
- **S3bd, S5bd, S6d:** these are single-step replays, so the model's run through Step 7 is an expected extra. All three now finish on the drops layout.

Coverage gap closed: Step 7 is now exercised on the drops layout.

## Canary release (2026-11-27)

One real release ran in a throwaway private GitHub repo, which has since been deleted. An Opus subagent drove the installed plugin (cache synced to `c2ff04d57`) with the release guard hook active. The project was the S1 fixture: a release branch with one `feat` and one `fix` commit, and two drops committed on `main`.

- The flow ran in this order:
  1. prepare
  2. preview (dry run, nothing written)
  3. aggregate
  4. sync
  5. commit-and-tag (the audit passed)
  6. push the branch, then `gh pr create`
  7. record-event
  8. close-phase, with status "waiting"
  9. operator merge
  10. push-tag
  11. release page
  12. close-phase, with status "ok"
- Every step exited 0. The closing check passed 8 of 8 and the tree ended clean.
- Checked on GitHub:
  - the PR is merged;
  - `v0.1.0` is on the remote and peels to the release commit;
  - the release page is published.
- The guard denied nothing. That includes `git push origin refs/tags/v0.1.0` after the merge, the D109 case.
- The project used the legacy event log. The drops layout was covered by round 2 and is covered again by the first monorepo release.

Notes (not defects; after the campaign at most):
- The final closing summary text still reads as it did before the merge ("tag is pushed after the PR is merged", "PR opened"), although the checks themselves are right.
- The release-notes condenser (an LLM step) turned the vacuous bullet "A first fix" into "Fixed a bug that the changelog does not describe".
- aggregate writes empty `decision_log_index.md` and `adr/INDEX.md` when there are no decision drops.
- With no CI in the project, `ci-security.json` is reported as regenerated but is missing, so there are 6 evidence documents.
- `SHIPWRIGHT_PLUGIN_ROOT` was not in the subagent's environment, so it used the installed path instead.

## Operator decisions (2026-11-27)

- **Confirm what was built: all kept as built.** This covers D34/D38, D37, D39/D40, D44, D45, D51, D60, D96, D92 and D100.
- **Gaps:** D89, D90, D63, D102/D105, D103 and D69/D71 go to the follow-up campaign, D89 first.

## Re-pin (step 5)

`golden_lock.py --plugin shipwright-changelog --repin` was run in the same PR as this report.
- **New frozen scenarios (D107):** each trace was recorded by the replay driver and is checked through the CLI driver.
  - S8b: a categorised hand-written `[Unreleased]` entry, Q5.
  - S14d: the default branch is `develop`, and the release is on `main`.
  - S14e: `pr-body`, Q10. The trace masks the body, so the scenario's check pins it on the CLI pass.
  - S18c: Edit, then Cancel.
- **D99:** the pinned prose is now a byte copy of the live `SKILL.md` and its references. The frozen shell chains are now pinned by their own hashes.
- **Lock:**
  - 53 approved deltas became moot, so `approved_deltas.json` is now `[]`.
  - Every changed lock entry is either the `after` of an approved delta or one of this change's own edits.
  - Four traces were added.
- **Tests:**
  - changelog root: 808 passed, 2 skipped;
  - `--check` is ok;
  - ruff and `verify_local.py` are green.
- **Reviews:** code and doubt reviews found nothing high. Two medium findings were fixed: the per-chain hash, and the note on the masked body.

## Observations (not defects; after the campaign at most)

- **Empty preview (S3d, S4d):** with no drops, the model still presents the empty preview, and the real aggregate then refuses. Stopping at an empty preview would be new behaviour.
- **Patch bump for BREAKING (S3bd):** a **BREAKING** drop under a `fix` commit gets a patch bump. This is Q9, after the campaign.
- **Untracked `triage.jsonl`:** close-phase reports `tree_clean ok` while `.shipwright/triage.jsonl` (written by the release audit, stop-2 P5) is untracked. To check whether that is on purpose.
- **Audit exit code (S14bl and others):** the release audit exits 0 while its findings JSON says `any_fail: true`. Step 6 gates on the exit code, as the old prose did. This is a question for the compliance plugin.
- **Re-dated section (S6d):** an identical existing `[1.3.0]` section is rewritten in place under the new date, and the preview does not mention the date change.
- **Default-branch lookup:** in every run it fails against the local bare repo, which has no symref HEAD, so the trunk falls back to `main`. That is the correct fallback, and it is a property of the harness.

## Lesson for the next plugin

Stop 2 listed D21 to D23 as "pinned failures, fixed as approved deltas in P3 to P8", but no unit took them. Because the golden freeze reproduces a pinned defect, CI stayed green on all three. Before a campaign closes, a check must map every stop-2 finding to a unit or to an explicit operator decision.
