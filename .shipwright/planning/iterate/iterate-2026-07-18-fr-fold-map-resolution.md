# Iterate — FR-Fold-Map resolution for tagged tests

- **Run ID:** `iterate-2026-07-18-fr-fold-map-resolution`
- **Type:** CHANGE · **Complexity:** medium · **Spec Impact:** MODIFY
- **Risk flags:** `touches_shared_infra`, `touches_io_boundary` (manifest JSON + schema)

## Problem (plain language)

A test can be labelled with the requirement it proves, e.g. `@covers("FR-01.44")`.
Later, a spec clean-up can **fold** a fine-grained requirement into a broader one
("terminal appearance" folded into "embedded terminal"). The spec records this in a
`## FR-Fold-Map` table so old references still resolve.

Today the traceability machinery ignores that table. It only looks at the surviving
requirement rows. So the moment a fold happens, every test labelled with a folded id
is read as *pointing at a requirement that does not exist* → `fr_absent` →
`confirmed_orphan` → the **D-orphan** audit check FAILs at MEDIUM.

**Evidence.** shipwright-webui #287 (`fr-taxonomy-regroup`) folded 66 FRs into 29
capability FRs and recorded 37 folds in a new `## FR-Fold-Map` table. When the
traceability retrofit (#289) landed on that spec, 22 tagged FRs were folded → **419
orphans** and D-orphan failed. It was worked around by hand-remapping every tag to its
survivor. Ref: webui `.shipwright/compliance/test-traceability-coverage-delta.md`
follow-on #5.

The result is a **hard coupling between two independent good practices**: keeping test
labels fine-grained, and periodically raising the spec to capability altitude. Doing
both breaks the build. That is the defect.

## Goal

A tag on a folded id resolves through the fold-map to its surviving requirement and
counts as coverage of that survivor. Granular tags survive a later taxonomy fold
instead of hard-breaking. A tag that genuinely points nowhere still orphans.

## Non-goals

- Rewriting/normalising tags in source (the fold-map resolves them; it does not edit them).
- Changing the frozen `@FR` tag grammar or the un-namespaced fan-out limitation.
- Authoring a fold-map for this monorepo (it has none; the change is inert here by design).

## Design

### One shared parser (no fork)

New `shared/scripts/lib/fr_fold_map.py`, alongside the existing frozen shared contracts
`fr_tag_grammar` / `requirement_model`. Both consumers use it: the compliance collector
via `load_shared_lib` (ADR-045-safe), the shared backfill engine via flat import.

Format parsed (as shipped by webui #287) — a `## FR-Fold-Map` section whose table rows
carry `folded → survivor`; ids may be backticked:

```markdown
## FR-Fold-Map

| Folded ID | → Survivor | Reason | Was (original name) |
|-----------|-----------|--------|---------------------|
| `FR-01.44` | `FR-01.28` | delta | Embedded terminal appearance |
```

### Resolution rule — a FALLBACK, never an override

For a tagged id `X`:

1. `X` matches an **active** requirement → bind there. *Unchanged behaviour; a repo with
   no fold-map, or a tag on a live FR, is byte-identically unaffected.*
2. Else walk the fold-map transitively to a survivor `S`; if `S` is **active** → bind the
   link to `S` and record `resolved_from: X` on the link.
3. Else → orphan, exactly as today (`fr_removed` / `fr_absent`).

This ordering is the safety property: the fold-map can only ever *rescue* a tag that
would otherwise orphan. It can never redirect a tag away from a live requirement.

### Fail-closed edges (each gets a test)

| Edge | Behaviour |
|---|---|
| Chain `A→B→C` | walks to the first **active** id it reaches, through removed/absent intermediates |
| Cycle `A→B→A` | **unresolved** → orphan (never hangs; visited-set + depth cap); one defect per loop |
| Self-fold `A→A` | ignored as an edge; recorded as a defect |
| Survivor is `removed` | **unresolved** → orphan `fr_removed` (classified from the *terminal*, so the operator is not told "this FR never existed"); defect `removed_survivor` |
| Survivor absent from table | **unresolved** → orphan `fr_absent`; defect `dangling_survivor` |
| Folded id ALSO an active row | active row wins (rule 1) and keeps its own coverage obligation; defect `folded_id_still_active` |
| **Folded id ALSO under `## Removed`** | **no rescue** — retirement beats folding; orphan `fr_removed`; defect `folded_id_removed` |
| Two specs fold the same id differently | edge **dropped**, defect `conflicting_survivor` — ambiguity is never guessed |
| Unparsable row (either or BOTH ids malformed) | edge skipped, defect `unparsable_row` |

### Hardening found while designing / reviewing (in scope, deliberate)

1. **Both FR-table parsers skip the fold-map section.** `_requirement_parse.parse_requirements`
   and `backfill_scan.parse_frs` parse *any* canonical-looking table row. webui's fold-map
   only escapes this because its ids happen to be backticked; an author writing the same
   table **unbackticked** would silently resurrect every folded id as an *active
   requirement demanding its own test coverage* — a large false-red.

2. **Retirement beats folding** (adversarial review). An FR under
   `## Removed Requirements` is never fold-rescued. Without this, moving an FR to Removed
   **and** adding one fold row in the same commit would file a test still carrying the
   dead tag as a link on the survivor, and the F11 removal gate
   (`_layer_coverage_removal._classify_at_head`) would read that as *"retargeted to a live
   FR"* — repealing its own load-bearing invariant (a clean retarget REPLACES a dead tag,
   it must not merely supplement it) via a two-line markdown edit. Genuine folds are
   unaffected: the real pattern drops a folded id from the table entirely, so it is
   *absent*, not *removed*. The contradiction is reported as `folded_id_removed`.

3. **`_lib_loader` resolves the shared lib by PRECEDENCE, not presence.** `lib` is a
   regular package in every plugin, so `import lib.X` binds to the first `lib` on
   `sys.path`; the loader only inserted `shared/scripts` *when absent*, which is a no-op
   once another plugin's `scripts` dir sits ahead of it. Latent (early call sites cached
   their module while ordering still favoured shared) until this change loaded a new
   shared module later in a session — surfacing as `ModuleNotFoundError: lib.fr_fold_map`
   in the adopt suite. Front-precedence is now scoped to the import and `sys.path` is
   restored, so it can never shadow a plugin's own `lib` afterwards.

Items 2 and 3 are blocking correctness for this change (2 closes a false-green it would
otherwise introduce; 3 is required for the shared-parser design to work at all), so both
belong here rather than in a follow-up iterate.

### Module extractions (mechanical, no behaviour delta)

Four cohesive clusters moved to their own modules to stay under the ADR-096 300-LOC cap,
each re-exported so every historical import path still resolves: `_fr_fold_map_parse`
(markdown mechanics), `_backfill_spec_parse` (`FR` + `parse_frs`), `_backfill_title_sim`
(the fuzzy title leg), `_group_d_render` (finding renderers).

### Artifact + schema (additive, optional)

`test-traceability.json` gains two optional top-level keys — `fold_map` (the resolved
edge set actually in force) and `fold_defects` (the hygiene diagnostics) — and
`testLink` gains an optional `resolved_from`. All optional, so an older manifest still
validates; `additionalProperties:false` requires the schema to declare them.

### D-orphan

Surfaces `fold_defects` as a LOW hygiene line (same treatment as `invalid_tags`): a
corrupt fold-map silently under-resolves tags, so it must not be invisible. Orphans that
fold-resolution could not rescue keep their MEDIUM.

### Backfill engine

`build_ctx` accepts the fold-map; an existing tag on a folded id is counted as
**honoured coverage of the survivor** instead of a confirmed orphan — so the retrofit
neither reports a false orphan nor proposes a redundant re-tag.

## Mini-plan

1. `shared/scripts/lib/fr_fold_map.py` — parse · merge · resolve · audit (TDD first).
2. Fold-map section skip in both FR-table parsers.
3. Collector: fold-fallback binding + `fold_map` / `fold_defects` / `resolved_from`.
4. `traceability_schema.json`: three additive optional declarations.
5. D-orphan: `fold_defects` hygiene surfacing.
6. Backfill: fold-aware honoured-tag resolution.
7. Tests: unit (parser/resolver edges) + integration (golden mini-repo with a fold) +
   round-trip boundary probe (manifest survives write→read→schema-validate).
8. Docs: `docs/hooks-and-pipeline.md` artifact matrix, conventions bullet, ADR drop.

**Alternative considered — normalise tags at scan time instead** (rewrite `@FR-01.44` →
`@FR-01.28` in source). Rejected: it destroys the finer-grained provenance the tag
carries, mutates user source on every fold, and is exactly the manual workaround webui
had to do. The fold-map is the spec's own declared alias table; resolving through it is
the non-destructive fix and keeps one source of truth.

## Acceptance Criteria

- **AC1** A tag on a folded id whose survivor is active binds to the survivor and
  produces no orphan; the link records `resolved_from`.
- **AC2** A tag on a live FR is unaffected by the presence of a fold-map (no override).
- **AC3** Cycle, self-fold, dangling survivor, removed survivor, conflicting cross-spec
  edge, and unparsable row each fail closed (orphan preserved) and are recorded as
  fold-map defects rather than silently swallowed.
- **AC4** Neither FR-table parser treats a fold-map row as an active requirement, whether
  or not its ids are backticked.
- **AC5** The manifest with fold data round-trips: write → read → v2-schema-valid; an
  older manifest without the new keys still validates.
- **AC6** D-orphan surfaces fold-map defects as a LOW hygiene finding and no longer
  fails on a fold-resolvable tag.
- **AC7** The backfill engine counts a folded-id tag as honoured coverage of the survivor
  (no confirmed orphan, no re-tag proposal).

## Affected Boundaries

- `test-traceability.json` producer→consumer contract (collector → D-orphan / RTM / WebUI)
- `traceability_schema.json` (frozen v2 contract; additive-only change)
- spec.md `## FR-Fold-Map` section (new parsed surface)
- backfill report JSON (orphan counts change when a fold-map is present)

## Confidence Calibration

- **Boundaries touched:**
  - `test-traceability.json` producer→consumer contract (collector → D-orphan / D-layer / D1 / RTM)
  - `traceability_schema.json` v2 (additive-only; re-validated on READ by `_group_d_manifest`)
  - spec.md `## FR-Fold-Map` (new parsed surface, consumed by two independent parsers)
  - backfill report JSON (`already_tagged` / orphan counts)
  - `sys.path` / `sys.modules` manipulation in `_lib_loader` (cross-plugin import boundary)

- **Empirical probes run:**
  1. *Does a fold-less repo really emit a byte-identical manifest?* — asserted directly
     (`test_a_repo_without_a_fold_map_emits_NO_new_keys`): no `fold_map`, no `fold_defects`,
     no `resolved_from` on any link. This is what keeps a committed churn artifact from
     diffing on every regen for every project that has no folds.
  2. *Round-trip through disk* — manifest written → re-read → equal and still v2-schema-valid.
  3. *Do the two consumers agree?* — the same fixture repo driven through BOTH the backfill
     engine and the real TT1 collector (in a clean subprocess, crossing the ADR-045 `lib`
     boundary); both reach the same verdict for a healthy fold and for a dangling one.
  4. *Does the full suite still pass?* — F0 GREEN, 18/18 units.
  5. **Probes that FAILED and changed the code (×3):** (a) parse-time defects (self-fold,
     unparsable row, conflicting survivor) never reached the manifest — only audit-time ones
     did; (b) one 2-edge cycle emitted 3 defects, burying the actionable one; (c) the full
     suite surfaced `ModuleNotFoundError: lib.fr_fold_map` from the adopt plugin — a latent
     `sys.path` **precedence** bug in `_lib_loader` (it ensured presence, not precedence)
     that this change was the first to trip. Each is now pinned by a regression test.
  6. **Review round — 3 independent passes, 9 further real defects (all fixed):** the
     adversarial doubt-reviewer found the one that mattered — the change repealed the F11
     **removal gate's** invariant, so removing an FR plus one fold row would dismiss its
     still-dead-tagged tests (ledger 22). Also: orphan reason misnamed a retired survivor
     as `fr_absent` (24); auditing each edge's immediate target false-flagged a healthy
     chain (25); `conflicting_survivor` content was spec-order-dependent and duplicated
     (26); a row with both ids malformed was silently swallowed (27); the cycle skip
     swallowed `folded_id_still_active` (28). The spec-reviewer caught that my AC4 backfill
     test was **vacuous** — backticked ids are skipped by the FR regex anyway, so it passed
     with the feature removed; replaced with an unbackticked case and **mutation-verified**
     (30). It also caught the link-aliasing fix shipping untested (29).
  7. *Does the E2E itself hold up?* — the first version of the monorepo regen check
     imported the collector in-process and failed in the full suite for the very reason
     this iterate fixed (`lib` precedence), while also leaking a `sys.path` entry into
     every later test. Both E2E cases now run in a subprocess, like production.

- **Test Completeness Ledger:** 0 testable-but-untested.

  | # | Behaviour | Disposition | Evidence |
  |---|-----------|-------------|----------|
  | 1 | Folded tag binds to survivor, no orphan, `resolved_from` recorded (AC1) | `tested` | `test_folded_tag_binds_to_survivor_and_produces_no_orphan`, `test_D_orphan_passes_on_a_fold_resolved_tag` |
  | 2 | Live-FR tag never redirected by a fold-map (AC2) | `tested` | `test_a_live_fr_tag_is_not_redirected_by_a_fold_map`, `test_active_folded_id_keeps_its_own_coverage_and_ignores_its_fold_entry` |
  | 3 | Transitive chain resolves to active terminal, through removed intermediates | `tested` | `test_transitive_chain_resolves_to_the_final_active_survivor`, `test_chain_resolves_through_a_REMOVED_intermediate_to_an_active_terminal` |
  | 4 | Cycle fails closed + terminates (AC3) | `tested` | `test_cycle_fails_closed_and_terminates`, `test_depth_cap_terminates_a_long_chain` |
  | 5 | Dangling / removed survivor fails closed (AC3) | `tested` | `test_dangling_survivor_fails_closed`, `test_chain_whose_terminal_is_removed_fails_closed`, `test_audit_flags_survivor_that_is_removed` |
  | 6 | Conflicting survivor (cross-spec AND intra-spec) drops the edge (AC3) | `tested` | `test_conflicting_survivors_drop_the_edge_fail_closed`, `test_intra_spec_duplicate_conflicting_rows_drop_the_edge` |
  | 7 | Unparsable / self-fold row recorded, not swallowed (AC3) | `tested` | `test_unparsable_row_is_recorded_not_swallowed`, `test_self_fold_is_dropped_and_recorded` |
  | 8 | Defect vocabulary is closed + every emitted kind declared | `tested` | `test_every_emitted_defect_kind_is_in_the_closed_vocabulary` |
  | 9 | One cycle = one defect (no per-member/per-tag amplification) | `tested` | `test_a_cycle_does_not_also_spawn_dangling_survivor_noise`, `test_two_independent_cycles_yield_two_defects`, `test_edges_outside_a_cycle_are_still_audited_normally` |
  | 10 | Fold rows never parsed as active requirements, backticked or not (AC4) | `tested` | `test_fold_rows_never_become_active_requirements[both params]` |
  | 11 | Section bounds: sibling heading closes, sub-heading does not, repeats all parsed, EOF | `tested` | `test_a_following_requirement_table_is_not_swallowed_by_the_section`, `test_a_deeper_subheading_does_not_truncate_the_section`, `test_repeated_fold_map_sections_are_all_parsed`, `test_section_at_end_of_file_without_a_closing_heading` |
  | 12 | Manifest with fold data is v2-schema-valid; round-trips (AC5) | `tested` | `test_manifest_with_fold_data_is_v2_schema_valid`, `test_manifest_round_trips_through_json_unchanged` |
  | 13 | No-fold repo emits no new keys — byte-identical (AC5) | `tested` | `test_a_repo_without_a_fold_map_emits_NO_new_keys` |
  | 14 | D-orphan surfaces fold defects as LOW hygiene; MEDIUM reserved for real orphans (AC6) | `tested` | `test_fold_defects_alone_are_LOW_hygiene_not_a_medium_failure`, `test_unsafe_edges_keep_the_orphan_and_record_a_defect` |
  | 15 | Backfill honours a folded tag as survivor coverage, proposes no re-tag (AC7) | `tested` | `test_folded_tag_is_honoured_as_coverage_of_the_survivor`, `test_without_a_fold_map_the_same_tag_is_a_confirmed_orphan` |
  | 16 | Backfill and collector agree on the same fold (cross-consumer) | `tested` | `test_backfill_and_collector_agree_on_the_same_fold[healthy, dangling]` |
  | 17 | Parser never raises on degenerate input | `tested` | `test_parser_never_raises_on_degenerate_input[5 params]` |
  | 18 | Defects are deterministically ordered regardless of merge order | `tested` | `test_defects_are_deterministically_ordered_regardless_of_merge_order`, `test_audit_output_is_sorted_and_stable` |
  | 19 | Defect carries line number + bounded raw; lowercase id is a loud defect | `tested` | `test_defect_carries_line_number_and_bounded_raw`, `test_lowercase_id_is_a_LOUD_defect_not_a_silent_normalisation` |
  | 20 | `load_shared_lib` wins on path PRECEDENCE, restores path, never shadows a plugin lib | `tested` | `test_lib_loader_precedence.py` (7 cases) |
  | 21 | Module extractions preserve every existing import path | `tested` | full F0 suite GREEN (4280+ shared, 1155 compliance) — `parse_frs`/`FR`/`tokenize`/`jaccard` still import from their historical modules |
  | 22 | **Retirement beats folding** — a removed FR is never fold-rescued, so the F11 removal gate stays HARD | `tested` | `test_removing_an_fr_and_folding_it_does_NOT_rescue_its_dead_tags`, `test_a_removed_folded_id_is_not_rescued_by_the_backfill_engine`, `test_an_id_under_removed_requirements_is_reported_as_a_contradiction` |
  | 23 | A genuinely folded (absent) id is still rescued — the guard is not over-broad | `tested` | `test_a_genuinely_folded_id_absent_from_the_table_is_still_rescued` |
  | 24 | Orphan reason names the terminal (`fr_removed` vs `fr_absent`) | `tested` | `test_a_chain_ending_at_a_REMOVED_survivor_reports_fr_removed`, `test_a_chain_to_nowhere_still_reports_fr_absent` |
  | 25 | A healthy chain through a dead intermediate emits NO defect (no false-red) | `tested` | `test_a_chain_through_a_removed_intermediate_resolves_with_NO_defect` |
  | 26 | `conflicting_survivor` content is merge-order-independent; 3 rivals → 1 defect | `tested` | `test_conflicting_survivor_content_is_identical_in_either_merge_order`, `test_three_specs_claiming_one_id_yield_ONE_conflict_defect` |
  | 27 | A row with BOTH ids malformed is reported, and the real header still is not | `tested` | `test_a_row_with_both_ids_malformed_is_still_reported`, `test_the_real_header_row_is_still_not_a_defect` |
  | 28 | A cycle does not swallow the folded-id status diagnostic | `tested` | `test_a_cycle_does_not_swallow_the_folded_id_status_diagnostic` |
  | 29 | One test carrying a folded AND a direct tag → one link, direct provenance, no cross-node aliasing | `tested` | `test_a_folded_and_a_direct_tag_on_one_test_yield_one_link_with_direct_provenance` |
  | 30 | Both parsers' fold-skip is non-vacuous (unbackticked table) | `tested` | `test_an_UNBACKTICKED_fold_table_is_not_read_as_live_requirements` (**mutation-verified**: disabling the skip fails exactly this test) |

- **Confidence-pattern check:**
  - *Asymptote (depth):* the resolver is exercised past the happy path into each way it can
    fail — cycle, self-fold, over-deep chain, dangling terminal, removed terminal,
    intra- and cross-spec conflict, malformed and lowercase ids, degenerate input. Three
    separate probes found real defects and changed the code, which is the signal that the
    depth was real rather than confirmatory.
  - *Coverage (breadth):* both consumers of the contract are tested independently AND
    against each other; both FR-table parsers are covered; the artifact is checked at the
    schema, round-trip, and no-change-when-unused levels.
  - *Integration composition:* `cross_component` does **not** fire (no merge/churn resolver,
    hook, phase validator, or campaign machinery in the diff — the touched files are a
    collector, an audit detective, and shared libs). Composition is nonetheless proven
    where it matters: ledger row 16 runs one fixture through both consumers across a real
    process boundary, which is the only place the two could have drifted.
