# ADR-094: Bloat exception — `github_triage` test suites raised for the `gh-prompt:` producer

- **Status:** accepted
- **Date:** 2026-06-01
- **Re-Review-Date:** 2026-09-01 _(check whether the github_triage test
  suites should be split per-source, or the exception can be retired)_
- **Incident Reference:** PR adding the `prompt_risks.json` triage producer
  (`gh-prompt:` source) + a hermeticity fix for the existing `gh-security`
  artifact path. First crossing surfaced when the new producer's tests +
  `_patch_api` extensions pushed two already-grandfathered test files past
  their baseline.

## Context

The `prompt_risks.json` triage producer adds a new artifact source mirroring
the proven `findings.json` path. Two **test** files grew:

- `shared/tests/test_github_triage.py` 413 → 421 (+8): `_patch_api` now mocks
  the artifact functions (`latest_security_workflow_run`,
  `download_security_findings`, `download_prompt_risks`) — a hermeticity fix for
  a **pre-existing** flake (the `gh-security` artifact path hit real `gh` once
  the repo had fresh successful `security.yml` runs; reproduced on `main`).
- `shared/tests/test_github_triage_artifact_fallback.py` 713 → 718 (+5):
  `_patch_api` gains a `download_prompt_risks` patch so the new consumer path is
  hermetic.

Source files were kept at/under baseline: `github_api.py` stayed at 392 (the
new `download_prompt_risks` rode a shared helper + a docstring trim);
`producer.py`/`consumer.py` are under 300 and unbaselined.

## Ousterhout Argument

These are cohesive **per-subsystem test suites** for `github_triage`, and
`_patch_api` is a deep test fixture: a narrow interface (patch every
`github_api` entry point) over substantial behaviour. The new source must be
mocked there too or the suite is non-hermetic. Splitting the suites to dodge
+13 LOC would scatter related triage-producer tests and force the fixture to be
duplicated — exposing the very wiring the fixture exists to hide.

## YAGNI Check

Every added line is needed **today**: the 3 `_patch_api` mocks close a live
flake reproduced on `main`; the fallback patch is required for the new
consumer path. No speculative scope — the regression tests for `gh-prompt:`
live in a separate, unbaselined file.

## Chesterton-Fence Check

The test files are large because `github_triage` has many sources
(security / secrets / CI / artifact), each needing coverage, with `_patch_api`
centralising gh mocking (DRY). git history shows the suites grew source-by-
source under that same structure. The fence stands for a reason; extending it
by a few lines for the new source is consistent with it, not a violation.

## Decision

Raise `test_github_triage.py` to 421 and
`test_github_triage_artifact_fallback.py` to 718 (`state: exception`,
`adr: ADR-094`). Retire when the `github_triage` suites are split per-source
(tracked at the Re-Review-Date).

## Consequences

The two suites now operate against the new limits; further additions must stay
within them or bump again with justification. No source-file limit moved.

## Rejected alternatives

- **Split the suites now** — disproportionate: the files are coherent and the
  trigger is +13 LOC, not a structural problem. Splitting churns a large,
  well-tested module for cosmetic LOC.
- **Skip the tests / skip the hermeticity fix** — unacceptable: leaves the new
  producer without regression coverage and the `gh-security` flake live.
