# Mini-plan: U2 — guard and close-phase accept a proven merge commit (D110 part 1, D113(1))

Run: iterate-2026-11-28-u2-guard-accepts-proven-merge · Complexity: medium · Campaign dfp-changelog-followups

## Goal
The release record (`.shipwright/runtime/release_state.json`, keeps `commit = R`) gains optional `published_commit = S`,
`merged_via` (`merge|squash|rebase`) and `proof = {pr_head, tree, base_before}`. One stdlib-only rule decides whether a
judged commit is the release; the release guard hook and the closing verify both use it. Nothing writes the fields yet
(U3 does), so `main` stays inert. D113(1): the closing summary reads the real tag state on origin.

## Changes
1. New `plugins/shipwright-changelog/scripts/hooks/release_merge_proof.py` (stdlib, next to `release_descent.py`):
   - `claimed(record)`: `published_commit` when all new fields are well formed (SHA shapes, `merged_via` in the set, proof dict), else None. No git call.
   - `proven(git, record)`: S when `proof.pr_head` is R or an event-only descendant of R (`release_descent.is_the_release`) and `tree(pr_head) == proof.tree == tree(S)`.
   - `accepts(git, record, judged)`: `release_descent.is_the_release(R, judged)` or `judged == S` with the proof holding.
2. `release_guard.py`: reads the whole record (`_record`), judges through `release_merge_proof.accepts`; the deny advice names the merge commit when one is claimed.
3. `release_verify.py`: `tag_local` and `tag_remote` accept the tag on R or on the proven S; `pr_state` (autonomous standalone) checks the commit the tag names: S on the base when the tag is on the proven S, else R (review round); `tag_remote` carries `on_origin`. No extra git call when the record has no new fields (golden traces unchanged).
4. `release_close.py` summary: "Tag pushed to origin" only when the verify saw the tag on origin naming the release; "Tag is pushed after the PR is merged" while a guided release waits; otherwise says the tag is missing or names another commit.
5. Tests: unit/real-git tests of the rule, guard, verify and summary (`tests/test_release_merge_proof.py`); an L1 end-to-end on the golden harness (real git, bare remote, gh stub) with a hand-made squash merge: valid proof → guard allows the tag push of S, close-phase 8 of 8; mismatched tree → guard denies, close-phase fails the three checks (`tests/test_release_merge_proof_e2e.py`). Two existing tests adapted to the guard's private signature change.
6. Docs: `docs/hooks-and-pipeline.md` (guard row, close-phase paragraph, `release_state.json` write-matrix row).

## Not in scope
The writer (push-tag proof, retag, record) is U3. No frozen file changes (SKILL.md, references, golden harness untouched).

## Alternative approach considered
Put the rule inside `release_guard.py` and duplicate it in `release_verify.py` — rejected because the brief asks for one rule in a
new module (the guard is near the 300-line cap and U7 adds more), and two copies drift.
Weaker proof (only `tree(S) == proof.tree`) — rejected because a hand-edited record could then set both S and the tree to any commit;
checking that `pr_head` is the release and carries the same tree ties S to the audited content.
