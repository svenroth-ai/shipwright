# Guard and close-phase accept a proven merge commit

Run: `iterate-2026-11-28-u2-guard-accepts-proven-merge` · campaign `dfp-changelog-followups`, unit U2 · FINDINGS D110 (part 1), D113(1) · FR-01.09.AC11 (restored: the closing summary says the release is out only when origin holds its tag).

The release record (`.shipwright/runtime/release_state.json`) gains three optional fields: `published_commit` (the PR's merge commit S after a squash or rebase merge), `merged_via` and `proof` (`pr_head`, `tree`, `base_before`). One stdlib rule, `plugins/shipwright-changelog/scripts/hooks/release_merge_proof.py`, accepts a judged commit when it is the release (the `release_descent` rule, unchanged) or when it is S and the proof holds in this repository: the PR head is the release or an event-only descendant of it, the PR head's tree and S's tree both equal `proof.tree`, and `proof.base_before` is an ancestor of S. The release guard hook and the closing verify (`tag_local`, `tag_remote`, `pr_state`) use it. Nothing writes the fields yet (U3 does), so `main` stays inert; a record without them costs no extra git call and answers exactly as before.

AC record: `restore` FR-01.09.AC11 (decided by code, `--ac-mode auto`). No new AC: the end-to-end promise for a squash-merged release needs U3's writer and belongs there.

## Architecture Review

External (`--mode architecture`, brief without rejection reasons): glm `approve`, openai `approve`. glm (low): `base_before` is carried but not read; resolved, the rule now checks that it is an ancestor of S.

Internal architecture review (architecture-internal-reviewer, opus): Ran: yes · verdict approve · severity low. Findings: the moved-base case (a squash of a stale branch has another tree; refused here, U3 stops on foreign commits, D112) — disclosed for U3; `base_before` shape-only — fixed (ancestry check); the published commit accepted only exactly (no event-only descent from S) — disclosed, the tag and the verify judge S itself; inert until U3 — accepted. Status: 1 fixed, 3 disclosed.

## Internal Plan Review (opus-plan-reviewer)

Ran: yes · Severity: low · Status: 3 fixed, 2 disclosed. Fixed: `base_before` ancestry check; the summary line when the `ls-remote` lookup failed (no longer "pushed after the merge"); rebase and merge-commit cases tested. Disclosed: hooks loaded by `sys.path` (both modules stateless, same pattern as `release_push`); a claimed record costs up to six local git calls.

## External-Plan-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| Merge-commit path (base moved) untested | medium | accepted-and-fixed: tests for a merge on an unmoved base (proven) and after the base moved (refused) |
| How close-phase learns what verify saw | medium | rejected-with-reason: one process; the summary reads verify's `tag_remote` check (`on_origin`) |
| pr_state fallback condition undefined | low | accepted-and-fixed: the PR check follows the commit the tag names |
| Other callers of the guard's private helpers | low | checked: two tests adapted, no other caller |
| S not proven to be on the base before the guard allows it | medium | accepted-and-fixed in part: `base_before` must be an ancestor of S; that S is on origin's base is proven by U3 and checked by the closing verify (the guard may not ask the remote, D90); documented as the trust boundary |
| `tag_remote` lookup failure vs absence | medium | accepted-and-fixed: `on_origin` is `None` when origin could not be asked; the summary says so |

## External-Code-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| PR check passes on R while the tag names an S off the base | medium | accepted-and-fixed: the PR check follows the tag; regression test with R on the base and S off it |
| Second close-phase tested only through `verify()` | low | accepted-and-fixed: guided release closed twice through `release.py close-phase` (e2e) |
| Missing `tag_remote` check falls back to the mode guess | low | accepted-and-fixed: treated as "origin could not be asked" |
| Redundant `claimed()` / descent work | low | rejected-with-reason: a few local git calls, only for a claimed record |
| String-presence drift test | low | rejected-with-reason: behaviour is covered on real git |

## Internal reviews (cascade)

Spec-reviewer (opus): PASS on dd5f9ca3d. Code-reviewer (opus) on bc2e9f4a5: three low findings, all fixed (plan wording, a passing merge-commit test, a duplicate test name). Doubt-reviewer (opus): two low doubts. (1) A hand-edited `base_before` can name any ancestor of S: the guard's protection rests on the tree checks; docstring says so. (2) The on-trunk line "Tag + main pushed" names the branch although verify only asked about the tag (pre-existing wording, kept); a record for another version prints "names another commit" (accepted, rare).

## Self-Review

1. Spec Compliance: pass. Every AC and the brief's done-when has a real-git test.
2. Error Handling: pass. Malformed fields are no claim; missing objects deny; a failed lookup is reported as such.
3. Security Basics: pass. No record field can approve content other than the audited release.
4. Test Quality: pass. Real git with a bare remote; negative cases for orphan, foreign tree, moved base, hand-edited tree, non-release head.
5. Performance Basics: pass. No git call without a claim; no remote call in the guard.
6. Naming & Structure: pass. New module next to `release_descent`; the guard stays at 233 lines.
7. Affected Boundaries: pass. `release_state.json` round trip probed (write_state, read_state, guard, close-phase).
8. Test Hygiene Probe: pass. `scan_test_hygiene.py --diff`: no findings.

## Confidence Calibration

Boundary: the release record's new fields (producer U3, consumers guard and verify). Probes run: round trip through `write_state`/`read_state`/`claimed` (ok), CRLF record (ok), UTF-8 BOM (no record, the pre-U2 deny), SHA-256 ids (claimed), uppercase or short ids (no claim), empty proof, list proof, null `merged_via` (no claim). Two consecutive no-finding probes: asymptote reached. Not probed: a record written by U3 itself (U3 does not exist yet; U3's e2e test closes it).
