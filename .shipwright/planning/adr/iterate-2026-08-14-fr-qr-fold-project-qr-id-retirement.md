# Retire the QR-/C- requirement id spaces (greenfield spec-generation)

## Context

`plugins/shipwright-project/skills/project/references/spec-generation.md` — the
reference `/shipwright-project` follows when it writes a fresh split's
`spec.md` — instructed the spec writer to mint `QR-{NN}.{YY}` (quality
requirement) and `C-{NN}.{YY}` (constraint) ids in dedicated `## 3. Quality
Requirements` / `## 4. Constraints` sections.

Nothing in the framework ever read either id. Verified repo-wide:
`fr_table_reader` accepts the canonical `FR-\d{2}\.\d{2}` form only;
`collect_requirements_from_planning` and the compliance `data_collector`
accept FR-shaped rows only; RTM, traceability, reconciliation,
`fr_change_history`, and Group D are all keyed on
`requirement_model.CANONICAL_FR_RE`; `--affected-frs QR-…` is rejected by the
existence gate (the paired defect, trg-a51e7502, on the `/shipwright-adopt`
producer). `docs/guide.md`, `shared/constitution.md`, and `shared/glossary.md`
never mention `QR`. The two producers did not even agree with each other:
`/shipwright-project` minted `QR-01.01`, `/shipwright-adopt` minted `QR-01`.

Two producers, zero consumers, two id formats. An id is a promise of
addressability — numbered prose nothing can reference is worse than
unnumbered prose, because it looks referenceable.

This re-merges a split made 2026-07-24 ("Bloat/file-size → a Quality
Requirement, later QR pass, not an FR"), whose purpose was to keep the FR
catalogue from inflating with how-well statements. That rule was never
codified (`shared/fr-authoring.md` does not mention quality at all — it lived
only in campaign notes and a doubt-reviewer's ad-hoc inference), and the
"later QR pass" had no destination: items routed to it were held nowhere,
because no reader existed. The routed example (bloat/file-size) already has
an enforcing test (the anti-ratchet gate over `shipwright_bloat_baseline.json`),
so as an FR it becomes a covered requirement rather than a parked note.

## Decision

One requirement id space: `FR`. Quality targets (performance, security,
scalability) become ordinary FR rows in the existing table — same Priority
column, same acceptance-criteria rule as any other requirement. `QR-` is
retired as an id space. Constraints keep their own section but lose their
ids: a constraint ("must use Supabase Auth", "must run on Windows") is
genuinely not a requirement with a test, so folding it into the FR table
would be dishonest — but an unread `C-{NN}.{YY}` id is exactly the same
defect one level down, so Constraints render as plain prose bullets
(grouped by type: Technical / Regulatory / Integration), no numbering.

No `Category` column was added to the FR table. Campaign S5 converged both
producers onto one table shape (`fr_table_shape.FR_TABLE_HEADER`), asserted
by test, precisely to end producer divergence; adding a column here would
re-open what S5 closed. The requirement text already carries the quality
attribute — "The system SHALL complete login requests within 500ms (p95)"
is self-evidently a performance requirement and needs no taxonomy label
with no consumer to say so.

## Consequences

Every fresh `/shipwright-project` spec.md now has exactly one id space to
learn and one table for compliance/RTM/traceability to read — no more
QR-/C- rows that look tracked but are invisible to every consumer. A new
regression test (`plugins/shipwright-project/tests/test_spec_generation_qr_fold.py`)
locks the retirement and proves, against the real shared `fr_table_reader`,
that a folded quality-target row parses as an ordinary requirement. Existing
specs (including this repo's own `.shipwright/planning/01-adopted/spec.md`,
which still carries a historical `QR-01`) are **not** migrated — rewriting
historical specs is a separate decision with a renumbering hazard, and no
gate reads those lines today. The adopt-side producer
(`plugins/shipwright-adopt/scripts/lib/spec_document.py`), which still emits
its own `QR-`/`C-` shape, is a separate paired task (trg-a51e7502) and is
deliberately untouched here.

## Rejected alternatives

**Keep QR-/C- and add a consumer for them.** Rejected: nothing in the
requirements model, RTM, or compliance layer was ever designed around a
second requirement id space, and building one now to rescue an
already-divergent, already-unread convention is solving a problem the
retirement makes disappear for free.

**Add a `Category` column to the FR table instead of folding by wording.**
Rejected: re-opens the exact producer-divergence problem campaign S5 closed
by converging both producers onto one asserted table shape, and duplicates
information the requirement's own SHALL/SHOULD/MAY sentence already carries.

**Migrate the historical `.shipwright/planning/01-adopted/spec.md` QR-01 row
in the same change.** Rejected: no gate reads that line today, and renumbering
a historical spec carries the exact id-collision hazard the paired task
(trg-a51e7502) documents. Producer-only change; migration is a separate,
deliberate decision if ever made.

## Test evidence

`plugins/shipwright-project/tests/test_spec_generation_qr_fold.py` (5 tests,
green): the reference no longer instructs a QR-/C- id space at any line
(unanchored regex re-check, catching a table-row reintroduction); Constraints
render as prose bullets with no id column; a quality-target FR row extracted
from the reference's own worked example parses via the real
`shared/scripts/lib/fr_table_reader.read_active_fr_rows` with the correct
Priority and text; and `FR_TABLE_HEADER` (from `fr_table_shape.py`, unchanged)
is still present in the worked example — no new column. Full local suite
(F0): 18/18 units green in 5.6 min, including the pre-existing
`integration-tests/test_fr_table_shape_convergence.py` (13 tests) and the
`shared/tests` FR-authoring/granularity subset (58 tests) that also read this
reference file, all unaffected by the edit.
