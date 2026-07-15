# Traceability test-harness / fixture package (P1 answer key)

Frozen fixtures for the requirement→test traceability campaign
(`2026-07-15-traceability-prerequisite` P1). These are the **targets** the later
(autonomous) campaign steps grade their own work against — the "answer key" that
makes TT1–TT8 self-verifiable and unattended-safe. **No gate/collector logic
lives here** — only contracts + fixtures.

`catalog.json` is the machine-readable index (example → expected result, keyed to
the four adversarially-checked properties). Layout:

| Path | What |
|------|------|
| `mini_repos/app/` | one mini-repo: `spec.md` (active + removed FRs, `Layers` in each provenance state) + tagged pytest/Playwright/Vitest tests (all four grammar forms) + a malformed tag + an untagged test |
| `diffs/removal/` | FR moved to `## Removed Requirements`, test still present → removal→orphan gate BLOCKS |
| `diffs/behavior_change/` | FR description changed (behavior-change signal) → cross-layer gate; green when the required layer is covered |
| `diffs/refactor/` | pure refactor, no spec/AC/FR delta → cross-layer gate does **NOT** fire (the "must NOT block" green case) |
| `evidence/` | JUnit / Playwright-JSON / Vitest reporter samples **incl. a skipped test** + `evidence_index.json` (normalized, keyed to test ids) |
| `llm_adapter/` | stubbed record/replay adapter + cassette so the backfill LLM leg runs offline (R4-bounded payloads, `auto_write=false`) |
| `decisions/` | predeclared adopt-ambiguity answers + orphan-retirement choices, so an unattended runner never stalls |
| `golden/` | `manifest.json` (schema v2 answer key) + `report.md` (layer-aware RTM snapshot) |

## The four key properties (what the adversarial panel checks)

1. **skipped ≠ covered** — `mini_repos/app` FR-03.01's e2e test is skipped, so the golden
   manifest marks e2e `MISSING` despite a present `@FR-03.01` tag (`evidence/`).
2. **removal flagged** — `diffs/removal` + the golden orphan for FR-03.09.
3. **refactor not blocked** — `diffs/refactor` (`expected_blocked=false`).
4. **golden correct** — `golden/manifest.json` validates against the v2 schema and matches
   the reference parser's output over `mini_repos/app`.

Contracts (elsewhere in the tree):
`scripts/lib/traceability_schema.json` (+ `.example.json`),
`shared/scripts/lib/requirement_model.py`, `shared/scripts/lib/fr_tag_grammar.py`
(+ `references/traceability-tag-grammar.md`).
