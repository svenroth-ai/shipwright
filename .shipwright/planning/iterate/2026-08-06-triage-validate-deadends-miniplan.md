# Mini-Plan — iterate-2026-08-06-triage-validate-deadends

## Goal

Remove three absorbing states from the triage delivery path so that no single
un-placeable line can stop the sweep permanently, without ever destroying an
operator decision.

## Chosen approach — proportional dispositions

`decide()` gains a fourth disposition, `hold`, and the classifier gains a third
error class. Together they make `block` mean only "corruption I must not paper
over".

### Step 1 — `shared/scripts/lib/triage_validate.py`

1. Parse with `lib.jsonl_records.split_records` instead of `json.loads`
   per physical line, mirroring `churn_merge.validate_events_text`.
   - Flatten to `(line_no, record)` pairs so a glued `header + append` line is
     handled: the **first record overall** is the header check; every later
     record on that same line is an ordinary event (today the whole line is
     skipped after the header branch).
   - An unrecoverable `remainder` remains an error and still sets
     `has_non_orphan_error`; its message gains the remedy:
     `run shared/scripts/tools/triage_repair.py --project-root <root>`.
   - Consequence to accept deliberately: a bare-scalar line (`123`) was
     previously tolerated in silence and is now a fragment → block. That matches
     `split_records`' documented contract and the event-log twin, and the block
     is remediable by the tool now named in the message.
2. Add `TriageValidation.unidentified_status: bool` — set when a `status` has no
   append anywhere **and** its id is missing or not a `str`. Give that class its
   own message ("no usable id — no reader can apply it"); the misleading "the
   merge dropped it" wording is wrong for it. `has_non_orphan_error` stays
   `False` so the caller can act on it.

### Step 2 — `shared/scripts/lib/sweep_quarantine.py`

3. `QuarantineDecision` gains `held: list[str]`, and `trimmed_outbox` is
   **renamed `materialized_outbox`** (external review r1 openai #2: one value was
   serving as both "what went onto the branch" and, by implication, "what the
   persisted outbox becomes" — the ambiguity is exactly how a held line gets
   deleted). The three lists are disjoint and exhaustive, pinned in the
   docstring and by a test:

   > `materialized_outbox + candidates + held == outbox_lines` as a **multiset,
   > in order**. `materialized_outbox` is a branch-materialization input and
   > never drives the outbox rewrite.

   **The persisted-outbox lifecycle, stated exactly** (r2 openai #1 — the r1
   wording "candidates is the ONLY list ever removed" was wrong, because it
   ignored the pre-existing GC). Two independent removal channels act on the
   outbox, and `held` is subject to neither:

   | Channel | Removes | Condition |
   |---|---|---|
   | Quarantine (this change) | `candidates` | dispositioned un-deliverable this sweep |
   | GC (pre-existing, unchanged) | ordinary lines | `is_delivered(...)` — present in **origin**'s tracked log, not merely committed on the branch |
   | — | `held` | never removed **because it is held** |

   The last row is stated that way deliberately (r3 openai #2). "Never removed"
   is too strong: origin can move between `decide()` and the rewrite, and the
   pre-existing GC may then observe the held line as delivered and drop it. That
   is *correct* — it is no longer held in any meaningful sense — so the invariant
   is about the reason, not the bytes, and no test asserts byte-for-byte
   retention across a moving origin.

   So an ordinary delivered line *is* eventually removed — by the GC, one sweep
   later, once origin confirms it. That deferral is the existing "never
   reset-after-read" invariant and this change does not touch it.

4. `decide()`:
   - `has_non_orphan_error` → `block` **first, before any side effect**. This
     covers the mixed line (valid records then an unrecoverable remainder,
     openai #4): the remainder sets the flag, so the sweep blocks before
     adoption, before `append_quarantine`, and before any rewrite.
   - Partition `outbox_lines` **by index in one pass** (r1 openai #5 — a
     set-difference loses multiplicity when two identical status records are
     buffered): each line goes to exactly one of `candidates` (orphan or
     unidentified status), `held` (protected status), or `materialized_outbox`.
     No sets, order and duplicate count preserved exactly.
   - If `candidates` and `held` are **both empty** while the verdict reported a
     defect → `block`: every defect lives in the worktree-tracked log, which the
     sweep cannot rewrite. (r2 deepseek #3 — stated positively; the r1 double
     negative was ambiguous.)
   - Re-materialize from `materialized_outbox` and re-validate. Residual error
     → `block`, carrying the `protected_status_unplaceable` message.
   - Otherwise `action = "quarantine"` if there are candidates else `"hold"`,
     with **both** lists populated so the two can co-occur.
5. **The residual re-validation is the load-bearing safety net, not the
   partition** (r2 openai #3). A defect that exists in BOTH the tracked log and
   the outbox — byte-identical lines in both sources — has its outbox copy
   dispositioned, but the tracked copy survives the trim, so the
   re-materialized text still fails and the sweep blocks. Provenance is
   therefore enforced by re-validation rather than tracked in the classifier.
   Pinned by behavior 23.

### Step 2a — glued lines that need a per-record disposition (openai #1)

Classification is record-granular after boundary recovery, but the outbox is
persisted, quarantined and GC'd **by physical line**. So a *glued* outbox line
holding both a deliverable record and a record needing hold/quarantine cannot be
dispositioned at line granularity: removing the line strands the deliverable
record, keeping it strands the sweep.

Re-serializing such a line inside the sweep is rejected — `triage_repair.py`'s
docstring documents why (it reflows a CRLF log to LF, producing a whole-file diff
on a `merge=union` artifact, and it breaks the byte-identity dedup in
`dedup_triage_lines`, which duplicates `status` events into the tracked log).

So this combination **blocks**, and the block is escapable: the message names
`triage_repair.py`, whose entire purpose is to split concatenated lines on disk,
one record per line, quarantining anything undecodable first. After the repair
the records are line-granular and the ordinary dispositions apply. This is a
*reachable* remedy, not a new dead end — which is the whole test this card applies.

**Mechanics, made deterministic** (r2 openai #2 — "when the disposition sets
cannot resolve the verdict" was not implementable). The partition loop uses
**one parser**, `split_records`, the same one the classifier uses — there is no
second predicate with divergent rules:

```
for ln in outbox_lines:
    recs, remainder = split_records(ln.strip())
    if remainder or len(recs) != 1:
        multi_record = True          # cannot disposition at line granularity
        materialized_outbox.append(ln)
        continue
    ... disposition recs[0] by event/id ...
```

A multi-record (or fragment-bearing) line therefore always lands in
`materialized_outbox`, so any defect it carries is caught by the residual
re-validation and blocks. `multi_record` is what turns that block into an
*actionable* one: it appends the `triage_repair.py` hint. Deterministic, and
AC11 is a property of the code path rather than of an emergent interaction.

Three points of precision (r3 openai #4, #5; deepseek #1):

- **`multi_record` is advisory metadata and never itself blocks.** A glued line
  whose records are all fine produces no validator errors at all, so `decide`
  returns `clean` before the partition ever runs. When there *are* errors
  elsewhere, such a line is materialized and remains deliverable. `multi_record`
  only selects whether the hint is appended to a block that some other defect
  already caused. Pinned by behavior 26.
- **Stripping is for parsing only, never for persistence.** The partition parses
  `ln.strip()` — matching the classifier and `read_jsonl_records`, both of which
  strip before `split_records` — but every list holds the **original `ln`**. No
  disposition path ever writes the stripped form, so dedup byte-identity and the
  file's EOL style are untouched.
- **The hint is computed before the early block too.** `multi_record` is
  determined in the same pass, so the "candidates and held both empty" block —
  which is where a glued outbox line lands — carries the repair hint rather than
  losing it to an earlier return.

Note the plain finding-15 case is unaffected: a glued line whose records are all
fine produces no errors at all, so it never reaches disposition and is delivered
verbatim, exactly as glued lines already in the tracked log are.

### Step 3 — `shared/scripts/lib/sweep_outbox.py` + `sweep_result.py`

6. Drive the mechanics off the **lists**, not the enum:
   `if decision.candidates: append_quarantine(...)`. **Never reassign
   `outbox_lines`** (r3 openai #1): in this module that name reads as "the outbox
   content", and assigning branch-materialization content into it is precisely
   how a held line gets deleted by a later reader of the variable. Bind a
   separate `branch_outbox_lines = decision.materialized_outbox` used for
   nothing but the `swept` count. The persisted rewrite already derives from its
   own fresh re-read of the outbox file (`current_lines`), which stays untouched.
7. The quarantine removal set on the outbox rewrite is **candidates only** —
   explicitly, not by relying on GC's "keep what is not origin-delivered". A held
   line must survive it. Pinned by a unit test (`held ∉ quarantined_text`) and at
   integration level by AC5.
7a. **Write ordering is already crash-safe and stays unchanged** (r2 openai #5,
   deepseek #2): decide → drift adoption → `append_quarantine` → branch write +
   commit → outbox rewrite **last**, via `durable_atomic_write`. A crash before
   the rewrite leaves every line still in the outbox, so nothing is lost; the
   replay re-quarantines, which duplicates a record in the operator-review buffer
   and loses nothing. That duplicate-on-replay is pre-existing behavior and is
   deliberately not changed here — widening scope to dedupe the quarantine append
   belongs to the buffer's own card, not to this one. A comment records the
   ordering rationale at the call site.
8. `SweepResult.held: int` + a `sweep_warnings` note (counts only, on an
   otherwise-successful run — same rule that made quarantines visible).
9. Operator-facing text stays **static** (openai #6): no log content, no record
   ids, no paths from the log are interpolated into the repair command.

### Step 4 — tests

- Extend `shared/tests/test_triage_validate.py` (behaviors 1-7, 16, 17).
- New `shared/tests/test_sweep_quarantine_dispositions.py` (behaviors 8-13).
- New `shared/tests/test_sweep_outbox_dispositions_integration.py` (behaviors
  14-15, real git repo via the existing `git_origin_repo` fixture + `_sweep_helpers`).
- **Update the TWO existing regression pins** that assert the disposition AC4
  deliberately reverses. Both keep their intent — the dismiss is never quarantined
  and never dropped from the outbox — and both gain an assertion for the new
  `held` channel. Test-Update-Klausel.
  1. `test_sweep_drift.py::test_status_whose_append_is_only_in_main_tracked_is_not_an_orphan`
     — unit level: `action == "block"` → `action == "hold"` + `held == [dismiss]`.
  2. `test_sweep_drift_guards.py::test_an_unplaceable_known_append_blocks_instead_of_eating_the_dismiss`
     — sweep level, renamed `..._holds_instead_of_...`: `status == "invalid"` →
     `held == 1`, plus a new assertion that the unplaceable status did NOT reach the
     branch. (Missed in the first draft of this plan; added after the Stage-1 spec
     review flagged the file as undeclared.)

## Files

| File | Change |
|---|---|
| `shared/scripts/lib/triage_validate.py` | boundary recovery + `unidentified_status` |
| `shared/scripts/lib/sweep_quarantine.py` | `held` disposition + predicates |
| `shared/scripts/lib/sweep_outbox.py` | drive off lists; thread `held` |
| `shared/scripts/lib/sweep_result.py` | `held` count + operator note |
| `shared/tests/test_triage_validate.py` | extend |
| `shared/tests/test_sweep_quarantine_dispositions.py` | new — the four dispositions |
| `shared/tests/test_triage_id_identity.py` | new — AC13, the str-only identity rule (split out so both stay under 300 LOC) |
| `shared/tests/test_sweep_outbox_dispositions_integration.py` | new |
| `shared/tests/test_sweep_drift.py` | update the unit-level regression pin |
| `shared/tests/test_sweep_drift_guards.py` | update the sweep-level regression pin |

`shared/scripts/lib/churn_merge.py` is deliberately **not** touched — it
re-exports names, and a new dataclass field needs no re-export change. That also
keeps `cross_component` off this diff.

## Risks

- **R1 — a held line is silently lost.** Mitigated by the disjoint-list
  invariant (Step 2.3), the candidates-only rewrite (Step 3.7) and AC5 at
  integration level (real sweep, real GC rewrite, second sweep places it).
- **R2 — quarantining an unidentified status destroys an operator decision.**
  Falsified by probe P4: `read_all_items` skips such a status, so it is inert.
- **R3 — boundary recovery lets real corruption through.** The unrecoverable
  remainder path is unchanged and still blocks; only *fully* recoverable
  concatenations are accepted, exactly as the event-log twin already does.
- **R4 — the stricter bare-scalar handling newly blocks a log that used to
  pass.** Accepted, and remediable via the now-named `triage_repair.py`.
- **R5 — a glued outbox line needing a per-record disposition.** Blocks, with
  the repair hint (Step 2a). No partial side effect, because the block is
  decided before any mutation.
- **R6 — duplicate identical status records lose multiplicity during
  partition.** Removed by construction: index partition, no sets.
- **R7 — `resolve_churn_conflicts` sees the stricter parser** (r2 deepseek #1;
  arithmetic corrected after AC13 landed — Stage-1 re-review carry-forward A).
  Audited: `_reconcile_triage` returns the error list as `triage_invalid`. Net
  effect on that path is **two fewer false rejections and one more true one**:
  a concatenated line in the tracked log currently aborts the churn merge and will
  now recover (the identical fix iterate-2026-07-20 applied to the events twin, for
  exactly that false-abort), and two appends sharing a non-`str` id were reported as
  a duplicate the dedup can never collapse — a log that could never merge again —
  and now validate; while a bare-scalar line, which no reader can use, now reports
  instead of passing silently. The two logs end up consistent. Pinned by
  behaviors 24 and 29.
- **R9 — AC13 removes tolerance for one previously-clean shape.** An
  `append` + `status` pair sharing a non-`str` id validated clean and now has its
  status quarantined. Accepted: the pair is already inert to every reader (pass 1
  creates no item, so pass 2 overlays nothing), so nothing observable is lost —
  the same P4 reasoning that licenses AC6. Recorded rather than discovered.
- **R8 — `hold` self-healing depends on a refreshed branch base** (r2 openai #4).
  True, and bounded: the sweep runs at worktree setup, and
  `setup_iterate_worktree.py` branches off a **freshly fetched**
  `origin/<default>` (a fetch failure is exit 3, a hard stop). So a held line is
  retried once per iterate, not continuously — that is the honest claim, and the
  spec says so rather than implying faster convergence.

## Alternative (rejected)

Keep `block` for the protected-status case and improve only the message /
add a "deliver main" flow. Rejected — it strands every unrelated append for the
duration and leaves the whole backlog in a gitignored buffer. Holding one line
delivers the other N with no operator action.
