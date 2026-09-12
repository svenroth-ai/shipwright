# Mini-Plan — e2-checks-project-elicitation

## Goal

Close the 9 `prompt-only (mechanisable)` lines the REQ-3 AC-evidence ledger
names under FR-01.02 (`/shipwright-project`, 6) and FR-01.16 (guided
requirement elicitation, 3), excluding FR-01.16's 5 judgement lines (e6's).
Per campaign decision D7, no line may become an LLM-judgement gate — each
either gets a deterministic check + test, or is explicitly downgraded to
`judgement` with a drift test and a reason.

## Approach

**FR-01.02 (`/shipwright-project`)** — new
`shared/scripts/tools/verifiers/_project_gate_extras.py` (4 pure
`GateResult` functions) + `_project_gate_wiring.py` (filesystem-facing
adapters), wired into `project_checks.run_project_checks()` — the same
dispatcher `update-step --step project` already blocks on:

- **#4 + #15 merged** — `basis_forbids_assumed`: no active FR row's `Basis`
  cell may read a bare `assumed` in a greenfield spec. The ledger itself
  flagged #4 (absolute ban) and #15 (allow-with-settlement) as a
  self-contradiction from the 2026-07-25 retro pass; rather than build a
  second, semantic "does this AC name a settlement" oracle (no deterministic
  aboutness check exists), this extends P4.2's already-shipped, already
  absolute grill-trace-layer ban (`check_greenfield_assumed`) to the FR-row
  layer — one mechanism, not two competing rules.
- **#5** — `criteria_free_of_implementation_detail`: reuses I1's own
  detector (`fr_hygiene_detectors.violations` — code-symbol/file-path/
  ADR-number/iterate-slug/HTTP-verb) against every active FR's acceptance
  CRITERIA text, not just the Name column I1 already covered.
- **#10** — `no_empty_split`: a declared split's `spec.md` must carry ≥1
  active FR row — the buildable floor under "cohesive parts"; topical
  coherence across a multi-row split stays a judgement call, no oracle.
- **#11** — `starting_guidance_present`: CLAUDE.md + the three agent_docs
  files Step 7 writes must exist AND be non-empty (existence-only was the
  gap); skipped for extension scope.
- **#8 split, not closed outright** — the floor (an ADR exists for the
  phase) was ALREADY enforced by the pre-existing C4 check
  (`check_c4_decision_log_has_phase_adr`), just never cited on this row.
  The link-BACK half (a specific ADR traceable from the specific
  requirement) has no addressable field in the FR-row schema — downgraded
  to `prompt-only (judgement)` with a new drift test pinning
  `requirement-elicitation.md` §7/§8's "linked from the requirement" / "an
  ADR, linked" instructions verbatim.

**FR-01.16 (guided elicitation)** — discovered during the walk that all
three rows (C, #3, #6) were **already substantially closed** by campaign
`req3-09-p4-grill-glossary` (trg-e9fa7c49 → trg-9c9c0792, dismissed
2026-09-10, one day before this run) — the ledger's own status cells simply
hadn't been updated when that work merged:

- **C** (context completely covered) — `verify_grill_trace_completeness
  .check_blank_dimension` + `check_grill_trace_coverage` (P4.2). Cite only.
- **#3, split** — the "is a captured term defined anywhere" half is
  `check_undefined_term` (P4.2), enforced/tested. The "does the NEW meaning
  collide with an EXISTING one" half (**3b**) stays judgement — comparing
  two meanings is reading comprehension, no oracle — drift-tested by P4.4's
  `test_module_pins_the_glossary_cross_check_trigger_by_sentence`.
- **#6** (every dimension answered/honestly marked) —
  `check_blank_dimension` + `check_greenfield_assumed` (P4.2). Cite only.

Nothing new was built for FR-01.16 — only the ledger's stale status cells
needed correcting, plus discovering and recording the #3/#3b split.

## Risk / boundaries

All four new project-gate functions are read-only checks over the
project's own `spec.md`/config/agent_docs artifacts, wired into an
existing verifier dispatcher (`project_checks.run_project_checks`) that
already blocks `update-step --step project` on other checks — no new
runtime/production code path, no new I/O boundary beyond reading files the
dispatcher already reads. `touches_io_boundary` fired on the diff-risk
re-check (file reads over spec.md/CLAUDE.md/agent_docs), consistent with
that existing shape, not a new kind of boundary.

Two existing test fixtures (`shared/tests/test_verifiers_project.py`'s
`seed_canon_project`, `plugins/shipwright-run/tests/
test_phase_validators_project.py`'s `_seed_basic_project`) wrote a
spec.md with no FR table at all and no CLAUDE.md/agent_docs — both needed
a minimal, valid FR row (+ `scope: "extension"` to skip the new
guidance check where CLAUDE.md/agent_docs were never modeled) so the new
gates didn't themselves redden pre-existing happy-path fixtures.

## Out of scope (recorded on the ledger, not built)

- FR-01.02 #8b (ADR link-back to a specific requirement) — no schema field
  exists to check it; drift-tested only, per D7's abort condition.
- FR-01.16 #3b (glossary-term collision comparison) — reading
  comprehension, no oracle; drift-tested only (already shipped by P4.4).
- FR-01.16's 5 judgement lines (#1, #2, #4, #5's record half, #7) are
  e6's, explicitly excluded by this sub-iterate's own spec.
