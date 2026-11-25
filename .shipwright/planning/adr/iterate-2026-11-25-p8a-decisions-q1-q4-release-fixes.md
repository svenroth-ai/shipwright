# ADR (run iterate-2026-11-25-p8a-decisions-q1-q4): release preview before write, branch push before PR, default branch from the remote

Campaign `dfp-pilot-changelog-p3-p8`, unit P8a. Scope: the operator re-scope of 2026-11-25 (FINDINGS D72). Detail per
decision: FINDINGS D72-D82.

## Self-Review

1. Spec Compliance: pass. Builds the re-scope (F2, F3, F5, D8); dropped items recorded (D72, D82).
2. Error Handling: pass. The trunk lookup falls back to `origin/HEAD`, then `main`; a failed branch push stops the release.
3. Security Basics: pass. The remote's branch name is validated and passed as argv after `--end-of-options`; both head pushes use `--no-follow-tags`.
4. Test Quality: pass. 17 L1 and 4 L2 cases, each failing on the old behaviour; 42 traces regenerated, replay and CLI drivers agree.
5. Performance Basics: pass. One `ls-remote` per `prepare`; the timeout is the runner's (D82(3), follow-up).
6. Naming & Structure: pass. All files under 300 lines; registry widened by one key, escape budget 1 to 0.
7. Affected Boundaries: pass. The run state gains `trunk` (producer `prepare`; consumers `record-event`, `push-tag`, the closing verify); round trip probed in `test_release_p8a.py`.

## Architecture Review

Internal (architecture-internal-reviewer): `revise`. External: glm `approve`, openai `approve` (both read the unrevised
spec). Internal findings and dispositions: the spec text is not re-scoped (rejected-with-reason: the spec is owned by
the orchestrator in the main checkout; D82(1)); the merge rule needs an operator decision (rejected-with-reason: the
code decides it, D73); the squash/rebase tag case loses its owner (rejected-with-reason: `push-tag` already refuses
`merged_without_release_commit`, D82(7)); validate the remote's branch name (accepted-and-fixed: regex plus argv);
failure modes (accepted: a failed push stops before the PR; a failed lookup falls back as today, D82(5)).

## External-Plan-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| Mini-plan scope differs from the spec (glm, openai) | high | rejected-with-reason: the operator re-scope (D72) is binding; spec amendment is the orchestrator's (D82(1)) |
| Q1 squash/rebase tag bug left live (glm) | high | rejected-with-reason: `push-tag` refuses `merged_without_release_commit` (P5), D82(7) |
| Edit then Cancel leaves the edit (openai) | high | accepted-and-fixed: Step 5 Cancel restores an edited drop |
| Silent fallback to `main` (openai) | high | rejected-with-reason: today's code always assumed `main`; stopping is new behaviour (D82(5)) |
| Escape removal may change traces (glm) | medium | accepted: the full trace set was regenerated; every change is attributed in approved_deltas.json |
| Dry run must write nothing (glm) | medium | accepted-and-verified: S18a compares the whole tree digest, untracked files included |
| Pinned prose not updated (openai) | medium | rejected-with-reason: the pin is the stop-2 citation baseline (D78) |
| Runtime proof of push before PR (openai) | medium | accepted-and-fixed: `tests/golden/test_p8a_push_before_pr.py` (real git, both drivers) |
| `push.followTags` can send the tag with the head push (opus plan reviewer) | medium | accepted-and-fixed: `--no-follow-tags` on both head pushes (D81) |
| Deferred upgrade note cannot be edited before Accept (opus, openai) | medium | recorded: pre-existing since P3, D82(2) |
| Verify reads `origin/HEAD` again instead of the stored trunk (opus) | low | accepted-and-fixed: `on_base` reads `trunk` first |
| Timeout / credential prompt on the lookup (opus, glm) | low/medium | recorded: D82(3) |
| Push URL echoed in the commands JSON (opus) | low | recorded: D82(4), same as the closing verify |
| Fold the push into release.py (opus) | low | rejected-with-reason: 1:1 with the other outward lines; the guard hook sees it (D82(6)) |

## External-Code-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| Scope differs from the spec (openai, glm) | high/medium | rejected-with-reason: D72, D82(1) |
| Edit then Cancel (openai) | medium | accepted-and-fixed (Step 5 Cancel) |
| Deferred upgrade note not editable (openai) | medium | recorded: D82(2) |
| Approved trace hashes without trace changes (openai) | high | rejected-with-reason: an artefact of the review diff, which excluded `*.trace.json`; `golden_lock.py --check` exits 0 on the tree |
| No promise-lock repin (glm) | medium | rejected-with-reason: no promise test changed; `--check` verifies the promise lock and passes |
| Replay driver's trunk lookup lacks the regex (glm) | medium | recorded: the replay runs on a controlled scratch remote; follow-up with the next re-pin |
| Lookup timeout (glm) | medium | recorded: D82(3) |
| `release_flow` does not stop on a cancel outcome (glm) | low | recorded: only S18a cancels, and it uses its own flow; a frozen-file change for the next re-pin |
| S14a asserts the literal `main` base (glm) | low | rejected-with-reason: S14c (a `master` remote) and the L1 tests prove the dynamic base |
| `_BRANCH` accepts `..` / `.lock` (glm, opus) | low | recorded: safe for argv; git refuses such a ref on use |

## Confidence Calibration

Boundary: the run-state file (`release_run.json`) gains `trunk`; the remote's `ls-remote --symref` output is parsed.
Probes run: (1) a `master` remote end to end (S14c, real git): trunk case, atomic trunk-and-tag push; (2) a remote
whose HEAD answer is an unsafe name (`-x;rm`): falls back to `main`; (3) no push URL and no `origin/HEAD`: `main`;
(4) `ls-remote` failure with `origin/HEAD` set: the local answer; (5) a run state written before F5 (no `trunk`):
`record-event` asks the remote. Probe (1) found the closing verify still asked `origin/HEAD` (fixed: reads `trunk`);
probes (2)-(5) found nothing; two consecutive clean probes after the fix, asymptote reached. Not probed: a remote
that hangs (D82(3)); a credential-bearing push URL (D82(4)).

## Fix round (orchestrator review: spec PASS, code REVISE, doubt one HIGH)

- Trunks additive (doubt HIGH, FINDINGS D85): default branch, then `main` and `develop` always, `master` while the default is
  unknown. `prepare` returns `trunk`, `trunk_source`, `on_trunk`; Step 7 branches on `on_trunk`. S14d: `develop` default,
  release on `main` = trunk release, no head push, no PR.
- Lookup (D86): `git -c credential.interactive=never ls-remote --symref origin HEAD`, `GIT_TERMINAL_PROMPT=0`, 30 s; no
  `get-url`, the recorded output cut to the one line read. Closes D82(3) and D82(4) for the lookup.
- Cancel in code (D84): `prepare` keeps the drop bytes, `release.py cancel` writes back what an Edit changed (never deletes a
  new file; refused after the real `aggregate`). S18c: Edit then Cancel, tree digest equals the one before.
- SKILL.md cap (D83 corrected, D87): the re-flow of seven paragraphs is undone; text a reference already holds is cut
  instead (262 lines). The push-tag sentence names `{branch}`. Hardening test: the head push block is exactly
  `git push origin HEAD --no-follow-tags`.
- Approved deltas name the fix per trace (D88). S14d and S18c run through both drivers and compare the two traces
  (`test_p8a_fix_scenarios.py`): a new frozen trace would need a re-pin of the golden lock.

## Fix round 2 (Opus re-review of 965cdfd98: code PASS with two medium, doubt three medium)

- Cancel hardening: a key with `\` or `:` is refused (`no_drop_snapshot`); before every write the target and each parent up
  to `CHANGELOG-unreleased.d/` must not be a symlink and the resolved path must lie inside the resolved drops directory
  (`unsafe_drop_path`). Every `prepare` takes the drop snapshot anew (no `setdefault`).
- Lookup env: the release guard's no-prompt env, shared as `release_descent.NO_PROMPT`; the runner closes stdin. The Windows
  grandchild-timeout hang is recorded (FINDINGS D90), no process-tree kill.
- Cancel is a bug fix under F2/D84, not a new feature (FINDINGS D91): Edit changes drops because the preview writes nothing;
  `release_written`, `no_drop_snapshot` and `left` are part of that fix. SKILL.md Step 5 tells the operator every `left` path.
- The release guard hook's static trunk list (FINDINGS D89) predates P8a and is left for stop 3.
