# Mini-plan: tag-gate follow-up

Run ID: iterate-2026-10-08-tag-gate-followup

## Files
- edit `shared/scripts/lib/fr_tag_grammar.py` - `_TEST_DECL_RE` accepts `.each(table)` / ``.each`table` `` before the title.
- edit `plugins/shipwright-compliance/scripts/lib/collectors/_file_tags.py` - fold a wrapped `.each` table onto the title line.
- new `shared/scripts/tools/verifiers/_tag_binding_ts_lex.py` - lexer (strings, templates, comments, regex literals, JSX).
- edit `_tag_binding_ts.py` (use the lexer; callee in the digest; `.each` declaration), `_tag_binding_identity.py` (pass path),
  `_tag_binding_py.py` (decorators in the digest, minus `covers`).
- edit `shared/scripts/tools/verifiers/_layer_coverage_regen.py` - cache the base prune set, build head with it.
- edit `shared/tests/test_finalization_claims_scenario.py` - `Gate(ok, detail, skipped)` + `EXPECTED_SKIPS`.
- tests: new `shared/tests/test_tag_binding_followup.py`, additions to `plugins/shipwright-compliance/tests/test_file_tags.py`,
  one rewritten case in `test_tag_binding_core.py`.
- spec: FR-01.11 AC42.

## Work breakdown
1. U11 skip-set (test only). 2. Lexer + TS digest (tests: regex, JSX, rename). 3. `.each` in grammar + joiner (tests: unit + collector).
4. Python decorators in the digest (tests: skip/parametrize/covers/class). 5. Base prune set (real-git test both directions).
6. Run all four affected pytest roots, ruff, `verify_local.py`.

## Test strategy
Real git + real collector for the boundary cases; pure digest cases for the lexer. All tagged `FR-01.11/AC42`.

## Alternative approach
Lex TS with a real parser (tree-sitter / esbuild) instead of a hand lexer. Rejected: adds a runtime dependency to a stdlib-only
verifier; the digest needs only token fidelity, not an AST.
