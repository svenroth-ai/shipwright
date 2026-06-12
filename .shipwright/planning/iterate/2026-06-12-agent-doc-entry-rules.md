# Iterate Spec — Agent-doc entry rules + budget gate + convention-routing fix

- **Run ID:** iterate-2026-06-12-agent-doc-entry-rules
- **Type:** CHANGE
- **Complexity:** medium
- **Date:** 2026-06-12

## Intent

The always-loaded Layer-1 agent docs (`architecture.md` → `## Architecture
Updates`, `conventions.md` → `## Learnings` + `## Convention Updates`) have
bloated into multi-hundred-char single-line paragraphs because — unlike
`decision_log.md` (F3), which has a hard ≤500-char/field write-time budget —
their entry-writing instructions (F2.md, F3a.md/reflection.md) carry no budget
and the format is unenforced. Detail belongs once in the on-demand ADR /
`.shipwright/planning/adr/` spec folder; the always-loaded docs should carry a
one-line "what + pointer". This is **Iterate 1 of a split** (user decision):
fix the rules + format + enforcement now; compress the existing backlog in a
follow-up iterate.

A correctness conflict was uncovered: `write_decision_log.py` routes
`architecture_impact=convention` → `conventions.md ## Convention Updates`
(compact), but the F11 gate + Group-F detective oracle (`architecture_doc.py`)
require **every** arch-impact run_id — incl. `convention` — in `architecture.md`.
So `F2.md` tells the iterate agent to hand-write verbose convention paragraphs
into `architecture.md`. User decision: reconcile so each impact has ONE home and
**structurally lock it** so writer ↔ oracle ↔ F2.md can't diverge again.

## Scope (Iterate 1)

1. **`architecture_doc.py`** — add `IMPACT_TARGETS` SSoT (`component`/`data-flow`
   → `architecture.md`/`## Architecture Updates`; `convention` →
   `conventions.md`/`## Convention Updates`). Make `missing_entries` /
   `missing_for_run` impact-aware (check each record against its target doc's
   text). Backward-compatible helper retained where practical.
2. **Both oracle callers** — F11 gate `check_architecture_documented`
   (`iterate_checks.py`) + Group-F F5 detective (`group_f.py`) read BOTH docs
   and route per `IMPACT_TARGETS`; messages name the correct section.
3. **`write_decision_log.py`** — consume `IMPACT_TARGETS` (single mapping), so
   the direct-append path and the oracle share one routing source.
4. **Routing drift test** — pins writer behavior + F2.md prose to
   `IMPACT_TARGETS` (forward + reverse), so the routing "can't happen again".
5. **Forward-only entry-budget gate** — new
   `plugins/shipwright-iterate/tests/test_agent_doc_entry_budget.py` (gating in
   CI's per-plugin loop): each dated entry under `## Architecture Updates` /
   `## Convention Updates` / `## Learnings` with date ≥ `_ENFORCED_FROM`
   (2026-06-13, forward-only — today's entries grandfathered) must be ≤ char
   budget. Hermetic unit tests prove the parser+budget discriminate.
6. **Rules** — `F2.md` (compact format + explicit routing + "point to the ADR,
   don't paste the paragraph"), `F3a.md`/`reflection.md` (compact dated one-line
   `## Learnings`; decisions → ADR).
7. **CONTRIBUTING de-dup** — replace the verbatim copy of root `CONTRIBUTING.md`
   in `conventions.md` (the `## Imported from CONTRIBUTING.md` block) with a one-
   line link to the root file (~262 lines removed). Producer fix (adopt
   harvester) noted as follow-up.
8. **Worked examples** — compress 1–2 entries per section via migrate-detail→
   ADR-spec-then-pointer; add this iterate's own compact entry.
9. **`docs/hooks-and-pipeline.md`** — reflect the budget + confirmed routing.

## Acceptance Criteria

- AC1 `architecture_doc.IMPACT_TARGETS` is the single routing SSoT; keys ==
  `REAL_IMPACTS`. `missing_entries` checks `convention` run_ids against
  `## Convention Updates` text and `component`/`data-flow` against
  `## Architecture Updates` text.
- AC2 F11 gate + Group-F detective pass when a `convention` run_id is documented
  in `conventions.md ## Convention Updates` (and fail when absent there), and
  symmetrically for `component`/`data-flow` in `architecture.md`.
- AC3 `write_decision_log._append_architecture_update` routes via
  `IMPACT_TARGETS`; the routing drift test fails if writer/oracle/F2.md diverge.
- AC4 The entry-budget gate flags a synthetic over-budget dated entry (hermetic)
  and passes on the real files (today's entries grandfathered, forward-only).
- AC5 `conventions.md` no longer embeds a verbatim CONTRIBUTING.md copy; it
  links to root `CONTRIBUTING.md`. No test/consumer asserted the embedded copy.
- AC6 F2.md / F3a.md / reflection.md mandate compact dated one-line entries +
  ADR pointers (progressive disclosure).

## Confidence Calibration
- **Boundaries touched:** `architecture_doc.py` (pure oracle consumed by F11
  gate + Group-F detective), `write_decision_log.py` (markdown producer →
  agent_docs), `architecture.md`/`conventions.md` (markdown the framework reads).
  `touches_io_boundary` (producer/consumer of markdown surfaces; `json.load` of
  decision-drops).
- **Empirical probes run:**
  - Oracle impact-aware routing (tmp drops + texts dict): convention→conventions.md,
    component→architecture.md, component-in-wrong-doc→missing, legacy fallback → all pass.
  - Writer producer→file round-trip (`_append_architecture_update` per impact in
    tmp): lands in the IMPACT_TARGETS file+section and NOT the other → pass.
  - Budget parser on a synthetic >600-char dated entry → flagged; old/undated → exempt.
  - Real-file drift test went **RED** on genuine pre-existing local drift
    (`iterate-2026-06-12-utf8-churn-merge` documented in neither doc) → fixed by
    adding the canonical `## Convention Updates` entry → GREEN. (RED proved the
    test discriminates.)
  - Full suites: shared 3173 passed / 12 skipped; iterate 374; compliance 682;
    ruff@0.15.15 clean. Marginal probe (full shared suite) surfaced no new finding.
- **Test Completeness Ledger:** (testable ⇒ tested)
  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | AC1 IMPACT_TARGETS SSoT + impact-aware `missing_entries` | tested | test_architecture_doc.py: test_impact_targets_*, test_missing_entries_convention_routes_*, _component_in_conventions_doc_is_missing |
  | AC2 F11 gate + F5 detective route per impact | tested | test_verify_iterate_finalization.py: _convention_in_conventions_doc_passes, _component_not_satisfied_by_conventions_doc; test_audit_groups_c_f.py: _convention_documented_in_conventions_doc_passes, _convention_legacy_in_architecture_passes |
  | AC3 writer consumes IMPACT_TARGETS + routing drift test | tested | test_agent_doc_entry_rules.py: test_writer_routes_per_impact_targets[*], test_f2_documents_canonical_routing |
  | AC4 forward-only budget gate (flags new, grandfathers old) | tested | test_agent_doc_entry_rules.py: test_over_budget_dated_entry_is_flagged, test_grandfathered_entries_exempt, test_new_entries_within_budget |
  | AC5 conventions.md no longer embeds CONTRIBUTING copy | tested | grep: no test asserts the copy; full suites green post-removal; file 606→308 LOC |
  | AC6 F2 documents compact routing | tested | test_f2_documents_canonical_routing |
  | AC6 F3a/reflection compact-format prose | untestable: requires-manual-visual-judgment | editorial guidance; the machine-checkable claim (F2 routing) is AC6-tested |
  0 testable-but-untested rows.
- **Confidence-pattern check:** asymptote — staged probes (oracle → callers →
  drift → plugin suites → full shared suite) each surfaced + resolved a finding
  (legacy-fallback read bug, removed-message test, real utf8 drift) until the
  marginal probe returned nothing new. Coverage — oracle, both callers, writer,
  drift test, budget gate, F2 doc, real files, both plugin suites, full shared
  suite, lint.
