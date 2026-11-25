# Mini-plan: P8a, the contradiction and bug fixes D7, D8, D12, D24

Scope set by the operator on 2026-11-25: port the release behaviour one to one, only made deterministic; fix bugs
and contradictions; nothing new. Dropped: tag after merge (Q1), auto-merge (Q2), Q3, Q9 (follow-ups after the campaign).

## Changes

1. **F2 (D12) preview before write.** `SKILL.md` Step 4 runs only `release.py aggregate --dry-run`; Step 5 shows the
   preview and asks Accept / Edit / Cancel; Accept runs the real `aggregate`; Edit changes the pending drop file and
   repeats the dry run; Cancel ends the release with nothing written. `release_prepare` defers the upgrade-note drop
   when the preview question asks (it already did for the version and out-of-sequence questions), so Cancel leaves the
   drops byte-identical. The prompt-mechanics registry loses its one escape (budget 1 to 0).
2. **F3 (D7) push before PR.** A literal `git push origin HEAD` block right before `gh pr create`; a failed push stops
   the release. Registry gains the command key `git push origin HEAD`.
3. **F5 (D24) default branch from the remote.** `release_event.trunk()` reads `git ls-remote --symref <push url> HEAD`,
   then `origin/HEAD`, then `main`; unsafe names fall back to `main`. `prepare` stores and returns it; `record-event`
   uses it for the trunk check and the PR base; `push-tag` accepts it; `SKILL.md` passes `--base "{trunk}"`.
   `develop` stays the second trunk (1:1).
4. **Q2 (D8) contradiction.** `references/first-actions.md` states the merge rule the code (`release_verify`) and
   Step 7 already state. No merge behaviour changes.

## Tests

- New `tests/test_release_p8a.py` (in-process, 15 cases): trunk lookup and fallbacks, prepare/record-event/push-tag on
  a `master` remote, deferral on a preview question, prose order (dry run, question, real call; push, then PR), and
  the merge rule in both texts.
- Golden harness: `push-branch` step, preview before the real aggregate, S18a/S18b judge Cancel/Edit (AC10), S14a/S14c
  judge the remote default branch. Traces regenerated; replay and CLI drivers must agree; every frozen file change is
  an approved delta citing the operator decision.

## Alternative approach considered

Re-pinning the pinned prose copy so the CITES line numbers follow the live prose — rejected because the pin is the
stop-2 citation baseline and a re-pin is a separate operator-reviewed step.
