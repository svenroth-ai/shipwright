# Iterate Spec: security-adopt-compliance-snapshots

- **Run ID:** iterate-2026-05-23-security-adopt-compliance-snapshots
- **Type:** change
- **Complexity:** medium
- **Status:** approved (2026-05-23) — follow-up to PR #78 (compliance-md-single-producer)

## Goal

Close the remaining drift gap from PR #78: after a `/shipwright-security` pipeline-mode scan or a `/shipwright-adopt` brownfield onboarding, the compliance MDs reflect the just-completed work AND the resulting commit qualifies as a snapshot baseline for the audit. Specifically:

1. **`shipwright-adopt`** Step H commits already (single `chore(shipwright): adopt …` commit). Adding a `Run-ID: adopt-<id>` trailer makes that commit a valid snapshot baseline so the next post-adopt audit reports `snapshot_unavailable=false` immediately (instead of waiting for the first iterate).
2. **`shipwright-security`** (pipeline mode only) gets a new Step 7.5 finalize that regenerates compliance MDs and creates an explicit `chore(compliance): refresh after security scan` commit with `Run-ID: security-<scan_id>` trailer. Standalone-mode flows are untouched — they already hand off to `/shipwright-iterate` per Step 8.
3. **`PHASE_REPORTS`** in `update_compliance.py` gains `adopt` and `security` entries with appropriate doc subsets.
4. **Audit `find_snapshot_commit`** keeps the `Run-ID:` filter (Codex pushback — producer-provenance is intentional protection). Both new commit producers contribute `Run-ID:` so they're recognized.

## Acceptance Criteria

- [ ] **AC-1 — Adopt commit qualifies as snapshot.** A successful `/shipwright-adopt` run produces a Step H commit whose body contains `Run-ID: adopt-<id>` (id derived from adopt context — see Mini-Plan). `find_snapshot_commit(project_root)` returns that commit's SHA. Verified by unit test with synthetic adopt-style commit fixture.
- [ ] **AC-2 — Adopt run_id format is stable + deterministic.** The `adopt-<id>` format MUST match a regex pattern (e.g., `^adopt-\d{4}-\d{2}-\d{2}-[a-z0-9-]+$`) enforced at commit-template build time. Verified by unit test.
- [ ] **AC-3 — PHASE_REPORTS supports `adopt` + `security`.** `update_compliance.py --phase adopt` regenerates `[rtm, test_evidence, change_history, sbom, dashboard]` (full set — adopt sets the initial baseline). `--phase security` regenerates `[dashboard, test_evidence, change_history, sbom]` (no RTM — security work doesn't change FR coverage). Verified by parametrized test.
- [ ] **AC-4 — Security pipeline finalize creates snapshot commit.** In pipeline mode (`shipwright_project_config.json` exists), after Step 7 completes, a new Step 7.5 runs:
  1. `uv run update_compliance.py --phase security`
  2. If any compliance MD changed → `git add .shipwright/compliance/` + `git commit -m "chore(compliance): refresh after security scan\n\nRun-ID: security-<scan_id>\nCo-Authored-By: Claude"`
  3. If no MD changed (no-op): SKIP commit, log "compliance unchanged after security scan"
- [ ] **AC-5 — Security standalone mode is untouched.** When `shipwright_project_config.json` is absent (standalone backend), Step 7.5 is a no-op. The Step 8 iterate handoff remains the canonical path for fix commits. Verified by test.
- [ ] **AC-6 — Security finalize is idempotent.** Running the security pipeline twice in succession (same scan results) doesn't create two `chore(compliance)` commits — the second run finds compliance unchanged. Verified by integration-style test.
- [ ] **AC-7 — Security finalize commit qualifies as snapshot.** After Step 7.5 commits, `find_snapshot_commit` returns that commit's SHA. Verified by extending the existing snapshot test fixture.
- [ ] **AC-8 — `seed_adopt_compliance.py` extends `--phases` default to include `adopt`** (in addition to retroactive project/plan/build/test, so the explicit adopt phase regen also runs). Verified by checking the default arg.
- [ ] **AC-9 — F11 verifier coverage for security commits.** The new `chore(compliance): refresh after security scan` commits don't break `verify_iterate_finalization.py` — they're not iterate commits, so most iterate-specific checks skip them. Verified by integration test.
- [ ] **AC-10 — Documentation updated.** `docs/hooks-and-pipeline.md` lists `adopt` and `security` as additional snapshot producers. `docs/guide.md` (if it references compliance regen flows) is checked. Adopt + Security SKILL.md sections updated for the new commit/finalize behavior. Updates to `architecture.md` and `conventions.md` per the standard flow.

## Spec Impact

- **Classification:** none
- **NONE justification:** Internal SDLC tooling change extending the snapshot-provenance audit from PR #78 to two additional producer paths (adopt + security pipeline). No user-facing product surface changes; compliance MDs remain tracked at the same paths with the same human-readable formats. No FR is added, modified, or removed.

## Out of Scope

- **Pipeline phase plugins (project/design/plan/build/test/changelog/deploy)** — their commits don't currently carry `Run-ID:` trailers either. They COULD be extended similarly but it's a wider scope decision; deferred to a separate iterate if needed. Today they're covered by the orchestrator's `run_compliance_update` side-effect (MDs written to disk between phases) but the resulting commits aren't snapshot-recognized. Acceptable: greenfield pipeline operators get `snapshot_unavailable=true` until the first iterate (or until adopt was used in their setup).
- **Git pre-commit hook for ad-hoc manual commits** — separate larger architecture change; deferred.
- **shipwright-security standalone-mode finalize** — explicit out-of-scope per AC-5. Standalone mode hands off to iterate; iterate's F5b covers regen.
- **Backfilling Run-ID into historical adopt commits** — forward-only fix.

## Design Notes

n/a (no UI).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shipwright-adopt` Step H (`git commit -m "...Run-ID: adopt-<id>"`) | `audit_staleness.find_snapshot_commit` | git commit body |
| `shipwright-security` Step 7.5 (NEW: `git commit -m "...Run-ID: security-<scan_id>"`) | `audit_staleness.find_snapshot_commit` | git commit body |
| `update_compliance.py --phase {adopt,security}` | `.shipwright/compliance/*.md` | Markdown files |

Round-trip tests required:
1. Synthetic git fixture: adopt-style commit (body contains `Run-ID: adopt-<...>` + modified `.shipwright/compliance/` files) → `find_snapshot_commit` picks it up.
2. Synthetic git fixture: security-style commit similarly.
3. `update_compliance.py --phase adopt` against synthetic project → regenerates expected file set.
4. `update_compliance.py --phase security` same.
5. `shipwright-security` Step 7.5: pipeline-mode, scan that produces no compliance diff → no commit created (idempotency).

## Confidence Calibration

- **Boundaries touched:** git commit bodies (new `Run-ID:` trailers), `PHASE_REPORTS` dict (new keys), shipwright-security pipeline flow (new finalize step).
- **Empirical probes planned (run during Build):**
  1. Run `update_compliance.py --phase adopt` against a real adopted project → diff vs. running `--phase iterate` → expected: same output (both regenerate the full set), confirms PHASE_REPORTS["adopt"] is correctly populated.
  2. Run `update_compliance.py --phase security` against the same project → diff vs. `--phase iterate` → expected: RTM omitted, other 4 present.
  3. Synthetic security finalize against fixture (mocked scan results) → first run creates commit, second run is no-op.
  4. Synthetic adopt commit with new Run-ID trailer → existing snapshot detection picks it up without regex/parser changes.
- **Edge cases NOT probed + why acceptable:** Standalone shipwright-security mode (explicitly out of scope per AC-5). Manual commits without `Run-ID:` (would require pre-commit hook — out of scope).
- **Confidence-pattern check:** Codex consult ruled out the "drop Run-ID filter" shortcut (would weaken producer-provenance) — that's a yes-then-bug avoided.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest plugins/shipwright-compliance/tests/test_audit_snapshot.py plugins/shipwright-compliance/tests/test_audit_group_e.py shared/tests/test_finalize_iterate.py -v` (extended with new cases for adopt + security phases / Run-ID variants).
- **Evidence path:** `.shipwright/runs/iterate-2026-05-23-security-adopt-compliance-snapshots/surface_verification.json`.

---

## Mini-Plan

### Phase 1 — Tests first (RED)

1. **`plugins/shipwright-compliance/tests/test_audit_snapshot.py`** — extend with:
   - `test_find_snapshot_commit_accepts_adopt_run_id`: synthetic commit with `Run-ID: adopt-2026-05-23-myrepo` + compliance touch → returns its SHA
   - `test_find_snapshot_commit_accepts_security_run_id`: ditto with `Run-ID: security-scan-001`
   - `test_find_snapshot_commit_prefers_most_recent_across_producers`: iterate + adopt + security commits in mixed order → most recent wins regardless of producer type

2. **`plugins/shipwright-compliance/tests/test_update_compliance_phases.py`** (NEW) — parametrized tests for:
   - `PHASE_REPORTS["adopt"]` produces all 5 MDs
   - `PHASE_REPORTS["security"]` produces 4 MDs (no RTM)
   - Both phases survive in CLI invocation (`--phase adopt` / `--phase security` exits 0)

3. **`plugins/shipwright-adopt/tests/test_adopt_commit_template.py`** (NEW or extend existing) — assert:
   - Adopt's commit message template includes a `Run-ID: adopt-<id>` line
   - The `<id>` matches the AC-2 regex

4. **`plugins/shipwright-security/tests/test_finalize_step.py`** (NEW) — extend existing security tests:
   - `test_finalize_skips_in_standalone_mode`: no `shipwright_project_config.json` → no commit
   - `test_finalize_creates_commit_when_compliance_changed`: mock update_compliance to dirty MDs → commit created with correct trailer
   - `test_finalize_skips_commit_when_no_change`: mock update_compliance to no-op → no commit
   - `test_finalize_idempotent_across_two_runs`: second invocation finds clean → no commit

All tests must FAIL initially.

### Phase 2 — Implement (GREEN)

1. **`plugins/shipwright-compliance/scripts/tools/update_compliance.py`** — extend `PHASE_REPORTS`:
   ```python
   PHASE_REPORTS = {
       ...existing entries...,
       "adopt": ["rtm", "test_evidence", "change_history", "sbom", "dashboard"],
       "security": ["dashboard", "test_evidence", "change_history", "sbom"],
   }
   ```

2. **`plugins/shipwright-adopt/scripts/tools/seed_adopt_compliance.py`** — extend `--phases` default to include `adopt`.

3. **`plugins/shipwright-adopt/skills/adopt/SKILL.md`** Step H — update the commit message template to include the trailer:
   ```
   chore(shipwright): adopt repository into Shipwright SDLC

   Adopted via /shipwright-adopt using profile=<profile>, scope=<scope>.
   Inferred <N> functional requirements from existing codebase.
   Seeded compliance artifacts (SBOM, change-history, RTM skeleton).
   Test evidence starts collecting from next /shipwright-test run.

   See .shipwright/agent_docs/decision_log.md for the adoption ADR
   (id is `max(existing) + 1`, 3-digit zero-padded — ADR-001 on greenfield).

   Run-ID: adopt-<YYYY-MM-DD>-<repo-name>
   ```
   Document the `<id>` derivation: `<YYYY-MM-DD>` from current UTC date, `<repo-name>` from `os.path.basename(project_root)` (lowercased, kebab-case).

4. **`plugins/shipwright-security/skills/security/SKILL.md`** — add new Step 7.5 between Step 7 and Step 8:
   ```markdown
   ## Step 7.5: Compliance Snapshot Refresh (Pipeline Mode Only)

   After Step 7 persists `shipwright_security_config.json`, refresh the
   compliance MDs so the next snapshot audit sees the post-security state.

   1. Run `uv run update_compliance.py --phase security` from the
      compliance plugin.
   2. If `.shipwright/compliance/*.md` files have changed (check git
      status), stage them + create a snapshot commit:
      ```bash
      git add .shipwright/compliance/
      scan_id=$(jq -r .scan_id .shipwright/securityreports/latest.json 2>/dev/null || echo "unknown")
      git commit -m "chore(compliance): refresh after security scan

      Updated dashboard/test-evidence/change-history/sbom to reflect post-scan state.
      No FR coverage change (RTM unaffected).

      Run-ID: security-${scan_id}
      Co-Authored-By: Claude <noreply@anthropic.com>"
      ```
   3. If no MD changed: skip the commit, log a one-line stderr notice.

   **Skip Step 7.5 entirely if:**
   - Pipeline mode not active (`shipwright_project_config.json` absent)
   - `os.environ.get("CI")` is set (CI doesn't commit)
   - `os.environ.get("SHIPWRIGHT_NON_INTERACTIVE")` is set
   ```

5. **New helper script** `plugins/shipwright-security/scripts/tools/finalize_security_compliance.py` — wraps the Step 7.5 logic so the SKILL.md doesn't need shell heredoc complexity. CLI:
   ```bash
   uv run finalize_security_compliance.py --project-root <path>
     [--scan-id <id>] [--skip-if-standalone]
   ```
   Returns structured JSON: `{committed: true/false, reason: "...", commit_sha: "..."}`.

6. **`docs/hooks-and-pipeline.md`** — add `adopt` and `security` to the snapshot-producer list.

7. **`plugins/shipwright-iterate/skills/iterate/SKILL.md`** — already updated in PR #78. NO further changes.

### Phase 3 — Verify & finalize

1. Run all tests: `uv run pytest shared/tests/ plugins/shipwright-compliance/tests/ plugins/shipwright-adopt/tests/ plugins/shipwright-security/tests/ -v`.
2. Run the snapshot audit against this iterate's own F6 commit → green.
3. F0.5 surface verification: CLI runner = the pytest invocation.
4. F2 architecture update: document the adopt + security snapshot producers.
5. F3 ADR: "Extend snapshot producers to adopt + security (pipeline mode). Run-ID filter preserved per Codex sanity-check."

### Risk & Rollback

- **Risk 1 (low):** shipwright-security's Step 7.5 might commit when the operator didn't want a commit (e.g., they wanted to review the regen first). Mitigated by the standalone-mode skip + CI-skip + interactive opt-out. Future: could add `--dry-run` flag.
- **Risk 2 (medium):** Adopt's Run-ID `adopt-<YYYY-MM-DD>-<repo-name>` could collide if two adopts run on the same day on the same repo. Mitigated by the date+repo-name being unique enough in practice; could add a `-<short-sha-of-tree>` suffix if collision becomes real.
- **Risk 3 (low):** `seed_adopt_compliance.py` extending `--phases` default to include `adopt` means existing tests that assert on default phases might break. Tests need updating (covered by AC-8).
- **Rollback:** Revert this iterate's commits. PR #78 architecture remains intact.

### Test-Update-Klausel

This iterate adds new commit producers (adopt, security pipeline finalize). Both contribute `Run-ID:` trailers, conforming to the audit's existing producer-provenance contract. SKILL.md updates codify the new behavior. No test-rule documentation changes needed beyond updating affected plugin SKILL.md sections.
