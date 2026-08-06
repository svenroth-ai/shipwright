# Iterate: dead-end states in triage validation and quarantine

- **Run ID:** `iterate-2026-08-06-triage-validate-deadends`
- **Card:** `trg-b854805c` (P2.19b, high/bug), split out of `trg-79102ee3`
- **Evidence:** `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`
- **Intent:** BUG · **Complexity:** medium (Stage-2 upgrade from `small`)
- **Spec Impact:** NONE (behavior of an internal delivery path; no FR surface changes)

## Problem

Three paths through `lib.triage_validate` and `lib.sweep_quarantine` reach a state
that triage delivery never comes back from. Each was reproduced against the
worktree checkout before any code was written (probe output in Confidence
Calibration below).

**(15) No record-boundary recovery in the validator.** `classify_triage_text`
runs `json.loads` on each *physical* line. The log's one-record-per-line
invariant is not enforced at the append boundary, so an interrupted or external
write leaves two records glued onto one line — the documented motivating failure
for `lib.jsonl_records`. The reader recovers such a line (`split_records`), and
the event-log twin `validate_events_text` was converted to `split_records` in
iterate-2026-07-20; the triage validator was not. One glued line therefore reads
as `not valid JSON` → `has_non_orphan_error` → `decide` returns `block` → the
sweep delivers nothing, this run and every future one, while every unrelated
buffered append and every foreign dismiss strands with it. Because
`read_all_items` recovers the same line cleanly, the board shows the item as
applied: the operator has no signal that delivery has stopped. The error text
names no remedy — `triage_repair.py` exists precisely for this and is never
mentioned.

**(17) `protected_status_unplaceable` is an absorbing state.** When a `status`
in the outbox has its `append` in main's *tracked* log but not reachable from
this branch, `decide` blocks — correctly refusing to quarantine, because
quarantining destroys the operator's dismiss and the item resurrects forever
(reproduced live 2026-07-14). But the remedy it prints — "deliver main (push /
merge origin), then re-run" — is unreachable: in this workflow `main` is never
pushed directly, it is only fast-forwarded from origin. So the block is
permanent, it strands the entire rest of the outbox with it, and the buffer
holding all of it is gitignored — one `git clean -xfd` from empty.

**(18) A status with a missing or non-`str` id has no disposition at all.** The
second pass records the error but adds the id to `orphan_status_ids` only
`if isinstance(iid, str)`. So `decide` sees errors, no orphan ids, and
`has_non_orphan_error == False` → `block`. Quarantine cannot select the line
(selection is by id); `triage_repair` cannot fix it (the JSON is valid). Dead
end. This finding was never assigned to a successor card — it was missed when
`trg-4ebc928e` was split.

## The shape of the fix

`decide` today has three outcomes and only two make progress, so any line the
sweep cannot place takes the whole outbox down with it. The fix gives each error
class a **proportional** disposition and narrows `block` to mean only
"corruption I must not paper over".

| Class | Disposition | Why |
|---|---|---|
| Fully-recoverable concatenation | **recover** | A union artefact, not corruption — the reader already recovers it. Parity with `validate_events_text`. |
| `status` whose append is in main's tracked log (`protected`) | **hold** | Not deliverable *yet*, but will be. Keep it buffered, deliver the rest, retry every sweep. |
| `status` with no append anywhere | **quarantine** | Not deliverable *ever*. Unchanged behavior. |
| `status` with missing / non-`str` id | **quarantine** | Not deliverable *ever*, and inert to every reader (probe P4) — so nothing observable is destroyed. |
| Bad header, duplicate append, unrecoverable fragment, empty log | **block** | Genuine corruption. Now names `triage_repair.py` as the remedy. |
| Any of the above living in the worktree-tracked (origin-side) log | **block** | The sweep cannot rewrite that log. Honest hard stop, unchanged. |

**hold** is the new state. A held line is trimmed from the materialized log but
left in the outbox — not quarantined (that destroys the dismiss), not blocking
(that strands everything else). Once main's append reaches origin the next sweep
places it normally, so the absorbing state becomes self-healing, and the
`git clean -xfd` blast radius shrinks from the whole backlog to the one line
that genuinely cannot be placed yet.

### Alternative considered and rejected

Keep `block` for (17) and make the message actionable — e.g. tell the operator
to open a PR from main, or add a `--deliver-main` flow. Rejected: it leaves every
unrelated pending append stranded for as long as the operator takes to act, and
the outbox stays one `git clean -xfd` from empty throughout. Holding one line
delivers the other N and requires no operator action at all. Recorded in the ADR.

## Acceptance Criteria

- **AC1** — A fully-recoverable concatenated line does not block: `classify_triage_text`
  recovers its records via `split_records`, validates them as ordinary events, and
  reports no error. A glued `header + append` first line is accepted as a header.
- **AC2** — An *unrecoverable* fragment still errors, still sets
  `has_non_orphan_error`, and the message names `triage_repair.py`.
- **AC3** — Duplicate-append and orphan-status detection see records that were
  previously hidden inside a concatenated line.
- **AC4** — A `protected` status is `hold`, not `block`: it is never a quarantine
  candidate, it stays in the outbox, and every other outbox line is delivered.
- **AC5** — A held line survives the sweep's outbox GC rewrite and is retried;
  once its append is reachable, the next `decide` returns `clean`.
- **AC6** — A `status` with a missing or non-`str` id is classified
  `unidentified_status`, quarantined when it originates in the outbox, and the
  sweep delivers the rest.
- **AC7** — Both dispositions can co-occur in one sweep (a quarantine candidate
  and a held line in the same outbox) without either being lost.
- **AC8** — The operator is told: `SweepResult.held` is reported by
  `sweep_warnings`, counts only, on an otherwise-successful run.
- **AC9** — A defect that lives only in the worktree-tracked log still blocks
  (the sweep cannot rewrite it) — no silent delivery of origin-side corruption.
- **AC10** — `materialized_outbox + candidates + held == outbox_lines` as an
  ordered multiset: every outbox line has exactly one disposition, duplicates
  included. `candidates` is the only list removed from the persisted outbox.
- **AC11** — A glued outbox line holding both a deliverable record and a record
  needing hold/quarantine blocks, and the message names `triage_repair.py`.
- **AC12** — A line with valid records followed by an unrecoverable remainder
  blocks with **no side effect**: no branch commit, no quarantine append, no
  outbox rewrite.
- **AC13** — **Only `str` ids participate in identity, on BOTH event kinds.**
  Discovered during build and scoped in deliberately (Stage-1 spec review,
  finding 1): finding 18 is about non-`str` ids, and fixing only the `status`
  side left the `append` side both crashing and inconsistent. Three things follow,
  each tested:
  1. `append_ids` collects `str` ids only, so the classifier agrees with the two
     other places that already decide this — `read_all_items` skips a non-`str` id
     in **both** passes, and `dedup_triage_lines._append_id` returns `None` for one.
     A non-`str` id is now inert everywhere rather than inert in two places and
     load-bearing in the third.
  2. **It removes a crash.** `append_ids.add(iid)` raised
     `TypeError: unhashable type` on `"id": []` — from inside the sweep's own lock,
     which is worse than any dead end here. Every membership test now checks
     `isinstance` **first**; evaluation order is load-bearing and pinned.
  3. **It retires a fourth dead end of finding 18's family.** Two non-identical
     appends sharing a non-`str` id were reported as a duplicate that
     `dedup_triage_lines` will never collapse — so that log could never be
     delivered again, by anything.

  **The one behavior change that is a genuine loss of tolerance:** an
  `append` + `status` pair sharing a non-`str` id validated *clean* before and now
  has its status quarantined out of the outbox. Accepted, because the pair was
  already inert — pass 1 creates no item for the append, so pass 2 has nothing to
  overlay — so nothing observable is destroyed (same P4 reasoning as AC6). It is
  called out here rather than left to be discovered.

- **AC14** — **The protection universe recovers record boundaries too.**
  `sweep_drift_events.append_ids_of` builds the set of append ids that stops a
  `status` being read as an orphan, so it is the gate on whether an operator's
  dismiss is destroyed. It still parsed one `json.loads` per physical line, which
  fails in the **destroying** direction: an append committed on local main inside
  a glued line vanished from the universe, the dismiss for it became an
  unprotected orphan, was quarantined, and the item resurrected once main reached
  origin. That is finding 15 × finding 17 composed — the worst outcome in this
  family, and the one the plan missed. Found by the **Stage-2 code review**.
  Widening this universe is monotonically safe: an extra id can only *prevent* a
  quarantine, never cause one. Adoption stays line-granular and conservative —
  `_is_producer_event` still refuses to MOVE a glued line rather than
  re-serializing it.

## Affected Boundaries

- **JSONL record boundary** — `lib.jsonl_records.split_records` becomes the
  validator's parser, matching the reader and the event-log twin.
- **`TriageValidation` dataclass** — public via `lib.churn_merge` re-export;
  consumers `reconcile_triage`, `resolve_churn_conflicts`, `sweep_quarantine`.
- **`QuarantineDecision` / `SweepResult`** — new `held` channel through
  `sweep_quarantine` → `sweep_outbox` → `sweep_result` → worktree setup output.

## Confidence Calibration

- **Boundaries touched:** JSONL record boundary (validator parser); the
  `TriageValidation` / `QuarantineDecision` / `SweepResult` dataclass contracts;
  the outbox GC rewrite (held lines must survive it).
- **Empirical probes run:**
  - **P1** (finding 15) — `classify_triage_text` on `HEADER \n APPEND+APPEND`
    returned `['line 2: not valid JSON (Extra data) …']`, `has_non_orphan_error=True`,
    `decide → block`; `split_records` on the same line recovered **2 records,
    remainder `''`**. Reader and validator disagree on identical bytes.
  - **P2** (finding 17) — `decide` with one protected status plus one unrelated
    pending append returned `block`, `candidates=[]`, `trimmed_outbox=[]`: the
    unrelated append `trg-new` was stranded by a line that had nothing to do with it.
  - **P3** (finding 18) — both `{"event":"status","newStatus":"dismissed"}` (no id)
    and `"id":123` produced one error each with `orphan_status_ids=set()`,
    `has_non_orphan_error=False`, `decide → block`, `candidates=[]`. Confirmed
    un-quarantinable and un-repairable.
  - **P4** (disposition safety for 18) — read `triage.read_all_items` pass 2:
    `if not isinstance(item_id, str) or item_id not in resolved: continue`. A
    status with a missing/non-`str` id is inert to every reader, so quarantining
    it destroys no observable operator decision. This is what licenses
    quarantine over hold for that class.
  - **P5** (blast radius) — grepped every caller of `validate_triage_text` /
    `classify_triage_text`: `reconcile_triage` (manual CLI, main's tracked log
    only — never sees the outbox), `resolve_churn_conflicts`, `sweep_quarantine`.
    No caller reads `TriageValidation` field-by-field except `sweep_quarantine`,
    so adding a field is additive.
  - **P6** (post-implementation) — round-trip probe over the record boundary:
    see `test_triage_validate_boundary_roundtrip`.
- **Test Completeness Ledger:** see `Test Completeness Ledger` section below.
- **Confidence-pattern check:**
  - *Asymptote (depth)* — the three findings are one defect seen three times:
    `decide` has no disposition between "deliver" and "stop the world". Fixing
    the classifier alone (15) would leave 17 and 18 absorbing; fixing the
    dispositions alone would leave the validator disagreeing with the reader.
    Both halves are required and are in one diff.
  - *Coverage (breadth)* — the classes enumerated in "The shape of the fix" are
    the complete partition of `classify_triage_text`'s error vocabulary: header,
    JSON, duplicate append, orphan status, empty log. Each row has a test.
  - *Integration composition* — `cross_component` does **not** fire on this diff
    (no file matches `CROSS_COMPONENT_FILE_PATTERNS`; `churn_merge.py` is
    untouched — it only re-exports names). The sweep-level behavior is still
    covered end-to-end by `category:"integration"` behaviors driving
    `sweep_outbox_to_branch` against a real git repo, because the held-line
    survival property (AC5) only exists in the composition of `decide` with the
    GC rewrite and cannot be proven at the unit level.

## Test Completeness Ledger

| # | Behavior | Disposition | Evidence |
|---|---|---|---|
| 1 | Recoverable concatenation validates clean (AC1) | tested | `test_triage_validate.py::test_concatenated_records_recover` |
| 2 | Glued `header+append` first line accepted (AC1) | tested | `test_triage_validate.py::test_header_glued_to_first_event` |
| 3 | Unrecoverable fragment errors + names `triage_repair` (AC2) | tested | `test_triage_validate.py::test_unrecoverable_fragment_names_the_repair_tool` |
| 4 | Bare scalar line is a fragment, not silently tolerated (AC2) | tested | `test_triage_validate.py::test_bare_scalar_line_is_a_fragment` |
| 5 | Duplicate append hidden in a glued line is detected (AC3) | tested | `test_triage_validate.py::test_duplicate_append_inside_a_glued_line` |
| 6 | Orphan status hidden in a glued line is detected (AC3) | tested | `test_triage_validate.py::test_orphan_status_inside_a_glued_line` |
| 7 | Missing / non-`str` id sets `unidentified_status`, not orphan (AC6) | tested | `test_triage_validate.py::test_status_without_usable_id_is_its_own_class` |
| 8 | Protected status → `hold`, never a candidate (AC4) | tested | `test_sweep_quarantine_dispositions.py::test_protected_status_is_held_not_blocked` |
| 9 | Held line: rest of the outbox is delivered (AC4) | tested | `test_sweep_quarantine_dispositions.py::test_hold_delivers_the_rest_of_the_outbox` |
| 10 | Unidentified status quarantined from the outbox (AC6) | tested | `test_sweep_quarantine_dispositions.py::test_unidentified_status_is_quarantined` |
| 11 | Quarantine + hold co-occur without loss (AC7) | tested | `test_sweep_quarantine_dispositions.py::test_hold_and_quarantine_co_occur` |
| 12 | Worktree-tracked-only defect still blocks (AC9) | tested | `test_sweep_quarantine_dispositions.py::test_tracked_side_defect_still_blocks` |
| 13 | `sweep_warnings` reports `held`, counts only (AC8) | tested | `test_sweep_quarantine_dispositions.py::test_sweep_warnings_reports_held` |
| 14 | Held line survives the GC rewrite and is retried (AC5) — **integration** | tested | `test_sweep_outbox_dispositions_integration.py::test_held_line_survives_the_sweep_and_is_retried` |
| 15 | Concatenated outbox line no longer blocks the real sweep (AC1) — **integration** | tested | `test_sweep_outbox_dispositions_integration.py::test_concatenated_outbox_line_no_longer_blocks_delivery` |
| 16 | Reader and validator agree on identical bytes (in-memory round-trip) | tested | `test_triage_validate.py::test_triage_validate_boundary_roundtrip` — the on-disk write→read→validate round-trip is behavior 15 |
| 17 | `validate_triage_text` stays a faithful string projection | tested | `test_triage_validate.py::test_validate_triage_text_projects_classifier_strings` |
| 18 | Disposition lists are disjoint + exhaustive (AC10) | tested | `test_sweep_quarantine_dispositions.py::test_dispositions_partition_the_outbox` |
| 18a | Input ORDER preserved within each list (AC10) | tested | `test_sweep_quarantine_dispositions.py::test_dispositions_preserve_input_order_within_each_list` |
| 19 | Duplicate identical status records keep multiplicity (AC10) | tested | `test_sweep_quarantine_dispositions.py::test_duplicate_status_records_keep_multiplicity` |
| 20 | Held line is never in the set removed from the persisted outbox (AC5) | tested | `test_sweep_quarantine_dispositions.py::test_held_is_not_in_the_quarantine_removal_set` |
| 21 | Glued line needing a per-record disposition blocks + names the tool (AC11) | tested | `test_sweep_quarantine_dispositions.py::test_glued_line_needing_disposition_blocks_with_repair_hint` |
| 22 | Valid records + unrecoverable remainder → block, zero side effects (AC12) — **integration** | tested | `test_sweep_outbox_dispositions_integration.py::test_unrecoverable_fragment_blocks_with_no_side_effects` |
| 23 | Byte-identical defect in BOTH tracked log and outbox still blocks (AC9) | tested | `test_sweep_quarantine_dispositions.py::test_defect_in_both_sources_still_blocks` |
| 24 | Churn resolver: concatenated line recovers, bare scalar reports (R7) | tested | `test_triage_validate.py::test_churn_resolver_triage_validation_shift` |
| 25 | A fully-valid glued outbox line is materialized, never held/quarantined (AC11) | tested | `test_sweep_quarantine_dispositions.py::test_valid_glued_line_is_materialized_not_dispositioned` |
| 26 | `sweep_warnings` reports `held` on every status, incl. a quiet sweep (AC8) | tested | `test_sweep_quarantine_dispositions.py::test_sweep_warnings_reports_held_on_a_quiet_sweep` |
| 27 | Unhashable **status** id does not crash the sweep (AC13.2) | tested | `test_triage_id_identity.py::test_an_unhashable_status_id_does_not_crash_the_sweep` |
| 28 | Unhashable **append** id does not crash the validator (AC13.2) | tested | `test_triage_id_identity.py::test_an_unhashable_append_id_does_not_crash_the_validator` |
| 29 | Duplicate append with a non-`str` id is no longer an undeliverable log (AC13.3) | tested | `test_triage_id_identity.py::test_duplicate_non_str_append_id_is_no_longer_undeliverable` + `test_triage_validate.py::test_churn_resolver_triage_validation_shift` (third assertion) |
| 29a | The one shape that stops being tolerated: matched non-`str`-id pair loses its status, keeps its append (AC13 / R9) | tested | `test_triage_id_identity.py::test_matched_non_str_id_pair_loses_its_status` |
| 30 | A dismiss survives when its append is glued on local main (AC14) — **integration** | tested | `test_sweep_outbox_dispositions_integration.py::test_a_dismiss_survives_when_its_append_is_glued_on_local_main` — verified to FAIL (`quarantined=1`) against a reverted `append_ids_of`, so the pin is real |
| 31 | A block never names an unplaceable id that was in fact held (Stage-2 finding 2) | tested | `test_sweep_quarantine_dispositions.py::test_a_held_id_is_never_reported_unplaceable` |
| 32 | A block a split would fix names `triage_repair.py`, incl. via the early corruption return (Stage-2 finding 3) | tested | `test_sweep_quarantine_dispositions.py::test_duplicate_append_in_a_glued_line_names_the_repair_tool` |
| 33 | Corruption elsewhere no longer swallows the protected-id correction (Stage-3 objection 1) | tested | `test_sweep_block_diagnostics.py::test_corruption_elsewhere_does_not_swallow_the_protected_correction` |
| 34 | A glued protected status is never described as absent from the outbox (Stage-3 objection 2) | tested | `test_sweep_block_diagnostics.py::test_a_glued_protected_status_is_not_called_absent` |
| 35 | The protected note states only what is true on every path | tested | `test_sweep_block_diagnostics.py::test_a_protected_id_outside_the_outbox_still_gets_the_correction` |
| 36 | Operator-facing warning wording for a blocked sweep | untestable | `requires-manual-visual-judgment` — the exact prose is reviewed, not asserted; the *presence* of the tool name is behaviors 3 and 21 |

0 testable-but-untested.

**External plan review — round 1 folded in:** openai #1 → behavior 21 +
mini-plan Step 2a; #2 → `trimmed_outbox` renamed `materialized_outbox` +
behaviors 18/20; #3 → resolved by inspection (one keyword-only construction
site); #4 → behavior 22; #5 → index partition + behavior 19; #6 → static
operator text. deepseek's four points → behaviors 2, 3, 8, 20.

**Round 2 folded in:** openai #1 → the persisted-outbox lifecycle table
(quarantine vs GC vs held) replaces the inaccurate "candidates only ever
removed"; #2 → Step 2a made deterministic, one parser (`split_records`) for both
classification and partition, `multi_record` drives the hint; #3 → the residual
re-validation named as the provenance safety net + behavior 23; #4 → risk R8,
self-healing scoped honestly to once-per-iterate; #5 + deepseek #2 → write
ordering documented as already crash-safe (R7a), duplicate-on-replay left
explicitly out of scope; #6 → static text re-affirmed. deepseek #1 → audit of
`resolve_churn_conflicts` + behavior 24; #3 → block condition restated positively.

**Round 3 folded in — and where it stopped.** deepseek **approve** (four low
findings, all folded: verdict provenance comment, `held` reported on a quiet
sweep → behavior 26, changelog note for the bare-scalar change, rename comment).
openai **revise**, and each remaining finding became an implementation
constraint rather than a plan rewrite: #1 → never reassign `outbox_lines`, bind
`branch_outbox_lines` instead; #2 → the held invariant restated as "never
removed *because it is held*", so a moving origin is not a contradiction and no
test asserts byte retention against it; #3 → new fields are trailing with
defaults (`unidentified_status: bool = False`, `held: list[str] =
field(default_factory=list)`) and the one construction site is keyword-only;
#4 → `multi_record` is advisory, never blocking → behavior 25; #5 → stripping is
parse-only, the original `ln` is what every list holds.

Review stopped here by decision: three rounds, verdicts converged to
approve/revise with no contradiction, and every open item is a constraint on
code that the Step 8 cascade will check against the real diff — which is a
stronger test of them than a fourth pass over prose.

## Architecture Updates

- No new route, component, schema, service or convention. The `held` disposition
  is a new state in an existing internal state machine and is recorded in the ADR
  rather than `architecture.md`.
