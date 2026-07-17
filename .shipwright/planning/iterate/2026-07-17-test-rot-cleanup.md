# Iterate: Test-rot cleanup (50 pre-existing skipped/focused tests)

- **Run ID:** iterate-2026-07-17-test-rot-cleanup
- **Intent:** CHANGE (test-infrastructure hygiene) · **Spec Impact: NONE** (no product FR
  behavior changes; only test-skip discipline)
- **Complexity:** medium (history-calibrated; 0 risk flags)
- **Campaign:** STEP 2 of the traceability follow-up (anchor `trg-6b4b6a33`); independent of STEP 1.
- **Reviewer of record:** the executing agent (per BRIEF EXECUTION CONTRACT). The human does
  NOT technically review; external LLM review is pulled for the non-trivial test changes + the
  scanner change.

## Problem
Adopt's repo-wide skip inventory found 50 (now 51) skipped/focused tests at onboarding —
standing test rot the monorepo's *diff-scoped* hygiene gate cannot see (it only checks the
PR delta, never the pre-existing baseline; there is no full-corpus hygiene gate in CI). Each
silently skips; if the skipped condition ever masks a real CI regression it reads green.

## Decision (Think-Before-Coding + one alternative)
The brief frames each site as "quarantine-with-expiry or delete", but that binary is too coarse
for the actual findings — most are **legitimate conditional skips**, not dead tests. Deleting a
legitimate conditional test loses real coverage (constitution: *fix the code, not the test*).
I apply the taxonomy the **governing ADRs already define** (ADR-044/045):

| Treatment | When | Mechanism |
|---|---|---|
| **CI-GUARD** | binary/tool IS provisioned in monorepo CI (git, uv, coverage) | `skip_or_fail_on_missing_binary()` / `if is_ci(): pytest.fail()` — loud in CI, skip locally |
| **CANONICAL** | already CI-gated but via a local wrapper the scanner can't see | canonical `is_ci()` |
| **REMOVE-DEAD** | the skip condition is now permanently False (guarded resource shipped) | remove the stale decorator |
| **ALLOW-MARK** | genuinely conditional even in CI (symlink/privilege, platform, cache-home, data-state, defensive committed-file, bootstrap, node-not-in-CI) | `# test-hygiene: allow-silent-skip` + reason (ADR-045 sanctioned) |
| **SCANNER-FIX** | the finding is a false positive on test FIXTURE *data* | prune `fixtures/` from the repo-wide inventory walk |

**Alternative considered & rejected:** blanket `# test-hygiene: allow-silent-skip` on all 51
(fast, one-line each). Rejected — it would silence the git/uv/coverage sites that ADR-044
explicitly wants **loud** in CI, and would leave a stale dead guard and a scanner FP in place.
Mass-suppression is exactly the anti-pattern ADR-044 was written against.

## Scope (51 sites → 0 findings)
See the per-site table in the PR body. Summary: **17 CI-GUARD · 2 CANONICAL · 2 REMOVE-DEAD ·
28 ALLOW-MARK · 1 DELETE · 1 SCANNER-FIX**. Test-only edits + one adopt-lib scanner refinement
(+ its test). No product/source code changes. `git`/`uv`/`coverage` confirmed CI-provisioned
(ci.yml); `node`/`npx` is NOT → its skip stays ALLOW-MARK. (`test_artifact_path_canon.py:256` is
ALLOW-MARK rather than CI-GUARD: the file sits at its grandfathered 300-line bloat cap, so a
+3-line CI-guard would ratchet it; git-ls-files-empty is a genuine non-git-checkout affordance,
so the inline marker is the correct low-cost disposition.)

- **DELETE (1):** `test_dev_server_multiservice.py` — the no-op `@pytest.mark.skip`ped
  `pass` stub `test_wait_for_service_port_held_by_external_process_no_pid`. It is the STEP-2
  "delete" disposition, distinct from the 2 REMOVE-DEAD (which turn conditional tests
  unconditional). It asserted **nothing** and, by design, exercised nothing — the port-held-no-PID
  path never reaches `_wait_for_service` (short-circuited by `_already_running_owned` at
  `cmd_start`). Its scenario is covered by `test_start_port_busy_no_state_errors_no_kill`, whose
  docstring now carries the preserved rationale. A meaningful assertion at the `_wait_for_service`
  level is impossible (the function isn't called), so "restore as executable test" is infeasible.

## Acceptance Criteria
1. `repo_wide_skip_inventory` over the worktree returns **0 findings** (down from 51).
2. Every previously-flagged test still *collects* and, where its condition is satisfiable,
   still *runs* — no coverage lost — **with one deliberate exception:** the no-op `pass` stub
   above is DELETED (STEP-2 "delete"). It asserted nothing and its scenario is covered elsewhere,
   so removing it loses no coverage; it is the only flagged site that no longer collects.
   The 2 REMOVE-DEAD decorators guard a now-always-present resource, so those tests run
   unconditionally afterwards.
3. The js fixture `auth.spec.ts` remains a `test.skip` (its 5 dependent compliance tests
   still pass).
4. Full test suite green (F0). No new lint findings.
5. New test pins the SCANNER-FIX: a `fixtures/` dir **under a `tests/` tree** is excluded
   from the inventory walk, while a `fixtures/` dir **outside** a tests tree is still scanned
   (so adopt keeps its brownfield rot sensitivity — narrowed per review).

## Review (I am reviewer of record — no human technical review)
- **Internal cascade:** self-review + code-reviewer (verdict SAFE-TO-MERGE, no blockers) +
  doubt-reviewer biased-to-disprove (verdict NO BLOCKING ISSUES; all 7 theses survived).
- **External panel:** `external_review.py` GPT-5.4 + Gemini 3.1 Pro. Gemini clean; GPT
  ship-with-fixes.
- **Findings addressed:** (a) GPT — the stub DELETE wasn't in the spec's count/AC → fixed
  above; (b) code+doubt — the global `fixtures/` prune was too broad for arbitrary brownfield
  repos → narrowed to `tests/`-tree scope + test; (c) code — one allow-marker reason was
  factually inverted (`test_github_api_artifact.py:473`, a gitignored dev-local sample) → reason
  corrected. Non-blocking "defensive-committed-file could be CI-GUARD" nit accepted as-is
  (ADR-045 sanctions the marker for genuinely-conditional skips).

## Confidence Calibration
- **Boundaries touched:** test files only (28) + `traceability_skip_inventory.py` (adopt lib).
  No `touches_io_boundary`, no `cross_component`, no product source. Risk flags: none.
- **Empirical probes run:**
  - Re-ran `repo_wide_skip_inventory` on the current tree → 51 findings (authoritative baseline).
  - Confirmed CI provisions git/uv/coverage but NOT node (ci.yml) → GROUP A safe, npx→ALLOW-MARK.
  - Confirmed `vite-hono.json` EXISTS → GROUP C skipif is dead (always False).
  - Confirmed `auth.spec.ts` skip is asserted-upon by 5 compliance tests → must stay skipped.
  - Confirmed only 1 finding lives under a `fixtures/` dir (all under a `tests/` tree) → the
    `tests/`-scoped prune subtracts exactly it, leaving a non-`tests` `fixtures/` still scanned.
- **Test Completeness Ledger:** table in the F5 block / PR body — every behavior `tested` or
  `untestable` w/ reason_code; 0 untested-testable.
- **Confidence-pattern check:** depth — re-running the exact producing scanner is the falsifiable
  asymptote (0 findings ⇒ done); breadth — all 5 treatment classes exercised; no integration
  composition needed (no cross_component machinery touched).
