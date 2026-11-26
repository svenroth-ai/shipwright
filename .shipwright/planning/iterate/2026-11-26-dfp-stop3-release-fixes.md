# Iterate: stop-3 release fixes for the changelog pilot (F-S3-1, D21, D22, D23, D25)

**Run ID:** iterate-2026-11-26-dfp-stop3-release-fixes
**Type:** bug · **Complexity:** medium (operator-set) · **Autonomous** · **Status:** implemented
**Source:** stop-3 live runs of the changelog pilot (`STOP3-FINDINGS.md`, scratchpad), FINDINGS rows D21, D22, D23, D25, D34, D38(6), D39, D40; operator decision 2026-11-26 (chat) for D25.
**Binding rule (P17a):** behaviour stays one to one with the old prose; a bug or a contradiction is fixed with a test; nothing new.

## Problem

Under the shipped default (the `drops` event layout) no release could finish from a clean tree, and after an
autonomous merge the tag push the skill prescribes was blocked:

1. **F-S3-1 (new, FINDINGS D109).** After `gh pr merge --merge --delete-branch` HEAD is `main` at the merge commit;
   `release.py push-tag` prints `git push origin refs/tags/v1.3.0`, and the PreToolUse hook `release_guard.py` denies it
   ("record names X, but HEAD is Y"). Root cause: `release_guard_commands.find_actions` gives `tags=True, refs=[]` for
   `refs/tags/vX`, `tag vX` and `--tags`; `_is_trunk_push` then falls back to the current branch (`main`), so HEAD is
   judged instead of the tag. `git push origin vX` (a bare name) was allowed. Reproduced on the live S2al-1 repo.
2. **D21.** `release_commit.DROP_DIRS` are named unconditionally in `git add -A` and in `git commit -- <paths>`; with
   neither folder tracked git exits 128/1 and the release commit fails (`commit_failed`).
3. **D22.** A consumed TRACKED drop under `CHANGELOG-unreleased.d/` is deleted by the aggregate but not in the pathspec;
   the deletion stays dirty, the release audit refuses, no tag.
4. **D23.** `release.py sync` (Step 5.5, `refresh_compliance_docs.py --stage`) records a `grade_snapshot` event (writer
   confirmed: the compliance grade emitter; under `drops` a new untracked drop file, under `legacy` with a tracked log a
   modified `shipwright_events.jsonl`); not in the pathspec, the audit refuses, no tag.
5. **D25 (operator decision 2026-11-26).** Unrelated dirty files (staged, unstaged, untracked): the release commit was
   made, then the audit refused; a half-finished release was left. Decision: check the tree BEFORE committing and stop
   with a message naming the unrelated paths; no commit.

## Root cause and fix

- `release_guard_commands._push` records `named_tags` (a tag the command itself names: `--tags`, `refs/tags/...`,
  `tag <name>` anywhere among the refspecs; never `--follow-tags`). `release_guard._is_trunk_push` returns False for a
  push with no branch refspec and `named_tags`: only tags go, so the tag's commit is judged. A combined push
  (`git push --atomic origin main refs/tags/vX`, `tag vX main`) is still a trunk push judged by HEAD.
- `release_commit.commit_pathspec` keeps a path only when git knows a file under it (`git ls-files --cached --others
  --exclude-standard`), and adds the consumed drops (`consumed_drops`, kept by `aggregate` from the aggregator's
  `processed_files`) and the event files Step 5.5 wrote (`events_pathspec`, kept by `sync` by comparing event file
  bytes before and after the compliance run). `git add -A` is never run with an empty pathspec.
- `commit_and_tag` first runs `git status --porcelain -z -uall`; any path no release pathspec covers stops with
  `reason: unrelated_changes`, `unrelated: [...]`, a plain message; nothing is staged or committed.
- `.shipwright/triage.jsonl` (written by the release audit after the commit) is not present at the pre-check on a first
  run: verified by the S1 scenarios (status before Step 6 has no such line) and by the golden runs.

## Spec Impact

**NONE** for `spec.md` (FR-01.09 AC01 already says the release is prepared from a clean tree; these are bugs against it).
Affected FR: FR-01.09 (AC01). No AC changes.

## Acceptance (bug)

- A tag-only push (`refs/tags/vX`, `tag vX`, `--tags`, bare `vX`) after a merge to the trunk is allowed while the tag
  names the recorded release commit; the trunk push and combined pushes are judged by HEAD as before.
- A project without `decision-drops/`/`adr/` gets a release commit and a tag (S1d).
- A consumed tracked drop's deletion is in the release commit; the tree is clean (S1t).
- Under the drops layout the release finishes; the `grade_snapshot` drop is in the release commit (S1/S2 drops).
- Unrelated staged/unstaged/untracked changes stop Step 6 before any commit, naming the paths (S15, S16c).

## Confidence Calibration
- **Boundaries touched:** PreToolUse hook command parsing (`release_guard_commands`); the run-state file in `.git`
  (`release_run.json`: new keys `consumed_drops`, `events_pathspec`); the git index / commit pathspec of Step 6.
- **Empirical probes run:** `git push --tags origin` on a scratch repo pushes only tags (branch not sent) — confirms
  `--tags` with no refspec is not a trunk push. `release_guard.decide` on the live S2al-1 repo: the four tag-only forms now
  allow, `git push origin main` still denies. Old code: the new L1 tests fail (10 guard, 5 commit), new code: pass.
- **Test Completeness Ledger:** see F5 block; every behaviour above has an L1 test in `tests/test_release_guard_stop3.py`
  or `tests/test_release_stop3_commit.py` and a golden scenario (S1, S1d, S1t, S2*, S15, S16c) through both drivers.
- **Confidence-pattern check:** depth — the D25 rule is tested for each kind of dirt and a rename; breadth — every frozen
  scenario reaching Step 6 runs through the replay and the CLI driver and must produce the same trace.

## Review rounds

- **Spec reviewer:** PASS.
- **Code reviewer:** PASS with two MEDIUM regressions of this unit, both fixed with tests: a project in a subfolder of the work tree (status paths stripped of `git rev-parse --show-prefix`) and `git push origin HEAD:refs/tags/vX` (a remote tag made from another commit stays judged by HEAD).
- **Doubt reviewer:** one new MEDIUM, fixed with tests: a matching `:` refspec beside a tag is not tag-only. Wording fixed where the prose promised more than the check gives (directory pathspecs, legacy event window, the trunk-only HEAD fallback). The stop message no longer advises committing.
- **External code review (GPT revise, GLM approve):** fixed: a failed `git status` stops with `tree_check_failed`; a staged deletion keeps its folder in the pathspec; drop-name normalization only under `events/drops/`.
- Open items left unchanged are listed in FINDINGS, stop 3.
