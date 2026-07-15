# Golden RTM snapshot — mini_repos/app (schema_version 2)

> The layer-aware Requirements Traceability render the manifest produces (TT2).
> Pinned as a regression snapshot. `ok` requires an enabled + executed-passing
> tagged test at that layer; a skipped/absent test is `MISSING`; `n/a` = not required.

| FR | Status | Priority | Unit | Integration | E2E | Required (source) |
|----|--------|----------|------|-------------|-----|-------------------|
| FR-03.01 | active | Must | ok | n/a | **MISSING** | unit, e2e (explicit) |
| FR-03.02 | active | Must | n/a | n/a | ok | e2e (inferred_legacy) |
| FR-03.03 | active | Should | ok | ok | n/a | unit (defaulted_legacy) |
| FR-03.09 | removed | Should | n/a | n/a | n/a | e2e (explicit) |

**Orphans (1):** `e2e/legacy.spec.ts::copies the launch command to the clipboard`
→ `@FR-03.09` (fr_removed, confirmed_orphan).

**Invalid tags (1):** `tests/test_auth.py::test_sign_in_locale` → `FR-1.3`.

**Untagged (1):** `tests/test_auth.py::test_health_endpoint`.

**Reading of the answer key:** FR-03.01's e2e is skipped, so despite a present
`@FR-03.01` tag it is **MISSING** at e2e (R1). FR-03.09 is removed but its e2e spec
still stands → a confirmed orphan (the session failure class).
