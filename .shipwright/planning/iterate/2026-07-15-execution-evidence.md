# Iterate ADR — TT-EV: Per-test execution-evidence ingestion → manifest status/executed

- Run-ID: `iterate-2026-07-15-execution-evidence`
- Campaign: `2026-07-15-test-traceability-layers` · sub-iterate `TT-EV` (#2 of 9)
- change_type: feature · complexity: small (risk flag `touches_migrations` is a
  prose-keyword false positive — the fixture mentions "database persistence"; the
  diff has no migration; overridden per `feedback_classifier_message_keyword_falsepos`)
- Closes Spec §11 **R1 / G5**: "covered at a layer" now means a tagged test that
  is **enabled AND observed passing** in that layer's runner evidence.

## What shipped

- `collectors/execution_evidence.py` — pure reader: JUnit XML / Playwright JSON /
  Vitest reporter → normalized `{path::name → {status, executed, runner}}`, frozen
  closed vocab, fail-closed coercion, cross-report fail-closed merge, waiver
  primitives (`waiver_state` / `layer_satisfied`), schema validation.
- `collectors/_execution_evidence_io.py` — discovery + writer + CLI; `refresh_index`
  (non-destructive, freshness-stamped, carries operator waivers forward).
- `evidence_index_schema.json` — frozen closed-enum boundary for the index (+ waiver).
- `test_links.generate_file` — one wiring call: refresh from raw reports; pass EMPTY
  evidence when no fresh report (fail-closed, never a stale pass).
- `F5.md` — documents the raw-report drop contract + fail-closed semantics.
- 35 new tests across two files (reader-core + join/waiver/wiring).

## External-Plan-Review-Findings (Step 3.5 — GPT-5.4 + Gemini 3.1 Pro, OpenRouter, not degraded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| P1 | High | Non-destructive refresh lets a stale index self-report a prior pass | accepted-and-fixed — `generate_file` passes EMPTY evidence when no fresh report; index left on disk for audit only; freshness stamp added |
| P2 | High | Naive `path::name` will mismatch across runner formats (browser suffix, params) | accepted-with-scope — identity is FROZEN by TT1 (`path::name`); mismatch degrades fail-closed to not_run (safe); cross-runner id reconciliation is TT6/TT8 (real-repo retrofit) |
| P3 | High | `surface_verification.py`/F5 don't PRODUCE reports → collector has no data | accepted-with-scope — reader + drop-contract (F5.md) + fail-closed absence shipped; producer reporter-flag emission deferred to TT5 (owns running suites base+head); surface_verification is runner-agnostic by contract, hardcoding flags would break its tested exit-code abstraction |
| P4 | Med | JUnit XXE / billion-laughs via `xml.etree` | accepted-and-fixed — no defusedxml dep available; added an 8 MB size cap + ParseError→fail-closed empty; reports are repo-internal |
| P5 | Med | `only`/`quarantined` source authority; unknown→quarantined can mislabel | accepted-with-note — reader maps runner evidence to enabled/skipped only; `only`/`quarantined` reserved for TT4 static hygiene; unknown→quarantined is the fail-closed held-out target, tested `only`/`quarantined`+pass ⇒ MISSING |
| P6 | Med | "missing evidence → not_run" must apply to EVERY expected test | accepted-and-fixed — TT1 defaults absent test → not_run; added partial-evidence omission test (report present, omits a required test → MISSING) |
| P7 | Med | Verify `_cov_status`/`_make_link` are truly evidence-aware | accepted-and-fixed — added a 7-case `_cov_status` predicate table (absent/skipped/fail/not_run/quarantined/only/enabled-pass) |
| P8 | Med | JUnit XML parser attack surface | see P4 |
| P9 | Med | Waiver policy: location, scope, UTC expiry, owner/ticket, waived≠ok | accepted-and-fixed — versioned schema, full accountability required, `scope` field, UTC date compare; "waived" surfaced by the gate (TT2) not as coverage=ok (frozen enum) |
| P10 | Low | Separate schema may be redundant; if kept, test enum-drift | accepted-and-fixed — schema is a spec requirement (validated boundary); added a code↔schema enum-drift test |
| P-tz | Low | Waiver expiry TZ drift | accepted — `waiver_state` compares in UTC at date granularity |

## External-Code-Review-Findings (Step 3.7 — GPT-5.4 + Gemini, OpenRouter, not degraded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | High | Regen with no reports still consumes a prior index's passes (AC3) | accepted-and-fixed — `fresh = refresh_index(...)`; `evidence = load_evidence() if fresh else {}` |
| C2 | High | Waivers can't flow index→gate; `normalize_index` drops them; `build_index` has no waiver input | accepted-and-fixed — `build_index`/`normalize_index` carry waivers; `refresh_index` reads + re-emits existing operator waivers |
| C3 | High | Finalization emission (surface_verification/F5) not implemented | accepted-with-scope — same as P3 (deferred to TT5; fail-closed absence) |
| C4 | Med | status=enabled inferred from a pass; no source-derived `only`/quarantine | accepted-with-note — same as P5; added `only`+pass ⇒ MISSING test |
| C5 | Med | The missing-evidence test blessed the stale-index regression | accepted-and-fixed — added `test_stale_index_is_not_trusted_when_no_fresh_reports` (generate_file two-run scenario) |
| C-gemini | — | `layer_satisfied` unused in-diff is fine (a TT2/TT5 primitive) | acknowledged — matches the mini-plan non-goal |

Internal reviewer cascade (spec→code→doubt): `delegated_to_orchestrator`.

## Self-Review (Step 3.6)

1. **Spec Compliance** — pass: AC1-AC5 each mapped to a green test; R1/G5 pinned.
2. **Error Handling** — pass: JSON/XML parse + oversized reports fail-closed to
   empty; missing evidence → not_run; malformed/expired waiver → not honored;
   schema drift raises loud on write.
3. **Security Basics** — pass: XML size cap vs billion-laughs; repo-internal
   reports; no secrets/eval/exec; waivers require accountability metadata.
4. **Test Quality** — pass: RED-before/green-after; real raw-report→reader→manifest
   round-trip; fail-closed edges pinned (skipped/missing/stale/expired/out-of-vocab/
   duplicate-merge/retry/oversized).
5. **Performance Basics** — pass: linear parse, byte-capped XML, lazy jsonschema.
6. **Naming & Structure** — pass: reader/io split mirrors `test_links`/`_test_links_io`;
   frozen vocab single source; every file ≤300 LOC.
7. **Affected Boundaries (ADR-024)** — pass: producer = `execution_evidence` reader,
   consumer = `test_links.build_manifest` via `load_evidence`; serialized format =
   `evidence_index_schema.json`. Real round-trip probe run (raw reports → index →
   manifest coverage + CLI producer probe).

Items failed: 0 / 7.

## Confidence Calibration (Step 3.8 — touches_io_boundary)

Boundaries probed:

- **Raw report → normalized index.** Probe: parse all three real P1 fixtures via
  the reader → reproduces the panel-verified `evidence_index.json` answer key
  exactly (status/executed/runner). Edge probes: skipped→not_run, failure/error
  children→fail, oversized XML→empty, duplicate id (fail then pass)→fail, Playwright
  retry (fail then pass)→pass, out-of-vocab→coerced. Findings: none after fix.
- **Index → manifest coverage (producer→consumer).** Probe: raw→reader→build_manifest
  ⇒ FR-03.01 e2e MISSING (skipped), FR-03.02 e2e ok; partial-evidence omission ⇒
  MISSING; stale on-disk index at `generate_file` ⇒ MISSING. Finding: stale-index
  trust hole (C1/P1) → fixed → re-probed green.
- **Waiver → gate decision.** Probe: valid/expired/invalid `waiver_state`;
  `layer_satisfied` honors valid, fails expired; waiver survives refresh + normalize.
  Finding: waiver-drop (C2) → fixed → re-probed green.
- **CLI producer probe:** ran `_execution_evidence_io` over the fixtures →
  skipped-e2e=not_run, dashboard=pass, 9 results. Green.

Probes run: 4 boundaries + CLI. Probes with findings: 2 (both fixed). Asymptote:
reached — two consecutive clean probe passes (full suite + CLI round-trip) after
the last fix. Edge cases NOT probed: real-world cross-runner id divergence
(browser-suffixed Playwright titles, parameterized pytest ids) — acceptable
because the campaign froze `path::name` (TT1) and a mismatch degrades fail-closed
to not_run; real-repo id reconciliation is TT6/TT8 scope.
