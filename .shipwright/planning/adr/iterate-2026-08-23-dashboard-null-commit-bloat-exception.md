# Bloat exception — `update_build_dashboard.py` raised to 548-LOC, `test_build_dashboard.py` raised to 760-LOC

- **Status:** accepted
- **Date:** 2026-08-23
- **Re-Review-Date:** 2026-11-23
- **Incident Reference:** iterate `iterate-2026-08-23-dashboard-null-commit`.
  `update_build_dashboard.py`'s `_generate_from_events` crashed with
  `TypeError: 'NoneType' object is not subscriptable` on a `work_completed`
  event carrying explicit `"commit": null` — `dict.get(key, default)` only
  substitutes on a *missing* key, not a present-but-`null` value. Observed
  in the adopted project leadwright; the crash is silent
  (`finalize_iterate.py`'s F5b call is best-effort) and permanent (the
  same historical event re-raises on every later run).

## Context

Both files already carry a bloat exception under ADR-124:
`update_build_dashboard.py` at 531 (measured 534 at this iterate's start —
ADR-124's own number and the baseline's recorded `current` had drifted
apart by a few lines from unrelated intervening changes; not a defect this
ADR needs to resolve, since it only raises the ceiling further) and
`test_build_dashboard.py` at 632, for nine regression cases covering a
different tolerance gap (WebUI's string-shaped `iterate_latest` layers).

This iterate crosses `test_build_dashboard.py`'s ceiling to 760 (+128 from
632) for seven new regression cases in a new `TestNullCommit` class:
`commit: null` at each of the two `_generate_from_events` call sites
(Recent Changes, Build History); `commit: ""` (the normal F5b pre-commit
state — 471/543 real events in this repo's own `shipwright_events.jsonl`
— proven by an empirical count run during Confidence Calibration) pinned
as *unchanged*, because the first fix attempt (`or "—"`) silently broke
it and was caught by external review before it shipped; null-tolerance
for the five sibling fields (`ts`, `tests`, `review`, `affected_frs`,
`description`) the same function reads from the same untrusted event
dicts, raised by Internal Plan Review after it showed the "no producer
writes null for this field today" argument was the same reasoning that
had just failed for `commit`; one case for `_test_status_from_iterate`'s
flat-fallback branch (`tests: null` with no `shipwright_test_results.json`
on disk) — a separate function missed by the sibling-field pass, caught
by the Stage-1 spec-reviewer HARD-GATE, which rejected the diff for the
resulting reachable `AttributeError`; and one case for `split: null` in
the Build History section, caught by the Stage-2 code-reviewer — not
merely a `None`-key rendering artifact but a real double-render defect
(the config-merge dedup at that call site looks for `"default"` and
never finds the `None`-keyed group, so the same section was appended
twice under two different headings).

`update_build_dashboard.py` itself also now crosses its own ceiling, to
548 (+14 from 534), for the code-review response: a new module-level
`_cell_or_dash()` helper (documents, in one place, the single subtlest
rule in this diff — `commit` and its four display-text siblings need an
explicit `is None` guard, not `or`, because an empty string is a real,
common, and meaningfully different value) plus the `split` guard.

## Ousterhout Argument

`update_build_dashboard.py` remains the deep renderer ADR-111 and
ADR-124 already argued for: one public entrypoint (`generate_dashboard`)
behind event-mode and config-mode table generation. `_cell_or_dash()` is
the one new symbol this iterate adds — private, four lines, called from
seven sites across two functions — and exists specifically to stop the
same misjudgment (an `or`-default silently reformatting a legitimate
empty-string row) from recurring at an eighth site later, which is
exactly the failure mode the Stage-2 review caught spreading across four
call sites in this diff's own first draft. Extracting it further (into a
shared module) would export an invariant — "commit-like fields need
`is None`, not truthiness" — that has no reason to be public; nothing
else in the repo renders this specific event shape.

`test_build_dashboard.py` is a test file: the honest comparison, per
ADR-124's own framing, is not against 300 lines but against shipping a
null-tolerance fix with no regression coverage for the exact class of
input (foreign/adopted event JSON) that caused the reported crash. Each
of the seven new cases pins one distinct behavior named in the iterate
spec's Test Completeness Ledger; none are incidental padding — each was
added because a previous version of the fix (an earlier draft in this
same iterate, or a gap named by one of four review passes) would have
shipped without it.

## YAGNI Check

- **`test_recent_changes_null_commit_does_not_raise` /
  `test_build_history_null_commit_does_not_raise`** — needed today; these
  are the reported crash's exact reproduction, at both call sites named
  in the bug report.
- **`test_recent_changes_empty_commit_still_renders_empty`** — needed
  today, not speculative: it is the test that caught a real defect in
  this iterate's own first fix attempt before it shipped (the external
  reviewer deepseek and an empirical event-log count both flagged the
  same regression independently). Deleting it would remove the only
  evidence that `commit: ""` renders correctly, which is the majority
  case in this repo's own event log.
- **`test_sibling_null_fields_do_not_raise` /
  `test_build_history_sibling_null_fields_do_not_raise`** — needed today;
  Internal Plan Review (opus-plan-reviewer, severity: medium) named six
  concrete crash sites for five sibling fields, all reachable from the
  same foreign-event trust boundary that produced the reported bug. Two
  consolidated tests (one per call site, all five fields per test) cover
  all six named sites without one test per field.
- **`test_test_status_flat_fallback_null_tests_does_not_raise`** — needed
  today; the Stage-1 spec-reviewer HARD-GATE rejected the first diff for
  a reachable `AttributeError` in `_test_status_from_iterate`'s
  flat-fallback branch, not covered by the two sibling-field tests above
  (those force `use_iterate=False` via `ts: None`). Carries a positive
  assertion alongside the negative one (Stage-2 code review: a bare
  "the section is absent" check also passes if the whole render silently
  broke) proving the render still succeeded.
- **`test_build_history_null_split_does_not_duplicate_section`** — needed
  today; Stage-2 code review found `split: null` was the one remaining
  top-level field left unguarded, and traced a concrete correctness bug
  beyond the crash class (double-rendered section under two headings,
  inflated `total_entries`), not just a cosmetic `### None`.
- **Refused as speculative:** hardening `generate_session_handoff.py`'s
  own `.get(...)[:n]` sites (a different file, different function, same
  general shape) — no test added there and no line added to the
  exception; disclosed in the iterate spec's Out of Scope, not folded in.
- **Refused as speculative:** nested-null tolerance (e.g.
  `"tests": {"total": null}` rather than `"tests": null`) — Stage-2 code
  review confirmed the top-level-only scope is defensible (matches what
  was actually observed in production) but flagged it was undisclosed;
  disclosed in the iterate spec's Out of Scope and this ADR's Known
  Limitations instead of widened.

## Chesterton-Fence Check

`update_build_dashboard.py`'s ceiling stands for the reason ADR-111 and
ADR-124 established: a deep renderer whose skip-arithmetic was already
extracted to a shared SSOT, leaving call-site residue behind the ceiling.
This change adds a third call-site residual (null tolerance, after
ADR-111's skip-tracking and ADR-124's string-shape tolerance) behind the
same narrow interface — it does not reintroduce logic that was
previously extracted.

`test_build_dashboard.py`'s ceiling stands for the documented reason in
ADR-124: it grows one focused test class at a time as the renderer gains
tolerance for a new input shape. This change continues that exact
pattern — one more class, `TestNullCommit`, for one more concretely
demonstrated input shape (explicit JSON `null`, at eight sites across two
functions, reachable from a foreign/adopted event log).

## Decision

New `current` values: `update_build_dashboard.py` → 548 (was 534, under
ADR-124's lineage); `test_build_dashboard.py` → 760 (was 632, under
ADR-124's lineage). Re-Review-Date 2026-11-23 — by then, if either file
has accumulated further per-shape tolerance residue past these ceilings,
evaluate whether the event-mode and config-mode table generators
(`update_build_dashboard.py`, already flagged for this at ADR-111) and
the event-mode test classes (`test_build_dashboard.py`, flagged at
ADR-124) are due to split — this iterate's own experience (three
independent review passes each finding one more unguarded site) is
further evidence for that split, not a reason to do it now under time
pressure from a live bug fix.

## Consequences

No downstream consumer contract changes — `generate_dashboard`'s output
shape is unchanged for every input this repo's own event log actually
contains (0 null-commit events at any of the eight guarded fields; the
fix only changes behavior for an input class — explicit null — that
previously crashed rather than rendered something). Future contributors
to either file inherit the new ceilings; a further crossing without
justification is blocked by the anti-ratchet hook as before.

**Known Limitations (disclosed, not fixed, this iterate):**
- Nested-null tolerance (a field present as a non-null container whose
  own sub-fields are null, e.g. `"tests": {"total": null}`, or a
  wrong-typed top-level value, e.g. `"commit": 123`) is not covered.
  Three concrete sites remain reachable with the same silent-permanent-
  stall failure mode: `_test_status_from_iterate:335`
  (`tests.get("total", 0) > 0` on a dict with `total: null`),
  `_generate_from_events` Test Status test_runs branch
  (`e2e.get("total", 0) - e2e.get("passed", 0)` on a null total), and the
  two `commit`-slicing sites on a non-string, non-null `commit` value.
- The underlying architecture that let this bug become *permanent* is
  unchanged: `finalize_iterate.py`'s F5b step swallows any exception to
  a log line with no gated signal, and the F11 verifier
  `check_build_dashboard_has_run_id` (C2) SKIPs whenever an F5c per-run
  entry exists (the normal case), so a crashed F5b step is caught by
  nothing. See the iterate spec's `## Internal Plan Review` for the
  scoping decision (disclosed, not fixed — a materially larger,
  separately-scoped change).

## Rejected alternatives

- **Just leave the ceilings and split the files now** — rejected:
  splitting mid-iterate, under time pressure from a live bug fix with
  four independent review passes already run, risks introducing exactly
  the kind of unreviewed structural change the review cascade exists to
  catch. The Re-Review-Date above schedules the split as deliberate,
  reviewed work instead.
- **Cut the sibling-field / split-field test coverage to stay under the
  old ceilings** — rejected: this is the same trade ADR-124 already
  rejected for a different gap — shipping the fix with no regression
  coverage for a failure mode a review pass specifically named would
  leave testable-but-untested behaviors in the Test Completeness Ledger,
  which fails the F11 gate.
- **One test per sibling/split field instead of consolidated tests** —
  rejected: one test per field (up to twelve) would cross both ceilings
  further for the same coverage the consolidated tests already provide;
  each consolidated test still fails at the first unguarded field if any
  guard regresses, which is the property the coverage exists for.
- **Extract `_cell_or_dash()` into a shared module instead of keeping it
  local to `update_build_dashboard.py`** — rejected (Ousterhout Argument
  above): nothing else in the repo renders this event shape, so
  "shared" would be speculative; ADR-111 already extracted the one piece
  of genuinely shared logic (`tests_block.py`) that had a second
  consumer.
