# Optional Capability column in the FR table: reader inventory and tolerance

Run-ID: iterate-2026-11-28-u1a-capability-column (campaign intent-pyramid, unit U1a)

## Decision
1. The FR table may carry a stored `Capability` column directly after `Area` (`fr_table_shape.FR_TABLE_COLUMNS_WITH_CAPABILITY`, `columns_of_canonical_header`). It is optional. Producers (adopt `spec_table`, the greenfield template) still emit the seven-column shape; no value is filled (U2b) and no gate rule reads it (U1b).
2. Every reader takes a spec with and without it. Header-driven readers needed no change; the fixed-shape ones were changed (below).
3. `Capability` is bookkeeping, not normative text: a capability move by the AI does not change an FR's digest (`_baseline_touch_spec`) nor count as a label hit (`_baseline_label_hits`). **Revisit in U2b and U1b**: before U1b's gate reads the column, decide whether a capability reassignment needs a change-history or drift entry, and in U2b whether filled values should be digested.

## Reader inventory (in-repo)
| Reader | Kind | Result |
|---|---|---|
| `lib/fr_table_reader.py` (+ `_fr_table_columns`, `_fr_table_cells`) and every projection of it: `drift_parsers.parse_fr_table`, `spec_parser`, `_backfill_spec_parse`, `fr_change_history`, `_fr_hygiene_*`, `_project_gate_extras`, adopt `spec_document`, compliance `_requirement_parse`, `group_i_rows`, `rtm` | header-driven by name | tolerant, test: `test_fr_table_capability_column.py` + compliance `test_requirement_parse_capability_column.py` |
| `lib/ac_catalog.parse_fr_table`, `lib/fr_scope_check._scan_table`, `tools/grill_trace_fr_coverage.extract_fr_rows` (default index 2 only without a header) | header-driven | tolerant, tested |
| `lib/fr_split_spec` (row move between splits) | header-driven, copies the row's cells | tolerant (a moved row keeps its Capability cell) |
| adopt `traceability_layers` (`find_ambiguous_frs`, `apply_layer_decisions_to_spec`) | header-driven Layers index, `cells[1]` = Area | tolerant, adopt `test_traceability_layers_capability_column.py` |
| adopt `spec_table.render_fr_table` | producer, canonical header | unchanged (emits seven columns) |
| `lib/fr_layer_cell_writer` | FIXED shape: exact canonical header, `len(cells) != len(FR_TABLE_COLUMNS)` | **changed**: accepts either canonical header, column count from the header found, still refuses zero or several headers and a ragged row |
| `verifiers/_baseline_label_hits._spec_lines` | FIXED shape: kept the first five cells ("ID..Description") | **changed**: with Capability at index 2 the first five cells would drop Description; now drops Basis/Layers/Capability by header (legacy first-five only when no header was seen) |
| `verifiers/_baseline_touch_spec.fr_digests` | header-driven ignored columns | **changed**: `capability` added to the ignored columns |
| `verifiers/_baseline_b_packs.catalog` (blind label packs) | FIXED shape: one regex over exactly seven cells | **changed** (found by the code review): rows read through `fr_table_reader.read_fr_rows`; its row set now follows that reader, so packs built earlier are not byte-comparable on non-canonical specs |
| `iterate/references/path-a-feature.md`, `path-b-change.md` ("the row has seven cells") | prompt-level row producers | **changed**: eight cells when the header carries Capability |
| `integration-tests/test_requirements_catalog_contract.py` (`cells[4]` = Description) | positional test reader | **changed**: Description index from the header row (it would have checked Priority) |
| `integration-tests/test_fr_table_shape_convergence.py` (`split("|")[6]` = Basis of the live spec; header literal asserts at lines 77/84) | positional on the LIVE spec | **changed** (found by the doubt review): Basis index from the header, header asserts use `columns_of_canonical_header` |
| `integration-tests/test_requirements_catalog_contract.py` (`[6]` = Layers of the live spec) | positional on the LIVE spec | **changed**: Layers index from the header row |
| `rtm_gate_support`, `design_screens_parser`, `boundary_coverage_report`, `ac_move_map`, `_fr_fold_map_parse` | other tables (RTM, screens, boundaries, move/fold maps) | not FR-table readers |

## Reader inventory (other repos, read only, nothing edited)
- shipwright-webui `server/src/core/mission-context/fold-map.ts` `parseFoldMap`: **positional** (`cols[1]` area, `cols[2]` name, `cols[4]` description). With the column present it would read the CAP id as the name and Priority as the description. Follow-up before U2b fills the column.
- leadwright `tests/lib/spec-ac-parsing.ts` (line ~152: `cells[3]` name, `cells[5]` description, with a leading empty cell): **positional**, same break. Follow-up before U2b.
- webui `scripts/ci/layer_promotion*.py` and leadwright `spec/spec_tabellen.py` were checked: no fixed FR-table column count found.
Rollout rule (external review): the column must not enter a spec those two read until their readers are fixed. Placing the column last would avoid both breaks; kept "next to Area" per the U0 ADR, one constant to change if the operator prefers the end.

## Architecture Review
External (GLM, OpenAI): approve / approve. Internal (architecture-internal-reviewer, opus): approve; worked in: checkable criteria (inventory table, per-reader with/without test), no writer emits the column, external readers are a prerequisite for U2b.

## Internal Plan Review (opus-plan-reviewer)
Medium: path-a/path-b seven-cell instruction and the cells[4] integration test were missed (both fixed, in the table). Low: `_spec_lines` and `_baseline_touch_spec` bookkeeping sets differ (aligned, Status test). Noted, not fixed: `ac_catalog` and `traceability_layers` take Area as the FR title (pre-existing), `grill_trace_fr_coverage._FR_ROW_RE` is dead code.

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| Inventory must exist before code, as an artifact (glm high) | accepted-and-fixed: this table, built first |
| Misspelled header silently read as "no Capability" (glm) | rejected-with-reason: readers resolve columns by NAME and never by count; the one writer accepts exactly the two canonical headers and refuses anything else |
| Ragged rows (glm) | accepted-and-fixed: test for a row with the wrong cell count under the Capability header |
| Digest excludes Capability, forward implication (glm) | accepted-and-fixed: decision 3, revisit in U2b |
| Rollout order for webui/leadwright (glm, openai) | accepted-and-fixed: rollout rule above |
| Closure checklist per reader, distinct values per column, blank Capability keeps digest (openai) | accepted-and-fixed: table above, distinct column values in the fixture, blank-cell digest test |

## Internal Code Review (opus)
High: `_baseline_b_packs.catalog` regex missed (fixed, test). Low: `_spec_lines` now drops exactly the touch digest's ignored columns via the same `IGNORED_COL_RE` predicate (shared on purpose), so both baseline modules agree. The old first-five-cells rule DROPPED a legacy Source column at index 5; the new rule keeps it, to agree with the digest. Re-running `_baseline_label_all.label_all` therefore changes the historical `hit_labels` for Source-era commits.

## Internal Doubt Review (opus)
Medium: label and digest disagreed for a Source-era column after Description (fixed: one predicate, no cut at Description). Low: the shared predicate weakens label independence (accepted, stated in the code comment); a header line inside an FR section is no longer part of the label set (accepted, unreachable: FR tables sit under a heading naming no FR id).

## Prerequisites for U2b (rollout)
Tracked in the campaign file `.shipwright/planning/iterate/campaigns/intent-pyramid/campaign.md`, section "Follow-ups from the 3f-bis reviews", line "U1a (PR #1133)".
Fix webui `fold-map.ts` and leadwright `spec-ac-parsing.ts` first; migrate ALL tables of a spec to the Capability header in one step (the layer writer refuses a spec mixing both headers).

## Known limitation
`_spec_lines` still falls back to "first five cells" for a table whose header it never saw (rows without a preceding header line); such a table cannot carry a Capability column that U1a knows about.

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| Inventory missing from the diff (openai, glm) | rejected-with-reason: the ADR file is untracked at review time (diff of the code commit); it is part of the final commit |
| `_spec_lines` column indices leak past their table (openai, glm) | accepted-and-fixed: kept across headings (a heading does not end a table); reset on a new `| ID |` header or a non-FR table row; a row of another width than its header falls back to the first five cells |
| Headerless 8-cell row falls back to first five cells (glm) | rejected-with-reason: a headerless row cannot be known to carry the column; documented under Known limitation |
| Integration test header detection is lowercase-compared already (glm) | rejected-with-reason: `head` is lower-cased before the compare |
| Downstream follow-ups as prerequisites for introducing the column (openai) | accepted-and-fixed: rollout rule in this ADR |

## Self-Review
1. Spec compliance: pass. 2. Error handling: pass (writer refuses zero/several headers, ragged rows). 3. Security basics: pass. 4. Test quality: pass (one fixture through every reader in both shapes, distinct column values). 5. Performance: pass. 6. Naming and structure: pass. 7. Affected boundaries: pass (spec table producer to readers probed both ways).

## Confidence Calibration
Boundary: FR table (producer shape) -> readers. Probes: 25 with/without cases over 10 readers; blank Capability cell digest equality; heading reset; mixed-header refusal. Finding of probe round 1: label-hit scan leaked columns past its table (fixed, probed again clean twice); round 2: blind label packs regex (found by review, fixed). Not probed: CRLF/BOM specs through the two changed verifiers (the shared reader already has BOM probes).
