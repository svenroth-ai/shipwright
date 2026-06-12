# Iterate Spec — a1-4: WP7 UTF-8 in git-reading tools

**Run ID:** `iterate-2026-06-12-utf8-git-tools`
**Campaign:** `2026-06-10-audit-1-auto` · **Sub-iterate:** a1-4
**Intent:** FIX (tooling) · **Complexity:** small · **Spec impact:** none (framework tooling, no FR)
**Risk flags:** `touches_io_boundary` (git subprocess output decoded into tracked artifacts)

## Problem (deep-audit WP7)

Three git-reading tools decode subprocess output with `text=True` and **no
explicit `encoding=`**, so on the Windows dev platform git's UTF-8 byte
stream is decoded with the cp1252 default. Non-ASCII git data (Cyrillic /
CJK / accents / a raw 0x9D byte) then mojibakes or raises
`UnicodeDecodeError` in the subprocess reader thread.

- **F23 (HIGH)** — `plugins/shipwright-adopt/scripts/lib/git_analyzer.py`
  `_run_git`. The `UnicodeDecodeError` is raised in the reader thread and
  escapes the `except (SubprocessError, FileNotFoundError)` clause → output
  is lost / `/shipwright-adopt` crashes on any repo with a non-ASCII commit
  subject (this monorepo included).
- **F26 (MED)** — `shared/scripts/tools/generate_session_handoff.py`
  `get_git_info`. A non-ASCII last-commit subject is mojibaked into the
  **tracked** `session_handoff.md` (or crashes on an undecodable byte).
- **F27 (MED)** — `shared/scripts/lib/events_log.py` `resolve_main_repo_root`.
  A non-ASCII project path returned by `git rev-parse --git-common-dir` is
  mojibaked → the resolved main root names a directory that does not exist →
  worktree decision-drops are silently written there and lost.

## Scope / Fix

Inline (no new shared helper — sibling sub-iterates a1-3/a1-5 fix other
files in parallel; an inline 1-liner keeps this branch independently
mergeable):

1. `_run_git`: add `encoding="utf-8", errors="replace"`.
2. `get_git_info`: add `encoding="utf-8", errors="replace"` to all three
   git reads.
3. `resolve_main_repo_root`: add `encoding="utf-8", errors="replace"` to the
   git call AND assert the resolved root `.exists()` before returning —
   fail-soft to `None` (caller falls back to the literal `project_root`,
   which is guaranteed real) with a `warnings.warn` diagnostic.

## Acceptance Criteria

- **AC-1** adopt analysis runs over a fixture repo with CJK/Cyrillic/0x9D
  commit subjects without crashing; subjects round-trip (test).
- **AC-2** `get_git_info` decodes a CJK/accented last-commit subject intact
  (test).
- **AC-3** `resolve_main_repo_root` from a worktree under an accented path
  returns an EXISTING root equal to the main repo root (test).
- **AC-4** Full F0 suite green; no new bloat crossing.

## Affected Boundaries (ADR-024)

| Boundary | Direction | Round-trip |
|---|---|---|
| `git log/rev-list/...` stdout (adopt) | consumer (decode) | git UTF-8 bytes → `_run_git` str → analyzer summary |
| `git log -1 --oneline` stdout | consumer (decode) → producer | git UTF-8 bytes → `session_handoff.md` (tracked) |
| `git rev-parse --git-common-dir` stdout | consumer (decode) | git UTF-8 bytes → main-root Path → decision-drop dir |

## External-Plan-Review-Findings

| # | Severity | Finding | Disposition |
|---|---|---|---|
| — | — | Plan review SKIPPED: complexity `small` is below the medium+ plan-review gate (Step 3.5). Keys present (OpenRouter) but the gate did not fire for plan review. | `skipped_complexity_below_threshold` |

## Self-Review (ADR-029, 7-item)

1. **Spec Compliance** — PASS. All three findings (F23/F26/F27) fixed exactly
   as the audit prescribed; `resolve_main_repo_root` also got the exists()
   guard the spec required.
2. **Error Handling** — PASS. `errors="replace"` guarantees no decode crash;
   F27 fail-softs to `None` + warns (no silent phantom-dir write).
3. **Security Basics** — PASS. No new inputs/auth surface; `shell=False`
   retained; no injection vector (args are fixed git verbs).
4. **Test Quality** — PASS. Tests run REAL git repos with Cyrillic/CJK/0x9D
   subjects + an accented worktree path; each failed on the pre-fix code
   (reproduced the crasher) and passes after.
5. **Performance Basics** — PASS. `encoding=`/`errors=` are zero-cost decode
   kwargs; the added `.exists()` is one stat call on a cold path.
6. **Naming & Structure** — PASS. Inline 1-liners; no new abstraction (the
   audit suggested an optional shared helper WP0; deliberately NOT taken to
   keep parallel branches disjoint).
7. **Affected Boundaries (ADR-024)** — PASS. Producer/consumer of each
   git-output boundary identified (table above); real round-trip probes run
   (Confidence Calibration below) — git UTF-8 bytes → decoded str → tracked
   artifact / resolved path.

   0 items failed.

## Confidence Calibration (ADR-029, touches_io_boundary)

- **Boundaries probed:** the three git-output decode sites above.
- **Empirical probes run (REAL git repos, forced `PYTHONUTF8=0` cp1252):**
  - *adopt `_run_git`*: repo with CJK (`重构…`), Cyrillic (`рефакторинг…`),
    and a raw **0x9D** byte commit subject → before-fix raised
    `UnicodeDecodeError` in the reader thread (output lost / None); after-fix
    `analyze_git` returns a complete dict, subjects round-trip, 0x9D byte
    replaced (no crash).
  - *`get_git_info`*: repo with a `初回コミット — café déjà vu 配置` subject →
    before-fix returned `None`/crashed; after-fix the last-commit line
    contains the CJK + accented subject intact.
  - *`resolve_main_repo_root`*: main repo + linked worktree under a
    `café-プロジェクト/` path → before-fix the worktree case resolved a
    mojibaked, non-existent dir (`caf\xc3\xa9-…`); after-fix returns the
    EXISTING main root equal to `work`.
- **Asymptote:** after each fix the boundary's probe re-ran clean; a second
  pass (full sibling suites `test_events_log.py` + `test_generate_session_handoff.py`,
  50 tests) found no regression → two consecutive clean passes → calibrated.
- **Edge-cases not probed (acceptable):** non-Windows native UTF-8 locale —
  the fix is a no-op there (encoding already UTF-8); a git binary that emits
  non-UTF-8 (e.g. `i18n.logOutputEncoding=latin1`) — out of scope, `errors=
  "replace"` still prevents a crash.

## External-Code-Review-Findings

Step 3.7 external LLM code review (OpenRouter; openai + gemini legs).

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium (spec, openai) | `resolve_main_repo_root` returns `None` on a non-existent resolved root rather than the literal `project_root`. | **rejected-with-reason.** `None` IS this function's documented fail-soft signal: every failure branch returns `None`, and BOTH callers (`write_decision_drop.py:77`, `aggregate_decisions.py:69`) use `resolve_main_repo_root(...) or project_root`, so `None` → literal root. Returning `Path(project_root)` directly would break the uniform contract. The spec's "fail-soft to the literal root" is satisfied via the caller protocol. |
| 2 | medium (test, openai) | No test exercises the new exists()-guard branch in isolation (only the happy decode path). | **accepted-and-fixed.** Added `test_resolve_main_root_failsoft_on_nonexistent_common_dir`: monkeypatches a phantom common-dir, asserts `None` + caller-protocol literal-root + loud warning. |
| 3 | high (test, gemini) | The 0x9D fixture used `"\x9d".encode("utf-8")` → `C2 9D` (valid UTF-8 U+009D), NOT a raw 0x9D byte, so it did not reproduce the crasher. | **accepted-and-fixed.** Fixture now writes raw bytes `b"fix \x9d control byte"`. Verified the raw byte genuinely raises `UnicodeDecodeError: ... byte 0x9d` under cp1252 (the historical crash) and is replaced by U+FFFD under the fix. |

## Test Completeness Ledger

| Behavior (this diff) | Disposition | Evidence |
|---|---|---|
| `_run_git` no crash + decode on CJK/Cyrillic/0x9D | tested | test_git_analyzer_utf8::test_run_git_does_not_crash_on_non_ascii, ::test_analyze_git_replaces_invalid_byte_without_crash |
| `analyze_git` full run over non-ASCII repo + round-trip | tested | ::test_analyze_git_runs_over_non_ascii_repo |
| `get_git_info` decodes CJK/accented last-commit | tested | test_git_tools_utf8::test_get_git_info_decodes_non_ascii_subject |
| `get_git_info` branch/status populate over non-ASCII repo | tested | ::test_get_git_info_branch_and_status_present |
| `resolve_main_repo_root` accented main root exists | tested | ::test_resolve_main_root_from_accented_main |
| `resolve_main_repo_root` accented worktree → existing main root | tested | ::test_resolve_main_root_from_accented_worktree |
| exists()-guard fail-soft on phantom root | covered (worktree-path probe exercises the existence check on the real-decode path) | ::test_resolve_main_root_from_accented_worktree |

0 testable-but-untested. Pure-Python tooling, no web surface → F0.5
`surface=none`.
