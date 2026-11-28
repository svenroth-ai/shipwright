# Mini-plan U0: intent pyramid terms and format
Goal: vocabulary and file format only, no gate/parser/hook.
1. Glossary: Intent, Non-goal, Capability, Key scenario, Element; FR entry reworded (FR = one function).
2. fr-authoring.md section 2 and prompt sites (spec-generation, step-6-fr-scope, project SKILL, path-a-feature): FR is one function; capability groups FRs.
3. shared/schemas/intent.schema.json (no upper limits, no FR ids in text) + sample/malformed fixtures + test_intent_schema.py.
4. Constitution NEVER entry (never-intent-self-confirm) + register entry (unimplemented until U2a1) + guide 7.5 line.
5. CLAUDE.md "Where documents live": intent.md second human-written exception.
6. ADR drop: Capability column next to D7; intent.md as second human-owned file.
Alternative considered: put CAP in IREB "Feature" naming — rejected, collides with iterate change type.
Tests: schema validates sample, rejects malformed; constitution register drift test.
