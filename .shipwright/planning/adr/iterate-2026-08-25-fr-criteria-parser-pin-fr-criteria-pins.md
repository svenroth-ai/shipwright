# ADR — Pin fr_criteria.py parsing widenings, fix table description exemption

**Run:** `iterate-2026-08-25-fr-criteria-parser-pin`

## Context

PR #648 unified three FR-criteria readers onto `shared/scripts/lib/fr_criteria.py`,
and parsing behavior widened past each predecessor without dedicated tests or
docs. Two triage cards — `trg-968e4d87` (Stage-2 code review) and `trg-467b7b2f`
(doubt-review round 1) — deferred four small findings from that PR, all from the
same run (R0, campaign req3-04-ac-identity-mono). This iterate merges and
resolves both cards in one pass since they touch the same file and the same kind
of work: pinning newly-widened parser behavior with tests.

## Decision

1. **`iter_anchored_blocks`'s two block-termination rules** — a same-or-lower-rank
   NON-FR heading ends a block, and a criterion line starting with `**FR-XX.YY`
   truncates one — pinned with 4 direct unit tests plus a one-line doc
   clarification. Behavior unchanged, now documented and tested.
2. **`criteria_texts`'s bullet-semantics widening** — numbered-list bullets
   (`1.`/`1)`), placeholder rejection, and continuation-line joining — pinned
   with 3 direct unit tests, plus one integration test proving I6's own real
   entry point sees the same semantics (not just `fr_criteria` directly).
3. **Bug fix: `compute_fr_coherence`'s FR-table description exemption.** It
   exempted a heading from `missing_description` on any non-empty picked table
   cell. `fr_table_reader`'s `TITLE_COLS = ("description", "name", "text",
   "requirement", "title")` falls back to the `Name` column when no real
   `Description` column exists — so a table with only a `Name` column silently
   satisfied the exemption with what is really just a short label, producing a
   false "has description" verdict in a compliance gate. Fixed by requiring the
   picked cell differ from the `Name` cell (`r.text.strip() != r.name.strip()`),
   with a RED-before-fix reproduction test and a regression guard proving the
   genuine-Description-column case still exempts correctly.
4. **I6's own entry point.** `group_i_criteria.py` gained `criteria_for(content,
   fr_id) -> list[str]`, mirroring the existing `has_criteria`. The three-way
   convergence integration test (`integration-tests/test_fr_criteria_three_way_
   convergence.py`) now calls this instead of reaching `group_i_criteria.
   fr_criteria.criteria_for` (the shared module's attribute) directly — the
   latter only proved the shared module was reachable, not that I6's own
   contract returns the right thing.

Explicitly out of scope: further unifying the three readers, or restructuring
`fr_criteria.py` beyond what these four pins need.

## Consequences

`compute_fr_coherence` now correctly reports `missing_description` for
Name-only tables (previously silently exempted) — a real behavior change to a
Shipwright-internal compliance check (S5 FR-coherence), not to any product FR
of a target project.

A residual, narrower edge case survives, deliberately: `TITLE_COLS` ranks `Name`
above `Requirement`/`Text`/`Title`, so a table with a `Name` **and** a
`Requirement`/`Text`/`Title` column but no `Description` column would still have
the genuine descriptive column silently ignored (`r.text` reads `Name`), and the
new filter would then deny a legitimate exemption. Checked against every real
fixture/corpus shape this repo ships (`golden.json`, `test_fr_table_reader_
contract.py`'s `SHAPES`, `test_rtm_fr_table_shapes.py`) — none combines `Name`
with `Requirement`/`Text`/`Title` and no `Description`, so this is confirmed
latent, not live. Filed as `trg-16075b99` for a future structural fix (a
`text_from_named_col` flag on `FrTableRow`, mirroring `layers_from_named_col`/
`basis_from_named_col`); not fixed here, as it is outside this iterate's scope.

## Rationale

Full review cascade run despite no risk flags at small complexity (spec-reviewer
→ code-reviewer → doubt-reviewer), given finding 3 is a genuine correctness fix
in a compliance gate. All three stages PASS; the one non-blocking finding
(the edge case above) was independently found by both code-reviewer and
doubt-reviewer and filed as `trg-16075b99` rather than fixed, per this
iterate's declared scope.

## Rejected

Fixing the `trg-16075b99` edge case in this same diff — rejected because it is
confirmed latent (not live against any real spec this repo ships) and the
merged triage card explicitly scoped this iterate to the four named findings,
not further reader unification or restructuring.
