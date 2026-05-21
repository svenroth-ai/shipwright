# ADR-059 — Hard-enforce FR-or-change-type at iterate finalize (C.1)

> Long-form spec backing the iterate-2026-05-21-c1-fr-gate-finalize
> ADR drop.

## Audience principle

Solo dev today, leadwright Phase 3 tomorrow. The existing
spec-impact gate covered FEATURE/CHANGE iterates well but exempted
BUG iterates entirely, which historically let internal fixes ship
without any classification at all. A solo dev maintaining a project
for a year ends up with dozens of "fix" events that say nothing
about what surface they touched — making "where did test
infrastructure last change?" or "why is this RTM row stale?" hard to
answer.

The fix is a second, broader gate that asks every iterate for one
of two answers: "I touched FR-X" or "I classify as
docs/tooling/compliance/infra because <reason>". Hard-enforce
because Phase 0 of the campaign already classified all pre-existing
events; there's nothing to migrate forward, only nothing to
regress.

## What landed in C.1 vs forward-looking

| Decision | Realized in this iterate? | Realized where |
|----------|---------------------------|----------------|
| D1 New FR-or-change-type gate predicate    | **Yes** | C.1 (this PR)                                  |
| D2 Hard-error forward-only (no staged rollout) | **Yes** | C.1                                        |
| D3 Read-side stays tolerant                | **Yes (intentional non-change)** | C.1                                |
| D4 Gate runs BEFORE spec-impact gate       | **Yes** | C.1                                            |
| D5 SKILL.md F7 documents the gate          | **Yes** | C.1                                            |
| D6 Formal `event.schema.json` JSON-Schema  | No — out of scope | Future iterate                                 |
| D7 Retroactive audit (Group D6)            | No — out of scope | Future iterate                                 |

## Decisions (C.1)

### D1. New predicate `_fr_or_change_type_gate_error(event)`

25-line pure function. Returns either `None` (pass / bypass) or a
dict `{"error": "fr_gate_unclassified", "detail": "<message>"}`.
Explicit branches for the four states (bypass, pass-via-FRs, pass-
via-change-type, fail) so the test matrix maps 1:1 onto code paths.

### D2. Hard-error forward-only

No staged rollout. Phase 0 retroactively classified every pre-
existing iterate event in the shipwright monorepo and the webui;
there are no legacy unclassified iterates left on disk. New
iterates written from this PR onward MUST pass the gate or the
event isn't written.

Rationale (rejected: staged rollout):

- Single-user repo; no other contributor to coordinate with.
- The shipwright_events.jsonl is gitignored — the only producer of
  events is `/shipwright-iterate`, which we control.
- A staged WARN-then-FAIL rollout adds complexity (which iterate
  flipped the switch?) without buying anything.

### D3. Read-side stays tolerant

`data_collector.WorkEvent.from_dict` already reads `change_type`
and `none_reason` as optional with `None` defaults (Phase 0 prep).
The gate is a write-side guard only. Old events with no
classification continue to parse, and the on-demand
`/shipwright-compliance` audit Group D can flag them if a future
iterate adds a `D6` check.

### D4. FR-gate runs BEFORE spec-impact gate

The FR-gate is the broader requirement (every iterate, incl. BUG);
the spec-impact gate is the stricter check (FEATURE/CHANGE only).
Surfacing the broader requirement first means an unclassified
iterate gets the most actionable error message — "set
--affected-frs OR --change-type" — instead of the more specific
"set --spec-impact" that wouldn't apply yet for BUG.

### D5. SKILL.md F7 documents the gate

The F7 step's spec-impact note now also describes the FR-gate +
the BUG-iterate `--change-type tooling --none-reason '...'` path.
Operators reading SKILL.md before running `record_event.py` see
both gates documented in one place.

### D6. Defense-in-depth check on `change_type` value

Argparse already restricts `--change-type` to `choices=["docs",
"tooling", "compliance", "infra"]` at the CLI boundary. The gate
still validates the value (via `_CHANGE_TYPE_VALUES` constant
membership) so a producer that constructs the event dict directly
via `build_event` can't sneak `change_type="garbage"` through.

### D7. `none_reason` whitespace-stripped before validation

`event.get("none_reason")` must be a `str` AND `.strip()` non-empty.
A producer passing `--none-reason "   "` (whitespace-only) gets
rejected — the gate's purpose is to force a real one-line
justification, not paperwork-shape evasion.

## Consequences

- Every iterate from this PR onward records explicit classification.
  The RTM's "FRs without tests" subsection (B.4) and the compliance
  dashboard's `Recent changes without FR` indicator stay populated
  with real data.

- A BUG iterate that fixes an FR-rooted regression sets
  `--affected-frs FR-X.Y` — the RTM picks up the deep-link (B.4)
  and shows the fix landing.

- A BUG iterate that fixes test plumbing / CI / scanner config
  sets `--change-type tooling --none-reason "<one-line>"`. The
  RTM's "FRs without tests" subsection ignores it (no FR
  associated); the change-history.md keeps the description; the
  one-line justification is the audit trail.

- The error message includes a pointer to SKILL.md step F4 so an
  operator hitting the gate for the first time knows where to
  read the convention.

## Rejected (kept for future me)

- **Staged WARN-then-FAIL rollout** — single-user repo, no
  migration concern. Adds switch-tracking complexity.
- **Treat `--change-type` alone (no `--none-reason`) as
  acceptable** — defeats the gate's purpose (a categorical answer
  without a reason is bureaucratic shape, not classification).
- **Expand the `change_type` enum** — `docs / tooling / compliance
  / infra` is a small fixed vocabulary; expanding it ad-hoc
  invites churn. A new category should require an ADR.

## External-Review-Findings

OpenRouter cascade ran 2026-05-21. 15 findings (OpenAI 10 + Gemini 5).
Medium and high addressed inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | MEDIUM | Confirm full CLI → event → gate path with integration tests. | accepted-and-already-correct — `test_main_passes_with_affected_frs` + `test_main_passes_with_change_type` + `test_main_exits_1_when_gate_rejects` cover the round-trip. |
| 2 | OpenAI | MEDIUM | Non-CLI producers (e.g. `finalize_iterate._record_event`) bypass the gate. | accepted-and-documented — gate scope matches the existing spec-impact gate (CLI boundary only). Tightening the finalize fallback path is out of scope for C.1; documented in the predicate's docstring. |
| 3 | OpenAI | MEDIUM | Malformed FR list shape (non-list, empty strings). | accepted-and-fixed — `_is_non_empty_fr_list` requires `isinstance(value, list) AND at least one trimmed non-empty string`. Tests: `test_empty_list_affected_frs_rejected`, `test_list_of_empty_strings_rejected`, `test_tuple_affected_frs_rejected`. |
| 4 | OpenAI | LOW    | Invalid `change_type` alongside valid FRs should be rejected. | accepted-and-fixed — if `change_type` is present at all, it must be in the canonical set. Test: `test_invalid_change_type_rejected_even_when_frs_present`. |
| 5 | OpenAI | MEDIUM | `none_reason` constraints (multi-line, length, control chars). | accepted-and-fixed — `_is_valid_none_reason` enforces single-line, ≤280 chars, no control chars (tab allowed). Tests: `test_multiline_none_reason_rejected`, `test_oversized_none_reason_rejected`, `test_control_chars_in_none_reason_rejected`, `test_tab_in_none_reason_allowed`, `test_valid_none_reason_at_max_length`. |
| 6 | OpenAI | MEDIUM | Atomicity — no side effects before gate. | accepted-and-already-correct — `main` runs `build_event()` (pure construction) → gate check → `append_event()`. No write before the gate. `test_main_exits_1_when_gate_rejects` asserts `shipwright_events.jsonl` doesn't exist after rejection. |
| 7 | OpenAI | LOW    | Read-side surfaces need to display `change_type`/`none_reason`. | deferred — RTM's "FRs without tests" subsection (B.4) already surfaces classification gaps; a future iterate can add a Coverage-Summary "Recent tooling iterates" subsection if useful. Out of scope for C.1. |
| 8 | OpenAI | LOW    | Gate at common event-recording boundary (not just `main`). | accepted-and-documented — same scope as the existing spec-impact gate. The gate's docstring explicitly calls out the `finalize_iterate._record_event` bypass; future hardening can move both gates into `append_event`. |
| 9 | OpenAI | LOW    | `detail` string echoes user input → log noise. | accepted-and-already-correct — the `detail` is producer-fixed text. The only user value interpolated is `change_type` (when invalid), wrapped in `repr()` to make the leak attempt visible. |
| 10 | OpenAI | LOW    | Missing `type`/`source` keys could KeyError in pure predicate. | accepted-and-fixed — predicate uses `.get()` throughout and explicitly handles `not isinstance(event, dict)`. Tests: `test_malformed_dict_input_clean_bypass`. |
| 11 | Gemini | MEDIUM | Empty list `[]` for FRs should fail like missing field. | accepted-and-fixed — `_is_non_empty_fr_list` rejects empty lists. Test: `test_empty_list_affected_frs_rejected`. |
| 12 | Gemini | MEDIUM | Mutual exclusivity / contradictory FRs + invalid change_type. | accepted-and-fixed — invalid `change_type` is rejected regardless of FR presence. |
| 13 | Gemini | MEDIUM | Hard-fail could break automated CI scripts. | accepted-and-documented — the monorepo's only `record_event.py` callers (F7 in SKILL.md + finalize_iterate) are inventoried. F7 always supplied `--affected-frs` / `--spec-impact`. The finalize fallback path bypasses the CLI gate (documented). |
| 14 | Gemini | LOW    | Argparse cross-arg validation for change_type + none_reason. | rejected-with-reason — the gate produces the canonical error message at one boundary; CLI-side validation would split the rule across two boundaries. Test `test_change_type_without_none_reason_rejected` covers it. |
| 15 | Gemini | LOW    | XSS via `none_reason` in webui. | rejected-with-reason — webui's concern, not record_event's. The webui markdown render already escapes content; this is the wrong layer for the fix. |

## External-Code-Review-Findings

OpenRouter cascade ran 2026-05-21 on the staged diff. 5 findings
(OpenAI 4 + Gemini 1, Gemini truncated mid-finding). Addressed inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | MEDIUM | `_is_valid_none_reason` enforces stricter rules (no newlines, max length, no control chars) than the spec AC describes. | accepted-and-fixed (spec) — iterate spec D7 + "Review-driven additions" section explicitly document the stricter constraints. ADR-059 D7 records the design choice. |
| 2 | OpenAI | MEDIUM | change_type-invalid + FRs-valid event is rejected; spec AC-3 says "any one pass condition suffices". | rejected-with-reason — iterate review #4 (OpenAI) and #12 (Gemini) explicitly asked for strict-data-on-disk semantics. Spec AC-4 + ADR D6 codify it. |
| 3 | OpenAI | MEDIUM | Non-dict input silently bypasses; spec implied fail-closed. | rejected-with-reason — programming errors (passing non-dict to a pure predicate) should surface as the caller's TypeError, not be conflated with classification rejection. `test_malformed_dict_input_clean_bypass` asserts the bypass; the CLI never produces non-dict input. |
| 4 | OpenAI | LOW    | `test_main_passes_with_change_type` only checks stdout, not on-disk event. | accepted-and-fixed — assertion strengthened to read `shipwright_events.jsonl` and verify `"type":"work_completed"`, `"change_type":"tooling"`, `"none_reason":"fix flaky CI"` all serialized. |
| 5 | Gemini | MEDIUM (truncated) | When `change_type` is present, validate `none_reason` even if FRs are also present (pair-integrity rule). | accepted-and-fixed — `_fr_or_change_type_gate_error` now validates the FULL `(change_type, none_reason)` pair as soon as `change_type` is non-None, regardless of FR presence. Tests: `test_change_type_without_reason_rejected_even_with_frs`, `test_change_type_with_invalid_reason_rejected_even_with_frs`. |

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-c1-fr-gate-finalize.md`
- Existing spec-impact gate (ADR-source: iterate-2026-05-16-spec-impact-gate)
- Generator: `shared/scripts/tools/record_event.py` (`_fr_or_change_type_gate_error`)
- Operator docs: SKILL.md F7 (iterate plugin)
- Compliance audit (future Group D6): `plugins/shipwright-compliance/scripts/audit/audit_detector.py`
