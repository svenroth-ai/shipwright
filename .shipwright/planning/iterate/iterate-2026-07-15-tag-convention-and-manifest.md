# Iterate ADR — TT1: `@FR` tag convention + `test_links` collector + traceability manifest

- **Run-ID:** iterate-2026-07-15-tag-convention-and-manifest
- **Campaign:** 2026-07-15-test-traceability-layers (sub-iterate TT1, serial #1 of 8/9)
- **Complexity:** medium · **change_type:** feature · **spec_impact:** none (framework tooling)
- **Covers gap:** G1 (no test→FR backward link). Blocks TT-EV, TT2, TT5, TT6, TT7.

## Summary

New compliance collector `test_links` reads the canonical `@FR-XX.YY` tags across pytest +
Playwright + Vitest (via the frozen `fr_tag_grammar` reference parser), joins them to the
FR table (Layers column, active + removed) and per-test execution evidence, and emits
`.shipwright/compliance/test-traceability.json` (schema v2). Data only — no gate flips. The
committed artifact is derived / RTM-visibility only; enforcing gates (TT5) regenerate
base+head themselves (R3). Footprint: 4 collector modules (split for the ≤300-LOC cap),
`update_compliance.py` PHASE_REPORTS wiring, both `rules/*tests.md.template` files, and one
test module. Bloat baseline NOT ratcheted; all files ≤300 LOC.

### Notable design decisions
- `_requirement_parse.py` **constructs** frozen `requirement_model.Requirement` objects from
  the spec FR table — it does not fork the model (the model is a contract, not a parser; its
  own docstring says collectors build instances from their own parse). Header-column-aware so
  the 4-col traceability shape and the 5-col adopt shape (ADR-031) never confuse Layers vs
  Description.
- `generate_file` scans the *conventional* test roots and honestly enumerates the untagged
  tests it finds; the COMPLETE repo-wide inventory (this monorepo has 638 test files under
  non-conventional dirs) is deferred to the shared backfill engine (TT6) + adopt (TT7) per
  Spec §7/§9 — committing a thousands-entry inventory here would be noise, not signal.
- Suite/`describe`-level tag propagation is added ON TOP of the reference parser (which binds
  `it`/`test` only, by design), reusing that parser's own classifiers so the valid/malformed
  split never diverges from the frozen grammar.

## External-Plan-Review-Findings (Step 3.5 — Gemini 3.1 Pro + GPT-5.4 via OpenRouter, both succeeded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| P1 | High | "Drop `_requirement_parse.py`; use the P1 requirement-model API." | **rejected-with-reason** — `requirement_model` is a frozen *model* (dataclass + closed vocab + key helpers), not a spec parser; no published parsing API exists. My parser produces the frozen `Requirement` type (no shape divergence) and is pinned by the golden test. Reviewer lacked the module source. |
| P2 | High | "AC3 requires untagged_tests; don't defer." | **rejected-with-reason** — `build_manifest` DOES enumerate untagged (fixture AC3 proven). Only the repo-wide inventory in `generate_file` is bounded, per Spec §7/§9 (TT6/TT8/adopt own it). |
| P3 | Med | "Remove coverage ok/MISSING; TT1 is data-only." | **rejected-with-reason** — the frozen v2 schema REQUIRES a `coverage` object and structurally enforces ok⟹enabled+pass; the golden pins the values. "No gates" = no red build, not "no coverage data". |
| P4 | Med | "4-file split is artificial." | **rejected-with-reason** — 300-LOC is a hard gate (ADR-099 + pre-commit anti-ratchet); a single file is ~460 LOC. Split lines are cohesive (IO / assembly / spec-parse / suite-tags). |
| GPT-P1 | High | "schema_version 1 vs 2 ambiguity." | **accepted-clarified** — frozen schema is `const 2`, MODEL_VERSION==2, golden is v2. The spec's "schema_version:1" line is superseded by its binding "consume manifest v2" revision. Emits 2. |
| GPT-P3 | High | "Static parse can't prove execution=pass; don't infer pass." | **accepted-and-verified** — status/executed come ONLY from the evidence index; absent evidence defaults to `not_run` (never `pass`), so coverage=ok requires real evidence. Pinned by `test_skipped_e2e_is_missing`. |
| GPT-P8 | Med | "spec_path normalization hides a rooting regression." | **accepted-and-fixed** — added `test_spec_path_is_project_root_relative_posix`. |

## External-Code-Review-Findings (Step 3.7 — Gemini + GPT-5.4 via OpenRouter, both succeeded; internal cascade delegated to orchestrator)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | High | `_requirement_parse.py` re-parses instead of P1 API. | **rejected-with-reason** — same as P1; no parsing API exists, output is the frozen type, golden-pinned. |
| C2 | High | `detect_layer` classifies `integration-tests/` and `.integration.test.*` as `unit`. | **accepted-and-fixed** — real bug. Now recognizes the `integration`/`integration-tests` dirs + `.integration.test.*`/`.integration.spec.*` filenames. Pinned by `test_layer_detection`. |
| C3 | Med | `generate_file` scans only a hard-coded root subset. | **rejected-with-reason (partial fix)** — repo-wide discovery is the TT6/TT8 boundary (Spec §7/§9); added `__tests__` to the conventional roots. The bounded scope is now pinned + documented by `test_generate_file_writes_valid_manifest`. |
| C4 | Med | Suite propagation drops the tag for a multiline callback brace / one-line suite. | **accepted-and-fixed (multiline+nested) / documented (one-line)** — added an `entered` flag so a Prettier-wrapped describe body is not popped early; pinned by `test_multiline_describe_signature_still_propagates` + `test_nested_describes_both_apply`. One-line `describe(...,()=>{it()})` remains a documented limitation. |
| C5 | Med | Tests bypass `generate_file` + `update_compliance` wiring (AC4). | **accepted-and-fixed** — added `test_generate_file_writes_valid_manifest` + `test_update_compliance_iterate_phase_emits_manifest`. |
| C6 | Low | AC2 fixture only covers same-line braces. | **accepted-and-fixed** — multiline + nested fixtures added. |
| C-Gemini | High(?) | Truncated mid-analysis of `_suite_tags.py` pending-state. | **reviewed — no actionable defect**; the `pending` state is cleared on every non-comment, non-decl line (matches the frozen parser's own flush semantics). |

## Self-Review (Step 3.6 — canonical 7-item checklist)

1. **Spec Compliance** — PASS. AC1–AC5 met; golden reproduced exactly (modulo audit-only
   provenance + spec_path rooting); frozen contracts consumed, not forked.
2. **Error Handling** — PASS. `ast.parse` SyntaxError → `[]`; malformed tags → `invalid_tags`;
   missing evidence → `not_run`; `git rev-parse` failure → zero-SHA; unreadable files use
   `errors="ignore"`. No unguarded crashes.
3. **Security Basics** — PASS. Sources are parsed as TEXT/AST (never imported/executed); no JS
   eval; paths constrained via `relative_to(project_root)`; output is JSON data (no markup
   injection). (GPT plan-review #9 concern — verified safe.)
4. **Test Quality** — PASS. 22 tests: golden equality, schema validity, three-runner/layer
   coverage, skipped≠covered, orphan, untagged, suite propagation (same-line/multiline/nested),
   multi-tag, malformed tolerance, layer detection, generate_file + update_compliance wiring,
   spec_path rooting. RED-before (build_manifest absent) → green-after.
5. **Performance Basics** — PASS. Single pass per file; bounded discovery in `generate_file`
   (no repo-wide walk); no N+1. Real-monorepo probe: ~25KB manifest, sub-second.
6. **Naming & Structure** — PASS. Cohesive modules; private helpers underscored; public surface
   re-exported from `collectors/__init__.py`.
7. **Affected Boundaries (ADR-024)** — PASS. Producer = `test_links.build_manifest`/`generate_file`;
   consumers = the v2 JSON schema (now) + the TT2 RTM (next). Round-trip probe (producer→file→
   schema-validate→reload) run — see Confidence Calibration.

## Confidence Calibration (Step 3.8 — empirical probes, asymptote heuristic)

Boundary: the human-edited `spec.md` FR table (a serialized-format consumer) + the
producer→file→consumer manifest round-trip.

- **Probes run (5):** (1) external code review found `detect_layer` misclassifies
  `integration-tests/` → **fixed**; (2) BOM + CRLF 4-col spec → parsed, valid; (3) 5-col adopt
  shape → Description read as title (not Layers), valid; (4) non-ASCII (`café ☕`) + whitespace-only
  Layers cell → parsed, valid; (5) `generate_file` producer→file→reload→schema-validate → OK.
- **Findings:** one bug (probe 1, layer detection) → fixed → probes 2–5 clean. Two+ consecutive
  clean probes ⇒ **asymptote reached; boundary calibrated.**
- **Edge cases not probed (acceptable):** duplicate leaf test titles across suites collide on
  `path::title` (fixtures unique; the frozen `fr_tag_grammar` uses the same identity contract — no
  divergence); one-line `describe(...,()=>{it()})` propagation (dominant multi-line form works;
  documented limitation); parameterized tests map to one id (execution-evidence identity is TT-EV's
  scope; TT1 defaults absent evidence to `not_run`).

## Risk-flag note

Classifier flagged `touches_migrations` — a prose-only false positive (the spec mentions
"database"/"migrations" in narrative; the diff has zero SQL / migration files). Overridden;
F11 recomputes from diff-predicates.
