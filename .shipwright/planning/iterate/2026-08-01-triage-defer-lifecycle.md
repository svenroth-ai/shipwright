# Iterate Spec: defer means defer — the park lifecycle

- **Run ID:** iterate-2026-08-01-triage-defer-lifecycle
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented
- **Card:** `trg-49f354ad` (split out of anchor `trg-4ebc928e`; content from
  `trg-51f8e2a1`). S1 delivered PR #509, S2 delivered PR #513 — this unit is
  unblocked and standalone.
- **Operator decisions (input, not re-derived):**
  `.shipwright/planning/iterate/2026-07-27-triage-defer-review-followup.md`
  § *Operator decisions taken 2026-07-27* — four plain-language questions, all
  four answered. The fifth part (cap) comes from `trg-51f8e2a1` part 5.

## Goal

Today `defer` records a decision that almost nothing downstream honours: a
parked finding re-appears as a **new** open item on the next import, never
closes when the problem goes away, is invisible to every surface except the
terminal listing, cannot be reversed by any command, and prints uncapped. Make
the third decision mean what the glossary already promises.

## Acceptance Criteria

### Part 1 — a park has a revisit date, and the park expires by itself

- [x] **AC-1** Given an operator parks an entry, when they do not name a date
      the entry should come back on, then the command refuses and nothing is
      written. The date is **required** on every surface this repo owns
      (`triage_cli.py defer`, and the `defer()` helper behind it).
- [x] **AC-2** Given a parked entry whose revisit date has **not** passed, when
      any consumer reads the store, then it reads as parked.
- [x] **AC-3** Given a parked entry whose revisit date **has** passed, when any
      consumer reads the store, then it reads as **open** — it is back on the
      open list without anyone doing anything, and without a second decision
      being written to the log. (A park expiring is not a decision anybody
      made; the append-only log records decisions.)
- [x] **AC-3a** Given the exact moment a park becomes due, then it is defined in
      one place and one way: **a park named for day D is due from 00:00:00 UTC
      on D**, i.e. due when `now_utc.date() >= D`. On D the entry is open, on
      D−1 it is parked. Stated because the plan's first draft left it to be
      inferred, and both external reviewers picked the ambiguity independently.
      Accepted and documented cost: an operator west of UTC sees an entry return
      up to ~14 hours before their local midnight on D. Sub-day precision is
      meaningless for a backlog park, so no timezone model is introduced (YAGNI).
- [x] **AC-4** Given a machine-raised finding that is parked and whose revisit
      date has not passed, when the same check raises the same finding again,
      then no second entry is created — the park suppresses the re-import.
      Today the dedup scan only suppresses against an **open** match, so
      parking a machine-raised finding yields a duplicate open entry **plus** a
      permanent parked one, which makes parking close to a no-op.
- [x] **AC-5** Given a parked entry whose revisit date has passed, when the same
      check raises the same finding again, then still no second entry is
      created — because AC-3 already put the original back on the open list, and
      the existing open-match rule suppresses it.
- [x] **AC-6** Given a revisit date that is not a date this project can read,
      when it is offered, then the command refuses with a message naming the
      accepted form (`YYYY-MM-DD`), rather than storing a value that later
      resolves to "never due" or "always due".
- [x] **AC-7** Given a stored entry carrying a damaged or missing revisit value
      (hand-edited file, or a park written before this change), when it is read,
      then it resolves as **parked, not due** — the conservative direction: an
      unreadable date must not silently re-open an entry, and must not silently
      bury one either (it stays visible in the parked section, which AC-11/AC-12
      make visible everywhere).

### Part 2 — a park closes itself when the finding goes away

- [x] **AC-8** Given a parked entry raised by a producer that auto-closes its own
      findings, when that producer next runs successfully and the finding is
      gone, then the parked entry is closed automatically — exactly as an open
      one is. This holds whether or not the revisit date has passed.
- [x] **AC-9** Given the same producer run, when a person uses a cooperating
      Python writer to **dismiss or promote** an entry between the producer's
      unlocked read and its write,
      then the producer still refuses and reports the entry KEPT — the
      `trg-93ceb2b0` guarantee delivered by S2 survives this change for every
      decision that ends the entry's life. The Command Center's
      `proper-lockfile` does not compose with Python `FileLock`; extending this
      guarantee to WebUI writes is tracked by `trg-97aeaede`.
- [x] **AC-9a** Given a person **parks or re-parks** an entry in that same
      window, then the producer's close **proceeds**, because the producer knows
      something the parker did not: the finding is gone. This is a deliberate
      narrowing of what `expected_status` protects, it follows directly from
      operator decision #2 ("a parked entry closes automatically when its
      underlying finding disappears, exactly like an open one"), and it is
      recorded here and in the shared constant's own docstring rather than left
      to be discovered. An external reviewer read the widening as an accidental
      weakening of S2 — it is neither accidental nor a weakening of what S2 was
      built to protect, and the integration test asserts this outcome explicitly
      rather than asserting a refusal that would contradict decision #2.
- [x] **AC-10** Given every producer that auto-closes findings, when the set of
      statuses it may close is read, then all of them read it from **one**
      declared place, so a future producer cannot be added with a different
      answer.
- [x] **AC-10a** Given every consumer whose behaviour depends on an entry's
      status, then it reaches that status through `read_all_items` (so expiry is
      applied for it), or it is recorded here as deliberately reading the
      **stored** status. Audit result, verified at code: one deliberate
      exception — `triage_gc._resolve_tracked_only`, which resolves a single file
      from stored events to decide droppability, and is unaffected because it
      never drops `triage` **or** `snoozed`. Everything else status-sensitive
      goes through `read_all_items`.

### Part 3 — a parked entry is visible on every surface

- [x] **AC-11** Given parked entries exist, when the machine-readable listing is
      produced (`triage_cli.py list --json`), then they are present in their own
      section, each carrying its revisit date. This is a **breaking change to a
      cross-repo output contract**, taken deliberately (operator decision #3):
      the output gains an explicit contract version so a consumer can tell the
      shapes apart.
- [x] **AC-11a** Given the machine-readable listing, then it is **never capped**
      — both sections are complete. The cap of AC-16 is a property of the two
      human surfaces only. A cap applied to the machine contract would silently
      drop data from a consumer that has no way to know it happened, which is
      the failure this whole run exists to stop.
- [x] **AC-12** Given parked entries exist, when the agent-facing document
      `triage_inbox.md` is rendered, then they appear in their own section with
      their reason and revisit date — not as the bare count it shows today.
- [x] **AC-13** Given the Command Center mirrors the machine-readable listing in
      its own implementation and pins it with a committed fixture, when this
      contract changes, then the follow-up in that repository is **filed as a
      triage card**, because it cannot ship in this repository's PR. Silently
      changing the contract and saying nothing is what this criterion forbids.

### Part 4 — a mistaken park can be reversed

- [x] **AC-14** Given an entry was parked by mistake, when the operator runs
      `triage_cli.py unpark <id> --reason <text>`, then it returns to the open
      list with that reason recorded and its revisit date cleared, and no
      hand-editing of the log is required. (Hand-editing is the exact
      untrusted-input path the renderer exists to defend against.) The reason is
      **required** and validated exactly as `dismiss`/`defer` validate theirs —
      same single-line rule, same 500-char cap.
- [x] **AC-15** Given the operator tries to un-park something that is not
      parked, then the command refuses and names the status the entry actually
      has. This is judged on the **effective** status, not the stored one: an
      entry stored `snoozed` whose revisit date has passed is already open, so
      un-parking it is refused as "already open" rather than writing a
      pointless second event.

### Part 5 — the parked view is capped

- [x] **AC-16** Given more parked entries than the display cap, when either the
      terminal listing or `triage_inbox.md` renders them, then only the first
      N are shown followed by a line stating how many were elided — the same
      shape `triage_inbox.md` already uses for the open list. Both surfaces read
      the cap from one constant.

### Cross-cutting

- [x] **AC-17** Given the stored wire format gains a field, when a status event
      carrying a revisit date is validated against
      `shared/schemas/triage_item.schema.json`, then it validates. (The status
      event is `additionalProperties: false`, so this is not optional.)
- [x] **AC-19** Given the revisit date is a field on a generic status event,
      then its transition rules are explicit and enforced, not inferred:
      (a) a revisit date is accepted **only** on a `snoozed` event and refused on
      any other, so a malformed or hostile event cannot acquire park semantics;
      (b) every later status event replaces the resolved revisit date with its
      own — so un-park, dismiss and promote **clear** it, and a re-park replaces
      it; (c) an entry that is open because its park expired is distinguishable
      from one an operator un-parked: the first still carries its revisit date,
      the second carries none.
- [x] **AC-20** Given a stored revisit value that is damaged or hostile — a hand
      -edited file is an untrusted input, and AC-7 deliberately lets such a value
      reach the views — when it is displayed on **any** human surface (the
      deferred section of the terminal listing and of `triage_inbox.md` alike),
      then it goes through **one** display converter that emits either a
      canonical `YYYY-MM-DD` or a fixed placeholder, never the raw stored value.
      A stored value must not be able to forge a row, open a fence, or emit a
      terminal escape. The machine contract keeps the raw stored `revisitAt`
      **and** the computed `revisitDue` boolean, so a consumer never has to
      parse a date to learn whether the entry is back.
- [x] **AC-21** Given the accepted date form, then it is parsed **strictly**:
      exactly `YYYY-MM-DD`, a real calendar date, no surrounding whitespace, no
      timestamp, no partial form. "Now" is taken once, at the store boundary, as
      an aware UTC value and passed into the pure helpers, which never read a
      clock themselves.
- [x] **AC-22** Given more parked entries than the display cap, then which ones
      are shown is **deterministic and identical** on both human surfaces and in
      the machine contract's ordering. The order is **total**, so no two entries
      can tie: valid revisit dates first in ascending order (soonest return
      first), then entries whose date is missing or unreadable, then by severity,
      then by id. Without a total order, "the first N" is whatever the union
      reader happened to traverse, and an operator would see a different subset
      from run to run.
- [x] **AC-23** Given an entry that is already parked, when the operator parks it
      again with a different date, then it is accepted and the new date replaces
      the old one. `defer` therefore accepts an entry that is effectively open
      **or** effectively parked, and refuses only the two decisions that end an
      entry's life (`dismissed`, `promoted`) — naming which one it found. Without
      this, AC-9a describes a race that could not happen and a mistaken date
      could only be corrected by un-parking first.
- [x] **AC-24** Given the expiry is applied when the store is read, then reading
      is **pure**: no byte of `triage.jsonl` or of the outbox changes, and a
      re-read still finds the stored last event for that entry to be `snoozed`.
      The effective status lives only in the resolved view. (No `storedStatus`
      field is added to that view — AC-19(c) already distinguishes the two cases:
      an expired park carries its revisit date, an un-parked entry carries none.)
- [x] **AC-25** Given the deferred section renders an entry's stored **reason**
      as well as its date, then that reason goes through the same escaping the
      open rows already use on both surfaces — a hand-edited reason carrying
      markdown fences, newlines or terminal escapes cannot forge a row, escape a
      fence, or reach the terminal raw.
- [x] **AC-26** Given seven producer paths are widened to close parked findings,
      then **each** of them is covered — not one representative — so a missed
      read filter or a missed precondition in any single producer is a failing
      test rather than a producer that silently never self-closes.
- [x] **AC-27** Given AC-22's order names severity as a tie-break, then it uses
      the project's existing severity rank (`triage.SEVERITY_RANK`, critical
      first) with an unknown or missing severity sorting last — the same rule
      `aggregate_triage` already sorts the open list by. The whole key lives in
      **one** helper, so two independently-written renderers cannot disagree at
      the cap boundary.
- [x] **AC-28** Given one read of the store, then **one** UTC instant decides
      every expiry question in it — tracked lines and outbox lines, status
      resolution, and the `revisitDue` values returned. `read_all_items` captures
      it once and passes it down; the idempotent append captures it **inside its
      lock** and uses that same instant for its read, its suppression decision
      and its precondition. Otherwise one entry could be due and another not,
      inside a single operation, purely because the UTC day turned over between
      two lines of the same read.
- [x] **AC-18** Given the glossary and the module headers describe what each
      surface guarantees, then no statement claims a gap that this run closes,
      and none claims a guarantee this run does not deliver.

## Spec Impact

- **Classification:** `modify`
- **Affected FRs:** `FR-01.14`
- **What changes:** FR-01.14 already promises that a finding is "deliberately
  deferred until later" and that a finding which no longer appears "is closed
  automatically". It does not yet say that a deferral is time-bounded and
  returns by itself, that a deferred entry closes itself the same way an open
  one does, that a deferral is reversible, or that a deferred entry stays
  visible. Those four promises are added to `spec.md` as new (E) criteria.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `triage.mark_status` (status event, now with `revisitAt`) | `triage.read_all_items` | JSONL line, `.shipwright/triage.jsonl` + outbox |
| `triage.read_all_items` (resolved view, now expiry-aware) | `triage_cli`, `aggregate_triage`, 7 auto-resolvers, compliance RTM/SBOM | in-process dicts |
| `triage_cli.py list --json` | Command Center parity fixture (`shipwright-webui`) | JSON, **versioned** |
| `triage.mark_status` | `shared/schemas/triage_item.schema.json` | JSON Schema |

## Out of Scope (stated, not silently dropped)

- **The Command Center consumer change.** Different repository, different PR.
  Filed as a triage card (AC-13).
- **`migrate_legacy_items`** in `github_triage/resolve.py`. It is a one-shot
  schema migration, not a "the finding disappeared" resolver; its docstring
  records that skipping decided items is deliberate (review finding #12). The
  self-close decision is about findings going away, so this is left alone.
  It **shares** `_dismiss_if_open` with the two resolvers that ARE widened, so
  the helper takes the expected-status set as a parameter and this caller keeps
  passing `("triage",)`. Widening it by accident is the specific mistake this
  note exists to prevent.
- **`accepted_risks_converge.py`.** Verified at code: it dismisses a triage item
  because an operator accepted the matching security risk — an operator decision
  propagating, not a finding disappearing. Decision #2 is about findings going
  away, so this stays `triage`-only. Widening it would mean deciding that
  accepting a risk also overrides a park, and no such decision is on record.
- **Requiring a revisit date at `mark_status`.** The date is required at the
  decision layer (`defer()` and the CLI). The raw store API keeps accepting a
  `snoozed` event without one, because the Command Center writes exactly that
  today (its route permits a reason-less park) and every park written before
  this change has none. Such an entry resolves as **parked, not due** (AC-7) —
  it stays visible and reversible instead of silently re-opening.
- **`triage_promote.promote` / `.dismiss`.** They stay `triage`-only. A parked
  entry that is due reads as open and is therefore promotable/dismissable
  again; a parked entry that is not due is a decision already taken.

## Confidence Calibration

- **Boundaries touched:** the four in the Affected Boundaries table — the JSONL
  status event (producer `mark_status` / consumer `read_all_items`), the
  resolved view (producer `read_all_items` / ~10 in-process consumers), the
  `list --json` output contract (cross-repo consumer), and the JSON Schema.

- **Empirical probes run** — each one a thing I did not know until I ran it:
  - *Diff-driven risk detector, before writing any code.* Ran
    `risk_detectors.is_cross_component_change` over the planned file list.
    **Finding:** `cross_component` fires — `shared/scripts/hooks/check_drift.py`
    matches `(^|/)hooks/.+\.py$`. So integration coverage was mandatory and
    non-dodgeable at every complexity, not something to decide later.
  - *Schema conditional, executed against a real validator* (6 cases).
    **Finding:** the `if`/`then` behaves as intended in all six, including the
    one an external reviewer raised — `reason` stays unconstrained on a `triage`
    event, so `unpark` can record why it reversed a park. Had I only read the
    JSON I would have assumed the `if` scoped to `revisitAt`; it does, but that
    was an assumption until it was executed.
  - *Mutation probe of the strengthened registry meta-test.* Replaced one
    `allowed=DEFERRABLE_STATUSES` with an unvetted name and expected red.
    **Finding: it stayed GREEN.** The pin unioned the statuses across callers,
    so a single well-behaved caller masked a bad one. Changed to "every supplier
    must resolve"; re-probed, now red on the mutation and green on the real code.
    A pin that cannot fail is not a pin.
  - *Mutation probe of the `test_evidence` regression test.* Reverted the read
    filter to `!= "triage"`. **Finding:** exactly `assert 0 == 1` — the new test
    reproduces the shipped defect rather than merely covering the line.
  - *Anti-ratchet, measured against the staged index rather than estimated.*
    **Finding:** eight entries move, not the two I had planned for; six are the
    +1 cost of one import. My pre-build estimate for `triage.py` was ~+20 and
    the real figure was +80 (trimmed to +66) — almost all docstring.
  - *Consumer audit by reading, not asserting.* Walked every
    `status == "triage"` site. **Finding:** exactly one deliberate
    stored-status reader (`triage_gc._resolve_tracked_only`), unaffected because
    it never drops `triage` or `snoozed`.
  - *Cross-repo blast radius, checked in the other repository.* **Finding:** the
    Command Center does not shell out to this CLI at runtime — it has its own
    TypeScript reader pinned by a hand-regenerated fixture. Nothing breaks live;
    the parity gate breaks on the next regeneration. That changed the shape of
    AC-13 from "coordinate a release" to "file a card and say so".

- **Test Completeness Ledger:** every behaviour this diff introduces or changes,
  each `tested` with its evidence. **Zero untested-testable.** One row is
  `untestable`; nothing is "could-test-but-didn't".

  | # | Behaviour | AC | Status | Evidence |
  |---|---|---|---|---|
  | 1 | `defer` refuses without a revisit date | AC-1 | tested | `test_triage_defer_cli.py::test_defer_without_a_revisit_date_is_refused`; `test_triage_defer.py` (`no-revisit-date`) |
  | 2 | a not-yet-due park reads parked | AC-2 | tested | `test_triage_defer_store.py::test_a_park_dated_in_the_future_still_reads_as_parked` |
  | 3 | a due park reads open, and nothing is written | AC-3 | tested | `test_triage_defer_store.py::test_a_park_whose_day_has_come_reads_as_open_with_no_second_event` |
  | 4 | due from 00:00 UTC on the named day | AC-3a | tested | `test_triage_defer_lifecycle.py` — day before / day itself / day after |
  | 5 | a not-due park suppresses re-import, beating the window | AC-4 | tested | `test_triage_defer_reimport.py::test_a_park_that_is_not_due_suppresses_the_re_import`, `::test_the_park_beats_the_recency_window` |
  | 6 | a due park suppresses via the pre-existing open-match rule | AC-5 | tested | `test_triage_defer_reimport.py::test_an_expired_park_also_suppresses_because_it_is_open_again` |
  | 7 | a malformed date is refused at store and CLI | AC-6, AC-21 | tested | `test_triage_defer_store.py` (6 forms), `test_triage_defer_cli.py` (4), `test_triage_defer_lifecycle.py` (13) |
  | 8 | an unreadable or absent date is parked-but-not-due | AC-7 | tested | `test_triage_defer_store.py::test_a_hand_edited_unreadable_date_stays_parked`, `::test_a_park_written_without_a_date_stays_parked_forever` |
  | 9 | each of 7 producer paths closes a PARKED entry | AC-8, AC-26 | tested | `test_triage_defer_producer_coverage.py` (4 paths) + the compliance-root sibling (3). Mutation-probed. |
  | 10 | the deliberate non-widening holds | out-of-scope | tested | `test_triage_defer_producer_coverage.py::test_the_legacy_migration_still_leaves_a_parked_entry_alone` |
  | 11 | a cooperating Python dismiss/promote in the race window is protected | AC-9 | tested | `test_triage_precondition_callers.py::test_phase_quality_dismiss_keeps_an_item_a_person_dismissed`; `test_triage_defer_composition_integration.py::test_a_dismissal_recorded_by_a_person_still_survives_the_sweep` |
  | 12 | a park in the race window does NOT stop the close | AC-9a | tested | `test_triage_precondition_callers.py::test_phase_quality_still_closes_an_item_a_person_parked_mid_flight` |
  | 13 | one declared status set, and every flip site resolves to a real one | AC-10 | tested | `test_triage_precondition_registry.py` (strengthened; mutation-probed) |
  | 14 | the one stored-status reader is unaffected | AC-10a | untestable — `covered-by-existing-test` | `triage_gc` never drops `triage`/`snoozed`; pinned by the pre-existing `shared/tests/test_triage_gc.py`. This diff changes nothing there, so a new test would assert someone else's behaviour. |
  | 15 | `list --json` carries a version and a deferred section | AC-11 | tested | `test_triage_defer.py::test_list_json_now_carries_the_deferred_entry_in_its_own_section`; `test_triage_cli_json.py` |
  | 16 | the machine contract is never capped | AC-11a | tested | `test_triage_defer_cli.py::test_the_machine_contract_is_never_capped` |
  | 17 | `triage_inbox.md` shows parked entries, not a count | AC-12 | tested | `test_triage_defer_cli.py::test_the_rendered_document_no_longer_shows_a_park_as_a_bare_count`, `::test_a_park_with_no_open_work_left_still_renders_its_section` |
  | 18 | `unpark` re-opens, clears the date, records the reason | AC-14 | tested | `test_triage_defer_cli.py::test_unpark_puts_a_parked_entry_back_and_clears_its_date`, `::test_unpark_requires_a_reason` |
  | 19 | `unpark` refuses anything not effectively parked | AC-15 | tested | `test_triage_defer_cli.py` (3 statuses + the expired-park case) |
  | 20 | both human surfaces cap, elide, and show the SAME entries | AC-16, AC-22 | tested | `test_triage_defer_cli.py` at exactly N and N+1, plus `::test_the_two_human_surfaces_show_the_SAME_entries` |
  | 21 | the wire accepts `revisitAt` only on a park | AC-17, AC-19a | tested | `test_triage_schema.py` (park with/without, 3 rejected statuses, 5 malformed forms) + `test_triage_defer_store.py` store-side refusals |
  | 22 | the schema rule does not constrain `reason` | AC-19a | tested | `test_triage_schema.py::test_the_revisit_rule_does_not_constrain_the_reason` |
  | 23 | a later event clears the date; expired ≠ un-parked | AC-19b/c | tested | `test_triage_defer_store.py::test_un_parking_clears_the_revisit_date`, `::test_an_expired_park_and_an_un_parked_entry_are_distinguishable` |
  | 24 | one display converter; a hostile date renders a placeholder | AC-20 | tested | `test_triage_defer_cli.py::test_an_unreadable_stored_date_renders_a_placeholder_not_its_bytes` |
  | 25 | a hostile stored reason cannot forge a row or open a fence | AC-25 | tested | `test_triage_defer_cli.py::test_a_hostile_stored_reason_cannot_forge_a_row_or_open_a_fence` |
  | 26 | the deferred order is total, unknown severity last | AC-22, AC-27 | tested | `test_triage_defer_lifecycle.py` (date / missing-date / severity / unknown-severity / id) |
  | 27 | an already-parked entry can be re-parked with a new date | AC-23 | tested | `test_triage_defer.py::test_defer_accepts_an_already_parked_item_and_replaces_the_date` |
  | 28 | reading is pure — no byte changes, stored event still `snoozed` | AC-24 | tested | `test_triage_defer_store.py::test_reading_an_expired_park_leaves_the_stored_event_saying_parked` |
  | 29 | one UTC instant decides a whole read, across both files | AC-28 | tested | `test_triage_defer_reimport.py::test_one_utc_instant_decides_a_whole_read_across_both_files` |
  | 30 | the documents match the commands they teach | AC-18 | tested | `test_triage_docs_consistency.py` (extended: `--revisit`, `unpark`, no stale card pointer) |
  | 31 | **integration** — producer, store, resolver and all three renderers compose across a park's whole life | `cross_component` | tested | `test_triage_defer_composition_integration.py` (6 scenarios) |

  **Not a behaviour, recorded so it does not look hidden:** AC-13 (file the
  Command Center card) is a delivery obligation, not code this diff executes.
  Verified in the owning `shipwright-webui` store — `trg-f2214310` — rather
  than inferred from this monorepo's store.

- **Confidence-pattern check:**
  - *Asymptote (depth).* The last three probes each still found something — the
    registry pin's union hole, the `test_evidence` read filter, the eight-not-two
    ratchet count. Depth had NOT flattened when the Stage-1 gate ran, and the
    gate found a live defect, which is the honest reading: my own probes were
    still productive, so "I am confident" would have been unfalsifiable noise.
    After the fixes, the two mutation probes are the depth evidence — each turns
    a specific reversion red.
  - *Coverage (breadth).* 7/7 producer paths, 3/3 surfaces, both stores
    (tracked and outbox), both sides of the UTC-day boundary, and all four
    statuses against the transition rules. The breadth gap the gate exposed —
    one representative producer instead of seven — is closed and was the whole
    reason the defect survived.
  - *Integration composition.* `cross_component` is diff-confirmed, and row 31
    is a real-scenario test driving the actual producer, the actual store and
    the actual three renderers, not stubs.

## Verification

- **Surface:** cli
- **Runner command:** `uv run --python 3.11 --with pytest --with pytest-mock pytest shared/tests/test_triage_defer_cli.py shared/tests/test_triage_defer_composition_integration.py -q -p no:cacheprovider --junit-xml C:\tmp\triage-defer-surface.xml`
- **Evidence path:**
  `.shipwright/runs/iterate-2026-08-01-triage-defer-lifecycle/surface_verification.json`
