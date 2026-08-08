# Run-id pointer lifecycle: retirement + stale-verdict re-audit

Run: `iterate-2026-08-07-run-id-lifecycle-fixes`. Bundles two follow-ups the
`iterate-2026-08-06-resolve-run-id-seam` change surfaced but did not itself
close: **trg-276994a4** (a retained post-merge worktree kept a finished run's
pointer resolvable) and **trg-b36fd844** (`already_audited` could freeze a
provisional verdict at its least-informed moment). `docs/hooks-and-pipeline.md`
("Two lifecycle follow-ups that seam surfaced, both fixed") carries the durable
behavioral contract; this file carries the review provenance and the
disposition of every finding that was NOT simply fixed.

## What shipped

- `shared/scripts/lib/run_pointer_retirement.py` (new): `retire_run_pointer`
  scans every pointer file under `.shipwright/iterate_active/` and unlinks
  every one whose own recorded `run_id` matches — keyed on `run_id` (a
  required CLI arg), not a session-derived filename. `deliver_pr.py` calls the
  best-effort wrapper on `EXIT_DELIVERED` and `EXIT_CLOSED`.
- `shared/scripts/lib/phase_quality/_staleness.py` (new): `is_stale_finding`
  — the single entry point `already_audited()` calls — treats a recorded
  finding as not-final when it is a hook-level error finding, or tagged
  `reason_code="unresolvable_run_id"` once `has_exact_iterate_entry` turns
  True.
- `shared/scripts/lib/phase_quality/_worktree_identity.py` (new): the
  gitdir-chain identity check (`is_worktree_of`) that makes the pointer-based
  worktree redirect (`pointer_worktree_root`, in `_run_id.py`) safe to trust —
  this is what closes the reachability gap (below) without accepting a
  spoofed `worktree_path`.
- `audit_phase_quality_on_stop.py`: resolves `(audit_root, via_pointer,
  plain_root)` via `resolve_project_roots`, renders aggregates at both roots
  when they differ, and treats a verified pointer redirect as an explicit
  root selection for the monorepo auto-descent guard.

## Review provenance

1. **Stage 1 spec-reviewer:** PASS — 1 non-gating note (a docstring date
   typo in `_resolution.py`, fixed).
2. **Internal Opus plan review** (operator-mandated, run before the external
   cascade, over an ad-hoc plan+spec pair since this run carries no
   iterate-spec at `small` complexity): verdict **PROCEED WITH CHANGES**.
   Load-bearing finding — the reachability gap below — folded in; the other
   findings (error-finding freeze, `EXIT_CLOSED` not covered, silent-failure
   observability, undocumented other pointer consumers) were fixed directly.
3. **External code-review cascade** (GPT + DeepSeek via OpenRouter,
   `external_review.py --mode code`), 3 rounds against the evolving diff:
   - **Round 1** — both providers verdict `revise`. Two genuine gaps fixed:
     a per-file stderr diagnostic on an individual unlink `OSError` (so one
     successful unlink in a multi-match scan cannot mask a sibling failure),
     and a `worktree_path`-presence check before treating a JSON file as a
     real pointer (so a stray non-pointer file sharing a `run_id` field
     cannot be deleted). Six further findings were rebutted with reasoning
     (infinite-loop claim verified false against the code; error-finding
     retry is intentional; best-effort-only retirement is the required
     shape; out-of-scope caller concerns; pre-fix findings not retroactively
     tagged is accepted, self-healing via GC).
   - **Round 2** — both providers verdict `revise` again, converging
     independently on the SAME single finding: the main-root/worktree
     reachability gap (below), which the internal Opus plan review had also
     flagged as load-bearing. With three independent mechanisms agreeing,
     it was fixed in-bundle instead of staying filed as a follow-up.
   - **Round 3** (final; recorded as this run's `external_code` review pass)
     — deepseek `approve`, openai `revise`. openai's four medium findings —
     retirement being best-effort/observable-not-durable, retirement wired
     only to `deliver_pr.py`'s two exits, unbounded error-finding retry, and
     the pointer-redirect trust surface — are addressed below
     (**accepted-with-reason**, not fixed) or were superseded by the internal
     Stage-2/3 re-review's own, stricter version of the same identity
     concern. No 4th external round was run against the diff produced by
     that internal re-review, given cost/time; the internal cascade (below)
     covers it instead.
4. **Internal Stage 2 code-reviewer** (opus, re-run fresh against the final
   diff after the round-3 external pass and the internal re-review that
   followed it): 12 findings — see disposition table.
5. **Internal Stage 3 doubt-reviewer** (opus, triggered by the irreversible
   `unlink()` and the worktree-identity trust surface): 8 doubts (D1-D8),
   verdict SHIP WITH FIXES — see disposition table.
6. **Self-review:** 8-item checklist, all pass.

## The reachability gap (rounds 2-3, superseding round 1's rebuttal)

Round 1 accepted deferring "root every phase-quality Stop audit at the run's
worktree" as a materially larger change than either fix here (filed as
`trg-f6c6112a`). Round 2 reversed that: both external providers AND the
internal Opus plan review independently concluded the re-audit trigger this
run's fix 2 depends on can only fire when `audit_root` resolves to the run's
own worktree (where F5c writes the ledger entry) — and a Stop-subprocess's
`cwd` is the MAIN repo even mid-iterate, so the pre-fix `plain
resolve_project_root()` chain rooted every audit at main, where the trigger
could never observe the entry appearing. Fixed in this bundle via
`pointer_worktree_root` + `is_worktree_of` (durable behavior documented in
`docs/hooks-and-pipeline.md`). `trg-f6c6112a` is dismissed as fixed, not
deferred.

## Disposition table — findings NOT simply fixed

| # | Source | Finding | Disposition |
|---|---|---|---|
| 1 | external round 3, openai | Retirement is best-effort; a failed unlink stays observable (stderr) but not durable — the pointer remains resolvable. | **Accepted-with-reason.** Durable failure-tracking (a resolver-checked tombstone, or a retry queue) is a materially larger design than either lifecycle fix; the stderr diagnostic already turns a silent no-op into an observable one, which was the operator-required fix shape per the doubt- and plan-reviewers. Filed as a residual, not a defect. |
| 2 | external round 3, openai | Retirement is wired only to `deliver_pr.py`'s two terminal exits; other run-ending paths (manual branch deletion, an alternate delivery command) leave the pointer live. | **Accepted-with-reason.** `deliver_pr.py` is this codebase's sole F11 delivery path; no alternate delivery command exists. A session-end sweep for orphaned pointers is a separate, larger mechanism than either fix here — noted as a possible future hardening, not built. |
| 3 | external round 3, openai | Treating every `source="error"` finding as stale creates an unbounded retry when the underlying hook failure is persistent (distinct from the provisional-SKIP loop, which IS bounded). | **Accepted-with-reason.** Intentional and bounded in the way that matters: each retry is one Stop-hook invocation (not a tight loop), and a persistently-failing hook already prints its own error every Stop regardless of this fix — the fix does not add invocations, it changes whether a stale error finding is silently trusted as final. A backoff/attempt-count mechanism is a genuine future improvement, not a defect blocking this bundle. |
| 4 | external round 3, openai | The pointer-based project-root redirect expands trust in pointer JSON; canonical-path containment and worktree-identity verification are required, not lexical prefix checks. | **Superseded, not merely accepted.** This is the same concern the internal Stage-2/3 re-review (below) found and fixed independently and more strictly: `is_worktree_of` verifies the full gitdir chain (forward `gitdir:` line AND git's own back-link), not a lexical `relative_to` containment check — closing both the container-spoofing case and the sibling-admin-dir case openai's round-3 note did not itself enumerate. |
| 5 | external round 3, openai | Requiring only `worktree_path` before unlinking is not a full pointer-identity check; a non-pointer JSON with both `run_id` and `worktree_path` would still be deleted. | **Accepted-with-reason.** Narrow and pre-existing (not introduced by this run): `.shipwright/iterate_active/` holds nothing but pointer files written by `write_run_pointer`; a hand-crafted or foreign file colliding on both field names is not a realistic operational shape. The round-1 fix (require `worktree_path` present) already closes the realistic case (a stray unrelated JSON). |
| 6 | external round 3, deepseek | The final full `shared/tests` suite result was "in flight" at review time, not yet confirmed against the reachability-redirect revision. | **Resolved by this session's own work**, not a design disposition: the full suite (8660 tests) has since run clean, and the diff-coverage gate (below) closed separately. |
| 7 | internal code-reviewer #2 | `resolve_project_roots(cwd, session_id)` honours `cwd` only for the pointer lookup; `plain_root` always reads the real process cwd via `resolve_project_root()`, ignoring the parameter. | **Rejected-with-reason.** The sole production caller (the Stop hook) always passes exactly `Path.cwd()` computed immediately before the call, so the divergence has no live path. Filed as a signature-cleanup follow-up, not a correctness fix. |
| 8 | internal code-reviewer #3 | `_resolution.py` re-implements `lib/project_root.py`'s env-read + validation verbatim instead of calling `project_root_was_explicitly_selected` after resolving `plain_root` first. | **Rejected-with-reason.** The suggested reordering touches call-order reasoning this session already reworked once (round-2 fix); duplicating ~5 lines was judged lower-risk than a second reorder this late in the run. Filed as a follow-up cleanup. |
| 9 | internal code-reviewer #4 | The terminal-exit retirement policy is documented in `run_pointer_retirement.py` but implemented as a bare tuple literal in `deliver_pr.py`, which pays the bloat cost without owning the reasoning. | **Rejected-with-reason.** `deliver_pr.py` is already at its ADR-122 bloat-exception ceiling with an addendum recorded for this run's own +4 lines (322→325); re-touching it for a 1-line net savings was judged not worth a second addendum this run. Filed as a follow-up. |
| 10 | internal code-reviewer #7 | `pointer_worktree_root` doesn't check `is_shipwright_project(worktree)`, contradicting a comment asserting it's inherently valid. | **Rejected-with-reason.** `_run_id.py` is at its 299-line bloat-gate ceiling (hard-blocks on any new crossing of 300). The gap is fail-safe as-is — an unguarded audit against a non-Shipwright worktree produces findings nobody reads, not a crash or security hole. Filed pending a docstring/bloat-budget pass. |
| 11 | internal code-reviewer #8 | The "pointer retirement did not complete" stderr warning fires on every routine no-pointer-exists delivery too, not only a genuine unlink failure — alarm-fatigue risk. | **Rejected-with-reason.** Distinguishing the two requires changing `retire_run_pointer`'s boolean return contract (covered by 9 existing tests) to a tri-state — a larger API change for a diagnostics-only concern. Deferred pending evidence the noise is actually confusing in practice. |
| 12 | internal code-reviewer #12 | `resolve_project_roots` runs the pointer resolution (a git subprocess) BEFORE the once-per-Stop claim, so all ~11 fan-out invocations pay the cost when `cwd` isn't the main checkout. | **Rejected-with-reason.** A call-order restructuring across the whole hook fan-out, correctness-neutral (performance only). Filed as a follow-up alongside the doubt-reviewer's independent D8 finding of the same issue. |
| 13 | internal doubt-reviewer D2 | Not retiring on `EXIT_NO_MERGER`/`EXIT_PENDING` was reasoned against the PRE-redirect consequence (a misattributed run_id string); post-redirect, a stale-but-live pointer misroutes every phase-quality finding write for the rest of the session, not just one string. | **Accepted-with-reason**, recorded in `run_pointer_retirement.py`'s own module docstring: the run is genuinely not over on those two exits, so retiring there would be premature, not defensive. |
| 14 | internal doubt-reviewer D3 | Anchoring the triage backlog write at `plain_root` avoids corrupting main's tracked backlog from a redirected run's mid-run state, but also means `plain_root`'s backlog reads main's LAST pre-redirect findings for the run's whole duration. | **Accepted-with-reason**, named explicitly in `resolve_project_roots`'s own docstring rather than left implicit: the trade-off is a known, bounded staleness window, not a defect. |
| 15 | internal doubt-reviewer D6 | The worktree-identity spoofing class (round 3) is closed in `phase_quality`'s own `pointer_worktree_root` only — `context_cost_session.resolve_active_project_root` and `iterate_stop_finalize._active_worktree_root` still use their own, looser checks against the same pointer field. | **Accepted-with-reason.** Scoped explicitly to `phase_quality` by this bundle; lifting `is_worktree_of` into a shared helper the other two consumers also call is a real follow-up, not folded in here to limit this run's surface. |
| 16 | internal doubt-reviewer D7 | `unlink()` was chosen over a `retired` flag with no recorded reasoning; a flag would be idempotent, reversible, and equally correct. | **Fixed** — a paragraph was added to `run_pointer_retirement.py`'s module docstring recording why `unlink` was kept (no per-file state to reconcile; a flag adds a write-then-read contract two consumers would each need to honor; the directory holds nothing but live-or-stale pointers with no other archival purpose). |
| 17 | internal doubt-reviewer D8 | `fast_main_root`'s zero-git fast path only short-circuits when `cwd/.git` is itself a directory; a cwd inside main falls through to a git subprocess on each of the ~11 Stop-hook fan-out invocations. | **Accepted-with-reason**, same residual as code-reviewer #12 above — filed as a follow-up rather than restructuring the hook's call order this late in the run. |

Findings fixed directly (not tabled above, since "fixed" needs no
disposition): D1 (back-link relative-path resolution bug in the round-3 fix
itself), D4 (silent exception-swallow in `is_stale_finding` — a stderr
diagnostic was added), code-reviewer #1 (the `relative_to` container/sibling
spoofing gap — the `is_worktree_of` two-part identity check), code-reviewer
#5/#6 (render-both-roots for the aggregate dashboard), code-reviewer #9
(`test_best_effort_swallows_errors` tested nothing — rewritten to force a
genuine raise), code-reviewer #10 (`fast_main_root` docstring contradicted
its own fail-safe behavior), code-reviewer #11 (this doc's provenance
trimmed out of `docs/hooks-and-pipeline.md` into this file).

## Diff-coverage gate closure (this session, after the review cascade above)

The F0 gate's diff-coverage check (`uvx diff-cover`, ≥80% of changed lines)
initially measured **74%** against the full suite run — every existing
Stop-hook test drives the real script via `subprocess.run` for genuine
end-to-end fidelity, which is invisible to the parent pytest process's own
coverage measurement (ADR-045). Closed file-by-file with direct unit/branch
tests, re-verified at **100%**:

- `_worktree_identity.py`, `_run_id.py`: new
  `shared/tests/test_worktree_identity_branches.py` (8 tests: unreadable
  `.git` file, non-UTF-8 back-link, missing back-link file, nonexistent
  admin dir, non-directory `.git`, a resolve-failure fallback) plus 5 new
  `pointer_worktree_root` branch tests appended to
  `test_pointer_worktree_root_identity.py` (blank `worktree_path`, gone
  worktree, a cwd one level inside main falling through to the git resolver,
  an unexpected-exception swallow, sentinel session).
- `_resolution.py`: one new test in `test_resolve_project_roots.py` forcing
  `resolve_project_root()` to raise (the multi-candidate monorepo case its
  own docstring names), proving the `plain_root = cwd` fallback.
- `_staleness.py`: two new tests appended to
  `test_already_audited_unresolvable_staleness.py` — a non-dict payload
  short-circuit, and a malformed-category value that raises `TypeError`
  mid-scan, proving the D4 stderr diagnostic actually fires.
- `run_pointer_retirement.py`: two new tests in `test_run_pointer_retirement.py`
  — a corrupted re-check read (the D3 recheck's own decode-error branch) and
  a per-file `unlink()` `OSError`, both proving the loop skips-and-continues
  rather than raising.
- `audit_phase_quality_on_stop.py`: new file
  `test_audit_phase_quality_stop_hook_direct.py` — imports the hook module
  directly and calls `main()` in-process (trading real-subprocess fidelity,
  already covered by the existing E2E suite, for coverage visibility on a
  module ADR-045 makes structurally invisible otherwise). Six tests cover
  the greenfield no-op, the disabled-by-flag no-op, the unrecognized-plugin
  no-op, a normal write-and-aggregate pass, the render-both-roots behavior
  via a real `git worktree add` + pointer fixture, and a per-phase exception
  not aborting the remaining phases.

Full `shared/tests` suite re-run clean after these additions: 8660 passed, 32
skipped, 20 deselected. `verify_local.py`'s 3 mirrored merge guards and
`ruff check .` both pass clean against the final diff.
