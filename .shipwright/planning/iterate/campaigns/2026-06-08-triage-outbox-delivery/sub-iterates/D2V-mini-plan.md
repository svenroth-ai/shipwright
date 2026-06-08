# D2V mini-plan — empirical verification gate for the D2 outbox sweep/GC

## Problem

D3 is stacked on D2 (outbox → sweep-into-PR-branch → GC). A silent triage-line
loss in D2 would propagate to every adopted repo via D3. We need an EMPIRICAL,
non-mocked proof that D2's safety properties hold under real contention before
D3 may proceed — a HARD gate that strict-stops the campaign on any failure.

## Approach (verification-only; no product code)

Build a real harness in `shared/tests/` that drives the REAL D2 code over REAL
git, with NO mocks, and record an auditable evidence artifact:

1. METHOD 1 — concurrency stress: a real thread calling the canonical
   `triage.append_triage_item(..., to_outbox=True)` (same `_FileLock` the sweep
   holds) races the real `sweep_outbox_to_branch` for >=200 trials with
   randomized jitter; assert zero loss + zero dup by full line-SET each trial.
2. METHOD 2 — abandoned-branch e2e: real `setup` sweeps onto branch 1; delete
   branch 1 unmerged; next real `setup` re-sweeps; assert survival (not stranded).
3. METHOD 3 — exactly-once after a REAL merge via `integrate_main.integrate`
   (dedup-provided, not bare merge=union); CRLF + ordering covered.
4. METHOD 4 — no `chore(triage)` fold commit on local `main` after a real `setup`.

Heavy 200-trial run marked `@pytest.mark.slow` (already-registered marker) so the
default fast suite stays tractable; it still runs on demand and in the gate.
Evidence flushed to `D2V-empirical-results.md` via a session-scoped collector.

## Alternatives considered

- Single-shot / count-only assertions — REJECTED by the spec; they cannot catch a
  race-window loss, and a count match can hide a swap (one lost + one dup).
- Mocking the lock / git — REJECTED; the whole point is to exercise the REAL
  contention primitive. A "pass" only achievable by mocking is a gate failure.
- A new `gate` marker — REJECTED in favor of the existing `slow` marker (no new
  marker registration, no unknown-marker warning).

## Gate semantics

All four methods PASS empirically → finalize `complete`. ANY method that cannot be
established (real loss/dup/strand/pollution, or mock-only pass) → `failed` /
`escalated` so the orchestrator strict-stops before D3.

## Acceptance criteria trace

- AC1 (concurrency >=200, 0 lost/0 dup, FileLock not mocked) → METHOD 1.
- AC2 (abandoned-branch survives + re-swept) → METHOD 2.
- AC3 (exactly-once after real merge, CRLF+order) → METHOD 3.
- AC4 (no fold commit on main after setup) → METHOD 4.
- AC5 (evidence artifact recorded) → `D2V-empirical-results.md`.
- AC6 (strict-stop on any failure) → per-method try/finally records FAIL and
  re-raises; runner returns non-complete on assertion failure.
