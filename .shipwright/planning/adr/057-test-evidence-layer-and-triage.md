# ADR-057 — Test Evidence Layer column + per-layer FAIL triage (B.3)

> Long-form spec backing the iterate-2026-05-21-b3-test-evidence-layer-and-triage
> ADR drop. The drop's `--spec-ref` points here so future readers don't
> have to reconstruct the design rationale from commits.

## Audience principle

Same as ADR-054 / 055 / 056: solo dev today, leadwright Phase 3 tomorrow.
Test failures are the loudest signal in any compliance run; the
producer must (a) say *what* is red and (b) hand the operator the
single command to fix it. Per-test noise (one card per failing case)
violates the audience principle — solo dev fixes whole layers in a
session, not test-by-test.

## What landed in B.3 vs forward-looking

| Decision | Realized in this iterate? | Realized where |
|----------|---------------------------|----------------|
| D1 Layer column on Test Progression          | **Yes** | B.3 (this PR)                                                            |
| D2 Integration / pgTAP columns on Full Suite | **Yes** | B.3                                                                      |
| D3 record_event layers-schema extension      | **Yes** | B.3                                                                      |
| D4 TestRunEvent legacy-event tolerance       | **Yes** | B.3                                                                      |
| D5 Per-layer FAIL triage producer            | **Yes** | B.3                                                                      |
| D6 `event_id` dogfood (ADR-054 D5)           | **Yes** | B.3                                                                      |
| D7 Auto-dismiss on green                     | **Yes** | B.3                                                                      |
| D8 Per-test failure IDs for non-e2e layers   | No — out of scope | Future iterate when wire format extends                       |

## Decisions (B.3)

### D1. Test Progression Layer column — 4-state classifier

The new `Layer` column on the `## Test Progression` table classifies
each `work_completed` event into one of:

| Source signal                                 | Layer       |
|----------------------------------------------|-------------|
| `tests.total > 0 AND tests.e2e_run = true`   | `mixed`     |
| `tests.e2e_run = true` only                  | `e2e`       |
| `tests.total > 0` only                       | `unit`      |
| neither                                      | `—`         |

Derived from existing wire fields — no schema change to work_completed
events. Integration / pgtap layers aren't surfaced here (those live on
test_run events). A future iterate can add a `tests.layers` array to
work_completed events if per-work-event integration/pgtap visibility
becomes needed.

### D2. Full Suite Runs table — 4-layer breakdown

The `## Full Suite Runs` table now renders one column per layer:

```
| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |
```

Layers with `total == 0` render as `—` (e.g. a Postgres-less project
shows `pgTAP: —` permanently — informative, not alarming). Sourced
from the new `layers.integration` and `layers.pgtap` keys on test_run
events.

### D3. `record_event.py` schema extension

New CLI flags `--integration-passed`, `--integration-total`,
`--pgtap-passed`, `--pgtap-total`. Behavior mirrors the existing
unit/e2e flags: emit a per-layer sub-dict in `layers` when at least
one flag is set. Legacy producers without the new flags continue
emitting the 3-key (`unit`, `e2e`, `smoke`) shape.

### D4. `TestRunEvent` reader tolerance

`from_dict` reads the new keys via `layers.get(<name>, {})`. Missing
keys default to `0` so the dashboard / RTM / Test Evidence reports
never crash when scanning historical test_run events written before
this iterate.

### D5. Per-layer FAIL triage producer

Closes ADR-054 D2 + D3. Reads the latest test_run event and emits one
`source="test-evidence"` triage item per failing layer:

- `dedup_key = "test-fail:<layer>"` (one card per layer)
- `severity` — layer-based (ADR-054 D3):
  - `e2e` / `integration` / `pgtap` → `high`
  - `unit` → `low`
- `kind = "bug"`
- `event_id = <latest test_run id>` — dogfoods ADR-054 D5 cross-link
- `launchPayload = "/shipwright-iterate --type bug"` + a layer-scoped
  context block

Auto-dismiss: any currently-`triage` `source="test-evidence"` item
whose `dedupKey` isn't in this run's set of failing layers flips to
`dismissed` with `reason="testEvidenceResolved"`. Promoted / dismissed
items stay terminal (audit_detector HIGH-2 contract).

Window-less idempotent dedup (`window_seconds=None`) — the same
failing layer is one issue, persistent across days until the operator
fixes it.

### D6. `event_id` dogfoods ADR-054 D5

Every triage card carries the originating test_run's event ID under
the wire key `eventId`. The compliance RTM render in B.4 will use this
to deep-link a failing FR row to the matching triage card. B.3 is the
first real producer to populate `event_id`; before this, every
producer left it null.

### D7. Detail body — top-10 for e2e, count-only for others

For the `e2e` layer the detail body lists the top-10 failing test IDs
sorted alphabetically from `data.test_results.e2e_failures`
(shipwright_test_results.json) plus a `+N more` footer when >10.

For `unit` / `integration` / `pgtap` the body states the failing
count and points the operator at `test-evidence.md`:

> N/M failing in <layer>. See test-evidence.md for the full breakdown.

This asymmetry exists because the test-result wire format only carries
per-test failure lists for e2e (`e2e.failures`). When the wire format
extends to carry per-test lists for other layers, the `_failure_detail`
helper consumes them through the same boundary.

### D8. Out of scope — per-test failure IDs for unit / integration / pgtap

The plan suggested top-10 failing test-IDs per layer. The producer
honors this for e2e (data exists) but not for the other layers (data
absent on the wire). Promoting this would require extending
`shipwright_test_results.json` to carry per-test failure lists for all
layers — a separate iterate that touches the test plugin's output
format. Out of scope here.

## Consequences

- Every `/shipwright-iterate` compliance run emits one card per failing
  test layer. Solo dev sees them in the inbox with `Fix-now` payloads
  pre-loaded with the right `/shipwright-iterate --type bug` invocation.

- ADR-054 D2 + D3 + D5 are now realized end-to-end on the producer side.
  RTM-side rendering of FAIL → triage links lands in B.4.

- `update_compliance.py` output carries two triage telemetries: existing
  `sbom_triage` (B.2) and the new `test_evidence_triage`. Both share the
  same `{appended, dismissed, error?}` shape.

- Existing producers that emit test_run events without integration/pgtap
  flags continue working unchanged — no migration required.

## Rejected (kept for future me)

- **`(layer, suite)` granularity** — ADR-054 D2 already rejected:
  inflates the inbox during multi-suite outages without ergonomic gain.
- **Severity `info` for unit failures** — would collapse into the
  `<details>` block, defeating launch-surface purpose. `low` keeps
  unit failures visible but quiet.
- **One triage item per failing test** — drowning noise; ADR-054 D2.
- **Auto-emit a per-test-event triage on every Stop hook** — too
  reactive; let the compliance run own emit so the operator gets one
  burst, not 50 per-Stop pings.

## External-Review-Findings

OpenRouter cascade ran 2026-05-21. Gemini + OpenAI returned 18 findings
combined. High and medium addressed inline before commit.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1  | Gemini | HIGH   | `passed < total` heuristic produces false positives for skipped tests. | accepted-and-fixed — added optional `failed` field on every layer (CLI `--<layer>-failed N`); producer prefers explicit count, falls back to `total-passed`. Covered by `test_skipped_tests_not_counted_as_failures` + `test_explicit_failed_triggers_emit`. |
| 2  | Gemini | MEDIUM | Producer crashes when `shipwright_test_results.json` is absent. | rejected-with-reason — `data.test_results.e2e_failures` is read via `(data.test_results.e2e_failures if data.test_results and ... else [])`. Missing file means `test_results is None`; the conditional already falls back to empty list. |
| 3  | Gemini | MEDIUM | Orphan cards when a layer is removed (total=0). | accepted-and-fixed — `*_evaluated` flag distinguishes "layer omitted" from "layer reported as zero". Both cases now intentionally do NOT auto-dismiss prior cards (operator must positively assert resolution). `test_omitted_layer_does_not_dismiss_prior_card` covers it. |
| 4  | Gemini | LOW    | `event.get("layers").get(...)` crashes on `null`. | accepted-and-fixed — `d.get("layers") or {}` plus per-layer `or {}` chain. |
| 5  | Gemini | LOW    | Markdown injection via test IDs. | accepted-and-fixed — `_sanitize` strips control chars; e2e IDs wrapped in backticks. `test_detail_strips_control_characters` covers it. |
| 6  | OpenAI | MEDIUM | Underlying `TestRunEvent` dataclass schema. | accepted-and-already-correct — `TestRunEvent` updated with `*_failed: int \| None` + `*_evaluated: bool`. Read-side defaults keep legacy events working. |
| 7  | OpenAI | MEDIUM | Partial pairs (`passed` without `total`). | accepted-and-fixed — `build_event` rejects `passed > total` / `failed > total`; partial pairs land as-is but don't trigger the FAIL path because `total > 0` gate isn't met (covered by `test_only_passed_flag_still_creates_layer`). |
| 8  | OpenAI | HIGH   | No validation for negative / non-integer counts. | accepted-and-fixed — `_non_negative_int` argparse type. `test_negative_value_rejected_at_cli` + `test_non_integer_rejected_at_cli` + `test_passed_exceeds_total_rejected` cover it. |
| 9  | OpenAI | MEDIUM | "Latest test_run" selection rule underspecified. | accepted-and-documented — docstring explicitly states "last in file order; `collect_events` preserves append order". Inline comment in `emit_test_failure_triage`. |
| 10 | OpenAI | MEDIUM | Auto-dismiss filters by `source` AND `dedup_key`. | accepted-and-already-correct — emit code checks `item.get("source") != _TRIAGE_SOURCE: continue` and `not dk.startswith(_TRIAGE_DEDUP_PREFIX)`. `test_emit_does_not_touch_non_sbom_items` from B.2 covers the sibling pattern; this iterate's tests inherit it via the same producer architecture. |
| 11 | OpenAI | MEDIUM | Missing-layer semantics (omitted ≠ green). | accepted-and-fixed — same as Gemini #3. |
| 12 | OpenAI | MEDIUM | Stale `shipwright_test_results.json` ↔ test_run correlation. | rejected-with-reason — adding strict commit/run-id correlation requires extending both wire formats; out of scope for B.3. Fallback already returns to "count + pointer" body when `e2e_failures` is empty. The detail line points the operator at test-evidence.md for the authoritative breakdown, which is regenerated from the same event log in lockstep with the triage emit. |
| 13 | OpenAI | MEDIUM | Shared post-SBOM/test-evidence hook centralization. | accepted-and-already-correct — both emits live inside `update_compliance.py`'s `for report_name in reports_to_update` loop; any phase whose `PHASE_REPORTS` entry includes `sbom` or `test_evidence` invokes the producer. |
| 14 | OpenAI | LOW    | Markdown column-shape change in Test Evidence. | accepted-and-documented — changelog drop covers the format change; no downstream parsers in the monorepo rely on column index (all consumers use markdown-aware readers). |
| 15 | OpenAI | LOW    | Layer classifier null-safety for legacy WorkEvents. | accepted-and-already-correct — `WorkEvent` dataclass defaults (`tests_total: int = 0`, `e2e_run: bool = False`) ensure the 5-line classifier never NPEs. `test_neither` covers the zero-field case. |
| 16 | OpenAI | MEDIUM | LaunchPayload + detail-body sanitization. | accepted-and-fixed — same as Gemini #5; `_sanitize` applied to detail + failure IDs. LaunchPayload is producer-fixed text (no user input), so no extra escaping needed there. |
| 17 | OpenAI | LOW    | `error` key may leak file paths / internal details. | accepted-and-fixed — error format reduced to `"{phase}:{rel-or-id}:{exc_type}"`; no message content. Inline comment cites OpenAI-L12. |
| 18 | OpenAI | LOW    | Shared dedup/dismiss helper. | deferred — both B.2 and B.3 producers now use the same pattern. Refactor into a `triage_producer_base` module after a third producer (likely C.2) lands, when the abstraction is clearer than the duplication. |

## External-Code-Review-Findings

OpenRouter cascade ran 2026-05-21 on the staged diff. 4 findings
(OpenAI 3 + Gemini 1, Gemini's response truncated mid-finding).
All actionable issues fixed inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | MEDIUM | `_sanitize` preserved `\n` — embedded newlines in failure IDs break the markdown layout despite the backtick wrap. | accepted-and-fixed — sanitize now strips ALL control chars (incl. `\n` / `\r`) and REPLACES them with a space (so `foo\nbar` becomes `foo bar`, not `foobar`); whitespace runs collapse to one. Test `test_detail_strips_control_characters` rewritten to assert no newline survives. |
| 2 | OpenAI | MEDIUM | Test codified the wrong behavior (asserted newline preserved). | accepted-and-fixed — same as #1. |
| 3 | OpenAI | LOW    | Only `--unit-failed` CLI parsing was tested; other three `--<layer>-failed` flags lacked direct tests. | accepted-and-fixed — added `test_integration_failed_serializes`, `test_pgtap_failed_serializes`, `test_e2e_failed_serializes`. |
| 4 | Gemini | MEDIUM (truncated) | Partial-pair allowance for `--unit-failed` without `--unit-passed` / `--unit-total`. | rejected-with-reason — response was truncated; my code DOES allow partial pairs (`failed` alone creates the layer dict with just `failed`). But the FAIL-triage producer requires `total > 0` AND `was_evaluated`, so a partial pair has no triage effect. The wire payload is slightly weird (`{"unit": {"failed": 5}}` without total), but harmless. Documented in the iterate spec's note about partial-pair tolerance. |

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-b3-test-evidence-layer-and-triage.md`
- ADR-054 (Triage Producer Contract — D2/D3/D5)
- ADR-056 (SBOM triage producer — sibling pattern)
- Producer: `plugins/shipwright-compliance/scripts/lib/test_evidence.py` (`emit_test_failure_triage`)
- Event schema producer: `shared/scripts/tools/record_event.py` (test_run layers extension)
- Reader: `plugins/shipwright-compliance/scripts/lib/data_collector.py` (`TestRunEvent`)
- Triage API: `shared/scripts/triage.py` (`append_triage_item_idempotent` with `event_id` kwarg)
