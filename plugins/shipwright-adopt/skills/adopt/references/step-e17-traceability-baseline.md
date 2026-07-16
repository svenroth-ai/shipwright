# Step E.17 — Traceability Baseline

Wires the requirement→test traceability capability (campaign
`2026-07-15-test-traceability-layers`, TT7) into brownfield onboarding, so an
adopted repo starts *with* a real, layer-aware RTM and the two gates have data
from day one — instead of accruing the stale-test rot the spec exists to catch.

## When it runs

After **Step E** (the spec is written; each FR carries an inferred `Layers`
column from TT3) and BEFORE **Step F**. Step F's compliance collector
(`test_links`, now wired into its `adopt` phase) reads the `@FR` tags this step
writes and emits `.shipwright/compliance/test-traceability.json`.

## Command

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/seed_traceability_baseline.py" \
  --project-root <cwd> \
  [--split-name 01-adopted] \
  [--decisions <predeclared-fixture.json>] \
  [--shared-root <path/to/shared>] \
  [--dry-run]
```

Prints a JSON summary and writes
`.shipwright/adopt/traceability-baseline.json` as a durable run summary (a tracked
record of what the baseline established; Step H does not currently read it).

## What it does

1. **Scaffold the `@FR` tag convention** into `<repo>/.claude/rules/tests.md`
   and `integration-tests.md` (copied from `shared/templates/rules/`, the SSoT).
   Idempotent + non-destructive — a rule file the repo already owns is preserved.
2. **Backfill existing tests** by subprocessing the shared TT6 engine
   (`shared/scripts/tools/backfill_test_links.py`). It writes `@FR` tags only for
   deterministic, high-confidence matches; low-confidence matches become review
   proposals. It **never** passes `--repo-follows-split-convention`: on a
   brownfield repo a bare `NN-` filename prefix is the Playwright/Cypress
   execution-ORDER convention, not a Shipwright split id, so a split match stays
   advisory (no false coverage — TT6 finding C2).
3. **Repo-wide skip inventory** — reuses TT4's `test_hygiene` (Python) +
   `ts_test_hygiene` (Playwright/Vitest/Jest) scanners across **every** test file
   (NOT diff-scoped — `filter_to_changed` is deliberately not applied), so the
   standing skip rot TT4's diff-scoped gate cannot see is caught at onboarding
   (Spec §11-R5).
4. **Resolve `required_layers` ambiguity** — see *Detection over questions* below.
5. **File triage** for the orphan/unmapped/proposal candidates + every
   pre-existing skip. Items are written to the **tracked** `.shipwright/triage.jsonl`
   (`to_outbox=False`) so they ship in the Step H commit and appear in the WebUI
   Inbox from day one. Idempotent (`dedup_key`, no recency window) — a re-adopt
   never duplicates a card. Each orphan carries its TT6 category: `confirmed_orphan`
   (a live tag → a removed/absent FR), `possible_orphan` (heuristic), or `unmapped`
   (no live FR maps). An `unmapped` test is framed as a **review candidate, never a
   stale-feature accusation** (§11-R4).

## Detection over questions (ambiguity resolution)

Most FRs are classified automatically from the detected surface (TT3 inference,
already in the spec). For an FR the scan genuinely cannot classify:

- **Interactive adopt** — ask the operator with `AskUserQuestion`, in plain
  language: *"Feature X — is this something a person uses in the browser (needs an
  end-to-end test), or backend-only (a unit/data test is enough)?"* Record the
  answer's layers.
- **Unattended adopt** — pass `--decisions <fixture>` (P1's predeclared answers —
  the `decisions/adopt_ambiguity.json` fixture shipped under the compliance plugin's
  traceability test fixtures). The tool consumes the matching answer (keyed
  `<split>::FR-id`) and **never stalls**. With no fixture answer it defers to the
  collector's inference. The tool itself never prompts — the interactive branch is the
  agent's job, not the script's.

## Zero-test repo

A repo with no tests backfills to an empty report: no tags written, no triage
filed, and the Step F manifest is valid + coverage-empty. Because every adopted
FR is `inferred_legacy` / `defaulted_legacy`, the compliance `D-layer` detective
treats missing layers as **advisory** (WARN), never a hard failure — so onboarding
is never blocked by the new gate (Spec §9 landmine).

## ADR-045 discipline

The tool imports NEITHER the shared `lib` package NOR the compliance `scripts.lib`
package in its own interpreter. The backfill engine (shared `lib`) runs in a
subprocess; the manifest collector (compliance `scripts.lib`) runs in Step F's own
interpreter. This interpreter imports only top-level `shared/scripts` modules
(`triage` + the TT4 hygiene scanners) and the adopt pure-libs
(`traceability_baseline`, `traceability_layers`).
