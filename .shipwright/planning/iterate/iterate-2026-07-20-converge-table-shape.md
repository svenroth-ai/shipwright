# Iterate — Converge the FR table shape (campaign S5)

**Run id:** `iterate-2026-07-20-converge-table-shape`
**Campaign:** `2026-07-18-requirements-catalog` · sub-iterate **S5**
**Complexity:** medium · **Mode:** change · **Spec Impact:** MODIFY
**Governing plan:** `Spec/design/2026-07-18-requirements-catalog-campaign-SPEC.md` §3.1, §3.2, §4 (S5), §6.2

## Problem

Five FR-table shapes existed for one concept. S4 collapsed the five *parsers* into one
header-driven reader; the *producers* still disagree. `/shipwright-adopt` emits
`| ID | Name | Priority | Description | Source | Layers |`, the greenfield template emits
`| ID | Requirement | Priority | Layers |`, and the greenfield **example** — the more
copyable of the two — emits `| ID | Requirement | Priority |`, missing a mandated column.
The live monorepo spec on disk is a sixth shape (`| ID | Name | Priority | Description | Source |`),
already stale against its own generator.

`Source` stores a file path, which is implementation detail (D3) and answers *where we
looked*, not *how we know*. `Area` does not exist, so grouping is carried only by the
folder — the axis D7 says must be rendered, never stored twice.

## Change

Both producers emit ONE shape:

```
| ID | Area | Name | Priority | Description | Basis | Layers |
```

- **`Area` is rendered from the group digit**, never stored as an independent axis (D7).
- **`Basis` replaces `Source`** with the closed vocabulary of §3.2.
- The live catalog table is migrated to the shape in the same commit (this is what makes
  S5 the first *visible* step).

## The hard blocker, and how it is handled

A requirement's provenance becomes `required_layers_source: explicit` the moment a
header-named `Layers` column holds a non-empty cell **without** the literal `(inferred)`
marker. `explicit` routes a coverage gap from advisory to hard
(`_layer_coverage_core.py:177` → `CheckResult(ok=False)` → ERROR → `sys.exit(1)`).
Measured today: 12 `defaulted_legacy` + 3 `inferred_legacy`, zero `explicit`, and 10 of the
15 requirements have zero test links. There is no bypass.

**Operator decision (2026-07-19): every machine-emitted `Layers` cell carries the literal
`(inferred)` marker.** Regex `\(\s*inferred\s*\)`, case-insensitive — `unit, e2e (auto)`
does NOT match.

**The migrated cells record the inference that already runs, they do not add a claim.**
`_infer_layers` derives `(e2e,)` for a UI/flow title and `(unit,)` otherwise. The migration
writes exactly that per row, so `required_layers` is byte-identical before and after and
only the provenance label moves (`defaulted_legacy` → `inferred_legacy`, both legacy).

## Decisions

### D-S5-1 — the `Source` → `Basis` mapping

Measured on the live table: 13× `enrichment.json`, 1× `backfill`, 1× an iterate run id.
(The campaign brief also predicted a `cli` value; it is not present — 15 rows, 3 distinct
values.) The mapping is decided here rather than left to fall out of the code:

| Today | → | Basis | Why |
|---|---|---|---|
| `enrichment.json` (13) | → | `code` | adopt's enrichment for this repo read plugin sources, `plugin.json` and `SKILL.md` files. Read from source is exactly `code`. |
| `backfill` (1, FR-01.14) | → | `code` | the backfill scanner derives from repo history and source, not from a human or a running app. |
| iterate run id (1, FR-01.15) | → | `code` | **re-derived, not carried over.** A run id records *when*, never *how*; D4 removes it from the requirement entirely. The basis was re-established by inspection: the contract it describes is present in source. |

**Answering SPEC §9 Q3 ("`enrichment` → `code`/`observed` — is that lossy?"): not lossy,
because the generator already knows which.** `_render_spec_md` picks
`f.get("source_file", f.get("url", "—"))` — a feature discovered by reading a file carries
`source_file`, one discovered by the Playwright crawl carries only `url`. That is precisely
the `code` / `observed` discriminator, available at the point where `Source` was rendered.
The generator therefore emits `code` for `source_file`, `observed` for a crawl-only `url`,
and `assumed` when neither exists — which is the honest label for a feature nobody
evidenced.

### D-S5-2 — `(inferred)` is scoped to machine-emitted cells

The greenfield template's `Layers` cells stay bare, so a greenfield author's declaration
reads as `explicit`. Stamping `(inferred)` into the template would permanently disarm the
hard gate for every future greenfield project — the opposite of the honesty argument that
motivates the marker. The marker marks *machine inference*; a human declaration is not
inference. The AC is verified where it bites: the 15 live rows, which must show zero
`explicit`.

### D-S5-3 — `Basis` is read from a `Basis` column only, never from `Source`

`BASIS_COLS = ("basis",)`. Treating a legacy `Source` cell as a `Basis` value would make
every already-adopted downstream repo hard-fail on `enrichment.json` — a malformed-value
verdict on data that was never claiming to be a basis. A spec with no `Basis` column
skips the check.

### D-S5-4 — a reasonless `other` is advisory, not malformed

SPEC §3.2 defines malformed as "neither in the vocabulary nor `other`", and states `other`
never blocks. A bare `other` is therefore reported in the advisory detail as missing its
reason, not escalated to a hard failure. Only a value outside the vocabulary is hard.

### D-S5-5 — Group I distinguishes FOUR states, not two

The S4 amendment to the AC requires three; the evidence supports four, and collapsing the
fourth back would re-create the class of silence this campaign removes:

| State | Meaning |
|---|---|
| `no_spec` | no `spec.md` on disk |
| `no_fr_rows` | spec present, nothing FR-shaped in it |
| `no_governing_header` | FR ids present, but no header names a Priority column |
| `no_canonical_ids` | a header WAS recognised, but no row id is canonical `FR-XX.YY` |

The last is the state S4's strict-id rule (C1) creates, and the one ADR-107, S4's mini-plan
and `frozen_bugs.py` FV-1 each cited as already-mitigated. It was not. It is read from the
`rejects` accumulator S4 shipped, not re-derived — with one additive field, `header_seen`,
because `non_canonical_id` alone cannot tell `no_governing_header` from `no_canonical_ids`.

## Blast radius

- `shared/scripts/lib/_fr_table_row.py` — **new**, holds `FrTableRow` (see below)
- `shared/scripts/lib/_fr_table_columns.py` — `BASIS_COLS`, `basis_cell`
- `shared/scripts/lib/fr_table_reader.py` — `basis` on the row, `header_seen` on rejects
- `shared/scripts/lib/fr_area.py` — **new**, Area rendered from the group digit
- `shared/scripts/lib/fr_basis.py` — **new**, the closed vocabulary + classifier
- `plugins/shipwright-adopt/scripts/lib/artifact_writer.py` — emit the shape
- `plugins/shipwright-project/skills/project/references/spec-generation.md` — template AND example
- `plugins/shipwright-compliance/scripts/audit/group_i.py` — four states + I5
- `.shipwright/planning/01-adopted/spec.md` — the migrated catalog table
- `integration-tests/requirements_corpus/golden.json` — regenerated with `--reason`

**`fr_table_reader.py` is at exactly 300 lines — the cap.** `FrTableRow` moves to a new
`_fr_table_row.py`, which is the same seam the module already uses (cells → columns →
reader): the row is the data contract between the layers, the reader is the state machine.
This buys the headroom for two additive fields without a new bloat crossing and without
ratcheting a baseline entry. `artifact_writer.py` is grandfathered at 695 and must not
grow, which is the second reason Area/Basis logic lives in shared modules.

## Acceptance criteria

- [ ] Both producers emit byte-identical headers.
- [ ] Every machine-emitted `Layers` cell carries the literal `(inferred)` marker.
- [ ] **Post-generation census: all 15 live requirements are `defaulted_legacy` or
      `inferred_legacy`; `explicit` count is ZERO.** Verified after the migration, not before.
- [ ] `required_layers` values are unchanged for all 15 rows.
- [ ] A malformed `Basis` hard-fails (Group I5); `other` is advisory only.
- [ ] Group I reports four distinct states where it used to report one `skip`.
- [ ] Golden corpus regenerated with `--reason`; every moved cell attributed to a decision
      above.
- [ ] Anti-ratchet gate `status: ok`, no new crossings.

## Landmine (carried from S4, verified again here)

**There are ZERO `### Removed Requirements` headings in the live spec.** The three
"occurrences" at lines 127/174/258 are prose inside requirement bodies; `_HEADING_RE`
requires `^#{1,6}\s`. SPEC §2.5's inline `**REMOVED** by` claim is *also* wrong: the single
marker at `01-adopted/spec.md:198` sits inside `### FR-01.01 — /shipwright-run` and retires
a sub-behaviour, not the requirement. Acting on either claim deletes a live requirement.
Nothing has ever been removed from this spec. The migration touches the table rows only.
