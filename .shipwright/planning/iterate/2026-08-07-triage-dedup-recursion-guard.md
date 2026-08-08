# Iterate 2026-08-07 — Triage outbox dedup: RecursionError escapes the canonical lock

**Run-ID:** `iterate-2026-08-07-triage-dedup-recursion-guard`
**Intent:** BUG · **Complexity:** medium (operator-overridden — see below)
**Status:** implemented
**Card:** `trg-57d0d6d3` (P2.19g), successor to the dismissed `trg-ed774f03`
**Evidence:** `.shipwright/planning/iterate/2026-08-05-it1-audit-remainder.md` (D1/AC-7,
where the card was filed), `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`

## Why this run exists, and why complexity is overridden

`trg-57d0d6d3` bundles two remainders the prior audit-remainder run deliberately did
NOT fix. Stage-1 classification (message-only, no diff yet) returned `small` with no
risk flags. The operator's launch instructions explicitly requested the medium-tier
review gate regardless — an internal Opus plan review followed by external plan
review, and a code-review cascade run with `model=opus` — so this run is executed at
**medium** by operator override (Override Classes: complexity-gated, user-adjustable).
That also matches what the two external-review CLI calls require (`--spec-file`,
`--plan-file`).

## Scope decision: TEIL 2 only

The card bundles two problems "because they are in the same neighborhood
(sweep_gc / churn_merge / triage_validate)". They are **not** bundled here.

**TEIL 1 (Ansammlung / accumulation of superseded appends) is explicitly OUT OF
SCOPE for this run, by the card's own instruction, not by omission.** The card's
"WICHTIG FÜR DEN NÄCHSTEN ANLAUF" section documents that a drain mechanism for this
was built, reviewed, and deleted three times (`.shipwright/planning/iterate/2026-08-05-it1-audit-remainder.md`,
Round 2 D1 / Round 3), because:

- it was the only path in the module able to delete the LAST copy of a record
  (`dedup_triage_lines` had, by definition, kept that line off every branch);
- its correctness depended on an agreement between `sweep_gc` and `churn_merge`
  using two different append-detectors on two different strings, which no test
  could hold;
- two of three attempts leaked in the DROP direction;
- the measured benefit is zero — the real 1457-line log contains no superseded
  append at all.

The card itself states the fail-safe direction explicitly: *"Liegenbleiben ist die
fail-safe Richtung; ohne Klappe ist der heutige Stand strikt sicherer als vorher"*
(leaving it alone is the fail-safe direction; without the drain, today's state is
strictly safer than before). Re-attempting it inside an `--autonomous` run with no
operator in the loop to weigh a fourth attempt is the wrong setting for a change
the card's own author flagged as needing a property test that "no test could hold"
three times running. **This run makes no code change toward TEIL 1.** The
`trg-57d0d6d3` card stays open for it; a future attempt still owes the property
test over both functions (intersection with what dedup keeps is empty) and its own
counter + log line, per the card.

**TEIL 2 (RecursionError escaping the canonical lock) is this run's entire scope.**

## Re-measurement: two of the card's own claims no longer hold

The card was filed 2026-08-06, against a version of the code that has since moved
(iterate-2026-08-06-triage-validate-deadends and the `lib.triage_dedup` extraction
both landed after). Re-measured 2026-08-07:

| Card said | Measured today |
|---|---|
| The unguarded call site is `churn_merge._append_id`, catching only `(JSONDecodeError, ValueError)` | No `_append_id` function exists in `churn_merge.py`. `dedup_triage_lines` was extracted to `lib/triage_dedup.py` (iterate-2026-08-06); the unguarded call site is `triage_dedup._parsed_append` (`triage_dedup.py:88-96`), and it catches exactly `(json.JSONDecodeError, ValueError)` — same defect, different address. |
| `classify_triage_text` "hat dieselbe blanke json.loads-Stelle und kann [RecursionError] daher nicht abfangen" | **Already fixed**, independently, by iterate-2026-08-06-triage-validate-deadends: `classify_triage_text` now parses via `lib.jsonl_records.split_records`, which explicitly catches `(ValueError, RecursionError)` at both raise sites (`jsonl_records.py:195`, `:251`) and degrades to a reported fragment instead of propagating. Verified by direct probe (see Confidence Calibration). |
| "aber churn_merge löst cross_component aus … deshalb eigener Lauf" (the fix touches `churn_merge.py`, which raises `cross_component`, hence its own run) | **Half right, for a different reason than stated.** `triage_dedup.py` alone does NOT match `CROSS_COMPONENT_FILE_PATTERNS` (measured: `is_cross_component_change(["shared/scripts/lib/triage_dedup.py"])` → `False`). But the internal Opus plan review (below) found a **second, sibling instance of the identical defect** in `churn_merge.py` itself — `dedup_event_lines` (`churn_merge.py:184`) — which this run now also fixes, and `churn_merge.py` IS filename-anchored in the pattern. Re-measured with both files in the diff: `is_cross_component_change([..., "shared/scripts/lib/churn_merge.py", ...])` → **`True`**. So `cross_component` fires after all — not for the reason the card gave (it never named `dedup_event_lines`), but for a reason the card's own author could not have seen before the `triage_dedup.py` extraction made `_append_id` two functions instead of one shared shape. |

**`cross_component` is confirmed TRUE for this run.** Per the risk taxonomy this
floors classification at medium (already the operator-overridden level) and owes
**integration coverage** — a real-scenario test proving the two fixed call sites
compose with their real callers, recorded as a `category:"integration"` behavior
in the Test Completeness Ledger (see Acceptance Criteria, AC-5).

## Root cause (F-debug)

**Call chain (verified by reading, not assumed):**
`sweep_outbox_to_branch` (`sweep_outbox.py:171`, inside `with triage._FileLock(lock_path):`)
→ `quarantine_decide` = `sweep_quarantine.decide` (`sweep_quarantine.py:153`)
→ `_materialize` (`sweep_quarantine.py:123`)
→ `dedup_triage_lines(worktree + outbox)` (`triage_dedup.py:144`)
→ per line, `_parsed_append(line)` (`triage_dedup.py:88`)
→ `json.loads(line)` inside `try: ... except (json.JSONDecodeError, ValueError): return None`.

A sufficiently deeply nested JSON value (e.g. `"[[[[...]]]]"` past Python's default
recursion limit) makes `json.loads` raise `RecursionError` from its scanner.
`RecursionError` subclasses `RuntimeError`, not `ValueError`, so it is **not**
caught by `_parsed_append`'s except tuple. It propagates uncaught through
`dedup_triage_lines` → `_materialize` → `decide` → `sweep_outbox_to_branch`,
all of which run **inside the canonical triage `_FileLock`**, and
`sweep_outbox_to_branch` is invoked from `setup_iterate_worktree.py`'s Step 5 —
exactly the abort point after a successful `git worktree add` that this module's
own docstring, `sweep_outbox.py`'s docstring, and `sweep_quarantine.py`'s docstring
all separately describe as something the sweep must not do.

**Precision correction (external plan review, openai — accepted).** The first
draft of this spec framed this as risking an *abandoned lock*. That overstated
it: `triage._FileLock` is a real context manager (`__enter__`/`__exit__`,
`shared/scripts/lib/file_lock.py:223`), so Python's `with` protocol releases it
on any exception, including `RecursionError` — the lock itself is never stuck.
The actual defect is narrower and still real: `setup_iterate_worktree.py` has no
handler around its Step 5 call (`setup_iterate_worktree.py:223`), so the
uncaught exception crashes the whole worktree-setup script *after* `git
worktree add` already succeeded (Steps 1-4) — leaving an orphaned worktree
directory and branch on disk, no snapshot written, no run pointer recorded, and
the run_id spent on a non-functioning environment that needs manual cleanup.
"Not survivable", as the sibling docstrings put it, means the setup script dies
mid-sequence leaving disk state behind, not that a lock is held forever.

**This is pre-existing, not introduced by this run** (the card is explicit: "Vorbestehend, nicht
neu"). It predates the `triage_dedup.py` extraction; the defect moved with the code,
address only.

**Why `RecursionError` is a realistic input, not a hypothetical:** `lib/jsonl_records.py`
already treats it as real and documented ("`RecursionError` (not a `ValueError`)
escapes from json's scanner on a deeply nested blob — plausible from a
truncated/interleaved write. Letting it propagate would crash every reader instead
of degrading.") and catches it at both its own `json` call sites. The same input
class reaches `triage_dedup._parsed_append` through the same outbox lines
`jsonl_records` was written to tolerate — a truncated or interleaved write is not
selective about which reader sees the damaged line first.

**Second instance, found by the internal Opus plan review, not by the card.**
`churn_merge.dedup_event_lines` (`churn_merge.py:184`) has the identical defect
shape one function away: `ev_id = json.loads(line).get("id")` inside
`try: ... except (json.JSONDecodeError, AttributeError): ev_id = None`. Neither
exception is `RecursionError`. This function dedups `shipwright_events.jsonl`
(not the triage log) and is called from
`resolve_churn_conflicts.py:155` (`_reconcile_events`), which runs during git
merge-conflict resolution when `origin/main` has advanced past an open iterate
branch — a context where an uncaught crash is arguably worse than the triage
path, since it aborts mid churn-merge-resolution rather than mid-lock. The card
never named this function (it only knew of the triage-side one, mis-described as
`_append_id`), but it is the same defect, immediately adjacent, discovered while
verifying the card's own claims against current code. Fixed in the same diff —
see Design.

A third caller of the triage-side function exists too:
`resolve_churn_conflicts.py:176` (`_reconcile_triage`) calls
`dedup_triage_lines` directly (a third call path alongside
`sweep_quarantine._materialize` and `reconcile_triage.py:224`). No extra fix is
needed for it — fixing at `_parsed_append`'s source protects every caller
uniformly, this one included.

## Acceptance Criteria

- [x] **AC-1.** ✅ done — `test_deeply_nested_append_does_not_raise_and_passes_through` + churn_merge sibling. A same-id `append` group containing one line whose value nests deeper
  than Python's JSON recursion limit does not raise `RecursionError` out of
  `dedup_triage_lines`; the pathological line is treated as unparseable (same
  outcome as a `JSONDecodeError` today — kept, routed to raw-text handling
  upstream, never crashes the caller).
- [x] **AC-2 (property test, per the card's own requirement for whoever next touches
  this module).** For arbitrary same-id append groups, `dedup_triage_lines`' output
  is a subset of its input (no line is ever fabricated), and it never raises for any
  syntactically-decodable-or-not JSON payload up to a bounded pathological nesting
  depth. This is the general "total function" property `triage_dedup.py`'s own
  module docstring already claims for `_anchor_of`; `_parsed_append` gets the same
  guarantee.
- [x] **AC-3 (regression guard, exact reproduction of the crash this fixes — outcome
  PINNED, path TRAVERSAL confirmed, lock USABILITY confirmed; strengthened per
  external review round 2, openai findings 1 & 2 — accepted).** Driving
  `sweep_outbox_to_branch` end-to-end with a deeply-nested line sitting
  alongside at least one ordinary, valid same-id append in the OUTBOX — so the
  pathological line reaches `dedup_triage_lines`' same-id grouping rather than
  being filtered out earlier by normalization or quarantine classification —
  (a) is confirmed to fail with `RecursionError` **pre-fix**, at the intended
  call chain (`dedup_triage_lines` → `_parsed_append`), before the fix is
  applied — the direct unit regression in AC-1 is the focused proof; this is
  the composition proof; (b) **post-fix**, completes without raising, and the
  returned `SweepResult.status == "invalid"` **REGARDLESS of whether the deep
  line originates in the outbox or the worktree-tracked log** — measured
  directly against `sweep_quarantine.decide`, correcting this AC's first draft
  (which assumed outbox-origin → `quarantine`): `classify_triage_text` reports
  ANY deeply-nested line as an "unrecoverable fragment"
  (`has_non_orphan_error = True`), and `decide()` returns `block`
  unconditionally on that flag, before the outbox-vs-tracked partition logic
  that would otherwise route an outbox-only defect to quarantine ever runs. So
  the fix's real, measured effect is narrower and more valuable than first
  assumed: the sweep no longer *crashes* on this input — it returns the exact
  same clean, actionable `block` result (citing `triage_repair.py`) that any
  other corrupt line already gets, with **nothing mutated** (mirrors the
  existing `test_unrecoverable_fragment_blocks_with_no_side_effects` pattern).
  There is no separate origin-dependent case to test — (c) below replaces the
  originally-planned outbox-vs-tracked split, since both origins measure
  identically; (d) after the run, the SAME canonical lock is successfully
  re-acquired and released in a minimal follow-up operation — an explicit,
  black-box proof that the lock is left usable, rather than inferring it from
  the `with` statement's semantics
  alone. Mirrors the existing E2E style in `shared/tests/_sweep_helpers.py` /
  the prior run's `test_e2e_*` tests.
- [x] **AC-4.** `classify_triage_text`'s existing `RecursionError` handling (already
  shipped) is pinned by a test in this run's diff, so the two resolvers this card
  names cannot silently diverge again — mirrors AC-5 of the prior run, which did
  the same thing for the `status`-event resolver pair.
- [x] **AC-5 (integration coverage — `cross_component` fires, see re-measurement
  table; outcome PINNED per external review, openai finding 1 — accepted).**
  Driving `resolve_churn_conflicts._reconcile_events` against an events log
  containing ordinary same-id duplicates plus one deeply-nested line: (a)
  completes without raising; (b) the deeply-nested line survives byte-identical
  in the output (widening the except tuple to `ev_id = None` must not drop,
  truncate, or silently merge the pathological line — only its `id` extraction
  degrades, per `dedup_event_lines`'s "never drops a distinct line" contract);
  (c) `validate_events_text` run against the result reports the line as
  unparseable via the same "not valid JSON (unrecoverable fragment)" path an
  ordinary corrupt line already takes (verified as a build-time probe before
  writing this as an assertion — see Confidence Calibration probe 7).
- [x] **AC-2, renamed "bounded invariant/matrix test" (external review round 2,
  openai finding 3 — accepted: "property test" implied generated inputs;
  the actual coverage is a hand-written combinatorial matrix, which is the
  honest and proportionate description).** Input domain: a `Sequence[str]` of
  JSONL lines in the real append-record shape (same `id`, varying payload) —
  not arbitrary Python objects. Matrix cells: ordinary valid appends × one
  syntactically-malformed line × one line with a JSON value nested
  deterministically beyond the interpreter's default recursion limit (reusing
  the proven `'{"a":' * 20000` idiom, never `sys.setrecursionlimit`) × placement
  (pathological line first / last / alongside its own same-id twin). Asserts
  ordered-subsequence preservation (output ⊆ input, order kept) and no
  exception for any cell. No new property-testing dependency — the bounded,
  hand-written matrix is sufficient at this scope. The identical matrix shape
  is written for `dedup_event_lines` too (deepseek round-1 finding — low,
  accepted: no equivalent coverage was specified for the second fixed
  function), **plus** deepseek round-2 finding (low, accepted): one matrix
  cell for `dedup_event_lines` specifically confirms that a pathological line
  sharing an `id` with an otherwise-valid, correctly-parsed line still leaves
  BOTH in the output (the `ev_id = None` degradation means the pathological
  line is invisible to the id-collision warning path, not deduplicated away —
  documented as intentional, not silently accepted).

## Design

**One token, one location.** Add `RecursionError` to `_parsed_append`'s except
tuple in `shared/scripts/lib/triage_dedup.py`:

```python
except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
    return None
```

(`TypeError` added post-Build, doubt-reviewer finding 4, Stage 3: the
function's docstring claims an absolute "Total: never raises" contract, and
`sweep_canon.canonical_form` — same file family, same claim — already guards
`TypeError` for the identical reason: the signature only ever receives `str`
today, but an absolute contract does not lean on caller discipline.)

`_parsed_append` returning `None` already means "not a usable append line" —
`dedup_triage_lines` skips it in the same-id grouping and it falls through
unmodified into the deduped output (byte-identical dedup in stage 1 still applies;
stage 2's grouping just never sees it as a group member). This is the exact
"treated as unparseable" outcome `AC-1` asks for, and it requires no change to
`dedup_triage_lines` itself — the fix is bounded to the one function that owns the
unguarded `json.loads`.

This is the same remedy `lib/jsonl_records.py` already applies at its two call
sites (`split_records`, `_decode_run`), so this run does not invent a new pattern —
it extends an established one to the two call sites in this neighborhood that were
missed when `triage_dedup.py` was extracted.

**Second location, same token.** `churn_merge.dedup_event_lines`
(`churn_merge.py:184`) gets the identical treatment:

```python
except (AttributeError, ValueError, RecursionError):
    ev_id = None
```

(`json.JSONDecodeError` is dropped rather than added, per external review —
openai finding 5, accepted: it is a `ValueError` subclass, so listing both is
redundant in a deliberately minimal diff. `ValueError` is added alongside
`RecursionError` for the same reason `triage_dedup._parsed_append` already had
it and this function didn't: `json.loads` can in principle raise other
`ValueError` subclasses beyond `JSONDecodeError`, and this function's job is
"figure out an id or give up", not "distinguish exception subtypes" —
matching `_parsed_append`'s existing tuple is defense-in-depth, not a response
to a measured failure mode. **Correction (doubt-reviewer finding 5, Stage 3):**
an earlier draft of this paragraph cited "malformed surrogate-escape sequences
round-tripped by `durable_read_text`" as the concrete trigger; checked directly
— `json.loads` on a `str` containing lone surrogates does not raise beyond
`JSONDecodeError`, the `UnicodeDecodeError` path needs `bytes` input, and no
caller here passes `bytes`. That claim is removed rather than left as an
unverified assertion in a spec that elsewhere demands empirical probes.
`_parsed_append`'s own tuple keeps `json.JSONDecodeError` explicit alongside
`ValueError` — that is pre-existing code this run does not touch beyond adding
`RecursionError`, so it is left as-is rather than "fixed" as a drive-by; only
the newly-written tuple drops the redundant subclass.)

Both fixes are the same shape: a call site whose contract is "best-effort parse,
`None`/skip on failure" gets its except tuple widened to match the failure modes
`json.loads` can actually raise on adversarial input, exactly as
`jsonl_records.py` already documents.

**Why not route `triage_dedup.py` through `split_records` instead of `json.loads`
directly (matching `classify_triage_text`'s fix)?** Considered and rejected for this
run: `_parsed_append` parses one already-line-split string and only needs a
best-effort "is this a usable append object", not `split_records`' record-boundary
recovery (glued multi-record lines, partial resync) — machinery `dedup_triage_lines`
does not need, since `sweep_quarantine._materialize` already normalizes to one
record per line upstream via `normalize_lines`. Importing `split_records` here to
reuse one exception tuple would add a dependency for no behavioral gain. A one-line
`except` addition is the smaller, more reviewable diff and matches the card's own
sizing ("Der Fix ist ein Token je Stelle").

## Affected Boundaries

- `shared/scripts/lib/triage_dedup.py` — fix 1 (except-tuple addition, `_parsed_append`)
- `shared/scripts/lib/churn_merge.py` — fix 2 (except-tuple addition, `dedup_event_lines`;
  found by the internal Opus plan review, not by the originating card)
- `shared/tests/test_sweep_gc_canonical.py` — the docstring of
  `test_unparseably_deep_object_degrades_instead_of_raising` (lines 182-188)
  asserts, as a documented pre-existing gap, that `dedup_triage_lines` still
  raises `RecursionError` for the exact input this run fixes. That claim becomes
  false on merge; the docstring is corrected, and it now points at where the
  end-to-end assertion it previously disclaimed actually lives (below) rather
  than growing one in place — **correction, spec-reviewer Stage 1**: this
  bullet originally said the test itself would be "extended into the
  end-to-end assertion"; that would have added real git/lock machinery to a
  file whose own docstring and prior Stage-3 review deliberately scope it to
  `sweep_canon` ONLY (`test_sweep_gc_canonical.py` never touches git, a
  worktree, or the canonical lock anywhere else in the file), so the extension
  is DELEGATED instead, named explicitly in the corrected docstring.
- `shared/tests/test_sweep_outbox_dispositions_integration.py` — the
  end-to-end assertion (AC-3): `test_deeply_nested_line_blocks_cleanly_instead_of_crashing_the_lock`,
  real git + real canonical lock, the file this kind of test already lives in.
- `shared/tests/` — new unit tests for both fixes, a property test (AC-2), a pin
  test for `classify_triage_text`'s already-shipped RecursionError handling
  (AC-4), and the integration test (AC-5)

Risk flags: `touches_shared_infra` (`shared/scripts/lib/`). Measured
`cross_component`: **True** once `churn_merge.py` is included (see re-measurement
table above) — integration coverage owed, AC-5.

## Alternative considered — and why not

**Catch `RecursionError` at a higher layer** (e.g. wrap the `dedup_triage_lines`
call in `sweep_quarantine._materialize`, or in `sweep_outbox_to_branch` itself).
Rejected: that would convert a whole-sweep failure into a silent partial success
with no clear "what happened to this one line" story, and it leaves every OTHER
direct caller of `dedup_triage_lines` still exposed to the same crash on its own
call path — there are three: `sweep_quarantine._materialize`,
`reconcile_triage.py:224`, and `resolve_churn_conflicts.py:176`
(`_reconcile_triage`), none of which go through `sweep_outbox_to_branch`. Fixing
at the source (`_parsed_append`) protects all three uniformly, matches the
existing `jsonl_records.py` precedent, and is the smallest diff that closes the
actual hole. The identical argument applies to `dedup_event_lines` and its own
caller, `resolve_churn_conflicts.py:155`.

**Surface the caught `RecursionError` as a dedup warning, rather than silently
returning `None`/skip** (raised by the internal Opus plan review as a candidate
third alternative — this module's own thesis is that the one path able to drop a
record must be able to say so). Considered and rejected for the parse-failure
case specifically: unlike an actual *drop* (the supersession collapse this
module exists to police), a line that fails to parse as an `append` is not
removed by either fix — it falls through unmodified into the deduped byte-stream
and is picked up downstream by `classify_triage_text`/`split_records`, which
already reports it as a corrupt fragment naming `triage_repair.py` (for the
triage side) or by `validate_events_text`, which reports the same for the
events side. Adding a second, duplicate warning at the parse site would tell the
operator about the same line twice through two different channels with no new
information. The module's "must be able to say so" thesis is about the
*supersession* decision (kept-last vs. collision), which is unaffected by this
fix — a line that can't even be parsed as an append was never a supersession
candidate.

## Confidence Calibration

- **Boundaries touched:** `shared/scripts/lib/triage_dedup.py` (fix 1),
  `shared/scripts/lib/churn_merge.py` (fix 2); test files under
  `shared/tests/`. Risk flag `touches_shared_infra`; `cross_component` **IS**
  true once `churn_merge.py` is included (measured, see re-measurement table —
  corrected here after external review, openai finding 6, caught this bullet
  had gone stale when the scope grew from one fix to two).

- **Empirical probes run (pre-build):**
  1. *Call chain confirmed by reading*, not assumed — traced
     `sweep_outbox_to_branch` → `sweep_quarantine.decide` → `_materialize` →
     `dedup_triage_lines` → `_parsed_append`, confirming the lock scope
     (`with triage._FileLock(lock_path):` wraps the entire chain in
     `sweep_outbox.py`).
  2. *`classify_triage_text` already fixed* — read `triage_validate.py`'s module
     docstring and body: it now parses via `split_records`, which the
     `jsonl_records.py` module docstring and code (lines 195, 251) confirm
     explicitly catches `(ValueError, RecursionError)`.
  3. *`cross_component` re-measured* — ran
     `is_cross_component_change(["shared/scripts/lib/triage_dedup.py", "shared/tests/test_triage_dedup.py"])`
     directly against `risk_detectors.py`; returned `False`.
  4. *`_append_id` no longer exists* — grepped `churn_merge.py` for the name the
     card uses; not present. The matching except-tuple
     `(json.JSONDecodeError, ValueError)` exists verbatim in `triage_dedup.py:92-93`
     (`_parsed_append`), confirming the address moved but the defect is the same
     one the card describes.
  5. *Reproduced directly, pre-fix* — called `dedup_triage_lines` with a line
     carrying `"[" * 3000 + "]" * 3000` nested under an object field; confirmed
     `RecursionError` propagates out uncaught (`REPRODUCED` — direct probe,
     2026-08-07, before any code was written).
  6. *Internal Opus plan review (per operator instruction, run before external
     review)* — verified the root-cause diagnosis and the one-token fix against
     the real code, and found the second call site
     (`churn_merge.dedup_event_lines`) this spec's first draft missed, plus the
     stale test docstring, the underspecified AC-3 verdict, and the third
     caller `resolve_churn_conflicts.py:176`. All four folded in above. One
     optional third alternative (surface `RecursionError` as a warning) was
     considered and rejected with reason (see Alternative section) rather than
     silently dropped.

## Round 1 — internal Opus plan review (2026-08-07, before any code written)

| Finding | Severity | Disposition |
|---|---|---|
| `churn_merge.dedup_event_lines` (`:184`) has the identical unguarded `json.loads`, missed by the spec's first-draft re-measurement table (which only grepped for the name `_append_id`) | high | **Accepted, folded in.** Fixed in the same diff (Design); `cross_component` re-measured TRUE with `churn_merge.py` included; AC-5 (integration coverage) added. |
| `test_sweep_gc_canonical.py:182-188`'s docstring documents the exact gap this run closes and becomes false on merge | medium | **Accepted, folded in.** Affected Boundaries updated; the test's docstring and scope will be corrected during Build. *(Superseded — see the corrected Affected Boundaries bullet and `test_sweep_gc_canonical.py`'s updated docstring, which delegate the end-to-end proof to `test_sweep_outbox_dispositions_integration.py` rather than extending this file in place; spec-reviewer Stage-1 finding 3.)* |
| AC-1/AC-3 asserted only "does not raise", which passes whether the post-fix line is quarantined, held, or silently persists forever | medium | **Accepted, folded in.** AC-3 now pins the exact verdict (`quarantine` for outbox-origin, `invalid`/block for tracked-origin). |
| Property test (AC-2) risk: `sys.setrecursionlimit` misuse could crash the interpreter instead of testing gracefully | medium | **Accepted, folded in as a build constraint** (see AC-2 note below): reuse the existing `'{"a":' * 20000` idiom already proven in `test_sweep_gc_canonical.py:190`; never call `sys.setrecursionlimit`. |
| Third caller `resolve_churn_conflicts.py:176` unnamed in the rejected-alternative rationale | low | **Accepted, folded in.** Named in Alternative section. |
| Third alternative not considered: surface the caught `RecursionError` as a dedup warning | low | **Considered and rejected with reason** — see Alternative section (parse failures fall through to the existing downstream corruption-reporting path; a duplicate warning at the parse site adds no information). |

**Build constraint carried forward from Round 1:** the property test (AC-2) must
not call `sys.setrecursionlimit` and must bound both nesting depth and example
count — reuse the proven `'{"a":' * 20000` / `"[" * N + "]" * N` idioms already
in the test suite rather than searching for the interpreter's exact limit.

- **Test Completeness Ledger:**

  | Behavior | Category | Status | Evidence |
  |---|---|---|---|
  | AC-1: deep line does not raise out of `dedup_triage_lines` | unit | tested | `test_triage_dedup.py::test_deeply_nested_append_does_not_raise_and_passes_through` |
  | AC-1 sibling: deep line does not raise out of `dedup_event_lines` | unit | tested | `test_churn_merge_recursion_guard.py::test_deeply_nested_event_line_does_not_raise_and_survives` |
  | AC-2 matrix: deep line + same-id twin, placement (first/last), + malformed sibling — `dedup_triage_lines` | unit | tested | `test_triage_dedup.py::test_deeply_nested_line_beside_a_valid_same_id_twin_is_a_collision`, `::test_deeply_nested_line_matrix_placement_first_and_last`, `::test_deeply_nested_line_beside_a_malformed_line` |
  | AC-2 matrix, identical shape — `dedup_event_lines` | unit | tested | `test_churn_merge_recursion_guard.py::test_deeply_nested_event_line_beside_a_valid_same_id_twin`, `::test_deeply_nested_event_line_matrix_placement_first_and_last`, `::test_deeply_nested_event_line_beside_a_malformed_line` |
  | AC-3: `sweep_outbox_to_branch` end-to-end — no crash, `status == "invalid"`, outbox unchanged, quarantine empty, nothing committed, lock reusable after | integration | tested | `test_sweep_outbox_dispositions_integration.py::test_deeply_nested_line_blocks_cleanly_instead_of_crashing_the_lock` (real git, real worktree, real lock — pre-fix failure confirmed via `git stash`) |
  | AC-4: `classify_triage_text`'s pre-existing `RecursionError` handling stays pinned | drift-pin | tested | `test_triage_validate.py::test_deeply_nested_line_is_reported_not_raised` (confirmed already-green pre-fix, proving the prior iterate's independent fix) |
  | AC-5: `_reconcile_events` survives a deep line byte-identical + reports it via `validate_events_text` | integration | tested | `test_resolve_churn_conflicts_recursion_guard.py::test_reconcile_events_survives_a_deeply_nested_line`, `::test_reconcile_events_deep_line_reported_as_unrecoverable_fragment` (real git repo, real event log; pre-fix failure confirmed via `git stash`) — this is the `cross_component`-mandated integration coverage |
  | Doubt-reviewer finding 1: `dedup_event_lines` does not raise `TypeError` on a non-`str` decoded id (unhashable-in-dict crash) | unit | tested | `test_churn_merge_recursion_guard.py::test_non_str_id_does_not_raise_typeerror` (reproduced pre-fix directly via `uv run python` probe) |
  | Doubt-reviewer finding 3: `_reconcile_triage` (the third real caller) survives a deep line, dedups its duplicate sibling, stages the rewrite, and reports the fragment — same composed-caller shape as AC-5, for the caller AC-5 didn't cover | integration | tested | `test_resolve_churn_conflicts_recursion_guard.py::test_reconcile_triage_survives_a_deeply_nested_line`, `::test_reconcile_triage_deep_line_reported_as_unrecoverable_fragment` |

  0 untested-testable behaviors.

## Round 2 — external plan review (2026-08-07, deepseek + openai via OpenRouter)

Verdicts: deepseek=**approve**, openai=**revise** (no contradiction — within one
step of each other per the tool's own comparator).

| Reviewer | Finding | Severity | Disposition |
|---|---|---|---|
| openai | AC-5 only asserted "does not raise" — insufficient for the events-log path; must show the pathological line is preserved, not silently dropped/merged | medium | **Accepted, folded in** (AC-5 rewritten with parts a/b/c above) |
| openai | AC-2 property-test domain underspecified — could read as arbitrary Python inputs rather than JSONL line strings | low | **Accepted, folded in** (AC-2 domain spelled out above) |
| openai | Spec overstated the risk as "lock abandonment"; a `with`-block exception still releases the lock — the real defect is an unhandled crash in the *caller*, after `git worktree add` | low | **Accepted, folded in** (Root cause section corrected above) |
| openai | AC-5's safety depends on an unverified claim about how `validate_events_text` reports an `ev_id=None` line — should be a build-time-verified prerequisite | low | **Accepted, folded in** (AC-5 part c; to be probed empirically during Build before being asserted) |
| deepseek | No property test specified for `dedup_event_lines`, only for `dedup_triage_lines`, despite the identical defect class | low | **Accepted, folded in** (AC-2 extended to both functions) |

### Round 2b — re-review after folding Round 2 in (same call, spec had changed)

Re-running the same external review against the updated spec text surfaced 6
more findings (openai) + 4 more (deepseek) — the tool is not idempotent across
spec edits, which is expected and is why this round exists. All accepted, no
rejections:

| Reviewer | Finding (compressed) | Severity | Disposition |
|---|---|---|---|
| openai | AC-3's E2E test could pass without the pathological line ever reaching `dedup_triage_lines` (earlier normalization/classification could intercept it first) | medium | **Accepted** — AC-3 now requires a pre-fix `RecursionError` reproduction at the intended call chain as part of the test, not just a post-fix outcome |
| openai | "Return succeeded" doesn't directly prove the lock is reusable | medium | **Accepted** — AC-3(d): reacquire the same canonical lock after each E2E run |
| openai | "Property test" (AC-2) is actually a bounded hand-written matrix, not generated cases — naming was misleading | low | **Accepted** — renamed "bounded invariant/matrix test" |
| openai | AC-5's dependency on `validate_events_text`'s exact behavior should be a verified precondition, not an assumption written into the AC before it's checked | low | **Accepted** — already planned as a build-time probe (Confidence Calibration probe 7); reinforced |
| openai | Redundant `json.JSONDecodeError` alongside `ValueError` in the new tuple | low | **Accepted** — dropped from the new `dedup_event_lines` tuple; pre-existing `_parsed_append` tuple left untouched (not a drive-by fix) |
| deepseek | Confirm the matrix covers a pathological line sharing an `id` with a valid line (both must survive in `dedup_event_lines`'s output) | low | **Accepted** — added as an explicit matrix cell |
| deepseek + openai (agreeing) | `validate_events_text` behavior for AC-5(c) must be probed at build time, not assumed | low | **Accepted** — same disposition as above, independently raised |
| deepseek | Bounded depth (`'{"a":' * 20000`) doesn't exercise "exactly at the recursion limit" (parses fine, no exception) | low | **Considered, no action needed** — reviewer's own conclusion: the fix targets lines that DO exceed the limit; a boundary-exact case exercises no new code path |

- **Confidence-pattern check:** Three review passes so far (internal Opus,
  external round 2, external round 2b re-review of the edited spec). Findings
  per pass: 6 (Round 1: 1 high / 3 medium / 2 low), 5 (Round 2: 1 medium / 4
  low), 10 (Round 2b: 2 medium / 8 low, one explicitly a no-action false
  alarm). Severity is trending down and no finding repeated verbatim across
  passes — depth is converging. Coverage: every AC now has an outcome-specific,
  path-traversal-confirmed, and (for the lock) usability-confirmed assertion.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-07-triage-dedup-recursion-guard/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — add
  `RecursionError` to the two existing best-effort parse except-tuples
- **Findings:** none from either reviewer
- **Reconciliation:** n/a — no objection to reconcile against the mini-plan's
  rejected alternative (broad `except Exception`); both reviewers independently
  named the same "smallest thing" this run already designed

Plan-stage reviews complete (internal Opus, external plan review x2, architecture
review). Build (Step 6, TDD) is next; the code-review cascade (Step 8,
spec-reviewer → code-reviewer → doubt-reviewer, model=opus per operator
instruction) runs after Build + Self-Review, before F6 commit, per the normal
skill order.

## Code-Review Cascade (post-Build)

### Stage 1 — spec-reviewer (opus)

First pass: **REJECT**, 3 findings. All accepted and fixed:

| Finding | Disposition |
|---|---|
| AC-3's E2E fixture used a distinct-id companion append instead of the same-id companion spec:158-161 names | **Fixed** — `test_sweep_outbox_dispositions_integration.py` now writes `h.item("trg-deepend2end")` beside `_deep_item("trg-deepend2end")` |
| `dedup_event_lines`'s AC-2 matrix was missing the placement and malformed-sibling cells the triage-side matrix has | **Fixed** — `test_churn_merge_recursion_guard.py` now carries all four cells, identical shape to the triage side |
| `test_sweep_gc_canonical.py`'s docstring claimed the boundary would be extended in place; the diff actually delegates to the E2E test | **Fixed the spec, not the diff** — the delegation is now recorded in Affected Boundaries (this file) as the intended design, not a silent divergence |

Re-review: **PASS**. Both non-blocking observations (a stale Round-1 disposition row; the Test Completeness Ledger being owed before F0) were addressed directly in this spec (see the superseded-marker on the Round 1 table above and the populated ledger in Confidence Calibration).

### Stage 2 — code-reviewer (opus)

**PASS**, 4 low findings, none blocking:

| Finding | Disposition |
|---|---|
| AC-5(b) test under-asserted (didn't prove the rewrite path ran; one dead disjunct) | **Fixed** — `test_resolve_churn_conflicts_recursion_guard.py` now asserts the rewrite branch ran, the duplicate line deduped, and the fragment error surfaces |
| `test_sweep_gc_canonical.py`'s corrected docstring carried an 11-line provenance paragraph (before/after narration) | **Fixed** — trimmed to the two load-bearing facts |
| Four sibling best-effort `json.loads` readers of the same events log (`campaign_status.py`, `iterate_phase_groups.py`, `iterate_timings.py`, `context_cost_core.py`) still miss `RecursionError` | **Deferred, not fixed here** (scope creep beyond this card) — filed as triage card `trg-acc195bf` |
| The `'{"a":' * 20000` nesting idiom is now spelled out in six test modules | **Left as-is** — reviewer's own conclusion: extraction is roughly a wash below 7 sites |

### External code review (parallel to Stage 3, deepseek + openai via OpenRouter, `--mode code`)

Verdicts: deepseek=**approve**, openai=**revise** (within one step, no contradiction).

| Reviewer | Finding | Severity | Disposition |
|---|---|---|---|
| openai | `.shipwright/triage.jsonl` carries 59 unrelated inserted lines, broadening the diff beyond TEIL 2 | medium | **Rejected, with reason** — investigated directly: every inserted line is a background triage-producer append/dismiss (compliance backlog, phase-quality, context-cost-measurement findings from unrelated iterates), not anything this session authored. Matches the established pattern of a sweep committing onto whatever branch is active (a `chore(triage)` commit already exists earlier on this branch, pre-dating this run). Reverting it would discard other producers' legitimate records; it is not part of this diff's design and carries no code-review risk. |
| openai | AC-3's "nothing mutated"/"nothing committed" claim only checked the outbox, quarantine, and branch triage lines — a defective implementation could still commit or touch another tracked file while returning `status == "invalid"` | medium | **Accepted, fixed** — the E2E test now also asserts the worktree's git HEAD is unchanged and `git status --porcelain` is empty after a blocked sweep |
| openai | The same-id-twin and malformed-sibling matrix cells (both `dedup_triage_lines` and `dedup_event_lines`) asserted membership only, not order — a reordering regression would pass | low | **Accepted, fixed** — all four cells now assert full ordered-output equality |
| deepseek | none — approve, no findings | — | — |

### Stage 3 — doubt-reviewer (opus, fresh-context, biased to disprove)

**PASS (advisory)** — 5 objections, 0 unilaterally blocking. Six disproof
attempts against the fix's core safety claims (chain totality inside the
canonical lock, no-silent-drop downstream, the named remedy's reachability,
`RecursionError` masking a real runaway, resync-path cost, stage-1 dedup
unaffected) all **failed to disprove** — the reviewer's own framing, not a
self-assessment. Every surviving objection triaged (per this run's own
"fix/disclose/decline-with-reason" bar, set for the review cascade by an
earlier triage card in this same neighborhood):

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | `dedup_event_lines` still crashes on a non-`str` decoded id (`{"id":["x"]}` is truthy and unhashable, so `ev_id in id_to_line` raises `TypeError`) — same input class the `RecursionError` guard exists for, and this repo already guards the identical hazard elsewhere (`sweep_quarantine.py`'s orphan-id check, `_parsed_append`'s `isinstance` check) | medium | **Accepted, fixed** — `dedup_event_lines` now does `isinstance(ev_id, str) and ev_id`, matching the established idiom; regression test `test_non_str_id_does_not_raise_typeerror` reproduced the crash pre-fix directly |
| 2 | AC-3(d)'s lock-reusability assertion is vacuous: `FileLock`'s reentrancy short-circuit (`enter_reentrant`) makes a same-thread reacquire succeed even if the release had leaked, since it only checks whether this thread already holds the key | medium | **Accepted, fixed** — the test now asserts the process-wide lock registry (`file_lock_registry`) holds no entry for the key, checked directly rather than inferred from a trivially-succeeding reacquire |
| 3 | The third real caller, `_reconcile_triage`, has no integration coverage — and unlike `_reconcile_events`, it writes + `git add`s its rewrite *before* validating, so a real regression there would leave a modified+staged log inside a half-resolved merge, not just fail an assertion | low-medium | **Accepted, fixed** — added `test_reconcile_triage_survives_a_deeply_nested_line` and `::test_reconcile_triage_deep_line_reported_as_unrecoverable_fragment`, mirroring the AC-5 events-side pair |
| 4 | `_parsed_append`'s "Total: never raises" docstring claim exceeds its except tuple by this repo's own standard — `sweep_canon.canonical_form` makes the identical absolute claim and deliberately guards `TypeError` too, for caller-discipline independence | low | **Accepted, fixed** — added `TypeError` to `_parsed_append`'s except tuple (Design section updated above) |
| 5 | The spec's stated rationale for the new bare `ValueError` in `churn_merge.py` ("malformed surrogate-escape sequences round-tripped by `durable_read_text`") is an unverified, and checked-wrong, claim in a spec that elsewhere demands empirical probes | low | **Accepted, fixed** — the claim is removed from this spec (Design section above); the addition is now recorded honestly as defense-in-depth, not a response to a measured failure |

- **Confidence-pattern check (code-review cascade):** 4 review passes (internal
  spec-compliance x2, code-reviewer, external code review, doubt-reviewer), 13
  findings total (0 high, 6 medium, 7 low/low-medium), 11 fixed directly, 1
  deferred to its own triage card with an explicit reason, 1 rejected with a
  verified reason. No finding repeated across passes; the doubt pass — the one
  stage explicitly biased to disprove rather than confirm — still surfaced 2
  genuine medium-severity gaps (a live crash, a vacuous assertion) that three
  prior passes missed, which is itself the strongest evidence this stage
  earned its place on a `cross_component` + canonical-lock change.
