# External Plan Review — empirical-followups

- **Run ID:** iterate-2026-05-21-empirical-followups
- **Mode:** iterate
- **Provider:** openrouter (Gemini + OpenAI)
- **Date:** 2026-05-21

## Reviewer summary

Both reviewers conclude the direction is sound and the phasing well-scoped, but call out concrete tightening needed around data-shape assumptions, edge cases, and consumer contract verification.

## Adopted findings (will fix in build)

### HIGH

- **OpenAI #1 (dependency, HIGH).** Verify the RTM consumer already reads `frId` from `triage.jsonl` and renders the deep-link without further changes; add an integration test that stamps a card → regenerates compliance → asserts both the RTM row AND the Coverage Summary `### FRs with open triage items` subsection contain the expected deep-link.
  - **Disposition:** Already empirically verified in the V-3 synthetic test (see `empirical-results.md` — seeding `trg-55a2f8bc` with `frId=FR-01.01` rendered `FAIL → [trg-55a2f8bc](...)` in both surfaces). The integration test will codify this contract — added as AC-1's round-trip test.

### MEDIUM (all adopted)

- **OpenAI #2 (approach).** Resolve E2E-column rendering ambiguity for the synthesis path.
  - **Decision:** Render `e2e` column as `—` ALWAYS in the synthesis branch — `tests.e2e_run` is a boolean signal without counts, so a count column can't be honestly populated from it. Document the limitation in the helper docstring; a future iterate can promote to counts when real `test_run` events become routine. (Reviewer suggested `yes/no` but that's inconsistent with the test_run branch's `passed/total` shape.)

- **OpenAI #3 + Gemini #5 (risk/approach).** Define ordering, filter, and cap semantics explicitly.
  - **Decision:** Filter first on `we.tests_total > 0`, then take the **last 30** in file order (matches data_collector's append order from `shipwright_events.jsonl`). Cap-after-filter ensures qualifying events aren't pushed off-screen by interleaved non-test events.

- **OpenAI #4 + Gemini #1 (edge-case).** Confirm the data shape the helper consumes.
  - **Disposition:** `data_collector` normalizes the nested wire `tests.total` / `tests.passed` keys onto the `WorkEvent` object as flat attrs `we.tests_total` / `we.tests_passed` / `we.e2e_run`. Existing code at `test_evidence.py:401` already uses `we.tests_total` — same path. No `KeyError` risk on missing nested keys because `data_collector` defaults to 0. Helper will use the same attr names.

- **OpenAI #5 (edge-case).** Reuse existing triage validation, not a new ad hoc subset.
  - **Decision:** Delegate to `triage.append_triage_item` for `severity` / `kind` / `title` validation (it already raises ValueError on unknown values). CLI adds only: `--fr-id` regex check (when provided) and JSON output formatting.

- **OpenAI #6 (dependency).** Verify packaging/execution path.
  - **Disposition:** `shared/scripts/tools/` is the canonical CLI tool dir — `record_event.py`, `triage_promote.py`, `write_decision_drop.py` all live there. Invocation pattern: `uv run shared/scripts/tools/triage_add.py ...`. No `__init__` needed. Add a smoke-test that invokes via `subprocess.run`.

- **OpenAI #8 (security).** Markdown-injection via `--title` / `--detail`.
  - **Disposition:** `markdown_table.escape_cell` already escapes pipes and newlines downstream. Add a test that feeds brackets / pipes / newlines in title to confirm the rendered markdown stays structurally valid.

- **OpenAI #10 (risk).** Schema-fixture test.
  - **Decision:** Add a parametrized test comparing the CLI-produced JSONL line shape against a hand-crafted reference item — only `frId` differs.

- **OpenAI #11 (edge-case).** Partial-presence cases for AC-2.
  - **Decision:** Add tests for: (a) `data.test_runs == []` + `data.work_events == []` → no Full Suite Runs section (existing behavior preserved); (b) `data.test_runs == []` + `data.work_events` present but all `tests_total == 0` → no section; (c) mixed sources (`iterate` + `build`) → both render correctly.

- **Gemini #2 (edge-case).** `--fr-id` regex on optional input.
  - **Decision:** Validate ONLY when `args.fr_id is not None`. Empty string also rejected as "missing" (`--fr-id ""`).

### LOW (adopted where cheap)

- **OpenAI #7 + #12 (risk/security).** Narrow ALLOWLIST + format-only warning.
  - **Decision:** Only extend `ALLOWLIST['compliance']` to add `.shipwright/agent_docs/triage_inbox.md`. Do NOT broaden the other 3 migrations preemptively. Surface a one-line "Note: --fr-id format-validated only; cross-FR existence not checked" in the CLI stdout when `--fr-id` is supplied (information, not warning — the design IS format-only validation per spec).

- **OpenAI #9 (edge-case).** stderr/stdout contract.
  - **Decision:** JSON on stdout for ALL outcomes (success or failure). Exit code 0 on success, 1 on validation error. Argparse errors continue to use argparse's default stderr+exit-2 (don't fight argparse).

- **Gemini #3 (dependency).** Verify RTM consumer reads `frId`.
  - **Disposition:** Same as OpenAI #1 — empirically verified.

- **Gemini #4 (approach).** Brittle markdown parsing in round-trip test.
  - **Decision:** Round-trip parser uses a robust regex (strip outer pipes, split on `|`, strip each cell) — not fixed-column indexing.

## Carry-forward (no plan change)

None. All 17 findings (12 OpenAI + 5 Gemini) are addressed above.

## Rationale for proceeding

Both reviewers' "overall assessment" reads "direction sound; tighten data-shape and edge-case handling." All concrete tightening fits in the existing AC scope without expanding it. The phased AC-3 → AC-1 → AC-2 sequence still amortizes risk correctly.
