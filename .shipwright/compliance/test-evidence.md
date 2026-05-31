# Test Evidence Report

Generated: 2026-05-31T11:52:03.721586+00:00

## Summary

| Metric | Value |
|--------|-------|
| Total test checkpoints | 78 |
| Total unit tests (latest) | 0/0 |
| New tests from iterations | +102 |

## Test Progression

| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |
|---|-------|--------|-------|-----------|-------------|--------|------|
| 1 | Gate CI Python lint on a curated bug-focused ruff ruleset (pyflakes F + high-signal E/W); remove the \|\| true + continue-on-error neutering; provision ruff via pinned uvx; rename job to Python (lint + test). | iterate | — | +0 | — | — | 2026-05-31 |
| 2 | iterate completion: test-completeness-gate | iterate | — | +0 | — | — | 2026-05-30 |
| 3 | iterate complete: P3.1 reviewer stack (spec-reviewer + doubt-reviewer cascade) | iterate | — | +0 | — | — | 2026-05-30 |
| 4 | Propagate canonical .shipwright artifact-ignore block to consuming projects via SSoT template + idempotent merge in adopt/project + drift test | iterate | — | +0 | — | — | 2026-05-30 |
| 5 | Add audit_compliance_on_stop.py: auto-emit/auto-dismiss source=compliance triage items on every iterate/changelog Stop, gated on full A-G audit coverage. | iterate | — | +0 | — | — | 2026-05-30 |
| 6 | Align 7 stale record_event tests to the C.1 FR-gate (gates all iterates incl. bug/intentless); surface CI shared-test gap (trg-f363b1ab) | iterate | — | +0 | — | — | 2026-05-30 |
| 7 | RTM: untested (0/0) events neutral; status from latest tested event (fixes 7 false FAILs); neutralize leaked verification event via event_amended | iterate | — | +0 | — | — | 2026-05-30 |
| 8 | SP3+OS2 post-Campaign-B reintegration — F-debug.md systematic-debugging sub-skill + assumptions-first interview pre-phase | iterate | unit | +0 | 317/317 | PASS | 2026-05-29 |
| 9 | suggest_iterate UserPromptSubmit hook: emit hookEventName on hookSpecificOutput (+ AST meta-test) | iterate | unit | +0 | 2558/2558 | PASS | 2026-05-29 |
| 10 | Bloat marker keyed off stdin-payload session_id (not env) in check_file_size.py + bloat_gate_on_stop.py | iterate | unit | +0 | 2549/2550 | FAIL | 2026-05-29 |
| 11 | P4.1 Skill Bootstrap Pack: using-shipwright SessionStart bootstrap + writing-plugin/plugin-cache Stop wave (SP2+SP4) | iterate | unit | +0 | 2545/2545 | PASS | 2026-05-29 |
| 12 | events.jsonl per-tree, PR-committed artifact (worktree iterate audit-log fix) | iterate | unit | +0 | 2449/2450 | FAIL | 2026-05-29 |
| 13 | Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings) | iterate | unit | +0 | 2449/2449 | PASS | 2026-05-28 |
| 14 | Correction event: spec_impact=none with proper justification field for the verifier (supersedes evt-13153a5c). | iterate | — | +0 | — | — | 2026-05-27 |
| 15 | Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check | iterate | — | +0 | — | — | 2026-05-27 |
| 16 | Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT) | iterate | — | +0 | — | — | 2026-05-27 |
| 17 | Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d). | iterate | — | +0 | — | — | 2026-05-27 |
| 18 | Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass + audit_staleness coverage extension + merge-not-rebase doc convention. | iterate | — | +0 | — | — | 2026-05-27 |
| 19 | B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | iterate | unit | +26 | 1104/1104 | PASS | 2026-05-26 |
| 20 | Pre-commit anti-ratchet hook + bloat-check CI workflow + bloat-exception ADR template + shared glossary (Campaign A.defense, closes Campaign A defense-in-depth layer) | iterate | mixed | +0 | 41/41 | PASS | 2026-05-25 |
| 21 | fix bloat_gate_on_stop.py Stop-hook schema violation | iterate | unit | +0 | 131/131 | PASS | 2026-05-25 |
| 22 | Campaign A.review: bloat reviewer prompts (Karpathy+Osmani+Shipwright) + Group H detective audit (H0-H6) | iterate | mixed | +0 | 14/14 | PASS | 2026-05-25 |
| 23 | Phase 0 bloat baseline inventory — activates A.foundation Stop-Gate | iterate | — | +0 | — | — | 2026-05-25 |
| 24 | Bloat Loop-Gate (Campaign A.foundation = A1+A2+A3): runtime-prompt classification, per-session marker writer, blocking Stop-Gate, registered in every plugin | iterate | unit | +0 | 2678/2678 | PASS | 2026-05-25 |
| 25 | SBOM triage producer cluster-collapse | iterate | mixed | +0 | 514/514 | PASS | 2026-05-23 |
| 26 | SBOM resolver pin to per-manifest .venv METADATA | iterate | mixed | +0 | 497/497 | PASS | 2026-05-23 |
| 27 | Resolve architecture.md merge-conflict markers (lines 90-94) + extend ALLOWLIST[compliance] to include finalize_security_compliance.py whose cross-plugin path comment trips the hyphen-segment regex blind spot | iterate | unit | +0 | 2/3 | FAIL | 2026-05-23 |
| 28 | C1 design verifier (and sister manifest-exists check) skip on scope=library projects via _is_no_ui_scope helper; audit translates ok=None to status=skip via existing check_result_to_finding | iterate | unit | +0 | 19/19 | PASS | 2026-05-23 |
| 29 | iterate finalization | iterate | — | +0 | — | — | 2026-05-23 |
| 30 | Architecture-md drift protection test + 11 historical drift entries backfilled + 3 discipline learnings in conventions.md (TDD RED-first, F0/F11 leak-guard symmetry, F2 flag-md coupling) | iterate | unit | +0 | 2/2 | PASS | 2026-05-23 |
| 31 | F11 verifier multi-commit-aware via run_id lookup (fixes false positives on iterate-f7-tracked-event-log-commit) | iterate | unit | +0 | 70/70 | PASS | 2026-05-23 |
| 32 | iterate skill F7b: seals tracked event-log appends to prevent silent reset wipe (commit_event_followup.py + SKILL.md + 6 tests) | iterate | unit | +0 | 6/6 | PASS | 2026-05-22 |
| 33 | compliance reconciliation: D1 spec-FR coverage — multi-FR event covering FR-01.03/04/05/06/07/08/09/12 (post-2026-05-04 watermark gap; no source/test/spec changes) | iterate | — | +0 | — | — | 2026-05-22 |
| 34 | mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | iterate | — | +0 | — | — | 2026-05-22 |
| 35 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 36 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 37 | Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | iterate | — | +0 | — | — | 2026-05-22 |
| 38 | deterministic render timestamps from max(event.ts) | iterate | unit | +34 | 34/34 | PASS | 2026-05-21 |
| 39 | empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | iterate | unit | +0 | 2621/2621 | PASS | 2026-05-21 |
| 40 | VERIFICATION: bug+change-type — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 41 | VERIFICATION artifact (amended: leaked from 2026-05-21 empirical-verification campaign; no real FR work) — neutralized by iterate-2026-05-30-rtm-covered-ignore-untested-events | iterate | — | +0 | — | — | 2026-05-21 |
| 42 | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 43 | Artifact-based GitHub security producer for Triage Inbox | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 44 | escape pipe and newline in markdown table cells | iterate | unit | +23 | 23/23 | PASS | 2026-05-20 |
| 45 | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | mixed | +0 | 3507/3507 | PASS | 2026-05-18 |
| 46 | triage detector dedup + auto-resolve (rebased onto #31) | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 47 | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | unit | +0 | 140/140 | PASS | 2026-05-16 |
| 48 | triage detector dedup + auto-resolve | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 49 | fix adopt external-review config defaults | iterate | mixed | +0 | 304/304 | PASS | 2026-05-16 |
| 50 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | mixed | +0 | 2519/2526 | FAIL | 2026-05-16 |
| 51 | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | mixed | +0 | 312/312 | PASS | 2026-05-15 |
| 52 | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | mixed | +0 | 40/40 | PASS | 2026-05-14 |
| 53 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 54 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 55 | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | unit | +0 | 16/16 | PASS | 2026-05-09 |
| 56 | evt-f66286bf | iterate | — | +0 | — | — | 2026-05-07 |
| 57 | evt-623a29ad | iterate | — | +0 | — | — | 2026-05-07 |
| 58 | F0.5 empirical-test backfill | iterate | unit | +0 | 1575/1575 | PASS | 2026-05-06 |
| 59 | F0.5 End-to-End Verification Gate | iterate | unit | +0 | 1548/1548 | PASS | 2026-05-06 |
| 60 | hooks-consistency parser handles quoted commands — 27/27 green | iterate | unit | +0 | 1297/1297 | PASS | 2026-05-06 |
| 61 | post-migration canon cleanup — 9 tests green | iterate | unit | +0 | 1270/1270 | PASS | 2026-05-06 |
| 62 | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | unit | +0 | 34/34 | PASS | 2026-05-05 |
| 63 | verifier accepts drop-dir entries + dashboard short-SHAs | iterate | unit | +0 | 32/32 | PASS | 2026-05-05 |
| 64 | adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | unit | +0 | 241/241 | PASS | 2026-05-05 |
| 65 | FR-table parser accepts 5-col adopt format + drift protection | iterate | unit | +0 | 1594/1628 | FAIL | 2026-05-05 |
| 66 | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | unit | +0 | 12/12 | PASS | 2026-05-05 |
| 67 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | unit | +0 | 1691/1716 | FAIL | 2026-05-05 |
| 68 | F runner contract mandates reviews (ADR-029) | iterate | unit | +0 | 188/188 | PASS | 2026-05-04 |
| 69 | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | unit | +0 | 1539/1539 | PASS | 2026-05-04 |
| 70 | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | unit | +19 | 19/19 | PASS | 2026-05-03 |
| 71 | changelog MSYS path-mangling linter | iterate | unit | +0 | 19/19 | PASS | 2026-05-03 |
| 72 | hooks.json quoting (deferred from ADR-020) | iterate | unit | +0 | 13/13 | PASS | 2026-05-03 |
| 73 | iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | unit | +0 | 53/53 | PASS | 2026-05-03 |
| 74 | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | unit | +0 | 47/47 | PASS | 2026-05-03 |
| 75 | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | unit | +0 | 249/249 | PASS | 2026-05-03 |
| 76 | fix hook_installer Shape A -> B | iterate | unit | +0 | 5/5 | PASS | 2026-05-03 |
| 77 | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | unit | +0 | 233/233 | PASS | 2026-05-02 |
| 78 | post-adoption framework cleanup (Sub-1A through 1D) | iterate | unit | +0 | 225/225 | PASS | 2026-05-02 |

## Full Suite Runs

| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |
|-----|---------|------|-------------|-------|-----|-------|------|
| 1 | iterate | 312/312 | — | — | — | — | 2026-05-15 |
| 2 | iterate | 2519/2526 | — | — | — | — | 2026-05-16 |
| 3 | iterate | 304/304 | — | — | — | — | 2026-05-16 |
| 4 | iterate | 1776/1783 | — | — | — | — | 2026-05-16 |
| 5 | iterate | 140/140 | — | — | — | — | 2026-05-16 |
| 6 | iterate | 1776/1783 | — | — | — | — | 2026-05-16 |
| 7 | iterate | 3507/3507 | — | — | — | — | 2026-05-18 |
| 8 | iterate | 23/23 | — | — | — | — | 2026-05-20 |
| 9 | iterate | 122/122 | — | — | — | — | 2026-05-20 |
| 10 | iterate | 122/122 | — | — | — | — | 2026-05-20 |
| 11 | iterate | 2621/2621 | — | — | — | — | 2026-05-21 |
| 12 | iterate | 34/34 | — | — | — | — | 2026-05-21 |
| 13 | iterate | 6/6 | — | — | — | — | 2026-05-22 |
| 14 | iterate | 70/70 | — | — | — | — | 2026-05-23 |
| 15 | iterate | 2/2 | — | — | — | — | 2026-05-23 |
| 16 | iterate | 19/19 | — | — | — | — | 2026-05-23 |
| 17 | iterate | 2/3 | — | — | — | — | 2026-05-23 |
| 18 | iterate | 497/497 | — | — | — | — | 2026-05-23 |
| 19 | iterate | 514/514 | — | — | — | — | 2026-05-23 |
| 20 | iterate | 2678/2678 | — | — | — | — | 2026-05-25 |
| 21 | iterate | 14/14 | — | — | — | — | 2026-05-25 |
| 22 | iterate | 131/131 | — | — | — | — | 2026-05-25 |
| 23 | iterate | 41/41 | — | — | — | — | 2026-05-25 |
| 24 | iterate | 1104/1104 | — | — | — | — | 2026-05-26 |
| 25 | iterate | 2449/2449 | — | — | — | — | 2026-05-28 |
| 26 | iterate | 2449/2450 | — | — | — | — | 2026-05-29 |
| 27 | iterate | 2545/2545 | — | — | — | — | 2026-05-29 |
| 28 | iterate | 2549/2550 | — | — | — | — | 2026-05-29 |
| 29 | iterate | 2558/2558 | — | — | — | — | 2026-05-29 |
| 30 | iterate | 317/317 | — | — | — | — | 2026-05-29 |

## Code Review Evidence

| Event | Review Type | Findings | Fixed | Status |
|-------|------------|----------|-------|--------|
| B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | external-iterate-review | 12 | 12 | PASS |

