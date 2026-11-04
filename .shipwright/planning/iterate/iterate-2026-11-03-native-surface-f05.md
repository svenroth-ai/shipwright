# Iterate: F0.5 accepts a native (Expo / React Native) UI surface

Run: `iterate-2026-11-03-native-surface-f05` | type: change | complexity: medium | GitHub #989 | status: draft

## Goal

A native-only mobile app (Expo / React Native, no web build) can never pass the F0.5 surface check on a medium+ iterate that
changes app source: every `.tsx` counts as UI, a UI diff demands `--surface web`, and `web` demands a staged Playwright report
that a browser-less app cannot produce. Add a fourth surface value `native` whose evidence is what a native app really has:
Jest results (Jest `--json` staged as the vitest-shaped report, or JUnit written with a `file` attribute), tied to the native
package that holds the touched UI. Every existing evidence rule stays: this run, this revision, passing results, `tests_run`
backed by them.

## Acceptance criteria

1. `surface_verification.py --surface native` is accepted and `tests_run` is parsed from Jest's summary (`Tests: N passed`).
2. `check_surface_verification` accepts `surface=native` for a diff whose every touched UI path lies in a native package
   (nearest `package.json` at the verified commit depends on `react-native` or `expo`, has no web framework dependency, and
   `react-dom` only counts as one when `react-native-web` is absent - the stock `create-expo-app` template carries both; the same
   holds at the merge-base unless the package is new), when staged evidence has passing JS/TS test results under EVERY touched
   native package; `tests_run` above the passing count (Jest cases counted per assertion) still fails.
3. `native` is refused when any touched UI path is NOT in a native package (a web file in the same diff) or is a web-only file
   (`*.web.tsx`, `.html`, `.vue`, `.svelte`, `.astro`), naming that path;
   `cli` and `none` stay refused for UI diffs; `web` is unchanged.
4. `native` evidence counts only results from JS/TS test files located under a touched native package: a Python JUnit report,
   or Jest results from another package, never satisfy it (absent / stale / failing / short-count paths fail as for `web`).
5. The refusal text for a UI diff names `native` as the option for a native package; the docs (F0.5 reference, hooks-and-pipeline)
   state the staging recipe, including the `file` attribute requirement for JUnit.

## Spec Impact

MODIFY of FR-01.11/AC07 behaviour (F0.5 surface evidence). Tests carry `FR-01.11/AC07`.

## Out of Scope (follow-up, stated in the PR)

Narrowing the `src/` frontend root rule in `lib/detect_frontend_changes.py`: a backend package's `src/**/*.ts` still counts as
`ui`. It is shared with Browser Verify and every other project, so it gets its own run with both-direction tests. A diff that
mixes backend `src/*.ts` with native UI is refused for `native` under AC3 until then.

## Design Notes

- New module `tools/verifiers/_surface_native.py`: `native_packages(project_root, commit, ui_paths)` returns the package
  directories (or the offending paths); reads `package.json` through `git show <commit>:<dir>/package.json` so the declaration
  is the verified revision's, not the working tree's.
- `_surface_evidence.py`: two vocabularies stay separate: staged report KINDS (`junit`, `vitest`, `playwright`) vs the result
  RUNNER label the reader writes (`pytest` for every JUnit, `vitest`, `playwright`). `native` = kinds {junit, vitest}, labels
  {pytest, vitest}, plus the package-root and JS/TS-extension filter. The orchestrator is grandfathered over the size cap:
  its edit is neutral in line count.
- `tests_run` for native is read from Jest's `Tests:` line only (the `Snapshots:` / `Test Suites:` lines are other units).
- No config switch and no agent-chosen flag: native-ness is derived from the diff's own packages, so `native` cannot be used to
  dodge the browser for a web app.

## Affected Boundaries

Consumer of `package.json` (JSON read at a commit), of the staged provenance sidecar and of JUnit / Jest-JSON reports.

## Confidence Calibration

- **Boundaries touched:** package.json at commit, staged reports, runner labels.
- **Empirical probes run:** see F5 (real git repos, real staging through `evidence_drop`).
- **Test Completeness Ledger:** see F5.
- **Confidence-pattern check:** the real `jest-junit` output shape was not run here; the `file`-attribute requirement is documented
  and tested through the reader, which is the same path real reports take.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Approach right; as planned it would refuse stock Expo apps, miscount Jest results and let a diff relabel a web package as native.
- **Findings:** completeness/high - stock Expo template carries react-dom + react-native-web: FIXED (react-dom disqualifies only without react-native-web; deliberate and documented). security/medium - package.json edited by the same diff: FIXED (also native at merge-base). security/medium - web-only files and other web frameworks: FIXED (web-only file types refused, wider dependency deny set, all four dependency fields, malformed = not native). completeness/medium - tests_run max over Jest's three summary lines: FIXED (`Tests:` line only). completeness/medium - duplicate titles across describes collapse to one id: FIXED (per-assertion case count from the staged Jest JSON). completeness/medium - kinds vs labels: FIXED (split + distinctness test; docs state the `--junit <base>=` rule). security/low - one package's tests satisfy another: FIXED (each touched package needs a passing result). completeness/low - stale surface lists: FIXED. completeness/low - nearest-package.json edge cases: FIXED (fail closed, per-directory cache). architecture/low - runner forms under shell=False: DISCLOSED in the recipe.
- **Known limitations:** Jest JSON ids line up only on the machine that ran the tests (absolute paths), like Playwright's rootDir; hoisted dependencies (nearest manifest only); an Expo app that really ships a web build through react-native-web is judged native and its browser run is skipped by design.
- **Status:** 9 fixed, 1 disclosed

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** low
- **Summary:** Build option A (a derived `native` surface); B breaks the no-browser-dodge constraint, D is too broad, C leaves an always-red gate.
- **Findings:** security/low - package.json is judged at the same commit the diff may edit: FIXED (native must also hold at the merge-base). completeness/low - Expo universal apps (react-dom) stay refused: DISCLOSED in docs and refusal text. completeness/low - jest-junit needs `addFileAttribute`, Jest JSON paths are absolute: FIXED (paths normalised to repo-relative, `..` refused; recipe documents the option). complexity-cost/low - Python JUnit exclusion rests on the extension filter: FIXED (a test fails if the filter is removed; framework lists in named constants).
- **Known limitations:** Expo universal apps; backend `src/*.ts` in the same diff (follow-up run).
- **Status:** 3 fixed, 1 disclosed

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-03-native-surface-f05/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (option A)
- **Findings:** glm: name the follow-up as the relief for mixed backend+app diffs, put a hint in the refusal text: accepted-and-fixed. Plan review (same two models, revise): Jest JSON vs vitest shape unvalidated: accepted-and-fixed (test with a real Jest `--json` shaped report through the reader; JUnit-with-`file` stays the second path); hoisted deps (nearest manifest only): disclosed + "no package.json above path" test; `..` / absolute path containment: accepted-and-fixed (normalise, path-aware under-test, test with traversal and sibling package with similar name); mixed monorepo diff test: accepted; filtered counting before comparing `tests_run`: accepted-and-fixed (count is taken from the filtered set; mixed-report test); web KIND/label regression: accepted (existing surface tests plus explicit JUnit-cannot-replace-Playwright test).
- **Reconciliation:** the mini-plan rejected a project-level switch because a web project could set it and skip the browser run; the reviewers, who never saw that reason, picked the same option A independently.
