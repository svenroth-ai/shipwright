# ADR-102: Extract the cross-platform `_FileLock` class into `lib/file_lock.py`

- Status: Accepted
- Date: 2026-06-13
- Run-ID: iterate-2026-06-13-shc-file-lock
- Campaign: 2026-06-13-shared-helper-consolidation (sub-iterate A)
- Spec Impact: NONE (pure behavior-preserving refactor; change_type=tooling)

## Context

Reducibility-catalog D-finding (duplication). The block-until-acquired
cross-platform `_FileLock` class was copied near-identically in
`shared/scripts/tools/record_event.py` and `shared/scripts/triage.py`. The
triage copy had already diverged: its `__enter__` did
`self._lock_path.parent.mkdir(parents=True, exist_ok=True)` — a strict
superset the record_event copy lacked.

## Decision

Extract ONE `FileLock` class into the EXISTING module
`shared/scripts/lib/file_lock.py` (which already hosted a *different*
primitive: the timeout-based `file_lock()` context-manager function used by
`append_changelog_entry.py` / `append_phase_history.py`; that function and its
`LockTimeout` are untouched). Both call sites import it aliased to the
historical private name: `from lib.file_lock import FileLock as _FileLock`.

The alias is load-bearing — `record_event._FileLock` is monkeypatched by the
F14 lifecycle-integrity test, and `triage._FileLock` is imported by
`sweep_outbox.py`, `triage_gc.py`, `reconcile_triage.py`, and
`test_triage_wp9_sanitize_outbox.py`. Re-exporting the alias keeps all those
references working with zero edits, which is the spec-mandated minimal surface.

Unified on the triage variant (parent-dir mkdir on enter) so neither call
site regresses. The only other prior divergence was the placement of the
`import time` statement (record_event imported it inside the except loop;
triage at the top of the win32 branch) — the shared class uses the
module-level `time` import already present in `file_lock.py`; behaviour
(0.001s poll, OSError catch, blocking flock on POSIX, LK_UNLCK + close on
exit) is otherwise byte-for-byte identical.

## Self-Review (7-item)

1. Spec Compliance — PASS (all AC met; existing assertions unchanged).
2. Error Handling — PASS (OSError catch/retry + exit cleanup preserved).
3. Security Basics — PASS (lock paths internal-derived; default-umask mkdir
   matches the already-shipped triage behaviour).
4. Test Quality — PASS (new focused test: mutual-exclusion via real threads,
   parent-dir creation, reuse, cross-module class identity).
5. Performance Basics — PASS (no semantic / poll-interval change).
6. Naming & Structure — PASS (`FileLock` class vs `file_lock()` function
   distinction documented in module docstring).
7. Affected Boundaries (ADR-024) — PASS (JSONL append-log format unchanged;
   only the guarding mutex moved; round-trip probes ran — see below).

## External-Plan-Review-Findings

| # | Provider | Severity | Finding | Disposition |
|---|----------|----------|---------|-------------|
| 1 | openai | medium | Import-context: `from lib...` only works with `shared/scripts` on sys.path | accepted-and-fixed — added sys.path bootstrap to triage.py (record_event.py already had one); verified by real `record_event` CLI invocation + full suite |
| 2 | openai | medium | Class identity may be missed by subtle consumers | accepted-and-fixed — added `record_event._FileLock is triage._FileLock is FileLock` compat assertion |
| 3 | openai | medium | Ensure no behavioral divergence beyond mkdir | accepted — diffed both copies; only `import time` placement differed (no semantic effect) |
| 4 | openai | low | New test may duplicate coverage | rejected-with-reason — test is tight (3+1 cases) and covers the primitive directly; spec asked for it |
| 5 | openai | medium | Downstream triage consumers under-tested | accepted — ran test_triage_wp9_sanitize_outbox / sweep_outbox / triage_gc / reconcile_triage (all green) |
| 6 | openai | low | mkdir changes failure shape on invalid path | accepted (documented) — internal-derived paths only; pre-existing triage behaviour |
| 7 | openai | low | API confusion (`file_lock()` vs `FileLock`) | accepted-and-fixed — module docstring delineates the two primitives |
| 8 | openai | low | Lockfile path trust | rejected-with-reason — all lock paths are trusted internal `.shipwright/*.lock` |
| 9 | gemini | medium | Private-alias re-export is an anti-pattern; update the 4 downstream files | rejected-with-reason — spec scopes this sub-iterate to the two call sites + explicitly allows aliasing; touching 4 more files is scope creep (Karpathy #3 Surgical) |
| 10 | gemini | low | API confusion | accepted-and-fixed (see #7) |
| 11 | gemini | low | umask on auto-mkdir could loosen perms | rejected-with-reason — no security-sensitive dirs; pre-existing shipped behaviour |
| 12 | gemini | medium | Unidentified OS-specific divergence | accepted (see #3) — strict diff confirmed |

## External-Code-Review-Findings

| # | Provider | Severity | Finding | Disposition |
|---|----------|----------|---------|-------------|
| 1 | openai | medium | `__exit__` doesn't reset `self._fp = None` (stale closed handle on reuse / double-exit) | accepted-and-fixed — wrapped unlock+close in try/finally that sets `self._fp = None`; no locking-behaviour change; re-verified by F14 + cross-process tests |
| 2 | openai | low | Direct test is thread-only, not cross-process | accepted — cross-process contract already covered by existing `test_sweep_outbox_concurrency.py` + `test_d2v_empirical_gate.py` on the same shared class |
| 3 | gemini | — | (malformed chain-of-thought; no actionable finding) | n/a |

## Confidence Calibration

- Probes run (4): (1) `record_event` CLI round-trip into a temp project;
  (2) parent-dir-creation acquisition (lock 3 dirs deep into a missing path);
  (3) cross-process mutual exclusion (sweep_outbox_concurrency + d2v
  empirical gate, OS-level msvcrt/fcntl); (4) triage append→read round-trip
  into a fresh `.shipwright`-less project (exercises mkdir-on-enter via the
  shared class).
- Probes with findings: 0 (the `__exit__` reset was a code-review finding,
  not a probe; fixed + re-verified).
- Edge cases not probed + why acceptable: invalid/permission-blocked lock
  parent path — lock paths are internal-derived `.shipwright/*.lock` under the
  project root (never untrusted); surfaces OSError identically to the
  pre-existing shipped triage behaviour, so no new exposure.
- Asymptote reached: yes (two consecutive clean probes).
