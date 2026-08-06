# Iterate Spec: P2.19c — corruption reads as absence; the board cannot tell delivered from buffered

- **Run ID:** iterate-2026-08-06-p2-19c-corruption-absence
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal

Close the five reader-side defects of triage card `trg-8652bf24` (IT-1 audit
findings 5/12/21/22/28) so that an unreadable span in the append-only triage log
can no longer read as absence, a valid record can no longer be discarded because
a damaged neighbour precedes it on the same physical line, and an operator
decision still sitting in the gitignored outbox is visibly distinguished from one
that has reached `origin`.

## Provenance and verification status

Card `trg-8652bf24`, split from `trg-79102ee3`. Evidence document:
`.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`,
which states plainly that only 3 of its 33 findings were verified by its author
and instructs *"Ground each fix before making it."* Findings 5, 12, 21, 22 and 28
are all in its **unverified** tiers.

**All five were therefore re-verified against the code in this run before any fix
was designed.** All five hold. Two of the audit's stated facts were re-measured
rather than inherited:

- The audit's "gating facts" section warns about `triage_gc.py` and
  `worktree_isolation.py`. Neither is touched by this change, so neither gates it.
  The gating fact that *does* bind was not in that section and is recorded under
  "Constraints discovered" below.
- The card's finding-28 measurement ("33 flips in the outbox, 26 with a tracked
  append") is from 2026-08-05 and no longer describes the store. Re-measured on
  the main tree at the start of this run: **18 outbox rows, 12 status flips, all
  12 undelivered, 11 of them invisible to `pendingDelivery`.** The magnitude is
  smaller than the card's but the defect is live and current.

## Acceptance Criteria

- [ ] **AC1 (finding 21)** — `split_records` recovers valid records that follow an
      unrecoverable prefix on the same physical line. The documented primary cause
      (a predecessor truncated mid-write, then appended onto) currently loses every
      record behind the damage; after the fix the valid records are returned and
      only the damaged span is reported as a fragment.
- [ ] **AC2 (finding 22)** — corruption reaches `read_all_items` consumers as
      retrievable data instead of being discarded, and the operator-facing report
      is not silenceable by a global warnings filter.
- [ ] **AC3 (finding 5)** — `read_jsonl_records` reads through `durable_read_text`
      so an unlocked reader retries past the Windows delete-pending window created
      by the sweep's `durable_atomic_write` publish, **without** changing which
      byte sequences separate records.
- [ ] **AC4 (finding 12)** — `mark_status` no longer spawns git subprocesses while
      holding the canonical append-log lock; the residence half of the routing
      decision, which genuinely depends on locked state, stays inside.
- [ ] **AC5 (finding 28)** — a status decision buffered in the gitignored outbox is
      visibly marked as not-yet-delivered on both the machine contract and the
      human listing. A delivered decision is not so marked.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** Every change restores behaviour the surrounding modules
  already document as their contract — `jsonl_records`' stated invariant *"on an
  append-only log, corruption must never read as absence"*, `durable_read_text`'s
  stated expectation that callers of `durable_atomic_write`-published files read
  through it, and `mark_status`' stated rule that the lock serialises store access.
  AC5 adds an output field, not a requirement: it makes an existing, already-
  required delivery distinction observable. No FR describes these internals.

## Out of Scope

- Findings 3, 14, 15–20, 23–27, 29 of the same audit — they belong to sibling
  cards P2.19a (`trg-2df5ac3d`), P2.19b (`trg-b854805c`), P2.19d (`trg-dc013d82`)
  and P2.19e (`trg-de99fdcb`), which remain open.
- The write-side and sweep/GC modules (`sweep_outbox`, `sweep_gc`, `triage_gc`,
  `reconcile_triage`, `sweep_drift`). This card is explicitly the **reader side**.
- Changing what the sweep delivers or when. AC5 only makes the existing buffered
  state *visible*; it does not add a delivery path.

### A deliberate deviation from the card's sequencing note, recorded

The card says finding 28 "is the measuring instrument for P2.19a and P2.19b and
should be built AFTER at least one of the two". Neither sibling is built. The card
nevertheless scopes all five findings to one iterate ("ein Iterate zieht die Karte
durch") and `--autonomous` forbids stopping to ask which reading wins.

Finding 28 is built here, because its own defect — the board showing a buffered
decision as delivered — is real and independently measured (11 live cases), and a
measuring instrument built before the thing it measures is not thereby wrong. The
sequencing note is honoured in the only way that costs nothing: the new surface is
additive and reports the state truthfully today, so when P2.19a/b land it measures
them without further change. **This is flagged for the operator in the F12 summary.**

## Constraints discovered (these shaped the design)

1. **`shared/scripts/triage.py` cannot grow by one line.** It is pinned in
   `shipwright_bloat_baseline.json` at `current: 882` and measures 882; the
   anti-ratchet fires on `measured > current` with no slack. Two of the five fixes
   land in this file. Consequence: new behaviour goes into a new sibling `lib`
   module and `triage.py` must come out net-neutral or smaller.
2. **`shared/scripts/tools/triage_cli.py` has ~6 lines of headroom.** It measures
   294 against the 300 limit and is *absent* from the baseline, so crossing 300
   creates a new Group-H1 crossing. Consequence: the finding-28 computation is a
   library derivation, not CLI code.
3. **`str.splitlines()` must not be used** to re-split the store. It breaks on nine
   characters git does not, so switching the reader from file-handle iteration to
   `splitlines()` would silently widen the record-separator alphabet. Recorded as a
   repo learning on 2026-07-28 after a forged-diff-boundary bug of exactly this
   shape.
4. **No import cycle.** `lib/jsonl_records.py` documents that this repo's CodeQL
   import-cycle findings (#281) began by parking shared logic in whichever module
   needed it first. The new module therefore takes **paths**, never `project_root`,
   and never imports `triage`.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `lib.atomic_write:durable_atomic_write` (via sweep/GC/repair rewrites) | `lib.jsonl_records:read_jsonl_records` | JSONL, UTF-8, surrogateescape |
| `triage:_append_line` | `lib.jsonl_records:split_records` | JSONL record boundary on one physical line |
| `triage:mark_status` (status event) | `lib.triage_integrity:undelivered_status_ids` | JSONL status event |
| `lib.triage_contract:build_listing` | Command Center WebUI `list --json` | JSON envelope, contractVersion 2 |

`touches_io_boundary` is **declared by hand** for this run. The path-based detector
`risk_detectors.is_io_boundary_change` returns False for every file here (it matches
config-file paths only, and its AST-pair detection is documented as deliberately
deferred), and no message keyword fired. The change nevertheless alters a record
decoder, a file-read encoding path and a machine-readable output contract, which is
what the flag exists to protect. Declaring it buys the Boundary Probe and the
round-trip requirement.

## Mini-Plan

### Chosen approach

One new leaf module plus five surgical edits. The new module exists because of
constraint 1 (`triage.py` cannot grow) and constraint 4 (no import cycle).

**New — `shared/scripts/lib/triage_integrity.py`** (takes *paths*, never a
project root; depends only on `jsonl_records`). It answers the two questions the
resolved item view structurally cannot:

- `store_corruption(*paths)` → the `CorruptFragment`s across the given store
  files (finding 22's data channel).
- `report_corruption(fragments, stream)` → the one operator notice, written to
  `sys.stderr` directly so no global warnings filter can silence it.
- `undelivered_status_ids(tracked_path, outbox_path)` → ids whose status event
  exists in the outbox but whose exact wire line is not present in the tracked
  store (finding 28).

**Edits**

1. `lib/jsonl_records.py::split_records` — on a decode failure, advance to the
   next plausible record start (`{`) and retry, instead of returning the whole
   tail as remainder. Emit the skipped span as the fragment. (AC1)
2. `lib/jsonl_records.py::read_jsonl_records` — read via
   `durable_read_text(..., errors="surrogateescape")`, then `split("\n")`.
   **Not** `splitlines()` (constraint 3). (AC3)
3. `triage.py::_iter_raw_lines_at` — delegate reporting to
   `triage_integrity.report_corruption`; drop the `warnings` import. Net −2 lines
   or better, satisfying constraint 1. (AC2)
4. `triage.py::mark_status` — hoist `should_route_to_outbox` above the `with`,
   keep the residence disjunct inside. Net-neutral. (AC4)
5. `lib/triage_contract.py` + `tools/triage_cli.py` — add a
   `pendingStatusDelivery` field (additive; **no** contract bump, per that module's
   own rule that a version bump is for shape changes, not new fields). (AC5)

   *Revised during build:* the human surface became a **store-level summary line**,
   not a per-row marker, and `lib/triage_render.py` is therefore untouched. The
   dominant case — an item dismissed while its flip sat in the outbox — resolves to
   a terminal status and leaves both listed sections, so a row marker cannot show
   it. Rationale carried in `format_pending_delivery_notice`'s docstring.

### Alternative considered and rejected

**Make `read_all_items` itself raise, or return a `(items, corrupt)` pair.**

Rejected on two independent grounds. Raising is the fail-closed blackout
`jsonl_records`' docstring records as explicitly rejected by its own spec review —
one damaged byte would take down every reader and every background producer.
Returning a pair is a breaking change to the single most-consumed function in the
triage surface (the audit itself names five unlocked call sites and there are
more), and it would have to be threaded through every caller to buy anything;
callers that did not opt in would still read absence. The chosen shape gives the
same information as a derived query any consumer can ask, plus a report on the two
surfaces an operator actually reads, at no cost to existing callers.

A second alternative — **redefining `pendingDelivery` to cover status events** —
was rejected because it silently changes the meaning of a field the Command Center
already renders, turning a contract break into something a consumer discovers as a
behaviour change rather than a parse error. A new field is honest and additive.

## External plan review — round 1, and what it changed

Both reviewers (openai, deepseek via openrouter) returned **revise**. Every
finding is answered below; the two `high` ones were settled by **measurement**,
not argument, and both changed the design.

| # | Finding | Resolution |
|---|---|---|
| 1 (high, openai) | Resyncing to "the next `{`" can surface an object embedded *inside* the damaged prefix as an independent record, and is quadratic. | **Confirmed real by probe** — the naive rule fabricated `{"b":1}` out of a truncated prefix `{"a":{"b":1},"c":"tr…`, and silently dropped the fragment. **Design changed:** a resync candidate is accepted only if the decode run from it consumes the *entire* remainder of the line. That rejected the fabricated record and recovered only the genuine one. Attempts are capped per line; on exhaustion the whole tail is the fragment (today's behaviour, fail-safe). |
| 2 (high, openai) + 1 (deepseek) | `durable_read_text(...).split("\n")` may not equal file-handle iteration; CRLF may leave a trailing `\r`. | **Refuted by probe.** Byte-identical across LF, CRLF, lone CR, no-final-newline, mixed, and invalid UTF-8 under `surrogateescape` — `read_text` applies the same universal-newline translation. The probe also **confirmed constraint 3**: `splitlines()` shatters one valid record into three on VT/FF/U+2028/NEL. No `rstrip("\r")` is needed and none is added. |
| 3 (medium, openai) | The corruption channel must scan the same store paths the listing read used, and stdout must stay valid JSON. | Adopted. The CLI derives items and corruption from the same two resolved paths; the notice goes to **stderr only**, and `list --json` carries the corruption as a field so stdout stays parseable. |
| 4 (medium, openai) | `undelivered_status_ids` semantics are ambiguous, and exact-line matching is brittle against re-serialization. | Adopted. Defined as **the item's latest (deciding) status event is not present in the tracked store** — that is the one that answers "has my dismiss reached origin". Comparison is on a **canonical sorted-key payload**, not the raw physical line, so re-serialization does not forge a false pending. |
| 5 (medium, openai) + 3 (deepseek) | Hoisting the git probe creates a TOCTOU window on the routing decision. | Accepted and documented rather than defended. The probe reads git refs, which the append-log lock never protected anyway, so the guarantee is unchanged in kind — only the sampling point moves earlier by the lock-wait. Recorded in the docstring as an advisory snapshot; the residence half stays inside the lock. |
| 6 (medium, openai) | Writing fragment bytes to stderr risks terminal-control injection (`surrogateescape` preserves arbitrary bytes). | Adopted. The notice reports path, line number and byte count only — never fragment content — and the path is rendered with `ascii()`. This matches the existing warning, which also never printed the text. |
| 7 (medium, openai) | An additive field is only safe if consumers tolerate unknown keys; avoid a second shape variant. | Adopted. `pendingStatusDelivery` is **always present as a boolean** on every row, exactly like `pendingDelivery`. `CONTRACT_VERSION` stays 2 per that module's own rule. |
| 8 (medium, openai) + 2 (deepseek) | The ledger is a placeholder; the fragment-collection mechanism is unspecified. | Adopted. Ledger filled before F0. On the mechanism: `split_records` keeps its existing `(records, remainder)` signature and `read_jsonl_records` keeps building `RecordRead.corrupt` from it — **no accumulator, no global, no signature change**, so DeepSeek's thread-safety concern does not arise. |
| 5 (low, deepseek) | Verify `warnings` has no other consumer in `triage.py` before dropping the import. | Verified: lines 38 (import) and 272 (sole use). Both go. |
| 4 (low, deepseek) | The resync fragment should read as "unrecoverable prefix", not "the whole tail". | Adopted — that is precisely what the guarded rule now produces. |

## External plan review — round 2, and what it changed

Re-run against the revised plan. openai returned **revise** again; deepseek's
verdict token was unreadable (`unknown`), so it is counted as neither approval nor
rejection. Round 2 found a defect round 1 had not — and it was **already shipped in
the working tree** when it arrived, which is exactly why the second pass was worth
running.

| # | Finding | Resolution |
|---|---|---|
| 1 (high) | The "candidate run must reach end-of-line" rule still fabricates: a damaged prefix ending `…"meta":{"embedded":1}` followed by a real append lets ONE run consume both and reach EOL, surfacing `embedded` as a record. | **Reproduced against my own implementation** — it returned `[{'embedded': 1}, 'trg-real']`. Necessary but not sufficient, exactly as claimed. **Design changed again:** recovery now requires a caller-supplied `is_record` predicate that **every** object in the run must satisfy, and **does nothing without one** (fails closed to pre-2026-08 behaviour). I measured why no built-in default is possible: the triage store keys records on `event` (1464/1465 live records, **0** containing a nested object), while `shipwright_events.jsonl` — which reads through the same leaf — keys on `type` and **306 of 799 records DO nest**. A default would be wrong for one of them. |
| 2 (high) | The attempt cap makes correctness depend on corruption shape, and the algorithm is quadratic up to the cap. | Accepted as an explicit, documented operational limit rather than papered over. With the predicate the candidate set is far smaller, and exhausting the cap degrades to reporting the whole span — never to a hang or to fabrication. Pinned by the two-sided budget pair in `test_triage_record_boundary_recovery.py` (the single-sided test first written here was vacuous — see the Stage-1 section below). |
| 3 (medium) | `store_corruption` rescans files the listing already read, so items and corruption can come from different snapshots. | Accepted as best-effort and documented. It is an advisory display, and the alternative — threading `RecordRead` through the whole listing path — would grow `triage.py`, which cannot take a single line. Recorded as a known limitation rather than silently. |
| 4 (medium) | "has reached origin" overclaims: tracked-store presence proves the event left the outbox, not that its commit was pushed. | **Correct, and my wording was wrong.** Both the function docstring and the operator notice now say *"not committed to any branch yet"*, and the docstring states explicitly that nothing here reads a remote. |
| 5 (medium) | Additive field still needs its consumers checked. | Verified in-repo: `build_listing` has exactly one production caller and no JSON schema, fixture, or golden file pins the row shape (`shared/schemas/triage_item.schema.json` versions the *stored* record, not this output). The Command Center is a separate repository and is **flagged in the F12 summary** rather than assumed. |
| 6 (medium) | Reporting must handle missing/unreadable stores, and repeated calls duplicate stderr notices. | **The duplicate was real**: one `triage_cli list` calls `_iter_raw_lines_at` four times, so one damaged span was announced four times, reading as four problems. Now reported once per distinct span per process, display-only — `store_corruption` still recomputes from the files, so no consumer's view changes. Missing stores were already handled and are pinned by a test. |
| 7 (low) | Bound the corruption representation so a malformed log cannot flood the operator. | The notice already reports shape only (path, line, byte count) and the pending-delivery list is capped at 5 ids with a `(+N more)` tail. |

### A note on where the external review payloads live

`reviews.json` carries the **round-2** payload (the last one run). Round 1's raw
JSON was not persisted — its findings are transcribed in the round-1 table above,
which is therefore the only record of them. Anyone auditing an attribution in that
table against `reviews.json` will find the two describe different rounds; that is
this gap, not a mis-citation. Recorded rather than quietly left to be discovered
(Stage-2 code review).

## Stage-1 spec review (internal `spec-reviewer`) — REJECTED, and what it changed

The hard gate rejected the first implementation with three blocking findings. All
three were real; the most serious was a **data-loss path this change itself
created**. Every one was reproduced before being fixed.

| # | Finding | Resolution |
|---|---|---|
| 1 (blocking) | The `list --json` corruption field promised in the round-1 review resolutions was **never built** — `store_corruption` had no production caller anywhere, so AC2's "retrievable data" channel existed only in tests. | Correct: I recorded an adopted resolution and then did not implement it. `build_listing` now takes a **required** `corruption` argument and the envelope carries a `corruption` block (`count`, `truncated`, `spans` with basename/line/bytes — shape only, capped at 20). `triage_cli` supplies it from the same two paths the listing read. |
| 2 (blocking) | The resync-cap test was **vacuous** — its input had no predicate-satisfying candidate, so deleting `_MAX_RESYNC_ATTEMPTS` left it green. | Correct, and the exact failure my own conventions warn about. Replaced with a **two-sided pin**: a record within budget IS recovered, one beyond budget is NOT. Mutation-verified in-process — with the cap the record is absent, with the cap removed `trg-toofar` is recovered, so the test now genuinely fails without the cap. |
| 3 (blocking) | My new notice tells the operator to run `triage_repair.py`, and that tool called `split_records` **without** the predicate — so it would rewrite the file **deleting the very record the reader had just recovered**. | **Reproduced end-to-end before fixing**: the reader returned `trg-SURVIVOR`, and `scan_path` produced `lines=[]`, quarantining the whole line — the survivor absent from the rewritten content. `triage_repair.scan_path` now passes `is_record=is_triage_record` (both files it targets are triage stores). Pinned by `test_repair_does_not_delete_the_record_the_reader_recovers`. |
| 4 (medium) | `triage_integrity`'s own reads did not use the predicate it defines, so corruption spans disagreed with the reader's (double-announcing) and a buffered decision behind a damaged prefix would read as **delivered**. | Correct — a false reassurance in the one function whose docstring forbids exactly that. Both `store_corruption` and `undelivered_status_ids` now read with the predicate. |
| 5 (medium) | `atomic_write.durable_read_text`'s docstring still said *"no triage-store reader goes through here"* — falsified by this very diff. | Rewritten in the same diff, net-neutral in line count so the file stays at its 300 limit. |
| 6 (note) | `triage_cli.py` now sits at exactly 300. | Confirmed and re-confirmed after the corruption wiring; the module docstring was compressed to pay for the new lines. |

The reviewer also **independently corroborated** three of the spec's measured
claims from the diff itself (the 1464/1465 `event` count, the 0-nested triage
result, and the 12-flips/11-masked figures), and correctly flagged the 306/799
events-log figure as measured-but-not-reproducible from this diff — it is recorded
here as such. It judged the finding-28 sequencing deviation honest and adequate.

## Stage-2 code review (internal `code-reviewer`) — REQUEST_CHANGES, and what it changed

Stage 1 passed, so this pass reviewed correctness and quality. It found **a second
false-reassurance defect** that two external rounds and Stage 1 had all missed, plus
four mediums. Reproduced before fixing, as before.

| # | Finding | Resolution |
|---|---|---|
| 1 (high) | `undelivered_status_ids` mirrored `read_all_items`' *ordering* but not its two pass-2 **filters**. A later status event with an out-of-vocabulary `newStatus` in the tracked store out-ranked — and masked — an older, genuinely buffered `dismissed` in the outbox. | **Reproduced**: the board showed `dismissed` (the buffered flip) while the function returned `set()` — a false reassurance, the one direction this marker must never fail in. Both filters are now mirrored (`newStatus in applied_statuses`, and id must have an `append`). `applied_statuses` is a **required** kwarg supplied as `triage.STATUSES`. Pinned by `test_out_of_vocabulary_tracked_event_cannot_mask_a_buffered_flip` and `test_a_status_event_with_no_append_is_not_named`. |
| 2 (medium) | `is_triage_record` accepted *any* object with a string `event`, justified by a measurement rather than an invariant — and it now feeds a **writer** (`triage_repair` re-serialises its output back into the file), so a fabricated record would be written into the log. | Tightened to match the writers: `event in ("append","status")` **and** a string `id`. A stray nested `{"event": …}` in wreckage no longer qualifies. |
| 3 (medium) | `list --json` read each store four times over, on a command the WebUI polls. | Added `store_facts`, which returns corruption + undelivered from **one** read of each file; the CLI now uses it. Halves the reads this change introduced. |
| 4 (medium) | `triage_integrity`'s ADR-045 fallback is **live in production** (`_iter_raw_lines_at` loads it on every store read) but untested, and its comment claimed otherwise. | Added `test_triage_integrity_sentinel_mode_works`, which drives the fallback and exercises `store_corruption` / `is_triage_record` / `store_facts` through it. The dual-`CorruptFragment`-class consequence is now recorded in the module so nobody adds an `isinstance` check across that boundary. |
| 5 (medium) | The delivery notice said "shown here" while the dominant case is precisely the one *not* shown, and its literal contained an em dash, breaking the ASCII claim its own docstring makes. | Reworded to "in this store … (some may not appear in the lists above)" and made ASCII throughout. |
| 6–14 (low) | Unused `stream` param; `_REPORTED` keyed on byte-length with the mark written before the report; basename computed two different ways; `shared_lib_loader`'s docstring stale in the same way `atomic_write`'s was; dangling clause in the `mark_status` docstring; the refused-flip probe cost; `_ts_key` duplication unenforced; Mini-Plan naming a file the design no longer touches. | All applied. `_span_key` now hashes span **content** (matching `triage_repair._fragment_key`) and marks only after a successful write; one shared `basename`; `shared_lib_loader`'s rule rewritten to "spell it both ways" and naming the two modules that do; `_ts_key` agreement is now a **test** (`test_delivery_check_agrees_with_the_reader_on_the_deciding_event`) rather than a comment. |

**Two files were split** under the 300-line limit as a direct result: `triage_integrity`
shed its delivery half into the new pure-stdlib leaf `lib/triage_delivery.py` (no
intra-package imports at all, so the no-cycle constraint holds by construction), and
`test_triage_reader_integrity.py` shed its AC5 tests into
`test_triage_delivery_visibility.py` along the same seam.

The reviewer also confirmed what it could not break: no third fabrication hole in the
resync (the leftmost genuine record start is always a candidate, so an interior
candidate can only win if it precedes it — exactly the case the predicate gates), the
cap pin is genuinely two-sided, the `(ts, file-order)` ordering mirror is faithful, the
hoist adds no new exception path, and all four import spellings of `jsonl_records`
resolve.

## External CODE review — and a FOURTH fabrication hole

Run on the production-code slice after Stage 2 approved. `openai` returned
**revise** (deepseek unavailable, so one opinion, recorded as such).

| # | Finding | Resolution |
|---|---|---|
| 1 (high) | The predicate `event in ("append","status") and isinstance(id, str)` is satisfied by a **two-key stub**, so wreckage containing `{"meta":{"event":"append","id":"forged"}` followed by a genuine append still fabricates `forged` — and `triage_repair` writes it into the log. | **Reproduced**: `recovered: ['forged', 'trg-real']`. This is the **fourth** distinct fabrication shape and the **third narrowing** of this predicate. Each earlier version was justified by a property of *today's data*; this one is read off the **writers** — `_REQUIRED_KEYS` lists every key `append_triage_item` and `mark_status` always emit, so a nested object must now be a COMPLETE record to qualify. The residual limit is stated honestly in the docstring rather than claimed away. Pinned by three new tests, including one proving a genuine `status` record is still recovered. |
| 2 (medium) | `bytes` in both the notice and the JSON block was `len(f.text)` — **code points, not bytes**, so a span holding one two-byte character reported "1 byte" against a contract that says byte count. | Fixed with one shared `span_bytes()` encoding through `surrogateescape`; both surfaces use it. Pinned by `test_the_notice_counts_BYTES_not_code_points`. |
| 3 (medium) | The JSON corruption block was capped but the **stderr notice was not** — a badly damaged log produces one line per fragment, unbounded. | Capped at 20 detail lines with a `(+N more not shown)` tail; the header still carries the true total. Pinned by `test_the_notice_is_bounded_on_a_badly_damaged_store`. |

**What finding 1 cost, and what it bought.** The stricter predicate broke seven
existing fixtures — all of which used minimal `{event,id,ts}` stubs. That is the
finding restated: those fixtures were not records, and a test suite built on
non-records cannot notice a non-record being recovered. They now construct what
the writer writes. `test_triage_record_boundary_recovery.py` was split again at the
300-line limit, shedding the durable-read half into `test_triage_durable_read.py`.

## Stage-3 doubt review - 10 doubts, and the one that half-unbuilt AC5

The adversarial pass ran with **no execution tool**, so its findings are read-derived
and it said so. It still produced the single most consequential finding of the run.

| # | Doubt | Resolution |
|---|---|---|
| 1 (high) | **AC5 was half-delivered.** `pendingStatusDelivery` is a per-ROW boolean, but the dominant case - an item dismissed while its flip sat in the outbox - resolves to a terminal status and leaves BOTH sections, so no row can carry it. `list --json` therefore reported "everything delivered" on a store with 12 buffered decisions. Worse: `test_buffered_decision_round_trips_to_the_json_contract` abandoned the CLI mid-test and asserted in-process, so it **confirmed** the gap its name claimed to disprove. | **Correct, and the most consequential finding of the run.** The Command Center - the one consumer this field exists for - was getting the surface that structurally cannot show the defect. FIXED: the envelope now carries a top-level `undeliveredDecisions` block (`count` / `truncated` / capped `ids`), mirroring `corruption`. The round-trip test asserts through the CLI's own stdout on a dismissed item, and a companion pins the clean case. |
| 2 (high) | **AC3 and AC4 work against each other**, and no earlier pass connected them. AC4 removed ~3 git subprocesses from the lock; AC3 routes four *in-lock* reads through `durable_read_text`, whose retry budget is 2 s - so under exactly the Windows delete-pending condition AC3 exists for, in-lock time can grow by up to 8 s where it previously failed fast. AC4's ordering test stays green while its stated goal inverts. | **Accepted and recorded, not silently absorbed.** The trade is deliberate - the old bare `open` *crashed* the reader in that window, which is finding 5's whole point - but the lock-hold consequence was never costed. Recorded here and in F12 as **unmeasured**. The honest next step is a `budget_seconds` parameter on the durable reader so a locked section can ask for a shorter one; `atomic_write.py` is at its 300-line limit, so that is a next-touch item. |
| 3 (medium) | The resync can still fabricate via a nested status-shaped object, and `triage_repair` writes it. | **Already closed by code that post-dates the review** - it read the v2 predicate; the external code review had already forced v3 (every writer-emitted key). Verified: the cited input now yields only `trg-REAL`. Its *stronger* suggestion - gate the WRITER by re-emitting recovered lines verbatim rather than re-serialising - is recorded as the better architecture and deliberately not taken here. |
| 4 (medium) | `CONTRACT_VERSION` should have bumped: `corruption` is an ENVELOPE key, and `corruption.count > 0` means `open`/`deferred` may be INCOMPLETE - so a v2-pinned consumer renders an incomplete board as complete. | Accepted as a real argument. Version stays 2 because bumping breaks the WebUI *immediately* for a field it does not yet read - a certain outage traded for a silent risk. The module docstring now records the revision **and** the incomplete-board consequence, in the file designated as the one a reviewer reads. Flagged in F12. |
| 5 (medium) | Both ADR-045 fallbacks **prepend** a 160+-module directory to `sys.path` for the process lifetime; the repo's own `collectors/_lib_loader.py` documents the opposite discipline. | Accepted and FIXED: `sys.path.append`, not `insert(0)`, in both modules, with the `_lib_loader` precedent named. Appending suffices and cannot shadow a plugin's own `lib`. |
| 6 (medium) | The round-2 table answers openai's seven findings one-to-one and leaves **deepseek's six unanswered**, including a HIGH about buffering the whole store. | Accepted - see the table below. The memory finding is answered with a **measurement** rather than an argument. |
| 7 (medium) | The hoist's widened window can produce *tracked-on-idle-main* drift, which `mark_status` itself calls undelivered drift needing a manual CLI. | Accepted; it misplaces rather than loses (both stores are union-read). Recorded, with `reconcile_main_triage` named as the recovery. |
| 8 (low) | A docstring cites a test that **does not exist** - introduced by the Stage-2 fix, the same false-reassurance shape this run spent the day closing. | Accepted and FIXED. |
| 9 (low) | `_REPORTED` is module-global, so "once per process" is really "once per loaded module". | Accepted and FIXED by weakening the claim, not the code. |
| 10 (low) | `durable_read_text` retries winerror 5, which is ambiguous, so an ACL-denied store stalls ~2 s per read; triage reads also pollute the shared retry tally. | Accepted as real and low; recorded. |

### The deepseek round-2 findings, answered

| # | Finding | Disposition |
|---|---|---|
| 1 (high) | Reading the entire store into memory risks OOM or latency. | **Measured**: the live `triage.jsonl` is **1.41 MB**, so a full read is ~1.4 MB transient. `store_facts` already halved this change's added read count. Accepted at this size; the measurement is the answer, and it is recorded so a future 10x store re-opens the question. |
| 2 (medium) | TOCTOU producing spurious `pendingStatusDelivery`. | Same window as doubt 7 and round-1 #5; misplaces rather than loses, now recorded in both directions. |
| 3 (medium) | The resync heuristic. | Superseded three times over; closed by the writer-derived predicate (v3). |
| 4-6 (low) | Fragment-collection mechanism, `warnings` consumer check, resync fragment wording. | All addressed in the round-1/round-2 tables (no accumulator; `warnings` verified sole-use; the fragment is the prefix). |

**Attribution note.** The round-1 table credits deepseek for the CRLF claim.
`reviews.json` holds the round-2 payload, where deepseek #1 is the memory finding -
so an auditor comparing the two finds a mismatch. Round 1's raw JSON was never
persisted; the round-1 table is its only record. Recorded rather than reconstructed.

## Confidence Calibration

- **Boundaries touched:** the four rows above — JSONL record decoding, the
  store read path's encoding/newline handling, the status-event wire shape, and
  the `list --json` envelope.

- **Empirical probes run** (each ran against real code before the corresponding
  design decision, not after):

  | Probe | Finding |
  |---|---|
  | Pre-fix reproduction of 21/22/28 against the shipped modules | All three reproduced. 21 lost `trg-bbbb` entirely; 22 returned a bare `list` with corruption dropped and **0 warnings under `-W ignore`**; 28 reported `pendingDelivery=False` for a decision sitting in the gitignored outbox. |
  | Live re-measurement of the card's finding-28 numbers | Card said 33 flips / 26 masked (2026-08-05). Actually **18 outbox rows, 12 status flips, 12 undelivered, 11 masked** today. Defect confirmed live; the card's magnitude was stale. |
  | Newline equivalence: file-handle iteration vs `durable_read_text(...).split("\n")` | **Byte-identical** across LF, CRLF, lone CR, no-final-newline, mixed, invalid UTF-8. Refuted the reviewers' `\r` claim. Same probe showed `splitlines()` shatters one record into three on VT/FF/U+2028/NEL — which is why it is banned in the docstring. |
  | Naive vs guarded resync on four corruption shapes | Naive fabricated `{"b":1}` from the wreckage AND silently dropped the fragment. Guarded rejected it. |
  | Nested-object resync probe (after round-2 review, against my own shipped code) | **My guarded rule still fabricated** `{'embedded': 1}`. Necessary-but-not-sufficient confirmed; forced the `is_record` predicate design. |
  | Record-shape survey of both logs reading through the leaf | Triage: 1464/1465 carry a string `event`, **0** nest. Events log: **0** carry `event` (they use `type`), **306/799 nest**. Proves no built-in default predicate can be correct — the leaf must fail closed. |
  | Sentinel-vs-package import mode of `jsonl_records` | Under path-load `__package__ == ''`, the relative import fails and `durable_read_text` binds from top-level `atomic_write` — the fallback is live, not dead code. |
  | Interpreter check | `uv run pytest` resolved a **Python 3.13** pytest while the worktree venv is 3.11; CI is 3.11. `uv sync --extra dev` fixed it. Every result recorded here is measured on 3.11. |

- **Test Completeness Ledger** — principle: *testable ⇒ tested*. 0 untested-testable.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | A valid record after a truncated predecessor is recovered (AC1) | tested | `test_valid_record_after_a_truncated_predecessor_is_recovered` PASSED |
  | 2 | A simple nested object in the damaged prefix is not fabricated | tested | `test_resync_never_fabricates_a_record_from_inside_the_damaged_prefix` PASSED |
  | 3 | A *complete* nested object followed by a real record is not fabricated | tested | `test_resync_rejects_a_complete_object_nested_in_the_damaged_prefix` PASSED |
  | 4 | Without `is_record`, recovery fails closed to pre-fix behaviour | tested | `test_without_a_predicate_recovery_fails_closed` PASSED |
  | 5 | A foreign-shaped (events-log) object is not recovered as a triage record | tested | `test_a_foreign_shaped_object_is_not_recovered_as_a_triage_record` PASSED |
  | 6 | Pure garbage keeps today's behaviour | tested | `test_unrecoverable_line_with_nothing_valid_behind_it_is_unchanged` PASSED |
  | 7 | A valid record followed by a damaged tail still reports the tail | tested | `test_valid_record_followed_by_a_damaged_tail_still_reports_the_tail` PASSED |
  | 8 | A scalar between records no longer swallows the second | tested | `test_a_scalar_between_two_records_does_not_swallow_the_second` PASSED |
  | 9 | Resync respects its attempt budget — a record within it is recovered, one beyond it is not | tested | `test_a_record_within_the_resync_budget_is_recovered` + `test_a_record_beyond_the_resync_budget_is_not_recovered` PASSED. **Mutation-verified**: removing `_MAX_RESYNC_ATTEMPTS` makes the second recover `trg-toofar`, i.e. fail. The prior single-sided version was vacuous and was caught by Stage 1. |
  | 10 | The reader goes through `durable_read_text` (AC3) | tested | `test_reader_goes_through_the_durable_read_path` PASSED |
  | 11 | Separator alphabet unchanged: LF/CRLF/lone CR/no-final-newline | tested | `test_record_separators_are_unchanged_by_the_durable_read` PASSED |
  | 12 | Raw VT/FF stay on one physical line (one fragment, not three) | tested | `test_raw_control_bytes_stay_on_one_physical_line` PASSED |
  | 13 | U+2028 does not split a valid record | tested | `test_unicode_line_separator_inside_a_record_does_not_split_it` PASSED |
  | 14 | `surrogateescape` survives the switch | tested | `test_undecodable_bytes_still_degrade_to_a_fragment` PASSED |
  | 15 | A missing file still reads empty | tested | `test_missing_file_still_reads_empty` PASSED |
  | 16 | Both ADR-045 import modes resolve and *work* | tested | `test_package_mode_…`, `test_sentinel_mode_…`, `test_sentinel_mode_actually_reads_a_store` PASSED (+ a guard test proving the subprocess probe can fail) |
  | 17 | Corruption is retrievable as data, across both stores, tolerating absence (AC2) | tested | `test_store_corruption_reports_the_damaged_span`, `…_spans_every_given_store`, `…_tolerates_a_missing_file` PASSED |
  | 18 | The notice survives a global warnings filter | tested | `test_corruption_notice_survives_a_global_warnings_filter`, `test_iter_raw_lines_reports_even_under_a_blanket_warnings_filter` PASSED |
  | 19 | The notice never echoes fragment bytes, and is ASCII-safe | tested | `test_corruption_notice_never_echoes_the_fragment_bytes`, `test_corruption_notice_is_ascii_safe` PASSED |
  | 20 | The notice goes to stderr, never stdout; a clean store is silent | tested | `test_iter_raw_lines_reports_corruption_to_stderr`, `test_a_clean_store_produces_no_stderr_noise` PASSED |
  | 21 | One damaged span is announced once per process | tested | `test_one_damaged_span_is_announced_once_per_process` PASSED |
  | 22 | The routing probe runs OUTSIDE the canonical lock (AC4) | tested | `test_routing_probe_runs_outside_the_canonical_lock` PASSED — asserts ordering, so it fails if the probe moves back inside, not only if deleted |
  | 23 | Residence routing (outbox-only, tracked, refused precondition) is unchanged | tested | `test_residence_still_routes_an_outbox_only_item_to_the_outbox`, `test_tracked_item_flip_stays_tracked`, `test_precondition_failure_still_writes_nothing` PASSED |
  | 24 | Undelivered detection: outbox-only pending, tracked delivered, canonical not byte-literal, deciding-event-only, missing outbox (AC5) | tested | `test_status_flip_only_in_the_outbox_is_undelivered`, `…_present_in_the_tracked_store_is_delivered`, `test_delivery_check_is_canonical_not_byte_literal`, `test_only_the_deciding_status_event_counts`, `test_a_missing_outbox_means_nothing_is_pending` PASSED |
  | 25 | `pendingStatusDelivery` always present as a boolean in both sections; `pendingDelivery` unchanged | tested | `test_listing_always_carries_a_boolean_pending_status_delivery`, `test_pending_delivery_field_is_unchanged` PASSED |
  | 26 | End-to-end: real writers → real files → real CLI subprocess reports the buffered decision | tested | `test_buffered_decision_round_trips_to_the_json_contract`, `test_open_item_with_a_buffered_flip_carries_the_field`, `test_human_listing_names_the_uncommitted_decisions` PASSED |
  | 27 | No false alarm when the decision is committed | tested | `test_a_fully_delivered_store_says_nothing` PASSED |
  | 28 | `list --json` stdout stays parseable when a store is corrupt | tested | `test_json_stays_parseable_when_a_store_is_corrupt` PASSED |
  | 29 | The `corruption` block is present and clean on a healthy store, carries shape never content, and is capped with `truncated` | tested | `test_a_clean_store_reports_an_empty_corruption_block`, `test_corruption_block_carries_shape_never_content`, `test_corruption_block_is_capped_and_says_so` PASSED |
  | 30 | `triage_repair` keeps the record the reader recovers, and still quarantines the damaged prefix | tested | `test_repair_does_not_delete_the_record_the_reader_recovers` PASSED — the data-loss path Stage 1 found, reproduced before the fix |
  | 31 | `list --json` reports corruption as data, not only on stderr | tested | `test_json_stays_parseable_when_a_store_is_corrupt` PASSED (asserts `corruption.count` and the span's path) |
  | 32 | The existing envelope-shape test still pins the top-level key SET exhaustively, plus every key it pinned before, plus the new block | tested | `test_list_json_empty_is_two_empty_sections` PASSED. My first rewrite dropped the exhaustiveness the whole-dict `==` gave and I wrongly called it "strictly stronger"; Stage 1 refused that claim and the key-set assertion was restored |
  | 33 | An out-of-vocabulary tracked status event cannot mask a buffered flip, and an orphan status is not named | tested | `test_out_of_vocabulary_tracked_event_cannot_mask_a_buffered_flip`, `test_a_status_event_with_no_append_is_not_named` PASSED — the Stage-2 high, reproduced before the fix |
  | 34 | The delivery check and `read_all_items` agree on which event decides | tested | `test_delivery_check_agrees_with_the_reader_on_the_deciding_event` PASSED — converts the `_ts_key` duplication comment into a gate |
  | 35 | `triage_integrity`'s ADR-045 fallback resolves AND works (it is live on every store read) | tested | `test_triage_integrity_sentinel_mode_works` PASSED |
  | 36 | An empty `applied_statuses` is refused rather than silently reporting "nothing pending" | tested | `test_an_empty_status_vocabulary_is_refused` PASSED — requiring the kwarg stops a caller forgetting it; only this stops one disabling the check |
  | 37 | A minimal forged stub nested in wreckage is rejected, for BOTH event kinds, while a genuine `status` record behind damage is still recovered | tested | `test_resync_rejects_a_minimal_forged_record_nested_in_the_prefix`, `test_a_status_shaped_stub_is_also_rejected`, `test_a_complete_status_record_after_damage_is_still_recovered` PASSED — the external code review's high, reproduced first |
  | 38 | Corruption byte counts are BYTES, on both surfaces | tested | `test_the_notice_counts_BYTES_not_code_points` PASSED |
  | 39 | The stderr notice is bounded and still reports the true total | tested | `test_the_notice_is_bounded_on_a_badly_damaged_store` PASSED |
  | 40 | The envelope carries `undeliveredDecisions`, so a buffered decision is visible to a consumer that reads no matching row | tested | `test_buffered_decision_round_trips_to_the_json_contract` (rewritten to assert through the CLI), `test_a_clean_store_reports_no_undelivered_decisions`, plus the envelope key-set pin PASSED |
  | 41 | The Command Center renders the new field correctly | untestable | `covered-by-existing-test` is **not** claimed. The WebUI is a separate repository with no executable consumer in this tree; the in-repo contract surface is covered by rows 25–40. Flagged to the operator in F12 rather than asserted. |

- **Confidence-pattern check:**
  - *Asymptote (depth).* The question "is the resync sound?" was asked three
    times and answered differently each time: naive → fabricates; guarded →
    still fabricates on a nested-complete-object prefix; predicate-gated →
    holds. Each step was settled by running the code, and the second step was
    caught **only** because a second external review ran against an
    already-implemented change. Depth was the load-bearing dimension here.
  - *Coverage (breadth).* Both logs that read through the leaf were surveyed, not
    just the one this card names — which is what showed a default predicate would
    be wrong. Both ADR-045 import modes are exercised in subprocesses. Both
    delivery directions (pending / not pending) and both notice states
    (present / silent) are asserted, so no assertion can pass vacuously.
  - *Integration composition.* `cross_component` does **not** fire on this diff
    (checked with `risk_detectors.is_cross_component_change`: `False`), so no
    `category:"integration"` behavior is owed. Rows 26–28 nevertheless drive the
    real producer → file → CLI-subprocess chain, because the units alone cannot
    see a wiring error between the writer, the derivation and the contract.

## Notes

Reviewer attention is most warranted on AC1 and AC3, which are the two changes
that can silently alter what the store *means*: AC1 changes which byte spans are
treated as records, and AC3 changes how bytes become lines. Both are behaviour-
preserving by intent and neither is safe on inspection alone.
