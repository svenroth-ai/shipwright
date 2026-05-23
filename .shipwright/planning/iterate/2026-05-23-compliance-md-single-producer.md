# Iterate Spec: compliance-md-single-producer

- **Run ID:** iterate-2026-05-23-compliance-md-single-producer
- **Type:** change
- **Complexity:** medium
- **Status:** approved (operator picked Option E pure 2026-05-23)

## Goal

Stop the recurring "stale compliance MD" cycle by:
1. Making **iterate finalize the sole producer** of `.shipwright/compliance/{rtm,test-evidence,change-history,sbom,dashboard}.md`.
2. Replacing the **fresh-render-vs-on-disk** byte-compare audit (`audit_staleness.py`) with a **snapshot-provenance** audit: compare on-disk against the last iterate-finalize commit's version (located via `Run-ID:` trailer and `--diff-filter=M -- .shipwright/compliance/`).

This eliminates E1-E5 false positives by construction: non-iterate commits (security work, manual fixes) don't touch `.shipwright/compliance/`, so the snapshot reference stays valid and the audit stays green. The semantic shifts from "MDs are a live mirror" to "MDs are a tracked snapshot of the last iterate-finalize state".

## Acceptance Criteria

- [ ] **AC-1 — Snapshot audit identifies the right baseline.** `audit_staleness.find_snapshot_commit(project_root)` returns the SHA of the latest commit that BOTH (a) contains `Run-ID:` in its body AND (b) modified one or more files under `.shipwright/compliance/`. Verified by a unit test that injects a fake git log (run_id commit + non-run_id commits + earlier run_id commit) and asserts the right SHA is picked.
- [ ] **AC-2 — Snapshot audit catches hand-edits.** When an on-disk compliance MD has been hand-modified (differs from the snapshot version), the audit emits the corresponding E1-E5 finding with `evidence=[snapshot_sha, file_path]` and a fix hint. Verified by an integration test that mutates one MD and asserts a stale finding.
- [ ] **AC-3 — Snapshot audit reports green when on-disk matches snapshot.** Immediately after a fresh git checkout (no local modifications), `audit_staleness.check_staleness()` returns `any_stale=False` for all 5 docs. Verified by a fixture test using a synthetic git repo.
- [ ] **AC-4 — Snapshot audit reports green AFTER non-iterate commits.** Simulate: snapshot commit `S` (with Run-ID:), then 3 unrelated commits that do NOT touch `.shipwright/compliance/`. Audit still uses `S` as baseline → all green. Verified by a fixture test.
- [ ] **AC-5 — Snapshot audit reports stale if baseline is unfindable.** If no commit with `Run-ID:` touched `.shipwright/compliance/` (greenfield project, or pre-adoption history), audit emits ONE finding `E0 (snapshot-unavailable)` with severity `info` (not high), evidence explaining the missing baseline. Verified by a fixture test on a synthetic repo with no Run-ID commits.
- [ ] **AC-6 — Iterate finalize produces a self-consistent snapshot.** After `finalize_iterate.py` + F6 commit completes inside an iterate worktree, the iterate's own `work_completed` event is reflected in the committed `rtm.md` / `test-evidence.md` / `dashboard.md` / `sbom.md`. Verified by an end-to-end TDD test.
- [ ] **AC-7 — F7 commit SHA is patched in place.** After F6 commits, the F7 step locates the just-recorded `work_completed` event in `shipwright_events.jsonl` (by `event_id` returned from F5b) and rewrites that line atomically (write-temp + rename) with the now-known commit SHA. Pre-existing audit-trail (other events) untouched. Verified by a round-trip test.
- [ ] **AC-8 — Stop-hook never writes tracked compliance files.** `generate_handoff_on_stop.py` writes `.shipwright/agent_docs/session_handoff.md` and `.shipwright/agent_docs/build_dashboard.md` only — no path under `.shipwright/compliance/` is touched. Verified by a hook-execution test that asserts mtime-stability of `.shipwright/compliance/*.md`.
- [ ] **AC-9 — No regression in determinism guarantees.** The deterministic-banner promise from `8382ff9` (two regens against the same `events.jsonl` → byte-identical MDs) still holds.
- [ ] **AC-10 — Documentation updated.** `docs/hooks-and-pipeline.md` describes the new single-producer + snapshot-audit semantics. `plugins/shipwright-iterate/skills/iterate/SKILL.md` updates F5b/F6/F7 ordering and the new `attach_commit_to_event` step.

## Spec Impact

- **Classification:** none
- **NONE justification:** Internal SDLC-tooling change. Audit semantic shifts (fresh-render → snapshot-provenance) and finalize substep ordering change, but no user-facing product surface changes. Compliance MDs remain tracked at the same paths with the same human-readable formats. No FR is added, modified, or removed.

## Out of Scope

- **events.jsonl machine-divergence sync** — handled in a separate iterate per user direction. This iterate only ensures iterate finalize on the machine running it produces a self-consistent snapshot; cross-machine sync of `shipwright_events.jsonl` is a different problem.
- **Backfilling the currently dirty MDs in `security/fix-nosem-syntax-2026-05-22`** — pre-existing operator drift; this iterate doesn't touch them. The operator can address them in a separate `chore(compliance): regen` commit or accept they'll be swept at the next iterate-finalize.
- **Consistency Validators (FR-refs / event-IDs valid)** — explicitly rejected by user (would re-introduce currency-lite false positives between iterates). May be added later as a separate Group H if drift signal is needed.
- **HEAD~1 contract for `change_history.py`** — dropped from this iterate. Snapshot-provenance audit makes it unnecessary: the audit doesn't compare against a live re-render anymore.
- **Per-phase plugin compliance regen (option B)** — explicitly rejected. The audit no longer flags non-iterate-commit drift, so per-phase regen is unnecessary.

## Design Notes

n/a (no UI affected).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/scripts/tools/record_event.py:append_event` | `events_log.latest_event_dt`, `data_collector.collect_work_events`, NEW `attach_commit_to_event` | JSONL (`shipwright_events.jsonl`) |
| **NEW** `shared/scripts/tools/record_event.py:attach_commit_to_event(event_id, sha)` | `data_collector` | JSONL line replacement (atomic) |
| `shared/scripts/tools/finalize_iterate.py:run` | F6 git commit (`git add .shipwright/compliance/`) | Markdown files |
| `plugins/shipwright-compliance/scripts/audit/audit_staleness.py` (REWRITTEN) | `aggregate_triage.py`, `run_audit.py` | StalenessReport dict |
| `git show <snapshot_sha>:<file>` | NEW snapshot audit | git object content |

Round-trip tests required:
1. `record_event` (commit="") → `attach_commit_to_event(sha)` → re-read → assert all fields except commit unchanged.
2. Two events same-ms → patch only one → assert other untouched.
3. Corrupt JSONL line between valid ones → `attach_commit_to_event` survives.
4. `find_snapshot_commit` against synthetic git history: (mixed Run-ID + non-Run-ID commits, some touching compliance/ some not, multiple Run-IDs) → returns the right one.

## Confidence Calibration

- **Boundaries touched:** `events.jsonl` (line replacement is new); audit-snapshot integration (new git-shell-out for `git show`).
- **Empirical probes planned (run during Build):**
  1. Round-trip `record_event` (no SHA) → `attach_commit_to_event(sha)` → `data_collector` → assert all fields except `commit` unchanged.
  2. Edge: two events in same millisecond — assert `attach_commit_to_event` patches by `event_id`, not by `ts` proximity.
  3. Edge: corrupt JSONL line mid-file — `attach_commit_to_event` skips it and patches the target.
  4. Edge: `find_snapshot_commit` on a brand-new repo with no Run-ID commits → returns None → audit emits E0 info.
  5. Edge: `find_snapshot_commit` when the same commit appears in 2 worktree-local branches → still picks the right one in main repo's git history (worktree-aware via `git -C main_repo log`).
  6. Edge: `git show <sha>:<file>` fails (file didn't exist at that commit) → audit emits stale finding with explanatory evidence, doesn't crash.
- **Edge cases NOT probed + why acceptable:** Cross-machine `events.jsonl` divergence (out of scope; operator handling separately).
- **Confidence-pattern check:** no yes-then-bug fired yet; will re-check post-Build.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_finalize_iterate.py shared/tests/test_record_event.py plugins/shipwright-compliance/tests/test_audit_staleness.py plugins/shipwright-compliance/tests/test_audit_snapshot.py -v` (specific test files extended/created during Build).
- **Evidence path:** `shipwright_test_results.json` `iterate_latest.surface_verification`.

---

## Mini-Plan

### Phase 1 — Tests first (RED)

1. **`plugins/shipwright-compliance/tests/test_audit_snapshot.py`** (new) — covers AC-1, AC-3, AC-4, AC-5 with a fixture that builds a synthetic git repo:
   - `test_find_snapshot_commit_picks_latest_run_id_commit_touching_compliance`
   - `test_find_snapshot_commit_returns_none_when_no_run_id_commit_touches_compliance`
   - `test_check_staleness_green_when_on_disk_matches_snapshot`
   - `test_check_staleness_green_after_non_compliance_commits_layered_on_snapshot`
   - `test_check_staleness_emits_e0_info_when_no_snapshot_available`
2. **`plugins/shipwright-compliance/tests/test_audit_staleness.py`** (extend) — `test_check_staleness_flags_hand_edited_md` (AC-2). Old tests that compared on-disk to fresh-render are migrated or deleted.
3. **`shared/tests/test_record_event.py`** (extend) — three tests for AC-7:
   - `test_append_event_without_commit_then_attach`
   - `test_attach_commit_to_event_concurrent_lines_same_ms`
   - `test_attach_commit_to_event_corrupt_line_survives`
4. **`shared/tests/test_finalize_iterate.py`** (extend or new) — `test_finalize_produces_self_consistent_snapshot` (AC-6): simulates full sequence record-event-pre → update_compliance → git commit → attach_commit_to_event; asserts the iterate's own event appears in the committed MDs.
5. **`shared/tests/test_generate_handoff_on_stop.py`** (extend) — `test_hook_does_not_touch_compliance_dir` (AC-8): mtime snapshot + hook run + mtime assertion.

All tests must FAIL initially.

### Phase 2 — Implement (GREEN)

1. **`shared/scripts/tools/record_event.py`** — add `attach_commit_to_event(project_root, event_id, commit_sha) -> bool`:
   - Locate `events.jsonl` via `events_log.resolve_events_path` (worktree-aware).
   - Stream-read line-by-line, find the one whose parsed JSON has `id == event_id`, rewrite that line with patched `commit` field, pass all others verbatim including corrupt ones.
   - Atomic: write to `events.jsonl.tmp` then rename.
   - Return `True` if patched, `False` if event_id not found.

2. **`shared/scripts/tools/finalize_iterate.py`** — restructure `run()`:
   - New step order:
     1. `_record_event_pre_commit(...)` → returns `event_id`, writes event to events.jsonl with `commit=""`.
     2. `_update_compliance(...)` → regen MDs (now includes the just-written event).
     3. `_update_dashboard(...)` → regen build_dashboard.md.
     4. Return result with `event_id`; caller does F6 commit.
     5. `_generate_handoff(...)` → after F6 (handoff already runs after record_event today; preserve that).
   - Add new helper `attach_commit_after_finalize(project_root, event_id, commit_sha)` for callers to invoke after F6 — wraps `record_event.attach_commit_to_event`.

3. **`plugins/shipwright-compliance/scripts/audit/audit_staleness.py`** — REWRITE:
   - Drop `default_renderers()` (no longer needed — no fresh-render).
   - Add `find_snapshot_commit(project_root, main_repo=True) -> str | None`:
     - Use `git -C <main_repo> log --grep='Run-ID:' --diff-filter=M --format=%H -- .shipwright/compliance/` (worktree-aware via `resolve_main_repo_root` from `events_log`).
     - Return first line (most recent) or None.
   - Rewrite `compare_doc(project_root, doc, snapshot_sha)`:
     - Read on-disk MD (normalize Generated: line).
     - Read `git show <snapshot_sha>:<doc.rel_path>` (normalize same way).
     - Byte-compare. Stale = different.
     - If `git show` fails (file didn't exist at snapshot): stale with explanatory error.
   - Rewrite `check_staleness(project_root, *, doc_filter=None) -> StalenessReport`:
     - Find snapshot commit. If None → emit single E0 info finding "no iterate-finalize snapshot found; staleness check skipped" → return report with `any_stale=False`.
     - For each doc in DOC_REGISTRY: `compare_doc(project_root, doc, snapshot_sha)`.

4. **`plugins/shipwright-compliance/scripts/tools/update_compliance.py`** — `_run_check_mode` no longer needs to pass `data` to `check_staleness`. Simpler signature.

5. **`plugins/shipwright-compliance/scripts/audit/group_e.py`** — adapt to new `StalenessReport` shape (E0 info finding handling, snapshot SHA in evidence).

6. **`shared/scripts/hooks/generate_handoff_on_stop.py`** — DELETE lines ~283-310 (the `# Update compliance docs (best-effort, idempotent)` block). Block has no replacement.

7. **`plugins/shipwright-iterate/skills/iterate/SKILL.md`** — F5b/F6/F7 sections updated to document the new order:
   - F5b-pre: record event (no SHA).
   - F5b: regen compliance.
   - F6: commit.
   - F6.5: attach_commit_to_event(event_id, F6_sha).
   - F7: NOW satisfied by F5b-pre + F6.5 (no separate record_event call).

8. **`docs/hooks-and-pipeline.md`** — document:
   - Compliance MDs have a single producer (iterate finalize).
   - Stop hooks NEVER write tracked compliance files.
   - Audit semantic is snapshot-provenance (compare on-disk to last iterate-finalize commit), not currency.

### Phase 3 — Verify & finalize

1. Run full test suite: `uv run pytest shared/tests/ plugins/shipwright-compliance/tests/ plugins/shipwright-iterate/tests/ -v`.
2. Run the snapshot audit against the main repo at HEAD: should find a snapshot commit AND report green for all 5 docs (after committing this iterate's own changes).
3. F0.5 surface verification: CLI runner = the pytest invocation above.
4. F2 architecture update: document the single-producer + snapshot-audit invariants in `architecture.md` (Component / Data Flow sections).
5. F3 ADR: "Compliance MDs single-producer + snapshot-provenance audit. Replaces fresh-render byte-compare; eliminates between-iterate false-positive class. F5b-pre + F6.5 ensures iterate's own event lands in committed snapshot." `--spec-ref` to point to this spec file if ADR body would exceed 500-char budget.

### Risk & Rollback

- **Risk 1 (low):** `attach_commit_to_event` writes to events.jsonl post-commit. If it fails, the F6 commit is still good — the event log just lacks the commit SHA for that work item. Soft degradation.
- **Risk 2 (low):** `find_snapshot_commit` returns None for projects without any iterate-finalize history yet → E0 info finding (not high) → audit is effectively a no-op. Acceptable for greenfield / pre-adoption.
- **Risk 3 (medium):** Existing snapshots in HEAD were written under the OLD F5b/F7 order (without the iterate's own event). The new audit comparing against THOSE snapshots is technically a "consistent past-snapshot" — no false positive, but also doesn't catch any "iterate's own event missing from snapshot" issue retroactively. Acceptable: forward-only fix.
- **Rollback:** Revert this iterate's commits. The old fresh-render byte-compare audit returns. Stop-hook auto-regen could be restored from git history if needed.

### Test-Update-Klausel

This iterate rewrites a core audit semantic (Group E moves from currency to snapshot). The SKILL.md F5b/F6/F7 update + `docs/hooks-and-pipeline.md` update codify the new contract. Test changes (delete fresh-render comparison tests, add snapshot comparison tests) reflect the semantic shift directly.
