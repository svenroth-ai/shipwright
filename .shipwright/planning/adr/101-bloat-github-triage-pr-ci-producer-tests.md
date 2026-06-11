# ADR-101: Bloat exception — `gh-pr-ci` producer test suite + the shared hermeticity conftest

- **Status:** accepted
- **Date:** 2026-06-11
- **Re-Review-Date:** 2026-09-11 _(check whether the github_triage test
  suites should finally be split per-source, or the exception retired)_
- **Incident Reference:** PR #191 (iterate-2026-06-11-automerge-gh-pr-ci-producer)
  — adds the `gh-pr-ci:{pr_number}` loop-closing triage producer (B4.5). First
  crossing surfaced when the new producer's comprehensive test suite and the
  shared autouse hermeticity fixture pushed two test-infra files past 300 LOC.

## Context

The `gh-pr-ci` producer surfaces failed hard-gates on open PRs into triage. Two
**test-infrastructure** files crossed the 300-LOC limit:

- `shared/tests/test_github_triage_pr_ci.py` (420) — a new, cohesive
  github_triage producer test suite (28 tests): the `github_pr_api` fetch/reduce
  layer, the `pr_ci_action_unit` mapper, the differentiated `resolve_pr_ci`, and
  the `import_findings` consumer wiring (every AC + both symmetry halves +
  truncation + `filter=latest` + all three resolve reasons + a wiring guard).
- `shared/tests/conftest.py` (296 → 320) — a single autouse fixture
  (`_isolate_github_pr_api`) that neutralises the live PR fetchers so the
  EXISTING github_triage consumer suites stay hermetic (`import_findings` now
  fans out to `gh api`; gh substitutes `{owner}/{repo}` from cwd, so an
  un-stubbed fetch inside the worktree would hit the real repo).

Source files were kept at/under budget on purpose: `github_api.py` was NOT grown
(the new fetches live in a fresh `github_pr_api.py`, 159 LOC); `consumer.py` is
294 (the PR-CI orchestration was extracted into `pr_ci.py`, 62); all other new
producer modules are <300 and unbaselined.

## Ousterhout Argument

Both files are **deep modules**. `test_github_triage_pr_ci.py` is one cohesive
per-subsystem suite over a narrow surface (one producer source) with substantial
behaviour behind it (network-fetch parsing, symmetry, truncation, differentiated
resolve). `conftest.py`'s autouse fixture is a deep test fixture: a one-line
interface (neutralise live PR fetchers) over the substantial guarantee that
every consumer test in the directory stays off the network. Splitting either
would expose internals the structure exists to hide — scattering related
triage-producer tests, or fragmenting the shared hermeticity guarantee.

## YAGNI Check

Every responsibility is needed **today**: each test pins a shipped AC or a
review-mandated guard (symmetry, truncation, `filter=latest`, keep-open). None
is speculative. The conftest fixture is needed the moment `import_findings`
gained the PR fetch — without it the existing suites flake against the live
repo. Nothing here could be deleted with "some work"; it is all load-bearing.

## Chesterton-Fence Check

The fence is **ADR-094** (2026-06-01), which already established that the
github_triage test suites stay WHOLE rather than split per-source — its own
Ousterhout/Rejected sections argue that splitting "would scatter related
triage-producer tests and force the fixture to be duplicated." This ADR honours
that standing decision: the new `gh-pr-ci` suite is the same class, so it is
exception-allowed, not split. The conftest fixture exists because the
alternative — stubbing in each consumer suite's `_patch_api` — would RATCHET
three grandfathered ADR-094 files (`test_github_triage.py` 421,
`test_github_triage_artifact_fallback.py` 718,
`test_github_triage_action_units.py` 598). Centralising in conftest tears down
that worse fence.

## Decision

Grant exceptions: `shared/tests/test_github_triage_pr_ci.py` → 420,
`shared/tests/conftest.py` → 320, both `state="exception"`, `adr="ADR-101"` in
`shipwright_bloat_baseline.json`. Retirement plan: at the Re-Review-Date, revisit
whether the github_triage suites (now 4: base, action_units, artifact_fallback,
pr_ci) warrant a shared `_github_triage_helpers.py` extraction that would let
several of them — and the conftest fixture — drop back under 300 together.

## Consequences

The new baseline `current` values become the anti-ratchet ceiling for these two
files; any further growth ratchets and must be justified. No downstream consumer
changes — these are test-only files. Cost if the exception outlives the
Re-Review-Date: two more test-infra files carrying the "comprehensive suite"
debt that a single helper-extraction iterate could repay.

## Rejected alternatives

- **Split `test_github_triage_pr_ci.py` now.** Rejected: directly contradicts
  ADR-094's standing decision that these suites stay whole; would scatter the
  producer's tests across files and duplicate the shared fixtures, for the sole
  purpose of dodging LOC.
- **Stub hermeticity in each consumer suite's `_patch_api` instead of conftest.**
  Rejected: ratchets THREE grandfathered ADR-094 files (421/598/718 → larger),
  a strictly worse bloat outcome than one +24-LOC conftest crossing, and
  duplicates the same three setattr lines four times.
- **Leave at 300 and shrink.** Rejected: the suite already omits no AC and the
  conftest was at 296 before any change — there is no slack to cut without
  deleting load-bearing coverage or unrelated fixtures.

---

## External Sources Acknowledged

The YAGNI Check + Chesterton-Fence Check headings are adapted from
obra/superpowers `writing-plans` (MIT © Jesse Vincent) and
addyosmani/agent-skills `code-simplification` (MIT © Addy Osmani). The
Incident-Reference field follows the per-decision incident-reference pattern of
`multica-ai/multica` `CLAUDE.md` (Apache-2.0 modified-with-hosting-restriction —
pattern reusable, text not copied).
