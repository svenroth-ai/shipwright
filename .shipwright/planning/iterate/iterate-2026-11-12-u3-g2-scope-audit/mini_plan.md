# Mini-plan U3 G2 scope audit
1. Text only (operator decision 3.4: no automatic skip): replace the false exemption sentence in audit_detector.py defaults comment and the compliance SKILL.md; point to disabled_checks: ["G2"] and the project's own g2_alias_map / g2_stoplist. Pinned by a doc test.
2. New module g2_scopes.py (scope_parts, unknown_scope_parts); group_g._check_g2 judges each comma part; the evidence names only unknown parts. group_g.py stays at 373 lines.
3. New test file test_audit_g2_scopes.py (parser, known+known passes, known+unknown flags only the unknown, all-unknown listed, doc pin).
Docs: hooks-and-pipeline.md G2 paragraph; changelog drop; cards trg-13c59214 and trg-5acb749f closed with a pointer.
