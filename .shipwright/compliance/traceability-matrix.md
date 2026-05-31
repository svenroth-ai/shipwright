# Requirements Traceability Matrix

Generated: 2026-05-31T11:53:17.529858+00:00

## Requirements Coverage

| Requirement | Title | Priority | Verified By | Tests | Last Verified | Status |
|-------------|-------|----------|-------------|-------|---------------|--------|
| [FR-01.01](../../.shipwright/planning/01-adopted/spec.md#fr-0101) | Orchestrate the full Shipwright SDLC pipeline — drives proje... | Must | evt-e3d2949e, evt-b0b9c422, evt-ca7b7d64, evt-7620210f | 225/225 → 1691/1716 | 2026-05-05 (iter) | FAIL |
| [FR-01.02](../../.shipwright/planning/01-adopted/spec.md#fr-0102) | Decompose project requirements (IREB) into well-scoped plann... | Must | evt-e3d2949e, evt-b0b9c422, evt-ca7b7d64, evt-7620210f +1 | 225/225 → 140/140 | 2026-05-16 (iter) | COVERED |
| [FR-01.03](../../.shipwright/planning/01-adopted/spec.md#fr-0103) | AI-assisted deep planning with research, optional interview,... | Must | evt-e3d2949e, evt-ca7b7d64, evt-ddb23fe7 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.04](../../.shipwright/planning/01-adopted/spec.md#fr-0104) | Generate UI mockups from IREB specs as standalone HTML scree... | Should | evt-e3d2949e, evt-ca7b7d64, evt-ddb23fe7 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.05](../../.shipwright/planning/01-adopted/spec.md#fr-0105) | Implement code from /shipwright-plan sections with TDD (red-... | Must | evt-e3d2949e, evt-ca7b7d64, evt-ddb23fe7 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.06](../../.shipwright/planning/01-adopted/spec.md#fr-0106) | Run unit tests, E2E tests (Playwright), smoke tests, and sec... | Must | evt-e3d2949e, evt-ca7b7d64, evt-c4ae8ef7, evt-ddb23fe7 | 225/225 → 19/19 | 2026-05-03 (iter) | COVERED |
| [FR-01.07](../../.shipwright/planning/01-adopted/spec.md#fr-0107) | Security scanning chain (Aikido + Semgrep + Trivy + Gitleaks... | Must | evt-e3d2949e, evt-ca7b7d64, evt-ddb23fe7 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.08](../../.shipwright/planning/01-adopted/spec.md#fr-0108) | Deploy to configured targets with smoke testing and rollback... | Should | evt-e3d2949e, evt-ca7b7d64, evt-ddb23fe7 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.09](../../.shipwright/planning/01-adopted/spec.md#fr-0109) | Parse Conventional Commits from git history, generate Keep-a... | Must | evt-e3d2949e, evt-ca7b7d64, evt-530b0980, evt-ddb23fe7 | 225/225 → 19/19 | 2026-05-03 (iter) | COVERED |
| [FR-01.10](../../.shipwright/planning/01-adopted/spec.md#fr-0110) | Generate audit-ready compliance documentation (RTM, test evi... | Must | evt-e3d2949e, evt-ca7b7d64, evt-30338dac, evt-a3888caf +1 | 225/225 → 140/140 | 2026-05-16 (iter) | COVERED |
| [FR-01.11](../../.shipwright/planning/01-adopted/spec.md#fr-0111) | Complexity-adaptive SDLC for ongoing changes — auto-detects ... | Must | evt-e3d2949e, evt-6c637864, evt-baaf4b0e, evt-ca7b7d64 +15 | 225/225 → 2/2 | 2026-05-23 (iter) | COVERED |
| [FR-01.12](../../.shipwright/planning/01-adopted/spec.md#fr-0112) | Local browser preview — start dev server for the target proj... | May | evt-e3d2949e, evt-ca7b7d64, evt-ddb23fe7 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.13](../../.shipwright/planning/01-adopted/spec.md#fr-0113) | Onboard an existing (brownfield) repository into the Shipwri... | Must | evt-e3d2949e, evt-273bbb54, evt-b0b9c422, evt-aab7ddbd +5 | 225/225 → 304/304 | 2026-05-16 (iter) | COVERED |
| [FR-01.14](../../.shipwright/planning/01-adopted/spec.md#fr-0114) | Pre-backlog triage buffer — findings from local hooks/scans/... | Must | evt-3f488ddc, evt-32f2f1f4, evt-84dbdf5e, evt-e14e5f26 +3 | 1642/1649 → 122/122 | 2026-05-20 (iter) | COVERED |

## Verification Timeline

| Event | Source | Type | FRs | Tests | Commit | Date |
|-------|--------|------|-----|-------|--------|------|
| post-adoption framework cleanup (Sub-1A through 1D) | iterate | change | FR-01.01, FR-01.02, FR-01.03 +10 | 225/225 | 3db485b | 2026-05-02 |
| shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | change | FR-01.13 | 233/233 | cffe191 | 2026-05-02 |
| fix hook_installer Shape A -> B | iterate | bug | FR-01.11 | 5/5 | 1ddf9ae | 2026-05-03 |
| suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | bug | FR-01.13, FR-01.02, FR-01.01 | 249/249 | b24f804 | 2026-05-03 |
| iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | feature | FR-01.13 | 47/47 | 9953008 | 2026-05-03 |
| iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | fix | FR-01.11 | 53/53 | 1a9c7f4 | 2026-05-03 |
| hooks.json quoting (deferred from ADR-020) | iterate | bug | FR-01.01, FR-01.02, FR-01.03 +10 | 13/13 | 6ca369d | 2026-05-03 |
| changelog MSYS path-mangling linter | iterate | bug | FR-01.09 | 19/19 | a13fd64 | 2026-05-03 |
| test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | feature | FR-01.06 | 19/19 | 216f8b3 | 2026-05-03 |
| iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | bug | FR-01.11 | 1539/1539 | 5415ed6 | 2026-05-04 |
| F runner contract mandates reviews (ADR-029) | iterate | feature | FR-01.11 | 188/188 | f6a14fc | 2026-05-04 |
| plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | bug | FR-01.11, FR-01.13, FR-01.02 +1 | 1691/1716 | a05ff22 | 2026-05-05 |
| post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | bug | FR-01.11 | 12/12 | afb3b63 | 2026-05-05 |
| FR-table parser accepts 5-col adopt format + drift protection | iterate | bug | FR-01.10, FR-01.13 | 1594/1628 | 656f96f | 2026-05-05 |
| adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | bug | FR-01.13, FR-01.11 | 241/241 | f4f7229 | 2026-05-05 |
| verifier accepts drop-dir entries + dashboard short-SHAs | iterate | bug | FR-01.11 | 32/32 | f1f0447 | 2026-05-05 |
| loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | bug | FR-01.11 | 34/34 | 49eca25 | 2026-05-05 |
| post-migration canon cleanup — 9 tests green | iterate | bug |  | 1270/1270 | 7383c18 | 2026-05-06 |
| hooks-consistency parser handles quoted commands — 27/27 green | iterate | bug | FR-01.11 | 1297/1297 | c5e6cb3 | 2026-05-06 |
| F0.5 End-to-End Verification Gate | iterate | feature | FR-01.11 | 1548/1548 | 88f3398 | 2026-05-06 |
| F0.5 empirical-test backfill | iterate | change | FR-01.11 | 1575/1575 | 0df63f2 | 2026-05-06 |
| evt-623a29ad | iterate | change |  | — | 686e7cc | 2026-05-07 |
| evt-f66286bf | iterate | change |  | — | 99fc87b | 2026-05-07 |
| known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | bug |  | 16/16 | f8d44da | 2026-05-09 |
| Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | feature | FR-01.14 | 1642/1649 | 6ba7df1 | 2026-05-11 |
| Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | feature | FR-01.14 | 1642/1649 | f638908 | 2026-05-11 |
| Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | feature | FR-01.14 | 40/40 | aab9bd7 | 2026-05-14 |
| RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | bug | FR-01.10 | 312/312 | ea24bf4 | 2026-05-15 |
| events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | bug | FR-01.11 | 2519/2526 | 34a7987 | 2026-05-16 |
| fix adopt external-review config defaults | iterate | bug | FR-01.13 | 304/304 | 3f5777d | 2026-05-16 |
| triage detector dedup + auto-resolve | iterate | bug | FR-01.14 | 1776/1783 | 931e6b5 | 2026-05-16 |
| spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | feature | FR-01.11, FR-01.10, FR-01.02 | 140/140 | c16d711 | 2026-05-16 |
| triage detector dedup + auto-resolve (rebased onto #31) | iterate | bug | FR-01.14 | 1776/1783 | cd957a0 | 2026-05-16 |
| fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | bug |  | 3507/3507 | 21cef22 | 2026-05-18 |
| escape pipe and newline in markdown table cells | iterate | bug |  | 23/23 | 9dd6c8b | 2026-05-20 |
| Artifact-based GitHub security producer for Triage Inbox | iterate | feature | FR-01.14 | 122/122 | 6f5dd5f | 2026-05-20 |
| Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | feature | FR-01.14 | 122/122 | 861c0fd | 2026-05-20 |
| VERIFICATION artifact (amended: leaked from 2026-05-21 empirical-verification campaign; no real FR work) — neutralized by iterate-2026-05-30-rtm-covered-ignore-untested-events | iterate | feature |  | — | 376c870 | 2026-05-21 |
| VERIFICATION: bug+change-type — should pass | iterate | bug |  | — | 376c870 | 2026-05-21 |
| empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | iterate | change |  | 2621/2621 | d8f3c05 | 2026-05-21 |
| deterministic render timestamps from max(event.ts) | iterate | bug |  | 34/34 | d325fd6 | 2026-05-21 |
| Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | iterate | Clear 5 compliance triage bloat items (G2 stoplist + G3 ADR stubs + 3x artifact-stale) from artifact-polish/empirical-verification campaigns |  | — | c3057ff | 2026-05-22 |
| Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts |  | — | 69f1498 | 2026-05-22 |
| Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts |  | — | 69f1498 | 2026-05-22 |
| mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | iterate | Fix partial-run audit incorrectly dismissing out-of-scope compliance triage items |  | — | 09fedde | 2026-05-22 |
| compliance reconciliation: D1 spec-FR coverage — multi-FR event covering FR-01.03/04/05/06/07/08/09/12 (post-2026-05-04 watermark gap; no source/test/spec changes) | iterate | change | FR-01.03, FR-01.04, FR-01.05 +5 | — | 1ca566a | 2026-05-22 |
| iterate skill F7b: seals tracked event-log appends to prevent silent reset wipe (commit_event_followup.py + SKILL.md + 6 tests) | iterate | change | FR-01.11 | 6/6 | 24d77be | 2026-05-22 |
| F11 verifier multi-commit-aware via run_id lookup (fixes false positives on iterate-f7-tracked-event-log-commit) | iterate | change | FR-01.11 | 70/70 | c1c8820 | 2026-05-23 |
| Architecture-md drift protection test + 11 historical drift entries backfilled + 3 discipline learnings in conventions.md (TDD RED-first, F0/F11 leak-guard symmetry, F2 flag-md coupling) | iterate | change | FR-01.11 | 2/2 | 1429aee | 2026-05-23 |
| iterate finalization | iterate | change |  | — | — | 2026-05-23 |
| C1 design verifier (and sister manifest-exists check) skip on scope=library projects via _is_no_ui_scope helper; audit translates ok=None to status=skip via existing check_result_to_finding | iterate | change |  | 19/19 | c7b1b29 | 2026-05-23 |
| Resolve architecture.md merge-conflict markers (lines 90-94) + extend ALLOWLIST[compliance] to include finalize_security_compliance.py whose cross-plugin path comment trips the hyphen-segment regex blind spot | iterate | bug |  | 2/3 | 9e26a9c | 2026-05-23 |
| SBOM resolver pin to per-manifest .venv METADATA | iterate | bug |  | 497/497 | fc1a7a8 | 2026-05-23 |
| SBOM triage producer cluster-collapse | iterate | change |  | 514/514 | 6be7aae | 2026-05-23 |
| Bloat Loop-Gate (Campaign A.foundation = A1+A2+A3): runtime-prompt classification, per-session marker writer, blocking Stop-Gate, registered in every plugin | iterate | feature |  | 2678/2678 | bfd4e63 | 2026-05-25 |
| Phase 0 bloat baseline inventory — activates A.foundation Stop-Gate | iterate | change |  | — | 66ec453 | 2026-05-25 |
| Campaign A.review: bloat reviewer prompts (Karpathy+Osmani+Shipwright) + Group H detective audit (H0-H6) | iterate | feature |  | 14/14 | babf9fc | 2026-05-25 |
| fix bloat_gate_on_stop.py Stop-hook schema violation | iterate | bug |  | 131/131 | 193b7f5 | 2026-05-25 |
| Pre-commit anti-ratchet hook + bloat-check CI workflow + bloat-exception ADR template + shared glossary (Campaign A.defense, closes Campaign A defense-in-depth layer) | iterate | feature |  | 41/41 | 55be715 | 2026-05-25 |
| B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | iterate | change |  | 1104/1104 | fbde435 | 2026-05-26 |
| Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass + audit_staleness coverage extension + merge-not-rebase doc convention. | iterate | change |  | — | 54ecb17 | 2026-05-27 |
| Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d). | iterate | change |  | — | 54ecb17 | 2026-05-27 |
| Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT) | iterate | change |  | — | b3ff2eb | 2026-05-27 |
| Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check | iterate | change |  | — | 25fd988 | 2026-05-27 |
| Correction event: spec_impact=none with proper justification field for the verifier (supersedes evt-13153a5c). | iterate | change |  | — | 25fd988 | 2026-05-27 |
| Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings) | iterate | bug |  | 2449/2449 | 9d9b1e5 | 2026-05-28 |
| events.jsonl per-tree, PR-committed artifact (worktree iterate audit-log fix) | iterate | bug |  | 2449/2450 | — | 2026-05-29 |
| P4.1 Skill Bootstrap Pack: using-shipwright SessionStart bootstrap + writing-plugin/plugin-cache Stop wave (SP2+SP4) | iterate | feature |  | 2545/2545 | e788870 | 2026-05-29 |
| Bloat marker keyed off stdin-payload session_id (not env) in check_file_size.py + bloat_gate_on_stop.py | iterate | bug |  | 2549/2550 | 4adfd44 | 2026-05-29 |
| suggest_iterate UserPromptSubmit hook: emit hookEventName on hookSpecificOutput (+ AST meta-test) | iterate | bug |  | 2558/2558 | — | 2026-05-29 |
| SP3+OS2 post-Campaign-B reintegration — F-debug.md systematic-debugging sub-skill + assumptions-first interview pre-phase | iterate | feature |  | 317/317 | — | 2026-05-29 |
| RTM: untested (0/0) events neutral; status from latest tested event (fixes 7 false FAILs); neutralize leaked verification event via event_amended | iterate | bug |  | — | — | 2026-05-30 |
| Align 7 stale record_event tests to the C.1 FR-gate (gates all iterates incl. bug/intentless); surface CI shared-test gap (trg-f363b1ab) | iterate | bug |  | — | — | 2026-05-30 |
| Add audit_compliance_on_stop.py: auto-emit/auto-dismiss source=compliance triage items on every iterate/changelog Stop, gated on full A-G audit coverage. | iterate | feature |  | — | — | 2026-05-30 |
| Propagate canonical .shipwright artifact-ignore block to consuming projects via SSoT template + idempotent merge in adopt/project + drift test | iterate | change |  | — | — | 2026-05-30 |
| iterate complete: P3.1 reviewer stack (spec-reviewer + doubt-reviewer cascade) | iterate | change |  | — | — | 2026-05-30 |
| iterate completion: test-completeness-gate | iterate | change |  | — | — | 2026-05-30 |
| Wire shared/ test suites (shared/tests, shared/scripts/tests, shared/scripts/tools/tests) into ci.yml as blocking per-dir invocations; fix 2 non-hermetic validate_env tests via a dir conftest; make the born-red arch-md sibling skip when gitignored decision-drops are absent. | iterate | change |  | — | — | 2026-05-31 |

## Coverage Summary

| Metric | Value |
|--------|-------|
| Total splits built | 0 |
| Build sections | 0 |
| Iterate changes | 78 |
| Requirements total | 14 |
| Requirements verified | 14/14 |
| Must-have verified | 11/11 |
| Total review findings | 12 |
| Unresolved findings | 0 |

### FRs with stale verification (> 14 days)

- [FR-01.01](../../.shipwright/planning/01-adopted/spec.md) — last verified 17d ago by `evt-7620210f` (2026-05-05)

