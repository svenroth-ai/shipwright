# Baseline protection (BP): BL0b broader measurement and decision report

**Unit:** BL0b · **Run:** `iterate-2026-10-28-bl0b-broader-measurement` · **Data:** `2026-10-27-baseline-protection-BL0B.json` (next to this file; `phaseA.*` are the measurements, `eval` is the rule evaluation) · **Builds on:** `2026-10-27-baseline-protection-REPLAY.md/.json`
**Reproduce:** `uv run --with coverage shared/scripts/tools/bl0b_head_run.py --tree <worktree at fd2aa8a60> --out <dir outside it>` (item 2), then `bl0b_analyze.py {paths|headmap|ac|packs|summary|probes|eval}`, and `bl0b_probes.py` (item 6). Every figure below is a key in the JSON.

This report measures; nothing gates. No change to `ci.yml`, `verify_local.py`, `deliver_pr.py`, hooks or workflows. The campaign halts here for the operator (stop 1).

## 0. Headline in plain language

- **Recommendation: SHADOW-ONLY.** Do not make a gating decision yet. BP does catch real unplanned changes, but on these data it would hold far too many PRs and name too many wrong requirements, and the extra machinery (T-code) did not beat a much simpler path-based guess.
- **The benefit is real but small.** Two independent blind labelers confirmed three PRs (#869, #887, #921) that changed behaviour of a requirement the author never named, and the git leg alone (spec text and test edits) already finds all three.
- **The cost is too high.** If the approved scope were exactly what authors declared, BP with T-code would still hold **43 of 100 PRs (about 11 a week)**, against a limit of 20. The git leg alone holds 17 (4 a week) but finds only 6 of 27 confirmed requirement changes.
- **T-code does not earn its keep.** Git leg plus T-code finds 78 % of the confirmed pairs; git leg plus the path-ownership guess finds 93 %. The rule needed T-code to be 20 points better; it is 15 points worse.
- **Precision fails everywhere.** 35 of the sources' hits on the 35 labeled PRs were judged wrong (limit: 3 per 100 PRs); 19 of them come from one wide-conftest PR (#897) and 16 without it, still far over the limit.

## 1. Setup fixed (item 1)

- **Roots run as CI runs them**, serially, one pytest process per root, no `-n auto`: plugin roots from the plugin directory (`--cov=scripts --cov=<tree>/shared`), shared roots and `integration-tests` from the repo root with `-m "not slow and not cross_plugin"`, all with `--cov-context=test`, in a clean detached worktree at `fd2aa8a60`. 18 of 18 roots produced a database, 32 minutes in total, **0 failures** (`phaseA.setup.roots`).
- **`plugins/shipwright-grade/tests`** now produces a database (393 passed): the 10 collection errors in the REPLAY run came from running it from the repo root, not from its own directory.
- **Every root measures `shared`**; a plugin's own `scripts` are measured in that plugin's root only (not in the shared or integration roots). Test ids and file paths are root-prefixed (0 unprefixed ids).
- **The 17 `shared/tests` failures could not be reproduced.** A clean worktree gives 0 failures at both the REPLAY-time commit `79878eaef` (13397 passed = 17 + 13380) and current main (13465 passed), with the same context mode and scrubbed environment. So they were not commit-dependent and not caused by the context run; they came from the state of the checkout the REPLAY run used. Their names were not stored, so whether they were FR-bound is unknown.

## 2. One HEAD context run mapped to history (item 2)

- 407 changed production functions in the 100 PRs: **305 (75 %) reach an FR**, 30 run only under unbound tests, 5 under no test, 4 are in unmeasured files, and **63 (15.5 %, in 18 PRs) are missing at HEAD** (renamed, deleted, moved). The merge-base fallback was **not run** for those 63: the 20 merge-base databases are gone and regenerating them was cut for time. A further 181 module-level changes are listed, not attributed.
- **Error rate against the 20 stored merge-base results:** 9 of 9 merge-base (PR, FR) pairs reappear at HEAD (0 % missed) and 9 of 10 functions are attributed again. HEAD adds 41 pairs the old four-tier run could not see, so the 82 % "disagreement" is extra coverage, not mismatch. (Compared against the stored results, not regenerated databases.)
- HEAD T-code reaches an FR on **57 of 100 PRs** (the old sample: 2 of 20).

## 3. Path-ownership baseline, new code, AC level (items 3 to 5)

Against the **author's declaration** (45 PRs, not independent) and against the **blind labels** (27 confirmed pairs on 22 PRs):

| Source | Recall vs declared | Precision vs declared | Recall vs blind labels (95 % interval) | Hits judged wrong on the 35 labeled PRs |
|---|---|---|---|---|
| git leg | 0.52 | 0.34 | 6 of 27 (0.22; 0.11-0.41) | 29 |
| path ownership | 0.89 | 0.40 | 24 of 27 (0.89; 0.72-0.96) | 25 |
| T-code at HEAD (N = 5) | 0.87 | 0.58 | 17 of 27 (0.63; 0.44-0.79) | 7 |
| git + T-code (BP) | 0.90 | 0.38 | 21 of 27 (0.78; 0.59-0.89) | 35 |
| git + path | 0.96 | 0.31 | 25 of 27 (0.93; 0.77-0.98) | 45 |

- **New code (item 4).** Of the 16 declared-only behaviour PRs: 12 add new code that a modified base function reaches (class a, counted through the caller), 1 is additive only (class b, #936), 3 add no new Python (#891, #892, #937). Across all 100 PRs: 49 a, 6 b, 45 none. Class a is name-matched (a modified function mentions the new name), so it may overcount on common names. HEAD T-code finds a declared FR in 15 of the 16 (not #936); the path baseline in 15 (not #891).
- **AC level (item 5).** 67 PRs touch something: 821 explicit-AC bindings, 99 FR-wide ones, median 2 ACs per touching PR (max 178). Authors declare FRs, never ACs, so with scope equal to the declared FRs the AC-level hold equals the FR-level hold (43) by construction. The AC level changes how much one approval covers, not who is held. T-spec is FR-level only.

## 4. Blind probes (item 6)

50 production functions drawn uniformly from an AST walk of `shared/**` and `plugins/*/scripts/**` (4635 eligible, no coverage involved), one semantic mutation each, judged by "does a covers-bound test that passed before now fail".

- **16 of 50 caught.** T-code recall on those: **14 of 16 (87.5 %)**; the two misses: a function only unbound tests execute, and one run only in a subprocess.
- **34 not caught:** 18 no covers-bearing test names the module, 8 a bound test executes it but the mutation survives, 5 referenced by a bound test but not executed in-process (subprocess), 3 executed only by unbound tests.
- The "no candidate" bucket is a limit of the textual test selection: for 6 of its 18, the HEAD contexts do link an FR-bound test; running exactly those caught the mutation in 2 of 6. T-code flags 28 of the 50 functions; only 14 of the 28 are detected by a failing bound test.

## 5. Pre-registered rules (unchanged from the spec)

Ground truth = the two blind labelers. A pair counts only if both said "behaviour changed" and both name the FR. Labels: 35 PRs, 29 both yes, 5 both no (#848, #855, #900, #908, #911), 1 unclear (#918), 0 yes/no disagreements. 22 PRs give **27 confirmed (PR, FR) pairs**. Seven yes-PRs (839, 859, 866, 886, 897, 919, 923) were left without an FR by labeler A because no FR describes the change (the hand-over also listed #935, but labeler A did name FR-01.09 there, and it is a confirmed pair); they are neither hit nor miss and are listed below.

| Rule | Limit | Measured | Result |
|---|---|---|---|
| R-benefit | at least 3 confirmed changes, FR not declared by the author, found by BP sources | 3 PRs (#869 FR-01.11; #887 FR-01.13 and FR-01.17; #921 FR-01.06), 4 pairs; git leg alone finds the same 3 | **PASS** (exactly at the limit) |
| R-recall | at least 70 % of confirmed pairs found | 21 of 27 = 78 % (denominator 27 pairs, 22 PRs; 95 % interval 59 % to 89 %: wide, roughly plus/minus 15-20 points) | **PASS** (the interval reaches below 70) |
| R-T-code-value | T-code adds at least 20 points over path baseline plus git leg | git + T-code 78 % minus git + path 93 % = **-15 points** | **FAIL** |
| R-precision | at most 3 wrong hits per 100 PRs | 35 wrong hits on the 35 labeled PRs (19 from #897, 16 without it); the other 65 PRs are unlabeled, so this can only be higher; 8 disputed hits not counted | **FAIL** |
| R-cost | at most 20 % held when scope equals the declared FRs | FR level 43 of 100; AC level 43 of 100; about 10.75 holds per week (git leg alone: 17 of 100, 4.25 per week) | **FAIL** |

**Outside every FR (not counted):** #839, #859, #866, #886, #897 (neither labeler names an FR), #919, #923. These are behaviour changes labeler A found no requirement for; for #839, #859, #866, #886, #919, #923 labeler B names one FR. Unclear: #918. Wrong-hit examples: #911 (a no-op fix; T-code and path name FR-01.01), #897 (a wide conftest change names 19 FRs the labelers do not).

## 6. Recommendation

**SHADOW-ONLY: no BP gating decision yet.** Derivation: the full plan (GO) needs all five lines; three fail. The pre-registered consequence of the failed R-T-code-value line is to replace BL2 by the path baseline. That does not rescue gating: the path baseline itself fails R-cost (49 of 100 held at declared scope) and R-precision (25 wrong hits), so the verdict stays SHADOW-ONLY, and any later BP work should use the path baseline or the git leg instead of T-code. GO-REDUCED does not rescue it either: the path baseline recalls more (89 %) but holds 49 of 100 PRs at declared scope and has 25 wrong hits, and the AC level holds exactly as many PRs as the FR level. What the data do support: the benefit exists and is found by the cheap git leg; T-code and the path guess add recall at the price of many extra holds.

**What the operator must still decide:**
1. Whether 43 % (git + T-code) or 17 % (git leg only) of PRs waiting for approval is acceptable, given that 17 % finds only about a fifth of the confirmed changes.
2. Whether a wide-change rule (N, and treating a scope-wide conftest as "listed, not held") is tried in shadow first; one PR (#897) accounts for 19 of the 35 wrong hits.
3. Whether to follow the pre-registered consequence and replace BL2 by the path baseline, or drop T-code in favour of the git leg. This report's suggestion, for the operator to decide: if BP continues, BL1 plus a git-leg-only shadow is the cheap next step.
4. The earlier open items (N, rule per PR class, BP's own `scope_frs`, P3.8) are unchanged from REPLAY section 11.

## 7. Operator spot-check sample (six PRs)

1. **#869** `feat(iterate): campaign runner reviews use the resolved tier`: both labelers: behaviour change in FR-01.11, the author declared nothing. Git leg and T-code both name FR-01.11 (the git leg also names FR-01.10, which the labelers do not), so this is a clean "benefit" case.
2. **#887** `refactor(adopt): stop scaffolding the Claude-Code-Review workflows`: despite the "refactor" label, adopt no longer scaffolds the workflows (FR-01.13, FR-01.17). The git leg finds both; T-code names FR-01.06 instead, which is wrong.
3. **#921** `fix(test): Windows-safe npx spawn, Browser Verify URL, chat-first host`: both name FR-01.06 and the author declared none. Git and T-code find it, but the git leg also names FR-01.12 and FR-01.13 which neither labeler affirms.
4. **#897** `feat(profiles): stack-profile resolver, schema and CLI`: a wide conftest change makes the git leg name 19 FRs that neither labeler affirms, and both labelers found no FR that covers the change. It is the biggest single source of wrong hits.
5. **#911** `fix(run): bind state before the retry loop`: both labelers say no behaviour change. T-code and the path baseline still name FR-01.01, a wrong hit.
6. **#923** `fix(run): a stack profile named in the wizard brief is taken over`: the author declared FR-01.01 and labeler B agrees, but labeler A found no matching FR. The git leg finds nothing; T-code names FR-01.01 plus FR-01.02 and FR-01.04.

## 8. Limits and deviations

- **Small, enriched label sample:** 35 PRs, chosen to contain the git leg's misses and extras plus 6 controls, so recall is measured where sources disagree and the precision count is not a rate over the window. 27 pairs give wide intervals.
- **Packs leaked a little:** PR titles naming an FR were redacted to `FR-xx`, but the test diffs still show `covers("FR-..")` marks on tests the PR added. Labeler A left 7 yes-PRs without an FR (handled above); AC ids came in two formats and only FR ids were compared.
- **17 shared/tests failures not reproduced** (section 1). **63 changed functions unresolved at HEAD**, no merge-base fallback run (section 2). Cross-check used stored merge-base results, not regenerated databases.
- **HEAD proxy:** bindings and executing tests are read at a recent commit, not at each PR's base. Plugin scripts are measured only in the plugin's own root.
- **Path baseline** uses an import graph by module stem (errs in its favour) and ignores non-Python files under `shared/`.
- **Probes:** ground truth depends on a textual choice of candidate tests (capped at 8 files per root); 18 of 50 had none, so the 32 % "caught" is a floor.
- **"Wrong"** here is semantic: neither labeler names the hit's FR on a PR both judged. Labelers name few FRs per PR, which raises the wrong count; the REPLAY report's mechanical 0 was a consistency check, not this.
- **Declared FRs** (`affected_frs`) are written after the diff exists and are only a reference.
