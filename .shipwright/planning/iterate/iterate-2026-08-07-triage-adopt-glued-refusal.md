# Iterate: name the escape and the shape in the adoption gate's glued-line refusal

- **Run ID:** `iterate-2026-08-07-triage-adopt-glued-refusal`
- **Card:** P2.19h, numbered 2026-08-06. Residual of P2.19b
  (`iterate-2026-08-06-triage-validate-deadends`), found by that run's own
  Stage-3 doubt review and deliberately left out of its scope. Blocked on
  P2.19b, which shipped and merged first (its AC14 fixed the sibling
  PROTECTION parser).
- **Intent:** CHANGE (behavior refinement of an existing internal gate) ·
  **Complexity:** small (`classify_complexity.py`: `touches_io_boundary`,
  history prior `small`, no `cross_split`)
- **Spec Impact:** NONE — internal delivery-path behavior only; no FR surface
  change.
- **Status:** implemented — all acceptance criteria met (see Test
  Completeness Ledger); full review cascade (self, plan, spec, code ×2,
  doubt) complete; F0 green (18/18 units, 100% diff coverage).

## Problem

`sweep_drift.py`'s `plan_main_tracked_drift` adopts main's *tracked*
`triage.jsonl` drift line-by-line, moving each line VERBATIM into the outbox.
Its gate, `_is_producer_event` (in `sweep_drift_events.py`), still runs one
`json.loads` on the whole physical line. `append_ids_of` — the sibling
PROTECTION-side parser in the same module — no longer does this: P2.19b/AC14
converted it to record-boundary recovery via `lib.jsonl_records.split_records`,
because failing there DESTROYS an operator's dismiss (a status is read as an
orphan and quarantined).

The two parsers now disagree on the exact same bytes. An UNCOMMITTED line in
main's tracked drift window that glues two records onto one physical line —
the documented "unterminated predecessor write" shape `lib.jsonl_records`
exists to name — is judged "not a triage producer event" by the gate. Since
the gate is unconditional (the *first* unparseable drift line refuses the
*entire* plan), `plan_main_tracked_drift` returns `refused` with
`main_tracked_unparseable`, and the sweep delivers nothing that run: not just
the glued line, every other pending append and dismiss in the outbox strands
with it.

**Confirmed empirically (Probe P1, below) before any code was written.**

This is a stall, not data loss: nothing is mutated (the plan-then-commit split
guarantees that), nothing already delivered is lost, and the sweep retries the
same drift every run — so a later manual repair heals it. But it is the same
"one bad line strands the whole buffer" class P2.19b's own title names, and
the refusal text does not name `triage_repair.py` — the tool that exists
specifically to split a glued line on disk — so an operator hitting this has
no escape hatch without reading the source.

## The shape of the fix

AC14 already recorded the right boundary for this: *"Adoption stays
line-granular and conservative — `_is_producer_event` still refuses to MOVE a
glued line rather than re-serializing it."* Adoption moves a drift line
**verbatim**, one physical line at a time (`commit_main_tracked_drift`
buffers `plan.fresh` lines as-is, then restores the tracked file via
`git checkout --`). Recovering the glued line's records and moving them as
*separate* records would mean re-serializing — writing bytes to the outbox
that never existed on disk in that form — which is a correctness risk this
run does not need to take to fix the actual defect (an unescapable refusal
message). So this residual does **not** widen what the gate is willing to
move, mirroring P2.19b's own precedent rather than re-deciding it:

- The first candidate from the card ("recognise it, refuse to move it, and
  say why") is the one implemented: `_is_glued_producer_line` (new leaf
  predicate in `sweep_drift_events.py`, same module and same
  `split_records`-without-`is_record` technique `append_ids_of` uses — the
  documented cause is two otherwise-complete records glued with no
  separating newline, which decodes forward with no backward resync needed).
  When the gate's existing `_is_producer_event` check fails on a drift line,
  `plan_main_tracked_drift` now asks this predicate before composing the
  refusal. If it recognises a producer event glued to other content, the
  plan still refuses — nothing about *what* is adopted changes — but the
  reason is the new `main_tracked_glued_line`, distinct from genuine
  corruption.
- The second half of the card ("name `triage_repair.py`") is folded in for
  **both** refusal reasons — the new `main_tracked_glued_line` and the
  pre-existing `main_tracked_unparseable` — since a genuinely corrupt line is
  exactly as escapable-in-principle (report mode costs nothing) as a glued
  one, and the card asked for it "at minimum" even if the first fix landed.

### Why line-granularity does not change the answer

The card asks explicitly whether adoption's line-granularity changes the
calculus here, since `_is_glued_producer_line` recognises exactly the shape
`append_ids_of` recovers. It does not, for the reason AC14 already gave: the
two parsers answer *different* questions. `append_ids_of` builds a read-only
**membership test** ("is this id already known") — adding an id to that
universe can only *prevent* a wrongful quarantine, never cause one, so
recovering it eagerly is monotonically safe. The adoption gate decides what
physical bytes get **moved and rewritten downstream** — recovering a glued
line's records and moving them separately would write bytes to the
git-tracked outbox that never existed verbatim on the tracked log, the exact
kind of silent rewrite `plan_main_tracked_drift`'s docstring says the whole
plan-then-commit split exists to avoid ("mutating first would... leaving
main's `git status` clean while the only copy of that data sits in a file
`git clean -x` deletes"). Recognising-without-moving keeps that guarantee
while still escaping the operator from an unexplained stall.

### Alternative considered and rejected

Recover and re-serialize the glued line's records into the outbox (mirroring
`append_ids_of` fully, not just its parsing technique). Rejected: it would
make adoption re-serialize bytes for the first time in this module's history,
diverging from every other guarantee in `sweep_drift.py` ("Lines that were
already fine are re-emitted BYTE-FOR-BYTE" is `triage_repair.py`'s own stated
invariant, not adoption's) and risking exactly the "verbatim comparison"
regressions `test_a_whitespace_only_edit_to_a_head_line_is_not_append_only`
exists to catch, for a defect whose actual severity is a stall (self-healing
on every retry), not data loss.

## Acceptance Criteria

- **AC1** (met) — A drift line that glues two well-formed producer events onto one
  physical line (no separating newline) is refused, not adopted: nothing is
  moved, the tracked log is untouched, the outbox is never created.
- **AC2** (met) — That refusal's reason starts with `main_tracked_glued_line`,
  distinct from `main_tracked_unparseable`, and names `triage_repair.py` with
  the placeholder `--project-root <root>` — never a literal `.`, since
  `main_root` is not the caller's cwd (see "Folded in from review" below).
- **AC3** (met) — A genuinely unparseable drift line (no producer event
  recoverable at all) keeps its existing `main_tracked_unparseable` reason
  and behavior, but now also names `triage_repair.py` the same way.
- **AC4** (met) — A clean, single producer-event drift line is unaffected: still
  adopted normally (`_is_glued_producer_line` never fires on it).
- **AC5** (met) — Directionally: whatever `append_ids_of` recovers from a glued
  line, `_is_glued_producer_line` also recognises as "glued", not "corrupt".
  Not symmetric — `append_ids_of` counts only `event=="append"`,
  `_is_glued_producer_line` accepts `append` or `status` — so this is
  pinned as a composition, not an equivalence.
- **AC6** (met) — A drift line whose damage is a truncated-JSON PREFIX glued to a
  complete producer event (the shape `lib.jsonl_records` itself calls the
  primary corruption cause, not only the two-complete-records case AC14
  fixed) is also recognised as `main_tracked_glued_line`, via backward
  resync — not silently misclassified as `main_tracked_unparseable`.

## Folded in from review

**Internal Opus plan review** (spawned per this run's explicit instruction,
before the external call) found three real defects in the first
implementation, all fixed before external review:

1. **HIGH — wrong tree named.** The first draft's hint hardcoded
   `--project-root .`. `plan_main_tracked_drift` operates on `main_root`,
   which this module's own `_head_lines` docstring says is deliberately NOT
   the caller's cwd (main's branch tip, not the iterate worktree's). An
   operator copy-pasting the hint from a worktree would repair the wrong
   log. Fixed by matching the two sibling call sites'
   (`sweep_quarantine.py`, `triage_validate.py`) existing convention: the
   literal placeholder `--project-root <root>`, which those two already use
   for exactly this reason. Pinned by AC2/AC3 and a reason-string assertion
   in both new tests.
2. **MEDIUM — narrower coverage than the card's own description.**
   `lib.jsonl_records`'s docstring names a damaged PREFIX (a truncated write
   appended onto) the *primary* corruption shape it exists to recover — not
   only the two-complete-records-glued case AC14 fixed. The first draft
   called `split_records` with no `is_record`, so it inherited
   `append_ids_of`'s narrower coverage without inheriting
   `append_ids_of`'s justification for it (a read-only membership test,
   where widening is monotonically safe either way). Here a missed
   truncated-prefix case would silently reproduce the exact unescapable
   stall this run exists to remove, while a false positive costs only
   message precision (adoption refuses regardless). Fixed: passes
   `is_record` to enable backward resync, bounded by the same
   `_MAX_RESYNC_ATTEMPTS` every other caller uses. `append_ids_of` itself is
   deliberately left untouched — its own coverage is P2.19b/AC14's decision,
   not this card's to revisit. Pinned by AC6.
3. **MEDIUM — AC5 was asserted, not exercised.** The original ledger mapped
   AC5 onto a test that never called `append_ids_of` at all. Fixed with a
   dedicated composition test, and AC5's wording corrected to state the
   guarantee is directional (not a false claim of parsing-technique parity).

Two low-severity findings were reviewed and intentionally left unchanged:
`_is_glued_producer_line`'s leading underscore despite being re-exported
cross-module matches the pre-existing convention already used for
`_is_producer_event`, `_is_header`, and `_parsed` in the same import block —
not a pattern this diff introduces or should unilaterally fix. Re-running
`_is_producer_event` inside `_is_glued_producer_line` on a line the caller
already knows fails it is deliberate: a pure leaf predicate should not trust
its caller's precondition.

**External plan review** (`--mode iterate`, GPT + DeepSeek): DeepSeek
`approve`, no findings. GPT `revise`, four findings, folded in:

1. **Medium — two independent copies of "is this a producer event" shape.**
   `_looks_like_producer_record` duplicated `_is_producer_event`'s inline
   check, risking drift if `_EVENTS` or the id contract changes later and
   only one copy is updated. Fixed: `_is_producer_event` now delegates to
   `_looks_like_producer_record` — one definition, shared by the clean-event
   check and the resync predicate.
2. **Low — "glued" doesn't promise the rest of the line is clean.** A valid
   record followed by unrelated garbage also returns `True` from
   `_is_glued_producer_line`. Intentional (the label means "a producer
   record is recoverable here", not "this line is otherwise benign" — the
   garbage is exactly what `triage_repair.py` quarantines), but undocumented
   and untested. Fixed: docstring states it explicitly; new test
   `test_is_glued_producer_line_fires_on_a_record_followed_by_unrelated_garbage`.
3. **Low — AC5's composition test used only one shape.** Parametrized over
   append+append and append+status.
4. **Low — the resync bound's provenance.** No code change: `split_records`
   bounds `_resync` internally regardless of caller, so no call site can
   introduce unbounded scanning; already stated in the docstring.

**Stage-2 code review** (`shipwright-build:code-reviewer`, `model=opus`),
five findings, all resolved:

1. **Documentation, not a functional swap — the stricter predicate exists,
   deliberately not reused here.** The reviewer asked why
   `_looks_like_producer_record` doesn't just call
   `lib.triage_integrity.is_triage_record`, the triage store's own hardened
   v3 shape predicate. That predicate requires every key a real writer always
   emits per event kind — hardened specifically because `triage_repair.py`
   *writes* recovered objects back to disk, so under-rejecting there is a
   forged-record injection risk. Nothing in this module writes anything:
   `_looks_like_producer_record` only selects the wording of a refusal
   message, so it deliberately keeps the looser, pre-existing shape
   `_is_producer_event` already used rather than adopting the stricter one —
   which would also require reworking the shared `_sweep_helpers.py` fixtures
   several unrelated test modules depend on (`item()` omits `source`/
   `severity`/`kind`, `status()` omits `by`), out of proportion to what this
   predicate's blast radius needs. Fixed by documenting the distinction and
   the reasoning directly on `_looks_like_producer_record`, not by changing
   its behavior.
2. **Duplication across three test files.** `outbox()`, `write_tracked()`,
   and the `seeded` fixture were each defined inline in the new test module,
   overlapping what `test_sweep_drift_guards.py` and
   `test_sweep_drift_commit.py` already define. Fixed: extracted into
   `_sweep_helpers.py` (the shared, non-collected plumbing module the sweep
   test suite already uses for exactly this purpose) and imported instead of
   duplicated in the new file; the two pre-existing modules keep their own
   copies for now (de-duplicating pre-existing code is a separate, boy-scout
   change, not this card's).
3. **Line-length / readability under LOC pressure.** The inline hint
   composition inside `plan_main_tracked_drift`'s validation loop had grown
   hard to read while chasing the 300-LOC guideline. Fixed: extracted
   `_REPAIR_HINT` (module constant) and `_bad_drift_reason()` (helper
   function) — the branch reads as two named cases instead of an inline
   if/else, and the extraction bought back the LOC room the readability fix
   spent.
4. **Missing test case: a decodable-but-non-record line is not glued.**
   `_is_glued_producer_line` was tested against corruption (`"{ BROKEN"`) and
   a clean event, but not against a line that decodes fine yet carries no
   recognisable producer shape at all (e.g. `{"foo":1}`) — the case that
   proves the predicate checks *shape*, not just "did `json.loads` succeed".
   Fixed: added to
   `test_is_glued_producer_line_distinguishes_glue_from_corruption_and_from_clean`.
5. **`--writers-quiesced` should be named literally in the hint, not just
   implied.** Folded into the same `_REPAIR_HINT` extraction (finding 3): the
   constant now spells out `--apply --writers-quiesced` explicitly, since
   `triage_repair.main` exits 2 on `--apply` without it — the hint should not
   make the operator discover that the hard way.

**Stage-2 confirming pass** (same reviewer role, re-review after the 5 fixes
above): **APPROVE**, all 5 confirmed landed correctly, plus 7 new low-severity
notes. Six addressed in this diff:

1. Ledger row 8's evidence cell named only the 5 directly-touched modules —
   extended to the full `sweep or reconcile or main_tree` sweep (230/230).
2. The predicate-swap docstring (finding 1 above) justified a production
   shape decision partly with test-fixture convenience, which both inverts
   the dependency direction and was already stale (this diff had just moved
   those fixtures) — trimmed to the durable write-path argument alone.
3. `_sweep_helpers.write_tracked` used `Path.write_text(encoding="utf-8")`,
   which raises on the lone-surrogate bytes this suite exists to model — the
   same trap `write_store_bytes` (in the same file) was written to avoid.
   Fixed: `write_tracked` now calls `write_store_bytes`.
4. `sweep_drift.py` sat at exactly 300 lines with zero headroom and two
   100+-column lines from the `_REPAIR_HINT`/`_bad_drift_reason` extraction —
   moved both into `sweep_drift_events.py` instead (the module `sweep_drift`'s
   own docstring already names as "what refusal rules are expressed in," with
   ~150 lines of headroom); `sweep_drift.py` is now 289 lines.
5. Two dangling bare `AC14` references (module docstring, `_bad_drift_reason`
   docstring) named no run id — both now cite
   `iterate-2026-08-06-triage-validate-deadends` explicitly, matching the rest
   of the module's citation style.
6. The new test module imported `_sweep_helpers` two ways (`as h` and named
   imports) when only the `seeded` fixture needs the bare form — narrowed to
   `from _sweep_helpers import seeded`, with `outbox`/`write_tracked` called
   as `h.outbox`/`h.write_tracked` like every other helper in the file.

One deferred, by the reviewer's own "non-blocking — current form works"
disposition: moving the `seeded` fixture from `_sweep_helpers.py` into
`shared/tests/conftest.py` (the repo's existing home for cross-module sweep
fixtures) to remove the two `# noqa: F811` this module's pytest-fixture-
import pattern requires. Left as a follow-up rather than folded in here — it
touches a shared fixture file several unrelated test modules depend on,
disproportionate to what this small-complexity card needs to fix.

Net effect of the confirming pass's fixes: `sweep_drift.py` 300→289 lines
(headroom restored), `sweep_drift_events.py` 139→154, all 230 tests in the
`sweep or reconcile or main_tree` sweep still pass, `ruff` clean.

**Stage-3 doubt review** (`shipwright-build:doubt-reviewer`, `model=opus`,
fresh-context, biased to disprove): could not disprove the core correctness
claim — the glued-recognition branch is provably unreachable from any
mutating path (traced, including on deliberate misuse of
`commit_main_tracked_drift`), the `_is_producer_event` refactor is
behaviour-identical, `_MAX_RESYNC_ATTEMPTS` is structurally enforced not just
asserted, AC5's directional claim is a theorem (backward resync is a
superset of forward-decode, so widening cannot make the label wrong relative
to `append_ids_of`), and no import cycle or reason-string consumer breaks.
Two medium doubts and one low, all fixed:

1. **Medium — the new hint sends the operator to rewrite main's tracked SSoT
   without naming the commit step.** `triage_repair.py --apply` rewrites
   `.shipwright/triage.jsonl` in place and never commits. An operator who
   runs it and stops leaves the working file byte-different from HEAD, so
   the *next* sweep hits `main_tracked_diverged` and delivers nothing —
   trading an escapable-but-confusing refusal for a worse, silent one. This
   repo already has a named precedent for the identical file
   (`lib.triage_gc_publish.DIVERGENCE_CONSEQUENCE`, written for `triage_gc
   --apply`'s own uncommitted-rewrite hazard). Fixed: `_REPAIR_HINT` now
   quotes that exact constant (imported, not restated, so the two remedies
   cannot drift apart) and tells the operator to commit the repaired log.
   Pinned by a new assertion in
   `test_a_glued_drift_line_refuses_but_names_the_repair_tool`.
2. **Medium — the sibling mutating path still reports the identical byte
   shape as unexplained corruption, and on a branch reported as SUCCESS.**
   `sweep_drift_restore._classify_salvage` classifies a late-landing line
   that fails `_is_producer_event` as `"unparseable"` regardless of shape;
   `restore_tracked_log` then returns `status="adopted"` (the sweep reports
   success) with `main_tracked_salvage_needs_review` and no remedy — worse
   than the plan-path stall this run fixes, because a success is easier to
   miss than a refusal, and the only surviving copy sits in a gitignored
   salvage file. The miniplan's R3 called this narrower and un-stalled;
   the doubt review showed the actual consequence is a silently-successful
   sweep with an unnamed fix. Fixed: `_classify_salvage` now returns the
   actual late lines on the unparseable path (previously discarded as `[]`,
   used only for this check — no behavior change), and
   `restore_tracked_log` composes `main_tracked_salvage_glued_line` +
   `_REPAIR_HINT` when any of them is glued, keeping
   `main_tracked_salvage_needs_review` for genuine corruption. Pinned by new
   test `test_a_glued_late_line_is_kept_but_names_the_repair_tool`.
3. **Low — the coverage claim overstated what backward resync recovers.**
   Composing the two shapes each already-passing test pins separately (a
   truncated prefix AND unrelated trailing garbage, or a prefix past the
   resync attempt cap) still falls back to `main_tracked_unparseable` — resync
   requires every object in a candidate run to satisfy the shape predicate.
   Message precision only (the hint is folded into both codes, so the escape
   hatch survives), but the docstring and this spec's Coverage bullet
   overstated completeness. Fixed: both corrected to state the bound
   honestly; no code change.

## Affected Boundaries

- **JSONL record boundary** (`lib.jsonl_records.split_records`) — read a
  second way in the same module that already reads it this way for
  `append_ids_of`; no change to `split_records` itself.
- **`DriftPlan.reason`** — a new value in the existing free-text `refused`
  reason string. No schema, no new field: every existing caller already
  treats `reason` as opaque prose (`.startswith(...)` in tests, printed
  verbatim to the operator).
- **`DriftResult.reason`** (Stage-3 doubt review) — the same free-text
  contract, widened by one more prose value (`main_tracked_salvage_glued_line`)
  on the salvage-restore path in `lib.sweep_drift_restore`. Same "opaque
  prose" treatment; no schema.
- **`lib.triage_gc_publish.DIVERGENCE_CONSEQUENCE`** (Stage-3 doubt review) —
  read (not written) by `sweep_drift_events._REPAIR_HINT`, a new one-directional
  dependency from the drift-adoption leaf module onto the GC-publish module.
  No cycle: `triage_gc_publish` imports only `churn_merge`, `git_base`, and
  `main_tree_guards`, none of which import anything in the `sweep_drift*`
  family.

## Confidence Calibration

- **Boundaries touched:** JSONL record boundary (read-only, in the adoption
  gate); the `DriftPlan.reason` string.
- **Empirical probes run:**
  - **P1** (reproduce the defect) — a working tree with `HEADER, seed-append,
    glued-line` (two well-formed appends, no separating newline) against
    `plan_main_tracked_drift` returned `status="refused"`,
    `reason="main_tracked_unparseable: drift line 1 is not a triage producer
    event"` — no mention of `triage_repair.py`. Confirms the exact stall the
    card describes.
  - **P2** (confirm the asymmetry) — on the identical glued bytes,
    `append_ids_of` recovered `{"trg-glued-a", "trg-glued-b"}` while
    `_is_producer_event` on the whole line returned `False`. This is the
    disagreement between the two parsers the fix removes for the refusal
    message, without removing it for adoption's line-granularity (by design,
    see "Why line-granularity does not change the answer").
  - **P3** (post-fix, pre-review) — same P1 setup against the first-draft
    fix: `status` unchanged (`"refused"`, still nothing mutated), `reason`
    now `"main_tracked_glued_line: ...; see \`uv run
    shared/scripts/tools/triage_repair.py --project-root .\` ..."` — this is
    the draft the internal Opus review caught (finding 1: wrong tree named).
  - **P4** (post-review) — same setup, final code: `reason` now names
    `--project-root <root>`, matching the sibling call sites. Re-run after
    every fix in this section; see the full suite result below.
- **Test Completeness Ledger:** see below.
- **Confidence-pattern check:**
  - *Asymptote (depth)* — one defect (an unescapable, misclassified refusal),
    fixed at its one call site (`plan_main_tracked_drift`'s validation loop);
    the internal Opus review's own second pass is the depth check here —
    it found the fix under-covered the shape `lib.jsonl_records` calls
    primary, which a shallower review would have missed since the first
    draft's own tests all passed.
  - *Coverage (breadth)* — the reachable shapes for a drift line that fails
    `_is_producer_event` are covered: glued-and-recognisable via two complete
    records (AC1/AC2), glued-and-recognisable via a truncated prefix (AC6),
    genuinely unparseable (AC3), and — by absence of any new branch —
    already-clean (AC4, unaffected). Not exhaustive of every composition:
    Stage-3 doubt review (low) found a truncated prefix glued to a valid
    record AND THEN unrelated non-record garbage still falls back to
    `main_tracked_unparseable` (resync requires every object in the
    recovered run to satisfy the shape predicate) — message precision only,
    since the hint is folded into both reason codes (AC3). Documented on
    `_is_glued_producer_line`'s docstring rather than chased further; no
    code change, since a wrong `False` there costs nothing this run needs
    to fix (the escape hatch still fires).
  - *Integration composition* — `cross_component` does not fire on this diff
    (`classify_complexity` found no `cross_split`; the touched files are not
    in `CROSS_COMPONENT_FILE_PATTERNS`). The existing integration coverage in
    `test_sweep_outbox_dispositions_integration.py` (`test_a_dismiss_survives_
    when_its_append_is_glued_on_local_main`) already exercises the real
    sweep over this exact glued-line shape end-to-end and continues to pass
    unmodified, confirming the refusal-message change does not alter delivery
    behavior.

## Test Completeness Ledger

| # | Behavior | Disposition | Evidence |
|---|---|---|---|
| 1 | A glued drift line (two complete records) refuses, mutates nothing, names `triage_repair.py --project-root <root>` (AC1, AC2) | tested | `test_sweep_drift_glued_refusal.py::test_a_glued_drift_line_refuses_but_names_the_repair_tool` |
| 2 | A genuinely unparseable drift line keeps `main_tracked_unparseable`, names `triage_repair.py --project-root <root>` (AC3) | tested | `test_sweep_drift_guards.py::test_malformed_drift_is_never_copied_into_the_outbox` (extended) |
| 3 | `_is_glued_producer_line` fires only on glue, never on a clean event, corruption, or a blank line (AC4, AC5) | tested | `test_sweep_drift_glued_refusal.py::test_is_glued_producer_line_distinguishes_glue_from_corruption_and_from_clean` |
| 4 | A truncated-prefix glue (backward resync) is also recognised as glued, not unparseable (AC6) | tested | `test_sweep_drift_glued_refusal.py::test_a_truncated_predecessor_glued_to_a_full_append_is_also_recognised` |
| 5 | `_is_glued_producer_line` agrees with `append_ids_of` on the same glued bytes, both append+append and append+status shapes (AC5, directional) | tested | `test_sweep_drift_glued_refusal.py::test_is_glued_producer_line_agrees_with_the_protection_universe[append+append,append+status]` |
| 6 | A recoverable record glued to unrelated garbage is still recognised as glued, not left undocumented (external review, GPT finding 2) | tested | `test_sweep_drift_glued_refusal.py::test_is_glued_producer_line_fires_on_a_record_followed_by_unrelated_garbage` |
| 7 | `_is_producer_event` and `_is_glued_producer_line` share one shape definition, not two that could drift (external review, GPT finding 1) | tested | covered by every test above continuing to pass post-refactor; no behavior change, just one definition instead of two |
| 8 | The full existing drift/adoption/sweep suite is unaffected by the message-only change | tested | `uv run pytest shared/tests -k "sweep or reconcile or main_tree or triage_gc"` — every module that calls `plan_main_tracked_drift`, `restore_tracked_log`, or the sweep/reconcile/main-tree/GC-publish families they compose with — 285/285 pass |
| 9 | A decodable line with no recognisable producer shape (e.g. `{"foo":1}`) is not glued (Stage-2 code review finding 4) | tested | `test_sweep_drift_glued_refusal.py::test_is_glued_producer_line_distinguishes_glue_from_corruption_and_from_clean` (extended) |
| 10 | The repair hint tells the operator to commit the repaired log, not just run the repair tool (Stage-3 doubt review, medium) | tested | `test_sweep_drift_glued_refusal.py::test_a_glued_drift_line_refuses_but_names_the_repair_tool` (extended, asserts `"commit"` in the reason) |
| 11 | A glued line that lands during the restore's residual window is preserved (not adopted) and its salvage reason names `triage_repair.py`, not left as unexplained corruption on a success-reported sweep (Stage-3 doubt review, medium) | tested | `test_sweep_drift_restore_faults.py::test_a_glued_late_line_is_kept_but_names_the_repair_tool` |
| 12 | Wording quality of the operator-facing hint text | untestable | `requires-manual-visual-judgment` — the exact prose is reviewed, not asserted; the *presence* of `triage_repair.py` and the correct placeholder are behaviors 1–2, 10 |

0 testable-but-untested.

## Architecture Updates

- No new route, component, schema, service, or convention. A refusal-reason
  string in an existing internal state machine gains one more value; recorded
  in the ADR, not `architecture.md`.
