# Spec: Tagless demo app (backfill fixture)

> Fixture mini-repo for the shared backfill engine (traceability TT6). Its tests
> are mostly tagless; the engine maps each to its FR as far as deterministically
> possible, proposes the low-confidence residue, and surfaces orphan candidates.
> Active + removed FRs; splits 05 (multi-FR) and 06 (single-FR, unique-split).

## Functional Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-05.01 | User can export orders to a CSV file | Must | unit |
| FR-05.02 | Dashboard shows the live order feed | Must | e2e |
| FR-06.01 | Archive an old campaign to cold storage | Should | integration |

- **FR-05.02** is exercised by a spec whose FILENAME carries the `FR-05.02` token
  (a deterministic `path_fr_token` → auto-write).
- **FR-06.01** is the sole active FR in split `06`, so a `06-*` test file is a
  `unique_split` match (deterministic → auto-write).
- **FR-05.01** is only reachable by title similarity from `test_export.py`
  (advisory → a proposal, never an auto-write).

## Removed Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-05.09 | Copy the launch command to the clipboard | Should | e2e |

- **FR-05.09** was retired. `e2e/flows/legacy.spec.ts` still carries the explicit
  `@FR-05.09` tag → a **confirmed orphan**. `tests/test_clipboard.py` is untagged
  but its title still matches the removed wording → a **possible orphan** (a
  candidate for review, never an auto-accusation).
