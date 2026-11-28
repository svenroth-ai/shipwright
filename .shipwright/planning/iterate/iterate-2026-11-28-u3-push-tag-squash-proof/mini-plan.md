# Mini-plan: U3 — push-tag after a squash or rebase merge: proof, retag, record, stop on foreign commits (D110 part 2, D112)

Run: iterate-2026-11-28-u3-push-tag-squash-proof · Complexity: medium · Campaign dfp-changelog-followups

## Goal
`release.py push-tag` accepts the PR's merge commit S after a squash or rebase merge only when (1) the PR head H is the
release commit R or an event-only descendant of it, (2) S is an ancestor of the freshly fetched base, (3) the merge proof
holds (tree(S) == tree(H), S directly on a base H already held). On success it writes `published_commit`, `merged_via`
and `proof` into the release record (U2's reader fields), moves the local tag onto S only while origin does not hold the
tag, and returns the tag push line. When (3) fails it stops with `foreign_commits_on_base`, naming the foreign commits and
their pending drops, and writes nothing. A merge commit keeps today's path (tag on R). A re-run gives the same answer.

## Changes
1. New `plugins/shipwright-changelog/scripts/lib/release_publish.py`: `merge_facts` (H, S from `gh pr view`), `_method`
   (merged_via + base_before from S's shape), `foreign_commits` (first-parent `merge-base(H,S)..S` minus S and the
   patch-equivalent replays, with the drops each commit added), `publish` (checks 1-3, ls-remote of the tag on the push
   URL, record write, retag `git tag -f -a` naming R).
2. `release_push.py`: `gh pr view --json state,mergeCommit,headRefOid,baseRefName` through the test seam
   (`release_paths.gh` -> `shared/scripts/release_seams.py`); MERGED + R not on base -> `release_publish.publish`;
   a re-run accepts a tag that already names the record's claimed merge commit. `merged_without_release_commit` retired.
3. `release_merge_proof.proven` tightened (orchestrator's review of U2): `base_before` must be an ancestor of `pr_head`,
   and per `merged_via` squash -> S's only parent is base_before; merge -> parents [base_before, pr_head]; rebase ->
   first-parent chain from S to base_before as long as pr_head's. Docstring trust-boundary paragraph corrected.
4. `shared/testkit/gh_stub.py` (frozen, approved delta, D114): `pr merge --squash|--rebase`, `pr view --json` with
   mergeCommit/headRefOid; `--merge` behaviour unchanged (no trace moves). Docstring shortened to stay under 300 lines.
5. `release_paths.shared_module` / `gh` (load shared modules by file, the gh seam).
6. Docs: SKILL.md Step 7, `release-workflow.md`, `rerunning-a-release.md` (frozen, approved deltas), `docs/hooks-and-pipeline.md`
   (guard row, P5/U3 paragraph, record row), `release_seams.py` docstring.
7. Tests: L1 e2e on the golden harness (`tests/test_release_push_merge_e2e.py`): squash and rebase -> push-tag proves,
   retags, guard allows, close-phase 8/8, re-run identical; merge commit -> tag on R, 8/8; foreign commit with a drop ->
   `foreign_commits_on_base` naming it and its drop, tag and record bytes unchanged, re-run identical; tag already on origin ->
   never moved. Real-git proof tests: R's tree committed onto a moved base (old or moved base recorded) denied by the guard and
   failed by the closing verify; rebase chain too long; merge without pr_head as second parent. Summary on the trunk says
   "not on origin". Stub contract tests for squash, rebase, pr view.

## Not in scope
Choosing the merge method / autonomous merge (U4), pipeline waiting (U5/U6), guard trunk list (U7).

## Alternative approach considered
Weaker fallback "same CHANGELOG section and manifest versions" — rejected by the brief (it let #1115 ship without its entry).
Asking `gh` for the merge method instead of reading S's shape — rejected: gh does not report the method, and the shape is
what the proof checks anyway. Folding foreign drops into the release automatically — rejected: operator decision D112 is
stop and report.
