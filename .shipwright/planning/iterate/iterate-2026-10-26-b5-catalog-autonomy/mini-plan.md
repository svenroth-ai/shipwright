# Mini-plan: B5 catalog and autonomy plumbing (iterate-2026-10-26-b5-catalog-autonomy)

Spec: campaign unit B5 (BRIEF D5, D6, D10). One rule, no special cases.

## Approach
1. `shared/scripts/lib/gate_unattended.py` (new, keeps gate_policy under 300 lines): denylist (11 explicit ids + suffix families `out-of-sequence-continue`, `prereqs-missing`), `validate_unattended` (non-empty str; only orchestrator-approve; not constitution; not denylisted), `unattended_answer_for` (fails closed).
2. `gate_policy.py`: `validate_catalog` calls it; `COVERED_PHASES` += test, changelog (tuple and JSON together); `resolve_gate_policy(..., autonomy=)` adds `unattended_answer`; `should_stop` is unchanged (master/CLI applies the answer after hash + FR-coverage checks); `read_run_config_autonomy`.
3. `resolve_gate_policy.py` CLI: `--autonomy` (default run_config).
4. Catalog JSON: `unattended_answer` on exactly design.preview-approval, design.review-loop-finalize, design.upload-screen-mapping; new gates test.{out-of-sequence-continue, dev-server-port, fix-attempts-exhausted(constitution)}, changelog.{out-of-sequence-continue, version-suggestion, entry-preview}; renderer shows the answer; .md regenerated.
5. Discipline blocks for test (first-actions.md) and changelog (new references/first-actions.md, SKILL.md net-negative lines) so test_phase_gate_discipline_present stays true.
6. D6 consumers: CLI choices, schema enum (+supervised), orchestrator docstring, run SKILL/references (Step 3 = master-side preflight, not a question, for package runs), autonomy-levels, build/test/changelog/deploy prompts, constitution tables. Sites keyed on human presence (phase_gate override allowlist) deliberately stay refusing unattended.
7. Docs: guide.md gate paragraph, hooks-and-pipeline.md phase-gate note.

## Tests
New shared/tests/test_gate_unattended.py (allowlist pinned, denylist pinned, validator rejections, resolver), CLI tests in shared/scripts/tools/tests, plugins/shipwright-run/tests/test_autonomy_unattended.py.

## Alternative approach considered
Hard-coding the three gates in the master: rejected, the catalog is the reviewed SSoT and the validator must be able to refuse a bad entry.
