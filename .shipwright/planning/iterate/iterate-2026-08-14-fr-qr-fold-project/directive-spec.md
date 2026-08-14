# Iterate directive: retire QR-/C- id spaces (greenfield producer)

Pair of trg-a51e7502 (the adopt half; that producer mints its own ids and is
covered by a separate task). This is the GREENFIELD entry path:
`/shipwright-project` follows `spec-generation.md` when it writes a fresh
split's `spec.md`.

## Measured state (2026-08-14)

`plugins/shipwright-project/skills/project/references/spec-generation.md`
instructed the spec writer to emit, alongside the FR table:
- `## 3. Quality Requirements` (`| ID | Requirement | Category |`), ids
  `QR-{NN}.{YY}`, with their own ACs
- `## 4. Constraints`, ids `C-{NN}.{YY}`

Nothing in the framework read either id: `fr_table_reader` accepts
`^FR-[\d.]+$` only; `collect_requirements_from_planning` and the compliance
`data_collector` accept FR-shaped rows only; RTM/traceability/reconciliation/
`fr_change_history`/Group D are keyed on
`requirement_model.CANONICAL_FR_RE` (`FR-\d{2}\.\d{2}`); `--affected-frs QR-…`
is rejected by the existence gate; `docs/guide.md`,
`shared/constitution.md`, `shared/glossary.md` never mention QR. The two
producers (project, adopt) did not even agree with each other on the shape
(`QR-01.01` vs `QR-01`).

## Decision (operator, 2026-08-14, final — do not re-open)

One requirement id space: `FR`. Quality targets become FR rows in the
existing table. `QR-` is retired as an id space. Constraints keep their
section but lose their ids — written as prose, since a constraint is not a
testable requirement. No `Category` column is added: campaign S5 converged
both producers onto one table shape (`fr_table_shape.FR_TABLE_HEADER`), and
the requirement text already carries the quality attribute. Quality rows
need a Priority (Must/Should/May) like any other row.

## Scope

- `spec-generation.md`: fold section 3 into the FR table; drop the QR id
  space; keep Constraints as prose without ids; fix the mint-numbering
  guidance that documented QR-/C- ids.
- Check the rest of the shipwright-project skill for the same instruction.
- `docs/guide.md`: verified to not mention QR — no change expected/made.
- Existing specs (e.g. this repo's own `.shipwright/planning/01-adopted/spec.md`,
  which still carries `QR-01`) are **not** migrated — producer-only change.

## Tests

The reference no longer instructs a QR-/C- id space; a spec generated per
the updated reference parses to requirements via the FR-table reader
(quality rows included); the `FR_TABLE_HEADER` constant is unchanged (no
new column).
