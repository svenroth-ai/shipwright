# ADR-103: Fold `spec_checks` git wrappers onto `verifiers/git_helpers.py`

- Status: Accepted
- Date: 2026-06-13
- Run-ID: iterate-2026-06-13-shc-git-helpers
- Campaign: 2026-06-13-shared-helper-consolidation (sub-iterate C)
- Spec Impact: NONE (pure behavior-preserving consolidation; change_type=tooling)

## Context

Reducibility-catalog D/A-finding (duplication). `spec_checks.py` re-defined
`_run_git` / `_git_available` (~lines 331,350) although
`verifiers/git_helpers.py` already provides them. The two `_run_git` variants
DIFFERED, which was the medium risk:

- `git_helpers._run_git(project_root, *args)` — `["git","-C",str(project_root),*args]`,
  returns `(rc,out,err)`, failure → `(1,"",""`), no timeout.
- `spec_checks._run_git(project_root, *args, timeout=10.0)` — `cwd=str(project_root)`,
  `encoding="utf-8", errors="ignore"`, `timeout=`, failure → `(-1,"",str(exc))`.

## Decision

1. Add an optional `timeout: float | None = None` param to
   `git_helpers._run_git`. The `timeout` kwarg is forwarded to
   `subprocess.run` ONLY when the caller set it (conditional kwargs build) —
   so an un-timed call keeps the exact kwarg shape it had before this param
   existed, leaving existing callers (`iterate_checks.py`,
   `integration_coverage.py`) byte-for-byte unchanged. Also added
   `encoding="utf-8", errors="ignore"` (matches the
   spec_checks variant's robustness; harmless for existing callers since
   `text=True` already decoded utf-8). Kept the `git -C` form and `(rc,out,err)`
   contract.

2. **Error-code reconciliation — unified on `1`.** Audited EVERY caller of
   `_run_git` / `_git_available` repo-wide (not only spec_checks). NO caller
   branches on the specific value `-1`, `1`, or `< 0` — all use `rc == 0` /
   `rc != 0`. Therefore unifying on git_helpers' existing `1` (and catching
   `subprocess.TimeoutExpired` → `(1,"","")`) is safe. See the audit table below.

3. `spec_checks.py` imports `_run_git, _git_available` from
   `tools.verifiers.git_helpers` (absolute form, matching its existing sibling
   import `tools.verifiers._iterate_run_id`); local defs deleted; the now-unused
   `import subprocess` removed.

4. Timeout parity preserved: all six `_run_git` call sites in spec_checks pass
   `timeout=10.0` explicitly (the value the deleted local default supplied).
   `_git_available`'s internal `rev-parse` is the one path that loses the 10s
   timeout — accepted: it is an instant local op, the timeout there was purely
   defensive, and it now matches the shared `iterate_checks` behaviour.

### Error-code audit (caller → rc branch)

| Caller | rc inspection | Depends on -1/1 specifically? |
|---|---|---|
| spec_checks `_git_available` (now shared) | `rc == 0` | no |
| spec_checks S4 `log` | `rc != 0 or not log_out` | no |
| spec_checks S4 `diff` | `rc != 0` | no |
| spec_checks `_is_ui_facing_iterate` | `rc != 0` | no |
| spec_checks `_readme_touched_recently` | `rc != 0` | no |
| spec_checks `_new_top_level_dirs` | `rc != 0` | no |
| spec_checks `_claude_md_touched_recently` | `rc != 0` | no |
| iterate_checks (2 sites) | `rc != 0` | no |
| integration_coverage (3 sites) | `rc == 0` | no |

Conclusion: every caller is success-vs-non-success only. Unifying on `1` is safe.

## Self-Review (7-item)

1. Spec Compliance — PASS (all 5 AC met; spec_checks assertions unchanged, G3 held).
2. Error Handling — PASS (OSError/ValueError/TimeoutExpired all caught → `(1,"","")`;
   no failure path now returns `-1`, and no caller cared).
3. Security Basics — PASS (both impls `shell=False` arg-list; no untrusted
   interpolation; `git -C` scopes the repo; read-only commands only).
4. Test Quality — PASS (new `test_git_helpers.py`: success, missing-binary,
   timeout-expired, default-no-timeout passthrough, explicit-timeout passthrough,
   git_available on/off repo. No assertion weakened.).
5. Performance Basics — PASS (no semantic change; one helper instead of two copies).
6. Naming & Structure — PASS (shared wrapper has a single home; ~25 LOC removed).
7. Affected Boundaries (ADR-024) — PASS. Boundary = the subprocess→git CLI text
   boundary. Producer = git CLI, consumer = the verifier checks. Round-trip probe:
   ran the S4/S9/S10 checks against REAL git repos via `test_spec_checks.py` (the
   `cwd=`→`git -C` swap is transparent) AND added direct `_run_git` real-repo
   probes in `test_git_helpers.py`. No serialized-file format changed.

## External-Plan-Review-Findings

| # | Provider | Severity | Finding | Disposition |
|---|----------|----------|---------|-------------|
| 1 | openai | high | Plan didn't state which rc convention is canonical / blast radius | accepted-and-validated — unified on git_helpers' `1`; audited ALL callers repo-wide; none branch on a specific value (see audit table) |
| 2 | openai | high | Audit must cover all git_helpers callers, not just spec_checks | accepted-and-validated — audited iterate_checks + integration_coverage too; all `== 0`/`!= 0` only |
| 3 | openai | medium | AC only requires test_spec_checks green; add helper-level tests | accepted-and-fixed — added test_git_helpers.py (success/non-zero/missing/timeout) |
| 4 | openai | medium | timeout semantics undefined (TimeoutExpired path) | accepted-and-fixed — catch subprocess.TimeoutExpired → `(1,"","")`; pinned by test |
| 5 | openai | medium | git_helpers may lack `cwd=`; import would break | rejected-with-reason — git_helpers uses `git -C <root>`, functionally equivalent to `cwd=<root>` for these ops; no `cwd` param needed; all call sites pass a repo root; full suite green |
| 6 | openai | medium | Classify each branch: success-only vs wrapper-vs-command failure | accepted-and-validated — audit table shows every branch is success-vs-non-success only |
| 7 | openai | medium | Validate stderr/message parity | accepted-and-validated — every `_run_git` caller discards `err` (binds to `_`); no test asserts stderr text |
| 8 | openai | low | Centralizing exec raises injection/path-traversal importance | accepted-and-validated — `shell=False` arg-list in both; `git -C` scoping; no untrusted interpolation |
| 9 | openai | low | Diff `_git_available` impls before deletion | accepted-and-validated — identical (`rev-parse --is-inside-work-tree`, `rc == 0`), no caching; only the failure-rc differed (addressed in #1) |
| 10 | openai | low | "Prove parity" underspecified | accepted-and-fixed — parity points (signature, rc for success/non-zero/missing/timeout, cwd-equiv, stderr) covered by helper tests + audit table |
| 11 | gemini | high | "no assertion changes" impossible if tests assert `-1` | rejected-with-reason — test_spec_checks.py uses REAL git repos and asserts STATUS_*; it never asserts the raw rc; all 63 stayed green unchanged |
| 12 | gemini | medium | Add `cwd=None` param to git_helpers | rejected-with-reason — duplicate of #5; `git -C` already provides the scoping |
| 13 | gemini | medium | Map TimeoutExpired to unified rc | accepted-and-fixed — same as #4 |
| 14 | gemini | low | Standardize on `1`, don't change git_helpers return values | accepted-and-validated — exactly the chosen approach; git_helpers' success/non-zero codes unchanged, only the failure sentinel is now shared |

## External-Code-Review-Findings

| # | Provider | Severity | Finding | Disposition |
|---|----------|----------|---------|-------------|
| 1 | openai | medium | `_run_git` passed `timeout=timeout` unconditionally; spec says forward "only when set" | accepted-and-fixed — build subprocess kwargs conditionally, add `timeout` only when `timeout is not None`; un-timed callers keep the exact prior kwarg shape |
| 2 | openai | medium | `test_run_git_default_passes_no_timeout` baked in `timeout=None` (wrong per spec) | accepted-and-fixed — renamed to `test_run_git_default_omits_timeout_kwarg`; now asserts `"timeout" not in kwargs` |
| 3 | gemini | n/a | Provider returned a truncated/garbled response (no actionable finding) | rejected-with-reason — non-parseable provider artifact; openai leg covered the same diff substantively |

## Confidence Calibration

Boundary touched: the subprocess→git-CLI text boundary (no serialized FILE format).

- Probes run:
  1. Real-repo round-trip via `test_spec_checks.py` S4/S9/S10 (init repo, commit,
     run check) — exercises the `cwd=`→`git -C` swap end-to-end. → no findings.
  2. Direct `_run_git` real-repo probe (`rev-parse --is-inside-work-tree` → `"true"`).
     → no findings.
  3. Missing-binary probe (FileNotFoundError) → `(1,"","")`. → no findings.
  4. TimeoutExpired probe → `(1,"","")`. → no findings.
  5. Default-no-timeout passthrough probe (`timeout` forwarded as `None`). → no findings.
- Asymptote: probes 1–5 each ran; the last two consecutive probes (default-passthrough,
  explicit-timeout passthrough) found nothing → boundary calibrated.
- Edge-cases not probed: undecodable-bytes output (now `errors="ignore"`, identical
  to the prior spec_checks behaviour, and no caller inspects raw bytes) — acceptable,
  as this is a strict robustness superset of the pre-existing git_helpers behaviour.
