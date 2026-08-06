# Iterate 2026-08-05 — IT-1 audit remainder, scope A (findings 14 / 26 / 27 / 13)

**Run-ID:** `iterate-2026-08-05-it1-audit-remainder`
**Intent:** CHANGE · **Complexity:** medium · **Card:** `trg-79102ee3` (P2.19)
**Evidence:** `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`

## Why this run exists

`trg-79102ee3` carried audit findings **14 and 20–29** with the note *"they need a
scoping decision before they are buildable"*. This run made that decision, on
re-measured evidence rather than on the audit's reported state, and builds only
the part that measurement supports.

### What re-measurement changed

Three of the audit's own statements no longer hold, and one unverified claim now does:

| Audit said | Measured 2026-08-05 |
|---|---|
| F26 is a two-sided partial overlay (`triage.py` **and** `triage_gc.py`) | The `triage.py` half is **already fixed** — it `continue`s on an out-of-enum status. Only `triage_gc.py` remains, so the finding is now a **divergence between twins**, which is worse than the symmetric bug it was filed as. |
| F29 includes `_CI_TRUTHY` / `_ci_active` in **three** copies | **Already resolved** — all four call sites delegate to the shared leaf `lib.ci_env` and say so in their docstrings. Real remainder is `_op_in_progress` (31+34) + `_has_staged_changes` (7+10) ≈ 38 LOC. |
| F14's live-evidence claim is *"unverified by me; check it first"* | **Verified.** `.shipwright/triage.jsonl` line 285 (`trg-60ef91fb`) carries `ts` ending `+00:00`. `triage._now_z()` always `.replace("+00:00", "Z")`, so it cannot emit that — the line was written by a **foreign producer** (the WebUI writer the audit names as non-cooperating). Same-id, non-identical appends are real, not hypothetical. |
| F28 implies live loss | **No loss observed.** 33 status flips sit in the outbox; all 33 were correctly swept onto this run's branch, and the GC anchors on `origin`, so an abandoned branch loses nothing. F28 is a **reporting** blind spot — the board cannot tell "delivered" from "buffered" — not evidence of loss. It was therefore *not* built here. |

### The split had a hole

S1 delivered findings 1–4, 6–8 (and 11 incidentally); S2 delivered 19. The card
covered 14 and 20–29. **Findings 5, 9, 10, 12, 13, 15, 16, 17, 18 were never
assigned to any successor card.** Among them F15, whose failure mode is that one
concatenated line permanently blocks *all* delivery, and F16/F17/F18, the terminal
states F28 exists to make visible.

All 20 findings are now accounted for: **4 built here**, **16 filed** as five
iterate-sized cards — `P2.19a` `trg-2df5ac3d` · `P2.19b` `trg-b854805c` ·
`P2.19c` `trg-8652bf24` · `P2.19d` `trg-dc013d82` · `P2.19e` `trg-de99fdcb`.

## Scope

**In:** findings **14**, **27** (one mechanism), **26**, **13**.
**Out, by operator decision 2026-08-05:** 20, 21, 22, 23, 24, 25, 28, 29 — filed above.

Deliberately excluded consequence: not taking F25 keeps `churn_merge.py` out of the
diff, so this run does **not** raise `cross_component` and does not owe integration
coverage. That is a scoping consequence, not an evasion — F25 travels with `P2.19a`,
which will owe it.

## Spec Impact: NONE (affected FR: FR-01.14 — Triage Inbox)

**Justification.** FR-01.14 already states the behaviour this run restores; no
criterion changes, is added, or is removed. Two existing criteria are the ones the
code fails today:

- *"Given several producers record findings at the same moment … none can swallow,
  truncate or hide another: every entry written is one that can afterwards be read
  back."* — F14 destroys a written entry.
- *"Given the Triage Inbox is compacted … only findings a background check closed by
  itself may go; every decision a person made stays as the record of what was decided
  and why."* — F26 lets a damaged event rewrite `statusBy`/`statusReason`, which is
  exactly what the compaction keys its **delete** decision on, so a person's decision
  can be reclassified as machine churn and removed.

F27 (unbounded buffer growth) is not covered by an explicit criterion; it rides along
because the same mechanism fixes it.

## Acceptance Criteria

- **AC-1 (F14)** — An outbox `append` whose `id` is present in `origin` but whose
  *content* differs is **not** dropped by the GC.
- **AC-2 (F27)** — An outbox `status` line that `origin` carries in a different but
  semantically equal serialization **is** dropped by the GC.
- **AC-3 (F14+F27, regression guard)** — A benign re-serialization (different key
  order / whitespace) of a genuinely delivered line is still recognised as delivered.
  This is FIX B's original goal and must survive the change.
- **AC-4 (F26)** — `triage_gc`'s resolver ignores an out-of-enum `status` event
  **entirely**: `status`, `statusBy` and `statusReason` all keep their prior values,
  matching `triage.read_all_items`.
- **AC-5 (F26, drift protection)** — A test pins **both** resolvers to the same
  behaviour for a damaged status event, so the twins cannot diverge again silently.
- **AC-6 (F13)** — The comment names a predicate that exists and records that the
  guard is advisory (evaluated outside the lock).
- **AC-7 (D1) — REVISED after the Stage-3 doubt review; the earlier wording is
  superseded.** An outbox append that a LATER same-id append supersedes is
  **retained**, not drained, and the retention is documented in `sweep_gc`'s module
  docstring and carried by card `trg-ed774f03` (P2.19g). No drainage mechanism ships.

  AC-7 originally required drainage, and a hatch for it was built and reviewed three
  times before being deleted. The reason is that the trade is inverted: retention is
  the FAIL-SAFE direction (the old id-only rule dropped these lines, so retaining
  them is strictly safer than today's `main`), while drainage was the only path in
  this change able to delete the LAST copy of a record — `dedup_triage_lines` having
  kept that line off the branch by definition. Its correctness was an agreement
  between two modules that no test could hold, two of three attempts leaked in the
  DROP direction, and the benefit is measured **zero**: the real 1457-line log
  contains no superseded appends at all. Both external reviewers correctly flagged
  the spec/implementation gap this left; the gap was the stale criterion, not the
  code.
- **AC-8 (D3)** — No float literal is canonicalizable, so no two float-bearing
  lines can cross-match. Overflow, underflow, rounding and the non-standard
  `NaN`/`Infinity` tokens are all covered; integers are unaffected.

## Round 2 — what the review cascade changed (2026-08-05)

The cascade found defects in this run's own fix, not only in the audited code. All
are recorded because the spec's original "direction of risk is safe" claim was
wrong as written.

| Stage | Outcome |
|---|---|
| **1 spec-reviewer** | **REJECT** — a compaction assertion read `plan.get("drop", [])`, a key `plan_gc` does not return, so it could never fail. Fixed to `plan["drop_ids"]` + a `plan["total"] == 1` vacuity guard, and proven discriminating by reverting the fix (pre-fix `drop_ids == {'trg-human1'}`). Re-review → **PASS**. |
| **2 code-reviewer** | 6 findings, all accepted. Non-finite floats cross-matched in the DROP direction; the "totality" test never reached the encoder (its input was a list); `delivered_membership`'s docstring was stale; `_reserialize`/`_append` were duplicated across two test modules; the AC-5 drift claim was too broad. |
| **3 doubt-reviewer** | 7 doubts. **Three were real defects in the fix** (below); two were test-validity; one was documentation drift; one attacked F26 and could not break it. |

**D1 — the fix for F27 re-created F27.** Two same-id appends in the buffer: dedup
keeps only the last at materialize, so the earlier one never reaches a branch and
therefore never origin — and under pure canonical membership its canonical form is
never in origin either, so it would sit in the gitignored outbox forever. The old
id-only rule drained it. Verified by direct probe. Closed by AC-7.

**D3 — the numeric closure was half.** `allow_nan=False` covered only the overflow
tail; `1e-400` and `0.0` both parse to `0.0` and still cross-matched. Closed by
AC-8 (reject the float type outright), which is total where the previous fix was a
sample.

**D2 — deliberately NOT fixed here → `trg-94d3cb73` (P2.19f).** Origin is decoded
with `errors="replace"` (`git_base.run_git`), the outbox with
`errors="surrogateescape"` (`sweep_text.read_text_verbatim`), so a line carrying a
non-UTF-8 byte can never match and stays buffered. Direction is retention, not
loss. Deferred by operator decision because both remedies are disproportionate:
changing `run_git` touches its 133 call sites, and bypassing `run_git_soft` locally
would discard the `TimeoutExpired` handling that audit findings 1 and 7 installed
for this exact path.

Also corrected: the F14 severity claim. The refreshed line **is** committed to the
branch before the GC drops it, so loss required that branch to never merge — real,
but weaker than "the content exists nowhere". The spec, the module docstring and
the end-to-end test now say so.

## Design

### F14 + F27 — one mechanism: canonical-form membership

Today `is_delivered` asks two different questions: an `append` is delivered **iff its
id is in origin** (content ignored → F14), and everything else **iff its raw text is in
origin** (any re-serialization is unmatchable forever → F27).

Replace both with one rule:

- a **parseable** line is delivered iff its *canonical form* is in origin's set of
  canonical forms — `json.dumps(obj, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)`;
- an **unparseable** line keeps raw-text membership (it has no canonical form, and a
  producer cannot re-serialize what it never parsed).

This satisfies all three ACs at once. Canonicalization absorbs key order and
whitespace, so FIX B's stated goal is preserved (AC-3); content differences now
survive the GC (AC-1); and status lines become GC-able across re-serialization (AC-2).

**Direction of risk is safe.** For appends the rule gets *stricter* — strictly fewer
lines dropped, and keeping a line is always the fail-safe direction. For status lines
it gets *looser*, but only on exact canonical equality, i.e. only when origin provably
carries the same record.

### F26 — mirror the already-fixed twin

Add the guard `triage.py` already has: skip the event entirely when `newStatus` is not
in `triage.STATUSES`, rather than declining to apply `status` while still overwriting
`statusBy` and `statusReason`. Plus AC-5's drift test, so the two resolvers are pinned
to each other instead of to one implementation.

### F13 — comment correction

`_unrelated_staged` does not exist; the predicate is `_has_staged_changes`. Also record
that it is evaluated *outside* the lock, so it is advisory rather than a guarantee.

## Alternative considered — and why not

**Make GC require id *and* exact raw-text match for appends.** Simpler, and it closes
F14. Rejected: it re-opens exactly what FIX B was built to fix — any benign
re-serialization would then never be GC-able, converting F14 into a worse instance of
F27 and making the gitignored buffer grow without bound. Canonicalization is the only
form that closes F14 *without* trading it for F27.

**Extract a shared pass-2 overlay for F26** rather than mirroring the guard. Rejected
for this run by operator decision: refactors stay out of data-loss fixes so the review
diff reads as behaviour change, not movement. AC-5's drift test buys the safety that
extraction would have, at no reviewability cost.

## Affected Boundaries

- `shared/scripts/lib/sweep_gc.py` — GC membership rule (F14, F27)
- `shared/scripts/tools/triage_gc.py` — tracked-store resolver (F26)
- `shared/scripts/lib/reconcile_triage.py` — comment only (F13)

Risk flags: `touches_shared_infra`. Not `cross_component` (see Scope).

## Round 3 — the hatch is deleted, and why that is the safer diff

The Stage-3 doubt review was asked to argue plainly whether the supersession hatch
was worth its risk. It argued that the trade is inverted, and the operator agreed.

**Retention is safer than the status quo.** Under `main`'s id-only rule a superseded
append was DROPPED. Without the hatch it is RETAINED. So the shipped change is
strictly more conservative than `main` for that class — what round 2 called a
"regression" is an *accumulation* regression, not a loss one.

**Drainage was the only irreversible thing in the diff.** When the hatch fired it
deleted the LAST copy: `dedup_triage_lines` had kept that line off the branch by
definition, so the gitignored outbox was the only place it existed. FR-01.14 — the
criterion this run's Spec-Impact rests on — says every entry written can afterwards
be read back.

**Its correctness could not be held by a test.** It was an agreement between
`sweep_gc` and `churn_merge`, using two different append detectors on two different
strings, and no test imported both. Three attempts were needed; two leaked in the
DROP direction (duplicate text; then a whitespace variant, because dedup keys its
byte-identical stage on the RAW line while `str.strip()` is Unicode-aware and JSON
whitespace is not). A fourth latent leak survived only because a *third* module
blocked first.

**The benefit is measured zero.** No superseded appends exist in the real 1457-line
log. The buffer is gitignored; `git clean -x` empties it anyway.

Deleting it also resolved four further doubts outright (the whitespace axis, the
misleading "both conditions" guarantee, the absent observability, and the missing
property test), and let `parse_delivered` return to a 2-tuple — so the type system
no longer offers a future caller the id-only anchor that caused finding 14 at all.

Both external code reviewers then flagged, correctly, that AC-7 still promised
drainage. That was a stale criterion, not a code gap; AC-7 is rewritten above.

## Confidence Calibration

- **Boundaries touched:** `shared/scripts/lib/sweep_canon.py` (new — canonical
  equivalence leaf), `sweep_gc.py` (membership + partition), `sweep_outbox.py` (call
  site + docstring), `shared/scripts/tools/triage_gc.py` (pass-2 overlay),
  `reconcile_triage.py` (comment), `shared/tests/_sweep_helpers.py`, plus
  `shared/glossary.md` and `docs/hooks-and-pipeline.md`. Risk flag
  `touches_shared_infra`; NOT `cross_component` (`churn_merge.py` deliberately out of
  scope — findings 25 and the RecursionError gap travel with their cards).

- **Empirical probes run:**
  1. *F14's premise* — `.shipwright/triage.jsonl` line 285 (`trg-60ef91fb`) carries a
     `ts` ending `+00:00`; `triage._now_z()` always `.replace("+00:00","Z")`, so a
     foreign producer really does re-serialize same-id records. The audit left this
     unverified; it holds.
  2. *F26's consequence* — reverted the fix and ran the compaction: `drop_ids ==
     {'trg-human1'}`. A human decision really was scheduled for deletion.
  3. *Non-finite collision* — `{"n":1e400}` and `{"n":1e999}` both canonicalized to
     `{"n":Infinity}`; after the float rejection both return `None`.
  4. *Supersession leak (twice)* — `superseded_appends([v1,v2,v2])` contained `v2`;
     later `[X,Y,X+" "]` named `X`, which dedup KEEPS. Both were drop-direction
     losses; both are moot now the hatch is gone.
  5. *Lock cost* — on the real 1457-line log: `parse_delivered` 25.5 ms, against a
     section budgeting 120 s for one commit. Also: all 1457 lines canonicalize, and
     ZERO superseded appends exist — the datum that decided the hatch's removal.
  6. *`STATUSES` type* — a tuple, so an unhashable `newStatus` cannot raise. The
     external reviewer's `TypeError` claim is a false positive; the guard test ships
     anyway against a future type change.
  7. *Keyword-only enforcement* — a leftover positional `is_delivered` call failed
     with `TypeError`, confirming the silent-reinterpretation hazard is now loud.

- **Test Completeness Ledger:** every behaviour this diff introduces or changes,
  each `tested` or `untestable` with a closed-vocabulary reason. 0 testable-untested.

  | # | Behaviour | Status | Evidence |
  |---|---|---|---|
  | 1 | Same-id, content-different append is not dropped (AC-1) | tested | `test_same_id_changed_content_survives`, `test_gc_keeps_same_id_when_content_differs`, `test_e2e_same_id_changed_append_stays_in_outbox` |
  | 2 | Re-serialized status line becomes GC-able (AC-2) | tested | `test_reserialized_status_line_is_delivered`, `test_e2e_reserialized_status_line_is_gcd` |
  | 3 | Key-order/whitespace immunity preserved (AC-3) | tested | `test_reserialized_append_is_delivered`, `test_gc_drops_delivered_append_even_if_reserialized` |
  | 4 | Duplicate-key lines never cross-match | tested | `test_duplicate_keys_do_not_cross_match` |
  | 5 | No float literal is canonicalizable (AC-8) | tested | `test_float_literals_never_cross_match` (4 pairs), `test_integers_remain_canonicalizable` |
  | 6 | `canonical_form` is total (leaf) | tested | `test_unparseably_deep_object_degrades_instead_of_raising`, `test_non_dict_json_routes_to_text_membership`, `test_bare_scalar_routes_through_text_path` |
  | 7 | Fail-safe on unreadable origin | tested | `test_empty_origin_delivers_nothing`, `test_delivered_membership_gcs_nothing_on_timeout` |
  | 8 | Damaged status event is skipped WHOLE (AC-4) | tested | `test_damaged_status_does_not_rewrite_the_human_decision` |
  | 9 | A damaged event cannot reclassify a human decision as machine churn | tested | `test_damaged_status_cannot_turn_a_human_decision_into_machine_churn` |
  | 10 | Non-string `newStatus` ignored identically | tested | `test_non_string_status_is_ignored_by_both_resolvers` |
  | 11 | Both resolvers agree on a damaged event (AC-5) | tested | `test_both_resolvers_agree_on_a_damaged_status_event` |
  | 12 | A valid status flip still applies (no over-blocking) | tested | `test_a_valid_status_event_still_applies` |
  | 13 | `is_delivered` membership sets are keyword-only | tested | every call site; a leftover positional call raised `TypeError` during verification |
  | 14 | AC-6 comment names an existing predicate and records that it is advisory | untestable | `requires-manual-visual-judgment` — a comment has no runtime behaviour; the two facts it asserts were verified by reading (`_has_staged_changes` exists at `:111`, called at `:201`, lock taken at `:218`) |
  | 15 | `glossary.md` / `hooks-and-pipeline.md` describe the shipped rule | untestable | `requires-manual-visual-judgment` — prose accuracy; no drift gate covers these two sentences |

- **Confidence-pattern check:**
  - *Asymptote (depth).* Six review rounds. Loss-class findings per round: 1, 2, 0,
    then the doubt review's argument that the remaining loss authority should not
    exist at all. The final round's external reviewers found ONE issue between them,
    and it was a stale spec line, not code. Depth has converged.
  - *Coverage (breadth).* Every AC has a test that fails against the pre-fix code.
    The three unfalsifiable assertions found during this run are fixed and each is
    now pinned by an empirical check.
  - *Integration composition.* `cross_component` is NOT raised (no `churn_merge`
    change), so no integration behaviour is owed. The end-to-end tests nonetheless
    drive the real sweep with real git, real worktrees and the real canonical lock.
  - *Known limitations, recorded not hidden.* Two ship as cards rather than silently:
    `trg-94d3cb73` (P2.19f, decode asymmetry) and `trg-ed774f03` (P2.19g, superseded
    accumulation + the `RecursionError` path gap). Both are retention-direction.
