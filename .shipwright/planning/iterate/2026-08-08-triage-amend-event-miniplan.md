# Mini-Plan: Triage `amend` Event

**run_id:** iterate-2026-08-08-triage-amend-event
**Spec:** `.shipwright/planning/iterate/2026-08-08-triage-amend-event.md`
**Trigger card:** trg-b310add8 (P2.46)

## Decisions confirmed with the operator (2026-08-08)

1. **Amendable fields:** `title`, `detail`, `severity`, `kind`. NOT amendable:
   `source`, `dedupKey`, `runId`, `evidencePath`, `commit`, `launchPayload`,
   `frId`, `suiteId`, `eventId`, `status` (status stays exclusively a `status`
   event). A `severity` amend recomputes `suggestedPriority`, mirroring
   `append`'s own derivation. **Correction (internal review, H1):** a `kind`
   amend changes only `kind` — there is no `kind`→`suggestedDomain`
   relationship anywhere in the codebase; `suggestedDomain` derives from
   `source`, which is not amendable.
2. **Who may amend:** human via CLI only, this iterate. No automated producer
   is wired to self-amend. `by` stays a free-form string (same convention as
   `status.by`: `cli` / `webui` / ... ), not a closed vocabulary — consistent
   with the existing field.
3. **Scope depth: full parity with `status`.** Every module that treats a
   `status` event as a first-class citizen gets the matching treatment for
   `amend`, not just the read path.

## Internal Opus plan review — findings folded in (2026-08-08)

Verdict: approve-with-changes. Full findings recorded in the iterate ADR
(Self-Review section). What changed in this plan as a result:

- **H1 (wrong derivation, corrected):** removed. A `kind` amend changes
  `kind` and nothing else — `suggestedDomain` is derived from `source`
  (`DOMAIN_FROM_SOURCE`, keyed on source, not kind), and `source` is not
  amendable. There is no `kind`→domain rule anywhere in the codebase; the
  original plan invented one. Only `severity`→`suggestedPriority` is a real
  recompute-on-amend case.
- **H2 (bloat budget, load-bearing):** `shared/scripts/triage.py` is
  baselined at exactly its measured size (882/882, zero headroom, hard
  pre-commit block on any growth) — confirmed by reading
  `shipwright_bloat_baseline.json` directly. `shared/scripts/tools/triage_promote.py`
  is the same (420/420, ADR-121 exception). `sweep_quarantine.py`,
  `triage_gc_core.py`, `shared/scripts/tools/triage_cli.py` are each exactly
  at the un-baselined 300-line default cap (any growth there is a NEW
  crossing — advisory only per the constitution's anti-ratchet rule, not a
  hard block, but named here rather than discovered at commit time).
  **Consequence:** new pure leaf `shared/scripts/lib/triage_amend.py`
  (ADR-045-safe, mirrors `triage_delivery.py`'s shape) holds everything that
  does not need the lock/IO primitives that only live in `triage.py`: the
  amendable-field vocabulary, per-field validation, the pass-2 overlay
  applier (skip-whole-event-on-invalid), the amend-event dict builder, and
  the `amendedBy`/`amendedAt` field-name constants. To make room inside
  `triage.py`'s zero headroom, `_check_optional_str`,
  `suggest_priority_from_severity`, and `suggest_domain_from_source`
  (~30 lines together) move into the SAME new leaf, re-exported from
  `triage.py` via the existing PEP 562 `__getattr__` lazy pattern (already
  used there for `_FileLock`/`AUTO_RESOLVABLE_STATUSES`) so every existing
  caller of `triage.SEVERITIES` / `triage.suggest_priority_from_severity`
  keeps resolving unchanged. `triage.py`'s own net addition is then just the
  thin `amend_triage_item()` wrapper + a widened pass-2 filter + one
  delegating call — verified ≤882 lines before commit (F0 / pre-commit will
  catch it either way, but this is planned, not discovered).
- **H3 (writer parity, was under-specified):** `amend_triage_item()` must
  replicate ALL of `mark_status`'s behavior, not just field validation:
  `FileNotFoundError` when neither store exists; `KeyError` when `item_id`
  is not a known `append` id in tracked ∪ outbox; the `should_route_to_outbox`
  probe OUTSIDE the lock (IT-1 audit finding 12 — spawns git subprocesses,
  must not run inside the lock); residence (`to_outbox`) derived INSIDE the
  lock from the same tracked/outbox id sets; the canonical lock taken
  exactly once, never from inside a `read_all_items` call (which must stay
  lock-free). Added as explicit ACs (AC13-AC16) plus a
  `test_amend_triage_item_acquires_the_canonical_lock_exactly_once` twin of
  the existing status test.
- **H4 (validator/GC coupling, was mis-sequenced):** item 8 (GC) is NOT
  deferrable and is bound to item 4 (validator) in the SAME work step —
  shipping item 4 (which makes an orphan amend a validation ERROR) without
  item 8 (which is what stops GC retaining an orphan amend line forever)
  self-inflicts a permanent block the very next GC run, the exact failure
  class `sweep_quarantine.py` was rewritten to end. Three more
  `validate_triage_text` consumers than originally named are now in the file
  table with their own test: `tools/ensure_current.py`,
  `tools/resolve_churn_conflicts.py`, `lib/reconcile_triage.py`.
- **M5 (quarantine parity, safety constraints):** the `amend` branch in
  `sweep_quarantine.decide()` is an ADDED `elif`, never a refactor of the
  existing by-index partition loop or the status branch. `protected`/
  `orphan_ids` become the UNION of status ∪ amend orphan sets (else a
  protected amend gets no explanation and the "corruption that is not
  there" defect the module was rewritten to prevent comes back). The
  existing `protected_status_unplaceable` token is pinned by
  `test_sweep_block_diagnostics.py` and stays exactly as-is; a NEW distinct
  `protected_amend_unplaceable` token is added, never a rename. `isinstance
  (iid, str)` stays FIRST in the amend branch, verbatim — membership-testing
  first raises `TypeError` on an unhashable id from inside the sweep's lock.
- **M6 (delivery-visibility, descoped to a follow-up):** widening the
  existing `undeliveredDecisions` envelope key was rejected — it is a set of
  ids and would silently stop counting an item that has BOTH a buffered
  status flip and a buffered amend, and the repo's own compliance artifacts
  (`.shipwright/agent_docs/iterates/iterate-2026-08-06-p2-19c-corruption-absence.json`)
  confirm the Command Center (a separate, unreachable-this-session repo)
  renders this exact key today. **Work item 7 (delivery visibility:
  `triage_delivery.py` amend tracking, `triage_contract.py`
  `pendingAmendDelivery` + new sibling `undeliveredAmends` envelope key) is
  moved out of this iterate into the same follow-up as the WebUI reader
  update** — it is advisory display only, nothing else depends on it, and
  it is the one piece that actually needs the cross-repo contract bump
  coordinated. Item 8 (GC) stays IN this iterate (see H4 — it is load-bearing,
  not display).
- **M7 (contract row shape, clarified):** `amendedBy`/`amendedAt` land on
  EVERY resolved item via `triage_contract.py`'s `{**it, ...}` spread — two
  new row keys, not one folded into `pendingAmendDelivery` (which is itself
  now deferred per M6). Verified: no `read_all_items` caller
  (`aggregate_triage`, `triage_promote`, `check_drift`,
  `github_triage/resolve`, `accepted_risks_converge`,
  `verify_sweep_delivery_surface`, `triage_cli`) writes a resolved item back
  to the store verbatim, so `additionalProperties:false` on the wire schema
  is never at risk from this.
- **M8 (ordering semantics, decided):** an amend does NOT overlay the
  resolved item's `ts` field — `ts` keeps meaning "time of the last STATUS
  decision" exactly as today (matches `aggregate_triage`'s own sort key,
  which uses `originalTs`, not `ts`). Ordering tests are written
  amend-vs-amend (later ts wins; equal ts → file-order tiebreak; malformed
  ts sorts earliest) plus one status-and-amend-same-ts test proving both
  apply regardless of which the merged sort visits first (their effects are
  on disjoint fields, so this is a compositional test, not an
  ordering-dependent one).
- **M9 (predicate hardening):** an amend event must carry at least one
  amendable field (`title`/`detail`/`severity`/`kind`) — the writer raises
  `ValueError` on a contentless amend, and the schema branch's `anyOf`
  requires at least one. `triage_integrity.py`'s docstrings naming "the two
  writers" and its v1/v2/v3 predicate-hardening history are updated to name
  three.
- **Missed-module verification (per the review):** `lib/triage_dedup.py`
  (byte-identical + same-id-append dedup only; amend passes through
  untouched — its own docstring enumerating "never touched by any of this"
  gains one line rather than leaving a reader to re-derive it),
  `lib/sweep_canon.py` (event-agnostic, no change), `lib/main_health.py`
  (unrelated `event` key, confirmed no relation), `tools/triage_repair.py`
  (inherits the widened `is_triage_record` predicate automatically — one
  behavior test, no code change).
- **L10-L12 (docstring/CLI polish):** stale "three kinds"/"two writers"/
  "ignores non-append/status" docstrings across `triage.py`,
  `triage_gc_core.py`, `sweep_drift_events.py`,
  `triage_item.schema.json` updated in the same diff (constitution:
  docs = what/how, updated with the code they describe). CLI `amend`
  subcommand rejects a no-field-flags invocation and defaults `--by` to
  `"cli"` like every existing subcommand, rather than requiring it.

## External LLM plan review — findings folded in (2026-08-08)

Two providers (openai via openrouter, deepseek), verdicts `revise` /
`approve`, no contradiction. What changed as a result:

- **Corruption-boundary hardening (openai, high).** `_REQUIRED_KEYS["amend"]
  = ("id","ts","by")` alone lets a contentless-but-key-complete forged
  object (`{"event":"amend","id":"trg-x","ts":"...","by":"cli"}`, no
  title/detail/severity/kind) pass `is_triage_record` as a genuine record,
  even though the schema's `anyOf` would reject it on the wire. Since
  `is_triage_record` gates what `triage_repair.py` recovers and **republishes
  to disk**, a forged shape passing here is the exact injection risk the
  predicate's v1→v2→v3 hardening history exists to close. `is_triage_record`
  now carries one amend-specific line beyond the generic keys-table check:
  after the required-keys gate passes for `event=="amend"`, also require at
  least one of `title`/`detail`/`severity`/`kind` present — mirroring the
  schema's own `anyOf`, inlined as a literal tuple rather than imported from
  the new leaf (keeps `triage_integrity.py`'s existing minimal-coupling
  design: it already deliberately never imports `triage` itself).
- **Module naming/cohesion (openai, low, folds into H2's extraction).**
  Dumping `suggest_domain_from_source` into a module named `triage_amend.py`
  is misleading — domain/source are explicitly NOT amendable. **Split into
  two new leaves**: `shared/scripts/lib/triage_fields.py` (generic,
  amend-agnostic: `_check_optional_str`, `suggest_priority_from_severity`,
  `suggest_domain_from_source` — used by BOTH `append` and `amend` paths)
  and `shared/scripts/lib/triage_amend.py` (amend-specific only: vocabulary,
  per-field validators, `build_amend_event()`, the pass-2 overlay applier).
  Same net bloat-budget effect on `triage.py` as the original H2 plan, just
  correctly named.
- **GC resolver ordering (openai, high — clarified, not a new gap).**
  `_resolve_tracked_only`'s amend overlay follows the SAME file-order
  (not ts-sorted) simplification its existing status overlay already uses —
  this function's own docstring already says "mirrors `read_all_items`
  resolution... but over a single file", i.e. it is a known, accepted
  approximation for GC's tracked-only, single-file case (no cross-file
  ordering question arises there), not a precision guarantee. Stated
  explicitly here so it reads as a documented design choice, not an
  oversight the reviewer had to find.
- **Outbox delivery path, happy case (openai, medium).** The quarantine-sweep
  tests (work item 6) cover orphan/protected/held amend classification, but
  not the plain CLEAN case: an amend written to the outbox, delivered
  through the sweep, resolved by a fresh `read_all_items`. Added as its own
  test in work item 6 — `dedup_triage_lines` already passes non-`append`
  lines through untouched (confirmed by reading its docstring: same-id
  supersession collapse applies only to `append`), so this is a coverage
  gap, not a suspected code gap.
- **Stale text fixed (openai, low).** The "Decisions confirmed" section
  above still said "a `kind` amend recomputes `suggestedDomain`" after the
  internal review had already corrected every other section (H1) — that
  sentence is removed; see the corrected Decision 1 above.
- **Metadata-sequencing tests (openai, low) + verification steps (deepseek,
  medium/low, no plan change — pre-commit verification only).** Added to
  work item 3: equal-ts amend-vs-amend ordering; a later invalid amend does
  NOT overwrite `amendedBy`/`amendedAt` from the prior valid one. Added as
  build-time verification (not a design change): grep for any positional
  (non-keyword) construction or unpacking of `TriageValidation`, and for
  direct top-level references to the three relocated field-helpers, before
  the relocation is considered done.

## Files to create/modify

| File | Change |
|---|---|
| `shared/schemas/triage_item.schema.json` | New `amend` `oneOf` branch: required `event,id,ts,by`; `anyOf` requires at least one of `title,detail,severity,kind` present; reuses the existing `severity`/`kind` enums; `additionalProperties:false` |
| **`shared/scripts/lib/triage_fields.py`** (NEW) | Pure leaf, amend-agnostic: `_check_optional_str`, `suggest_priority_from_severity`, `suggest_domain_from_source`, relocated from `triage.py` (bloat-budget room, H2) — kept in a generically-named module since domain/source derivation applies to `append`, not amend (external review finding) |
| **`shared/scripts/lib/triage_amend.py`** (NEW) | Pure leaf (ADR-045-safe, mirrors `triage_delivery.py`'s shape), amend-specific only: amendable-field vocabulary/constant, per-field validators, `build_amend_event()`, the pass-2 overlay applier (skip-whole-event on any invalid present field), `amendedBy`/`amendedAt` constants |
| `shared/scripts/triage.py` | Thin `amend_triage_item()` (full `mark_status` parity: `FileNotFoundError`/`KeyError`, `should_route_to_outbox` outside the lock, residence derived inside it, single lock acquisition) delegating validation/event-building to the new leaf. `read_all_items` pass 2: widen the existing status-events filter to `event in ("status","amend")`, sort together by `(ts, file-order)` unchanged, add one `elif` dispatching an amend to the leaf's overlay applier. `amendedBy`/`amendedAt` initialized `None` in pass 1. `SEVERITIES`/`KINDS`/etc. re-exported via the existing `__getattr__` lazy pattern. Net line count verified ≤882 before commit. |
| `shared/scripts/lib/triage_integrity.py` | `_REQUIRED_KEYS["amend"] = ("id", "ts", "by")` PLUS one amend-specific content check in `is_triage_record` — at least one of `title`/`detail`/`severity`/`kind` must be present (inlined literal, not imported, to keep this module's existing minimal-coupling design) — closing a real forged-record gap an external reviewer found: a key-complete-but-contentless amend would otherwise pass as a valid record; docstrings updated from "two writers" to three |
| `shared/scripts/lib/triage_validate.py` | `classify_triage_text`: track `amend_ids` alongside `status_ids`; second pass adds `orphan_amend_ids`/`unidentified_amend` (new trailing, defaulted `TriageValidation` fields — no positional-arg break) mirroring the existing status branch, own message wording |
| `shared/scripts/lib/sweep_quarantine.py` | `decide()`: partition loop gains an ADDED `elif event == "amend":` branch (never a refactor of the existing loop) — orphan/protected/held classification symmetric with `status`; `protected`/`orphan_ids` become the union of status ∪ amend orphan sets; new distinct `protected_amend_unplaceable` token (existing `protected_status_unplaceable` untouched — pinned by `test_sweep_block_diagnostics.py`) |
| `shared/scripts/lib/sweep_drift_events.py` | `_EVENTS = frozenset({"append", "status", "amend"})` |
| `shared/scripts/lib/triage_gc_core.py` | `_resolve_tracked_only`: apply `amend` overlay (title/detail/severity+suggestedPriority/kind) so GC's own report never shows stale fields; `apply_gc_reporting`'s rewrite filter includes `"amend"` alongside `"append","status"` so an orphaned amend line for a dropped id is compacted away instead of retained forever (load-bearing — bound to the `triage_validate.py` change, see H4 above, not deferrable); `_validate_after` gains an amend-orphan check symmetric with the existing status-orphan check |
| `shared/scripts/tools/triage_cli.py` | New `amend` subcommand: `triage_cli.py amend <id> [--title T] [--detail D] [--severity S] [--kind K] [--by cli]`, calling `triage.amend_triage_item()`; rejects a no-field-flags invocation |
| `shared/scripts/tools/ensure_current.py`, `shared/scripts/tools/resolve_churn_conflicts.py`, `shared/scripts/lib/reconcile_triage.py` | No code change — confirmed consumers of the widened `validate_triage_text`; one behavior test each proving an orphan-amend error surfaces the same way an orphan-status error already does |
| `shared/scripts/lib/triage_dedup.py` | Docstring only — its existing "never touched by any of this" enumeration gains `amend` |
| `shared/scripts/tools/triage_repair.py` | No code change — inherits the widened `is_triage_record` predicate automatically; one behavior test |
| `shared/tests/*` (new + extended) | See Test Strategy |

**Confirmed NO code change needed** (verified by reading, not assumed):
`shared/scripts/lib/triage_render.py` (renders whatever `read_all_items`
resolves), `shared/scripts/tools/aggregate_triage.py` (same — calls only
`read_all_items`), `shared/scripts/lib/sweep_canon.py` (event-agnostic),
`shared/scripts/lib/main_health.py` (unrelated `event` key).

**Explicitly out of scope, this iterate (moved to a follow-up triage card):**
- **Delivery-visibility parity** (`triage_delivery.py` amend tracking,
  `triage_contract.py` `pendingAmendDelivery` + new `undeliveredAmends`
  envelope key) — descoped per the internal plan review (M6): it is
  advisory display only, nothing else depends on it, and it is the one
  piece that genuinely needs the WebUI cross-repo contract bump coordinated
  rather than shipped alone. Bundled into the same follow-up as the WebUI
  reader update below.
- WebUI TypeScript reader + parity fixture — separate repo, not reachable
  this session. Old title/detail/severity/kind persist there until that repo
  is updated. Filed as a follow-up (see below), named in the ADR and F12
  summary per the constitution's "read state from where it is authoritative"
  rule.
- Any automated producer calling `amend_triage_item()` — the primitive is
  built and CLI-reachable; nothing production is wired to call it yet.

## Work breakdown (sequential)

1. **New leaf modules** (`lib/triage_fields.py` + `lib/triage_amend.py`) —
   the relocated generic helpers in the first; amendable-field vocabulary,
   per-field validators, `build_amend_event()`, the pass-2 overlay applier in
   the second. Test: pure unit tests on both leaves directly (no store, no
   IO) — valid/invalid field combos, whole-event skip on one bad field,
   severity→suggestedPriority recompute; a grep-verified check that no
   caller referenced the three relocated names at module top level in a way
   the `__getattr__` re-export wouldn't cover.
2. **Schema** — add the `amend` branch to `triage_item.schema.json`
   (`anyOf` requires ≥1 amendable field present). Test: extend
   `test_triage_schema.py` with a valid-amend, an invalid-amend
   (extra prop / missing required / no fields present) case, and a
   nested-forgery negative test mirroring the append/status ones.
3. **Core read/write** (`triage.py`) — `amend_triage_item()` with full
   `mark_status` parity (AC13-16: `FileNotFoundError`, `KeyError`,
   `should_route_to_outbox` outside the lock, single lock acquisition) +
   `read_all_items` pass-2 fold-in + `amendedBy`/`amendedAt` + the
   `__getattr__` re-exports for the relocated pure helpers. Verify net line
   count ≤882 before commit. Tests: extend the two-pass-resolution test
   family (`test_triage_storage.py`, `test_triage_outbox.py` style) with
   amend-specific cases — title-only amend leaves detail untouched; severity
   amend recomputes suggestedPriority; an amend with an invalid severity is
   skipped whole (prior state survives); amend-vs-amend ordering by
   `(ts, file-order)`, including the EQUAL-ts case (file-order tiebreak);
   malformed `ts` sorts earliest; a status and an amend at the same `ts`
   both apply regardless of merge-sort tie order (disjoint fields); a later
   INVALID amend does not overwrite `amendedBy`/`amendedAt` from the prior
   valid one; `test_amend_triage_item_acquires_the_canonical_lock_exactly_once`.
4. **Corruption boundary** (`triage_integrity.py`) — `_REQUIRED_KEYS`
   addition + the amend content-presence check (external review finding) +
   docstring update. Test: an amend line is NOT reported as a corrupt span;
   a malformed/forged amend-shaped object still is; a key-complete but
   CONTENTLESS amend (no title/detail/severity/kind) is ALSO still reported
   as corrupt, matching the schema's `anyOf`.
5. **Validator + GC, bound together** (`triage_validate.py` +
   `triage_gc_core.py`) — orphan-amend classification AND the matching GC
   compaction/orphan-check fix land in the SAME step, never split (H4: an
   orphan-amend validation error without the GC fix self-inflicts a
   permanent block on the next GC run). Test: mirrors the existing
   status-orphan tests, one set for amend; an amend for a
   machine-churn-dropped id is compacted away, not retained;
   `_validate_after` catches a post-compaction orphan amend; the three
   confirmed-no-change consumers (`ensure_current.py`,
   `resolve_churn_conflicts.py`, `reconcile_triage.py`) each get one
   behavior test proving the orphan-amend error surfaces through them
   identically to an orphan-status error today.
6. **Quarantine sweep** (`sweep_quarantine.py`) — amend orphan/protected/held
   parity, added `elif` branch only. Test: mirrors the existing
   status-orphan hold/quarantine/block fixtures for amend
   (protected-via-known-append-ids → held with `protected_amend_unplaceable`,
   unprotected-orphan → quarantined, glued-line hint still fires,
   `test_sweep_block_diagnostics.py`'s existing status pins untouched), PLUS
   the plain happy-path case an external reviewer flagged as untested: an
   amend written to the outbox is delivered through the sweep unmodified
   (`clean` verdict) and resolves correctly from a fresh `read_all_items`.
7. **Drift adoption** (`sweep_drift_events.py`) — `_EVENTS` addition +
   docstring update. Test: an amend line on main's tracked log is
   recognized as a producer record (not refused as unparseable).
8. **CLI** (`triage_cli.py`) — `amend` subcommand, rejects a no-field
   invocation, `--by` defaults to `"cli"`. Test: extends
   `test_triage_cli.py` with an end-to-end amend-then-list round trip.
9. **Docstring sweep** (L10) — `triage.py`, `triage_gc_core.py`,
   `sweep_drift_events.py`, `triage_item.schema.json`,
   `triage_dedup.py`'s "never touched" list, `triage_repair.py` behavior
   test. No production logic in this step, doc-accuracy only.
10. **Boundary Probe** (`touches_io_boundary`) — round-trip test: write an
    amend via the CLI, read the store back from a fresh process, confirm the
    resolved fields match (per `references/round-trip-tests.md`).
11. Resolve trg-b310add8 (P2.46) — `promoted`, `by=cli`, referencing this
    run_id, once merged.
12. File ONE follow-up triage card (neutral, descriptive, per constitution —
    no internal file:line detail needed) covering BOTH deferred pieces
    together, since they share one delivery: "Cross-repo triage `amend`
    parity — WebUI reader + delivery-visibility tracking
    (`pendingAmendDelivery`/`undeliveredAmends`)", referencing this run_id
    and P2.34.

## Test strategy

Unit tests only — this is pure Python, no UI, no E2E surface. `touches_io_boundary`
is triggered (JSONL read/write), so one round-trip test per AC5/AC9 combo, per
`references/round-trip-tests.md`. Full existing triage suite re-run (not just
`--related`) since this touches shared invariants across many modules that
already have dense mutual test coverage (medium complexity → full suite per
the Phase Matrix). No `cross_component` flag fires (see Planned Run Summary
reasoning) so no separate mandatory `category:"integration"` behavior is
required by the F11 gate — written anyway for the delivery/GC/quarantine
composition, since that is exactly the kind of "do the pieces compose"
coverage the codebase already carries for the `status` path
(`test_delivery_check_agrees_with_the_reader_on_the_deciding_event`,
`test_triage_operator_decision_integration.py`).

## Alternative approach (considered, rejected)

**Alternative: a separate `amendments.jsonl` side-log**, keyed by item id,
read as an overlay on top of `read_all_items`'s existing output — instead of
a third event kind inside the same file.

**Rejected because:** it would need its own git-tracked file, its own
`merge=union` behavior, its own corruption/delivery/GC/drift-adoption
machinery duplicated from scratch, and a SECOND lock or a shared one
(re-introducing exactly the cross-file ordering hazard `read_all_items`
already had to solve once for outbox-vs-tracked `status` events — see its
own docstring on why `(ts, file-order)` ordering across files is
load-bearing). It also splits a card's history across two files for no
operational gain: nothing needs `amendments.jsonl` to be prunable or
deliverable independently of `triage.jsonl`. Folding `amend` into the
existing file, existing lock, and existing two-pass resolver — as the
operator's own brief specified — reuses every one of those solved problems
instead of re-solving them.

## Risks named for the reviewers

- **Blast radius, revised after internal review.** This now touches 8
  production modules plus one new pure leaf, down from the original 9 +
  cross-repo envelope change — delivery-visibility parity (the piece with
  the real cross-repo contract risk) was descoped to a follow-up per the
  internal Opus review (M6). What remains still includes modules with dense
  external-review scar tissue (`sweep_quarantine.py`, `triage_gc_core.py`),
  but each touch there is now a narrowly-scoped added branch, not a
  refactor of existing logic, and is bound to a concrete correctness
  requirement (H4) rather than a "full parity for its own sake" argument.
  External review should still weigh in on whether this is right-sized for
  one PR.
- **Bloat-budget extraction risk.** Moving `_check_optional_str`/
  `suggest_priority_from_severity`/`suggest_domain_from_source` out of
  `triage.py` (required — that file has zero headroom, see H2) touches a
  module with dense existing test coverage. The `__getattr__` re-export
  pattern is already established in the same file for two other names, so
  this is precedent-following, not a new pattern — but it is the one
  "moves working code" change in this plan and deserves explicit review
  attention.
