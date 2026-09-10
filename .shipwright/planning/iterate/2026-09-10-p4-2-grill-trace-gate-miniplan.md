# Mini-Plan — P4.2 grill-trace record + completeness gate

Run-ID: iterate-2026-09-10-p4-2-grill-trace-gate
Campaign: req3-09-p4-grill-glossary (sub-iterate P4.2)
Complexity: small (Step 2 classifier); effective complexity: small
(Step 3.4 diff-driven re-check — no risk flags, no diff-driven detector fired;
diff 1344 LOC triggers plan review + code review cascade regardless of
complexity tier)

Implements the design at
`.shipwright/planning/campaigns/2026-07-24-req3-grill-trace-enforcement-DESIGN.md`
verbatim — item (2) of `trg-e9fa7c49` (REQ3.09 Phase 4), project-surface only.

## 1. Files to create/modify

- **New:** `shared/grill-trace-format.md` — the grill-trace record schema
  (evidence/dimensions/glossary_delta/confirmed_by/fit_criterion/terms_used),
  mirroring `shared/context-format.md`'s doc shape.
- **New:** `shared/scripts/tools/grill_trace_format.py` — the data model +
  validation (`parse_trace`) + the sanctioned read API (`read_trace_dir`).
  Split out up front (not after a 300-LOC crossing) since it has two callers
  from day one — the producer and the gate — same precedent as
  `context_md_format.py`.
- **New:** `shared/scripts/tools/write_grill_trace.py` +
  `_write_grill_trace_cli.py` — the producer, one JSON file per elicited
  requirement, `--payload-file` JSON contract (never hand-assembled shell
  args from interview text — P4.1's precedent).
- **New:** `shared/scripts/tools/verify_grill_trace_completeness.py` — the
  completeness gate. Mirrors `verify_iterate_finalization.py`'s `check_*` /
  `CheckResult` pattern (reuses `tools.verifiers.common`). Enforces the four
  closed-vocabulary STOP conditions (blank dimension, greenfield `assumed`,
  undefined term, outcome without fit criterion) plus a distinct,
  separately-named coverage guard (interview ran, zero traces written).
- **New:** `shared/tests/test_grill_trace_format.py`,
  `test_write_grill_trace.py`, `test_verify_grill_trace_completeness.py` —
  direct-call unit coverage (diff-coverage visible) plus one `--payload-file`
  CLI subprocess test mirroring `write_context_term.py`'s shell-injection
  regression test. Includes the required honesty-guard test: a well-formed
  but low-quality trace (one-word definition, terse assumption reason)
  passes every check.
- **Edit:** `plugins/shipwright-project/skills/project/references/interview-protocol.md`
  — add "Capturing the grill-trace — write it per requirement, at
  confirmation", instructing the producer be called at the §9
  confirm-before-acting turn.
- **Edit:** `plugins/shipwright-project/skills/project/references/step-8-completion.md`
  + `SKILL.md` — wire the gate into Step 8's verification list as item 7,
  **blocking** phase completion on a red result (not advisory).
- **Edit:** `docs/hooks-and-pipeline.md` — Artifact Write Matrix: new row for
  the grill-trace producer/gate, and update the `CONTEXT.md` row's
  "no pipeline reader calls it yet" note now that this gate is the consumer.

`plugins/shipwright-adopt/**` is explicitly out of scope (owned by a
different triage item, `trg-1aa5a8ab`) and is not touched.

## 2. Design decisions not open for re-litigation

- The four STOP conditions and the honesty guard are DESIGN.md's, verbatim.
- **Requirement linkage without FR-id joining, but WITH a slug join at
  gate-time (revised post-plan-review):** a grill-trace is self-contained
  at write time (`requirement_text`, `terms_used` declared by the
  interviewer) — it cannot be joined to a spec.md FR row by id, because FR
  ids don't exist yet at interview time (Step 1 precedes Step 6's spec
  generation). The ORIGINAL plan stopped there, with `requirement_key`
  matching the FR row's `Name` column "by convention, not by
  parser-enforced join". External plan review found this left a
  partially-recorded interview (some requirements traced, one silently
  skipped) invisible to the `grill_trace_coverage` guard, which only
  detects the all-or-nothing SKIPPED case. Fixed by adding
  `fr_trace_coverage` (`grill_trace_fr_coverage.py`): at Step 8, once
  spec.md exists, it slugifies every live FR row's `Name` cell with the
  same rule and requires a matching grill-trace `requirement_key` — a
  narrow, local `Name`-column-only parser (deliberately not
  `drift_parsers.parse_fr_table`, which never exposes `Name`), not a
  general FR-table reader. This closes the partial-coverage gap while
  still never needing FR ids at interview time; the join happens later,
  at gate-time, against the one column it needs.
- **`terms_used` is declared, not scanned.** Free-text term extraction from
  `requirement_text` is a judgment call (honesty guard §3) — the gate must
  never make one, so the interviewer declares which terms the requirement
  depends on and the gate does plain set-membership against
  `shared/glossary.md` ∪ `CONTEXT.md`.

## 3. Component hierarchy

N/A — no UI surface.

## 4. Data model changes

None beyond the new JSON record shape (`shared/grill-trace-format.md`),
which is a project-side planning artifact, not a database/schema change.

## 5. Test strategy

- Unit tests on `grill_trace_format.parse_trace`/`read_trace_dir` — shape
  validation, closed-vocabulary rejection, malformed-file surfacing.
- Unit tests on `write_grill_trace.write_trace` — create/update/idempotency/
  rejection-before-any-write, plus one `--payload-file` CLI subprocess test
  for the single-quote shell-injection regression.
- Unit tests on every `verify_grill_trace_completeness.check_*` function —
  one per STOP condition, plus the coverage guard, plus `run_all_checks`
  end-to-end against a real planning tree.
- **Honesty-guard test (required AC):** a structurally-complete but
  low-quality trace (one-word evidence/definition, terse `assumed` reason)
  passes every check except the one genuine completeness gap it also
  contains, proving the gate never judges prose.
- No E2E/browser surface — backend scripts + doc/reference-doc changes only.

## Known limitations / explicitly out of scope

- Only `/shipwright-project`'s surface is wired (this sub-iterate's scope).
  `adopt`/`iterate` are reserved `surface` values in the schema, not wired
  — `trg-1aa5a8ab` owns the onboarding-side trigger.
- The original `grill_trace_coverage` guard is a global "zero traces
  despite an interview having run" check, not a per-FR-row join. As
  revised in §2, it is now PAIRED with `fr_trace_coverage`, a narrow
  `Name`-column-only join added post-plan-review specifically to close
  the partial-coverage gap the global check alone cannot see — this is no
  longer an unaddressed scope decision, it is the shipped design.
