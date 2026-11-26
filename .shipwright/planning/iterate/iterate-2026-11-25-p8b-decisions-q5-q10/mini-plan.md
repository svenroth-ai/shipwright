# Mini-plan: P8b, decisions Q5, Q6, Q7, Q8, Q10 and fixes F8, F9

Scope set by the operator on 2026-11-25 (re-scope, binding): port the release behaviour one to one, only made
deterministic; fix bugs and contradictions; nothing new. Q9 is out. Unsure items STRICT-STOP; new ideas go to FINDINGS.

## Changes

1. **Q5 (AC09) hand-written `[Unreleased]` entries move into the release.** New `shared/scripts/changelog_unreleased.py`
   (`take`, `marked`): bullets under one of the six category headings move, with continuation lines, into that category
   of the new section after the drop bullets. Bullets under no heading stay and are named as before (no guessing).
   `aggregate_changelog.py --move-unreleased` (only `release.py aggregate` passes it); the dry run's `section_preview`
   marks them `(hand-written)`.
2. **Q6 (D20)** the three proposed promises become `passing` entries with test checks on the existing L1 tests; no new
   AC, `spec.md` unchanged. `test_promises_meta.py` lets an entry without an AC id be pinned by a non-promise test.
3. **Q7 (D9)** remove `--from` from `release.py prepare`, the banner, `SKILL.md`, guide 4.8 and Appendix B. Build nothing;
   `rerunning-a-release.md` was checked first and now says a re-run is not "start from X".
4. **Q8 (D16)** `release_version.normalize`: strip one leading `v`, refuse non-SemVer (usage error). `prepare` refuses a
   version not above the last tag (`version_not_above_last_tag`); a non-SemVer last tag is noted, not compared.
5. **Q10 (D15)** `release.py pr-body` writes `## Changelog` + this version's section to a file in the git dir; Step 7
   passes `--body-file`. Title and content as the skill says today; no compare link (difference recorded in FINDINGS).
6. **F8** `refresh_compliance_docs.py` snapshots the index of the seven before the producers and restores it on any
   refusal (`compliance_git.index_entries` / `restore_index`).
7. **F9** the cherry-pick fallback writes a drop file (`write_changelog_drop.py`, run id `release-fallback`) before the
   real aggregation, instead of appending to `[Unreleased]`.

## Tests

- `plugins/shipwright-changelog/tests/test_release_p8b.py` (Q7, Q8, Q10, F9, Q5 wiring), `shared/tests/test_changelog_unreleased.py`
  (Q5), `shared/tests/test_refresh_refusal_unstages.py` (F8); each fails on the old code.
- Golden: S10 (F9), S16b (F8), S19 (Q7), eleven PR traces (`--body-file`); both drivers agree; every frozen change is an
  approved delta with a per-file source; `golden_lock.py --check` exits 0.

## Alternative approach considered

Q5: fold unheaded bullets into a guessed category ("Changed") — rejected, that is a guess and would move AC09.
Q10: add the compare link and change the title to `chore(release): vX.Y.Z` — rejected by the re-scope (new behaviour).
