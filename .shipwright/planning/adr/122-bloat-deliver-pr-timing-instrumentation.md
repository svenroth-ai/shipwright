# ADR-122: Bloat exception — `shared/scripts/tools/deliver_pr.py` raised to 317-LOC

- **Status:** accepted
- **Date:** 2026-08-04
- **Re-Review-Date:** 2026-11-04 _(check whether the timing instrumentation
  has since been folded into a leaner shape, or whether the ladder itself
  has grown further and warrants a real split)_
- **Incident Reference:** iterate-2026-08-04-iterate-timing-attribution —
  the F11 delivery-ladder timing instrumentation (`delivery`/`delivery_wait`/
  `ci_wait` producer spans) first pushed this file past 300 lines.

## Context

`deliver_pr.py` (260 → 317, +57) is the F11 capability ladder: arm → watch →
self-merge, with the identity/refusal/terminal-state guards around it. This
iterate added `record_timing` (default off) so the real CLI path can
self-record its own `delivery`/`delivery_wait`/`ci_wait` producer spans —
measurement only, no change to the ladder's decisions. 45 lines of the
instrumentation (the span-wrapping helpers) were already split out into a
new `shared/scripts/lib/deliver_pr_timing.py` (unconstrained, no baseline
entry) during this same iterate specifically to minimize this file's growth;
what remains is the wiring at the two call sites (`deliver()`'s wrap, and
the `self_merge()` call site) plus the `main()` opt-in.

## Ousterhout Argument

`deliver()` is a deep module: one narrow public entry point
(`deliver(pr_url, ..., record_timing=False) -> dict`) hiding the ladder's
three-rung decision logic (arm outcome classification, identity refusal,
terminal-state short-circuit, host-watch vs. self-merge dispatch) — genuinely
substantial behavior behind a small interface. A further split (e.g. moving
the rung-selection logic to yet another file) would expose that internal
sequencing as a public seam between two files for a change neither concern
needs to know about, trading a 17-line overage for a shallower module.

## YAGNI Check

Every added line is load-bearing: the `record_timing` parameter and its
default (existing test suite untouched), the `instrument_watch` wrap
(rung 2), the `delivery`/`delivery_wait` self-recording (removes a fragile
cross-component agent-mark dependency an external plan review flagged), and
the `_call_self_merge`/`timed_self_merge_call` wrap (rung 3). Nothing here is
speculative — every line is exercised by a test in
`shared/tests/test_deliver_pr_timing.py`.

## Chesterton-Fence Check

The file's existing shape (one `deliver()` entry point, `Host`/`watch`
seams fully injected for testability) was itself the subject of a prior
design (iterate-2026-07-31-f11-delivery-truth, cited in the module
docstring) — "no member can be half-faked" is a documented invariant.
Splitting the ladder logic out from `deliver()` to chase line count would
cut across that invariant for no functional gain.

## Decision

Raise `shared/scripts/tools/deliver_pr.py` to `current: 317`
(`state: exception`, `adr: ADR-122`). Retire this exception at the
Re-Review-Date if the file has not grown further; if it has, re-evaluate
whether the ladder's three rungs (arm / host-watch / self-merge) now
warrant their own module.

## Consequences

Nobody else operates against this limit directly — it is a solo-owned CLI
tool with `deliver()`/`summary()`/`main()` as its only public surface,
consumed by F11's SKILL step and this iterate's own test suite (both
already updated). If the exception holds past Re-Review-Date, the cost is
purely readability of one already-deep module, not a compounding one.

## Rejected alternatives

- **Leave it at 260 and revert the timing instrumentation.** Rejected —
  that is the card's own deliverable; declining it defeats the point.
- **Split rung 2 (host-watch) and rung 3 (self-merge) dispatch into a
  separate `deliver_pr_rungs.py`.** Rejected per the Ousterhout argument
  above — the three rungs share the same `steps`/`outcome` state machine
  and splitting them exposes that internal sequencing as a cross-file
  contract for a change (measurement) that touches neither rung's own
  decision logic.
- **Reindent the whole ladder body into a nested closure inside `deliver()`
  to avoid a second parameter list.** Attempted first; rejected as
  needlessly higher-risk (a ~120-line mechanical reindentation of
  already-reviewed, spec-reviewer-approved logic) for a marginal line
  count difference against the same net file size.

## Addendum 2026-08-04 (code review)

317 → 322 (+5): code review found the ladder's original `watch` wrapping
was applied unconditionally, so `self_merge()`'s own internal retry loop
(rung 3) each recorded its own `ci_wait` on top of the outer one — a real
data-integrity bug (duplicated, mislabeled spans), not a size issue, but
the fix (move the `instrument_watch` wrap to the exact rung-2 call site
instead of the top of `deliver()`) added 5 net lines. `current` raised to
322 in the same commit.

## Addendum 2026-08-08 (F11 pointer retirement, trg-276994a4)

322 → 325 (+3): F11 was made to retire this run's `.shipwright/iterate_active/`
pointer once `deliver()` confirms a DELIVERED exit, closing trg-276994a4 (a
retained post-merge worktree kept the pointer resolving a finished run's id
for the rest of the session). The three lines are the import of
`lib.run_pointer_retirement.retire_run_pointer_best_effort` (a new,
unconstrained module — see its own docstring for why it isn't folded into
`worktree_isolation.py` or here) and the two-line `if exit_code ==
EXIT_DELIVERED: retire_run_pointer_best_effort(...)` guard in `main()`. An
earlier version of this call also carried a `--session-id` CLI argument
(+1 more line); Stage-2 code review found it made the whole fix a silent
no-op whenever `$SHIPWRIGHT_SESSION_ID` did not reach the delivery
subprocess's environment, so retirement was redesigned to key on `--run-id`
(already a required argument) instead, which removed the flag entirely.
`current` raised to 325 in the same commit.

## Addendum 2026-08-08 (deliver_pr.py double-resolve, code review)

325 → 326 (+1): Stage-2 code review found `Path(args.project_root).resolve()`
computed twice in `main()` — once for `deliver()`, once for the pointer
retirement call above — with an unrelated blank line dropped in the prior
addendum to buy back a line against this same ceiling (the "cap at current =
zero headroom forces design" pathology, previously observed elsewhere in this
file). Fixed by binding `project_root` once and passing it to both call
sites; net effect is +1 line because the new binding line costs more than the
one deleted duplicate call saves. `current` raised to 326 in the same commit.

## Addendum 2026-08-10 (P2.59, branch-feedback authority)

326 → 331 (+5): `main()` now spawns the merge-authority lifecycle compliance
audit (`audit_compliance_lifecycle.py --scope merge`) once `deliver()`
confirms a DELIVERED exit — the point at which merge authority may first
converge the global compliance backlog (see `docs/hooks-and-pipeline.md`'s
"Compliance backlog lifecycle authority"). Following this file's own
established pattern (Addendum 2026-08-08), the subprocess call itself was
extracted whole into a new, unconstrained `lib/deliver_pr_compliance_audit.py`
(`run_merge_compliance_audit`, mirroring `lib.run_pointer_retirement`'s
shape) rather than inlined — what remains here is one import line and the
three-line `if exit_code == EXIT_DELIVERED: result["merge_compliance_audit"]
= run_merge_compliance_audit(...)` call site. `current` raised to 331 in the
same commit.
