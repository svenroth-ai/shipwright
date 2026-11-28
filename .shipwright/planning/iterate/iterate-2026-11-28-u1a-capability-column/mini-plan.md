# Mini-plan U1a: optional Capability column in the FR table, every reader tolerant
Goal: the FR table may carry a stored `Capability` column after `Area`; every reader works with and without it. No values filled (U2b), no gate (U1b).
1. Inventory every FR-table reader (header-driven vs positional) incl. webui/leadwright (read only).
2. fr_table_shape: constants for the with-Capability shape + columns_of_canonical_header().
3. fr_layer_cell_writer: accept either canonical header, column count from the header found.
4. _baseline_label_hits._spec_lines: header-driven bookkeeping columns (was: first five cells, which would drop Description once Capability sits at index 2). _baseline_touch_spec: Capability cell not part of the normative digest.
5. Tests: one fixture rendered both ways through every reader (shared/tests, adopt, compliance).
6. Docs: fr-authoring 4a, hooks-and-pipeline; ADR records the inventory.
Alternative considered: put the column last (after Layers) so positional readers never move; kept "next to Area" per the U0 ADR, external positional readers listed as follow-ups.
Tests: parametrized with/without column over reader set; existing suites unchanged.
