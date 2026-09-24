# Review-cascade findings — `iterate-2026-09-22-r4-state-mechanics`

<!-- Named by run_id, not a numeric ADR-NNN (assigned later at release, per
     `_template-bloat-exception.md`'s convention). Referenced from F3's
     decision-drop via `--spec-ref`. -->

Campaign `campaign-dag-scheduler`, sub-iterate R4 (concurrent state
mechanics). Two independent external-LLM review passes ran against this
sub-iterate: Step 3.5 (plan review, against the R4 spec section before
build) and Step 3.7 (code review, against the actual diff). Each finding
below is dispositioned `accepted-and-fixed`, `rejected-with-reason`, or
`accepted-and-deferred-to-R5a`.

## External-Plan-Review-Findings (Step 3.5 — GLM + OpenAI, 15 findings)

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM | medium | `check_unit_attempt.py` load-bearing but no owner named | rejected-with-reason: verified to already exist in `shared/scripts/checks/`, now with dedicated test coverage (`test_check_unit_attempt.py`) |
| 2 | GLM | medium | R2 ("no fencing on lease touch") vs R4 ("fencing on every mutation incl. lease touch") contradicts | accepted-and-deferred-to-R5a: no live caller can supply a real `attempt_id` to the lease-touch path until R5a wires the runner brief; fencing it now would fence against a value nothing yet produces. Duplicate of OpenAI #6 below. |
| 3 | GLM | medium | R1's `cmd_next` ancestry guard runs inside `loop.lock` (same lock-timing hazard R4 fixes for `cmd_next_batch`) | rejected-with-reason: out-of-scope for R4 — `cmd_next` is R1's existing code; R4's own work breakdown scopes the lock-timing fix to `cmd_next_batch`, its explicitly-named "batch-parallel sibling" |
| 4 | GLM | low | No backoff specified if a whole wave's ready set is ancestry-stale (hot-spin risk) | accepted-and-deferred-to-R5a: `cmd_next_batch` already returns a distinct exit 4 ("stalled, nothing ready") vs exit 2 ("done"); backoff *policy* on repeated exit 4 is the orchestrator wave loop's job, not this CLI's |
| 5 | GLM | low | `cmd_finalize` summary field breakdown (merged/failed/held) not spec'd | rejected-with-reason: already satisfied — `sub_iterate_finalize_summary` returns explicit `merged`/`failed`/`held`/`total` counts |
| 6 | GLM | low | `cmd_mark_merged` doesn't itself attest PR identity | accepted-and-fixed: docstring states precisely what the command does and does not attest |
| 7 | GLM | low | Runner's Step 1.0.5 failure path (stale fencing) unspecified | accepted-and-deferred-to-R5a: R4 builds `cmd_mark_running` itself (correctly returns exit 5); specifying the *runner's* reaction to that exit code is R5a's own brief/spec |
| 8 | OpenAI | high | `held` units read as permanently unschedulable — no auto-resume on `cmd_init` | rejected-with-reason (misreading): the edge table explicitly names `cmd_mark` (operator-initiated) as the *sole* `held -> pending` path, by design — a deliberate stop-gate, not an oversight; `cmd_init`'s `RESUMABLE` set correctly *reports* held units via `pending: N` rather than silently dropping them |
| 9 | OpenAI | high | R1-era `cmd_next` could falsely report "done" when all pending units are dependency-blocked | rejected-with-reason: out-of-scope for R4 (R1's code); already partially mitigated by R1's own fix — the JSON body's `reason` field now distinguishes "stalled" from "done" even though the exit code (2) is unchanged; R4 owns `cmd_next_batch`'s exit codes, not `cmd_next`'s |
| 10 | OpenAI | high | Atomic claiming underspecified around outside-lock work vs. a fresh in-lock snapshot | accepted-and-fixed: `cmd_next_batch` treats outside-lock work as prefetch only — the in-lock claim re-validates every dependency's `merged_commit` against a fresh snapshot before claiming (also independently raised by the code-review cascade, OpenAI/GLM medium, and hardened there) |
| 11 | OpenAI | medium | "Base derived from dependencies' merged commits" is ambiguous for multiple deps | rejected-with-reason: already satisfied — the implementation never derives a base from dependency commits; it resolves ONE immutable `origin/<default>` ref per batch (`_resolve_batch_base`) and asserts every dependency's `merged_commit` is an ancestor of that same ref |
| 12 | OpenAI | high | Legacy invalid unit IDs flow unvalidated into worktree paths / branch names / shell fragments | accepted-and-deferred-to-R5a: R4 itself never constructs a worktree path or branch name (see finding on `cmd_next_batch`'s claimed-payload shape, R5a's job); the one path R4 itself builds from an untrusted value (`rejected_payload_path`'s `attempt_id`) is already charset-validated with a digest fallback (code-review fix, this run) |
| 13 | OpenAI | medium | R2's unfenced lease-touch vs R4's fencing invariant | accepted-and-deferred-to-R5a: duplicate of GLM #2 above |
| 14 | OpenAI | medium | `cmd_mark_merged` doesn't itself verify ancestry-reachability of the SHA | rejected-with-reason: intentional — documented in the command's own docstring as the authoritative producer of a trustworthy SHA; re-verifying here would be circular, and the real identity check is R5b's step-3g caller's job, performed once before calling this command |
| 15 | OpenAI | medium | `max_attempts` predicate ambiguous (total claims vs. retries) | accepted-and-fixed: `cmd_release`'s docstring + the actual predicate (`attempt + 1 >= max_attempts`) now state precisely "K total claims" |

## External-Code-Review-Findings (Step 3.7 — OpenAI + GLM, 13 findings incl. 2 duplicate pairs)

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | OpenAI | high | Path traversal: untrusted `--attempt-id` reaches `rejected/{attempt_id}.json` | accepted-and-fixed: `_safe_rejected_filename` (charset regex + digest fallback) + resolved-path containment assert in `rejected_payload_path` |
| 2 | OpenAI | high | `cmd_record`'s fencing check runs in an early, released lock; never re-validated at write time (TOCTOU) | accepted-and-fixed: `enforce_record_fencing` re-invoked inside every write-lock acquisition with `target_status` set. Duplicate of GLM #1 below. |
| 3 | OpenAI | medium | A matching token alone lets `cmd_record` write `built`/`failed` regardless of current row status, skipping the state machine | accepted-and-fixed: `enforce_record_fencing` gained an `is_legal_transition` check against `target_status`, re-run inside every write lock |
| 4 | OpenAI | medium | `_ancestry_ok`'s fetch-retry (60s timeout) runs inside `loop.lock` | accepted-and-fixed: `cmd_next_batch` restructured so ancestry pre-check runs entirely outside the lock; in-lock claim only re-checks a cheap merged-commit snapshot for staleness |
| 5 | OpenAI | medium | No physical worktree/branch cleanup on launch-failure release or lease reclaim | accepted-and-fixed (corrected 2026-09-23 — see below): `cmd_release` now attempts best-effort `git worktree remove`/`git branch -D` via `_cleanup_unit_worktree`, recomputing the path from validated `(campaign_slug, unit_id, attempt)` (`lib.campaign_unit_worktree`) and reading the branch back from git itself; any failure is swallowed and never blocks the logical release, per the spec's own reclaim/cleanup split. **Correction:** the original disposition here claimed "R1's `git worktree prune` at next-claim already sweeps a failed cleanup" — false; no `git worktree prune` call exists anywhere in `shared/scripts/` today (verified by grep during the Stage-1 spec-reviewer's re-check). The spec's "swept by `git worktree prune` at the next claim" sentence describes an intended fallback for a *failed cleanup attempt*, not license to skip the attempt — that gap is what this fix closes. Bloat exception filed: `iterate-2026-09-22-r4-state-mechanics-loop-claim-bloat.md` (300 -> 345 LOC). Lease-reclaim's own physical cleanup (distinct from launch-failure release) remains R5a's, unchanged — R4 builds no lease-reclaim caller. |
| 6 | GLM | high | Same TOCTOU race as OpenAI #2 | duplicate — see OpenAI #2 |
| 7 | GLM | high | `cmd_init_sub_iterate_payload` silently reports `resumed, pending: 0` for a unit stuck at legacy status `"in_progress"` | accepted-and-fixed: legacy `in_progress` units now routed through `_reconcile_legacy` alongside (not instead of) the new lease-based reconcile |
| 8 | GLM | medium | `cmd_next_batch`'s claimed payload omits `worktree`/`branch`/`run_dir`, forcing R5a to re-derive the naming formula | accepted-and-deferred-to-R5a: the naming formula is already the single source of truth, stated verbatim in R4's own spec section; R4's work breakdown scopes it to "atomic claim, single-writer fencing," not runner-brief construction, which is R5a's own job and has the campaign-slug/description context R4 does not |
| 9 | GLM | medium | `cmd_mark --status merged` defaults `--campaign-worktree` to `None`, so its fetch/ancestry check silently runs against the process cwd | accepted-and-fixed: `--campaign-worktree` is now required (fails closed with a clear error) whenever `--status merged` |
| 10 | GLM | medium | A just-claimed unit has no lease field yet; a reconcile in that window reads it as "never leased" and reclaims it, burning an attempt | accepted-and-fixed: `_claim_unit` now writes an initial `lease_expires_at` at claim time |
| 11 | GLM | low | No `cmd_next_batch`-level test exercises a real `depends_on` edge (only `_ancestry_ok` in isolation and dependency-free units were covered) | accepted-and-fixed: added `test_claims_unit_whose_dependency_ancestry_verifies` |
| 12 | GLM | low | Section-flow `cmd_record`/`_reconcile_legacy` cwd-independence untested through that call path (only the raw path helpers are tested with `monkeypatch.chdir`) | rejected-with-reason: the underlying primitive (`runs_dir_for`/`handoff_dir_for`) is already directly tested for cwd-independence, and `_reconcile_legacy`/`cmd_record` pass `state_path` straight through with no re-derivation — there is no additional wiring left to exercise |
| 13 | GLM | low | ADR/INDEX.md/baseline numbers (668 vs. 683) inconsistent | accepted-and-fixed: `INDEX.md` regenerated via `rebuild_adr_index.py`; ADR + baseline both now state the final measured 757 |

## Summary

8 findings fixed in code (2 high, 5 medium, 1 low, from the code-review
cascade, including code-review finding #5's 2026-09-23 correction — see its
row above) + 2 docstring-precision fixes and 1 doc-regeneration fix from the
plan-review cascade. 5 findings deferred to R5a with documented reasoning
(all concern runner-brief/worktree construction or the R2-lease-touch
fencing migration, neither of which R4's own file list or work breakdown
owns). 6 findings rejected as either already-satisfied by the actual
implementation or a misreading of the design (`held`'s deliberate
operator-only resume path being the recurring one). No finding was ignored
without a recorded reason.

**2026-09-23 addendum:** a Stage-1 spec-reviewer re-check of the merged PR
found code-review finding #5's original disposition rested on a false
factual claim (no `git worktree prune` call exists in `shared/scripts/`) and
that the underlying gap — `cmd_release` never attempting the spec-required
cleanup — was real. Fixed; see the corrected row above and the new bloat
exception `iterate-2026-09-22-r4-state-mechanics-loop-claim-bloat.md`. The
same re-check also flagged the ADR-045 bare-sibling import of `loop_mark`
in `loop_claim.py` (fixed: now `lib.loop_mark`-qualified, matching the
sub-iterate spec's own stated import convention) and two artifact
accuracy issues, fixed without any code/design change: `r4-spec-section.md`
was regenerated from the full sub-iterate spec (was a 283-line excerpt of a
different document — the plan's own R4 restatement, which has no
Acceptance Criteria section — rather than the 335-line sub-iterate spec
that actually carries the AC text `loop_mark.py`'s docstring cites), and
`iterate-2026-09-22-r4-state-mechanics-loop-state-bloat.md`'s rejected-
alternatives section was corrected to lead with its real (Ousterhout)
rejection reason rather than a bare module-count argument the AC's own
cohesion-split permission contradicts as a general rule.
