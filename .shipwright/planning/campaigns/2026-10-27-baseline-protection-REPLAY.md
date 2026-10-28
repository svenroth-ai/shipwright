# Baseline protection (BP): REPLAY report for operator stop 1

**Unit:** BL0 · **Run:** `iterate-2026-10-28-bl0-touch-library-and-replay` · **Brief:** `2026-10-27-baseline-protection-BRIEF.md` (section 5, item 1)
**Data:** `2026-10-27-baseline-protection-REPLAY.json` (next to this file; each number below is recomputed from it or from a command listed under *Reproduce*, none is typed in by hand). Captured against `origin/main` at the time of the run; the 100 PRs are #937 down to #831 (merged 2026-10-02 .. 2026-10-28; the data holds exactly this window).
**Reproduce:** `uv run shared/scripts/tools/replay_baseline_lock.py --repo . --limit 100 --out replay.json` (derived legs, git only; add `--code-sample 20 --probes 5 --workdir <dir outside the repo>` for the context runs; `--from-json replay.json` re-summarises without git). Measurements and labels: `uv run shared/scripts/tools/measure_baseline.py {label|fanout|verifier|roots} --repo . [--workdir <dir>]` (module docstring has the details); each writes under `measure.*` in the JSON (`label` also `records[].hits`): `measure.hit_labels`, `measure.fanout_changed`, `measure.fanout_executed`, `measure.verifier`, `measure.roots`.

This report measures; nothing gates. Nothing in `ci.yml`, `verify_local.py`, `deliver_pr.py` or any gate changed. The campaign halts here.

## 0. Headline in plain language

- If BP held every PR whose diff touches an existing requirement, with no approved scope, **39 of the last 100 PRs (39 %) would have waited for you.** Half of the iterates (25 of 50) and 13 of 30 campaign-unit PRs. Docs, dependency-bot, manual and release PRs were never held (0 of 18).
- In **27 of those 39** the author had themselves recorded the same requirement as affected (`affected_frs`). Those holds are friction, not surprises: they stop only because a single iterate has an empty approved scope. **12 PRs (12 %) touched a requirement the author never named**; those are the interesting ones, and the ones you are asked to re-label (section 9).
- If the approved scope were exactly what the author declared, the hold rate would be **12 %**, not 39 %. That is the real size of "unplanned change"; the rest is the cost of requiring an approval.
- **Production code is where the blind spot is.** Of the functions any test executes, only **48 %** (1875 of 3928, in the files of `shared` that all 17 test roots measure) are executed by a test that is bound to a requirement. A seeded change to such a line is noticed (5 of 5 probes, by T-code only); a change to a line executed only by unbound tests is not (0 of 4); a change in a `SKILL.md` is not (0 of 5).
- **Per-hit labels:** of 106 hits, 1 is `wrong` by my mechanical check (static, #840), 40 are friction (author declared the FR), 65 need your intent to separate harmful from benign (section 8). Every source is inside the brief's bar of 3 `wrong` per 100 PRs on these labels; your re-label of the sample (section 9) is what makes that real.
- The `fr_impact` map is almost never recorded: **0 of the 100 PRs** carry one. 45 carry `affected_frs`. The declaration is too sparse to stand in for the derived set, which is the brief's premise.

## 1. Stop-1 checklist (brief section 5, item 1)

| Input | Where | Status |
|---|---|---|
| Base rate: PRs with a non-empty touched set | section 2 | 39 / 100 |
| Base rate: PRs carrying `fr_impact` | section 2 | 0 / 100 (45 / 100 carry `affected_frs`) |
| Hold rate per PR class | section 3 | measured |
| T-code fan-out and proposed N | section 5 | measured; N = 5 proposed |
| Mutation-probe results | section 6 | 14 conclusive probes |
| Labels per hit | section 8 | 106 hits labelled (1 wrong); 65 need your intent |
| Random sample for the operator | section 9 | 20 hits |
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

The two 18-FR PRs (#860, #873) both change `shared/tests/conftest.py`, which is attributed scope-wide to every test below it. They are the "shared helper" case the brief expects; section 5 proposes treating them as broad. They stay held either way: each also has a real FR-bound test edit, so they add 2 to the 39 held. Taken out of the population the rate would be 37 of 98 (38 %) instead of 39 of 100 (39 %).

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

**Result.** Only **2 of 20** PRs had a changed line executed by an FR-bound test (#915: 1 function, 1 FR; #899: 9 functions, 8 FRs). Of the changed production functions the four tiers could say anything about, 10 ran under an FR-bound test and 22 ran under none (function-level notes, `measure.fanout_changed`). Separately, at file level, 80 changed production files and 65 changed test files had "no coverage at base" (not measured by these four tiers, or never executed; 145 file-level notes in all, a different unit from the function counts). So the brief's disclosed limit is quantified as follows: where the tiers measure a changed function at all, 10 of 32 reach an FR, and a further 80 changed production files are not measured by these tiers.

**Fan-out, as the brief defines it** (FRs reached per *changed* function, `measure.fanout_changed`): across the 20 PRs, 10 changed functions were executed by an FR-bound test: 9 reach 1 FR and 1 reaches 8 (`isolate_user_profiles_dir` in #899, shared test plumbing). Another 22 changed functions were executed by no FR-bound test. That sample is too small to set N on its own, so I also measured a **variant, a deviation from the brief's wording** (`measure.fanout_executed`): FRs reached per *executed* function in the files of `shared` that all 17 test roots measure at HEAD (695 files, 4055 functions). 3928 are executed by some test; 2053 of those by no bound test (fan-out 0); 1875 (48 %) reach at least one FR: 1457 reach 1, 228 reach 2, 101 reach 3, 63 reach 4, then a gap (1 reaches 5), then 12 reach 6, 1 reaches 7, 1 reaches 8, 4 reach 10, 6 reach 14 and 1 reaches 20. Median of the non-zero ones is 1; p95 is 3; max 20. The wide ones are shared infrastructure (`isolate_user_profiles_dir` (20), `carry_destination_mode` (14), `replace_retrying` (14), `durable_atomic_write` (14)).

**Proposal for N: 5.** A function reaching more than 5 FRs is "listed, not held". That is 25 of 1875 FR-bound executed functions (1.3 %), the widest ones listed above (the eight widest are in `measure.fanout_executed.widest`) are shared plumbing, and N = 5 sits in the gap of the histogram (one function at exactly 5); N = 2 would list 190 (10.1 %), N = 8 would still list 11. This is conditional: the coverage target was `shared` only (plugin `scripts` are unmeasured until BL2), so a plugin function's fan-out is not in this figure. The shadow period is the check before N is frozen. The same threshold should apply to scope-wide static attribution (the two 18-FR conftest PRs).

## 6. Mutation probes (which source notices a seeded production change)

Fifteen probes over five of the 20 PRs, three per PR, run in the PR's merge-base worktree over the real context databases (re-run with the final probe code; one probe whose seeded edit did not parse is not counted).

| Probe | Conclusive | Noticed | By which source |
|---|---|---|---|
| Line executed by an FR-bound test | 5 | **5** | T-code only |
| Line executed only by tests with no FR binding | 4 | 0 | none |
| A `SKILL.md` line (prose) | 5 | 0 | none |

So: T-code is the only source that sees a production change, and only where a bound test runs the line. Prose and shell are outside every source, as brief section 0 states; here it is measured. If you decide at stop 1 that prose matters, BP does not cover it and the plugin conversions are what shrink it.

## 7. Costs measured

All numbers are in `measure.*` of the JSON and recomputed by `measure_baseline.py` (`roots`, `verifier`); the machine was shared with other work, so every time is an upper bound.

- **Verifier wall-clock** (`measure.verifier`): `verify_iterate_finalization.py` run on the five most recent merged iterate commits (#937, #936, #935, #934, #933), each in a detached worktree at its merge commit: 2.6, 2.0, 2.0, 2.0, 2.0 seconds (median 2.0, max 2.6). Negligible next to CI. The exit code was 1 in this scratch environment (two checks error there); every check ran or was skipped by its own rule, so the time is the cost of a complete pass, not a verdict.
- **Context run vs plain run, two roots** (`measure.roots`): `shared/scripts/tools/tests` 189.4 s with `--cov-context=test` vs 170.7 s without (+11 %); database 1.15 MB vs 0.09 MB (12x). `plugins/shipwright-changelog/tests`: 9.1 s vs 8.4 s (+8 %); 0.07 MB vs 0.05 MB. Contexts cost about a tenth in time on the larger root and about an order of magnitude in artifact size.
- **Per-root context-run time, every root once** (`measure.roots`, one pytest process per root run one after another, `-m "not slow and not cross_plugin"`, coverage target `shared`): `shared/tests` 25.7 min; `integration-tests` 4.8 min; `plugins/shipwright-compliance/tests` 3.2 min; `shared/scripts/tools/tests` 3.2 min; the remaining 14 roots take at most 64 s each. About 43 minutes one after another; CI runs them in parallel jobs. Two caveats from the runs: `shared/tests` had 17 failing tests in this environment (unrelated to BP), and `plugins/shipwright-grade/tests` collected with 10 errors when run from the repo root.
- **Four-tier context run per PR** (the subset used for T-code, `code.prs[].tiers`): median 206 s.

## 8. Labels (per hit)

A **hit** is one (PR, requirement, source) the replay reported: 106 hits in all. For each hit I re-decided from the raw PR content, without the touched-set derivation (`verifiers/_baseline_label_hits.py`, `measure_baseline.py label`; result in `records[].hits[].label`, and for T-code in `code.prs[].hits`), whether the source attributed it correctly:

- **T-test:** the cited test is bound to that FR by the text of its `covers` marks (function, class or module) and really changed or was deleted.
- **T-spec:** the normative text of the FR (row description and section prose; not Basis/Layers, `(inferred)`, `[ACnn]`) really differs.
- **Static:** the cited conftest/helper really changed (an AST difference, or the file appeared or vanished) and an FR-bound test really reaches it (a scope-wide change such as an autouse fixture, a hook, a module-level statement; or a changed name the bound test uses, followed through helper-to-helper references). A purely added import does not count.
- **T-code:** the changed function (base lines touched by the diff) is executed, per the context database, by a test bound to the FR (binding read from the test's text at the base).

A hit that fails that check is **`wrong`**. A correct hit is **`correct-benign`** where the author declared the FR (friction, provisional) and **`correct-undetermined`** where the author did not: whether it is `correct-harmful` or `correct-benign` needs your intent, not a diff.

| Source | Hits | correct-benign (declared) | correct-undetermined (not declared) | wrong | wrong per 100 PRs (limit 3) |
|---|---|---|---|---|---|
| T-spec | 5 | 5 | 0 | 0 | 0.0 |
| T-test | 36 | 21 | 15 | 0 | 0.0 |
| Static attribution | 56 | 13 | 42 | 1 | 1.0 |
| T-code (20 PRs) | 9 | 1 | 8 | 0 | 0 of 9 hits in 20 PRs |

The only hit I label wrong:
- #840 FR-01.11 (static): the changed name `RUNNER_REASON_CODES` in `shared/tests/_review_cli_harness.py` is used by none of the three FR-01.11-bound tests that import the harness.

Reading: on these labels every source is within the brief's bar of 3 `wrong` per 100 PRs (T-spec 0, T-test 0, static 1, T-code 0 of 9 hits). Three honest limits. (1) My check is mechanical and finds a hit **wrong** only when the evidence does not support it; a hit that is technically reached but semantically irrelevant is `correct-undetermined` until you say otherwise, and the 65 undetermined hits are where your re-labelling matters. (2) The static count is dominated by two conftest PRs (#873, #860: 18 FRs each), where a scope-wide conftest change really does reach every bound test below it; whether that is useful or noise is a `correct-benign` question for you. (3) The T-code sample is two PRs: six of #899's eight FRs (FR-01.09, .10, .11, .14, .20, .21) come from one shared isolation helper alone (`isolate_user_profiles_dir`), which is the fan-out case N exists for.

## 9. Random sample for you to re-label

20 hits, seeded (`random.Random(20261028)`, up to five per source, `measure.hit_labels.sample`). For each: is the listed FR really affected? Label `correct-harmful` (a behaviour change you would have wanted to see), `correct-benign` (right FR, harmless), or `wrong`. My label is in the fourth column; overwrite it.

| PR | FR | Source | My label | Evidence |
|---|---|---|---|---|
| #899 | FR-01.21 | code | correct-undetermined | shared/scripts/profile_test_isolation.py::isolate_user_profiles_dir changed; executed by 4 test(s) bound to FR |
| #915 | FR-01.10 | code | correct-undetermined | shared/scripts/lib/layer_promotion.py::evaluate_fr changed; executed by 4 test(s) bound to FR-01.10 (e.g. shar |
| #899 | FR-01.11 | code | correct-undetermined | shared/scripts/profile_test_isolation.py::isolate_user_profiles_dir changed; executed by 4 test(s) bound to FR |
| #899 | FR-01.13 | code | correct-undetermined | shared/scripts/profile_test_isolation.py::isolate_user_profiles_dir changed; executed by 6 test(s) bound to FR |
| #899 | FR-01.06 | code | correct-benign | shared/scripts/profile_model.py::user_dir changed; executed by 2 test(s) bound to FR-01.06 (e.g. shared/script |
| #871 | FR-01.11 | spec | correct-benign | .shipwright/planning/01-adopted/spec.md: 8 line(s) added/changed, 0 removed in FR-01.11 text |
| #845 | FR-01.11 | spec | correct-benign | .shipwright/planning/01-adopted/spec.md: 19 line(s) added/changed, 9 removed in FR-01.11 text |
| #861 | FR-01.11 | spec | correct-benign | .shipwright/planning/01-adopted/spec.md: 7 line(s) added/changed, 0 removed in FR-01.11 text |
| #841 | FR-01.11 | spec | correct-benign | .shipwright/planning/01-adopted/spec.md: 7 line(s) added/changed, 0 removed in FR-01.11 text |
| #863 | FR-01.11 | spec | correct-benign | .shipwright/planning/01-adopted/spec.md: 3 line(s) added/changed, 2 removed in FR-01.11 text |
| #922 | FR-01.01 | static | correct-undetermined | integration-tests/_brief_harness.py: changed ['build_fixture_1'] used by a test bound to FR-01.01 in integrati |
| #873 | FR-01.19 | static | correct-undetermined | shared/tests/conftest.py: module-level/scope-wide change reaches 5 test(s) bound to FR-01.19 |
| #873 | FR-01.01 | static | correct-undetermined | shared/tests/conftest.py: module-level/scope-wide change reaches 10 test(s) bound to FR-01.01 |
| #860 | FR-01.03 | static | correct-undetermined | shared/tests/conftest.py: module-level/scope-wide change reaches 1 test(s) bound to FR-01.03 |
| #860 | FR-01.20 | static | correct-undetermined | shared/tests/conftest.py: module-level/scope-wide change reaches 4 test(s) bound to FR-01.20 |
| #904 | FR-01.01 | test | correct-benign | plugins/shipwright-run/tests/test_phase_validators_late.py::test_deploy_phase_returns_the_canon_verdict: bound |
| #921 | FR-01.12 | test | correct-undetermined | shared/tests/test_chat_first_json_profile.py::test_dev_server_is_the_declared_block_not_the_default_service: b |
| #935 | FR-01.09 | test | correct-benign | plugins/shipwright-changelog/tests/test_skill_event_ships_in_release_pr.py::test_event_is_recorded_and_committ |
| #855 | FR-01.17 | test | correct-undetermined | shared/tests/test_ci_yml_execution_evidence_step_shape.py::test_artifact_step_uses_upload_artifact_action: bou |
| #862 | FR-01.10 | test | correct-benign | plugins/shipwright-compliance/tests/test_git_commit_command.py::test_string_running_programs_share_the_depth_b |

Full evidence for any PR: `2026-10-27-baseline-protection-REPLAY.json`, `records[].evidence` and `records[].hits`. The earlier PR-level sample (15 held PRs) stays in the JSON under `sample`.

## 10. BP's own `scope_frs` (proposal)

BP changes the delivery, finalization and CI-gate machinery. Proposed, for approval at stop 1:

- **FR-01.11** (/shipwright-iterate): finalization checks, the verifier, delivery, campaign step 3g/3f-bis. The FR the replay shows touched most (15 of 39 holds).
- **FR-01.10** (/shipwright-compliance): the F11 checks and required-checks drift tooling BL6 touches.
- **FR-01.17** (independent re-check on the code host): `baseline.yml` and the required checks.
- **FR-01.01** (/shipwright-run): `campaign-mode.md` is the orchestrator contract BL1/BL3/BL4 edit; the replay attributes FR-01.01 in 9 of 39 holds (run-plugin tests in 5, integration tests in 4, shared tests in 2; two PRs count in two groups).

Not proposed: FR-01.09 (changelog; only BL6's guide/glossary text, which are not FR behaviour) and FR-01.06 (the test phase is not changed). Until you approve, BP's own PRs report as out of scope in shadow, as the brief expects.

## 11. Decisions for you (plain language)

1. **N (broad threshold):** how many requirements one shared function may reach before a change to it is only *listed* rather than *held*. Proposal 5 (section 5). Smaller means more holds on shared plumbing; larger means shared plumbing is waved through.
2. **Rule per PR class:** release, layer promotion, revert, manual. Measured: 0 of 18 docs/bot/manual/release PRs were held; the layer-promotion PR that was held changed a bound test. Proposal: apply the same rule to layer promotion, exempt release PRs that contain no code or test change, and decide revert when one appears.
3. **BP's own `scope_frs`:** section 10.
4. **The P3.8 supersession** (an edited test body under an unchanged AC becomes a hold for out-of-scope FRs only): unchanged by this unit; the replay shows T-test is the largest source of hits that are not conftest scope-wide (36 hits, 15 of them undeclared), so the supersession is what makes BP bite.
5. **Whether BP proceeds.** Facts for the decision: the guarantee covers 12 % of PRs as real unplanned change plus 27 % as approval friction; production code is covered only where a bound test runs it (48 % of executed functions, 2 of 20 sampled PRs saw any T-code hit); prose, shell and config are not covered at all. If you judge 39 % friction too high before `scope_frs` exists, the choice is to start with T-spec + T-test only (the shadow window will tell) rather than T-code, which costs BL2 (a large unit) for a signal that fired in 2 of 20 PRs.
6. **Thresholds for stop 2:** the hold-rate and friction-rate numbers above are the baseline to set them against (hold 39 %, of which friction 27 %).

## 12. Deviations from the brief and disclosed limits

- **T-spec reader.** The brief names keystone's AC digest. Keystone's digest covers acceptance criteria only and keys them by AC id, while the brief's own ignore list says AC-id tokens are not a change and the catalog row's statement is. A purpose-built reader (row + section prose + criteria text; order- and marker-insensitive) implements that list. Keystone's digest was tried as a union and rejected (it turns an AC re-mint into a change). Reviewed and accepted by the Stage-1 spec review on that condition. The brief's "(keystone's AC digest)" wording should be corrected at the next revision.
- **Manifest runtime ids** (parametrize instances) as a binding source are deferred. Bindings are static at function granularity, which over-approximates (every instance shares its function's FRs) and so cannot miss; it can only raise the hold rate. A changed parametrize case is still a modification.
- **Tests under `fixtures/` directories** are excluded from test roots (they hold data repos, not tests); a Python helper under `tests/fixtures/` that tests import is not attributed. The repo-root `conftest.py` (outside any `tests/` directory) is not attributed either.
- **Static attribution of a helper module** reaches direct importers only (a test-side helper that itself imports the changed one is not followed).
- **Context-run scope.** Four tiers only, all run from the repo root (CI runs plugin tiers from the plugin directory). A PR whose code sits in an unmeasured tier is out of the 20-PR selection; within the selection, functions no measured tier runs are counted "unattributed". N was derived from all 17 roots with coverage target `shared` (plugin `scripts` unmeasured).
- **Shared machine.** The 20 context runs and the per-root timing ran concurrently with other work; timings are upper bounds.
- **Squash merges.** All 100 PRs were squash commits; the merge base is the first parent. A rebase-merge would need the PR's own base.
- **Historical declarations** come from `shipwright_events.jsonl` `work_completed` events matched by run id; Of the 100 PRs, 45 declare FRs (`affected_frs`), 40 have an event that declares none, and 15 have no event (8 dependency-bot, 4 manual, 2 docs, 1 release); none carries `fr_impact`.
- **Labels are mechanical.** `wrong` is decided by an independent re-read of the raw PR content (section 8); `correct-benign` vs `correct-undetermined` follows from whether the author declared the FR, because `correct-harmful` needs intent. Only your re-labelling of the sample makes them final.
- **PR window.** The first draft of this report said #937..#840; the data holds #937..#831 (the 107 numbers in that range include 7 that are not merged PRs). Corrected here and in the sample tables.
- **Reproducing sections 5, 7 and 8.** `measure_baseline.py` recomputes the fan-out (both definitions), the verifier wall-clock, the per-root context-run cost and the labels, and writes them into the JSON; the report cites those keys. Raw coverage databases are not committed (about 13 MB for the 17 roots; `roots` regenerates them, `replay_baseline_lock.py --code-sample` regenerates the 20 T-code databases). The T-code hit labels need those databases, so they are stored in the JSON (`code.prs[].hits`) rather than recomputed from git alone. Timings differ per run; the counts do not.
- **Verifier exit code.** The five verifier runs time a complete pass but exit 1 in this scratch environment (two checks error there), so the wall-clock is a cost, not a verdict.
- **Environment.** `shared/tests` showed 17 failures when run (with contexts) on this machine; they are outside BL0's files and were not investigated here.

## 13. What the library is, for the units that follow

`shared/scripts/tools/verifiers/_baseline_touch_{git,spec,binding,static,coverage,core}.py` derive the touched set from a merge-base diff (three-dot; no merge base is an error), fail closed on any unreadable or unparsable file, and expose `touched_set` and `evaluate_hold(touched, scope, n)`. `_baseline_touch_replay_{stats,code}.py`, `_baseline_label_hits.py`, `_baseline_measure.py`, `replay_baseline_lock.py` and `measure_baseline.py` are the measurement tooling. `_baseline_touch_static.py` and `_baseline_touch_coverage.py` are replay-grade prototypes that BL2 owns and may replace. The 66 L1 tests are analogues of the brief's S1-S8 and S17 cases, not the L2 seeded regressions the owning units must still deliver. If you stop BP at stop 1, the replay modules can be removed without touching the core derivation.
