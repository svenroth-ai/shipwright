# D2V Iterate ADR — EMPIRICAL verification gate for the D2 outbox sweep/GC

Run-ID: `iterate-2026-06-08-outbox-delivery-d2v`
Complexity: medium (treated; classifier keyworded `trivial`, but this gate
exercises the triage IO boundary under real contention — `touches_io_boundary`
applies) · Risk flags: `touches_io_boundary`

## Decision

VERIFICATION-ONLY sub-iterate — essentially no product code. Build a REAL empirical
harness that PROVES D2's safety properties (whole-section lock + origin-delivered GC
+ never-reset-after-read) under real conditions and RUN it as a HARD gate stacked
under D3. The harness drives the REAL D2 code (`triage._FileLock` /
`append_triage_item(..., to_outbox=True)`, `lib.sweep_outbox.sweep_outbox_to_branch`,
`tools.setup_iterate_worktree.setup`, `tools.integrate_main.integrate`) over real
git — nothing mocked.

Five empirical methods, all PASS (evidence:
`.shipwright/planning/iterate/campaigns/2026-06-08-triage-outbox-delivery/D2V-empirical-results.md`):

- METHOD 1 — 200 real THREAD-concurrent trials (deterministic per-trial seed), zero
  loss / multiset count==1 per id over branch ∪ outbox.
- METHOD 1b — 40 real CROSS-PROCESS trials (separate OS process contends the
  OS-level `_FileLock`), same multiset proof (added per external review).
- METHOD 2 — abandoned-branch e2e: real `setup` → delete branch unmerged → next real
  `setup` re-sweeps; line survives in the durable outbox, never stranded.
- METHOD 3 — exactly-once after a REAL merge: real `git merge` via the seeded
  `merge=union` driver delivers the line, then `integrate_main.integrate`'s dedup
  collapses two sides carrying it to EXACTLY one; CRLF + header-ordering covered.
- METHOD 4 — no `chore(triage)` fold commit on local `main` after a real `setup`
  (ref equality + subject scan); the append rode the iterate branch.

Packaging: `test_d2v_empirical_gate.py` (methods 1/1b + smoke) +
`test_d2v_empirical_gate_e2e.py` (methods 2-4) + `_d2v_helpers.py` (evidence
collector) + `_d2v_outbox_producer.py` (cross-process producer). The heavy
200-trial + 40-process runs are `@pytest.mark.slow` (the already-registered
marker — no new marker, no unknown-marker warning) so the default fast suite stays
tractable; they still run on demand and in the gate via `-m slow`. A FAST 12-trial
smoke runs in the default suite to catch a harness regression without the heavy load.

Note on METHOD 2 git refs: `branch1_head == branch2_head` in the evidence is
EXPECTED, not a flaw — both branches sweep the same single line from the same base
with a deterministic committer (fixture env), so the content-addressed commit SHAs
coincide. The proof is the re-sweep presence assertion, not SHA distinctness.

## GATE outcome: **PASS** — every proof established empirically. Finalized `complete`.

## External-Plan-Review-Findings (OpenRouter: openai + gemini)

| # | Provider | Sev | Finding | Disposition |
|---|----------|-----|---------|-------------|
| 1 | gemini | high | git e2e risks mutating the developer's host repo | rejected-already-handled: ALL tests use the `git_origin_repo`/`tmp_path` fixtures + `tmp` worktrees; the harness never touches the host repo (subprocess argv arrays, paths confined to pytest tmp). |
| 2 | openai | high | set comparison can hide a swap (one lost + one dup) — prove MULTISET | accepted-and-FIXED: added `count_titles` multiset assertion (`count==1` per expected title over branch ∪ outbox deduped-by-physical-line) to METHOD 1 + 1b, alongside the existing per-id presence + branch physical-dup checks. |
| 3 | openai/gemini | high/med | thread-only contention may mask OS-level FileLock races under the GIL | accepted-and-FIXED: added METHOD 1b — 40 real CROSS-PROCESS trials via `_d2v_outbox_producer.py` (separate `python` process), contending the canonical OS-level `_FileLock` (`msvcrt.locking`/`fcntl.flock`). The thread proof keeps the >=200 count; the process proof covers cross-process contention. |
| 4 | gemini/openai | med | METHOD 3 uses `integrate` not bare `merge=union` — proves a different property | accepted-with-reason + added coverage: exactly-once is INTEGRATE-dedup-provided, NOT bare-`merge=union`-provided — documented in the D2 ADR FIX C (a bare merge of two sides both carrying L duplicates until the next integrate). `integrate_main.integrate` IS the real production merge path devs run. Added an explicit assertion that the REAL `git merge` (seeded `merge=union` driver) DELIVERS the line to origin (no merge-layer loss), separate from the integrate-dedup exactly-once proof. |
| 5 | openai | med | CRLF / ordering not introduced deterministically | rejected-already-handled: METHOD 3 writes an explicit `\r\n`-terminated outbox line via `write_bytes` (deterministic), seeds a header-first log, and asserts header-still-first post-merge. |
| 6 | openai | med | abandoned-branch can't distinguish "GC never removed" from correct recovery | rejected-already-handled: METHOD 2 asserts the intermediate state explicitly — the line REMAINS in the outbox after sweep-1 (`assert line in outbox_lines` — origin un-advanced so GC kept it), THEN branch deletion + re-sweep. Both branch heads recorded in the evidence. |
| 7 | openai | med | randomized jitter not reproducible/diagnosable | accepted-and-FIXED: deterministic per-trial seed `_BASE_SEED + trial` (recorded in the evidence detail) so the interleave schedule is reproducible for replay. |
| 8 | openai | med | git e2e env not self-contained (user.name/email, branch, autocrlf) | rejected-already-handled: the `git_origin_repo` fixture sets local `user.email`/`user.name` (`set_identity`) + `-b main` + an explicit `.gitattributes`; no reliance on global config. Git is required (real-git gate) — a missing binary fails loudly, not a silent skip. |
| 9 | openai | med | no-pollution `git log` message scan too coarse | rejected-already-handled: METHOD 4 asserts `main_before == main_after` REF equality (the strong check) AND the subject scan as a secondary. |
| 10 | openai | med | concurrency covers only one producer / one sweep window | accepted-partially: each trial already appends 4 pre + 4 concurrent (multiple lines per window); the multiset proof covers all of them. Back-to-back sweeps are covered by METHOD 2/3 (re-sweep + two-branch sweep). Multi-producer fan-out deemed out of scope (one background producer per tree is the real topology). |
| 11 | openai | low | `slow` marker lets CI omit the gate | accepted-with-reason: the campaign orchestrator INDEPENDENTLY re-runs the 200-trial proof per the runner contract (`reviews.code: delegated_to_orchestrator`); the gate is not convention-only. |
| 12 | openai | low | test-only code runs real git — path/arg misuse risk | rejected-already-handled: subprocess argv arrays (no shell), all ops confined to pytest tmp dirs, generated ref/file names are deterministic synthetic tags. |
| 13 | gemini | low | orphaned lockfiles on mid-loop strict-stop | rejected-already-handled: `_FileLock.__exit__` releases the OS lock + closes the fp; the lock sidecar lives in the per-test `tmp_path` (discarded at teardown) — no host pollution. |
| 14 | openai/gemini | low | session-scoped evidence flush drops on hard crash | accepted-with-reason: each method records into the collector in a `try/finally` (so a FAIL is recorded before the re-raise); the artifact is the committed deliverable (not a temp path) — a hard interpreter crash is acceptable to lose because the gate then visibly didn't complete (no green commit). Incremental append deemed not worth the format complexity. |

## External-Code-Review-Findings (OpenRouter: openai + gemini, diff-mode)

The external LLM CODE review (diff-mode) was run on the staged harness diff. The
internal reviewer cascade (`spec-reviewer → code-reviewer → doubt-reviewer`) is
delegated to the campaign orchestrator (`reviews.code: delegated_to_orchestrator`):
the runner has no `Agent` tool, and the orchestrator ALSO independently re-runs the
200-trial proof.

| # | Sev | File | Finding | Disposition |
|---|-----|------|---------|-------------|
| C1 | high | gate.py | >=200 only on THREAD path; cross-process only 40 | accepted-with-reason: the spec explicitly permits thread OR subprocess for the >=200; the thread path (200) SATISFIES it, the 40 cross-process trials are ADDITIVE OS-level insurance (added at C1/C3 of the plan review). Clarified the artifact detail to state the thread path is the spec's >=200, not insufficient. |
| C2 | med | gate.py overlap | no guarantee the producer overlapped the sweep | accepted-and-FIXED: the producer now signals AFTER its first append and keeps appending (non-zero jitter) so the sweep starts with one append in flight and MORE arriving during its lock window — guaranteed real overlap, not an early-finished producer. |
| C3 | med | gate.py set-union dup | set-union of branch ∪ outbox masks a cross/in-file physical dup | accepted-and-FIXED: added `assert_no_physical_dup` over RAW (un-deduped) per-file line LISTS on BOTH branch and outbox (catches an in-file physical duplicate a stripped-line set collapses), kept alongside the union multiset count. |
| C4 | med | gate.py partial-run PASS | a partial slow selection flushes an artifact reporting PASS over only the subset that ran | accepted-and-FIXED: `Evidence.all_passed()`/`verdict()` now require ALL `REQUIRED_METHOD_TAGS` present (else INCOMPLETE), and a `pytest_sessionfinish` hook FAILS the session (exit 1) when METHOD 1 ran but any mandatory method is missing. Empirically verified: METHOD-1-only run exits 1 "GATE INCOMPLETE"; full gate exits 0. |
| C5 | med | helpers.all_passed | `all_passed()` true even if mandatory methods never recorded | accepted-and-FIXED: same as C4 — `missing_required()` gates the verdict. |
| C6 | low | e2e.py method 3 second side | second-side relies on integrate dedup, could mask a union-driver regression | accepted-with-reason + added coverage: added an explicit assertion that the REAL `git merge` (seeded `merge=union` driver) DELIVERS the line to origin pre-integrate (isolates union-driver delivery from integrate's dedup). Exactly-once across two carrying sides is INTEGRATE-provided by design (D2 ADR FIX C). |

## Self-Review (7-item)

1. **Spec Compliance** — PASS: all 6 ACs met empirically (concurrency >=200 / 0 loss
   / 0 dup / FileLock not mocked; abandoned-branch survives+re-swept; exactly-once
   after real merge CRLF+order; no fold commit on main; evidence artifact;
   strict-stop on any failure via try/finally + re-raise).
2. **Error Handling** — PASS: each method wraps its body in `try/except
   AssertionError`, records a FAIL MethodResult, and re-raises so the runner returns
   non-complete; subprocess `communicate(timeout=30)`; producer-process returncode
   asserted.
3. **Security Basics** — PASS: subprocess argv arrays (no shell), paths confined to
   pytest `tmp_path`, deterministic synthetic ref/tag names, no host-repo writes.
4. **Test Quality** — PASS: REAL git/worktrees/threads/subprocess/lock/integrate; no
   mocks; multiset (not count-only) comparison; 200 thread + 40 process trials;
   deterministic seeds; evidence artifact with refs/SHAs/node-ids.
5. **Performance Basics** — PASS: heavy runs are `slow`-gated out of the fast suite;
   the gate run is ~72s (acceptable for a HARD safety gate); no N+1.
6. **Naming & Structure** — PASS: `test_d2v_empirical_gate*` + `_d2v_helpers` +
   `_d2v_outbox_producer` mirror the `_sweep_helpers` pattern; every file < 300 LOC;
   reuses the existing `slow` marker (no new marker).
7. **Affected Boundaries (ADR-024)** — PASS: producer = background triage append to
   the outbox; consumers = sweep materializer, union `read_all_items`, git
   `merge=union` + integrate dedup, GC. REAL round-trip probes run
   (producer→outbox→sweep→branch→merge→integrate→GC), both thread- and
   process-contended.

## Confidence Calibration (touches_io_boundary — MANDATORY; this IS the empirical method)

Boundary: triage append-log outbox ↔ tracked-log ↔ git (commit + merge=union +
integrate-dedup + GC) under concurrent producer contention.

Probes run (empirical, REAL — the asymptote heuristic is literally the method here):
- PROBE-1: 200 THREAD-concurrent trials, deterministic seeds → zero loss, multiset
  count==1 → no finding.
- PROBE-2: 40 CROSS-PROCESS trials (OS-level lock contention) → zero loss, multiset
  count==1 → no finding (added after the thread proof exhausted; the second
  contention CLASS with no findings).
- PROBE-3: abandoned-branch re-sweep (real setup + branch -D + next setup) → line
  survives + re-swept → no finding.
- PROBE-4: exactly-once after a real `git merge` (union driver delivers) +
  `integrate` dedup → exactly one occurrence, validates, header ordered → no finding.
- PROBE-5: no-pollution (ref equality on local main after real setup) → main HEAD
  unmoved, append on the branch → no finding.

Asymptote: the thread-contention class reached two-consecutive-no-finding within its
200 trials; the external review surfaced a SECOND contention class (cross-process),
which I added (PROBE-2) and ran — it ALSO found nothing. Two distinct contention
classes + three e2e classes, all no-finding → boundary declared CALIBRATED for the
gate.

Edge-cases NOT probed + why acceptable:
- multi-producer (>1 background producer per tree) fan-out → out of scope; the real
  topology is one background-hook producer per tree.
- non-`origin` remote name → out of scope (D1 gates outbox population on `origin`).
- corrupt-line wedge → pre-existing reconcile contract; the producer path can't
  inject a corrupt line (D2 ADR finding #4, follow-up candidate).
