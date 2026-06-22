# Requirements Traceability Matrix

Generated: 2026-06-22T21:48:01.463729+00:00

## Requirements Coverage

| Requirement | Title | Priority | Verified By | Tests | Last Verified | Status |
|-------------|-------|----------|-------------|-------|---------------|--------|
| [FR-01.01](../../.shipwright/planning/01-adopted/spec.md#fr-0101) | Orchestrate the full Shipwright SDLC pipeline — drives proje... | Must | evt-e3d2949e, evt-b0b9c422, evt-ca7b7d64, evt-7620210f | 225/225 → 1691/1716 | 2026-05-05 (iter) | COVERED |
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
| iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | bug | FR-01.11 | 53/53 | 1a9c7f4 | 2026-05-03 |
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
| Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | iterate | change |  | — | c3057ff | 2026-05-22 |
| Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | change |  | — | 69f1498 | 2026-05-22 |
| Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | change |  | — | 69f1498 | 2026-05-22 |
| mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | iterate | change |  | — | 09fedde | 2026-05-22 |
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
| Collapse phase-quality Tier-1 FAIL triage into one rolling phaseQuality:backlog action-unit; add phase-applicability gate and run_id=unknown spec-check guard | iterate | change |  | — | — | 2026-05-31 |
| Render unengaged phases as SKIP (not FAIL) in the persisted finding JSON so the skill-compliance dashboard agrees with the triage inbox | iterate | change |  | — | — | 2026-05-31 |
| Collapse the compliance detective-audit mirror into one rolling compliance:backlog action-unit (auto-dismiss + refresh + legacy retirement) | iterate | change |  | — | — | 2026-05-31 |
| events=union + churn-merge resolver/integrate_main: auto-reconcile generated artifacts on origin/main merge | iterate | change |  | — | — | 2026-06-01 |
| remove vestigial "\|\| true" from CI integration step (gate failures) + add pathlib.Path import to clear 14 F821 in test_events_log.py | iterate | change |  | 2771/2771 | — | 2026-05-31 |
| Wire shared/ test suites (shared/tests, shared/scripts/tests, shared/scripts/tools/tests) into ci.yml as blocking per-dir invocations; fix 2 non-hermetic validate_env tests via a dir conftest; make the born-red arch-md sibling skip when gitignored decision-drops are absent. | iterate | change |  | — | — | 2026-05-31 |
| Gate CI Python lint on a curated bug-focused ruff ruleset (pyflakes F + high-signal E/W); remove the \|\| true + continue-on-error neutering; provision ruff via pinned uvx; rename job to Python (lint + test). | iterate | change |  | — | — | 2026-05-31 |
| CI gate-coverage guard + workflow hardening (test-dir coverage, loose-gate allowlist, security fail-closed) | iterate | feature |  | 2674/2675 | — | 2026-05-31 |
| plugin-sync Stop-hook triage item written to durable main-repo log (worktree-aware) | iterate | bug |  | 48/49 | — | 2026-06-01 |
| D5 honors change_type+none_reason exemption; add audit_config.disabled_checks applicability gate; framework repo disables A5.6/B7/D1/G2 | iterate | change |  | — | — | 2026-06-01 |
| Document the gating ruff CI lint step in CLAUDE.md Development section. | iterate | change |  | — | — | 2026-06-01 |
| Detective audit honors event_amended corrections (group_d applies shared apply_amendments SSOT before D1-D5; new shared/scripts/lib/events_amend.py, re-exported by config.py); D4 disabled for the framework monorepo (gating-CI stale-noise); evt-5aca940d corrected to spec_impact=none. | iterate | change |  | — | — | 2026-06-01 |
| Pinned third-party GitHub Actions (setup-uv, create-or-update-comment) to commit SHAs; added SHA256 verification for the Gitleaks binary download in ci.yml + security.yml; corrected stale SECURITY.md scope (webui) and Dependabot wording. | iterate | change |  | — | — | 2026-06-01 |
| Rewrote test_upload_sarif_action_used to assert the real upload-sarif uses: line (anchored regex, version-agnostic) instead of matching a stale comment; corrected the two @v3 permission comments in security.yml to @v4. | iterate | change |  | — | — | 2026-06-01 |
| Dedup SessionStart Phase-Quality injection to once-per-event via event_once.claim_once (fail-open). | iterate | change |  | — | — | 2026-06-02 |
| Add producer-owned campaign lifecycle status (draft->active->complete): campaign_init writes status:draft to status.json + campaign.md frontmatter; campaign_progress gains a start subcommand (->active), update-status auto-sets complete when all sub-iterates complete, summary prints the top-level status; the autonomous campaign loop marks the campaign active at run start; missing status = legacy fallback to done<total. | iterate | feature |  | — | — | 2026-06-03 |
| Fix the adopt security-gate so it resolves SARIF severity at rule level, blocks on any secret, and fails closed — previously a structural false green in every adopted repo. | iterate | bug |  | — | — | 2026-06-04 |
| Scope the bloat recorder to the project root so cross-repo edits do not leak into this project marker and block its Stop gate. | iterate | bug |  | — | — | 2026-06-04 |
| C1/C2 detective-realign doc + ledger closeout | iterate | change |  | 41/41 | — | 2026-06-05 |
| Set security.yml.template checkout to fetch-depth: 1 (working-tree only) and correct the misleading diff-aware-secret-scans comment; no scanner reads git history. | iterate | change |  | — | — | 2026-06-05 |
| Enforce the FR-gate on the finalize write-path + accept same-event D3 delivery | iterate | change |  | 64/64 | — | 2026-06-05 |
| Add A5.8: execute the deployed critical-gate shell against dual-artifact fixtures (flavor-agnostic across SARIF/findings.json; skip-safe; env kill-switch). | iterate | change |  | — | — | 2026-06-05 |
| gitleaks --report-path - wrote a stray file named - instead of stdout, so the secrets leg silently returned 0 findings everywhere; report now written to a temp file and read back; smoke positive-control converted to ADR-044 CI-gated fail | iterate | bug |  | 320/320 | — | 2026-06-05 |
| Make the bloat marker recorder + Stop gate worktree-aware: strip the .worktrees/<slug>/ prefix for the baseline lookup so a worktree iterate growing an already-baselined file (ADR+bump) is not mis-classified crossing and does not false-block Stop (trg-305e2aab) | iterate | change |  | 9/9 | — | 2026-06-05 |
| B7 Rule E: exclude non-functional Conventional-Commit types (build/chore/ci/docs/style/test) from B7 by default (configurable); functional types still flagged. Supersedes the narrow Rule D + kills the ci/docs/chore backfill treadmill. | iterate | change |  | 44/44 | — | 2026-06-05 |
| Propagate degraded scanner legs (fatal/empty/truncated) via a scan_errors side-channel so the threshold/report/CI-gate layers fail closed instead of treating a dead leg as a clean 0-findings scan. | iterate | change |  | — | — | 2026-06-05 |
| triage.jsonl merge-safety + leak-guard exemption (like events) — C2 | iterate | change |  | 49/49 | — | 2026-06-05 |
| git-track triage.jsonl: gitignore negation + scaffolder self-heal (C1) | iterate | change |  | 19/19 | — | 2026-06-05 |
| triage_gc tool: machine-churn-only dismissed-pile compaction | iterate | feature |  | 387/387 | — | 2026-06-05 |
| SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift) | iterate | change |  | 617/617 | — | 2026-06-05 |
| adopt skill docs: triage.jsonl is tracked, not gitignored (D) | iterate | change |  | 24/24 | — | 2026-06-05 |
| F5 architecture-drift detector switched from a git-history oracle (dead on gitignored drops) to content reconciliation (incl. convention); new canon/blocking F11 gate check_architecture_documented sharing one oracle (shared/scripts/lib/architecture_doc.py); dead check_architecture_reviewed + run_cross_artifact_checks removed; 5 orphan architecture.md entries back-filled. | iterate | change |  | — | — | 2026-06-06 |
| triage docs + monorepo migration (campaign 2026-06-05-track-triage-jsonl, sub-iterate E) | iterate | change |  | 2839/2839 | — | 2026-06-07 |
| GC machine-churn complianceRefreshed compliance-backlog dismissals (add token to triage_gc.MACHINE_REASONS) | iterate | change |  | 24/24 | — | 2026-06-07 |
| adopt scaffolds .gitleaks.toml + hardens security.yml.template | iterate | change |  | 312/312 | — | 2026-06-07 |
| Add campaign_init --expands-triage / --from-triage so a triage item can be promoted to a campaign anchor; writes expands_triage into both status.json and the campaign.md frontmatter so the Command Center shows 'Start Campaign' on that triage card. | iterate | feature |  | — | — | 2026-06-07 |
| SBOM distinguishes not-installed from no-declared-license; not-installed is silent (no triage, dash in sbom.md), only resolved-but-no-license is surfaced. | iterate | change |  | — | — | 2026-06-07 |
| Harden iterate finalization tooling: F11 verifier accepts none_reason as a spec_impact=none justification; F0.5 surface_verification rejects compound runners fast with a clear error; arch-drift sanity test no longer false-FAILs on a post-release tree. | iterate | change |  | — | — | 2026-06-07 |
| allowlist cafebabe:deadbeef in oss_backend generated gitleaks config (GAP-3) | iterate | change |  | 56/56 | — | 2026-06-07 |
| Track campaign status.json for compliance-detective-realign + track-triage-jsonl (durable per-sub board on fresh clone / deployed WebUI; stopgap for trg-fda5f7a3). | iterate | change |  | — | — | 2026-06-07 |
| triage main-tree drift reconcile-and-commit at integrate/sync | iterate | change |  | 2861/2861 | — | 2026-06-07 |
| scaffold the append-log merge=union .gitattributes driver into managed repos (adopt E.13c + iterate self-heal) | iterate | change |  | 2884/2884 | — | 2026-06-07 |
| Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | iterate | change |  | 2913/2913 | 2293a76 | 2026-06-08 |
| evt-b9b5ddf2 | iterate | change |  | 2954/2954 | 005f643 | 2026-06-08 |
| Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | iterate | change |  | 6/6 | 7a31e33 | 2026-06-08 |
| evt-ec8e9621 | iterate | change |  | — | 77cc652 | 2026-06-08 |
| Relocate phase-quality skill-compliance roll-ups under the gitignored FINDING_DIR; resolve main_repo_root (not cwd) in the bloat marker writer+reader via a shared fail-soft resolver; defensive nested-locks gitignore canon. | iterate | change |  | — | — | 2026-06-08 |
| Relocate detective-audit JSON from repo root to .shipwright/compliance/audit-report.json; canon re-excludes audit-report.{md,json} (propagates to adopted repos); drop obsolete framework root ignore. | iterate | change |  | — | — | 2026-06-09 |
| Iterate-scoped external-review markers gitignored (not blanket); 6 tracked copies untracked. | iterate | change |  | — | — | 2026-06-09 |
| Triage dedup collapses same-id appends keep-last (reader parity); unblocks outbox sweep on producer update re-append. | iterate | change |  | — | — | 2026-06-09 |
| Campaign sub-iterates self-identify: runner Step 4 + manual --campaign/--sub-iterate-id stamp campaign/sub_iterate_id into the work_completed event via F5b --event-extras-json | iterate | feature |  | 3457/3458 | — | 2026-06-10 |
| Add triage_cli.py list --json (unioned open items + pendingDelivery) as a WebUI contract. | iterate | feature |  | — | — | 2026-06-10 |
| Gate D2V evidence markdown write behind SHIPWRIGHT_D2V_WRITE_EVIDENCE; default runs assert without writing the tracked artifact. | iterate | change |  | — | — | 2026-06-10 |
| History-calibrated complexity prior + cross-domain scope vocabulary for the iterate Stage-1 classifier | iterate | change |  | — | — | 2026-06-10 |
| triage_cli list pins stdout to UTF-8: fixes UnicodeEncodeError on Windows consoles for non-cp1252 item titles (found by the webui pending-delivery-badge boundary probe). | iterate | bug |  | — | — | 2026-06-10 |
| Exempt session_handoff.md + build_dashboard.md (with triage_inbox.md) from artifact-path-canon in all migrations; drift test; dismiss trg-6ed063ae. | iterate | change |  | — | — | 2026-06-10 |
| Campaign status projection: pure regenerate_campaign_status producer + campaign_progress regenerate CLI project per-sub-iterate status.json from the campaign.md skeleton and self-identifying work_completed events, with a never-downgrade guard (campaign 2026-06-07-tracked-campaign-status S2). | iterate | feature |  | 3426/3445 | — | 2026-06-10 |
| Per-tree campaign status.json: F5b finalize wiring + scoped churn resolver (campaign S3) | iterate | change |  | 3442/3462 | — | 2026-06-10 |
| Bloat Stop-gate resolves a file's ceiling from the worktree baseline it measures, not main (trg-28e83840) | iterate | bug |  | 3088/3088 | — | 2026-06-10 |
| Campaign status backfill + docs (S4): parse_campaign_skeleton strips markdown emphasis from id/slug cells so a legacy campaign.md (bold **C1**) matches the plain committed status.json ids (else re-projection drops completed subs); a read-only drift-guard test verifies every tracked campaign regenerates without downgrade; docs landed (hooks-and-pipeline glob-churn note, glossary Campaign-Status + token-vocab SSoT, ADR). Closes campaign 2026-06-07-tracked-campaign-status. | iterate | change |  | 3451/3471 | — | 2026-06-10 |
| Make campaign sub-iterate spec_path repo-relative POSIX instead of machine-absolute (N1, trg-196f4aa6, follow-up of campaign 2026-06-07-tracked-campaign-status): new pure campaign_paths.py (relativize_spec_path / campaign_spec_path); campaign_init writes relative; the projection self-heals on regenerate (carry + fill); one-off idempotent migration rewrote the 7 tracked campaigns (44 sub-paths). | iterate | change |  | 3468/3488 | — | 2026-06-11 |
| Fix the check_security_scan PreToolUse deploy-gate: it substring-matched the whole command, so a trigger keyword (deploy/jelastic/vercel/...) inside a quoted argument VALUE — an iterate-finalization --justification, a commit message, or an echo string — false-blocked unrelated commands. New _is_deploy_command strips quoted spans ("..." / '...') before matching; main() uses it. Real deploy commands/scripts/paths stay visible and still gate. | iterate | bug |  | 669/679 | — | 2026-06-11 |
| Add gh-pr-ci:{pr_number} action-unit: failed hard-gates on open PRs land in triage (B4.5 automerge loop-closing). Differentiated auto-resolve; session-wide symmetry; draft exclusion; truncation + filter=latest guards. | iterate | feature |  | — | — | 2026-06-11 |
| Tier-3 PR review via OpenRouter custom-script (B4.5 Phase 2): pr-review.yml workflow + pr_review.py reviewer + pr_reviewer prompts + 4 snapshot/unit test files | iterate | feature |  | 414/417 | — | 2026-06-11 |
| F11 arms GitHub-native auto-merge for iterate/* PRs (gh pr merge --auto --squash --delete-branch), branch-scoped + fail-soft (B4.5 Phase 3) | iterate | change |  | 363/363 | — | 2026-06-11 |
| triage.mark_status routes idle-main status flips to the outbox (symmetric with append_triage_item), completing campaign D1 for the status side; fixes undelivered tracked drift from WebUI/Stop-hook dismisses | iterate | change |  | 3131/3131 | — | 2026-06-11 |
| Pin UTF-8 on git-reading subprocess decodes (deep-audit WP7 F23/F26/F27) | iterate | bug |  | 8/8 | — | 2026-06-12 |
| WP5 hook project-root/worktree resolvers + project guard (F5/F6/F7/F8/F10) | iterate | bug |  | 23/23 | — | 2026-06-12 |
| UTF-8 (utf-8-sig) in config readers + errors=replace on the F0.5 runner decode (deep-audit WP8/F24+F25) | iterate | bug |  | 3515/3516 | — | 2026-06-12 |
| WP6 deep-audit fix: strict UTF-8 in resolve_churn/integrate_main git-I/O + structured commit-failure handling (F22 HIGH, F17 MED) | iterate | bug |  | 3147/3147 | — | 2026-06-12 |
| Fix two structurally-inert compliance gates (deep-audit WP3): Group H now in run_all default + on-stop coverage gate widened to A-H (F20); S4 FR-preservation join no longer raises TypeError (F21) | iterate | bug |  | 3146/3146 | — | 2026-06-12 |
| Installer/shell POSIX fixes (deep-audit WP10 F33-F38): set -e prereq counter, uv ~/.local/bin PATH, 13-plugin space-safe alias refresh, python3 resolver, dotenv-parse verify-setup | iterate | bug |  | 3157/3157 | — | 2026-06-12 |
| WP9 triage tooling hardening: F30 phaseQualityRefreshed GC token + drift meta-test, F19 GC TOCTOU recompute-under-lock, F31 control-char sanitizer on title/detail/evidence (C0+C1) in both render surfaces, F29 promote/dismiss accept outbox-only items | iterate | bug |  | 3163/3164 | — | 2026-06-12 |
| Compact agent-doc entries + impact-aware routing SSoT (IMPACT_TARGETS) + forward-only 600-char entry-budget gate; conventions.md CONTRIBUTING de-dup | iterate | change |  | — | — | 2026-06-12 |
| triage_gc union-residence under-lock recompute (a1-6/F19 follow-up) + source-derived drift meta-test + tty_sanitize extraction | iterate | change |  | 3193/3193 | — | 2026-06-12 |
| Scope the two whole-set arch-drift checkers (test_architecture_md_reflects_arch_impact + Group-F F5 detective) to decision-drops owned by this tree (run_id in committed shipwright_events.jsonl) so cross-branch campaign sibling drops no longer false-fail; fail-open when no event log. | iterate | change |  | — | — | 2026-06-12 |
| compress agent-doc backlog to one-line pointers + retire convention-routing fallback + lower entry-budget cutoff | iterate | change |  | 4279/4279 | — | 2026-06-12 |
| config-reader BOM tolerance (read_config utf-8-sig) + integrate_main commit-failure branch tests; split two at-limit test modules under 300 LOC | iterate | change |  | 19/19 | — | 2026-06-12 |
| Consolidate the project-detection predicate across all hooks onto one canonical lib.project_root.is_shipwright_project | iterate | change |  | 3203/3203 | — | 2026-06-12 |
| Serial integrate_main merge for campaign/parallel iterates: ensure_current.py refresh-if-behind guard at F11 + SHIPWRIGHT_ITERATE_AUTOMERGE defer with serial drain (auto-merge churn fix, Option A). | iterate | change |  | — | — | 2026-06-12 |
| merge=union for curated agent-docs (architecture.md + conventions.md) via a distinct CURATED_DOC_UNION_PATHS category; closes the parallel-iterate bullet-prepend cascade server-side (follow-up to automerge-serial-integrate). | iterate | change |  | — | — | 2026-06-12 |
| Delivery-Watch: F11 confirms the PR actually merges green before done (no shoot-and-forget); watch_pr_delivery.py + F2 budget-lint-before-push rule. | iterate | change |  | — | — | 2026-06-12 |
| End-to-end parallel-merge cascade integration test (3 concurrent iterates + a 3-sub campaign): proves curated-union + churn-regenerate + JSONL-union resolve together with no cascade. | iterate | change |  | — | — | 2026-06-12 |
| Windows: test-run the python3 probe so the Microsoft Store stub does not abort the marketplace cache sync | iterate | bug |  | 3284/3284 | — | 2026-06-12 |
| cross_component risk flag forces an integration-coverage test at medium+, enforced non-dodgeably by the F11 verifier recomputing the flag from the diff. Closes the composition axis of the empirical machinery. | iterate | change |  | — | — | 2026-06-12 |
| Clear bloat Group H1/H2: tighten 51 stale baseline entries to actual LOC + grandfather 8 oversize files (reducibility-catalog dogfood); follow-ups trg-af476d87 + trg-b9acb195. | iterate | change |  | — | — | 2026-06-12 |
| W2 phase-quality check SKIPs on an unresolvable run_id (mirror S2/S3); fixes the audit-context false-FAIL/false-PASS when no iterate run resolves; also fixes a latent empty-run_id crash | iterate | change |  | 3289/3289 | — | 2026-06-12 |
| Intelligent bloat gate: LOC-as-router -> falsifiable reducibility reviewer (closed catalog D/A/X/C/S/M/P/T + guardrails G1-G6); shared SSoT catalog + per-language idiom-map + reviewer dimensions across 3 surfaces + drift-protection test. | iterate | change |  | — | — | 2026-06-12 |
| Relocate resolve_main_repo_root from lib/events_log.py to lib/repo_root.py with a lazy back-compat re-export; migrate net-zero consumers; keep the two grandfathered consumers (iterate_checks, group_f) on the re-export to avoid ratcheting bloat. | iterate | change |  | — | — | 2026-06-12 |
| Coerce explicit-null affected_frs/new_frs (and tests/review) in WorkEvent.from_dict | iterate | bug |  | 697/697 | — | 2026-06-12 |
| WP1: phase-session hooks resolve identity from the stdin payload (F1); atomic event-log dedup (F14); phase_failed/stale_stop_rejected event types (F15) | iterate | change |  | 3348/3362 | — | 2026-06-12 |
| run-config concurrency & atomicity (WP2: F11/F12/F13) | iterate | bug |  | 162/162 | — | 2026-06-13 |
| extract diff-driven risk detectors + integration-coverage verifier into dedicated modules to ratchet two bloat baselines down | iterate | change |  | 3818/3830 | — | 2026-06-13 |
| adopt scaffolds profile-aware CodeQL + AUTOMERGE_SETUP doc for brownfield automerge-readiness (bloat-check deferred) | iterate | feature |  | 3737/3737 | — | 2026-06-13 |
| hook block-channel (WP4): route PostToolUse security-guard reasons to stderr; SessionStart drift gate is honest warn-only via additionalContext | iterate | change |  | 3400/3400 | — | 2026-06-13 |
| docs install/Get-Started rewrite + GitHub/auto-merge guide + marketplace metadata parity | iterate | change |  | — | — | 2026-06-13 |
| guide.md correctness audit + 21 fixes vs code/ADRs | iterate | change |  | — | — | 2026-06-13 |
| audit-3 WP11a docs/SSoT reconciliation (F3 hooks.json format, F4 registry drift, F9 outbox matrix, F28 F6 decision-drops staging) | iterate | change |  | 3796/3796 | — | 2026-06-13 |
| sync 6 stale SKILL.md/code/config items to the corrected guide (C1-C6) | iterate | change |  | 4343/4343 | — | 2026-06-13 |
| durable atomic writes (fsync) across all atomic writers | iterate | change |  | 4283/4283 | — | 2026-06-13 |
| Read run-config standalone flag without triggering the unlocked legacy migration | iterate | change |  | 164/164 | — | 2026-06-13 |
| audit-3 WP11b low-risk hardening (F18/F32/F39/F40/F41) | iterate | change |  | 4220/4236 | — | 2026-06-13 |
| code-simplify skill (OS1 / P3.2): SIMPLIFY sub-mode of CHANGE + behavior_snapshot snapshot/verify gate + F-simplify.md + guide docs | iterate | feature |  | 4082/4082 | — | 2026-06-13 |
| Align the bloat marker writer (check_file_size) to key delta/was_in_allowlist off the worktree's own baseline via a shared worktree_root_for SSoT also used by the Stop gate (trg-537334f1). | iterate | change |  | 3419/3419 | — | 2026-06-13 |
| unify the code-simplify gate with the bloat/reducibility catalog: relocate behavior_snapshot.py to shared/scripts/tools (SSoT), F-simplify adopts the catalog vocabulary, catalog cites the snapshot/verify gate as the mechanical G3 proof | iterate | change |  | 3996/3996 | — | 2026-06-13 |
| Extract duplicated cross-platform _FileLock into shared/scripts/lib/file_lock.py; both call sites import it; unify on the parent-dir-creating superset. | iterate | change |  | — | — | 2026-06-13 |
| iterate finalization | iterate | change |  | — | — | 2026-06-13 |
| Triage not for current-run work — drop plugin-sync + F0.5 triage producers | iterate | change |  | 3653/3665 | — | 2026-06-13 |
| Fold spec_checks _run_git/_git_available onto verifiers/git_helpers.py (optional timeout param, unified failure code) | iterate | change |  | 69/69 | — | 2026-06-13 |
| interleaved-serial as the single documented campaign default (branch_strategy: serial) | iterate | change |  | 3881/3881 | — | 2026-06-13 |
| Pin verifier CLI stdout to UTF-8 — fix Windows cp1252 UnicodeEncodeError on '→' in reports | iterate | bug |  | 3441/3453 | — | 2026-06-13 |
| tighten bloat baseline to actual LOC; prune 3 under-limit entries (clear Group H2) | iterate | change |  | 3442/3442 | — | 2026-06-13 |
| Document the campaign interleaved-serial run-model in docs/guide.md (new Chapter 8 Campaign Mode section + Appendix B sharpening + stale drain-example fix) | iterate | change |  | 7/7 | — | 2026-06-14 |
| tighten bloat baseline for autonomous_loop.py (current 440 to 436) | iterate | change |  | 96/96 | — | 2026-06-14 |
| Hook fan-out consolidation: once-per-event guard (claim_once_for_event) on audit/handoff/drift + session-state phase resolver (resolve_engaged_phases) | iterate | change |  | 3473/3473 | — | 2026-06-14 |
| Phase-quality rollups read load_actionable_findings (excludes sentinel run_id=unknown snapshots), so stale/degenerate audits stop driving false Tier-1 surfacing across the triage backlog, SessionStart injection, dashboard and report. | iterate | change |  | — | — | 2026-06-14 |
| Repo-agnostic agent-doc entry-budget gate (lib.agent_doc_budget + check_agent_doc_budget.py + F11 verifier check), closed the run-id-slug date hole, fixed the blank-line ADR writer, and compacted/de-bolded architecture.md + conventions.md. | iterate | change |  | — | — | 2026-06-14 |
| SessionStart phase-quality consumer drops sentinel-run (run_id unknown) FAILs from a stale findings digest and caps AFTER filtering; raw parser left uncapped. Defense-in-depth mirroring load_actionable_findings. | iterate | change |  | — | — | 2026-06-15 |
| tighten bloat baseline for iterate_checks.py (1122->1121) | iterate | change |  | 94/94 | — | 2026-06-15 |
| Remove development-provenance references (ADRs, iterate IDs, version/campaign stamps) from docs/guide.md so it documents current behavior, not its origin history | iterate | change |  | 85/85 | — | 2026-06-16 |
| Lead README and guide openings with the brand tagline 'Ship right, not just fast.' and the vibe-coding-to-agentic-engineering positioning | iterate | change |  | 24/24 | — | 2026-06-16 |
| Compliance-artifact rendering fixes: shared normalize_intent() for the Type column (RTM Verification Timeline + Build Dashboard); skip-aware PASS/COVERED for merged-work passed<total gaps in Test Evidence + RTM (never a gap-driven FAIL); unconditional Audit Report + conditional Activity Dashboard links in the Compliance Dashboard. | iterate | change |  | 701/701 | — | 2026-06-16 |
| launch version unification & Beta branding | iterate | change |  | 28/29 | — | 2026-06-17 |
| launch PII / local-path scrub | iterate | change |  | 20/20 | — | 2026-06-17 |
| align root pyproject version + de-PII a source comment | iterate | change |  | 34/34 | — | 2026-06-17 |
| pr-review truncation fails closed | iterate | bug |  | 420/423 | — | 2026-06-17 |
| anti-ratchet corrupt-baseline fail-closed | iterate | bug |  | 139/139 | — | 2026-06-17 |
| Add a once-per-(Stop,session) claim_once_for_event guard to bloat_gate_on_stop's block path so a single stop event emits one bloat block instead of one-per-plugin (12x in webui session bfd244ca). | iterate | bug |  | — | — | 2026-06-20 |
| Add a once-per-(Stop,session) claim_once_for_event guard to aggregate_triage_on_stop so one stop regenerates triage_inbox.md once instead of once-per-plugin; a failed winner releases the claim so a sibling retries. | iterate | change |  | — | — | 2026-06-20 |
| Bump cryptography 48.0.0->49.0.0 (shipwright-plan/uv.lock) and ws 8.20.1->8.21.0 + 7.5.10->7.5.11 (shipwright-test/scripts/perf/package-lock.json) to clear 3 HIGH dependency CVEs from the 2026-06-22 scheduled security scan. | iterate | change |  | — | — | 2026-06-22 |
| Add _resolve_trivy_ignorefile + wire --ignorefile <target>/.trivyignore.yaml into _run_trivy (oss_backend.py) so Trivy SCA findings can be accepted via a scoped, time-bounded repo-root register; add .trivyignore.yaml accepting CVE-2026-54285 (perf package-lock, expired_at 2026-12-22) + 4 unit tests. | iterate | change |  | — | — | 2026-06-22 |
| Add shared/tests/test_trivyignore_register.py enforcing that every .trivyignore.yaml accepted-risk entry is scoped (paths\|purls) + time-bounded (expired_at) + justified (statement); register optional (absent passes). Self-tested (rejects sloppy, accepts well-formed). | iterate | change |  | — | — | 2026-06-22 |

## Coverage Summary

| Metric | Value |
|--------|-------|
| Total splits built | 0 |
| Build sections | 0 |
| Iterate changes | 209 |
| Requirements total | 14 |
| Requirements verified | 14/14 |
| Must-have verified | 11/11 |
| Total review findings | 66 |
| Unresolved findings | 24 |

### FRs with stale verification (> 14 days)

- [FR-01.01](../../.shipwright/planning/01-adopted/spec.md) — last verified 17d ago by `evt-7620210f` (2026-05-05)

