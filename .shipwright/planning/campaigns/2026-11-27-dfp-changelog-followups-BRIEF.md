# Campaign brief: changelog pilot follow-ups (`dfp-changelog-followups`)

Date: 2026-11-28 · Status: rev 2, ready, not started · Rev 1 (2026-11-27) was the input list written at the close of stop 3.
Sources: `2026-10-25-dfp-pilot-changelog-FINDINGS.md` (D-numbers), `-LEARNINGS.md` (stop 3), `-STOP3-REPORT.md`, `-STOP3-PLAN.md` (Q3, Q9), an Opus review of rev 1, and the operator decisions of 2026-11-28 (section 5).
Branch strategy: `serial`. Build, PR, checks green, merge, then the next unit from a fresh `origin/main`. Every unit has a `depends_on` edge on the one before it, so no two units build at the same time: most of them touch the same release files.

## 0. Goal

A release finishes through the plugin with any merge method, on this squash-only repo too, with no hand work and no lifting of the guard. Code never ships without its changelog entry. After that: close the guard gaps, a few small items, and the two confirmed features Q3 and Q9.

These are product changes, each one confirmed by the operator. The pilot's one-to-one conversion rule does not apply.

## 1. Units

| ID | Title | Complexity | depends_on |
|---|---|---|---|
| U1 | Root `pyproject.toml` and `uv.lock` as release manifests (D111) | small | |
| U2 | Guard and close-phase accept a proven merge commit (D110 part 1, D113(1)) | medium | U1 |
| U3 | push-tag after a squash or rebase merge: proof, retag, record, stop on foreign commits (D110 part 2, D112) | medium | U2 |
| U4 | Autonomous merge: pick the method, pin the head, stop when behind | medium | U3 |
| U5 | Pipeline: a phase can wait for the release PR merge (shipwright-run) | medium | U4 |
| U6 | Changelog in pipeline mode waits for the merge, then closes (D113(7)) | medium | U5 |
| U7 | Guard reads the trunk from the run state, and the guard gaps (D89) | medium | U6 |
| U8 | Small items: D113(3), D113(6), D69, D71(3)(4)(5) | small | U7 |
| U9 | Q3: refuse a hand release while an automatic one runs | medium | U8 |
| U10 | Q9: a pending note can be marked "breaking" | medium | U9 |

There is no stop-and-ask unit for D112: stop and report is part of U3 (operator, section 5).

Notation used below: **R** is the release commit in the release record (the one the audit checked). **H** is the PR head at merge time. **S** is the merge commit on the base (`gh pr view --json headRefOid,mergeCommit,state,baseRefName`).

### U1: root `pyproject.toml` and `uv.lock` as release manifests (D111). Small.

- **Scope.** `shared/scripts/lib/manifest_sync_core.py` knows only `package_json`, `marketplace_json` and `package_lock_json`. Add two formats, `pyproject_toml` (the `version` in `[project]`) and `uv_lock` (the `version` of the root package in `uv.lock`), in a new `shared/scripts/lib/manifest_sync_toml.py`. Change only lines inside the target table, keep every other byte, and parse the result again with `tomllib` before writing. Declare both files in the repo's `shipwright_changelog_config.json`.
- **Files likely touched.** `manifest_sync_core.py`, the new `manifest_sync_toml.py`, `shipwright_changelog_config.json`, `plugins/shipwright-changelog/skills/changelog/references/manifest-sync.md`, tests in the `shared/tests` root.
- **Done when.** An L1 test on a copy of this repo's real root `pyproject.toml` and `uv.lock` bumps both to a new version and changes nothing else (byte diff). A `pyproject.toml` with no `[project]` version, or a lock with no root package, is refused with a named error. `release.py sync` on a scratch project with all five formats moves every slot to one version.
- **Risks.** This is new parser code in `shared/`, and it ships to plugin consumers. A table-scoped edit must not hit a `version` key of another table (`[tool.*]`, a dependency entry in the lock); a test pins each case.

### U2: guard and close-phase accept a proven merge commit (D110 part 1, D113(1)). Medium.

- **Scope.** The release record (`.shipwright/runtime/release_state.json`) keeps `commit = R`. It gains an optional `published_commit = S`, `merged_via` (`merge`, `squash` or `rebase`) and a proof block `{pr_head, tree, base_before}`. Nothing writes these fields yet (U3 does), so this unit stays inert on `main` until U3 lands. That is why it goes first: `main` never has a writer whose commit the guard denies.
  - A new stdlib-only `plugins/shipwright-changelog/scripts/hooks/release_merge_proof.py`, next to `release_descent.py`, holds the one rule both callers use. A judged commit passes when `release_descent.is_the_release(R, …)` holds, or when it equals `published_commit` and `git rev-parse S^{tree}` still equals the recorded tree. The tree check stops a hand-edited record from approving any commit.
  - The release guard and close-phase use that rule. In `release_verify.py`, `tag_local` and `tag_remote` accept the tag on `published_commit`, and `pr_state` accepts S on the base (today `on_base(R)` fails after a squash).
  - D113(1): the closing summary in `release_close.py` says "pushed" or "waiting" from whether the tag is really on origin, not from `tag_may_be_pending`.
- **Files likely touched.** `release_guard.py`, the new `release_merge_proof.py`, `release_verify.py`, `release_close.py`, their tests, `docs/hooks-and-pipeline.md`.
- **Done when.** L1 tests on real git with a bare remote: a record with a valid proof lets the guard allow the tag push of S, and close-phase passes 8 of 8. A record whose tree does not match S is denied by both. A record without the new fields behaves exactly as today (all current changelog tests stay green). The second close-phase summary says "pushed" once the tag is on origin.
- **Risks.** `release_guard.py` is 226 lines against the 300 cap, and U7 adds more. Put the new logic in the new module, not in the guard.

### U3: push-tag after a squash or rebase merge (D110 part 2, D112). Medium.

- **Scope.** After a squash or rebase merge, `release.py push-tag` accepts S only when all three hold:
  1. H is R, or an event-only descendant of R (`release_descent.is_the_release`). This catches commits pushed to the branch after record-event.
  2. S is an ancestor of the freshly fetched base. This catches a force-pushed base.
  3. `tree(S) == tree(H)`.
  1 and 3 together carry the audit of R over to S. 3 also enforces D112: any foreign commit that landed changes the tree. **Nothing weaker is accepted.** The rev-1 fallback "same CHANGELOG section and manifest versions" is rejected: that check is exactly what let #1115 ship without its entry.
  - **When 3 fails: stop and report** (`foreign_commits_on_base`). Name the first-parent commits from `merge-base(H, S)` to S minus the PR's own commits, and their pending drops. Tag nothing, write nothing. The operator decides what follows (for v0.37.0 it was addendum #1116).
  - **When all three hold:** write `published_commit`, `merged_via` and the proof into the record. If `git ls-remote` shows the tag is not on origin, retag it in code (`git tag -f -a vX S`, the message names R). Never move a tag that is already on origin. Then return `git push origin refs/tags/vX`. A re-run with the same record is idempotent (today `named != commit` refuses it).
  - **A merge commit keeps today's path:** tag R. Foreign commits merged next to it are not in R's tree, so their drops stay pending for the next release. That is correct and satisfies D112. Do not "fix" it.
  - Rebase merge: same proof; listing the foreign commits is best-effort. A merge queue or a conflict resolved in the web UI changes the tree, so it is refused. That is correct.
  - push-tag now writes for the first time. Update its docstring, `SKILL.md`, `release-workflow.md`, `rerunning-a-release.md` and `docs/hooks-and-pipeline.md`.
- **Files likely touched.** `release_push.py`, `release_commit.py` (record helpers), `SKILL.md` and the two references (frozen), tests.
- **Done when.** An L1 end-to-end test on real git, with a bare remote and the `gh` stub reporting `mergeCommit`: prepare, commit-and-tag, PR, squash merge, push-tag, tag push through the guard, close-phase 8 of 8. The same with a rebase merge, and with a merge commit (today's path, tag on R). A foreign commit merged onto the base before the squash ends in `foreign_commits_on_base`, names that commit and its drop, and leaves tags and record unchanged. A second push-tag run gives the same answer. A tag already on origin is never moved.
- **Risks.** The window between the check and the merge cannot be closed under squash. A foreign commit that lands in it ends in a refusal, never in a silently wrong tag.

### U4: autonomous merge (operator decision: stop when behind). Medium.

- **Scope.** Today the autonomous path runs `gh pr merge --merge`, which fails on this repo.
  - Pick the method from `gh repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed`, and prefer a merge commit (no retag needed).
  - Always pass `--match-head-commit H`.
  - Before a squash or rebase merge, check that the fetched base tip is an ancestor of H. If the base moved, **stop**: the release must be restarted. No automatic rebuild, and no `gh pr update-branch` (that would break check 1 of U3).
  - The merge stays one literal outward line in `SKILL.md`, so the guard sees it. A `release.py` call (for example `merge-ready`) answers which line to run, or why none.
  - Guided mode: a person merges in the web UI, so only U3's proof applies. The `waiting_for_merge` text says "merge while the branch is up to date with the base".
- **Files likely touched.** `release.py` and a new or existing `release_*` module, `SKILL.md` and `release-workflow.md` (frozen), the guard command matcher if the new merge line is not recognised yet, tests.
- **Done when.** L1 tests with the `gh` stub: a repo allowing only squash gets a squash line with `--match-head-commit`; a repo allowing merge commits gets `--merge`; a base that moved stops with a plain message telling the operator to restart, and nothing is merged. The guard allows the chosen line during a release.
- **Risks.** Touches `SKILL.md`, so PR Review may block (see section 3).

### U5: the pipeline can wait for the release PR merge (shipwright-run). Medium.

Operator decision: a pipeline-started release also waits for the merge before tagging. Today `mode: pipeline` never waits: it pushes the tag on R before the merge. After a squash that tag is off the trunk, and the next release's `tag --merged HEAD` (D100) no longer sees it. The pipeline must come back to the release after the merge and close it. That needs this unit in `plugins/shipwright-run`, before the changelog side (U6) can use it.

- **What must change today.** A phase result is `ok` true or false only (`single_session/result_contract.py`), and the lifecycle turns it into `done` or `failed`. `phase_state_machine.next_phase_task` then moves from `changelog` to `deploy`, or ends the run. The loop (`orchestrator_pkg/single_session_loop.resolve_next_dispatch`) knows one "waiting for a person" answer, `ask_human`, and only for a phase gate past its retry cap. Nothing can say "this phase is not done, it waits for something outside the run".
- **Scope.** A phase result can say it waits for an outside event, with a reason (`waiting_for_merge`) and the PR URL. The loop then answers a waiting action (no new dispatch, nothing failed, the run is not complete, deploy is not scheduled). The resume card names what to do ("merge PR …, then resume"). On resume, the same changelog task is dispatched again. A waiting phase must never be read as done by the run-completion check.
  - Prefer a shape that needs no new value in `shared/schemas/run_config.v2.schema.json`: the WebUI reads that schema. If a new phase status turns out to be needed, that is a STRICT-STOP for the operator.
- **Files likely touched.** `single_session/result_contract.py`, `orchestrator_pkg/single_session_loop.py`, `phase_task_lifecycle.py`, `plugins/shipwright-run/agents/phase-runner.md`, `skills/run/references/single-session-loop.md`, `docs/hooks-and-pipeline.md` (between-phase actions), `docs/guide.md` chapter 4, tests in the shipwright-run root.
- **Done when.** A loop test: a changelog result that waits leaves the task not done, the run not complete and deploy not scheduled; the loop reports the waiting action with the PR URL; on resume the changelog task is dispatched again; a second result `ok` moves on to deploy, or ends the run with `deploy_target: none`. Every current shipwright-run test stays green.
- **Risks.** This is the pipeline's core loop. If the change grows past medium (for example a schema change, or both the multi-phase loop and the single-session loop), split it and stop for the operator before building.

### U6: changelog in pipeline mode waits for the merge, then closes (D113(7)). Medium.

- **Scope.** `release_verify.waits_for_merge` is true for any release from a feature branch, `pipeline` included. In pipeline mode the first pass ends after record-event and close-phase "waiting" with the waiting result of U5. The second pass (after the merge) runs push-tag (with U3's proof), the release page and close-phase "ok". D113(7): `SKILL.md` says plainly that close-phase runs twice in a release that waits for the merge.
- **Files likely touched.** `release_verify.py`, `release_push.py`, `release_close.py`, `release_gates.py` if needed, `SKILL.md` and `release-workflow.md` (frozen), the `driven` scenarios of the golden harness, `docs/hooks-and-pipeline.md`.
- **Done when.** An L1 end-to-end test of a driven release on real git: the first pass leaves the tag local, nothing pushed, and the waiting result; after a squash merge with the `gh` stub, the second pass pushes the tag on S, publishes the page and passes 8 of 8. A release on the trunk does not wait, as today. The golden traces of the driven scenarios move only as approved deltas citing D113(7) and this unit.
- **Risks.** Changes what a driven release does: every changed trace needs an approved delta, and a new driven scenario needs a re-pin.

### U7: the guard reads the trunk from the run state, and the guard gaps (D89). Medium.

- **Scope.** D89: `release_guard.py` keeps `TRUNKS = ("main", "master", "develop")`, while `release.py` uses `release_event.trunks()`. `prepare` already stores `trunk` and `trunk_source` in the run state. Move the `trunks()` rule into a stdlib helper in `scripts/hooks/` and let both read it from the run state. The hook must not ask the remote on every command: that would bring D90 into the hook. Then fix the gaps the stop-3 doubt review recorded:
  - `git push origin @` means HEAD;
  - a `refs/heads/*` glob means every branch;
  - `--tags` sends every local tag, so a stray tag besides the release tag is judged;
  - `HEAD~3:refs/tags/vX` off the trunk is judged by its source commit, not by the local tag.
- **Files likely touched.** `release_guard.py`, `release_guard_commands.py`, a new hooks helper, `release_event.py`, tests, `docs/hooks-and-pipeline.md`.
- **Done when.** Guard tests on real git: a repo whose default branch is `production` protects `production`; with the default `main`, a push to `master` is not a trunk push; each of the four forms above is judged as stated; all current guard tests stay green.
- **Risks.** The guard file is near the 300-line cap; split before it crosses. A deny that should not happen blocks ordinary pushes: keep the "no release in progress, never block" test.

### U8: small items. Small.

- **D113(3):** aggregate writes no `decision_log_index.md` and no `adr/INDEX.md` when there are no decision drops (or writes them only if they already exist).
- **D113(6):** the upgrade note reads well as a changelog bullet (today: "Not to upgrade. … see below").
- **D69:** S12a's frozen trace equals S2a.legacy's byte for byte. Give S12a a release-page fixture that differs from S2a's, so its trace records the page step it judges. The trace change is an approved delta citing D69.
- **D71(3):** an invalid B-item regex and an unknown `scope` in `plugin_conversion.json` exit 2. **D71(4):** correct the A10b and A11 reasons in `plugin_conversion.json`. **D71(5):** a test for a real `uv run … prepare` line outside a fence.
- **Files likely touched.** `shared/scripts/tools/aggregate_changelog.py` or the index writer, the upgrade-note template, the S12a scenario module, `shared/scripts/tools/check_plugin_conversion.py`, `shared/config/plugin_conversion.json`, tests.
- **Done when.** Each item has a test that failed before and passes now; the S12a and S2a.legacy traces differ.

### U9: Q3, refuse a hand release while an automatic one runs. Medium.

- **Scope.** `release.py prepare` started by hand (`mode: standalone`) refuses while a stored run state shows a release in progress that a pipeline or an autonomous run started. The message names the running release (version, branch, run, when it started). An explicit override flag takes over; it is written into the run state and the message says what it does.
- **Files likely touched.** `release_prepare.py`, `release_runstate.py`, `release.py`, `SKILL.md` (frozen), `docs/guide.md` (4.8, Appendix B), tests.
- **Done when.** L1 tests: a hand `prepare` during an automatic release is refused and changes nothing; with the override it goes on and the state records it; a finished or cancelled automatic release does not block; a hand release does not block a hand re-run (today's re-run path).

### U10: Q9, a pending note can be marked "breaking". Medium.

- **Scope.** A drop can carry an explicit breaking marker. The aggregator raises the major version for it and puts it under the breaking heading. Nothing is guessed from the text (STOP3-REPORT: a **BREAKING** drop under a `fix` commit gets a patch bump today; that stays so unless the marker is set).
- **Files likely touched.** `shared/scripts/tools/write_changelog_drop.py` (the drop format is written by several plugins, iterate among them), the aggregator and version step, `changelog-format.md` and `SKILL.md` (frozen), `docs/guide.md`, a new frozen scenario (re-pin), tests.
- **Done when.** L1 tests: a marked drop raises `1.2.3` to `2.0.0` and lands under the breaking heading; the same text without the marker does not; old drops without the field read as before. The iterate drop writer and the release read the same field (a boundary test).
- **Risks.** A drop format change crosses plugins. Old drops must keep working; a missing field means "not breaking".

## 2. Golden freeze (every unit)

The freeze is live (`plugins/shipwright-changelog/tests/golden/`). Since the stop-3 re-pin `approved_deltas.json` is `[]`.
- A changed frozen file (the live `SKILL.md` and its ten references, `plugins/shipwright-changelog/pyproject.toml`, the root `conftest.py`, the golden harness, every trace) needs an entry in `approved_deltas.json`: scenario = path, field `sha256`, before and after, approver, date, and `source` = the D- or Q-number and the FINDINGS row (or this brief's unit for Q3/Q9).
- A file added to or removed from the frozen set (a new trace) is `uv run shared/testkit/golden_lock.py --plugin shipwright-changelog --repin` in the same diff; the review reads the entries it prints.
- A promise test that moves: `golden_lock.py --promise-only --repin`, with the test named in the PR.
- Before every push: `golden_lock.py --check` exits 0 and the changelog test root is green.
- A trace that moves and is not explained by the unit's own change is a STRICT-STOP.

## 3. How each unit runs

- **Read first:** this brief, the FINDINGS rows the unit cites, `docs/hooks-and-pipeline.md`, `docs/building-skills-plugins-agents.md`. Requirement: FR-01.09 in `.shipwright/planning/01-adopted/spec.md` (FR-01.01 for U5); the runner passes `--ac-mode auto`.
- **Reviews:** the normal iterate process at the unit's complexity. Medium: architecture review before the build. Then `spec-reviewer`, `code-reviewer`, `doubt-reviewer`, each spawned with `model=opus` passed explicitly, plus the external review.
- **Repo rules:** docs in the same diff; new files at most 300 lines; one pytest root per process; `uvx ruff@0.15.15 check .` and `uv run scripts/verify_local.py` before the push; a unit edits a test only inside its touch set.
- **Anything that needs an operator answer is a STRICT-STOP.** Do not guess. A failed unit stops the campaign.
- **Records:** new findings go to FINDINGS in a new section "Follow-up campaign" (numbers from D114); what a unit taught goes to LEARNINGS.
- **Merge:** the runner only pushes its branch. The orchestrator opens the PR, waits for the checks, and admin-merges when every check except PR Review is green (operator grant for this campaign, 2026-11-28). If any other check is red, the orchestrator does not merge.
- **After each merge:** `bash scripts/update-marketplace.sh`, then `uv run scripts/check_plugin_cache_sync.py --strict`.

## 4. Mapping: every finding to a unit or out

STOP3 lesson: before the campaign closes, every row below is checked against what merged.

| Item | Where |
|---|---|
| D63 conversion and "passing" checks in CI | Out: needs the operator's CI acknowledgement; a separate small PR later |
| D66 where the stop-3 harness lives | Out: operator decision |
| D69 duplicated frozen trace | U8 |
| D71(1)(2) Windows process kill in the conversion check | Out: not decided (declined in fix round 2) |
| D71(3)(4)(5) | U8 |
| D89 guard trunks are a fixed list | U7 |
| Guard gaps (`@`, `refs/heads/*`, stray `--tags`, `HEAD~3:refs/tags/vX`) | U7 |
| D90 hung git helper on Windows | Out: not decided; U7 keeps the remote out of the hook so the guard is not exposed to it |
| D91 Cancel in code | Done in the pilot (P8a) |
| D92 hand-written entries move | Done (P8b), confirmed as built 2026-11-27 |
| D93 D20 promises without an AC | Done (P8b); turning them into ACs would be a later spec change |
| D94 `--from` removed | Done (P8b) |
| D95 version at the boundary | Done (P8b) |
| D96 PR body from a file | Done (P8b), confirmed as built 2026-11-27 |
| D97 refused evidence refresh restores the index | Done (P8b) |
| D98 cherry-pick fallback writes a drop | Done (P8b) |
| D99 pinned prose re-pin | Done at the stop-3 re-pin |
| D100 compare with the tag reachable from HEAD | Done (P8b), confirmed as built 2026-11-27 |
| D101 review fixes | Done (P8b) |
| D102 interrupted mixed release needs a hand reconcile | Out: not decided |
| D103(1) identical hand-written and drop entry shown twice | Out: not decided |
| D103(2)-(5) other known limits | Out: recorded limits, nothing to build |
| D104 a hand-written entry is never split | Done (P8b) |
| D105 a drop that could not be deleted shows up again | Out: not decided |
| D106 smaller fixes | Done (P8b) |
| D107 golden gaps | Done at the stop-3 re-pin |
| D108 column-0 entries stay | Done (P8b) |
| D109 tag push after the merge | Done (#1112) |
| D110 release finishes with any merge method | U2, U3, U4; pipeline mode U5, U6 |
| D111 root `pyproject.toml` and `uv.lock` | U1 |
| D112 foreign commits between release branch and merge | U3 (stop and report) |
| D113(1) stale closing summary | U2 |
| D113(2) condenser rewrites vacuous bullets | Out: judging its output needs a person |
| D113(3) empty decision indexes | U8 |
| D113(4) `ci-security.json` missing without CI | Out: a compliance-plugin question |
| D113(5) `SHIPWRIGHT_PLUGIN_ROOT` not set in a subagent | Out: investigate first |
| D113(6) upgrade-note wording | U8 |
| D113(7) close-phase runs twice | U6 |
| Q3 refuse a hand release during an automatic one | U9 |
| Q9 "breaking" marker | U10 (also the STOP3 "patch bump for BREAKING" observation) |
| Empty preview (STOP3 observation) | Out: new behaviour, operator decides |
| Re-dated identical section (STOP3 observation) | Out: new behaviour, operator decides |
| Untracked `triage.jsonl` after the audit | Out: `ADVISORY` in `release_close.py` excludes it on purpose; operator confirms or files a triage card |
| Audit exits 0 with `any_fail: true` | Out: a compliance-plugin question |
| Pre-check gaps recorded at stop 3 (untracked hand files under release folders, legacy event-log lines around Step 5.5) | Out: pre-existing, not raised by the operator; a triage card if wanted |

## 5. Operator decisions (Sven, 2026-11-28)

- Admin merge is granted for this campaign when every check except PR Review is green. The orchestrator merges, never the runner.
- D112: stop and report. No automatic addendum, so there is no separate D112 unit.
- U4: a release branch that is behind the base before an autonomous squash merge stops; the release is restarted. No automatic rebuild.
- Pipeline-started releases wait for the merge before tagging (U5, U6).
- Q3 and Q9 are in this campaign, as the last units.
- Not decided, so out of the run and back to Sven later: D90 and D71(1)(2), D102 and D105, D103(1), D66, the next-plugin discussion, the compliance questions (`any_fail`, `ci-security.json`), D113(2), D113(5), the empty preview, the re-dated section, `triage.jsonl`.
- D63 is out of the run: it needs Sven's CI acknowledgement and becomes a separate small PR.

## 6. After the campaign (operator steps, not units)

- **Live acceptance:** the next monorepo release runs from `prepare` to the closing check (8 of 8) through the plugin, on this squash-only repo. Each unit's "done when" uses end-to-end tests instead.
- **Canary first** (LEARNINGS stop 3): copy the target repo's merge settings, and run it while another PR merges, so U3's stop-and-report path is seen live.
- The mapping check of section 4.
- The next-plugin discussion (more end-to-end automation; lessons in LEARNINGS, "Stop 3").

## 7. Risks

- The golden freeze and the promise lock move in most units: budget the approved deltas, and never accept a moved trace without one.
- U2 to U6 change the release's outward path. Each step lands inert first (U2 before its writer U3, U5 before its user U6), so `main` never holds a writer that the guard or the loop rejects.
- U5 touches the pipeline loop of every project, not only releases. Keep the change behind the new waiting result, and keep every current loop test green.
- U1 and U10 change code in `shared/` that ships to consumers.
- Editing `plugins/*` or `shared/scripts` does not reach the runtime plugin cache by itself (section 3, after each merge).
