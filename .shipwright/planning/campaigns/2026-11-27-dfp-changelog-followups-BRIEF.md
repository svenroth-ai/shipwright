# Follow-up campaign for the changelog pilot: input list (draft)

**Status:** draft, not started. It is written at the close of stop 3 (2026-11-27), from the pilot's FINDINGS, LEARNINGS and the STOP3-REPORT. The operator confirms the scope and the order before any unit runs. The conversion rule no longer applies here: these are product changes, each one confirmed by the operator.

## Priority 1: a release finishes with any merge method (operator, 2026-11-27)

The first monorepo release (v0.37.0) could not be finished by the plugin. The fix is one unit, possibly split:

- **D110:** after a squash or rebase merge, `push-tag` finds the merge commit on the base and proves that it carries the release. It then tags that commit and updates the release record, so the release guard and the closing check accept it. Squash merges and merge commits must both work, with no hand work and no lifting of the guard.
- **D112:** before tagging, detect commits that landed on the base between the release branch and the merge. Stop and name them, or take their changelog and decision drops into the release. Code must never ship without its entry.
- **D111:** the root `pyproject.toml` (and the lock's root package version) becomes a declared release manifest.
- **Acceptance:** the next monorepo release runs from `prepare` to the closing check (8 of 8) through the plugin, on this squash-only repo.

## Priority 2: guard and robustness gaps

- **D89:** the release guard protects only `main`, `master` and `develop`. Read the trunk from the remote's default branch.
- **Older guard gaps** from the stop-3 runs: `git push origin @`, `refs/heads/*` globs, `--tags` pushing other tags, and `HEAD~3:refs/tags/vX`.
- **D90:** a hung git helper on Windows can outlast the 30-second default-branch lookup.
- **D102 and D105:** an interrupted release that already moved hand-written entries needs a hand reconcile, and a drop that could not be deleted shows up again.

## Priority 3: smaller items and triage

- **D103:** known limits, such as an identical hand-written entry and drop entry appearing twice.
- **D69 and D71:** a duplicated frozen trace, and the rough Windows process kill in the conversion check.
- **D63:** run the conversion check and the "passing" check in CI. This needs a workflow change, and its acknowledgement is the operator's.
- **D113:**
  - the stale closing summary;
  - the release-notes condenser rewriting vacuous bullets;
  - empty decision indexes;
  - a missing `ci-security.json` in projects without CI;
  - `SHIPWRIGHT_PLUGIN_ROOT` not set in a subagent;
  - the upgrade-note wording;
  - "close-phase runs twice", which is only implied.
- **STOP3-REPORT observations:**
  - the empty preview is still shown;
  - the untracked `triage.jsonl` after the release audit;
  - the audit exits 0 with `any_fail: true` (a question for the compliance plugin);
  - a re-dated identical section.

## After-campaign items already confirmed (2026-11-25)

- **Q3:** a release started by hand while an automatic release runs is refused, naming the running one, with an explicit override.
- **Q9:** a pending note can be marked "breaking" on purpose, which raises the major version. Nothing is guessed from the text.

## Also open

- **D66:** where the stop-3 harness (`runscenario.py`, report, model shim) lives. Proposal: the generic parts go to `shared/scripts/tools/`, and the model shim stays with the operator.
- **Next plugin:** discuss more end-to-end automation before the next conversion starts. The lessons are in LEARNINGS, "Stop 3".
