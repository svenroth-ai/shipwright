# STOP 3 (P7-op) plan: deterministic-first pilot of `/shipwright-changelog`

**State on 2026-11-26.** Every unit of the campaign `dfp-pilot-changelog-p3-p8` is merged: P3 #1099, P4 #1100, P4b #1101, P5 #1102, P6 #1103, P7 #1107, P8a #1109 and P8b #1110. The plugin under test is `main` at `f73a33d8a` (P8b), and the plugin cache is synced to it. This file says what stop 3 needs and in which order. The procedure itself is defined in the pilot BRIEF, section 5, "P6, P7, P7-op".

## What stop 3 proves

Stop 2 froze today's behaviour as 43 replay traces, plus 43 real-model runs against the old prose (`2026-10-25-dfp-pilot-changelog-FULLRUN-REPORT.md`). Since then the CI has checked the new CLI against those traces on every PR, and every difference is listed in `approved_deltas.json` with its source. What is **not yet** shown is that a real model, driving the thin `SKILL.md` and `release.py`, behaves as well as it did with the old prose. Stop 3 shows that, and then releases for real.

## Before stop 3 can start

1. **Harness (FINDINGS D66).** The full-run harness (`runscenario.py`, `fullrun_report.py`, `gh_model_shim.py`, `agg.py`) and the stop-2 baseline runs are outside the repo, at `C:\Users\SvenRoth\shipwright-stop3-harness`. Recommended: run it from there once more for stop 3, then move the generic parts (scenario runner, report) to `shared/scripts/tools/` as a separate change; the model shim stays with the operator. The operator's answer is needed before step 1 below.
2. **Plugin hash.** Record the hash of the plugin as loaded (`main` at `f73a33d8a`). The checker refuses the T1 hash.
3. **Scenario list.** Use the 43 stop-2 scenarios plus the ones added since, which have no frozen trace yet (D107): S14d (default branch `develop`, release on `main`), S18c (Edit, then Cancel), a categorised hand-written `[Unreleased]` entry (Q5), and a run of `pr-body` (Q10).
4. **Fork sample.** P2-op made none (the FULLRUN-REPORT has no fork run). So the fork comparison of programme P23 is skipped, and the report says so.
5. **Canary repo.** A throwaway repository with a private remote, for step 3.

## Steps

1. **L3 runs.** Each scenario is run with an Opus subagent driving the plugin from `f73a33d8a`, as at stop 2: no headless `claude -p`, no `bypassPermissions`. Every difference from the stop-2 run of the same scenario is one of:
   - an approved delta (already in `approved_deltas.json`, so expected);
   - a harness artefact;
   - a finding.
   Nothing is accepted silently.
2. **Report.** `fullrun_report.py` writes `2026-10-25-dfp-pilot-changelog-STOP3-REPORT.md`, laid out like the stop-2 report: matches, harness artefacts, model errors, ambiguous prose, and replay-vs-prose differences.
3. **Canary release.** One real release in the canary repo: the full flow through PR, merge, tag, release page and closing check, with the release guard hook active.
4. **Operator decisions.** The operator answers the list below.
5. **Re-pin.** `golden_lock.py --plugin shipwright-changelog --repin` adds the new scenarios of D107 and folds the pinned prose snapshot (D99). This empties `approved_deltas.json`, and the review reads the printed `entries`.
6. **First real release** of the monorepo with the converted plugin.
7. **Hand-over.** FINDINGS and LEARNINGS become the input of the follow-up campaign, together with the after-campaign items below. **STOP 3** closes.

## Decisions the operator answers at stop 3

Each item is phrased by what it changes in practice. The D number points to the detail in FINDINGS.

**Confirm what was built (default: keep as built)**
- D34 and D38: the release guard allows the small event commit after the release commit. A declined release blocks pushes in that checkout for up to 48 hours, or until `SHIPWRIGHT_RELEASE_GUARD=off`.
- D37: two shared files outside the planned touch set were edited for the guard hook, and `gh pr merge` is held only for the release's own PR.
- D39 and D40: the tag push stays a visible command in the skill. `release.py push-tag` only decides which command to run, so the guard hook can still see the push.
- D44: in a run started by the pipeline in guided mode, the tag is pushed while the PR is still open. Waiting would mean the tag is never pushed, because the pipeline never comes back to this step. The alternative is to stop with a note for a person.
- D45: the one allowed exception to "the skill only names commands" lives in a registry file, not in the skill text.
- D51: the skill's size cap is now 263 lines. Keep the entry, or drop it.
- D60: the check "every requirement has a test that judges it" was kept, in a new file. Deleting it is possible but cannot be undone.
- D96: the PR title stays "Release vX.Y.Z" and the body has no compare link. Change either?
- D92: a hand-written changelog entry without a category heading stays in "Unreleased" and is named, never sorted in by guessing. Should such entries go somewhere?
- D100 (decided by the orchestrator): a release version must be higher than the last release tag **on the same branch**, so backports keep working.

**Gaps to schedule (default: follow-up campaign)**
- D89: the release guard knows only `main`, `master` and `develop` as main branches. In a repo whose default branch has another name (e.g. `production`) the guard does not protect it.
- D90: on Windows, a hung git helper can outlast the 30-second limit of the default-branch lookup.
- D63: the conversion check and the "passing really passed" check are not part of CI. A CI step needs a workflow change and its acknowledgement.
- D102 and D105: an interrupted release that already moved hand-written entries must be reconciled by hand. A drop file that could not be deleted shows up again in the next release.
- D103: known limits, such as an identical hand-written entry and drop entry appearing twice.
- D69 and D71: one frozen trace duplicates another, and the conversion check's process kill has rough edges on Windows.

**After the campaign (confirmed by the operator on 2026-11-25, built as separate changes)**
- Q3: a release started by hand while an automatic release is running is refused, naming the running one, with an explicit override.
- Q9: a pending changelog note can be marked "breaking" on purpose, which raises the major version; nothing is guessed from the text.

## What carries to the next plugin

- **Method:** programme BRIEF, P17 and P17a (the operator rule on how a unit sorts what it finds), with the per-plugin template in its section 5.
- **What the pilot taught:** `2026-10-25-dfp-pilot-changelog-LEARNINGS.md`, with a section per unit and a closing summary.
- **What it saved:** `2026-10-25-dfp-pilot-changelog-SAVING-REPORT.md`.
- **Reusable tools:**
  - `shared/testkit/golden_lock.py` (freeze and deltas);
  - `shared/scripts/tools/check_prompt_mechanics.py` with `shared/config/converted_skills.json` (the skill names commands and does not explain them);
  - `shared/scripts/tools/check_plugin_conversion.py` with `shared/config/plugin_conversion.json`;
  - `shared/scripts/tools/junit_promises.py`.
- **Stop-3 harness:** the location is decided at stop 3 (D66).
