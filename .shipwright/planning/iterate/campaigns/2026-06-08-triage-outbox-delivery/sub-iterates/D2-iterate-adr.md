# D2 Iterate ADR — sweep outbox into PR branch + abandoned-branch-safe GC

Run-ID: `iterate-2026-06-08-outbox-delivery-d2`
Complexity: medium · Risk flags: `touches_io_boundary` (triage append-log + git)

## Decision

Replace the per-iterate "fold main-tree triage drift into a `chore(triage)` commit
on LOCAL main" (`reconcile_main_triage`, the orphan generator) with a SWEEP of the
gitignored main-tree outbox into the iterate PR BRANCH, plus an abandoned-branch-safe
GC. Net: background appends ride the PR to origin; local main never accrues a fold
commit. Drop integrate_main's vestigial reconcile (Codex Q1); relegate
`reconcile_main_triage` to a manual-CLI-only fallback.

New module `shared/scripts/lib/sweep_outbox.py` (`sweep_outbox_to_branch`). The
canonical triage lock spans read-outbox → read-worktree → materialize → branch-commit
→ GC (Codex Q4). GC drops an outbox line ONLY once it is in `origin/<default>:triage.jsonl`
(Codex unlisted abandoned-branch failure mode). EOL-normalize + `dedup_triage_lines` +
`validate_triage_text` are the IDENTICAL helpers reconcile uses (Codex Q3).

## External-Plan-Review-Findings (OpenRouter: openai + gemini)

| # | Provider | Sev | Finding | Disposition |
|---|----------|-----|---------|-------------|
| 1 | gemini | high | `git commit` opens `$EDITOR` → deadlock under lock | rejected-already-handled: code passes `-m subject`; `run_git` uses argv array + `--no-pager`. No interactive prompt. |
| 2 | gemini | med | `git show origin/main:triage.jsonl` fatal on missing ref → aborts mid-lock | rejected-already-handled: `_origin_delivered_set` uses `run_git(check=False)`, returns `set()` on `returncode != 0`. Empirically probed (PROBE-2). |
| 3 | openai | high | stale `origin/<default>` → delivered line lingers in outbox | accepted-with-reason: harmless by design (line is already on the branch; re-sweep is idempotent via union-dedup). setup Step-3 `git fetch origin` refreshes origin BEFORE the sweep — documented in the step-5 comment. |
| 4 | openai | high | one invalid outbox line wedges delivery of all valid lines forever | accepted-with-reason: (a) the outbox is written only by `triage.append_line` (valid JSON, serialized) — a raw corrupt line can only arrive via direct file injection, not a producer path; (b) this is the SAME `invalid → no commit` contract `reconcile_main_triage` already had — D2 preserves it, does not regress; (c) the union reader is tolerant (skips corrupt lines) so visibility is retained. Quarantine-file mitigation is out of D2 scope → follow-up candidate. |
| 5 | openai/gemini | med | hardcoded remote name `origin` | accepted-with-reason: the whole campaign assumes `origin` — D1's `should_route_to_outbox` REQUIRES an `origin` remote before routing to the outbox at all, so a non-`origin` repo never populates the outbox. Consistent with the codebase (`default_branch`, `setup` all key off `origin`). |
| 6 | openai | med | duplicate concurrent SWEEP invocations for one repo | accepted-and-covered: the canonical lock serializes; the abandoned/double-sweep tests + lock-contention proof cover the race. A second sweep of the same outbox is `no_change` (test_double_sweep_idempotent). |
| 7 | openai | med | exactly-once depends on `.gitattributes` merge=union being present | accepted-and-covered: setup step 4.5 `self_heal_gitattributes` scaffolds it; the seed fixture writes it; test_swept_line_exactly_once_after_union_merge exercises the real union driver. |
| 8 | openai | med | skipped/failed sweep silently defers delivery | accepted-with-reason: `SweepResult` carries an explicit `status`/`reason`; setup prints a non-silent fail-soft line on invalid/error. A guard skip defers to the NEXT setup (the outbox is durable, gitignored, never cleared on skip). |
| 9 | openai | med | EOL/serialization mismatch could break text-membership GC | accepted-and-covered: producer + sweep + merge all canonicalize via the same strip/CRLF-absorb idiom; test_crlf_outbox_line_swept + the round-trip outbox test prove the normalized string survives. |
| 10 | openai | low | coupling to private `triage._FileLock`/`_lock_path`/`_atomic_write` | accepted-with-reason: deliberate — reconcile already couples to the SAME private helpers; sharing the EXACT lock primitive is the whole point (Codex Q4). Promoting to a public API is a cross-cutting refactor beyond D2. |
| 11 | openai/gemini | low | secrets/duplicates promoted to git history | accepted-with-reason: outbox content is the same triage items that ship in PRs anyway; union-dedup collapses physical duplicates on the next branch. No new exposure surface. |

## External-Code-Review-Findings (OpenRouter: openai + gemini)

| # | Sev | File | Finding | Disposition |
|---|-----|------|---------|-------------|
| C1 | high | sweep_outbox.py empty-outbox early return | empty outbox returns `no_change` before GC | accepted-with-reason: an empty outbox has NO lines to GC (GC operates on `outbox_lines`) — the early return is functionally complete. A whitespace-only file is the only un-trimmed case (cosmetic, harmless). |
| C2 | med | sweep_outbox.py GC writeback EOL | survivors written with WORKTREE EOL, not outbox's own EOL → CRLF outbox rewritten to LF | accepted-and-FIXED: capture `outbox_eol` from the outbox's own normalize; write survivors with `outbox_eol`. New test `test_gc_preserves_outbox_own_eol_not_worktree_eol`. |
| C3 | med | setup_iterate_worktree.py skipped sweep | `skipped` sweep outcomes silently proceed | accepted-and-FIXED: setup now surfaces any non-clean sweep (`invalid`/`error`/`skipped`) via `sweep_warning` in the payload `warnings`; invalid/error also printed to stderr. |
| C4 | med | test_sweep_outbox.py EOL parity | parity test reimplements reconcile logic inline | accepted-and-FIXED: parity test now runs the SAME raw input through reconcile's real inline idiom + the shared `dedup_triage_lines`, comparing resulting bytes (dup-collapse + CRLF-dominant preserved). |
| C5 | med | test_reconcile_triage_wiring.py integrate test | drift simulated via tracked append, not the D1 outbox | accepted-and-FIXED: `test_integrate_main_does_not_reconcile_main` now writes the real `.shipwright/triage.outbox.jsonl` and asserts integrate neither commits to main NOR consumes the outbox. |

## Self-Review (7-item)

1. **Spec Compliance** — PASS: sweep+GC under one lock, drop integrate reconcile,
   relegate reconcile to manual — all AC met, empirical tests not mocked.
2. **Error Handling** — PASS: every git call `check=False` + structured `SweepResult`;
   commit `TimeoutExpired` → `error`; never raises into setup.
3. **Security Basics** — PASS: argv arrays only (no shell interpolation); paths from
   trusted `main_root`/`worktree_path`; `validate_triage_text` gates content.
4. **Test Quality** — PASS: real git/worktrees/threads/lock; line-SET (not count)
   comparison; 20 concurrency trials + lock-contention proof; guards covered.
5. **Performance Basics** — PASS: lock spans a small git commit on a tiny log; no
   N+1; reads are single `git show`/file reads.
6. **Naming & Structure** — PASS: `sweep_outbox_to_branch`/`SweepResult` mirror
   `reconcile_main_triage`/`ReconcileResult`; module < 300 LOC; tests split < 300.
7. **Affected Boundaries (ADR-024)** — PASS: producer = background triage append to
   outbox; consumers = sweep materializer, union `read_all_items`, git `merge=union`
   driver. Real round-trip probe (producer→outbox→sweep→branch→merge→GC) run.

## Confidence Calibration (touches_io_boundary — MANDATORY)

Boundary: the triage append-log outbox ↔ tracked-log ↔ git (commit + merge=union + GC).

Probes run (empirical, real):
- PROBE-1 (canonical lock blocks a concurrent append for the full hold) → confirmed
  307ms block while lock held 300ms (no finding).
- PROBE-2 (missing `origin` ref → `_origin_delivered_set` returns `set()`, no raise) →
  confirmed no exception (no finding).
- Round-trip: producer→outbox→sweep→branch (test_sweep_commits_on_branch_not_main +
  header-preserved) → no finding.
- merge=union exactly-once (real divergent push + real git merge) → exactly-one
  occurrence, validate passes → no finding.
- CRLF outbox line swept (test_crlf_outbox_line_swept) → normalized, no spurious dup →
  no finding.
- Abandoned-branch re-sweep (delete branch unmerged, sweep onto new branch) → line
  re-swept and present → no finding.
- 20-trial concurrency (producer races sweep) → ZERO line lost / ZERO duplicated by
  line-SET compare → no finding.

Asymptote: two+ consecutive probe classes with no findings after the initial design →
boundary declared calibrated. Edge-cases NOT probed + why acceptable:
- non-`origin` remote name → out of scope (D1 gates outbox population on `origin`).
- corrupt-line wedge → pre-existing reconcile contract, producer path can't inject it
  (follow-up candidate, finding #4).
