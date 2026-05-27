# Iterate Spec — tracked-artifacts-single-producer-and-finalize-sandbox

- **Run ID:** `iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox`
- **Intent:** CHANGE
- **Complexity:** medium
- **Spec Impact:** MODIFY — extends PR #78 / ADR-088 / iterate-2026-05-23 single-producer pattern from 5 compliance MDs to 3 agent-doc MDs; AND adds finalize-sandbox gate to a code path that escaped #78.
- **Risk flags:** `touches_io_boundary`, `touches_shared_infra`
- **Affected Boundaries:**
  - Stop-hook → filesystem write surface (`session_handoff.md`, `build_dashboard.md`, `triage_inbox.md`)
  - Iterate-finalize → filesystem write surface (compliance MDs + 3 agent-doc MDs)
  - Session-to-worktree pointer → finalize project_root resolution
  - Git history → branch integration (merge vs rebase preserves Run-ID trailers)
  - `.gitignore` whitelist of `.shipwright/`

## Problem Statement

Verified against session `40b1eb76` end-state: 8 dirty files in main, 49 Stop hooks fired in last turn. Two distinct bugs combine to produce the recurring "main is dirty after every session" pattern:

### Bug 1: Stop-hook tracked-artifact writes (Option B from analysis 2026-05-25)

`shared/scripts/hooks/generate_handoff_on_stop.py` and `shared/scripts/hooks/aggregate_triage_on_stop.py` re-generate THREE tracked artifacts on every Stop event in EVERY plugin (12 plugins × Stop frequency):

| Artifact | Tracked path | Writer (Stop) |
|---|---|---|
| `session_handoff.md` | `.shipwright/agent_docs/session_handoff.md` | `generate_handoff_on_stop.py:270` (also `iterate_stop_finalize` repair, finalize_iterate step 4) |
| `build_dashboard.md` | `.shipwright/agent_docs/build_dashboard.md` | `generate_handoff_on_stop.py:279` (also iterate-finalize step 3) |
| `triage_inbox.md` | `.shipwright/agent_docs/triage_inbox.md` | `aggregate_triage_on_stop.py:72` (also aggregate_triage.py CLI) |

Result: every long-lived branch sees the three tracked files mutated by every Stop in main, producing perpetual merge conflicts and `git status` noise. PR #78 fixed the analogous problem for the 5 compliance MDs (single producer = iterate-finalize). The agent-doc trio was missed.

### Bug 2: Finalize-sandbox escape (newly discovered via verification)

`plugins/shipwright-iterate/scripts/hooks/iterate_stop_finalize.py:106-110` sets `SHIPWRIGHT_PROJECT_ROOT` to the active worktree path ONLY when `_active_worktree_root()` returns non-None. When the per-session pointer is stale (worktree removed post-merge) or never written (non-iterate session), `_active_worktree_root` returns None, the env var stays unset, and `resolve_project_root()` (line 130) falls back to **cwd** — which is the main tree.

The repair pass then runs `finalize_iterate.run(project_root=<main tree>, run_id=<last iterate>)`, writing the 5 compliance MDs + 3 agent-doc MDs into main. PR #78's single-producer guarantee holds at the source-level (only `finalize_iterate` writes) but not at the target-level (writes the wrong tree).

### Bug 3 (process-level): rebase destroys Run-ID trailers on integration

When integrating `main` into a long-lived `iterate/<slug>` branch with a `git rebase`, the rebase re-writes each commit's parent — but it also reapplies commits as new SHAs WITHOUT carrying through the trailer-bearing merge commits. The audit_staleness audit keys on `--grep=Run-ID:` against `git log` on the current branch; rebased branches lose the canonical Run-ID-trailer commits and report false `snapshot_unavailable`. Reachable via:

```
$ git checkout iterate/slug
$ git rebase main          # ← destructive
$ git log --grep=Run-ID    # ← misses any commit re-parented from main
```

## Goal

Eliminate `main is dirty after every session` by extending the single-producer pattern to ALL eight tracked-but-derived MDs (5 compliance + 3 agent-doc) AND closing the finalize-sandbox escape AND codifying merge-not-rebase as the convention for Run-ID-bearing branches.

## Acceptance Criteria

### AC-1: `.shipwright/agent_docs/runtime/` is gitignored

`.gitignore` re-excludes `/.shipwright/agent_docs/runtime/` (alongside `decision-drops/` and `visual/`). A new file written under this path does NOT appear in `git status` on either main or any iterate worktree.

### AC-2: Stop-hook writes redirect to `runtime/`

`generate_handoff_on_stop.py` writes `session_handoff.md` and `build_dashboard.md` under `.shipwright/agent_docs/runtime/` instead of `.shipwright/agent_docs/`. Same for `aggregate_triage_on_stop.py` writing `triage_inbox.md`. Empirical probe: after a Stop event, the three tracked paths are byte-identical to their state pre-Stop.

The phase_task namespaced handoff (`runs/<runId>/<phaseTaskId>/handoff.md`) and the loop-namespaced handoff (`planning/handoffs/<loopId>/<unit>.md`) keep their existing paths — both are already write-isolated per session/run and don't dirty main.

### AC-3: Iterate-finalize snapshots runtime → tracked, then wipes runtime

At F5b, `finalize_iterate.run()` performs a "snapshot" step AFTER the existing dashboard/handoff write steps:

1. Copy `runtime/session_handoff.md` → `agent_docs/session_handoff.md` (if runtime file exists).
2. Copy `runtime/build_dashboard.md` → `agent_docs/build_dashboard.md` (same).
3. Copy `runtime/triage_inbox.md` → `agent_docs/triage_inbox.md` (same).
4. **Wipe** the 3 runtime files (`unlink(missing_ok=True)`). The runtime dir is preserved (Stop hooks recreate with `parents=True, exist_ok=True`).

The snapshot is byte-identical (same producer wrote both runtime and the now-overwriting generator output to tracked). Idempotent: a second finalize call finds no runtime files (wiped by the first) and the tracked files were just regenerated — exits with no diff.

If a `runtime/` file is missing (fresh worktree, first iterate after onboarding, or post-wipe state), finalize calls the existing generator to write directly to the tracked path AND skips the wipe step (nothing to wipe). Subsequent Stop hooks will populate runtime/ as needed.

**Persistence semantics:** runtime files are NEVER long-lived. Either (a) a Stop hook just wrote them and the next iterate-finalize wipes them, or (b) they don't exist (cleanest state). Worst case is one Stop hook's worth of bytes (~3-50 KB total across 3 files) lingering between sessions on a long-running clone.

### AC-4: Finalize repair-pass refuses without valid worktree pointer

`iterate_stop_finalize.py` step 4 (repair pass) MUST exit silently (best-effort no-op + stderr note) when `_active_worktree_root()` returned None earlier in main(). The repair pass NEVER calls `finalize_run(project_root=cwd)` because cwd at Stop-time is the main repo. Test: in a worktree-removed session, the Stop hook produces zero writes to `.shipwright/compliance/*.md` in main.

### AC-5: audit_staleness coverage for agent-doc trio

`audit_staleness.DOC_REGISTRY` extends to include the 3 agent-doc MDs (`session_handoff.md`, `build_dashboard.md`, `triage_inbox.md`) alongside the 5 compliance MDs. The `find_snapshot_commit` lookup widens to either `.shipwright/compliance/` OR `.shipwright/agent_docs/` paths (since finalize writes both sets). Group E audit now catches drift on the agent-doc trio identically to the compliance set.

### AC-6: Convention codified — `git merge`, not `git rebase`, for Run-ID branches

`docs/hooks-and-pipeline.md` gains a "Branch integration" section stating: `iterate/<slug>` and any branch whose commit history contains a `Run-ID:` trailer MUST be integrated into main via `git merge` (no fast-forward where appropriate) so the trailer-bearing commit SHAs stay reachable from main. `git rebase main` on such a branch is forbidden because it re-parents commits and audit_staleness's `--grep=Run-ID:` lookup needs the original SHAs intact.

A new test, `shared/tests/test_branch_integration_doc.py`, parses the doc and asserts the "Branch integration" section names both `merge` and `rebase` and contains the canonical forbidden-pattern command line.

### AC-7: Drift-protection meta-tests

- `shared/tests/test_runtime_dir_gitignored.py` — empirically verifies `.shipwright/agent_docs/runtime/` is ignored via `git check-ignore`.
- `shared/tests/test_stop_hooks_write_runtime.py` — runs each Stop hook in a temp project; asserts no write to tracked agent_docs paths.
- `plugins/shipwright-iterate/tests/test_repair_pass_refuses_main.py` — invokes `iterate_stop_finalize.main()` with `SHIPWRIGHT_SESSION_ID` set to a non-pointer-bearing UUID + cwd at a fake main tree; asserts no compliance writes occur.
- `plugins/shipwright-compliance/tests/test_audit_staleness_agent_docs.py` — drift-protection across both registry sets.

### AC-8: Dogfood — empty `git status` after end of THIS iterate

After this iterate's F11 push completes, `git status` on main shows zero modified files for the duration of the next 3 unrelated `/shipwright-*` invocations (verified via the PR review process). This is the canonical empirical signal that the bug is closed.

## Confidence Calibration

- **Boundaries touched:** Stop-hook write surface (3 files), iterate-finalize write surface (8 files: 5 compliance + 3 agent-doc), `.gitignore` whitelist, finalize project-root resolution, audit_staleness DOC_REGISTRY, branch-integration convention.
- **Empirical probes run:**
  1. **runtime-dir ignore probe** — `git check-ignore` against `.shipwright/agent_docs/runtime/session_handoff.md` returned rc=0 with rule `/.shipwright/agent_docs/runtime/` matched. `git ls-files .shipwright/agent_docs/runtime/` returned empty. **Finding: none.**
  2. **Handoff Stop-hook write probe** — invoked `generate_handoff_on_stop.py` in a tmp project, verified writes land only at `.shipwright/agent_docs/runtime/{session_handoff,build_dashboard}.md` and tracked level stayed empty. **Finding: none.**
  3. **Triage Stop-hook write probe** — invoked `aggregate_triage_on_stop.py`, verified `--out-dir runtime/` flow worked, runtime/triage_inbox.md present, tracked/triage_inbox.md absent. **Finding: none.**
  4. **finalize round-trip probe** — pre-seeded runtime/ with Stop-hook-shape content, ran finalize, verified: handoff at tracked carries canon marker; dashboard at tracked carries `run_id`; triage at tracked = byte-identical copy of runtime; runtime/ is empty post-finalize. **Finding: none.**
  5. **finalize idempotency probe** — ran finalize twice in a row. First call: 3 tracked files written, runtime emptied. Second call: triage seeded via aggregate_triage, runtime stays empty, the difference between the two tracked-triage outputs is timestamp-banner-only and tracks events.jsonl deterministically — **expected divergence, not a bug**.
  6. **Path-escape probe (`--out-dir`)** — passed `--out-dir <project_root>/../escape/` to aggregate_triage; returned rc=2, refused to write outside project_root. **Finding: none.**
  7. **Boundary-asymmetry check** — emit (Stop) and resolve (finalize) both target `runtime/<file>` paths, symmetric by construction not by gate. Cross-checked against learning lines 92/96 about asymmetric gates being the second-most-common boundary-probe failure mode.

- **Edge cases NOT probed + why acceptable:**
  - Cross-machine drift between two operators editing different runtime files concurrently: out of scope; the runtime dir is per-clone, no operator hands runtime/* to another.
  - The phase_task namespaced handoff (`runs/<runId>/<phaseTaskId>/handoff.md`): unchanged in this iterate. It already writes under a per-run subdir that doesn't dirty main.
  - Cross-plugin Stop-hook ordering: orderings between `aggregate_triage_on_stop` (registered LAST) and `generate_handoff_on_stop` are preserved by the redirect — both write to runtime/.
  - Concurrent Stop-hook and finalize executions writing the same `runtime/<name>.md`: atomic `os.replace` makes per-file writes safe; per-file unlink in finalize is best-effort. Acceptable because Stop hooks are per-session-serialized by Claude Code.

- **Edge cases NOT probed + why acceptable:**
  - Cross-machine drift between two operators editing different runtime files concurrently: out of scope; the runtime dir is per-clone, no operator hands runtime/* to another.
  - The phase_task namespaced handoff (`runs/<runId>/<phaseTaskId>/handoff.md`): unchanged in this iterate. It already writes under a per-run subdir that doesn't dirty main.
  - Cross-plugin Stop-hook ordering: orderings between `aggregate_triage_on_stop` (registered LAST) and `generate_handoff_on_stop` are preserved by the redirect — both write to runtime/.

- **Confidence-pattern check (asymptote heuristic):** Probe 4 (snapshot idempotency) directly tests the producer/consumer contract central to AC-3. If it returns no finding, run Probe 6 (round-trip) as the empirical asymptote — if THAT also returns no finding, the marginal probe yields no signal. Pattern matches ADR-024's producer→file→consumer rule. Boundary-asymmetry risk class (per learning lines 92, 96) is mitigated because emit (Stop) and resolve (finalize-snapshot) both target the same `runtime/<file>` paths — symmetric by construction, not by gate.

## Spec Impact (mandatory at medium+)

- **Spec Impact:** MODIFY
- **Affected FRs:** none — this is internal framework plumbing, not a user-facing FR.
- **New FRs:** none.
- **Change type:** internal-correctness fix (closes recurring `git status` dirty-tree class)
- **None reason:** N/A (impact is MODIFY)

## External Review Findings — addressed in build

External review (OpenRouter: openai+gemini, 2026-05-27) returned 14 findings on the plan. Adjustments folded into the build:

- **OpenAI #1 + #14 (high/medium):** finalize-snapshot is COPY-only per-file decision — no "always generate then overwrite". Both runtime-write and finalize-snapshot ultimately call the SAME generator (the runtime write IS the canonical generator output; finalize just copies it). No semantic divergence possible by construction.
- **OpenAI #4 (medium):** per-file atomic replace (`tempfile.NamedTemporaryFile` + `os.replace` + `Path.unlink(missing_ok=True)`). Partial failure leaves either old-tracked + runtime present (next finalize retries cleanly) or new-tracked + runtime gone (success).
- **OpenAI #5 (medium):** new `shared/scripts/lib/artifact_paths.py` holds `RUNTIME_DIRNAME = "runtime"` and `TRACKED_AGENT_DOC_NAMES = {"session_handoff", "build_dashboard", "triage_inbox"}` constants used by Stop hooks, finalize, and audit.
- **OpenAI #7 (medium):** `_active_worktree_root` validates the resolved path exists AND is under `main_repo_root(cwd)`. Foreign paths treated as None.
- **OpenAI #8 (medium):** `audit_staleness.compare_doc` returns `stale=False, exists=False, error="not-in-snapshot"` when BOTH on-disk and snapshot side are missing — handles fresh adopts where a tracked doc was never snapshotted.
- **OpenAI #9 (low):** verified empirically pre-build: `git ls-files | grep agent_docs/runtime/` returned zero results. Gitignore alone is sufficient.
- **OpenAI #10 (medium):** `aggregate_triage.py --out-dir` is constrained to be under `project_root.resolve()`. `argparse` validator rejects escaping paths.
- **OpenAI #11 (medium):** finalize-snapshot resolves canonical paths and refuses symlinked runtime files (matches `Path.resolve().is_relative_to(project_root)` + `is_symlink()` check).
- **Gemini #1 (high):** read-path concern documented in ADR — runtime/ is **live state**, tracked is **snapshot state**. Automated framework readers want snapshot semantics (verifiers, audits, dashboards consumed at iterate boundaries). Operator-facing inspection of mid-session state is `cat .shipwright/agent_docs/runtime/<file>.md`. No automated readers currently need runtime fallback (verified via grep). Future runtime-fallback readers will use the helper `read_runtime_or_tracked(project_root, name)` exposed by `artifact_paths.py`.
- **Gemini #3 / OpenAI #6 (medium):** audited that step 4 in `iterate_stop_finalize.main()` IS the last step before `return 0` (line 142-152). Early return at step 4 is structurally safe.

Findings deferred (LOW): OpenAI #12 (programmatic rebase guard), OpenAI #13 (cross-session concurrency tests), Gemini #2 (pre-rebase hook), Gemini #5 (Python 3.8+ check — repo requires 3.11+).

## ADR Identity

ADR-NNN assigned at `/shipwright-changelog` release per the run-id-as-identity convention. Linked to ADR-088 (single-producer pattern) and the 2026-05-23 compliance-md-single-producer iterate.
