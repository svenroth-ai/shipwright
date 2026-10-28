# Baseline protection (BP): REPLAY report for operator stop 1

**Unit:** BL0 · **Run:** `iterate-2026-10-28-bl0-touch-library-and-replay` · **Brief:** `2026-10-27-baseline-protection-BRIEF.md` (section 5, item 1)
**Data:** `2026-10-27-baseline-protection-REPLAY.json` (next to this file; every number below is recomputable from it). Captured against `origin/main` at the time of the run; the 100 PRs are #937 down to #840 (merged 2026-10-02 .. 2026-10-28).
**Reproduce:** `uv run shared/scripts/tools/replay_baseline_lock.py --repo . --limit 100 --out replay.json` (derived legs, git only; add `--code-sample 20 --probes 5 --workdir <dir outside the repo>` for the context runs; `--from-json replay.json` re-summarises without git).

This report measures; nothing gates. Nothing in `ci.yml`, `verify_local.py`, `deliver_pr.py` or any gate changed. The campaign halts here.

## 0. Headline in plain language

- If BP held every PR whose diff touches an existing requirement, with no approved scope, **39 of the last 100 PRs (39 %) would have waited for you.** Half of the iterates (25 of 50) and 13 of 30 campaign-unit PRs. Docs, dependency-bot, manual and release PRs were never held (0 of 18).
- In **27 of those 39** the author had themselves recorded the same requirement as affected (`affected_frs`). Those holds are friction, not surprises: they stop only because a single iterate has an empty approved scope. **12 PRs (12 %) touched a requirement the author never named**; those are the interesting ones, and the ones you are asked to re-label (section 9).
- If the approved scope were exactly what the author declared, the hold rate would be **12 %**, not 39 %. That is the real size of "unplanned change"; the rest is the cost of requiring an approval.
- **Production code is where the blind spot is.** Of the functions any test executes, only **38 %** are executed by a test that is bound to a requirement. A seeded change to such a line is noticed (5 of 5 probes, by T-code only); a change to a line executed only by unbound tests is not (0 of 4); a change in a `SKILL.md` is not (0 of 5).
- The `fr_impact` map is almost never recorded: **0 of the 100 PRs** carry one. 45 carry `affected_frs`. The declaration is too sparse to stand in for the derived set, which is the brief's premise.

## 1. Stop-1 checklist (brief section 5, item 1)

| Input | Where | Status |
|---|---|---|
| Base rate: PRs with a non-empty touched set | section 2 | 39 / 100 |
| Base rate: PRs carrying `fr_impact` | section 2 | 0 / 100 (45 / 100 carry `affected_frs`) |
| Hold rate per PR class | section 3 | measured |
| T-code fan-out and proposed N | section 5 | measured; N = 5 proposed |
| Mutation-probe results | section 6 | 14 conclusive probes |
| Labels per hit | section 8 | provisional by rule; operator re-labels |
| Random sample for the operator | section 9 | 15 PRs |
| BP's own `scope_frs` proposal | section 10 | proposed |
| Verifier wall-clock (5 iterates), context-run cost | section 7 | measured |
| Decisions for you | section 11 | listed |

## 2. Base rates

| Measure | Value |
|---|---|
| PRs replayed / errors | 100 / 0 |
| Touched set non-empty (T-spec + T-test + static test-dir attribution) | 39 (39 %) |
| Carries `fr_impact` | 0 |
| Carries `fr_impact` or `affected_frs` | 45 |
| Derived and declared agree (share at least one FR) | 27 |
| Derived only (author named no matching FR) | 12 |
| Declared only (author named an FR, the diff touches none) | 18 |
| PRs with a "moved" test (listed, not touched) | 4 |
| PRs whose evidence was incomplete (would be held fail-closed) | 0 |
| FRs per touching PR | 32 PRs touch 1 FR; 5 touch 2-3; **2 touch 18** (see below) |

The two 18-FR PRs (#860, #873) both change `shared/tests/conftest.py`, which is attributed scope-wide to every test below it. They are the "shared helper" case the brief expects; section 5 proposes treating them as broad. Without them the hold rate is unchanged (37 %): they were already held through a real test edit.

"Declared only" (18): documentation, planning and tool PRs whose author lists a requirement they relate to without any bound test or spec text changing. A derived set cannot see these by design; they are not misses of the guarantee in section 0 of the brief.

## 3. Hold rate per PR class (empty approved scope)

| Class | PRs | Held | Rate |
|---|---|---|---|
| iterate | 50 | 25 | 50 % |
| campaign-unit | 30 | 13 | 43 % |
| layer-promotion | 2 | 1 | 50 % |
| dependency-bot | 8 | 0 | 0 % |
| docs | 5 | 0 | 0 % |
| manual | 4 | 0 | 0 % |
| release | 1 | 0 | 0 % |
| revert | 0 | - | - |

Class is derived from the branch and title (`replay_baseline_lock.py` via `pr_class`). **Release and layer-promotion** (decision S10 of the brief): the one layer-promotion PR that was held (#886) edited an FR-01.10 test; the other (#915) touched nothing derived. The one release PR (#875) touched nothing. No revert occurred in the window, so that class is unmeasured. Campaign units have no `scope_frs` yet (the field does not exist in any historical brief), so their rate here equals the empty-scope rate; with a correct `scope_frs` it would fall toward the 12 % of section 0.

## 4. Which source notices what

| Source | Hits | Of which the author also declared | Not declared |
|---|---|---|---|
| T-spec (normative text changed) | 5 | 5 | 0 |
| T-test (bound test modified / deleted) | 36 | 21 | 15 |
| Static test-dir attribution (fixture, conftest, helper) | 56 | 14 | 42 (34 from the two conftest PRs, 8 otherwise) |
| T-code (context run, 20 PRs, see 5) | 2 PRs | - | - |

T-spec is quiet and precise. T-test carries most of the signal. Static attribution is the noisy source: apart from the two scope-wide conftest PRs it produced 20 hits, 8 of them undeclared.

## 5. T-code: fan-out, proposed N, coverage limits

**Method.** For the 20 most recent PRs that changed Python production code inside a measured target, a detached worktree of the merge base ran four test tiers with `--cov-context=test` (`shared/scripts/tools/tests`, `shared/scripts/tests`, `plugins/shipwright-iterate/tests`, `plugins/shipwright-changelog/tests`; coverage targets `shared` and those two plugins' `scripts`). The PR's own diff was attributed through those contexts (enclosing function for added or deleted lines).

**Result.** Only **2 of 20** PRs had a changed line executed by an FR-bound test (#915: 1 function, 1 FR; #899: 9 functions, 8 FRs). 167 changed functions across the 20 PRs were "executed by no FR-bound test" (or not measured by these four tiers). This is the brief's disclosed limit, quantified: most production changes are invisible to T-code today because most tests carry no requirement tag.

**Fan-out** (FRs reached per function, all 1000 executed functions in the measured files at HEAD, two tiers, `fanout.py` logic in section 12): 619 functions are executed by no bound test (fan-out 0), 367 reach 1 FR, 2 reach 2, 5 reach 3, 4 reach 6, 2 reach 7, 1 reaches 8. Median of the non-zero ones is 1; p95 is 1; max 8. The wide ones are shared infrastructure (`atomic_write.py`, `durable_publish.py`, `profile_test_isolation.py`).

**Proposal for N: 5.** A function reaching more than 5 FRs is "listed, not held". At HEAD that is 7 of 1000 executed functions (0.7 %), all shared plumbing (fan-outs 6, 6, 6, 6, 7, 7, 8); N = 2 would list 12 functions, N = 8 none. This is conditional: it rests on two tiers. With all tiers measured the fan-out only grows, so BL2 should re-measure before N is frozen (the shadow period is the check). The same threshold should apply to scope-wide static attribution (the two 18-FR conftest PRs).

## 6. Mutation probes (which source notices a seeded production change)

Fifteen probes over five of the 20 PRs, three per PR, run in the PR's merge-base worktree over the real context databases (re-run with the final probe code; one probe whose seeded edit did not parse is not counted).

| Probe | Conclusive | Noticed | By which source |
|---|---|---|---|
| Line executed by an FR-bound test | 5 | **5** | T-code only |
| Line executed only by tests with no FR binding | 4 | 0 | none |
| A `SKILL.md` line (prose) | 5 | 0 | none |

So: T-code is the only source that sees a production change, and only where a bound test runs the line. Prose and shell are outside every source, as brief section 0 states; here it is measured. If you decide at stop 1 that prose matters, BP does not cover it and the plugin conversions are what shrink it.

## 7. Costs measured

- **Verifier wall-clock** (`verify_iterate_finalization.py` against five merged iterate commits): 1, 2, 2, 2, 2 seconds. Negligible next to CI.
- **Context run vs plain run.** `shared/scripts/tools/tests`: 151 s with `--cov-context=test` vs 148 s without (+2 %); database 1.19 MB vs 0.10 MB (12x). `plugins/shipwright-changelog/tests`: 7.2 s vs 9.4 s (noise). Contexts cost almost nothing in time and about 12x in artifact size.
- **Per-root context-run time, every root once** (while a second replay shared the machine, so upper bounds): `shared/tests` 22.0 min (17 tests failed in this environment, unrelated to BP), `integration-tests` 5.7 min, `plugins/shipwright-compliance` 3.2 min, `shared/scripts/tools/tests` ~2.5 min, `plugins/shipwright-run` 53 s, `plugins/shipwright-test` 54 s, the remaining 12 roots under 50 s each. About 41 minutes if run one after another; CI runs them in parallel jobs. `plugins/shipwright-grade` collected with 10 errors when run from the repo root.
- **Four-tier context run per PR** (the subset used here): median 206 s.

## 8. Labels

I cannot label `correct-harmful` from the diff alone; that needs your knowledge of what each PR was supposed to change. What the data allows, by a mechanical rule:

- **correct-benign (friction), provisional:** a held PR whose touched FR the author also declared. **27 PRs.** These would be approved once and listed.
- **needs your label:** a held PR with a touched FR the author did not declare. **12 PRs** (#921, #919, #918, #910, #908, #900, #887, #886, #869, #855, #848, #843) plus the 2 conftest PRs.
- **wrong (the source mis-attributes):** none can be asserted without you. Upper bounds if every undeclared hit were wrong: T-spec 0, T-test 15 hits in the 12 PRs, static 8 outside the two conftest PRs. The brief's bar is "at most 3 `wrong` per 100 PRs per source"; **T-spec passes outright; T-test and static cannot be shown to pass without your labels**, and static attribution should be expected to need work (it is the least precise source).

Spot reads by me, not labels: #848 (Dependabot setup) and #843 (PR-review model switch) edit tests bound to FR-01.07 as a side effect of their change; that reads as `correct-benign`. #910 / #919 / #921 edit profile-resolver tests bound to FR-01.06, with no `affected_frs`: plausibly real unrecorded impact.

## 9. Random sample for you to re-label

Fifteen held PRs, seeded sample (`random.Random(20261028)`, reproducible). For each: is the listed FR really affected? Label `correct-harmful` (a behaviour change you would have wanted to see), `correct-benign` (right FR, harmless), or `wrong`.

| PR | Class | Title | Sources | Author declared | Evidence |
|---|---|---|---|---|---|
| #919 | campaign-unit | feat(profiles): bundle a chat-first-json stack profile | FR-01.06 | - | test_non_profile_files_never_listed |
| #922 | campaign-unit | feat(design): Design takes the Brief package (B3a) | FR-01.01, FR-01.04 | FR-01.04 | static _brief_harness.py, conftest.py |
| #843 | iterate | feat(pr-review): switch the PR-review gate default model | FR-01.07 | - | TestFileContract.test_every_re_exported_name_resol... |
| #869 | iterate | feat(iterate): campaign runner reviews use the resolved tier | FR-01.10, FR-01.11 | - | test_runner_spawns_internal_reviews...; static conftest.py |
| #921 | campaign-unit | fix(test): Windows-safe npx spawn, Browser Verify URL | FR-01.06, 01.12, 01.13 | - | test_existing_fixtures_match_the_same_profile... |
| #910 | iterate | fix(project): write the project config to the project root | FR-01.06 | - | test_write_project_config_profile_lookup_root... |
| #860 | iterate | fix(iterate): campaign runner passes the lease token | 18 FRs | FR-01.11 | test_hook_is_registered_for_both_events; static conftest.py (scope-wide) |
| #874 | iterate | fix(review): close the U0/U3/U4/U10 review-record follow-ups | FR-01.11 | FR-01.11 | test_a_stage_1_reject_is_not_recorded_as_completed |
| #840 | campaign-unit | feat(finalization): review record and test ledger enforced | FR-01.11 | FR-01.11 | static _review_cli_harness.py |
| #871 | iterate | feat(iterate): Stop hook keeps an autonomous iterate running | FR-01.11 | FR-01.11 | spec text of FR-01.11 changed |
| #848 | iterate | chore(ci): activate Dependabot for github-actions only | FR-01.07 | - | test_deleting_the_register_cannot_silence... |
| #882 | iterate | fix(iterate): stop guard stays silent while a reviewer runs | FR-01.11 | FR-01.11 | test_incremental_scan_resumes... |
| #905 | campaign-unit | feat(profiles): custom stack profiles in the interview | FR-01.06 | FR-01.06 | test_missing_shared_tree_is_an_install_error...; moved test |
| #847 | campaign-unit | fix(compliance): a logged override lets the coverage gate pass | FR-01.10 | FR-01.10 | test_inproc_legacy_section_line... |
| #879 | iterate | fix(triage): raise one card per critical/high security finding | FR-01.14 | FR-01.14 | test_import_findings_auto_resolves_fixed_alert |

Full evidence for any PR: `2026-10-27-baseline-protection-REPLAY.json`, `records[].evidence`.

## 10. BP's own `scope_frs` (proposal)

BP changes the delivery, finalization and CI-gate machinery. Proposed, for approval at stop 1:

- **FR-01.11** (/shipwright-iterate): finalization checks, the verifier, delivery, campaign step 3g/3f-bis. The FR the replay shows touched most (13 of 39 holds).
- **FR-01.10** (/shipwright-compliance): the F11 checks and required-checks drift tooling BL6 touches.
- **FR-01.17** (independent re-check on the code host): `baseline.yml` and the required checks.
- **FR-01.01** (/shipwright-run): `campaign-mode.md` is the orchestrator contract BL1/BL3/BL4 edit; the replay shows run-plugin tests attributed to FR-01.01 in 7 holds.

Not proposed: FR-01.09 (changelog; only BL6's guide/glossary text, which are not FR behaviour) and FR-01.06 (the test phase is not changed). Until you approve, BP's own PRs report as out of scope in shadow, as the brief expects.

## 11. Decisions for you (plain language)

1. **N (broad threshold):** how many requirements one shared function may reach before a change to it is only *listed* rather than *held*. Proposal 5 (section 5). Smaller means more holds on shared plumbing; larger means shared plumbing is waved through.
2. **Rule per PR class:** release, layer promotion, revert, manual. Measured: 0 of 18 docs/bot/manual/release PRs were held; the layer-promotion PR that was held changed a bound test. Proposal: apply the same rule to layer promotion, exempt release PRs that contain no code or test change, and decide revert when one appears.
3. **BP's own `scope_frs`:** section 10.
4. **The P3.8 supersession** (an edited test body under an unchanged AC becomes a hold for out-of-scope FRs only): unchanged by this unit; the replay shows T-test is the largest source (36 hits) and half of its hits are undeclared, so the supersession is what makes BP bite.
5. **Whether BP proceeds.** Facts for the decision: the guarantee covers 12 % of PRs as real unplanned change plus 27 % as approval friction; production code is covered only where a bound test runs it (38 % of executed functions, 2 of 20 sampled PRs saw any T-code hit); prose, shell and config are not covered at all. If you judge 39 % friction too high before `scope_frs` exists, the choice is to start with T-spec + T-test only (the shadow window will tell) rather than T-code, which costs BL2 (a large unit) for a signal that fired in 2 of 20 PRs.
6. **Thresholds for stop 2:** the hold-rate and friction-rate numbers above are the baseline to set them against (hold 39 %, of which friction 27 %).

## 12. Deviations from the brief and disclosed limits

- **T-spec reader.** The brief names keystone's AC digest. Keystone's digest covers acceptance criteria only and keys them by AC id, while the brief's own ignore list says AC-id tokens are not a change and the catalog row's statement is. A purpose-built reader (row + section prose + criteria text; order- and marker-insensitive) implements that list. Keystone's digest was tried as a union and rejected (it turns an AC re-mint into a change). Reviewed and accepted by the Stage-1 spec review on that condition. The brief's "(keystone's AC digest)" wording should be corrected at the next revision.
- **Manifest runtime ids** (parametrize instances) as a binding source are deferred. Bindings are static at function granularity, which over-approximates (every instance shares its function's FRs) and so cannot miss; it can only raise the hold rate. A changed parametrize case is still a modification.
- **Tests under `fixtures/` directories** are excluded from test roots (they hold data repos, not tests); a Python helper under `tests/fixtures/` that tests import is not attributed. The repo-root `conftest.py` (outside any `tests/` directory) is not attributed either.
- **Static attribution of a helper module** reaches direct importers only (a test-side helper that itself imports the changed one is not followed).
- **Context-run scope.** Four tiers only, all run from the repo root (CI runs plugin tiers from the plugin directory). A PR whose code sits in an unmeasured tier is out of the 20-PR selection; within the selection, functions no measured tier runs are counted "unattributed". N was derived from two tiers.
- **Shared machine.** The 20 context runs and the per-root timing ran concurrently with other work; timings are upper bounds.
- **Squash merges.** All 100 PRs were squash commits; the merge base is the first parent. A rebase-merge would need the PR's own base.
- **Historical declarations** come from `shipwright_events.jsonl` `work_completed` events matched by run id; PRs without an iterate event (docs, bots, manual) have "no declaration".
- **Heuristic labels** in section 8 are provisional by rule; only your re-labelling of the sample makes them real.
- **Environment.** `shared/tests` showed 17 failures when run (with contexts) on this machine; they are outside BL0's files and were not investigated here.

## 13. What the library is, for the units that follow

`shared/scripts/tools/verifiers/_baseline_touch_{git,spec,binding,static,coverage,core}.py` derive the touched set from a merge-base diff (three-dot; no merge base is an error), fail closed on any unreadable or unparsable file, and expose `touched_set` and `evaluate_hold(touched, scope, n)`. `_baseline_touch_replay_{stats,code}.py` and `replay_baseline_lock.py` are the measurement tooling. `_baseline_touch_static.py` and `_baseline_touch_coverage.py` are replay-grade prototypes that BL2 owns and may replace. The 50 L1 tests are analogues of the brief's S1-S8 and S17 cases, not the L2 seeded regressions the owning units must still deliver. If you stop BP at stop 1, the replay modules can be removed without touching the core derivation.
