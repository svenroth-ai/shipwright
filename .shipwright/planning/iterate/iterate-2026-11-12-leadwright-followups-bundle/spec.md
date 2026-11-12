# Iterate spec: leadwright-followups bundle (run iterate-2026-11-12-leadwright-followups-bundle)

Type: change. Complexity: small. Spec impact: none (behavior-preserving hardening and honesty fixes inside existing audit/collector checks; no new requirement).

Follow-ups collected from the leadwright-followups campaign (U1-U4). Five items, one PR:

1. **G2 whole-string match.** `unknown_scope_parts` accepts a scope string that is itself listed in the known set (a stoplist/alias entry such as `daemon,lib`) before splitting, so such entries keep matching. `daemon,lib,x` still reports all three parts. G2 docstring in `group_g.py` says every comma-joined part (or the whole string if listed as-is) must resolve. `test_audit_g2_scopes.py`: new test for the short-circuit; the doc assertions check all three docs (detector, SKILL, hooks doc) per name.
2. **G4 detail and wording.** The `fail` detail names up to 5 distinct open card ids (`+N more` beyond). The outbox limit is described as a limit of the merge-scope audit (detached worktree, no outbox), not of "CI". Test asserts the card id is in the detail.
3. **Honest test tags.** `test_audit_group_g4_close_tokens.py` is tagged at FR level `FR-01.14` (it does not prove AC03 "decision recorded"). `test_triage_status_less_append.py` keeps `FR-01.14/AC01` (a status-less append stays visible in the inbox with a state, which is what AC01 says).
4. **Bloat.** `_group_d_traceability.py` back under 300 lines: the `_EMPTY_SKIP` constant and its comment move to `_group_d_render.py` and are imported.
5. **Lexer leak.** A describe whose body opens and closes on its own line (`describe('x', () => {});`) is popped at once and no longer hands its tag to later tests. A describe with its callback on the next line, or with a `{ tag: [...] }` option object on the line, still propagates. Two regression tests.

Out of scope: any change to G4/G2 verdict semantics, other U2 code-review lows (accepted limits).
