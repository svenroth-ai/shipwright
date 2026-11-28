# Mini-plan: U4 — Autonomous merge: pick the method, pin the head, stop when behind (D110)

Run: iterate-2026-11-28-u4-autonomous-merge-method · Complexity: medium · Campaign dfp-changelog-followups

## Goal
The autonomous release merge in SKILL.md Step 7 (today `gh pr merge --merge --delete-branch`, which fails on this
squash-only repository) becomes one literal line `gh pr merge --{method} --match-head-commit {head} --delete-branch`
that a new `release.py merge-ready` call fills in, or refuses with a reason. Operator decisions (2026-11-28): squash and
merge commit both work, merge commit preferred; always pin the head; a base that moved before a squash or rebase merge
stops with a plain restart message and nothing is merged or re-created; repository settings are read, never changed.

## Changes
1. New `plugins/shipwright-changelog/scripts/lib/release_merge.py` `merge_ready(rec, plugin_root, version)`:
   record + run state checks (autonomous standalone release on a feature branch, event recorded); HEAD on the release
   branch and the release or its event commit (`release_descent`, the guard's rule); `gh pr view --json state,headRefOid`
   OPEN with head == HEAD; `gh repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed` -> merge >
   squash > rebase; for squash/rebase fetch the base (FETCH_HEAD only) and require `merge-base --is-ancestor FETCH_HEAD
   HEAD`, else `base_moved` with a restart message. Answer `ok` + `argv` + `line`, or `refused` + `reason` + `detail`.
   Push URL user/token redacted from the answer.
2. `release.py`: `merge-ready` subcommand. `release_verify.fetch_base` extracted from `on_base` (same keys).
3. `release_push.py`: `waiting_for_merge` detail says "merge it while the branch is up to date with the base".
4. SKILL.md Step 7 (frozen): the merge-ready call + the one literal merge line, base_moved handling, guided text.
   `release-workflow.md` (frozen): rationale. `docs/hooks-and-pipeline.md`, `docs/guide.md` 4.8.
   `shared/config/converted_skills.json` (+ merge-ready command), `plugin_conversion.json` (+ subcommand).
5. `shared/testkit/gh_stub.py` (frozen, at the 300-line cap): split the flag/git plumbing into
   `gh_stub_support.py`; add `repo view --json <settings>` (from `state.json` `repo`, all allowed when unset), refuse a
   disallowed method, honour `--match-head-commit`. The new file joins the frozen set: `golden_lock.py --repin`
   (brief section 2), `approved_deltas.json` emptied as the lock writer requires; no trace moves.
6. Spec: FR-01.09 gains AC16 (pre-build AC record, auto mode).
7. Tests: unit (`test_release_merge_ready.py`, injected runner: methods per settings, base moved, every refusal,
   redaction, SKILL template == printed line, CLI) and L1 e2e on the golden harness (`test_release_merge_ready_e2e.py`:
   squash-only -> pinned squash line, guard allows it, it merges, push-tag proves; merge allowed -> --merge, tag on R;
   base moved -> base_moved, nothing merged; a late push -> host refuses the pinned line and the guard denies).

## Not in scope
Pipeline waiting (U5/U6); guard trunk list (U7); changing the golden CLI driver's merge-pr step (it keeps the stop-3
prose line; the traces stay unchanged).

## Alternative approach considered
Let merge-ready run the merge itself — rejected: the brief keeps outward commands as one literal line the guard sees.
`gh pr update-branch` before a squash — rejected by the operator (breaks push-tag's proof). Trimming the stub docstring
again instead of a split — rejected: the orchestrator asked for a split, and the docstring is the stub's contract.
