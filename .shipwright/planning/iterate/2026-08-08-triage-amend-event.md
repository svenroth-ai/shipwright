# Iterate Spec: Triage `amend` Event

**Run ID:** iterate-2026-08-08-triage-amend-event
**Status:** implemented
**Intent:** CHANGE
**Complexity:** medium
**Trigger:** triage card `trg-b310add8` (P2.46) — operator brief, 2026-08-07/08

## Problem

The triage store (`.shipwright/triage.jsonl`) is append-only with two event
kinds: `append` (mint a card) and `status` (flip its status). There is no way
to correct a card's `title`/`detail`/`severity` in place. The only recourse is
dismiss-and-re-file, which mints a new id and breaks any cross-reference to
the old one. Measured over 2026-08-05/07: ~30 cards dismissed and re-filed for
content-identical corrections (one wave alone: 23 cards / 46 events), on a
premise that later turned out wrong — pure churn, no data loss, but real
friction and history noise ("dismissed: retitled as X" forces chasing down X).

## Why append-only stays

The store's git-tracked, `merge=union` + triage-specific dedup design is what
let ~12 concurrent worktrees write to it this week with zero conflicts. A
mutable file reintroduces the N(N-1)/2 collision class `DERIVED_SNAPSHOTS`
exists to prevent. This change adds a **third append-only event kind**, it
does not touch mutability.

## Shape (operator-specified, non-negotiable)

```json
{"event":"amend","id":"trg-x","title":"...","detail":"...","by":"...","ts":"..."}
```

Folded into `read_all_items`'s existing second pass — the SAME pass that
already applies `status` events, ordered together by `(ts, file-order)`, not a
separate third pass. A field absent from an amend line leaves the
corresponding stored field untouched (a title-only correction is a
title-only amend). A field PRESENT but invalid (e.g. an unknown severity)
invalidates the whole event — skip whole, never half, mirroring the existing
convention for a damaged `status` event.

## Design decisions (guided, not autonomous — operator's own framing)

See mini-plan for the three decisions and their resolution, confirmed with
the operator before build:

1. Which fields are amendable
2. Who may write an amend event
3. Which readers must learn the new event type this iterate, and which are
   explicitly deferred with a documented reason

## Acceptance Criteria

- [x] AC1: `triage.amend_triage_item()` appends a well-formed `amend` event;
  validates the same way `append_triage_item` validates optional fields;
  rejects a contentless amend (no amendable field present).
- [x] AC2: `read_all_items` resolves an amend correctly: present fields
  (`title`/`detail`/`severity`/`kind`) overlay, absent fields are untouched,
  ordering is `(ts, file-order)` interleaved with `status` events in the
  same pass (not a separate pass). The resolved item's `ts` is NOT
  overlaid by an amend (stays "time of last status decision").
- [x] AC3: An amend with an invalid field value (e.g. bad severity) is skipped
  in its entirety — the item's prior state is unchanged, nothing raises.
- [x] AC4: A severity amend recomputes `suggestedPriority` from the new
  severity, matching append's own derivation. (A `kind` amend changes only
  `kind` — there is no `kind`→`suggestedDomain` relationship anywhere in the
  codebase; `suggestedDomain` derives from `source`, which is not amendable.)
- [x] AC5: The resolved item exposes who/when it was last amended
  (`amendedBy`/`amendedAt`), analogous to `statusBy`/`statusReason` for status.
- [x] AC6: `shared/schemas/triage_item.schema.json` gains an `amend` `oneOf`
  branch; every field the writer emits validates; `additionalProperties:false`;
  `anyOf` requires at least one amendable field present.
- [x] AC7: `triage_integrity.is_triage_record` recognizes `amend` — an amend line
  is never misclassified as an unrecoverable corrupt span.
- [x] AC8: `sweep_drift_events._EVENTS` recognizes `amend` — a legitimate amend
  line on main's tracked log is adopted like `append`/`status`, never refused
  as unparseable.
- [x] AC9: A human can write an amend via the CLI (`triage_cli.py`), with an
  actor/`by` value recorded (defaults to `"cli"`).
- [x] AC10: `triage_render.py` and `aggregate_triage.py` display amended
  title/detail/severity correctly with NO code change required (they already
  read whatever `read_all_items` resolves) — verified, not just assumed.
- [x] AC11: `triage_validate.py`'s orphan-amend classification and
  `triage_gc_core.py`'s matching compaction/orphan-validation fix ship
  TOGETHER (never one without the other — an orphan-amend validation error
  without the GC fix self-inflicts a permanent GC block).
- [x] AC12: `sweep_quarantine.decide()` classifies an orphan/protected amend
  the same way it already classifies an orphan/protected status (held when
  protected by a known append elsewhere, quarantined when genuinely
  unreachable), without changing any existing status-path behavior or its
  pinned `protected_status_unplaceable` token.
- [x] AC13: `amend_triage_item()` raises `FileNotFoundError` when neither store
  exists, and `KeyError` when `item_id` names no known `append` anywhere.
- [x] AC14: `amend_triage_item()` probes `should_route_to_outbox` OUTSIDE the
  lock and derives residence INSIDE it, acquiring the canonical lock exactly
  once (never from inside a `read_all_items` call).
- [x] AC15: Deferred-scope items (delivery-visibility parity —
  `pendingAmendDelivery`/`undeliveredAmends` — and the WebUI reader update)
  are explicitly recorded — as an ADR note and as a single follow-up triage
  card — not silently dropped.
- [x] AC16: Card `trg-b310add8` (P2.46) is resolved (promoted/closed) referencing
  this run, once delivered.

## Confidence Calibration
- **Boundaries touched:** `.shipwright/triage.jsonl` (JSONL read/write —
  `touches_io_boundary`), `shared/schemas/triage_item.schema.json` (wire
  contract)
- **Empirical probes run:**
  - Bloat-cap probe: `triage.py` measured at 928/882 lines after the initial
    implementation; iteratively trimmed and re-measured (`wc -l`) after each
    edit down to 881/882, then back to exactly 882/882 once the writer-side
    `check_amend_title` guard (a fix-round addition) used the last line of
    headroom, then to 881/882 again after the Stage-2 code-review round
    consolidated `check_amend_vocab`+`check_amend_title` into one
    `check_amend_fields` call site, then to exactly 882/882 once more — zero
    headroom — after the Stage-3 doubt-review D1 fix (`amend_triage_item`
    returning `to_outbox`) added back a line, requiring three further rounds
    of docstring compaction plus inlining a `line = json.dumps(...)`
    intermediate straight into the `_append_line(...)` call — never assumed
    under budget, always re-measured after edit.
  - Real-file round-trip probe (`test_amend_round_trips_unicode_and_special_characters`):
    an amend carrying unicode/quotes/newlines/backslashes written to an actual
    disk file, then read back fresh, byte-for-byte compared; raw bytes
    inspected to confirm `ensure_ascii=False` (no `\uXXXX` escaping).
  - AC10 (no-code-change consumers) EMPIRICALLY verified, not assumed: a
    throwaway probe script appended an item, amended it, then called
    `triage_render.format_item` and `aggregate_triage.render_markdown`
    directly — both rendered the AMENDED title/severity with zero production
    code touched.
  - Pre-existing-failure isolation probe: two `test_triage_precondition_callers.py`
    failures surfaced when run alongside `test_triage_write_path_contracts.py`;
    reproduced identically on `git stash`-ed pre-change code, confirming a
    pre-existing test-composition artifact, not a regression from this change.
  - CLI subprocess probe: `triage_cli.py amend` exercised via real subprocess
    invocation (exit codes 0/2, argparse `choices` rejection, stderr wording)
    before the dedicated test file existed.
- **Test Completeness Ledger:**

  | Behavior | AC | Status | Evidence |
  |---|---|---|---|
  | Writer builds well-formed amend, rejects contentless | AC1 | tested | `test_triage_amend_event.py::test_amend_rejects_contentless_call` + `test_triage_amend.py::test_build_amend_event_*` |
  | Writer rejects unknown severity/kind | AC1 | tested | `test_amend_rejects_unknown_severity`, `test_amend_rejects_unknown_kind` |
  | Writer rejects a blank/whitespace-only title (mirrors `append_triage_item`; blank never reaches the wire schema, whitespace-only never reaches the reader as an inert no-op) | AC1/AC6 | tested | `test_amend_rejects_an_empty_title`, `test_amend_rejects_a_whitespace_only_title` |
  | Reader overlay: present overlays, absent untouched, `(ts,file-order)` merged with status | AC2 | tested | `test_amend_overlays_present_fields_leaves_absent_untouched`, `test_amend_ordering_interleaves_with_status_by_ts`, `test_multiple_amends_last_valid_wins_per_field` |
  | Ordering: equal-ts file-order tiebreak, malformed-ts sorts earliest, status+amend same-ts both apply, later invalid amend doesn't clobber prior valid metadata | AC2 | tested | `test_equal_ts_amends_tiebreak_on_file_order`, `test_malformed_ts_amend_sorts_earliest`, `test_status_and_amend_at_the_same_ts_both_apply`, `test_later_invalid_amend_does_not_clobber_a_prior_valid_amends_metadata` |
  | `item["ts"]` never overlaid by an amend | AC2 | tested | `test_amend_does_not_overlay_item_ts` |
  | Invalid-field amend skipped WHOLE | AC3 | tested | `test_amend_with_invalid_field_is_skipped_whole` + `test_triage_amend.py::test_try_apply_amend_skips_whole_event_on_any_invalid_field` |
  | Severity amend recomputes `suggestedPriority`; kind has no domain side effect | AC4 | tested | `test_amend_severity_recomputes_suggested_priority`, `test_amend_kind_change_does_not_alter_suggested_domain` |
  | `amendedBy`/`amendedAt` exposed, default `by="cli"` | AC5 | tested | `test_amend_defaults_by_to_cli`, `test_apply_amend_records_amended_by_and_at` |
  | Schema `amend` branch: valid/contentless/unknown-key/bad-enum | AC6 | tested | `test_triage_amend_schema.py` (5 cases) |
  | `is_triage_record` recognizes amend; forged content-empty amend refused DURING BOUNDARY RESYNC (Stage-3 doubt review, finding 7: `is_triage_record` is consulted only by `_resync`, after genuine line damage — a contentless amend arriving on its own well-formed line is a separate, narrower gap: it passes `validate_amend_event` unmolested, since that function deliberately does not call `has_amend_content`, and overlays only `amendedBy`/`amendedAt` while changing no other field) | AC7 | tested | `test_triage_record_boundary_recovery.py` (4 new cases, boundary-resync scope only) |
  | `triage_repair` splits and preserves an append+amend glued line end-to-end | AC7 | tested | `test_triage_repair.py::test_apply_splits_an_append_amend_glued_line_and_preserves_both` |
  | `sweep_drift_events._EVENTS` adopts amend | AC8 | tested | `test_sweep_drift_events_amend.py` |
  | CLI `amend` subcommand, `by` fixed to `"cli"` | AC9 | tested | `test_triage_cli_amend.py` (5 cases) + live subprocess probe |
  | `triage_render`/`aggregate_triage` display amended fields, NO code change | AC10 | tested (empirical probe, not code-reading) | inline probe scripts, see above |
  | Validator + GC orphan-amend classification, bound together; GC dry-run report reflects amended fields | AC11 | tested | `test_triage_gc_amend.py` (4 cases, incl. the self-inflicted-block guard and the `plan_gc` report-overlay case) |
  | Orphan-amend surfaces through the three real `validate_triage_text` consumers the same way orphan-status already does | AC11 | tested | `test_ensure_current_triage_absorb_guards.py::test_absorb_skips_an_orphan_amend_same_as_an_orphan_status`, `test_resolve_churn_conflicts_triage.py::test_triage_invalid_on_orphan_amend_same_as_orphan_status`, `test_reconcile_triage.py::test_orphan_amend_is_invalid_same_as_orphan_status` |
  | Sweep quarantine orphan/protected amend, pinned status token unchanged, NEW distinct `protected_amend_unplaceable` token, clean happy path | AC12 | tested | `test_sweep_quarantine_amend.py` (8 cases, incl. the CLEAN happy path and the two-token block case) |
  | `FileNotFoundError`/`KeyError` contract | AC13 | tested | `test_amend_raises_filenotfound_when_store_missing`, `test_amend_raises_keyerror_for_unknown_id` |
  | Lock acquired exactly once, probe outside lock | AC14 | tested | `test_amend_triage_item_acquires_the_canonical_lock_exactly_once` |
  | Deferred scope recorded (ADR note + one follow-up card) | AC15 | tested (existence verified, not a unit test) | mini-plan "External LLM plan review" section + `trg-d5ef8039` read back via `read_all_items` |
  | Card `trg-b310add8` resolved referencing this run | AC16 | tested (existence verified) | `triage_promote.promote()` return value: `newStatus="promoted"`, `promotedTaskId="iterate-2026-08-08-triage-amend-event"` |
  | Writer rejects a non-string title/detail (Stage-2 review finding 1: a non-str `detail` would otherwise write past the schema and be silently skipped WHOLE on read, discarding a co-submitted valid `title` too) | AC1 | tested | `test_amend_rejects_a_non_string_title`, `test_amend_rejects_a_non_string_detail`, `test_triage_amend.py::test_check_amend_title_rejects_a_non_string`, `::test_check_amend_detail_rejects_a_non_string` |
  | Argument validation runs BEFORE any I/O, mirroring `mark_status` (Stage-2 review finding 2) | AC1/AC13 | tested | `test_amend_validates_arguments_before_checking_store_existence` |
  | `_resolve_tracked_only` initializes `amendedBy`/`amendedAt` for every item, not only amended ones (Stage-2 review finding 3 — shape parity with `read_all_items`) | AC11 | tested | `test_triage_gc_amend.py::test_resolve_tracked_only_initializes_amended_fields_for_unamended_items` |
  | Wire schema rejects a whitespace-only title on both `append` and `amend` branches (Stage-2 review finding 6 — closes the gap for non-Python writers) | AC1/AC6 | tested | `test_triage_amend_schema.py::test_amend_with_whitespace_only_title_fails_schema`, `::test_append_with_whitespace_only_title_fails_schema` |
  | `sweep_drift_events` glued-amend-line reason code (replaces a redundant duplicate assertion flagged by Stage-2 review finding 9) | AC8 | tested | `test_sweep_drift_events_amend.py::test_an_amend_line_glued_to_another_record_gets_the_glued_reason_code` |
  | `validate_triage_text`'s second pass reports orphan status/amend errors in FILE order, not kind-major order (Stage-2 review finding 11) | AC11 | tested | `test_triage_validate.py::test_orphan_amend_and_status_errors_report_in_file_order` |
  | CLI notes when an amend lands in the outbox, not tracked (Stage-3 doubt review D1 — the only operator-visible delivery signal, given AC15's deferred scope) | AC9/AC15 | tested | `test_triage_cli_amend.py::test_amend_on_idle_main_notes_it_landed_in_the_outbox` + `::test_amend_positional_id_happy_path`'s negative assertion (no note on a plain tracked write) |
  | Orphan amend quarantined under its OWN reason text, not a borrowed `"status"` string (Stage-3 doubt review D3) | AC12 | tested | `test_sweep_outbox_dispositions_integration.py::test_orphan_amend_is_quarantined_with_its_own_reason` |
  | `_resolve_tracked_only` (GC path) resolves status+amend in the same two-pass `(ts, file-order)` order as `read_all_items`, not one interleaved file-order pass (Stage-3 doubt review D4) | AC11 | tested | `test_triage_gc_amend.py::test_resolve_tracked_only_handles_an_amend_preceding_its_append_in_file_order`, `::test_resolve_tracked_only_resolves_two_same_id_amends_by_ts_not_file_order` (both proven to fail under the pre-fix single-pass code) |
  | A held status id no longer makes an unrelated glued amend look "withheld" (Stage-3 doubt review D6 — `held_ids` split by event kind) | AC12 | tested | `test_sweep_block_diagnostics.py::test_a_held_status_does_not_make_a_glued_amend_look_held_too` |
  | `apply_amend` collapses a non-string forged `by`/`ts` to `None` instead of raising `AttributeError` downstream (Stage-3 doubt review D7, mirrors `mark_status`'s existing non-str-`status` guard) | AC5 | tested | `test_triage_amend.py::test_apply_amend_collapses_a_non_string_by_and_ts_to_none` |
  | `lib.triage_fields` (new lazy-loaded leaf) resolves under ADR-045 sentinel mode (Stage-3 doubt review D9) | — | tested | `test_jsonl_records_load_modes.py::test_triage_fields_sentinel_mode_resolves_severities_and_kinds` |

  0 untested-testable behaviors.
- **Confidence-pattern check:**
  - *Depth (asymptote):* four independent review rounds (internal Opus →
    external plan review, 2 providers → architecture review, 2 providers →
    Stage-2 code-reviewer, post-implementation) each surfaced real, distinct
    issues (false derivation, zero-headroom bloat collision, under-specified
    writer parity, wrongly-decoupled validator/GC, forged-record gap,
    module-naming cohesion, a silently-lossy `detail` type gap, an
    I/O-before-validation ordering bug, a GC shape asymmetry, a stale wire
    constraint, a kind-major error-ordering bug); the architecture round
    returned zero findings from either provider, and the Stage-2 round's
    findings were all closed with tests in the same pass — convergence, not
    fatigue.
  - *Breadth (coverage):* every module the mini-plan's Repo Scout identified
    as touching the store's event-kind vocabulary is now amend-aware (leaf
    modules, `triage.py` core + schema, `triage_integrity`, `triage_validate`
    + `triage_gc_core`, `sweep_quarantine`, `sweep_drift_events`,
    `triage_cli`) — 80+ new tests added across the build and the Stage-2
    fix round, 0 regressions across the full `shared/tests` suite (1389
    passed before the fix round; re-run after). What is explicitly OUT of
    scope (delivery-visibility widening, WebUI TS reader) is named in
    AC15/the follow-up card, not silently dropped.

## Architecture Review

**Internal Opus plan review (2026-08-08):** approve-with-changes. 4 HIGH
findings (a false `kind`→`suggestedDomain` derivation; `triage.py` at its
exact bloat cap with zero headroom; the amend writer under-specified
relative to `mark_status`'s routing/lock/error parity; the validator and GC
fixes wrongly treated as independently deferrable) plus 5 MEDIUM and 3 LOW —
all folded into the mini-plan before external review. Full findings
recorded in the mini-plan's "Internal Opus plan review" section.

**External plan review (`--mode iterate`, 2026-08-08):** openai=`revise`,
deepseek=`approve`, no contradiction. 6 findings from openai (a real
forged-record gap at the corruption boundary — a key-complete but
contentless amend would pass `is_triage_record`; a module-naming/cohesion
issue from bundling amend-agnostic and amend-specific helpers together;
plus lower-severity test-coverage and stale-text findings), 4 from deepseek
(verification-only, no design change). All folded into the mini-plan.

**Architecture review (`--mode architecture`, 2026-08-08):** openai=`approve`,
deepseek=`approve`, no findings from either. Both independently confirmed
Option A (a third append-only event kind in the existing store, folded into
the existing resolution pass) as "the smallest thing that would do," and
both named the same permanent cost explicitly: every current and future
consumer of the store must learn to recognize `amend`, mirroring the
obligation `status` already imposes. Full brief:
`.shipwright/planning/iterate/iterate-2026-08-08-triage-amend-event/architecture_brief.md`.

## Doubt Review (Stage-3, post-implementation)

Fresh-context adversarial pass over the finished diff, biased to disprove.
9 findings (D1-D9); every one closed with either a code fix + regression
test, or (D2 only) a written rebuttal, per the reviewer's own closing rule.

- **D1** (should-not-ship-unanswered): delivery-visibility parity for
  `amend` is explicitly deferred (AC15), so on idle main the CLI's success
  message was the operator's ONLY signal a correction hadn't reached any
  branch — and it said nothing. **Fixed**: `amend_triage_item` now returns
  whether the write landed in the outbox; `cmd_amend` prints a one-line note
  when it did. `test_amend_on_idle_main_notes_it_landed_in_the_outbox` +
  `test_amend_positional_id_happy_path`'s new negative assertion cover both
  branches.
- **D2** (should-not-ship-unanswered): (a) a stale plugin-cache copy of
  `sweep_drift_events.py` — one still missing `"amend"` from `_EVENTS` —
  would jam the ENTIRE outbox delivery pipeline for EVERY event kind, not
  only amend, since the sweep can't classify past the first unrecognized
  line; (b) the WebUI's TypeScript reader's behavior on an unrecognized
  `amend` line is unverified from this repository (it's a separate repo).
  **Rebuttal, not a code fix**: (a) is not a new risk this diff introduces —
  `CLAUDE.md`'s "When editing plugin-side files" section already makes
  `scripts/update-marketplace.sh` + `check_plugin_cache_sync.py --strict`
  a standing, mandatory step after every `shared/scripts/` push, for
  exactly this reason (a prior staleness incident is cited by name: "cost
  iterates 7-11 their fixes"). This diff doesn't weaken or bypass that gate;
  it relies on the existing one, same as every other `shared/scripts/`
  change before it. What IS new here is naming the specific failure shape
  (a stale sweep jams ALL delivery, not just amend's) so the next person
  reading this file understands the stakes of skipping the sync step — that
  context is recorded in this paragraph since there's nowhere more specific
  to pin it. (b) is recorded as an explicit open question on card
  `trg-d5ef8039` (the AC15 follow-up) rather than guessed at: this repo has
  no visibility into `shipwright-webui`'s reader, and asserting it "handles
  it gracefully" without reading that code would be exactly the kind of
  confident-but-unverified claim this review round exists to catch.
- **D3**: orphan `amend` lines were quarantined under the SAME hardcoded
  `"status"` reason text as orphan `status` lines. **Fixed**: `sweep_quarantine.py`
  now tags each quarantined line with its actual event kind via
  `quarantine_reason(event)`; `test_orphan_amend_is_quarantined_with_its_own_reason`
  (full git-repo integration test) confirms the `reason` field starts with
  `"un-deliverable amend"`.
- **D4**: `_resolve_tracked_only` (GC path) applied status+amend events in a
  single interleaved file-order pass instead of `triage.read_all_items`'s
  two-pass `(ts, file-order)` resolution — a real behavioral divergence
  between the two readers. **Fixed**: rewritten to mirror `read_all_items`
  exactly, in a new `lib/triage_gc_resolve.py` (extracted to keep
  `triage_gc_core.py` under the 300-LOC guideline). Two regression tests
  proven to fail under the old single-pass code and pass under the new one.
- **D6**: a held `status` line's id could make an unrelated, never-a-hold-
  candidate `amend` line look "withheld" in a block message, because both
  kinds shared one `held_ids` set. **Fixed**: split into `held_status_ids`/
  `held_amend_ids`, threaded separately through `block_errors()`.
  `test_a_held_status_does_not_make_a_glued_amend_look_held_too` regresses it.
- **D7**: a forged/hand-edited `amend` line with a non-string `by`/`ts`
  raised `AttributeError` deep in a consumer instead of degrading like
  `mark_status`'s existing non-str-`status` guard. **Fixed**: `apply_amend`
  now collapses a non-str `by`/`ts` to `None`, keeping both `str | None` for
  every consumer; `test_apply_amend_collapses_a_non_string_by_and_ts_to_none`
  regresses it.
- **D9**: `lib.triage_fields` (the NEW lazy-loaded leaf this iterate
  introduced for `SEVERITIES`/`KINDS`) had no ADR-045 sentinel-mode test,
  unlike the pre-existing leaves it sits beside. **Fixed**:
  `test_triage_fields_sentinel_mode_resolves_severities_and_kinds` pins the
  fallback path directly (a full shadowed `triage_cli.py` import was
  rejected as unrealistic — see that test's docstring for why).
- **D5, D8**: doc/probe findings, already closed inline — D5 (docs claimed
  "four verbs," amend made it five) fixed in `docs/guide.md` and
  `docs/security-ci-setup.md`, regressed by
  `test_the_documents_describe_the_amend_subcommand`; D8 was a bloat-cap
  headroom re-measurement, not a defect (see Confidence Calibration above).
