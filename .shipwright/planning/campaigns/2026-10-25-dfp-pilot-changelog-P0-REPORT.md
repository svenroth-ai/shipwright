# P0 report: deterministic-first pilot of `/shipwright-changelog`

**Unit P0, 2026-11-14, tree `92dfee901` (origin/main at unit start).** Input of operator stop 1. Companion files: `...-FINDINGS.md` (what is wrong), `...-LEARNINGS.md` (what the method taught), and in `.shipwright/planning/campaigns/2026-10-25-dfp-pilot-changelog-inventory/`: `inventory.json`, `truth_table.json`, `subprocess_map.json`, checked by `shared/scripts/tools/check_skill_inventory.py`. Counts below are measured outputs, not targets.

## 1. Pin list (found by breaking the prose)

Method: a throwaway worktree on `92dfee901`; `SKILL.md` and the nine references other than `release-notes-prompt.md` replaced by one line `PLACEHOLDER`; the five roots run once each, one pytest process per root, no `-n`.

**Result: 30 tests in 13 files fail with the prose broken, the same set the brief lists (rev 6, MEASURE section 8): no difference.** Every name below was read from the pytest summary of the broken pass.

| Root | Failed | Files (tests) |
|---|---|---|
| `plugins/shipwright-changelog/tests` | 18 of 111 | `test_skill_event_blocks_behaviour.py` (7: AC01, behaviour through prose, a promise candidate that rebinds to the CLI), `test_skill_release_flag_wiring.py` (4, no `covers` mark), `test_skill_event_ships_in_release_pr.py` (3), `test_skill_upgrade_notes_check.py` (2), `test_changelog_judgement_drift.py` (1), `test_setup_changelog_version_suggestion.py` (1) |
| `shared/tests` | 10 of 14,681 | `test_events_drop_hardening.py` (4: behaviour through prose), `test_release_pathspec_doc_sync.py` (3), `test_canon_marker_write_contract.py` (1, FR-01.01), `test_events_reference_guard.py` (1), `test_phase_gate_discipline_present.py` (1) |
| `integration-tests` | 2 of 685 | `test_multi_session_removal_residue.py` (1), `test_phase_skill_invocation_mode_canon.py` (1) |
| `shared/scripts/tests` | 0 (704 passed, 3 skipped) | |
| `shared/scripts/tools/tests` | 0 (1,502 passed, 21 skipped) | |

Constraint, not pin (programme P11): the five cross-plugin guards in the brief (`test_canon_marker_write_contract.py`, `test_phase_gate_discipline_present.py`, `test_events_reference_guard.py`, and the two integration tests) fail here too; the thin `SKILL.md` must keep satisfying them. `test_condense_release_notes.py` and `test_changelog_aggregation_idempotency.py` do not fail: not pins. Granularity: a failing test says the prose is pinned, not which section; the inventory's per-section mapping to the pins is a job for P5. This tree adds no pin: the checker's tests use throwaway skills only.

## 2. Promise list (programme P18, P19)

"Driver-level" means: the replay driver of P2b runs today's command sequence on a scratch project and the test asserts the outcome. Count of ACs that can get a green driver-level test against the unchanged skill: **14 of 15** (more than half; AC11 cannot, see below). Counted strictly, without the conditions named in the next sentence and in the AC01 and AC10 rows, it is 10 of 15 (AC01, AC10, AC14 and AC15 are conditional yeses); still more than half. Two of the 14 rest partly on the replay trace alone (`oracle: trace`): AC01 (the PR exists: the `gh` stub log) and AC15 (second half, no back-fill: nothing happens). AC14 and AC15 also need P1's `gh` and fixture-model seams first.

| AC | Promise in plain words | Existing `covers` candidates | Driver-level test against the unchanged skill |
|---|---|---|---|
| AC01 | after a release run there is a readable note, a version tag, and an open request to deliver it | `test_skill_event_blocks_behaviour.py` (6 marked; behaviour through prose, rebinds to the CLI), `test_skill_event_ships_in_release_pr.py` (3), `test_skill_upgrade_notes_check.py` (3), `test_changelog_judgement_drift.py` (1): text pins | yes for the note and the tag (S14a). The PR part needs the head branch pushed before the run; today's order opens the PR first (D7), where the stub refuses and the replay records the refusal. Counted yes with that precondition (13 of 15 if the operator wants the unpushed-head path as the promise). PR via the stub is `oracle: trace` |
| AC02 | entries are grouped by kind of change | `test_changelog.py` (1): **not on the skill's path** (finding D13) | yes: S2g; needs a new test on the drop directories |
| AC03 | nothing recorded since the last release: it says so and stops | `test_changelog_aggregation.py` (4) | yes: S5a, S5b |
| AC04 | next version: break raises the first number (second before 1.0), feature the second, else the third; none yet: 0.1.0 | `test_git_utils.py` (5), `test_setup_changelog_version_suggestion.py` (4) | yes: S1, S2, S3, S4. A break recorded only in a drop (S3b) is today's gap D5, not a promise |
| AC05 | decision numbers are assigned once, at release | `test_aggregate_decisions.py` (1) | yes: S10 |
| AC06 | the new section goes above the latest released one; title and older entries stay | `test_changelog_aggregation.py` (1) | yes: S2 and others |
| AC07 | writing a version again replaces its section; two sections for one version stop the write | `test_changelog_aggregation_idempotency.py` (3), `..._refusal.py` (1) | yes: S6, S7c |
| AC08 | a section that no longer matches the pending entries, or is marked withdrawn, stops the write and says which | `test_changelog_aggregation_refusal.py` (2) | yes: S7a, S7b |
| AC09 | entries written the old way are named back to the operator | `test_changelog_aggregation.py` (1) | yes: S8 |
| AC10 | the whole release can be previewed without anything changing on disk | `test_changelog_aggregation_refusal.py` (2) | yes: S9, when no migration page changed (otherwise the upgrade-notes check writes a drop before any preview, D12) |
| AC11 | preparing a release publishes nothing until the request is merged | `test_changelog_aggregation.py` (1): the aggregation half only | **no, as one promise for all modes**: guided and driven runs push tags and create the release page before the merge (D2), so it is red there; it is green in standalone autonomous and unattended, where the merge comes first (and AC01's open request is then absent). A driver test per autonomy cell would be green in some cells and red in others, so it cannot be one test; counted as no. The aggregation half (ledger row 9a) can be protected |
| AC12 | the version is written into every declared manifest in the release commit and checked before the tag | `test_sync_release_manifests_git.py` (2) | yes: S11a, S11b |
| AC13 | every version occurrence in a manifest is written together | 21 tests (`test_manifest_sync_core_lock.py` 17, `..._marketplace.py` 1, `..._git_lock.py` 3) | yes: S11a (nested catalog) |
| AC14 | a release page with a checked summary, tag and link built from facts | `test_validate_release_notes.py` (3), `test_create_github_release.py` (2); `test_publish_release_notes.py` has no mark | yes: S12a, S12b, after P1's code seams (the prose stays unchanged) |
| AC15 | a failed release page does not undo the release and is reported; old versions get no page | none | yes: S12c (first half), no-back-fill half `oracle: trace`; after P1's code seams (the prose stays unchanged) |

Ledger side (both ways, in `2026-07-23-req3-ac-evidence-ledger-mono.md`): AC02 drops to `enforced, untested`, AC06 is `enforced, tested` on the aggregator's test, AC11 splits into 9a and 9b, AC07/AC08/AC12-AC15 get rows. Counts after: 0 / 25 / 15 / 26 / 98 (row 5, AC05, also moves from `enforced` to `enforced, tested` on `aggregate_decisions.py`).

## 3. P24 "before" measurement

Measured on the tree above, one root per process, JUnit durations (the five roots of the broken pass ran in parallel on a busy machine, so the big roots are slower than what an iterate pays; MEASURE section 3 and 7.3 make the same caveat).

| Measure | Value |
|---|---|
| Changelog test root | 111 tests, 7.1 s pytest time (6.9 s summed from JUnit; about 15 s wall-clock with `uv` start) |
| The 18 changelog pins | 3.8 s of the 6.9 s |
| The 10 pins in `shared/tests` | 1.1 s (the five pin files alone: 56 tests, 9.3 s wall-clock) |
| The 2 pins in `integration-tests` | under 1 s (the two files alone: 51 tests, 1.7 s) |
| All 30 pins | about 5 s of test time |
| Other roots, full run (same parallel pass) | `shared/tests` 14,681 tests in 1,483 s (24 min 42 s), `integration-tests` 685 in 403 s, `shared/scripts/tools/tests` 1,502 in 186 s, `shared/scripts/tests` 704 in 25 s |
| Prose size | `SKILL.md` 440 lines; ten reference files, 707 lines in total |

Pins cost almost no machine time; their cost is that they tie 13 files to the wording of one prompt. The saving report (P24, at P7) compares these numbers with the end state.

## 4. Stack profile key listing (programme section 8)

`shared/profiles/*.json` carry these top-level keys (number of files in brackets): `architecture_rules` (1), `rules` (4), `linting` (5), `testing` (5), `test_gate` (3), `ci` (1), `traceability` (1), `confidence` (3), `known_gaps` (3), `folder_structure` (5), `stack` (5), `deploy` (4), `dev_server` (4), `required_env_vars` (4), `migrations` (4), `pre_deploy_safety` (3), `rollback` (3), `smoke_test` (3), `environments` (3), `error_tracking` (1), `auth` (3), `client` (3), `services` (2), `design_system` (1), `ui`, `ux_shape`, `ui_host` (2 each), `env_files` (2), `package_manager` (4), `languages` (1), `catalog_codes` (1), `implementation_status` (3), `notes` (3), plus identity and schema keys (`name`, `description`, `version`, `profile_schema_version`, `target_id`, `target_kind`, `$schema`, `$id`, `title`, `type`, `properties`, `required`, `allOf`, `additionalProperties`, `$defs`, `_skill_companion`). Keys that carry a rule or a gate: `architecture_rules`, `rules`, `linting`, `testing`, `test_gate`, `ci`, `traceability`, `pre_deploy_safety`, `rollback`, `smoke_test`, `migrations`.

**Result:** the changelog skill and the release tools it runs read no stack-profile key (no `PROFILE_KEYS_READ` in the changelog plugin, `aggregate_*`, `sync_release_manifests`, `refresh_compliance_docs`, `publish_release_notes`, `create_github_release`, `condense_release_notes`, `fold_events_for_release`, `record_event`). The only changelog reference in the profile directory is the word "release" in a deploy comment. No profile changes in this pilot (programme section 8).

## 5. Questions for the operator where FR-01.09 and the guide are silent (plain language)

Each answer becomes a finding or a follow-up; the conversion itself keeps today's behaviour.

1. **Tag and release page before or after the merge?** When a release is prepared on a working branch and a review request is opened, today the version label and the public release page appear right away, before anyone has accepted the request. The requirement says nothing is released until the request is merged. Should the label and the page wait for the merge? (D2, D7)
2. **Should an automatic run merge the release request itself?** One part of the skill says yes when the run is hands-off, another part says a hands-off pipeline run always leaves the request open for a person. Which one is right? (D8)
3. **A release started by hand while an automatic run is going.** The instructions say it asks you whether to carry on; the pipeline's rules say it must stop and hand the question back to the automatic run instead. Today it is not settled which happens, and with "hands-off" set it can wait for an answer nobody gives. Should it ask you, refuse, or carry on? (D19)
4. **Cancelling at the preview.** By the time you see the preview, the changelog file is already written and the pending notes are already used up. Should "cancel" put everything back as it was, or is leaving it as it is fine? (D12)
5. **Old-style entries.** Entries someone wrote straight into the "Unreleased" section are only reported, never moved. Should the release move them into the new version automatically, or keep just warning? (AC09, guide step 4)
6. **Things the release does that no requirement mentions.** It tells existing projects what they must do after upgrading (the upgrade-notes check), tidies old event files, and records the release in the project's history. Should these become written promises of the release, or stay as housekeeping nobody promised? (D20)
7. **"Start from version X".** The help text and the guide promise a way to start the release from a given earlier version label. It does not exist. Build it, or remove the promise? (D9)
8. **A version typed in by hand.** If you type a version with a leading "v" or something that is not a version number, the skill accepts it and builds a wrong label. Should it refuse and ask again? (D16)
9. **A breaking change written only in a pending note.** Today only commit messages decide the version number, so such a change gives a minor or patch number. Should pending notes count too? (D5)
10. **The release request description.** It currently shows a literal "\n" instead of line breaks, and the text it should show is not defined. Fix it in the follow-up? (D15)
