# Baseline protection (BP): REPLAY report for operator stop 1

> **Note 2026-10-29:** the campaign this report belongs to was stopped after BL0b; see the stop note in `2026-10-27-baseline-protection-BRIEF.md`. The stop-1 approval line was never given. The figures remain valid as a measurement.

**Unit:** BL0 · **Run:** `iterate-2026-10-28-bl0-touch-library-and-replay` · **Brief:** `2026-10-27-baseline-protection-BRIEF.md` (section 5, item 1)
**Data:** `2026-10-27-baseline-protection-REPLAY.json` (next to this file; each number below is recomputed from it or from a command listed under *Reproduce*, except the counterfactual rates 39 of 100 and 36 of 96 in section 2 and the added-file count in section 12, which I derived by hand from `records[].sources` and from `git diff --diff-filter=A` on the merge commits). Captured against `origin/main` at the time of the run; the 100 PRs are #937 down to #831 (merged 2026-10-02 .. 2026-10-28; the data holds exactly this window).
**Reproduce:** `uv run shared/scripts/tools/replay_baseline_lock.py --repo . --limit 100 --out replay.json` (derived legs, git only; add `--code-sample 20 --probes 5 --workdir <dir outside the repo>` for the context runs; `--from-json replay.json` re-summarises without git). Measurements and labels: `uv run shared/scripts/tools/measure_baseline.py {roots|fanout|verifier|label|summary|rederive} --repo . [--workdir <dir>]` (module docstring has the details); each writes under `measure.*` in the JSON (`label` also `records[].hits`): `measure.hit_labels`, `measure.fanout_changed`, `measure.fanout_executed`, `measure.verifier`, `measure.roots`. `rederive` re-runs the git leg (T-spec, T-test, static) over the stored PRs with the current library; `summary` recomputes the summary block from the records.

This report measures; nothing gates. Nothing in `ci.yml`, `verify_local.py`, `deliver_pr.py` or any gate changed. The campaign halts here.

## 0. Headline in plain language

- If BP held every PR whose diff touches an existing requirement, with no approved scope, **40 of the last 100 PRs (40 %) would have waited for you** (counted from T-spec, T-test and static attribution, the git leg that ran over all 100 PRs; T-code ran on a 20-PR sample only, see section 2). Half of the iterates (25 of 50) and 14 of 30 campaign-unit PRs. Docs, dependency-bot, manual and release PRs were never held (0 of 18).
- In **27 of those 40** the author had themselves recorded at least one of the same requirements as affected (`affected_frs`); in **23 of the 40** the author recorded every requirement the diff touched. Those 23 are friction, not surprises: they stop only because a single iterate has an empty approved scope. **Read 23 as an upper bound on friction:** `affected_frs` is written at finalization (F5b), after the diff exists, so an author can name what the diff already shows. **13 PRs (13 %) touched a requirement the author never named**, and 4 more (#922, #899, #873, #860) declared some of what they touched but not all of it.
- If the approved scope were exactly what the author declared, **17 PRs (17 %)** would still be held (the 13 plus those 4), not 40. That is the size of "unplanned change" on these data, **a lower bound** for the reason above; the other 23 are the cost of requiring an approval. (The earlier draft of this report said 12 %; that figure came from the stale git leg (section 12). `summary.held_with_scope_eq_declared` is the metric.)
- **The git leg misses declared changes.** 45 PRs declare at least one requirement, and for **18 of them (40 %) the derived set is empty**. Sixteen of the 18 are behaviour changes by their titles (for example `fix(changelog)`, `feat(design)`, `feat(test)`, `feat(run)`, `feat(compliance)`, `fix(iterate)`); only #872 and #902 are prose or skill text (section 2). So the git leg alone is blind to a large share of what authors themselves call a requirement change; T-code is the source meant to see those, and the sample could not show it (section 5).
- **Production code is where the blind spot is.** Of the functions any test executes, only **48 %** (1875 of 3928, in the files of `shared` that the 17 test roots which produced coverage measure) are executed by a test that is bound to a requirement. The seeded-change probes (5 of 5, 0 of 4 and 0 of 5 noticed) have outcomes fixed by their construction, the prose one included; they show that the pipeline is consistent, not that T-code finds real changes, and only blind probes would be evidence (section 6).
- **Per-hit labels:** of 144 hits (git leg 135, T-code 9), 0 are `wrong` by my mechanical check, 44 are friction (provisional) (author declared the FR), 100 need your intent to separate harmful from benign (section 8). That 0 is a **consistency check, not the brief's semantic "wrong"**: the check re-derives the evidence untruncated and tests the same kind of predicate the sources use, so a near-zero result is nearly guaranteed. Your re-label of the sample in section 9 can falsify the brief's bar of 3 `wrong` per 100 PRs but cannot confirm it for static or test, where the sample is 5 of 93 and 5 of 37 hits (section 8).
- The `fr_impact` map is almost never recorded: **0 of the 100 PRs** carry one. 45 carry `affected_frs`. The declaration is too sparse to stand in for the derived set, which is the brief's premise.

## 1. Stop-1 checklist (brief section 5, item 1)

| Input | Where | Status |
|---|---|---|
| Base rate: PRs with a non-empty touched set | section 2 | 40 / 100 |
| Base rate: PRs carrying `fr_impact` | section 2 | 0 / 100 (45 / 100 carry `affected_frs`) |
| Hold rate per PR class | section 3 | measured |
| T-code fan-out and proposed N | section 5 | measured; N = 5 proposed |
| Mutation-probe results | section 6 | 14 conclusive probes (two of three kinds circular) |
| Labels per hit | section 8 | 144 hits labelled (0 wrong, a consistency check); 100 need your intent |
| Random sample for the operator | section 9 | 20 hits |
| BP's own `scope_frs` proposal | section 10 | proposed |
| Verifier wall-clock (5 iterates), context-run cost | section 7 | measured |
| Decisions for you | section 11 | listed |

## 2. Base rates

| Measure | Value |
|---|---|
| PRs replayed / errors | 100 / 0 |
| Touched set non-empty (T-spec + T-test + static test-dir attribution) | 40 (40 %) |
| Held if the approved scope were exactly the declared FRs (`held_with_scope_eq_declared`) | 17 (17 %) |
| Touched set non-empty and entirely declared (`touched_all_declared_prs`) | 23 |
| Carries `fr_impact` | 0 |
| Carries `fr_impact` or `affected_frs` | 45 |
| Derived and declared agree (share at least one FR) | 27 |
| Derived only (author named no matching FR) | 13 |
| Declared only (author named an FR, the diff touches none) | 18 |
| PRs with a "moved" test (listed, not touched) | 4 |
| PRs whose evidence was incomplete (would be held fail-closed) | 0 |
| FRs per touching PR | 32 PRs touch 1 FR; 4 touch 2-3; **4 touch 18 or 19** (see below) |

**Scope of every held count in sections 0 to 3 and 10:** the git leg, that is T-spec + T-test + static attribution, over all 100 PRs. T-code ran on 20 PRs only (`code.prs`). In that sample the git leg holds 11 of 20; T-code would also hold #915 (a layer-promotion PR the git leg passes: it changed `evaluate_fr`, which FR-01.10 tests execute), so 12 of 20. Across the whole sample that is T-code's only addition: all eight of #899's T-code FRs (FR-01.06, .09, .10, .11, .13, .14, .20, .21) are already in its git-leg source set through static attribution, and #915 / FR-01.10 is the one FR in the sample that only T-code reports. The 100-PR figures therefore understate the full derived set by whatever T-code would add outside the sample.

The four wide PRs (#860, #873, #897, #899) all change a `conftest.py` under `shared/tests` or `shared/scripts/tests`, which is attributed scope-wide to every test below it. They are the "shared helper" case the brief expects; section 5 proposes treating them as broad. #860, #873 and #899 each also have a real FR-bound test edit, so they stay held either way; #897 is held only through its conftest. **N is not applied to static attribution in the library** (it is a proposal for the shadow period). The N-applied counterfactual is **39 of 100** (only #897 leaves the held set); taking the four PRs out of the population altogether would give 36 of 96 (38 %). Both against 40 of 100 (40 %).

**"Declared only" (18 of the 45 PRs that declare a requirement, 40 %): the author names a requirement and the git leg derives none.** The first draft called these documentation, planning and tool PRs; the titles say otherwise. Sixteen are behaviour changes by their titles: #937 `fix(changelog)`, #936 `feat(design)`, #934 `fix(security,run,grade)`, #933 `fix(quality,audit)`, #925 `feat(test)`, #924 `feat(design)`, #923 `fix(run)`, #920 `feat(run)`, #913 `fix(run)`, #892 `fix(iterate)`, #891 `fix(triage)`, #883 `fix(phases)`, #866 `feat(compliance)`, #842 and #837 `feat(finalization)`, #839 `fix(compliance)`. Only two are prose or skill text: #872 (`refactor(iterate)`, moves SKILL.md paragraphs) and #902 (`feat(profiles)`, skill prose). Whether each behaviour change is a requirement change is for the author's declaration to say; what is measured is that no bound test or spec text changed in the git leg. Six of the 18 were in the 20-PR T-code sample (#937, #934, #933, #924, #923, #920) and **T-code saw none of them**: five (#934, #933, #924, #923, #920) changed production files the four tiers do not measure at all ("no coverage at base"), and in #937 the changed file is measured but its changed function (`main`) and module-level code run only under tests with no FR binding. The other 12 were outside the sample, so whether T-code would see them is not known.

**`affected_frs` is written at F5b, after the diff exists.** So "declared" is not an independent plan: 23 (the entirely declared holds) is an upper bound on friction and 17 % a lower bound on unplanned change.

## 3. Hold rate per PR class (empty approved scope; git leg, see section 2)

| Class | PRs | Held | Rate |
|---|---|---|---|
| iterate | 50 | 25 | 50 % |
| campaign-unit | 30 | 14 | 47 % |
| layer-promotion | 2 | 1 | 50 % |
| dependency-bot | 8 | 0 | 0 % |
| docs | 5 | 0 | 0 % |
| manual | 4 | 0 | 0 % |
| release | 1 | 0 | 0 % |
| revert | 0 | - | - |

Class is derived from the branch and title (`replay_baseline_lock.py` via `pr_class`). **Release and layer-promotion** (decision S10 of the brief): the one layer-promotion PR that was held (#886) edited an FR-01.10 test; the other (#915) touched nothing in the git leg, but T-code attributes its changed function `evaluate_fr` to FR-01.10 (section 5), so **with T-code layer promotion is 2 of 2 held**. The one release PR (#875) touched nothing. No revert occurred in the window, so that class is unmeasured. Campaign units have no `scope_frs` yet (the field does not exist in any historical brief), so their rate here equals the empty-scope rate; with a correct `scope_frs` it would fall toward the 17 % of section 0.

## 4. Which source notices what

| Source | Hits | Of which the author also declared | Not declared |
|---|---|---|---|
| T-spec (normative text changed) | 5 | 5 | 0 |
| T-test (bound test modified / deleted) | 37 | 22 | 15 |
| Static test-dir attribution (fixture, conftest, helper) | 93 | 16 | 77 (70 from the four scope-wide conftest PRs, 7 otherwise) |
| T-code (context run, 20 PRs, see 5) | 2 PRs (9 hits) | 1 | 8 |

T-spec is quiet and precise. T-test carries most of the signal outside the conftest cases. Static attribution is the noisy source: apart from the four scope-wide conftest PRs it produced 20 hits, 7 of them undeclared.

## 5. T-code: fan-out, proposed N, coverage limits

**Method.** For the 20 most recent PRs that changed Python production code inside a measured target, a detached worktree of the merge base ran four test tiers with `--cov-context=test` (`shared/scripts/tools/tests`, `shared/scripts/tests`, `plugins/shipwright-iterate/tests`, `plugins/shipwright-changelog/tests`; coverage targets `shared` and those two plugins' `scripts`). The PR's own diff was attributed through those contexts (enclosing function for added or deleted lines).

**Result.** Only **2 of 20** PRs had a changed line executed by an FR-bound test (#915: 1 function, 1 FR; #899: 9 functions, 8 FRs). That is limited by the sample, not a signal rate for T-code: the four tiers measure only part of the code, and 80 changed production files in these 20 PRs were not measured at all (below), so the 2 of 20 is a floor. Of the changed production functions the four tiers could say anything about, 10 ran under an FR-bound test and 15 ran under none (function-level notes, `measure.fanout_changed`); a further 9 notes are code added or changed outside any function (module level), counted separately because there is no function to ask about. Separately, at file level, 80 changed production files had "no coverage at base" (not measured by these four tiers, or never executed; a different unit from the function counts). The first draft counted 22 functions and 65 changed test files here; the stored notes came from an earlier attribution pass, in which blank and comment lines and module-level code were counted as functions "executed by no FR-bound test" and test-directory files were noted (they are static attribution's). They were recomputed from the stored context databases with the current code (no test was run again; the FR attributions did not change). So the brief's disclosed limit is quantified as follows: where the tiers measure a changed function at all, 10 of 25 reach an FR, and a further 80 changed production files are not measured by these tiers.

**Fan-out, as the brief defines it** (FRs reached per *changed* function, `measure.fanout_changed`): across the 20 PRs, 10 changed functions were executed by an FR-bound test: 9 reach 1 FR and 1 reaches 8 (`isolate_user_profiles_dir` in #899, shared test plumbing). Another 15 changed functions were executed by no FR-bound test. That sample is too small to set N on its own, so I also measured a **variant, a deviation from the brief's wording** (`measure.fanout_executed`): FRs reached per *executed* function in the files of `shared` that the 17 test roots with coverage output measure at HEAD (695 files, 4054 functions). 3928 are executed by some test; 2053 of those by no bound test (fan-out 0); 1875 (48 %) reach at least one FR: 1457 reach 1, 228 reach 2, 101 reach 3, 63 reach 4, then a gap (1 reaches 5), then 12 reach 6, 1 reaches 7, 1 reaches 8, 4 reach 10, 6 reach 14 and 1 reaches 20. Median of the non-zero ones is 1; p90 and p95 (nearest rank) are 3; max 20. The wide ones are shared infrastructure (`isolate_user_profiles_dir` (20), `carry_destination_mode` (14), `replace_retrying` (14), `durable_atomic_write` (14)).

**Proposal for N: 5.** A function reaching more than 5 FRs is "listed, not held". That is 25 of 1875 FR-bound executed functions (1.3 %) in the population; among the changed functions that reach any FR, 1 of 10 (`isolate_user_profiles_dir`, 8 FRs) is above N, a share that rests on one function. The widest ones listed above (the eight widest are in `measure.fanout_executed.widest`) are shared plumbing, and N = 5 sits in the gap of the histogram (one function at exactly 5); N = 2 would list 190 (10.1 %), N = 8 would still list 11. This is conditional, and the figure is biased low in two ways that I did not correct: (1) the coverage target was `shared` only (plugin `scripts` are unmeasured until BL2), so a plugin function's fan-out is not in it; (2) every root ran with `-m 'not slow and not cross_plugin'`, so slow and cross-plugin tests, which also bind to FRs, contributed no contexts, and plugin roots ran from the repo root instead of their own directory (CI's way), which can change what imports and collects. Both can only remove FR-bound executions, so real fan-out is at least what is shown, and the gap at N = 5 (one function at exactly 5) may be produced by the measurement rather than by the code. The shadow period is the check before N is frozen. The same threshold should apply to scope-wide static attribution (the four wide conftest PRs); it does not today (section 2 gives the counterfactual).

## 6. Mutation probes (a consistency check of the pipeline, not a measure of T-code)

Fifteen probes over five of the 20 PRs, three per PR, run in the PR's merge-base worktree over the real context databases (re-run with the final probe code; one probe whose seeded edit did not parse is not counted).

| Probe | Conclusive | Noticed | By which source |
|---|---|---|---|
| Line executed by an FR-bound test | 5 | **5** | T-code only |
| Line executed only by tests with no FR binding | 4 | 0 | none |
| A `SKILL.md` line (prose) | 5 | 0 | none |

**What this does and does not show.** All three probe kinds have outcomes fixed by construction. The two production probes are circular: each seeded line is chosen from the same context database T-code then reads, so "executed by a bound test, noticed" and "executed only by unbound tests, not noticed" follow by construction. They confirm that seeding, diffing, attribution and the hold rule are self-consistent; they do not show that T-code finds real changes, and they could not have come out the other way (so the brief's stop condition "the probes show nothing is noticed" could not have fired from them). Blind probes, with lines chosen independently of the database, were not run; BL2 should add them. The `SKILL.md` probe is fixed too: no source reads prose, so a seeded sentence cannot be noticed, which brief section 0 states and this only restates. None of the three is evidence about T-code; only blind probes would be. If you decide at stop 1 that prose matters, BP does not cover it and the plugin conversions are what shrink it.

## 7. Costs measured

All numbers are in `measure.*` of the JSON and recomputed by `measure_baseline.py` (`roots`, `verifier`); the machine was shared with other work, so every time is an upper bound.

- **Verifier wall-clock** (`measure.verifier`): `verify_iterate_finalization.py` run on the five most recent merged iterate commits (#937, #936, #935, #934, #933), each in a detached worktree at its merge commit: 2.6, 2.0, 2.0, 2.0, 2.0 seconds (median 2.0, max 2.6). Negligible next to CI. The exit code was 1 in this scratch environment (two checks error there); every check ran or was skipped by its own rule, so the time is the cost of a complete pass, not a verdict.
- **Context run vs plain run, two roots** (`measure.roots`): `shared/scripts/tools/tests` 189.4 s with `--cov-context=test` vs 170.7 s without (+11 %); database 1.15 MB vs 0.09 MB (12x). `plugins/shipwright-changelog/tests`: 9.1 s vs 8.4 s (+8 %); 0.07 MB vs 0.05 MB. Contexts cost about a tenth in time on the larger root and about an order of magnitude in artifact size.
- **Per-root context-run time, every root once** (`measure.roots`, one pytest process per root run one after another, `-m "not slow and not cross_plugin"`, coverage target `shared`): `shared/tests` 25.7 min; `integration-tests` 4.8 min; `plugins/shipwright-compliance/tests` 3.2 min; `shared/scripts/tools/tests` 3.2 min; the remaining 14 roots take at most 64 s each. About 43 minutes one after another; CI runs them in parallel jobs. Of the 18 roots, **17 produced a coverage database**; `plugins/shipwright-grade/tests` collected with 10 errors (exit 2, no database) when run from the repo root, so it contributes to the cost figure (1.9 s) but not to the fan-out. `shared/tests` had 17 failing tests in this environment (unrelated to BP).
- **Four-tier context run per PR** (the subset used for T-code, `code.prs[].tiers`): median 206 s.

## 8. Labels (per hit)

A **hit** is one (PR, requirement, source) the replay reported: 144 hits in all. For each hit the labeller re-derives the **untruncated** evidence at the merge commit (the stored evidence strings are cut at 5 items, the labeller does not read them) and re-decides from the raw PR content (`verifiers/_baseline_label_hits.py`, `_baseline_label_all.py`, `measure_baseline.py label`; result in `records[].hits[].label`, and for T-code in `code.prs[].hits`), whether the source attributed it correctly:

- **T-test:** the cited test is bound to that FR by the text of its `covers` marks (function, class or module) and really changed or was deleted. A test renamed in the same commit is paired with its base body (docstring and decorators ignored) and counts through both bindings.
- **T-spec:** the normative text of the FR (row description and section prose; not Basis/Layers, `(inferred)`, `[ACnn]`) really differs.
- **Static:** the cited conftest/helper really changed (an AST difference, or the file appeared or vanished) and an FR-bound test really reaches it (a scope-wide change such as an autouse fixture, a hook, a module-level statement; or a changed name the bound test uses, followed through helper-to-helper references in the changed module and in the consumer). A purely added import does not count.
- **T-code:** the changed function (base lines touched by the diff, an inserted line mapped to its enclosing base function) is executed, per the context database, by a test bound to the FR (binding read from the test's text at the base).

A hit that fails that check is **`wrong`**. A correct hit is **`correct-benign`** where the author declared the FR (friction, provisional) and **`correct-undetermined`** where the author did not: whether it is `correct-harmful` or `correct-benign` needs your intent, not a diff.

| Source | Hits | correct-benign (declared) | correct-undetermined (not declared) | wrong | wrong per 100 PRs (limit 3) |
|---|---|---|---|---|---|
| T-spec | 5 | 5 | 0 | 0 | 0.0 |
| T-test | 37 | 22 | 15 | 0 | 0.0 |
| Static attribution | 93 | 16 | 77 | 0 | 0.0 |
| T-code (20 PRs) | 9 | 1 | 8 | 0 | 0.0 (normalised by the 20-PR code sample) |

**This 0 is a consistency check, not the brief's semantic "wrong".** The labeller asks whether the evidence supports the hit under rules that mirror how the source reasons (the cited test is bound and changed; the named helper is used by a bound test; the function is executed by a bound test). It cannot ask whether the FR is the right thing to be warned about. Two things follow. (1) A result of 0 is close to guaranteed whenever the source and the labeller agree on what a binding is, so it should not be read as "the sources are right 100 %". (2) The brief's bar of 3 `wrong` per 100 PRs is about the semantic question and **can only be judged from your re-label of the sample in section 9**. For the record, the labeller itself was wrong twice during this unit (both on #840, both fixed and each given a test): it first read an evidence form it did not parse, and it did not pair a test renamed together with a docstring edit and a re-tag; each was caught by re-reading the diff, not by the check.

Further limits. (3) The static count is dominated by four conftest PRs (#860, #873, #897, #899: 18 or 19 FRs each), where a scope-wide conftest change really does reach every bound test below it; whether that is useful or noise is a `correct-benign` question for you. (4) The sample in section 9 is stratified, 5 hits per source, so your re-label can falsify the bar (one clear `wrong` among the 5 would already be a finding) but cannot confirm it for static (5 of 93 hits) or test (5 of 37). (5) The reasons stored with static labels are of the form "e.g. <file>: N bound test(s)": they cite the first supporting item only, not all of them. (6) The T-code sample is two PRs: six of #899's eight FRs (FR-01.09, .10, .11, .14, .20, .21) come from one shared isolation helper alone (`isolate_user_profiles_dir`), which is the fan-out case N exists for.

## 9. Random sample for you to re-label

20 hits, seeded (`random.Random(20261028)`, up to five per source, `measure.hit_labels.sample`). **This re-label is what decides the brief's `wrong`-per-100 bar** (section 8). For each: is the listed FR really affected? Label `correct-harmful` (a behaviour change you would have wanted to see), `correct-benign` (right FR, harmless), or `wrong`. My label is in the fourth column; overwrite it.

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
| #922 | FR-01.01 | static | correct-undetermined | e.g. integration-tests/_brief_harness.py: changed ['build_fixture_1'] used by a test bound to FR-01.01 in inte |
| #873 | FR-01.11 | static | correct-undetermined | e.g. shared/tests/conftest.py: module-level/scope-wide change reaches 1 test(s) bound to FR-01.11 (first suppo |
| #897 | FR-01.04 | static | correct-undetermined | e.g. plugins/shipwright-design/tests/conftest.py: module-level/scope-wide change reaches 7 test(s) bound to FR |
| #860 | FR-01.06 | static | correct-undetermined | e.g. shared/tests/conftest.py: module-level/scope-wide change reaches 23 test(s) bound to FR-01.06 (first supp |
| #897 | FR-01.02 | static | correct-undetermined | e.g. plugins/shipwright-project/tests/conftest.py: module-level/scope-wide change reaches 2 test(s) bound to F |
| #921 | FR-01.12 | test | correct-undetermined | shared/tests/test_chat_first_json_profile.py::test_dev_server_is_the_declared_block_not_the_default_service: b |
| #935 | FR-01.09 | test | correct-benign | plugins/shipwright-changelog/tests/test_skill_event_ships_in_release_pr.py::test_event_is_recorded_and_committ |
| #904 | FR-01.01 | test | correct-benign | plugins/shipwright-run/tests/test_phase_validators_late.py::test_deploy_phase_returns_the_canon_verdict: bound |
| #855 | FR-01.17 | test | correct-undetermined | shared/tests/test_ci_yml_execution_evidence_step_shape.py::test_artifact_step_uses_upload_artifact_action: bou |
| #862 | FR-01.10 | test | correct-benign | plugins/shipwright-compliance/tests/test_git_commit_command.py::test_string_running_programs_share_the_depth_b |

Full evidence for any PR: `2026-10-27-baseline-protection-REPLAY.json`, `records[].evidence` and `records[].hits`. The earlier PR-level sample (15 held PRs) stays in the JSON under `sample`.

## 10. BP's own `scope_frs` (proposal)

BP changes the delivery, finalization and CI-gate machinery. Proposed, for approval at stop 1:

- **FR-01.11** (/shipwright-iterate): finalization checks, the verifier, delivery, campaign step 3g/3f-bis. The FR the replay shows touched most (17 of 40 holds).
- **FR-01.10** (/shipwright-compliance): the F11 checks and required-checks drift tooling BL6 touches.
- **FR-01.17** (independent re-check on the code host): `baseline.yml` and the required checks.
- **FR-01.01** (/shipwright-run): `campaign-mode.md` is the orchestrator contract BL1/BL3/BL4 edit; the replay attributes FR-01.01 in 11 of 40 holds (through a bound-test edit in 6, through static attribution in 7; four of the 11 are the wide conftest PRs, and two PRs count in both).

Not proposed: FR-01.09 (changelog; only BL6's guide/glossary text, which are not FR behaviour) and FR-01.06 (the test phase is not changed). Until you approve, BP's own PRs report as out of scope in shadow, as the brief expects.

## 11. Decisions for you (plain language)

1. **N (broad threshold):** how many requirements one shared function may reach before a change to it is only *listed* rather than *held*. Proposal 5 (section 5), conditional on the two measurement biases named there. Smaller means more holds on shared plumbing; larger means shared plumbing is waved through.
2. **Rule per PR class:** release, layer promotion, revert, manual. These are policy choices, not conclusions the data support: release is n = 1, layer promotion n = 2, revert n = 0. The classes also mix: docs-titled PRs on campaign branches (#898, #916, #858) fall into campaign-unit, so the docs rate (0 of 5) and the campaign-unit rate (14 of 30) are not clean per-kind rates. Measured on the git leg: 0 of 18 docs/bot/manual/release PRs were held, and 1 of 2 layer-promotion PRs (it changed a bound test); with T-code the second one (#915) is held too, so 2 of 2 (it changed a function that FR-01.10 tests run). Proposal: apply the same rule to layer promotion, exempt release PRs that contain no code or test change, and decide revert when one appears.
3. **BP's own `scope_frs`:** section 10.
4. **The P3.8 supersession** (an edited test body under an unchanged AC becomes a hold for out-of-scope FRs only): unchanged by this unit; the replay shows T-test is the largest source of hits that are not conftest scope-wide (37 hits, 15 of them undeclared), so the supersession is what makes BP bite.
5. **Whether BP proceeds.** Facts for the decision: with an exactly declared scope BP would hold 17 % of PRs as real unplanned change; today, with no scope, it holds 40 %, of which 23 PRs (23 %) are approval friction. Production code is covered only where a bound test runs it (48 % of executed functions). **How much T-code adds is not established by this replay; in the sample it added one FR on one PR (#915 / FR-01.10).** Only 2 of the 20 sampled PRs saw any T-code hit, but the four tiers could not measure 80 of the changed production files in those PRs, so 2 of 20 is limited by the sample, not a signal rate. The fan-out and probe measurements do not settle it either (section 5 biases, section 6 circularity). **The git leg misses 18 of the 45 PRs that declare a requirement (40 %), 16 of them behaviour changes by title, and T-code saw none of the 6 that were in its sample**; so "T-spec + T-test only" is not a safe starting point on this evidence, and neither does the replay show that T-code fixes it. Prose, shell and config are not covered at all. If you judge 40 % friction too high before `scope_frs` exists, the choice is between living with it in shadow and measuring T-code on a broader sample first (the 20-PR sample could not measure 80 production files; a broader sample measures more existing code but cannot see changes that only add code, section 12); this replay does not support dropping T-code, and does not support paying for BL2 (a large unit) on this evidence alone. Read the friction as an upper bound and the 17 % as a lower bound (`affected_frs` is written after the diff exists).
6. **Thresholds for stop 2:** the hold-rate and friction-rate numbers above are the baseline to set them against (hold 40 % on the git leg; 23 of the 40 friction, an upper bound; 17 % if the scope equals what the author declared, a lower bound).

## 12. Deviations from the brief and disclosed limits

- **T-spec reader.** The brief names keystone's AC digest. Keystone's digest covers acceptance criteria only and keys them by AC id, while the brief's own ignore list says AC-id tokens are not a change and the catalog row's statement is. A purpose-built reader (row + section prose + criteria text; order- and marker-insensitive) implements that list. Keystone's digest was tried as a union and rejected (it turns an AC re-mint into a change). Reviewed and accepted by the Stage-1 spec review on that condition. The brief's "(keystone's AC digest)" wording should be corrected at the next revision.
- **Manifest runtime ids** (parametrize instances) as a binding source are deferred. Bindings are static at function granularity, which over-approximates (every instance shares its function's FRs) and so cannot miss; it can only raise the hold rate. A changed parametrize case is still a modification.
- **Tests under `fixtures/` directories** are excluded from test roots (they hold data repos, not tests); a Python helper under `tests/fixtures/` that tests import is not attributed. The repo-root `conftest.py` (outside any `tests/` directory) is not attributed either.
- **Static attribution of a helper module** reaches direct importers only (a test-side helper that itself imports the changed one is not followed).
- **Context-run scope.** Four tiers only, all run from the repo root (CI runs plugin tiers from the plugin directory). A PR whose code sits in an unmeasured tier is out of the 20-PR selection; within the selection, functions no measured tier runs are counted "unattributed". N was derived from the 17 of 18 roots that produced a coverage database (`plugins/shipwright-grade/tests` gave none), all run with `-m 'not slow and not cross_plugin'`, plugin roots from the repo root, coverage target `shared` (plugin `scripts` unmeasured).
- **Shared machine.** The 20 context runs and the per-root timing ran concurrently with other work; timings are upper bounds.
- **Squash merges.** All 100 PRs were squash commits; the merge base is the first parent. A rebase-merge would need the PR's own base.
- **Historical declarations** come from `shipwright_events.jsonl` `work_completed` events matched by run id; Of the 100 PRs, 45 declare FRs (`affected_frs`), 40 have an event that declares none, and 15 have no event (8 dependency-bot, 4 manual, 2 docs, 1 release); none carries `fr_impact`.
- **Labels are mechanical.** `wrong` is a consistency check on untruncated evidence re-derived from the raw PR content (section 8), not the brief's semantic `wrong`; `correct-benign` vs `correct-undetermined` follows from whether the author declared the FR, because `correct-harmful` needs intent. Only your re-labelling of the sample makes them final.
- **Git leg re-derived.** The first draft's stored git leg predated the final static-attribution fixes (a modified conftest attributed scope-wide made #897 and #899 wide). `measure_baseline.py rederive` re-ran it with the committed library and every figure above is from that run; the T-code entries were re-attributed from their stored context databases with the current attribution code (blank and comment lines skipped, module-level code noted separately; no test was re-run, the FR attributions are unchanged), and the probes were not re-run.
- **PR window.** The first draft of this report said #937..#840; the data holds #937..#831 (the 107 numbers in that range include 7 that are not merged PRs). Corrected here and in the sample tables.
- **Reproducing sections 5, 7 and 8.** `measure_baseline.py` recomputes the fan-out (both definitions), the verifier wall-clock, the per-root context-run cost and the labels, and writes them into the JSON; the report cites those keys. Raw coverage databases are not committed (about 14 MB for the 17 roots; `roots` regenerates them, `replay_baseline_lock.py --code-sample` regenerates the 20 T-code databases). The T-code hit labels need those databases, so they are stored in the JSON (`code.prs[].hits`) rather than recomputed from git alone. Timings differ per run; the counts do not.
- **Verifier exit code.** The five verifier runs time a complete pass but exit 1 in this scratch environment (two checks error there), so the wall-clock is a cost, not a verdict.
- **New code is invisible to T-code by design.** `code_touched` skips added files without a note, and "new code in a function that does not exist at base" notes are in none of the `fanout_changed` counts (10 / 15 / 9 / 80). Nothing ran that code at base, so no test can attribute it. In the 20-PR sample, `git diff --diff-filter=A` on the merge commits shows 42 of the 134 changed production files were added, 10 of 28 in the six declared-only PRs in the sample (#937 0 of 1, #934 2 of 6, #933 1 of 3, #924 2 of 7, #923 1 of 3, #920 4 of 8). A broader sample measures more existing code but cannot see changes that only add code.
- **Known limit, latent.** Removed module-level lines executed by a bound test land in `targets['<module>']` in `code_touched`, but `_changed_functions` in the labeller never returns `<module>`, so such a T-code hit would be labelled `wrong`. No committed number is affected (no T-code hit in the data is module-level). No code change here.
- **Environment.** `shared/tests` showed 17 failures when run (with contexts) on this machine; they are outside BL0's files and were not investigated here.

## 13. What the library is, for the units that follow

`shared/scripts/tools/verifiers/_baseline_touch_{git,spec,binding,static,coverage,core}.py` derive the touched set from a merge-base diff (three-dot; no merge base is an error), fail closed on any unreadable or unparsable file, and expose `touched_set` and `evaluate_hold(touched, scope, n)`. `_baseline_touch_replay_{stats,code}.py`, `_baseline_label_hits.py`, `_baseline_label_all.py`, `_baseline_measure.py`, `_baseline_proc.py` (scrubbed subprocess environment and the workdir guard), `replay_baseline_lock.py` and `measure_baseline.py` are the measurement tooling. `_baseline_touch_static.py` and `_baseline_touch_coverage.py` are replay-grade prototypes that BL2 owns and may replace. The 97 L1 tests (`pytest --collect-only` per file with `coverage` installed: `test_baseline_touch.py` 31, `test_baseline_label.py` 23, `test_baseline_replay.py` 13, `test_baseline_touch_coverage.py` 6, `test_baseline_replay_code.py` 24; the coverage file skips itself without `coverage`, so 91 collect without it) are analogues of the brief's S1-S8 and S17 cases, not the L2 seeded regressions the owning units must still deliver. If you stop BP at stop 1, the replay modules can be removed without touching the core derivation.
