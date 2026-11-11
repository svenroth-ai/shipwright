# Mini-plan: U1 tag binding (iterate-2026-11-11-u1-tag-binding)

1. `_suite_tags.py`: per-line brace delta from `ts_lexer.lex` over the joined source (jsx per file suffix); replace `line.count`.
2. `_suite_tags.py`: the unbound-covers path emits `InvalidTag(reason="unbound-covers-comment", test="")`, raw = `path:line: // @covers ids`; also on a consecutive overwrite and at EOF. Never rebinds.
3. `_tag_binding_core._flag_tags`: that reason goes to warnings (only when new vs base), never findings. `_group_d_traceability.check_orphan`: worded apart, never fails D-orphan.
4. `untagged-modified` finding text names both remedies; remains a hard STOP; no new exemption code.
5. Tests: fixtures against `propagate_suite_tags`, gate routing, D-orphan wording. Docs: hooks-and-pipeline.md, changelog drop, regenerate test-traceability.json last.
