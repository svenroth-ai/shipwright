# ADR (run iterate-2026-11-25-p8b-decisions-q5-q10): hand-written entries in the release, the version at the boundary, the PR body from a file, a clean index after a refused refresh

Campaign `dfp-pilot-changelog-p3-p8`, unit P8b. Scope: the operator re-scope of 2026-11-25 (Q5, Q6, Q7, Q8, Q10, F8, F9;
Q9 out). Detail per decision: FINDINGS D92-D103.

## Self-Review

1. Spec Compliance: pass. Builds the re-scope; the Q10 title/compare-link difference is recorded, not changed (D96).
2. Error Handling: pass. Invalid versions are usage errors (`invalid_version` for a library caller); `version_not_above_last_tag` stops `prepare`; `pr-body` refuses a missing or doubled section; a refused refresh restores the index and reports any failure.
3. Security Basics: pass. The PR body no longer passes through shell quoting (`--body-file`, written in the git dir); the version is validated (ASCII digits) before it reaches argv or a tag.
4. Test Quality: pass. About 50 new L1 cases (plugin root and `shared/tests`), each failing on the old behaviour; 16 traces regenerated; replay and CLI drivers agree; stale pins of the old behaviour updated.
5. Performance Basics: pass. One `ls-files` and at most seven `update-index` calls on a refusal; the `[Unreleased]` reader is one pass.
6. Naming & Structure: pass. New files 49-140 lines; `aggregate_changelog.py` 469 (baseline 472); `SKILL.md` 263 (cap 263) without a re-flow; `pr-body` registered in both registries.
7. Affected Boundaries: pass. `CHANGELOG.md [Unreleased]` -> aggregator -> section; the PR-body file -> `gh`; the drop writer -> aggregator; the git index -> refresh. Each probed on real files or real git (Confidence Calibration).

## Architecture Review

Internal (architecture-internal-reviewer): `approve` (smallest option: fix in the CLI and aggregator). External: glm `revise`,
openai `revise`. Findings and dispositions: (1) the `pr-body` subcommand and three new helper modules are more surface than
needed (glm, openai, internal low/medium): rejected-with-reason. No existing code step creates the PR (`gh pr create` is an
outward prose command), the body is needed only on the feature-branch path and must be the final section after Step 5, so
a call at that point is the 1:1 of the old `{entry}`; each helper sits next to its only caller and keeps a 300-line file
under its cap. (2) `--move-unreleased` should be the default (glm): rejected-with-reason. `aggregate_changelog.py` has
other callers whose output must stay byte-identical (1:1 rule); the release is the one caller that passes it, pinned by
`test_q5_both_aggregate_calls_move_the_hand_written_entries_and_only_the_preview_marks_them` and
`test_without_the_flag_the_aggregator_still_only_names_them`. (3) Q5 duplicate/cancel/rerun cases (internal): the preview
writes nothing, so Cancel has nothing to undo; rerun pinned (D102); duplicates recorded (D103(1)). (4) Q8 no-tag and
pre-release cases (internal): pinned in `test_not_above_follows_semver_precedence` (no tag = no comparison, pre-releases
by SemVer precedence, as the CLI accepted them before). (5) F8 must not unstage the operator's staged files (internal):
accepted, the restore compares with the index the run found (`test_a_refused_refresh_unstages_what_it_staged_and_keeps_what_the_operator_staged`).

## External-Plan-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| Q8: a non-SemVer or metadata-bearing last tag skips the comparison (glm, openai) | high/medium | accepted-and-fixed for build metadata (D101); a tag that is no SemVer at all keeps today's behaviour with a notice (D95) |
| Q8: backports are now refused (opus plan reviewer) | medium | resolved in fix round 1 (D100): the compare uses the highest release tag reachable from HEAD, so a backport passes as before P8b |
| Q5: the interrupted mixed release refuses instead of converging (opus, openai) | medium/high | accepted and pinned by a test (D102); converging is new behaviour |
| Q5: "after the drops" ordering is invented (glm) | medium | rejected-with-reason: before Q5 the entries were not released at all, so there is no order to port; recorded (D92) |
| Q5: preview and real run on one fixture, continuation lines, S8 (openai) | high | accepted: `test_changelog_unreleased.py` runs both on one fixture; the full trace regen left S8 unchanged (its bullets are unheaded) |
| Q6: a non-promise pin weakens the validator; Q6 pins outside the lock (openai, opus) | medium/low | rejected-with-reason: promise tests bind to an AC id and Q6 adds none; the limit is recorded (D103(3)) |
| Q6: promise lock steps missing from the plan (glm) | medium | accepted-and-verified: no promise test changed; `golden_lock.py --check` verifies the promise lock and exits 0 |
| F9: `release-fallback` run id collisions (glm, openai) | medium | accepted-and-verified: probed, two bullets give two drops, a repeat gives none (D101) |
| F8: crash path, fixed set of seven, staged-plus-unstaged fixture (glm, openai) | medium/low | accepted: a crash already resets to HEAD (unchanged); the seven are the tool's own set; the operator-staged case is tested |
| Unheaded hand-written bullets need a decision (openai code review) | high | recorded for the operator: they stay and are named, never placed by a guess (D92) |
| MSYS warning names a made-up drop path; blank line splits a bullet; message advice (opus) | low | accepted-and-fixed (D101); the refusal message now points to Step 7 and `rerunning-a-release.md` |

## External-Code-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| Unheaded bullets left behind (openai) | high | recorded for the operator (D92); not a guess |
| Build metadata on the last tag bypasses the check; Unicode digits accepted (openai) | high | accepted-and-fixed, tested (D101) |
| `git rm --cached` fails with an untracked copy; failures swallowed (openai) | high | accepted-and-fixed: `update-index --force-remove`, `unstage_failed` reported, tested |
| Interrupted mixed release refuses (openai) | medium | accepted and pinned (D102) |
| Pinned prose not updated (openai) | medium | rejected-with-reason: the pin is the stop-2 citation baseline, re-pinned at stop 3 (D78 precedent, D99) |
| `bullet-folding.md` not touched (glm) | medium | rejected-with-reason: it describes ADR and doc-bullet folding only; no fallback or `append_changelog_entry.py` mention |
| Other traces should have changed (glm) | medium | rejected-with-reason: `golden_lock.py --check` exits 0 on the tree; only traces with a PR step, S10, S16b and S19 changed |
| `prepare` raises on a raw version as a library (glm) | medium | accepted-and-fixed: normalises, else `invalid_version` |
| Fallback retry duplicates (glm) | low | accepted-and-verified (D101) |
| Hand-written text equal to a drop renders twice (glm) | low | recorded (D103(1)) |
| S19 runs `prepare` twice (glm) | low | rejected-with-reason: `run.step()` looks up a recorded result, it runs nothing |

## Confidence Calibration

Boundaries: `CHANGELOG.md` `[Unreleased]` read and rewritten by the aggregator; the PR-body file written for `gh`; the
drop writer feeding the aggregator; the git index of the seven evidence paths. Probes: (1) a real aggregation with drops
and multi-line hand-written bullets, then the dry run on the same input: found the blank-line split (fixed), re-probed
clean; (2) the interrupted mixed release on real files: refuses, changes nothing (pinned); (3) `write_changelog_drop.py`
with the fixed run id, two bullets then a repeat: two files, no third; (4) a refused refresh on real git with an
operator-staged path and an untracked copy of a new path: found the `git rm --cached` failure (fixed), re-probed clean;
(5) the PR body on a real repo: real newlines, nothing in `git status`; (6) both drivers over S10: found the order
difference of the fallback bullet (fixed with the fixed run id), re-run clean. Asymptote reached: two consecutive clean
probes after the last fix. Not probed: a `gh` run against a real host (the scratch records argv only).

## Fix round 1

The opus reviews of 9d7d741d1: spec REJECT (Q8 refused backports), code PASS, doubt one high and two medium. Closed list,
all done in one commit on top:

| Item | Fix | Record |
|---|---|---|
| Q8 refuses a backport (high) | the compare takes the highest release tag from `git tag --merged HEAD` (`tags-merged`); setup's `last_tag` keeps its other uses | D100, D95; real-git test |
| `take()` can split an entry (medium) | fences tracked, lazy column-0 continuation kept, an unclosed fence leaves the entry whole and named, lines split on `
` only | D104 |
| A re-run of a finished section pulls newer hand-written entries (medium) | `--move-unreleased` only while the section is not written; the warn-only unlink is recorded, not changed | D105 |
| Golden coverage (low) | PR body through the CLI pinned; the cannot-compare notice tested with `v01.2.0`; no new frozen trace | D106, D107 |
| Docs (low) | leftover fallback drops ride into the next release; duplicate-text collapse; Q8 wording narrowed | D103(5), reference, guide, SKILL |
| Code review (low) | precedence-dependent assert split; dead CRLF replace dropped, body-file lifetime named; `index_entries` stage 0 only, conflicts reported | D106 |

Probes after the fix: the real-git backport (v2.0.0 on main, 1.4.1 on `1.x` passes, 1.4.0 and 1.3.9 refused); a re-run
after a finished release with a new hand-written bullet (converges, the file unchanged; the argv check fails when the
fix is reverted); `take()` over a lazy continuation, a column-0 fence, an unclosed fence, U+2028 and CRLF. After the last
change the whole changelog root (756 passed) and F0 ran green.
