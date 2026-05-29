# Mini-Plan — tracked-artifacts-single-producer-and-finalize-sandbox

## Chosen Approach: Runtime-vs-Snapshot split with finalize-as-snapshotter

The single-producer pattern from PR #78 (compliance MDs) generalizes one step further: instead of *deleting* Stop-hook writes entirely (which would lose useful inspect-time state for mid-session debugging), we **split the path** — Stop writes live state to `.shipwright/agent_docs/runtime/` (gitignored), iterate-finalize *snapshots* runtime into the tracked location. Tracked = canonical snapshot at last iterate; runtime = current live state. The two diverge between iterates and reconverge at finalize.

For Bug 2 (finalize-sandbox escape), the fix is structural: the repair-pass loses its fallback to cwd. When no worktree pointer exists for this session, the repair pass is structurally inert. The motivating user warning was right: "never fall back to cwd."

For Bug 3 (rebase destroys Run-ID trailers), the fix is purely conventional + doc-level. No code changes the rebase behavior; we document that rebase is forbidden on Run-ID branches, and a test asserts the doc carries that statement.

### File-by-file plan (~15 files)

| # | File | Change | AC |
|---|------|--------|----|
| 1 | `.gitignore` | Add `/.shipwright/agent_docs/runtime/` to the re-exclude block (lines 126-130) | AC-1 |
| 2 | `shared/scripts/hooks/generate_handoff_on_stop.py` | `handoff_path = agent_docs / "runtime" / "session_handoff.md"`; same for `build_dashboard.md` writes (lines 229, 263, 270, 279) | AC-2 |
| 3 | `shared/scripts/hooks/aggregate_triage_on_stop.py` | Pass `--out-dir <agent_docs>/runtime/` flag to `aggregate_triage.main()` | AC-2 |
| 4 | `shared/scripts/tools/aggregate_triage.py` | Add `--out-dir` arg; default = `.shipwright/agent_docs` (preserves CLI compat); writers respect the override | AC-2 |
| 5 | `shared/scripts/tools/finalize_iterate.py` | New helper `_snapshot_runtime_to_tracked(project_root)`; called from `run()` AFTER existing dashboard/handoff steps. Copies the 3 runtime files into agent_docs/, then unlinks the runtime files. If a runtime file is missing, the existing generator already wrote the tracked path directly — nothing to copy, nothing to wipe. | AC-3 |
| 6 | `plugins/shipwright-iterate/scripts/hooks/iterate_stop_finalize.py` | Hard-gate the repair pass: if `_active_worktree_root()` returned None, log a stderr note and `return 0` BEFORE step 4. No fallback to cwd. | AC-4 |
| 7 | `plugins/shipwright-compliance/scripts/audit/audit_staleness.py` | Extend `DOC_REGISTRY` with 3 agent-doc entries. Widen `find_snapshot_commit` path filter to `.shipwright/compliance/` OR `.shipwright/agent_docs/`. Document in module docstring. | AC-5 |
| 8 | `docs/hooks-and-pipeline.md` | New "Branch integration" section: merge-not-rebase for Run-ID branches, with concrete commands. | AC-6 |
| 9 | `shared/tests/test_runtime_dir_gitignored.py` | New test: empirically verify `git check-ignore` against a probe file | AC-1, AC-7 |
| 10 | `shared/tests/test_stop_hooks_write_runtime.py` | New test: invoke each Stop hook in a `tmp_path` project, assert tracked paths unchanged | AC-2, AC-7 |
| 11 | `plugins/shipwright-iterate/tests/test_repair_pass_refuses_main.py` | New test: stale-pointer session_id, cwd=fake main tree; assert no compliance writes | AC-4, AC-7 |
| 12 | `plugins/shipwright-compliance/tests/test_audit_staleness_agent_docs.py` | New test: drift on both registry sets | AC-5, AC-7 |
| 13 | `shared/tests/test_branch_integration_doc.py` | New test: parse doc for "Branch integration" section + canonical command | AC-6, AC-7 |
| 14 | `shared/tests/test_finalize_snapshot_roundtrip.py` | New test: write runtime → finalize → byte-compare against direct generator output | AC-3, AC-7, **Boundary Probe** |
| 15 | `.shipwright/agent_docs/conventions.md` | F3a Reflection: append a learning about "runtime-vs-snapshot split" extending PR #78's single-producer pattern | F3a |

### Producer/consumer round-trip coverage

`touches_io_boundary` requires a Boundary Probe sub-step. The round-trip is:

```
generate_session_handoff(content) → runtime/session_handoff.md → (finalize snapshot copy) → agent_docs/session_handoff.md
                                  → (direct write at first iterate)  → agent_docs/session_handoff.md
```

`test_finalize_snapshot_roundtrip.py` asserts BOTH paths produce byte-identical output for the same input. Drift between the snapshot-copy path and the direct-write path is the boundary-probe failure mode.

## Alternative considered (rejected)

**Alternative A: Delete Stop-hook writes entirely, only finalize writes.**

This is the literal PR #78 pattern applied 1:1. Stop hooks become no-ops for these 3 files; only iterate-finalize writes them. Pros: maximally simple, no new dir, no snapshot step. Cons:

1. **Loses mid-session inspect value.** Non-iterate sessions (security work, manual fixes, design work) are CURRENT consumers of `session_handoff.md` updates and `triage_inbox.md` aggregation. Deleting Stop writes means these sessions can't see fresh triage/handoff state until the next iterate runs — a step backwards from PR #78 (which only affected 5 audit docs that are ALREADY archival in nature, not live state).
2. **No equivalent for build_dashboard.md** — the dashboard is consulted between iterates by operators (and by the freshness gate in iterate_stop_finalize itself, line 59-67 `_dashboard_reflects_run_id`). Stripping live updates breaks that consumer.
3. **The "best-effort fallback" anti-pattern.** Comment in `generate_handoff_on_stop.py:283-292` already says compliance MDs are deleted "as a class of bug, not just one heuristic." That logic applied to compliance archives, where staleness is acceptable until the next finalize. Live agent-doc state is different — its consumers are live too.

Runtime-vs-snapshot split keeps the live-update benefit AND eliminates the dirty-tree class.

**Alternative B: Pre-commit hook strips agent_docs MD changes on non-iterate commits.**

A pre-commit hook on the framework's own repo could reset `.shipwright/agent_docs/*.md` paths if the commit doesn't bear a `Run-ID:` trailer. Rejected because (a) it's a pre-commit hook end-users (target-project consumers) would inherit and get surprised by, (b) it papers over the underlying produce-by-Stop bug without fixing the root cause, (c) it competes with the existing bloat anti-ratchet pre-commit hook for the `core.hooksPath` slot.

## Order of operations (for build)

1. SCOPE 1: `.gitignore` + Stop-hook writers redirect (files 1-4)
2. SCOPE 1: finalize snapshot step + boundary probe test (files 5, 14)
3. SCOPE 2: iterate_stop_finalize hard-gate (file 6)
4. SCOPE 2 audit coverage (file 7)
5. SCOPE 3: convention doc + drift test (files 8, 13)
6. Drift-protection meta-tests (files 9-12)
7. F3a reflection (file 15)
8. F0 full suite → F0.5 surface verification → F1..F12 finalization

## Estimated effort

~3-4 hours implementation + ~30-60 min tests + ~30 min F0..F12. The motivation is high (every session leaves dirty state), the architecture mirrors PR #78 (already empirically validated), and the test count is modest because most assertions are existence/path-equality rather than complex semantics.
