# push-tag proves a squash or rebase merge commit, retags, stops on foreign commits

Run: `iterate-2026-11-28-u3-push-tag-squash-proof` · campaign `dfp-changelog-followups`, unit U3 · FINDINGS D110 (part 2), D112, D114 · FR-01.09.AC11 (restored: on a squash-only repository the release is put onto its target again).

After a squash or rebase merge the release commit R never reaches the base, so `release.py push-tag` waited forever. Now, when `gh pr view` reports the PR `MERGED` and R is not on the base, `push-tag` calls `lib/release_publish.py`. It accepts the PR's merge commit S only when:

1. the PR head H is R or an event-only descendant of R (`release_descent`),
2. gh reports the base the release recorded (`pr_base_changed` otherwise), and S is an ancestor of that base freshly fetched from the push URL,
3. the shared proof (`scripts/hooks/release_merge_proof.py`) holds: tree(S) == tree(H), and S sits directly on `base_before` as `merged_via` says (squash: S's only parent; merge: parents `[base_before, H]`; rebase: as many single-parent commits as H is past `base_before`, ending on it, each patch-equal to a PR commit by `git cherry`).

Then it writes `published_commit`, `merged_via` and `proof` into `.shipwright/runtime/release_state.json` (atomically, `.part` + `os.replace`) and moves the local annotated tag onto S (`git tag -f -a`, the message names R) while origin does not hold the tag. A tag on origin naming another commit is never moved (`tag_on_origin_not_the_merge_commit`); one already naming S is fetched as its exact object. Anything else refuses and writes nothing: `merge_commit_unknown`, `merge_commit_changed`, `pr_base_changed`, `pr_head_not_the_release`, `merge_commit_not_on_base`, `merge_state_unknown`, or `foreign_commits_on_base` with the first-parent commits from `merge-base(H, S)` that are not the PR's own (`git cherry`) and the changelog drops each added (`diff-tree -m --first-parent`). A merge-commit release keeps the tag on R. A re-run gives the same answer. The push stays the one literal line in `SKILL.md`; the whole JSON answer is redacted of URL user and token.

The proof was tightened on the orchestrator's review of U2: equal trees alone admitted `commit-tree <release tree> -p <moved base>`.

The gh stub (`shared/testkit/gh_stub.py`, frozen, approved delta) learns `pr merge --squash|--rebase` and `pr view --json` (D114); push-tag calls gh through the test seam `release_seams.gh_command`.

AC record: `restore` FR-01.09.AC11 (decided by code, `--ac-mode auto`). No new AC (brief: turning promises into ACs is a later spec change).

## Architecture Review

External (`--mode architecture`): glm `approve`, openai `approve` (option A: make the existing push-tag step write the claim the guard already reads). glm (low): the proof vocabulary grows; kept minimal, one rule shared by writer, guard and verify.

Internal architecture review (architecture-internal-reviewer, opus): Ran: yes · verdict approve.

## Internal Plan Review (opus-plan-reviewer)

Ran: yes · verdict revise (medium) · Status: 7 fixed, 1 disclosed. Fixed: real-git tests for `pr_head_not_the_release` and `merge_commit_not_on_base`; push URL credentials redacted and `credential.interactive=never`; publish fetches the base itself after gh reported the merge (no stale FETCH_HEAD from on_base); rebase detection requires `git cherry` all `-`; foreign subjects cut to 80 characters, control characters removed; tree and method facts in the refusal; retag recovery by re-run (record first, tag second). Disclosed: the `shared_module` cache key is not namespaced (one plugin per process).

## External-Plan-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| Single-commit rebase looks like a squash | medium | accepted: labelled squash; the squash proof is as strict, only the label differs |
| "Event-only descendant" undefined | medium | rejected-with-reason: the existing `release_descent` rule; test with a commit pushed after the release |
| Origin tag on R: what the user sees | medium | accepted-and-fixed: `tag_on_origin_not_the_merge_commit`, tested |
| Brief not readable by the reviewer | high | rejected-with-reason: reviewer tooling; the runner followed the brief |
| Rebase proof by chain length only | high | accepted-and-fixed: single-parent walk ending on the base and `git cherry` patch equality |
| Partial write between record and tag | high | accepted-and-fixed: record first, tag second, re-run completes; atomic record write |
| TOCTOU between ls-remote and the push | low | accepted: the printed push is never forced, so a tag made in between makes it fail, not move |

## External-Code-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| PR retargeted to another base | high | accepted-and-fixed: `pr_base_changed`, tested |
| Rebase chain reachable through a second parent | high | accepted-and-fixed: single-parent walk, tested with the sibling graph |
| Origin tag on S made elsewhere, local tag differs | medium | accepted-and-fixed: fetch origin's exact tag object, tested by a real push |

## Internal reviews (cascade)

Spec-reviewer (opus): round 1 REJECT (merge-commit e2e test did not run the guard; fixed), round 2 PASS on e87d6625a. Code-reviewer (opus) on 866ecbdbd: PASS, one medium (on_base's recorded calls still carried the push URL; fixed by redacting the whole answer, e2e test), three low fixed (failed `git cherry` chose rebase; refusal wording when only the shape failed; regex stopped at the first `@`), one disclosed (`gh_stub.py` at exactly 300 lines). Doubt-reviewer (opus) on ffdd68400: high (a hand-made S = `commit-tree tree(H) -p F` with `merged_via: rebase` passed the chain-shape check and the guard would approve a trunk push undoing F) fixed with the `git cherry` check, regression test fails without it; medium (non-atomic record write) fixed; low (FETCH_HEAD race) rejected, fails toward a refusal and the closing verify re-checks; low (rebase of a PR holding merge commits is refused) disclosed.

## Self-Review

1. Spec Compliance: pass. All four ACs and both U2 review items have real-git tests through the gh stub.
2. Error Handling: pass. Every refusal returns before the record write; a failed retag is repaired by a re-run.
3. Security Basics: pass. Parent-tied proof with patch equality; no credentials in the answer; prompts off.
4. Test Quality: pass. Real git, bare remote, the stub merges; each refusal tested; new proof tests fail on the old rule.
5. Performance Basics: pass. Only the squash/rebase path adds calls; merge-commit traces unchanged.
6. Naming & Structure: pass. Writer in a new 158-line module; push-tag 110 lines; one proof rule.
7. Affected Boundaries: pass. `release_state.json` written by the CLI, read by the in-process guard and the close-phase CLI; `gh pr view` JSON from the stub to `merge_facts`.
8. Test Hygiene Probe: pass. No findings.

## Confidence Calibration

Boundaries: the release record (producer now push-tag, consumers guard and verify) and `gh pr view` JSON. Probes: e2e round trips for squash, rebase, merge (ok); URL redaction over https token, user:password, ssh, scp-like, file and raw-`@` URLs (ok after the regex fix); `merge_facts` with a null merge commit and uppercase ids (no claim). Two consecutive no-finding probes: asymptote reached. Not probed: a raw `/` inside a URL password (must be percent-encoded in a URL anyway); a real GitHub merge queue (out of scope, refused by the tree check).
