# Iterate Spec: Freeze traceability contracts + build the panel-verified harness

- **Run ID:** `iterate-2026-07-15-contracts-and-harness`
- **Campaign:** `2026-07-15-traceability-prerequisite` · sub-iterate **P1**
- **Intent:** FEATURE (Path A) · **FR-gate: `spec_impact: none`, `change_type: tooling`** — framework-internal,
  DORMANT contracts + test-only fixtures; no product FR / application behavior is affected (this monorepo has no
  product FRs, and nothing is wired into the pipeline yet). The diff is *additive* new artifacts, no gates / no product logic.
- **Complexity:** medium
- **Source spec:** `C:/01_Development/shipwright/Spec/test-traceability-across-layers.md` §4, §11 (gitignored — absolute path)

## Problem / Goal (Think Before Coding)

The main traceability campaign can only run **autonomously** if every later step can grade its
own work with a machine (a test that goes red, then green). The grading *targets* — the frozen
contracts every collector/gate is written against, and the fixture "answer key" — do not exist
yet. P1 produces **only those targets**: versioned interfaces/schemas + a loadable fixture
package, then has an **independent adversarial panel** (GPT + Gemini + Codex, biased to
disprove) vouch for them. Builder ≠ verifier — the author never self-grades the answer key.

**Explicitly out of scope (YAGNI / Surgical):** no `test_links` collector, no `D-orphan`/
`D-layer` gates, no F11/F0.5 gate logic, no RTM rendering. Those are the (autonomous) main
campaign. P1 writes the *contract the code is graded against*, not the code.

## Alternatives considered (Think Before Coding)

- **A — Build contracts + fixtures now, panel-verify, defer all gate logic (CHOSEN).** Matches
  the campaign's independence requirement: a trustworthy answer key vouched-for by an adversarial
  panel unlocks autonomy for TT1–TT8. Cost: an extra fixture-package + panel round-trip up front.
- **B — Skip the fixtures, let each later sub-iterate invent its own targets.** Rejected: every
  later step would self-grade (builder == verifier), the exact rot the campaign exists to stop;
  no shared answer key ⇒ divergent manifests (R5's "one requirement model" violated).
- **C — Also ship the reference collector/gates in P1.** Rejected: violates "logic-free P1",
  couples the contract freeze to gate correctness, and makes the panel grade behavior instead of
  targets. Contracts must be frozen and independently vouched-for *before* any gate is written.

## Scope / Deliverables

### 1. Frozen contracts (versioned)
- **Manifest v2 JSON Schema** — `plugins/shipwright-compliance/scripts/lib/traceability_schema.json`
  (real JSON Schema, Draft 2020-12) encoding Spec §11 v2: `schema_version`, `collector_version`,
  `source_commit`, `spec_hash`; `requirements` keyed by **namespaced** `spec_path::FR-XX.YY` with
  `{id, spec_path, title, priority, status, required_layers, required_layers_source, tests{layer:
  [{id,path,layer,status,executed,tag_source}]}, coverage}`; `orphans[]` (with `category`),
  `invalid_tags[]`, `untagged_tests[]`. Plus a **golden example** that validates.
- **`@FR` tag grammar** — `shared/scripts/lib/fr_tag_grammar.py` (pure, documented, limited syntax —
  **structured, not naive regex**): the four accepted forms (pytest `@pytest.mark.covers(...)` via
  AST; TS/JS `// @covers FR-XX.YY` comment; Playwright/Vitest native `@FR-XX.YY` tag; Vitest title
  suffix) + malformed → `invalid_tags`. Grammar reference doc + register the pytest `covers` marker.
- **Requirement-model API (one, versioned)** — `shared/scripts/lib/requirement_model.py`: the single
  `(id, title, status, required_layers + provenance, spec_path/namespace)` model that `spec_parser`,
  the compliance `rtm` collector, `test_links`, and Group D will all import (R5). Contract/type only.

### 2. Test-harness / fixture package
`plugins/shipwright-compliance/tests/fixtures/traceability/`:
mini-repos (tagged pytest/Playwright/Vitest + `spec.md` with active **and** removed FRs +
`required_layers` in each provenance state); synthetic base/head diffs (removal, behavior-change,
**pure-refactor** green case); execution-evidence samples (JUnit / Playwright-JSON / Vitest,
**incl. a skipped sample** — R1 "skipped ≠ covered"); a stubbed record/replay LLM adapter;
predeclared-decision fixtures; golden manifest/report snapshots (schema_version-pinned).

### 3. Adversarial verify + completion summary
Panel (`external_review.py` GPT+Gemini + a Codex pass) over each fixture+golden, biased to
disprove, checking the four key properties; loop to clean. End-of-run summary surfaces the
example→expected table + four verdicts + any product decisions to note.

## Acceptance Criteria (from campaign spec)

- **AC1** — versioned manifest v2 JSON Schema + golden example validate; encodes per-test
  status/executed, provenance, orphan categories, invalid_tags, namespaced keys.
- **AC2** — `@FR` grammar documented + pytest `covers` marker registered; reference parser proves
  each accepted form binds to a test and each malformed form → `invalid_tags`.
- **AC3** — fixture package loads (mini-repos, diffs incl. refactor, evidence incl. **skipped**,
  LLM adapter, predeclared decisions, golden snapshots) — each with a smoke test.
- **AC4** — adversarial panel (GPT + Gemini + Codex) passes the four key properties, no open
  finding, run not degraded (real reviews returned).
- **AC5** — completion summary surfaces example→expected + four verdicts + product decisions;
  framework suite green; footprint within compliance lib + shared + new fixtures dir; bloat baseline
  not ratcheted; files ≤300 LOC.

## Affected Boundaries (io_boundary / round-trip)

- **JSON schema ↔ golden example** (round-trip: golden validates; malformed golden fails).
- **Tag grammar text/AST ↔ classified `{valid, invalid_tags}`** (each form parses; malformed rejected).
- **Execution-evidence JSON (JUnit/PW/Vitest) ↔ per-test `{status, executed}`** (skipped ⇒ not `pass`).
- **Manifest JSON ↔ schema** (golden manifest snapshot validates).

## Confidence Calibration

- **Boundaries touched:** JSON-Schema↔golden; tag-grammar text/AST↔`{valid, invalid_tags}`;
  execution-evidence↔per-test `{status, executed}`; manifest↔schema.
- **Empirical probes run:**
  1. Validated golden example + golden manifest against the schema **live** (`jsonschema.Draft202012Validator`),
     with negative controls (`schema_version=1`, non-canonical id, bad `executed` enum, extra prop) — all rejected. ✅
  2. Ran the reference parser over the mini-repo → exactly the 7 expected hits (all 4 `tag_source`s) + 1 `invalid` (`FR-1.3`),
     untagged test omitted — matches the golden. ✅
  3. `pytest --collect-only` on the compliance suite → **no** fixture sample test leaked (collection guard holds). ✅
  4. Full compliance suite **977 passed**; 30 new contract/fixture tests green; ruff@0.15.15 clean; all files ≤300 LOC. ✅
  5. LLM adapter offline replay returns the recorded adjudication; unknown payload → `ReplayError`; a payload with a
     test body → `ValueError` (R4 data control). ✅
- **Test Completeness Ledger** (testable ⇒ tested; 0 untested-testable):

  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | Manifest schema is valid Draft2020-12 (AC1) | tested | `test_schema_is_valid_draft2020` |
  | Golden example validates (AC1) | tested | `test_golden_example_validates` |
  | Golden manifest validates (AC1) | tested | `test_golden_manifest_validates` |
  | Malformed instances rejected: version/id/enum/extra (AC1) | tested | `test_schema_rejects_malformed` |
  | `MODEL_VERSION` == schema `schema_version` const (AC1/R5) | tested | `test_model_version_tracks_manifest_schema_version` |
  | pytest marker binds to fn; multi-id (AC2) | tested | `test_pytest_marker_binds_to_function` |
  | pytest malformed + non-string arg → invalid (AC2) | tested | `test_pytest_marker_malformed_and_nonstring_are_invalid` |
  | non-`covers` decorator ignored (AC2) | tested | `test_non_covers_decorator_ignored` |
  | `// @covers` comment binds to next test (AC2) | tested | `test_covers_comment_binds_to_next_test` |
  | native tag form (AC2) | tested | `test_native_tag_form` |
  | title-suffix form (AC2) | tested | `test_title_suffix_form` |
  | TS malformed → invalid (AC2) | tested | `test_ts_malformed_tag_is_invalid` |
  | canonical-id accept/reject (AC2) | tested | `test_canonical_fr_id`, `test_is_canonical_fr` |
  | all 4 `tag_source`s exercised over the fixture (AC2/AC3) | tested | `test_fixture_repo_exercises_all_four_tag_sources` |
  | fixture binds expected FRs; only `FR-1.3` invalid (AC2) | tested | `test_fixture_repo_binds_expected_frs` |
  | untagged test → no hit (AC2) | tested | `test_fixture_untagged_test_produces_no_hit` |
  | pytest `covers` marker registered (compliance + root) (AC2) | tested | `test_covers_marker_registered` |
  | LAYERS closed vocab / `is_layer` (R5) | tested | `test_layers_are_the_closed_vocabulary` |
  | `namespaced_key` round-trip incl. `::` in namespace (R5) | tested | `test_namespaced_key_round_trips`, `..._splits_on_last_delimiter` |
  | `Requirement.key` / `is_active` (R5) | tested | `test_requirement_key_and_status` |
  | `required_layers_source` vocab (R4) | tested | `test_required_layers_source_vocabulary` |
  | mini-repo loads (spec + 6 test files) (AC3) | tested | `test_minirepo_loads` |
  | diffs load + expected verdicts (removal=block, refactor=green, change=green) (AC3) | tested | `test_diffs_load_with_expected_verdicts` |
  | evidence loads incl. skipped; skipped never reads as pass (AC3/R1) | tested | `test_evidence_loads_including_skipped` |
  | LLM adapter offline replay + `ReplayError` + body refused (AC3/R4) | tested | `test_llm_adapter_replays_offline_and_refuses_bodies` |
  | predeclared decisions load (adopt + orphan file_triage) (AC3) | tested | `test_predeclared_decisions_load` |
  | golden report snapshot present (AC3) | tested | `test_golden_report_snapshot_present` |
  | catalog paths resolve + 4 key_properties (AC3/AC5) | tested | `test_catalog_paths_all_resolve` |
  | **schema enforces skipped≠covered** (coverage ok ⟹ enabled+pass) (AC1/R1) | tested | `test_schema_enforces_skipped_not_covered` |
  | **schema enforces removed ⟹ no live tests** (AC1) | tested | `test_schema_enforces_removed_has_no_live_tests` |
  | evidence index agrees with the RAW Playwright report (AC3/R1) | tested | `test_evidence_loads_including_skipped` (raw↔index cross-check) |
  | diff scenarios are self-contained (linked tests exist in base+head) (AC3/R3) | tested | `test_diffs_load_with_expected_verdicts` |
  | grammar: title tag binds only as a **suffix** (AC2) | tested | `test_title_tag_binds_only_as_a_suffix` |
  | grammar: trailing-junk token → invalid, not a valid prefix (AC2) | tested | `test_trailing_junk_token_is_invalid_not_a_valid_prefix` |
  | grammar: `// @covers` binds only when adjacent / same-line (AC2) | tested | `test_covers_comment_binds_only_when_immediately_adjacent`, `..._on_same_line_...` |
  | grammar: malformed `// @covers` surfaced even when unbound (AC2) | tested | `test_malformed_covers_recorded_even_when_unbound` |
  | exported `TAG_TOKEN_RE` rejects trailing continuations (AC2) | tested | `test_exported_tag_token_re_rejects_continuations` |
  | adapter: a body cannot hide in `candidate_frs` either (R4) | tested | `test_llm_adapter_replays_offline_and_refuses_bodies` |
  | adversarial-panel judgment on the 4 properties (AC4) | untestable → `requires-external-nondeterministic-service` | verified by the panel RUN (GPT+Gemini+Codex), not a unit test |
  | completion-summary content (AC5) | n/a (iterate report artifact, not diff code) | produced at F12 + human-read; suite/ruff/LOC/bloat are gate-verified |
- **Confidence-pattern check:** *asymptote (depth)* — schema tested with **negative controls** (not just "golden passes");
  grammar tested per-form + malformed + non-string + non-`covers`-decorator; evidence tested for the skipped≠pass invariant.
  *coverage (breadth)* — all 4 grammar forms, all 3 provenance states, active+removed FRs, orphan/invalid/untagged, 3 diff
  scenarios (incl. refactor-green), evidence incl. skipped, adapter, decisions, goldens, catalog. *integration composition* —
  **not `cross_component`** (no merge/churn/event-log/hook/phase-validator/campaign machinery touched) ⇒ no integration row
  required; the schema↔golden↔grammar↔evidence contracts still compose end-to-end via the fixture-driven grammar test.

## Adversarial panel (AC4) — verdicts

Panel = **GPT-5.6-terra-pro + Gemini 3.1 Pro** (`external_review.py --mode code`, both
`success:true, degraded:false` every round) **+ Codex** (read-only `codex exec`). Biased to
disprove; looped to convergence over **4 rounds**:

- **R1** (GPT+Gemini) — 7 findings: grammar token under-capture, loose title/comment binding,
  weak evidence/diff tests, unbounded LLM payload, schema `reason` gap → all fixed.
- **R2** (GPT+Gemini+Codex) — schema lacked structural teeth (added `ok⟹enabled+pass`,
  `removed⟹empty-tests`), grammar same-line/malformed-unbound covers, `TAG_TOKEN_RE`
  continuation footgun, `candidate_frs` unbounded, diffs not self-contained. **Codex confirmed
  the 4 properties.** → all fixed.
- **R3** (GPT+Gemini+Codex) — **Gemini clean**; schema per-required-layer coverage + layer-matched
  links, nullable `unmapped` orphan, `test.describe` false-bind, TS-reference limitations
  documented. **Codex again confirmed the 4 properties.** → all fixed.
- **R4** (GPT+Gemini+Codex) — GPT **ship-with-fixes** (down from block): canonical `candidate_frs`,
  forced `auto_write=false`, lexically-clean refactor fixture, + the capstone golden↔parser↔evidence
  test. **Codex: "everything else checked out statically"** (all 4 properties). Gemini confirmed the
  round-3 orphan fix. → all fixed.

**Four key-property verdicts (converged; 3/3 vouched-for):**

| Property | Verdict | How it's now enforced |
|---|---|---|
| skipped ≠ covered | ✅ PASS | golden marks the skipped e2e `MISSING`; schema **rejects** `coverage=ok` without an enabled+pass link (`test_schema_enforces_skipped_not_covered`) |
| removal flagged | ✅ PASS | removed FR is a `confirmed_orphan`; schema **rejects** a removed FR keeping live tests |
| refactor not blocked | ✅ PASS | refactor diff has no spec/FR delta and is lexically token-clean; Codex-confirmed green |
| golden correct | ✅ PASS | golden validates against the v2 schema **and** matches the reference parser + evidence (`test_traceability_golden_consistency.py`); Gemini clean, Codex-confirmed alignment |

**Not degraded:** all GPT+Gemini legs returned real reviews (`degraded:false`); Codex returned
findings each round. **Residual findings are by-design, not defects:** AC4 "panel artifact" + AC5
"completion summary" are the run's own deliverables (this verdicts block + the F12 end-of-run
summary), not code in the diff — the campaign specifies *no special gate artifact*.

## Test plan

Schema-validation tests (golden passes; malformed fails); grammar-parser tests over each accepted +
malformed form; fixture-loader smoke tests (each fixture class loads); evidence-ingestion tests
(skipped ≠ pass). Then the adversarial panel over fixtures/goldens, iterated to clean. **No gate
logic exercised** — P1 only proves the targets are well-formed, loadable, and independently vouched-for.

## Notes / Landmines

- **Framework change** → at finalize: `bash scripts/update-marketplace.sh` + `uv run scripts/check_plugin_cache_sync.py --strict`.
- Fixture `.py` sample tests must **not** be collected by the real pytest suite (they are DATA) —
  guard collection (conftest `collect_ignore`), verify empirically.
- `touches_migrations` from the classifier is a **prose false-positive** — no migrations; recorded in `degraded[]`.
- Keep builder ≠ verifier; the panel is the rigor. No coded go-gate — the human starts the main campaign.
