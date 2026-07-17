# Mini-Plan: arch-doc-refresh-harden

## Approach (chosen)

**Canonical anchor = run_id.** The release aggregator stops maintaining a second
`ADR-NNN` bullet in the curated append docs; the ADR↔run_id mapping stays in
`decision_log.md`. A new forward-only shape-gate makes the bullet grammar
enforceable, and the active tail is normalized once with the gate as the
RED→GREEN oracle.

### Build order (TDD)

1. **Doc content (independent):** swap the System-Overview mermaid for the
   validated portable block; rewrite `## Data Flow` → `### Plugins` + `### GitHub`
   from `scratchpad/dataflow-draft.md`. Preserve the 8 live run_id tokens.
2. **Aggregator surgical guard + canonicalize writer (RED→GREEN):**
   - `_append_architecture_update` (write_decision_log.py:262): emit the full
     canonical form `- **ADR-NNN** (date): <Impact> — <summary>. → decision_log
     (ADR-NNN)`. Update `shared/tests/test_arch_update_writer_format.py`.
   - `aggregate_decisions.aggregate` (L181-188): SKIP the doc-append when the
     drop's run_id is already documented in the target section (iterate dup gone);
     keep a fallback append for the undocumented-run_id edge (no new orphans).
   - **Do NOT touch `append_decision`** (L319) — the direct build/plan/project/
     test/deploy appender is single-entry, non-dup, must keep working.
   - Unit tests: folded documented drop → 0 new curated-doc lines; `append_decision`
     → exactly 1 canonical bullet.
3. **Shape-gate (RED→GREEN):** new SSoT `shared/scripts/lib/agent_doc_shape.py`
   reusing `agent_doc_budget.iter_entries/entry_anchor/entry_date`; canonical rule
   over the **two `…Updates` sections only** (exclude `## Learnings` — date-first
   grammar): anchor ∈ {`**iterate-…**`, `**ADR-NNN**`} (reject Campaign/sub_iterate/
   free-text), has date, has `→` pointer; `enforced_from=2026-06-28`; undated/
   pre-cutoff grandfathered. → repo-agnostic CLI `tools/check_agent_doc_shape.py`
   (UTF-8 stdout) → F11 wrapper `tools/verifiers/agent_doc_shape_check.py`, a
   `check_...` call appended to the `run_all_checks` list + import. Unit tests per
   malformation + canonical pass; a membership drift-guard test (house convention);
   monorepo full-corpus pytest. **Derive the exact tolerances (Impact-word set,
   em-dash, suffix) from the real corpus so no legit line false-fails.**
4. **Normalize active tail — BOTH docs:** `architecture.md`: delete 31 `ADR-NNN`
   dups + convert orphan `ADR-327` → `iterate-2026-07-15-execution-evidence`;
   `conventions.md`: delete 21 `ADR-NNN` dups. Leave `→ archive`/pre-cutoff. Gate
   GREEN full-corpus; re-check ≤600 budget + 8 tokens.
5. **Spec of record:** `references/F2.md` (keep the 4 routing substrings; state
   the no-dup rule), `architecture.md` + `conventions.md` inline headers,
   `docs/hooks-and-pipeline.md` (register the verifier).
6. **Compose + verify:** test that `run_all_checks` actually invokes
   `check_agent_doc_shape` (composition proof). `cross_component` will NOT fire
   from the diff (verifier meta-tooling excluded); if it fires from Run-Summary
   prose, override (prose-only FP) + record in `degraded[]`. Full pytest suite;
   external review (GPT+Gemini); cache-sync.

### Key files
- `.shipwright/agent_docs/architecture.md` (mermaid, Data Flow, tail, header)
- `.shipwright/agent_docs/conventions.md` (Convention-Updates tail dedup, header)
- `shared/scripts/tools/write_decision_log.py` (canonicalize `_append_architecture_update`)
- `shared/scripts/tools/aggregate_decisions.py` (skip-if-documented guard)
- **new** `shared/scripts/lib/agent_doc_shape.py`, `.../tools/check_agent_doc_shape.py`,
  `.../tools/verifiers/agent_doc_shape_check.py`
- `shared/scripts/tools/verifiers/iterate_checks.py` (import + append to run_all_checks)
- **new** `shared/tests/test_agent_doc_shape.py`, `shared/tests/test_agent_doc_shape_check_wiring.py`
- `shared/tests/test_arch_update_writer_format.py` (update for canonical writer)
- `plugins/shipwright-iterate/tests/test_agent_doc_entry_rules.py` (extend, or new file)
- `plugins/shipwright-iterate/skills/iterate/references/F2.md`, `docs/hooks-and-pipeline.md`

## Alternative considered (rejected)

**Option 2 — canonical = ADR-NNN, aggregator rewrites the run_id bullet in-place.**
At release, find the change's `- **<run_id>** …` line and rewrite the anchor to
`ADR-NNN` (preserving Impact + sentence). Rejected: fragile release-time string
surgery on always-loaded Layer-1 context (locate exact line, preserve rich
sentence not the terse summary, keep ≤600 budget, handle not-found / already-
compacted / worktree-vs-main), and it fights the enforcement machinery, which
already matches on the run_id token. Option 1 is a safe subtraction; the ADR
number remains one `Run-ID:` lookup away in `decision_log.md`.

## Risk / safety
- HARD: preserve the 8 live component/data-flow run_id tokens (drift/F5/F11).
- HARD: every dated append-section bullet ≤ 600 chars.
- Registry SSoT rule: new verifier needs forward+reverse drift protection.
- `cross_component` likely fires (verifier machinery) → integration test, non-dodgeable.
- Framework-plugin edits → cache-sync at the end or runtime never sees them.
