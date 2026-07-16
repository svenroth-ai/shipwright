# Iterate ADR — TT3: `required_layers` on FRs (project + plan + adopt infers)

- **Run-ID:** iterate-2026-07-15-required-layers-on-frs
- **Campaign:** 2026-07-15-test-traceability-layers (sub-iterate TT3, serial #3 of 8/9)
- **Complexity:** medium (classifier said `large` — prose-keyword FP, overridden; see Risk-flag note) · **change_type:** feature · **spec_impact:** none (framework tooling)
- **Covers gap:** G2, G4 (the "declare the expectation" half) + adopt inference (Spec §6, ask E). Depends on TT1; lands before TT2's `D-layer` hard gate.

## Summary

Give each FR a declared `Layers` set (`{unit, integration, e2e}`) so per-layer coverage is
machine-checkable. TT1 already shipped the single requirement-model parser
(`_requirement_parse.parse_requirements`) reading the `Layers` column into
`Requirement.required_layers` + `required_layers_source ∈ {explicit, inferred_legacy,
defaulted_legacy}` and feeding the manifest — so the model-side parse + provenance were
already DONE. TT3's remaining work:

1. **`shared/scripts/lib/drift_parsers.py`** — the shared FR-table parser DROPPED a row
   carrying a `Layers` column (its optional tail required exactly 2 cells). Net-zero fix:
   append the linear `(?:[^|]*\|)*` trailing-cell tolerance (mirrors rtm.py's
   ReDoS-hardened matcher). No divergent layer-parse added — the model parser stays the one
   `required_layers` producer (binding R5).
2. **`plugins/shipwright-adopt/scripts/lib/render_helpers.py`** — new pure
   `infer_required_layers(feature)`: route/page/UI-framework ⇒ e2e; migration / schema /
   table / RLS-policy source ⇒ integration; every FR ⇒ unit; unknown ⇒ unit only
   (conservative, Spec §9). Neutral leaf, no cross-package import.
3. **`plugins/shipwright-adopt/scripts/lib/artifact_writer.py`** — net-zero: add a `Layers`
   column to the adopt FR table, annotated `(inferred)` (see decision below).
4. **Docs** (what/how, no provenance): spec-generation.md (Layers column + emission
   heuristic + author override), e2e-test-plan.md, adopt SKILL.md, guide.md.
5. **Tests** (new files, avoid grandfathered): drift tolerance, adopt inference + rendered
   spec + brownfield-fixture pipeline, extended requirement-parse (explicit integration,
   legacy provenance, `(inferred)` downgrade, normalization).

Bloat baseline NOT ratcheted: `drift_parsers.py` stays exactly 523; `artifact_writer.py`
695 < 771; new/edited source ≤300; runtime-prompt ≤400.

### Notable design decisions
- **`(inferred)` marker (provenance fix).** Adopt writes a *populated* Layers cell; the model
  parser would classify any populated cell `explicit` → an adopted brownfield FR would collapse
  into the hard-gate regime and drown in MISSING findings (Spec §9). Fix: adopt annotates its
  surface-derived cells `(inferred)`; the model parser downgrades a marked cell to
  `inferred_legacy` (advisory). This keeps the three provenances distinct (R4) and honors the
  "adopted FRs stay advisory" landmine. Verified by the producer→spec.md→parser round-trip probe.
- **No divergent parser.** `drift_parsers` / `rtm.collect_requirements` / `spec_parser` are NOT
  taught to parse `required_layers`. `_requirement_parse` (→ manifest) is the single API (R5);
  drift only needs to stop dropping rows; RTM (TT2) reads the manifest. Adding a second
  layer-parse to those would be the exact anti-pattern R5 forbids.
- **Legacy inference is conservative single-layer** (`("e2e",)` / `("unit",)`), matching the
  brief's "(unit; e2e if UI-classified)". The full `unit + surface` union is the EMISSION rule
  (adopt code always prepends unit; project/plan documented to). The two paths differ by design.

## External-Plan-Review-Findings (Step 3.5 — Gemini 3.1 Pro + GPT-5.4 via OpenRouter, both succeeded, not degraded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| G1 | High | drift_parsers dropping the Layers column blinds drift → a manual layer downgrade escapes. | **rejected-with-reason** — the Layers-coverage gate is TT2's `D-layer`, which regenerates base+head from the head spec via the model parser (R3), NOT drift_parsers (coarse FR-text/priority drift, deliberately layer-agnostic per R5). A manual downgrade is caught by D-layer reading the head spec. |
| G2 | Med | Adopt inference misses backend API (controller/handler/resolver) → integration under-reported. | **rejected-with-reason** — Spec defines the integration signal as a *persistence* surface (table/RLS/migration/schema); broadening to `api`/`controller` risks the Spec §9 "drown adopted repos in MISSING-integration" landmine and exceeds the spec-mandated heuristic. Authors refine via iterate. |
| G3 | Low | Layers column could land at different indices per generator; verify header-mapped not index-mapped. | **accepted-and-verified** — `_requirement_parse` IS header-column-aware (`_header_map` + `_LAYERS_COLS`); drift_parsers only discards the tail. No change. |
| G4 | Low | ReDoS on `(?:[^|]*\|)*`; consider `.*`. | **rejected-with-reason** — mirrors rtm.py's CodeQL-cleared linear matcher; the two `_FR_TABLE_RE` forms are an explicit "kept in sync" invariant; `[^|]*\|` is linear (no ambiguous overlap). Added a pathological-row timing regression test. |
| O1 | High | Provenance can't tell a pre-rollout absent field from a post-rollout author omission → post-rollout omission stays advisory (AC3). | **rejected-with-reason (design per R4)** — the campaign keys WARN-vs-FAIL on `required_layers_source` (explicit⇒hard, legacy⇒advisory), not a creation-timestamp; a durable rollout marker is out of TT3 scope + not the reviewed design. Residual (a human hand-omitting the column post-rollout reads advisory) documented as a TT2/TT4 follow-up; mitigated by project/plan always emitting the column + TT8 retrofitting legacy→explicit. |
| O2 | High | Adopt-rendered Layers would read as `explicit`, collapsing inferred provenance (violates §9 + R4). | **accepted-and-fixed** — the `(inferred)` marker + model-parser downgrade to `inferred_legacy`. Round-trip probe confirms. This was the one real correctness bug. |
| O3 | Med | Audit call paths; add spec→model→manifest round-trip; rtm.py/spec_parser may re-parse. | **accepted-partially** — audited: only 2 `_FR_TABLE_RE` (drift + rtm), both now tolerant; `_requirement_parse` is the single manifest path. Added the round-trip probe + the `(inferred)` provenance test. rtm/spec_parser stay layer-agnostic by R5. |
| O4 | Med | Regex trailing tolerance underspecified (blank/whitespace/reordered/extra cols). | **accepted-and-fixed** — `_requirement_parse` is header-driven (reorder-safe); added normalization test (case-fold, dedup, drop-unknown) + drift tests for 3/4/6-col + backward-compat. |
| O5 | High | Layers validation semantics (`E2E`, dup, `foo`, `none`, empty). | **accepted-and-fixed** — the model parser already normalizes (lowercase + dedup + valid-only); pinned by `test_layers_are_normalized_...`. A hard-reject-on-invalid (needs an `invalid_layers` channel) is deferred to TT2/TT4. |
| O6 | Med | AC1 needs project/plan to actually EMIT; are the reference docs the runtime templates? | **accepted-and-verified** — `/shipwright-project` + `/shipwright-plan` are prompt-driven; spec-generation.md / e2e-test-plan.md ARE their runtime authoring instructions. Updating them IS the emission change (no code entrypoint). |
| O7 | Med | Adopt heuristic on arbitrary text; incidental keywords misclassify; use structured signals. | **accepted-and-fixed** — the helper reads adopt's *structured* signals (`source_file`/`route`/`framework`), matched on path SEGMENTS; added a negative test (`components/UserTable.tsx` ⇒ e2e, not integration) + a union test. |
| O8 | Med | AC3 needs TT2 D-layer behavior; add a versioned contract fixture shared with TT2. | **accepted-partially** — the P1 `fixtures/traceability/` harness already carries provenance-tagged specs as the shared contract; TT3 pins the parser's three-regime output; TT2 consumes the manifest. |

## External-Code-Review-Findings (Step 3.7 — Gemini + GPT-5.4 via OpenRouter; Gemini returned garbled/non-actionable; internal cascade delegated to orchestrator)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | High | No rollout marker → post-rollout omission not hard-gated. | **rejected-with-reason** — same as plan O1 (design per R4). |
| C2 | High | UI fallback `("e2e",)` omits unit; explicit `e2e` accepted without unit. | **rejected-with-reason** — the brief's backward-compat default is explicitly "(unit; e2e if UI-classified)" = a single conservative inferred layer (TT1 contract). Emission paths (adopt code / project-plan docs) DO always include unit. Forcing unit onto an explicit author set would violate Spec D2 "authors can override". |
| C3 | High | Only compliance parser updated; shared parser + RTM don't carry the field. | **rejected-with-reason** — R5: `_requirement_parse`→manifest is the single requirement-model API; the coarse parsers stay layer-agnostic; RTM (TT2) reads the manifest. Adding layers to each = the divergent-parser anti-pattern. |
| C4 | Med | Provenance from an untrusted free-text `(inferred)` marker is author-forgeable → hard-gate bypass. | **accepted-risk (documented)** — threat model is honest authors (a self-downgrade is self-sabotage, not an attack); the marker keeps provenance in the spec.md single-source and is human-readable ("these were auto-derived, review them"). A trusted out-of-band channel is deferred (new artifact, out of TT3 scope). Documented in SKILL.md + the parser docstring. |
| C5 | Med | Adopt misses a `src/tables/orders.ts` table surface (not under db/schema). | **accepted-and-fixed** — added `tables?` + `repositor(y|ies)` as path-SEGMENT signals (segment-anchored so `UserTable.tsx` still ⇒ e2e; negative test green). |
| C6 | Med | Adopt tests use hand-built dicts, not a real fixture repo (AC2). | **accepted-and-fixed** — added `test_brownfield_fixture_route_frs_declare_e2e_end_to_end` running the real `infer_features_ast` over the `nextjs_repo` fixture → render → assert `e2e (inferred)`. (migration→integration is pinned at the unit level; `feature_inferrer` enumerates routes, not migrations.) |
| C7 | Med | No project/plan generation test asserting emitted defaults. | **rejected-with-reason** — project/plan emission is prompt-driven via the reference docs (no code entrypoint to unit-test); adopt's code-driven emission IS tested. |

## Internal review cascade (orchestrator) — spec PASS · code PASS (2 non-blocking MED) · doubt 1 HIGH + 2 MED

The orchestrator ran the internal `spec-reviewer` → `code-reviewer` → `doubt-reviewer` cascade
on the pushed diff (the runner has no Agent tool). spec PASS, code PASS; the adversarial
doubt-reviewer found (and the orchestrator confirmed by reading the code) a HIGH provenance
re-collapse plus advisories, all fixed on the SAME branch and folded into the amended F6.
`reviews.code.status = "delegated_to_orchestrator"`.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| D1 | High | Provenance collapse re-opened at the parse seam: a **filled-but-non-canonical** Layers cell (author typo/synonym, `int, db`) → `_parse_layers` returns `()` → falls through to `_infer_layers` → advisory `defaulted_legacy`, escaping the post-rollout hard gate AND silently discarding the author's intended layer. | **accepted-and-fixed** — a non-empty, explicitly-headed Layers cell with zero valid layers + no marker now stays `explicit` (hard-gated) and is recorded in a new `invalid_layers` manifest channel (mirrors `invalid_tags`; schema `$defs/invalidLayer`, optional/additive so the golden still validates). Positional headerless cells stay legacy (Description ambiguity). Pinned by `test_nonempty_but_noncanonical_layers_cell_is_flagged_not_demoted` + `test_invalid_layers_cell_surfaced_and_fr_stays_explicit`. |
| D2 | Med | Over-broad `_INFERRED_MARKER_RE` matched `inferred\|auto\|adopt\|adopted`, but adopt only emits `(inferred)` — a post-rollout author writing `(auto)` was silently downgraded to advisory, escaping the gate. | **accepted-and-fixed** — narrowed to exactly `(inferred)`. Pinned by `test_only_the_exact_inferred_marker_downgrades_not_auto_or_adopt`. |
| D3 | Med | Untested cross-plugin marker contract: the bare `(inferred)` literal is duplicated across adopt (writer) and compliance (reader) with no spanning test → a drift on either side false-REDs every adopted FR while both suites stay green. | **accepted-and-fixed** — added a cross-plugin round-trip (`test_inferred_marker_roundtrip_binds_adopt_emit_to_compliance_read`) that renders a real adopt spec and pipes it through the real compliance parser, asserting `inferred_legacy`. |
| D4 | Med (code+doubt) | e2e over-declaration: `is_ui = bool(route) or bool(framework)` fired e2e on EVERY adopted feature (feature_inferrer sets route+framework even for backend fastapi/flask/express) — contradicting "API-only stays unit". | **accepted-and-fixed** — e2e now requires a UI framework token OR a UI-file source, and a KNOWN backend framework suppresses it (incl. Flask's `app/views/` handlers); dropped the bare `app/`+`routes/` over-fire from `_E2E_SOURCE_RE`. Pinned by `test_backend_api_route_is_not_e2e` + `test_backend_data_route_infers_integration_not_e2e`. |
| D5 | Low (code) | ReDoS perf test used a MATCHING row (never exercised backtracking-on-failure). | **accepted-and-fixed** — added `test_trailing_tolerance_is_linear_time_on_a_NON_matching_row` (no closing pipe, forces the `\s*$` failure path). |
| D6 | Low (code) | Test-only ADR-045 bypass: raw `sys.path.insert` + `from requirement_model import LAYERS`. | **accepted-and-fixed** — routed through compliance's `_lib_loader.load_shared_lib`; adopt `lib.*` imported first so the loader's `shared/scripts` path insert can't shadow adopt's `lib` (documented in the test header). |

## Self-Review (Step 3.6 — canonical 7-item checklist)

1. **Spec Compliance** — PASS. AC1 (explicit + default parse, integration case), AC2 (adopt
   infers, real-fixture pinned), AC3 (provenance two regimes + `(inferred)` downgrade), AC4
   (RED-before → green tests), AC5 (docs + footprint + bloat + LOC) all met.
2. **Error Handling** — PASS. `infer_required_layers` reads `.get(...)` with defaults (missing
   keys safe); parsers tolerate absent/blank/malformed Layers cells (fall to inference); no
   unguarded crashes on empty/None features.
3. **Security Basics** — PASS. No eval/exec; Layers cell parsed as text (valid-only token
   filter); regex is linear (ReDoS-safe, pathological-row test). `(inferred)`-marker
   forgeability is an accepted-risk (honest-author threat model, documented — C4).
4. **Test Quality** — PASS. 23 new/extended tests across 3 files: drift tolerance (3/4/6-col +
   backward-compat + timing), adopt inference (route/page/migration/RLS/table/union/negative +
   marker + brownfield fixture), parser (explicit integration, legacy provenance, `(inferred)`
   downgrade, normalization). RED-before verified (drops + ImportError) → green-after.
5. **Performance Basics** — PASS. Single-pass regex per row; no N+1; the trailing-tolerance
   pattern is linear (4000-cell row < 1s test).
6. **Naming & Structure** — PASS. `infer_required_layers` in the neutral-leaf `render_helpers`
   (already imported by artifact_writer → net-zero); marker regex + docstring co-located with the
   provenance logic it drives.
7. **Affected Boundaries (ADR-024)** — PASS. Producer = adopt `_render_spec_md` + project/plan
   authoring; consumer = `_requirement_parse` → manifest (+ drift_parsers coarse read). Real
   producer→spec.md→consumer round-trip probe run (see Confidence Calibration).

## Confidence Calibration (Step 3.8 — empirical probes, asymptote heuristic)

Boundary: the human-edited/machine-parsed `spec.md` FR table (a serialized-format producer +
consumer) — `touches_io_boundary`.

- **Probes run (4, two-process to mirror the real pipeline + avoid the ADR-045 `lib` in-process
  collision):** (1) external code review found the adopt `explicit`-collapse bug → **fixed** via
  `(inferred)` marker; (2) adopt renders a real 3-FR spec (route/migration/util) → the model
  parser reads it back → all three `inferred_legacy`, surface layers correct (route⇒e2e,
  migration⇒integration, util⇒unit) → clean; (3) CRLF-encoded human-edited spec → explicit
  `unit, integration` round-trips → clean; (4) drift_parsers on the same 6-col `(inferred)` spec
  → no FR dropped, body = Description, marker never leaks into FR text → clean.
- **Findings:** one bug (probe 1) → fixed → probes 2–4 clean. Two+ consecutive clean probes ⇒
  **asymptote reached; boundary calibrated.**
- **Edge cases not probed (acceptable):** a maliciously hand-forged `(inferred)` on an explicit FR
  (accepted-risk C4 — honest-author threat model); BOM prefix (utf-8 `errors="ignore"` +
  `splitlines` already proven BOM/CRLF-tolerant in TT1's calibration); multi-split display-id
  fan-out (inherited TT1 limitation, TT2/TT5 scope).

## Risk-flag note

The complexity classifier returned `estimate: large` with `touches_auth` / `touches_rls` /
`touches_migrations`. All are **prose-keyword false positives** (`prior_source: keyword`,
`history_n: 0`): the spec *discusses* auth/sign-in, RLS, and migrations only as example
surface-inference keywords; the actual diff touches ZERO auth/RLS/migration code (one net-zero
regex line, a ~45-line pure adopt helper, doc + test additions). Overridden to `medium` per the
documented `classify_complexity` message-keyword FP pattern; F11 recomputes risk from
diff-predicates (`risk_detectors.py`), which will not re-raise these.
