# ADR-058 — RTM ↔ Triage deep-link + Coverage Summary rewrite (B.4)

> Long-form spec backing the iterate-2026-05-21-b4-rtm-deep-link-and-coverage
> ADR drop.

## Audience principle

Solo dev today, leadwright Phase 3 tomorrow. The RTM's job is to
answer "which FRs are in trouble, and where do I click to fix them?"
in one glance. The previous Coverage Summary was a thin
counters-only table that didn't answer either question — operators
had to cross-reference test-evidence.md + triage_inbox.md manually.
The rewrite makes the RTM the single navigation surface for
FR-level work.

## What landed in B.4 vs forward-looking

| Decision | Realized in this iterate? | Realized where |
|----------|---------------------------|----------------|
| D1 RTM consumes `frId` cross-link            | **Yes** | B.4 (this PR) |
| D2 Status-cell override (triage > unit)      | **Yes** | B.4           |
| D3 Coverage Summary → 3 subsections          | **Yes** | B.4           |
| D4 Suite-level cross-link (`suiteId`)        | No — out of scope | Future iterate when test-evidence producers populate suiteId |
| D5 Stale-window configurability              | No — out of scope | Deferred until operator complains       |

## Decisions (B.4)

### D1. RTM consumes B0's `frId` cross-link

ADR-054 D5 made `frId` / `suiteId` / `eventId` first-class wire
fields on triage append events. B0 added the producer side; B.4
adds the consumer:

```python
def _open_triage_by_fr(project_root):
    """{fr_id: [open triage items]} from .shipwright/triage.jsonl"""
```

Only `status == "triage"` items participate (promoted / dismissed /
snoozed are terminal). The helper lazy-imports the triage API so a
minimal CI env without `shared/scripts/` on `sys.path` falls through
to `{}` rather than crashing.

### D2. Status cell overrides events-derived status when triage is open

The Status cell logic in `_requirements_coverage_events`:

1. Compute events-derived status as before (COVERED / COVERED
   (baseline) / FAIL / NO TESTS / NOT VERIFIED).
2. If `_open_triage_by_fr` returns at least one item for the FR,
   **replace** the status string with
   `FAIL → [trg-XXX](../agent_docs/triage_inbox.md#trg-XXX)`
   (comma-separated when multiple).

Rationale: an open triage card is positive evidence the operator
hasn't accepted the current verification state. Even if unit tests
are passing, the operator flagged something — the RTM must surface
that loud, not bury it under a COVERED label.

### D3. Coverage Summary → 3 operator-actionable subsections

The thin metrics table at the top of the section is kept (the
dashboard's quality indicators link into it). Below the table, three
new subsections render only when non-empty:

#### `### FRs without tests`

FRs with zero `work_completed` events tying back via `affected_frs`.
Each row: bullet with link to the FR's spec.md and the first 80 chars
of the FR text.

#### `### FRs with stale verification (> 14 days)`

FRs whose latest verifying event is older than
`_STALE_VERIFICATION_DAYS` days (14 per the plan). Sorted oldest-
first so the operator's eye lands on the longest-neglected FR.

#### `### FRs with open triage items`

FRs with at least one open triage card carrying `frId`. Each row
renders `[FR-X.Y](../../spec.md): FAIL → [trg-AA](...)` so the
operator clicks directly into the triage card.

Sections are omitted entirely when their set is empty. Quiet output
when nothing is wrong is the audience principle dial — the operator
sees the three subsections only when there's work to do.

## Consequences

- The compliance dashboard's `Quality indicators` row for FR
  coverage now points at a richer RTM where action paths are
  inline. The previous "go check 3 different .md files" friction
  collapses to one click.

- ADR-054 D5 is now closed end-to-end: producers (B0 + B.3) set
  `frId`; consumer (B.4 RTM) renders the deep-link; the aggregator's
  HTML anchors (B0) make the fragment resolve.

- The Coverage Summary section is no longer a "padding metric" —
  every non-zero subsection is actionable.

- The work_completed → FR-coverage link doesn't change; only the
  Status cell rendering and the Coverage Summary structure.

## Rejected (kept for future me)

- **Suite-level cross-link (`suiteId`)** — B.3's
  `emit_test_failure_triage` populates `event_id` (the test_run
  cross-link) but not `suite_id` because per-test-failure granularity
  isn't on the test_run wire format. When test-evidence gains
  per-test data (out of scope here), the existing consumer reads
  `suiteId` for free.

- **Configurable stale-window threshold** — over-engineering for
  solo dev. The 14-day value mirrors the plan B.4 spec. Configurable
  threshold deferred until an operator complains.

- **Section Traceability table deep-links** — the section-trace table
  is greenfield-only (operates on per-section data, not FRs). Out of
  scope.

- **Move open-triage rows into the table itself** as new columns —
  inflates row width on every project, defeats the audience
  principle. The subsections at the end of Coverage Summary are
  conditional, which is the right ergonomic.

## External-Review-Findings

OpenRouter cascade ran 2026-05-21. 15 findings (Gemini 5 + OpenAI 10).
High/medium addressed inline. Notable: Gemini-H1 (datetime.now
determinism) prompted a non-trivial refactor — the "now" reference
for stale-verification math now anchors to the latest event's
timestamp, not wall-clock, so RTM regenerations against the same
event log produce byte-identical output.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | Gemini | HIGH   | `datetime.now()` makes RTM non-deterministic — diff churn on every regeneration. | accepted-and-fixed — `_reference_now` returns `max(work_events.timestamp)` so stale math advances only when new events are added. Fallback to `datetime.now()` only when `work_events` is empty (greenfield pre-first-iterate). `test_regeneration_is_deterministic` asserts two consecutive `generate(data)` calls produce identical output. |
| 2 | Gemini | MEDIUM | Silent data loss in minimal envs if triage import fails. | rejected-with-reason — for a solo-dev artifact, a missing optional dependency that produces a quieter RTM is acceptable; printing a warning placeholder bloats the rendered file for the common case. The lazy-import keeps the RTM functional; if the operator wants to know why links are missing, they re-run with the full env. |
| 3 | Gemini | MEDIUM | Hardcoded relative link path. | accepted-and-fixed — `_TRIAGE_INBOX_REL = "../agent_docs/triage_inbox.md"` constant; future relocation is a one-line change. |
| 4 | Gemini | MEDIUM | Corrupt timestamps silently dropped. | accepted-and-fixed — `_parse_iso_ts` now emits `warnings.warn` on malformed input; row still skipped (failing whole RTM render for one corrupt event would be worse). `test_malformed_timestamp_warns_and_skips` covers it. |
| 5 | Gemini | LOW    | Status override loses prior context. | rejected-with-reason — operator clicks `trg-XXX` for context. Keeping the override loud matches the audience principle ("loud only where relevant"). Documented in D2 rationale. |
| 6 | OpenAI | MEDIUM | Lazy import only catches ImportError; read failures could still crash. | accepted-and-already-correct — `_open_triage_by_fr` wraps the `read_all_items` call in `try/except Exception` returning `{}`. Existing code; reviewer missed it. |
| 7 | OpenAI | MEDIUM | Status override changes semantics (downstream parsers). | accepted-and-documented — no internal consumer parses the Status cell programmatically; only the markdown is rendered. The override is intentional per D2. Documented in changelog drop. |
| 8 | OpenAI | MEDIUM | Hardcoded relative path. | accepted-and-fixed — same as Gemini #3. |
| 9 | OpenAI | MEDIUM | FR-ID normalization (case/whitespace). | rejected-with-reason — FR IDs follow `FR-NN.MM` strictly. Producers (B0 contract) write `frId` verbatim from caller; consumer (RTM) reads `req.id` verbatim from spec parser. Both use exact match. Documented in iterate spec. |
| 10 | OpenAI | MEDIUM | `_frs_without_tests` vs stale could double-classify. | rejected-with-reason — `data.work_events` is pre-filtered to `type == "work_completed"`. Both subsections use the same `fr_events_map`; an FR is in exactly one subsection (none → no-tests; some old → stale; some recent → neither). |
| 11 | OpenAI | LOW    | Malformed timestamps silently skipped — masks data quality. | accepted-and-fixed — same as Gemini #4. |
| 12 | OpenAI | LOW    | Lexicographic sort wrong for trg-XX numeric strings. | rejected-with-reason — triage IDs are `trg-<8 hex>` (fixed-width hex from `_generate_id`). Lexicographic == byte-wise for equal-length hex strings. No bug. |
| 13 | OpenAI | LOW    | Add integration test against real triage payload shape. | accepted-and-already-correct — `_seed_open_triage_item` calls `triage.append_triage_item` directly (no mocking), so tests exercise the real on-wire shape. |
| 14 | OpenAI | LOW    | Constrain triage ID pattern. | accepted-and-fixed — `_TRIAGE_ID_RE` rejects malformed IDs in `_render_fail_triage_links`. `test_malformed_trg_id_is_skipped` covers it. |
| 15 | OpenAI | LOW    | Centralize "open triage for FR" lookup. | accepted-and-already-correct — `_open_triage_by_fr` + `_render_fail_triage_links` are both used by `_requirements_coverage_events` and `_render_open_triage_section`. Single source of truth. |

## External-Code-Review-Findings

OpenRouter cascade ran 2026-05-21 on the staged diff. OpenAI returned
5 findings; Gemini's response was truncated mid-finding. Addressed
high/medium inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | HIGH   | `fr_events_map` built from all `data.work_events` — could capture non-work_completed events. | rejected-with-reason — `data_collector.collect_events` already filters `data.work_events` to `type == "work_completed"`. Reviewer missed the upstream filter; verified at `data_collector.py:1276`. Documented inline. |
| 2 | OpenAI | MEDIUM | `events[-1]` assumes chronological order; event log may have out-of-order events (`event_amended`). | accepted-and-fixed — `_frs_with_stale_verification` now picks `max(parsed)` rather than `events[-1]`. |
| 3 | OpenAI | MEDIUM | `_parse_iso_ts` emits `warnings.warn`; spec AC-9 said "silently skip". | accepted-and-fixed — spec AC-9 updated to require the warning (silent skip alone hides corrupt event streams). |
| 4 | OpenAI | MEDIUM | Sort-order test only counts occurrences, doesn't verify deterministic ordering. | accepted-and-fixed — `test_multiple_items_per_fr_render_all` now records the two seeded IDs and asserts they appear comma-separated in sorted order. |
| 5 | OpenAI | MEDIUM | No test for `+00:00` suffix (AC-9 explicitly mentions both `Z` and `+00:00`). | accepted-and-fixed — `test_iso_timestamp_with_plus_0000_suffix_accepted` covers it. |
| 6 | Gemini | (truncated) | Response cut mid-sentence while reasoning about malformed last-event semantics. | rejected-with-reason — response inconclusive. The latest-by-max-timestamp fix from OpenAI-M2 incidentally addresses the "malformed last event hides the whole FR" concern Gemini was building toward (the malformed event no longer participates in latest-selection). |

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-b4-rtm-deep-link-and-coverage.md`
- ADR-054 (Triage Producer Contract — D5: cross-link fields)
- ADR-057 (B.3 — first producer populating `event_id`)
- Generator: `plugins/shipwright-compliance/scripts/lib/rtm_generator.py`
- Aggregator (emits the `<a id="trg-XXX">` anchors that the deep-links resolve to): `shared/scripts/tools/aggregate_triage.py`
