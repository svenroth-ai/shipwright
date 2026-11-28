# Architecture Brief — U1a Capability column

Problem: the FR table needs a place to store which capability (CAP id) each FR belongs to. Readers must keep working on tables with and without that column.

Options:
1. Add an optional `Capability` column right after `Area`; make the few fixed-shape readers header-driven.
2. Add the optional column as the LAST column (after Layers).
3. Store the FR-to-capability mapping outside the FR table (a separate file, or only in intent.md).
4. Do nothing now and derive the mapping from the FR id group.

Permanent addition: one column in a human-readable table, two constants, one helper.
