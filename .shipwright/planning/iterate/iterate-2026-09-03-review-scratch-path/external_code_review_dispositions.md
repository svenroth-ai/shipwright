# External-Code-Review-Findings (for the iterate ADR, F3)

Verdicts: glm=revise, openai=revise (no contradiction — both converge on the
same core issues, read two ways).

| # | Severity | Reviewer | File | Finding | Disposition |
|---|---|---|---|---|---|
| 1 | medium | glm+openai | code-review-protocol.md:11-25 | Step 1's "keep this resolved path in hand for step 2 and cleanup" instructs carrying a value across separate Bash tool calls — the exact AC-forbidden pattern. | accepted-and-fixed: reworded so step 2 independently re-resolves via its own `$(...)` invocation; step 1 now says "never carry ... across a separate Bash tool call." |
| 2 | medium | openai | review_scratch.py:38-43 | Component validation accepted case-insensitive alias collisions (`Foo`/`foo`) and Windows reserved device names (`CON`, `NUL`), risking one run's cleanup silently removing another's snapshot on a case-insensitive filesystem. | accepted-and-fixed: `_validate_component` now canonicalizes to lowercase (callers use the returned, canonicalized value for path construction) and rejects `con/prn/aux/nul/com[1-9]/lpt[1-9]` (with or without an extension) via `_WIN_RESERVED_RE`. |
| 3 | medium | openai | code-review.md / sub-iterate-runner.md | Cleanup is not guaranteed on the failure path — prose saying "run on failure" doesn't structurally guarantee it when a Bash-tool call fails and execution stops. | rejected-with-reason: this is the exact tradeoff the user-approved Architecture Review reconciliation already made when dropping the self-healing sweep — a leftover file in the private, ACL-hardened, per-user root is accepted as a non-problem, not a target for garbage collection or a bash `trap EXIT` (which also doesn't compose across the Agent-tool-call boundary these flows cross). Re-litigating cleanup-on-failure guarantees would reinstate the complexity the Architecture Review explicitly declined. |
| 4 | low | openai | review_scratch.py:75-82 | `cleanup()`'s `Path.exists()` returns False for a dangling symlink, so a dangling reparse point at `run_root` was treated as "missing" and skipped past the reparse-point rejection. | accepted-and-fixed: `cleanup()` now checks `run_root.is_symlink()` in addition to `.exists()` before the early no-op return, so a dangling symlink still reaches the hardening checks below. |
| 5 | low | glm | autonomous_loop.py:161-171 | Empty/malformed stdin raised an unhandled `JSONDecodeError` traceback instead of the file branch's clean error. | accepted-and-fixed: explicit empty-stdin check plus a `try/except json.JSONDecodeError` around the parse, both returning a clean `ERROR:` message. New regression test: `test_init_reports_a_clean_error_on_empty_stdin`. |
| 6 | low | glm | test_review_scratch_guard.py:50 | The non-empty-glob sentinel used an aggregate `> 50` threshold, which stays "healthy" even if one of the three glob trees goes silently empty. | accepted-and-fixed: now asserts each of the three glob patterns individually matches at least one file. |
| 7 | low | glm | test_review_scratch.py / test_campaign_units_stdin_pipe_integration.py | In-process unit tests monkeypatch the private base, so the real hardened-root resolution is only exercised by the one subprocess contract test (happy path only). | disclosed, no_change_needed: acceptable given the 43-test pre-existing `host_resource_lease`/`_host_resource_locking` suite already covers the fail-closed `TMPDIR` override contract directly; adding a redundant subprocess-level pin was judged not worth the extra `uv run` cost for this fix. |
| 8 | low | glm | code-review.md (cascade step 1) | The cascade's Branch A step-1 bash block is a bare `resolve` call whose stdout goes nowhere — dead command. | accepted-and-fixed: same fix as the internal code-reviewer's identical finding — removed the dead command, folded the rationale into prose. |
| 9 | low/informational | glm | (spec) | Post-merge marketplace-sync AC correctly disclosed and ordered. | no_change_needed: already tracked as an open AC. |

**Status:** 6 accepted-and-fixed, 1 rejected-with-reason, 2 no_change_needed,
0 declined-without-reason. No finding named an unaddressed defect after
triage; the case-collision, dead-command, and cleanup-guarantee findings
overlap substantially with the internal `code-reviewer`'s independent pass
(same root issues, different angle), confirming both passes converged.
