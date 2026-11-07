# Iterate: second e2e fixture `social-engagement-baseline` with its own checklist

Run: `iterate-2026-11-03-e2e-baseline-fixture` | type: feature | complexity: medium | no triage card

## Goal

Add a third skill-companion e2e fixture next to `social-engagement-real` (which keeps working unchanged): the finished Briefing
package derived from the REAL social-engagement skill (21 capabilities, 7 approved mockups, synthetic service answers in the
real shapes, a stand-in agent run), plus a checklist derived item by item from the brief's own Fit criteria, so the operator-started
e2e run can say, per capability, whether the built app does what the brief promises.

## Acceptance criteria

1. The package is copied byte-identical into `integration-tests/fixtures/social-engagement-baseline/` (hash unchanged, `OPEN.md` and
   `provenance.md` travel with it, no evidence folder); it carries no approval - the harness records `approved_by: fixture:<name>`
   in the run's COPY only (outside the hash).
2. `SHIPWRIGHT_E2E_FIXTURE=social-engagement-baseline` selects its own checklist (`social-engagement-baseline-expected-result.md`) and
   suite; `social-engagement-board` (default) and `social-engagement-real` behave as before; the report prints the fixture and the
   checklist that ran.
3. The checklist covers lifecycle, the API contract, fetching through the adapter against local fake servers (Syften, Apify, HN
   replaying `seed/recorded/` through `index.json`; dummy tokens; secrecy scan), dedupe, run storage, draft lint, status and derived
   expiry (clock override), feedback, queue, events, lessons, config, data folder files and layout, data location order, the store
   and adapter structure checks, the built SKILL.md, the board (master-detail, counts, keys, thread view, one comment count, copy,
   feedback, status actions, 390 px, tokens), plus the shared pipeline items and the soft S03/S09.
4. The screen tour reaches each mockup state from the screen-map by a recipe and checks a marker; a state that is not reached is
   reported and no wrong screenshot is attached.
5. New check code is split into small modules under `src/baseline/` (each below the 300-line cap), has unit tests with synthetic
   input, typecheck and the existing unit specs pass, README and answer key are updated, no real network or key is used.

## Spec Impact

NONE (test harness and fixture data; no product behaviour). Tests carry `FR-01.06` (the e2e harness requirement).

## Out of Scope

A real e2e run (the operator starts it), editing the package, changing the S08 gate logic, changing how `social-engagement-real` runs.

## Design Notes

- One new module folder `src/baseline/`; the shared modules get only additive hooks (fixture name, `Checklist.describe`, a trigger
  phrase parameter, one `if (baseline)` branch each in the spec for static checks, approval stamp and the suite).
- Every dynamic check starts the BUILT `backend/server.py` itself (`companion.ts`): free 127.0.0.1 port, throw-away data folder, temp
  HOME, clean environment; a `Probe` collects expectations per item so one item reports every broken rule.
- The fake services (`fake-services.ts`) are data driven from `index.json` (`when` sentences), record every request, and can be told
  to fail; tokens are random dummy values per run.
- Approval: `approval.ts` stamps the run's copy only when the delivered package has none.
- State reaching: recipes keyed by screen id, each checks a marker of the state.

## Affected Boundaries

Producer/consumer of serialized data: `brief.json` (read-modify-write of the COPY; hash-excluded keys only - tested with the
pipeline's own digest), `seed/recorded/index.json` (read by the fake), `seed/agent/run-synthetic.json` (posted to the companion),
the companion's JSON API (consumed by the checks), `screen-map.json` (consumed by the tour; a Python test pins one recipe per screen).

## Confidence Calibration

- **Boundaries touched:** brief.json copy, index.json replay, run-synthetic.json post, companion API, screen-map.json.
- **Empirical probes run:** package hash after the approval stamp (real pipeline digest); fake servers replayed over the real
  recorded files (Syften pages, Apify actor selection by url, dataset paging, HN, 401, forced failures); a stand-in Python backend
  started and killed by `companion.ts` (correct and flawed Host rule); mockup 01 and 07 read by the board helpers; the stand-in
  feedback text parsed from the real mockups.
- **Test Completeness Ledger:** see F5; the checks against a REAL built app cannot run here (no built app exists without a model run).
- **Confidence-pattern check:** the dynamic checks were exercised against a stub only; their expectations come from the brief text.
  The first real run is the empirical test; unknowns are listed in the report (linkedin-queries.json format, the helper's flags).

## Internal Plan Review

(see reviews.json)
