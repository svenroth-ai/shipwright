# Spec: Demo App (traceability fixture)

> Fixture mini-repo for the requirement->test traceability harness. Its tagged
> tests, execution evidence, and golden manifest are the "answer key". Active
> and removed FRs; the `Layers` column exercises each `required_layers` provenance
> state (explicit / inferred_legacy / defaulted_legacy — the latter two are the
> collector's job when the column is absent, pinned in the golden manifest).

## Functional Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-03.01 | User can sign in | Must | unit, e2e |
| FR-03.02 | Dashboard shows live orders | Must | |
| FR-03.03 | Persist an order to the database | Should | |

- **FR-03.01** declares its `Layers` explicitly → `required_layers_source: explicit`.
- **FR-03.02** has no `Layers`; it is a UI/flow FR, so the collector infers `e2e`
  → `required_layers_source: inferred_legacy`.
- **FR-03.03** has no `Layers` and no strong heuristic signal, so it falls back to the
  every-FR default `unit` → `required_layers_source: defaulted_legacy`.

## Removed Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-03.09 | Copy the launch command to the clipboard | Should | e2e |

- **FR-03.09** was retired (moved here). Its e2e spec still exists and still carries the
  `@FR-03.09` tag → a **confirmed orphan** (`reason: fr_removed`). This is the session
  failure class the campaign exists to catch.
