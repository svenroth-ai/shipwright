# Empirical Verification Results — Artifact-Polish Campaign

**Verified:** 2026-05-21
**Verifier:** Claude Code session (Opus 4.7 1M)
**Repos tested:** shipwright (monorepo @ `376c870`), shipwright-webui (adopted @ `c502254`)
**Handover:** `2026-05-21-artifact-polish-empirical-verification.md`

---

## Headline

| Iterate | Visible on shipwright | Visible on webui | Status                                          |
|---------|-----------------------|------------------|-------------------------------------------------|
| B.2 SBOM  | ✅ 2 cards rendered  | ✅ correct null   | Works on real data                              |
| B.3 layer | ✅ Layer column live | ✅ Layer column live | Layer column works; Full Suite Runs DOA      |
| B.4 RTM   | ⚠️ infra works, no producer | ⚠️ same     | **Producer gap** — synthetic test green         |
| C.1 gate  | ✅ all 5 cases pass  | ✅ all 5 cases pass | Hard-enforced as designed                     |
| C.2 F4-F7 | ✅ all 4 detectors run | ✅ all 4 fire on webui | Canonical F6@270-line test passes        |
| C.3 cache | ✅ drift detected (fixture) | ✅ skip (no plugins/) | Both branches verified                  |

Overall: 5 of 6 iterates have visible operator-facing effect on real data. **B.4 alone is dead-on-arrival** without an FR-aware producer — handover's known gap is confirmed.

---

## Setup checklist
- [x] Marketplace sync run + verified: `13 synced, 0 skipped, 0 errors`.
- [x] Baseline compliance tests: `434 passed` (matches handover expectation).
- [~] Baseline shared tests: `2161 passed, 1 failed` (handover expected `2162 passed`). The 1 failure is **`test_no_legacy_artifact_paths[compliance-migrated]`** — path-canon lint catches 2 occurrences of `compliance/` in B.2 SBOM card launchPayloads (`plugins/shipwright-compliance/scripts/tools/...`) in the locally-modified `triage_inbox.md`. This is a regex-prefix issue (`-` before `compliance/` is not in the negative-lookbehind class), not a feature regression — fix options are either (a) extend `ALLOWLIST['compliance']` in `shared/scripts/lib/artifact_migrations.py` to permit the plugin-source-tree prefix, or (b) add `# artifact-path-canon: legacy` marker on the lint-triggering lines. Recommend (a) since the path is structurally legitimate. See "Bugs / gaps" below.

---

## Per-iterate results

### V-1. B.2 SBOM — undeclared-license triage

**shipwright** (visible-effect criteria):
- [x] `sbom_triage` key in JSON output: `{appended: 0, dismissed: 0}` (idempotent on re-run; cards already existed).
- [x] 2 `source="sbom"` cards in `triage.jsonl`: `trg-db49aad2` (plugins/shipwright-plan, google-genai@1.0.0), `trg-95fba1e3` (plugins/shipwright-security, requests@2.31.0).
- [x] `triage_inbox.md` renders both cards with copy-pasteable launchPayloads (`cd 'plugins/shipwright-plan' && uv sync && cd - && uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate`).
- [x] Idempotency confirmed (re-run yielded 0 appended).
- [ ] Auto-resolve (running `uv sync`) NOT executed — too disruptive for verification.

**webui** (visible-effect criteria):
- [x] `sbom_triage` key: `{appended: 0, dismissed: 0}` — correct.
- [x] All 55 deps (client+server workspaces) have resolved licenses (3 unique: Apache-2.0, ISC, MIT), so 0 SBOM cards is the correct null result.
- [x] No false positives on multi-workspace JS repo.

**Verdict:** B.2 produces visible, real-data effect on shipwright; correctly emits zero on a fully-licensed webui.

---

### V-2. B.3 — test-evidence Layer column + per-layer FAIL triage

**shipwright:**
- [x] `## Test Progression` header is the new 8-column form: `# | Event | Source | Layer | New Tests | Suite Total | Result | Date`.
- [x] Layer column populated with real values (`mixed`, `unit`, `e2e`) across 37 rows.
- [ ] `## Full Suite Runs` section **NOT rendered** — `shipwright_events.jsonl` contains 0 `test_run`-type events. Code path is correct (`_full_suite_runs()` returns `[]` when `data.test_runs` is empty), but no test_run events means no visible output.
- [ ] No test-evidence triage cards (0 in `triage.jsonl`) — corollary of the above: no test_run events → nothing to fail.

**webui:**
- [x] `## Test Progression` header has the 8-column form with Layer.
- [x] Layer column populated across 127 rows.
- [ ] `## Full Suite Runs` not rendered (0 test_run events in webui's events log either).
- [ ] No test-evidence triage cards.

**Verdict:** Layer column lights up visibly on both repos. The `## Full Suite Runs` table and per-layer FAIL triage have **zero visible effect today** because no producer in the pipeline records `type="test_run"` events on real shipwright/webui runs. Same shape of producer gap as B.4 — the renderer works but no upstream data flow reaches it.

---

### V-3. B.4 — RTM `FAIL → trg-XXX` deep-link

**Step A — Gap confirmed on both repos:**
- shipwright: `grep -c '"frId":"FR-' triage.jsonl` = 0; `grep 'FAIL → \[trg-' traceability-matrix.md` = 0.
- webui: same — 0 and 0.

**Step B — Synthetic verification (seed FR-bearing card, regen RTM):**

shipwright (seed `trg-55a2f8bc` with `frId=FR-01.01`):
- [x] After regen, FR-01.01 row shows: `| ... | FAIL → [trg-55a2f8bc](../agent_docs/triage_inbox.md#trg-55a2f8bc) |`.
- [x] Coverage Summary `### FRs with open triage items` lists FR-01.01 with the same deep-link.
- [x] Coverage Summary `### FRs with stale verification (> 14 days)` already rendered pre-seed (FR-01.03 through FR-01.09, 17d ago).

webui (seed `trg-7b67ad13` with `frId=FR-01.01`):
- [x] FR-01.01 row shows the FAIL deep-link.
- [x] Coverage Summary `### FRs with open triage items` lists FR-01.01 with the same deep-link.

**Step C — Cleanup:** Both synthetic cards dismissed via `triage.mark_status('dismissed', by='verification', reason='synthetic-test-cleanup')`. Audit trail preserved (append+status events both in JSONL). Post-cleanup regen: 0 FAIL deep-links remaining in either RTM.

**Gap confirmed:** yes — code path works, but no producer in the campaign sets `frId` on cards.

**Recommended follow-up:** Option (3) from handover — add a manual `--fr-id` flag to `record_event.py task_created` (and/or ad-hoc triage producers) so operators can stamp FRs when context exists. Smallest patch, biggest unlock. Defer options 1 (phase-quality FR mapper) and 2 (test-suite → FR map) until the manual path is shown to be insufficient.

---

### V-4. C.1 FR-or-change-type gate

**shipwright (5 cases):**
- [x] Step 1 (unclassified): exit 1, `"error": "fr_gate_unclassified"`, NO event written.
- [x] Step 2 (`--affected-frs FR-01.01`): exit 0, `evt-9a656b5f` written.
- [x] Step 3 (`--change-type tooling --none-reason "verification test"`): exit 0, `evt-5be2bab6` written.
- [x] Step 4 (`--change-type` without `--none-reason`): exit 1, malformed-reason error.
- [x] Step 5 (multi-line `--none-reason`): exit 1, malformed-reason error.

**webui (5 cases):**
- [x] Step 1: exit 1.
- [x] Step 2: exit 0, `evt-904b92f3` written.
- [x] Step 3: exit 0, `evt-6ca6247c` written.
- [x] Step 4: exit 1.
- [x] Step 5: exit 1.

**Verdict:** C.1 hard-enforces the gate on both real repos as designed. Verification events left in log (self-labeled `VERIFICATION:`):
- shipwright: `evt-9a656b5f`, `evt-5be2bab6` (2 events).
- webui: `evt-904b92f3`, `evt-6ca6247c` (2 events).

---

### V-5. C.2 audit detectors F4-F7

**shipwright (CLAUDE.md = 136 lines):**
- F4 ADR-bloat: **pass** — "no bloated ADRs without spec_ref".
- F5 architecture-drift: **pass** — "no arch-impact drift since marker 932e0d221ea1".
- F6 CLAUDE.md size: **pass** — "CLAUDE.md is 136 lines (≤ 200)".
- F7 iterate-annotation leak: **pass** — "1 inline iterate references (≤ 5)".

**webui (CLAUDE.md = 270 lines — canonical F6 test):**
- F4 ADR-bloat: **fail** — "5 ADR(s) exceed 60 lines without a spec_ref link → refactor. Heaviest: ADR-058 (129 lines), ADR-099 (123 lines), ADR-095 (107 lines), ADR-096 (97 lines), ADR-098 (77 lines)".
- F5 architecture-drift: **fail** — "architecture.md has no shipwright:architecture marker, but 1 arch-impact drop(s) exist → run the first sync to establish a baseline. Drops: iterate-2026-05-21-triage-fix-now-and-phase-slash_001.json".
- F6 CLAUDE.md size: **fail** — "CLAUDE.md is 270 lines, exceeds the 200-line hygiene cap" — **the canonical real-world test of the F6 detector passes**.
- F7 iterate-annotation leak: **fail** — "8 inline 'Iterate X (ADR-NN)' references in CLAUDE.md exceed the 5-reference cap. Sample: Iterate 5, Iterate 3, Iterate 3, Iterate 2, Iterate 3".

**Verdict:** All 4 detectors run on real repos, emit meaningful detail + evidence, fire correctly on webui's known-bloated state. C.2 has visible, actionable operator output.

---

### V-6. C.3 plugin-cache vs repo drift

**shipwright (with plugins/):**
- [x] Default exit 0 (fail-soft as designed).
- [x] Output: `plugin-cache-sync: WARN — 1 plugin(s) drifted. Run scripts/update-marketplace.sh to re-sync.`
- [x] Drift detail: `shipwright-compliance` cache 0.2.2, 1 file missing in cache: `tests/fixtures/audit_sample/shipwright_run_config.json` (expected per handover risk register — fixture files legitimately don't sync to cache).
- [x] `--json` output is valid JSON with `status:"drift"`, `drifted_count:1`, per-plugin details across 13 plugins.

**webui (no plugins/):**
- [x] Output: `plugin-cache-sync: skip — no plugins/ dir in repo`.
- [x] Exit 0, no false-WARN.

**Verdict:** Both branches verified. The single drift in shipwright is the expected fixture-file case noted in the handover risk register, not a real sync miss.

---

## Cleanup actions taken

- [x] Synthetic triage cards dismissed: 2 (`trg-55a2f8bc` shipwright, `trg-7b67ad13` webui). Audit-trail append+status events preserved.
- [x] Transient audit JSON files removed: `audit_shipwright.json`, `audit_webui.json`, `.tmp_audit_shipwright.json`.
- [ ] Verification events kept in log: 4 total (2 per repo), all self-labeled `VERIFICATION:`. Handover explicitly permits this.

---

## Bugs / gaps found

1. **B.4 producer gap (known, confirmed empirically).** No producer in B.2-B.4 emits `frId` on triage cards, so the `FAIL → trg-XXX` deep-link and the `### FRs with open triage items` subsection both have zero visible effect on production data today. Synthetic-card test green; pure producer-side gap. → Recommended fix: add `--fr-id` flag to `record_event.py` (manual stamping) as the smallest unlock.

2. **B.3 Full Suite Runs section is silent on real repos.** `_full_suite_runs()` in [plugins/shipwright-compliance/scripts/lib/test_evidence.py:452](plugins/shipwright-compliance/scripts/lib/test_evidence.py#L452) returns `[]` when there are no `test_run`-type events. Neither shipwright nor webui records any `test_run` events in `shipwright_events.jsonl` — only `work_completed` events that carry test counts as side-data. Visible effect = 0. Either (a) extend the test-evidence emitter to synthesize Full Suite Run rows from `work_completed.tests_*` fields, or (b) add a producer that writes explicit `test_run` events at suite-end. Same producer-shape gap as B.4.

3. **Path-canon lint fails on its own B.2 output.** `test_no_legacy_artifact_paths[compliance-migrated]` flags 2 lines in `.shipwright/agent_docs/triage_inbox.md` that contain `plugins/shipwright-compliance/scripts/tools/...` because the regex `(?<![\w/.\\])compliance/` doesn't include `-` in the negative-lookbehind class. The launchPayload string is structurally legitimate (it's a plugin source-tree path, not a legacy artifact path). → Fix: extend `ALLOWLIST['compliance']` in [shared/scripts/lib/artifact_migrations.py](shared/scripts/lib/artifact_migrations.py) to permit `shipwright-compliance/` and similar plugin-prefixed forms. Low priority; only fires on dirty working trees with regenerated triage_inbox.md.

---

## Recommended follow-ups

1. **FR-aware triage producer** to give B.4 visible real-world output. Recommend handover Option 3 (manual `--fr-id` flag on `record_event.py`) as the minimum viable patch. Cost: 1 iterate (~30 min).

2. **Full Suite Runs synthesis from work_completed events** so B.3's 4-layer breakdown lights up on real repos. Two sub-options as above; (a) is the smaller change and doesn't require pipeline-wide producer rework.

3. **Path-canon ALLOWLIST extension** to fix the false-positive on shipwright's own SBOM launchPayloads.

4. **Webui CLAUDE.md trimming** — F6/F7 detectors are now firing high-signal; pre-launch hygiene work would clear them. F4 ADR-bloat findings also actionable.

---

## Sign-off

- [ ] Operator-reviewed
- [ ] Decision on B.4 follow-up: \_\_\_ (recommended: Option 3 — manual `--fr-id` flag)
- [ ] Decision on B.3 Full Suite Runs follow-up: \_\_\_
- [ ] Path-canon ALLOWLIST fix scheduled? \_\_\_

---

## Appendix: Files modified during verification

- `.shipwright/compliance/*.md` (both repos): regenerated by `update_compliance.py`. No semantic change beyond the synthetic-card seed/dismiss cycle.
- `.shipwright/agent_docs/triage_inbox.md` (both repos): regenerated.
- `.shipwright/triage.jsonl` (both repos): +1 append event, +1 status (dismissed) event per repo.
- `shipwright_events.jsonl` (both repos): +2 VERIFICATION-labeled events per repo from V-4 cases 2 and 3.

All changes are pure regen / audit-trail; no source code touched.
