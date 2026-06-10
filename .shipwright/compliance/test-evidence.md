# Test Evidence Report

Generated: 2026-06-10T22:55:27.413208+00:00

## Summary

| Metric | Value |
|--------|-------|
| Total test checkpoints | 136 |
| Total unit tests (latest) | 3451/3471 |
| New tests from iterations | +166 |

## Test Progression

| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |
|---|-------|--------|-------|-----------|-------------|--------|------|
| 1 | Campaign status backfill + docs (S4): parse_campaign_skeleton strips markdown emphasis from id/slug cells so a legacy campaign.md (bold **C1**) matches the plain committed status.json ids (else re-projection drops completed subs); a read-only drift-guard test verifies every tracked campaign regenerates without downgrade; docs landed (hooks-and-pipeline glob-churn note, glossary Campaign-Status + token-vocab SSoT, ADR). Closes campaign 2026-06-07-tracked-campaign-status. | iterate | unit | +0 | 3451/3471 | FAIL | 2026-06-10 |
| 2 | Per-tree campaign status.json: F5b finalize wiring + scoped churn resolver (campaign S3) | iterate | unit | +0 | 3442/3462 | FAIL | 2026-06-10 |
| 3 | Campaign status projection: pure regenerate_campaign_status producer + campaign_progress regenerate CLI project per-sub-iterate status.json from the campaign.md skeleton and self-identifying work_completed events, with a never-downgrade guard (campaign 2026-06-07-tracked-campaign-status S2). | iterate | unit | +0 | 3426/3445 | FAIL | 2026-06-10 |
| 4 | Exempt session_handoff.md + build_dashboard.md (with triage_inbox.md) from artifact-path-canon in all migrations; drift test; dismiss trg-6ed063ae. | iterate | — | +0 | — | — | 2026-06-10 |
| 5 | triage_cli list pins stdout to UTF-8: fixes UnicodeEncodeError on Windows consoles for non-cp1252 item titles (found by the webui pending-delivery-badge boundary probe). | iterate | — | +0 | — | — | 2026-06-10 |
| 6 | History-calibrated complexity prior + cross-domain scope vocabulary for the iterate Stage-1 classifier | iterate | — | +0 | — | — | 2026-06-10 |
| 7 | Gate D2V evidence markdown write behind SHIPWRIGHT_D2V_WRITE_EVIDENCE; default runs assert without writing the tracked artifact. | iterate | — | +0 | — | — | 2026-06-10 |
| 8 | Add triage_cli.py list --json (unioned open items + pendingDelivery) as a WebUI contract. | iterate | — | +0 | — | — | 2026-06-10 |
| 9 | Campaign sub-iterates self-identify: runner Step 4 + manual --campaign/--sub-iterate-id stamp campaign/sub_iterate_id into the work_completed event via F5b --event-extras-json | iterate | mixed | +0 | 3457/3458 | FAIL | 2026-06-10 |
| 10 | Triage dedup collapses same-id appends keep-last (reader parity); unblocks outbox sweep on producer update re-append. | iterate | — | +0 | — | — | 2026-06-09 |
| 11 | Iterate-scoped external-review markers gitignored (not blanket); 6 tracked copies untracked. | iterate | — | +0 | — | — | 2026-06-09 |
| 12 | Relocate detective-audit JSON from repo root to .shipwright/compliance/audit-report.json; canon re-excludes audit-report.{md,json} (propagates to adopted repos); drop obsolete framework root ignore. | iterate | — | +0 | — | — | 2026-06-09 |
| 13 | Relocate phase-quality skill-compliance roll-ups under the gitignored FINDING_DIR; resolve main_repo_root (not cwd) in the bloat marker writer+reader via a shared fail-soft resolver; defensive nested-locks gitignore canon. | iterate | — | +0 | — | — | 2026-06-08 |
| 14 | evt-ec8e9621 | iterate | — | +0 | — | — | 2026-06-08 |
| 15 | Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | iterate | unit | +6 | 6/6 | PASS | 2026-06-08 |
| 16 | evt-b9b5ddf2 | iterate | unit | +36 | 2954/2954 | PASS | 2026-06-08 |
| 17 | Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | iterate | unit | +22 | 2913/2913 | PASS | 2026-06-08 |
| 18 | scaffold the append-log merge=union .gitattributes driver into managed repos (adopt E.13c + iterate self-heal) | iterate | unit | +0 | 2884/2884 | PASS | 2026-06-07 |
| 19 | triage main-tree drift reconcile-and-commit at integrate/sync | iterate | mixed | +0 | 2861/2861 | PASS | 2026-06-07 |
| 20 | Track campaign status.json for compliance-detective-realign + track-triage-jsonl (durable per-sub board on fresh clone / deployed WebUI; stopgap for trg-fda5f7a3). | iterate | — | +0 | — | — | 2026-06-07 |
| 21 | allowlist cafebabe:deadbeef in oss_backend generated gitleaks config (GAP-3) | iterate | unit | +0 | 56/56 | PASS | 2026-06-07 |
| 22 | Harden iterate finalization tooling: F11 verifier accepts none_reason as a spec_impact=none justification; F0.5 surface_verification rejects compound runners fast with a clear error; arch-drift sanity test no longer false-FAILs on a post-release tree. | iterate | — | +0 | — | — | 2026-06-07 |
| 23 | SBOM distinguishes not-installed from no-declared-license; not-installed is silent (no triage, dash in sbom.md), only resolved-but-no-license is surfaced. | iterate | — | +0 | — | — | 2026-06-07 |
| 24 | Add campaign_init --expands-triage / --from-triage so a triage item can be promoted to a campaign anchor; writes expands_triage into both status.json and the campaign.md frontmatter so the Command Center shows 'Start Campaign' on that triage card. | iterate | — | +0 | — | — | 2026-06-07 |
| 25 | adopt scaffolds .gitleaks.toml + hardens security.yml.template | iterate | unit | +0 | 312/312 | PASS | 2026-06-07 |
| 26 | GC machine-churn complianceRefreshed compliance-backlog dismissals (add token to triage_gc.MACHINE_REASONS) | iterate | unit | +0 | 24/24 | PASS | 2026-06-07 |
| 27 | triage docs + monorepo migration (campaign 2026-06-05-track-triage-jsonl, sub-iterate E) | iterate | unit | +0 | 2839/2839 | PASS | 2026-06-07 |
| 28 | F5 architecture-drift detector switched from a git-history oracle (dead on gitignored drops) to content reconciliation (incl. convention); new canon/blocking F11 gate check_architecture_documented sharing one oracle (shared/scripts/lib/architecture_doc.py); dead check_architecture_reviewed + run_cross_artifact_checks removed; 5 orphan architecture.md entries back-filled. | iterate | — | +0 | — | — | 2026-06-06 |
| 29 | adopt skill docs: triage.jsonl is tracked, not gitignored (D) | iterate | unit | +0 | 24/24 | PASS | 2026-06-05 |
| 30 | SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift) | iterate | unit | +0 | 617/617 | PASS | 2026-06-05 |
| 31 | triage_gc tool: machine-churn-only dismissed-pile compaction | iterate | unit | +0 | 387/387 | PASS | 2026-06-05 |
| 32 | git-track triage.jsonl: gitignore negation + scaffolder self-heal (C1) | iterate | unit | +0 | 19/19 | PASS | 2026-06-05 |
| 33 | triage.jsonl merge-safety + leak-guard exemption (like events) — C2 | iterate | unit | +0 | 49/49 | PASS | 2026-06-05 |
| 34 | Propagate degraded scanner legs (fatal/empty/truncated) via a scan_errors side-channel so the threshold/report/CI-gate layers fail closed instead of treating a dead leg as a clean 0-findings scan. | iterate | — | +0 | — | — | 2026-06-05 |
| 35 | B7 Rule E: exclude non-functional Conventional-Commit types (build/chore/ci/docs/style/test) from B7 by default (configurable); functional types still flagged. Supersedes the narrow Rule D + kills the ci/docs/chore backfill treadmill. | iterate | unit | +0 | 44/44 | PASS | 2026-06-05 |
| 36 | Make the bloat marker recorder + Stop gate worktree-aware: strip the .worktrees/<slug>/ prefix for the baseline lookup so a worktree iterate growing an already-baselined file (ADR+bump) is not mis-classified crossing and does not false-block Stop (trg-305e2aab) | iterate | unit | +0 | 9/9 | PASS | 2026-06-05 |
| 37 | gitleaks --report-path - wrote a stray file named - instead of stdout, so the secrets leg silently returned 0 findings everywhere; report now written to a temp file and read back; smoke positive-control converted to ADR-044 CI-gated fail | iterate | unit | +0 | 320/320 | PASS | 2026-06-05 |
| 38 | Add A5.8: execute the deployed critical-gate shell against dual-artifact fixtures (flavor-agnostic across SARIF/findings.json; skip-safe; env kill-switch). | iterate | — | +0 | — | — | 2026-06-05 |
| 39 | Enforce the FR-gate on the finalize write-path + accept same-event D3 delivery | iterate | unit | +0 | 64/64 | PASS | 2026-06-05 |
| 40 | Set security.yml.template checkout to fetch-depth: 1 (working-tree only) and correct the misleading diff-aware-secret-scans comment; no scanner reads git history. | iterate | — | +0 | — | — | 2026-06-05 |
| 41 | C1/C2 detective-realign doc + ledger closeout | iterate | unit | +0 | 41/41 | PASS | 2026-06-05 |
| 42 | Scope the bloat recorder to the project root so cross-repo edits do not leak into this project marker and block its Stop gate. | iterate | — | +0 | — | — | 2026-06-04 |
| 43 | Fix the adopt security-gate so it resolves SARIF severity at rule level, blocks on any secret, and fails closed — previously a structural false green in every adopted repo. | iterate | — | +0 | — | — | 2026-06-04 |
| 44 | Add producer-owned campaign lifecycle status (draft->active->complete): campaign_init writes status:draft to status.json + campaign.md frontmatter; campaign_progress gains a start subcommand (->active), update-status auto-sets complete when all sub-iterates complete, summary prints the top-level status; the autonomous campaign loop marks the campaign active at run start; missing status = legacy fallback to done<total. | iterate | — | +0 | — | — | 2026-06-03 |
| 45 | Dedup SessionStart Phase-Quality injection to once-per-event via event_once.claim_once (fail-open). | iterate | — | +0 | — | — | 2026-06-02 |
| 46 | Rewrote test_upload_sarif_action_used to assert the real upload-sarif uses: line (anchored regex, version-agnostic) instead of matching a stale comment; corrected the two @v3 permission comments in security.yml to @v4. | iterate | — | +0 | — | — | 2026-06-01 |
| 47 | Pinned third-party GitHub Actions (setup-uv, create-or-update-comment) to commit SHAs; added SHA256 verification for the Gitleaks binary download in ci.yml + security.yml; corrected stale SECURITY.md scope (webui) and Dependabot wording. | iterate | — | +0 | — | — | 2026-06-01 |
| 48 | Detective audit honors event_amended corrections (group_d applies shared apply_amendments SSOT before D1-D5; new shared/scripts/lib/events_amend.py, re-exported by config.py); D4 disabled for the framework monorepo (gating-CI stale-noise); evt-5aca940d corrected to spec_impact=none. | iterate | — | +0 | — | — | 2026-06-01 |
| 49 | Document the gating ruff CI lint step in CLAUDE.md Development section. | iterate | — | +0 | — | — | 2026-06-01 |
| 50 | D5 honors change_type+none_reason exemption; add audit_config.disabled_checks applicability gate; framework repo disables A5.6/B7/D1/G2 | iterate | — | +0 | — | — | 2026-06-01 |
| 51 | plugin-sync Stop-hook triage item written to durable main-repo log (worktree-aware) | iterate | unit | +0 | 48/49 | FAIL | 2026-06-01 |
| 52 | CI gate-coverage guard + workflow hardening (test-dir coverage, loose-gate allowlist, security fail-closed) | iterate | unit | +0 | 2674/2675 | FAIL | 2026-05-31 |
| 53 | Gate CI Python lint on a curated bug-focused ruff ruleset (pyflakes F + high-signal E/W); remove the \|\| true + continue-on-error neutering; provision ruff via pinned uvx; rename job to Python (lint + test). | iterate | — | +0 | — | — | 2026-05-31 |
| 54 | Wire shared/ test suites (shared/tests, shared/scripts/tests, shared/scripts/tools/tests) into ci.yml as blocking per-dir invocations; fix 2 non-hermetic validate_env tests via a dir conftest; make the born-red arch-md sibling skip when gitignored decision-drops are absent. | iterate | — | +0 | — | — | 2026-05-31 |
| 55 | remove vestigial "\|\| true" from CI integration step (gate failures) + add pathlib.Path import to clear 14 F821 in test_events_log.py | iterate | unit | +0 | 2771/2771 | PASS | 2026-05-31 |
| 56 | events=union + churn-merge resolver/integrate_main: auto-reconcile generated artifacts on origin/main merge | iterate | — | +0 | — | — | 2026-06-01 |
| 57 | Collapse the compliance detective-audit mirror into one rolling compliance:backlog action-unit (auto-dismiss + refresh + legacy retirement) | iterate | — | +0 | — | — | 2026-05-31 |
| 58 | Render unengaged phases as SKIP (not FAIL) in the persisted finding JSON so the skill-compliance dashboard agrees with the triage inbox | iterate | — | +0 | — | — | 2026-05-31 |
| 59 | Collapse phase-quality Tier-1 FAIL triage into one rolling phaseQuality:backlog action-unit; add phase-applicability gate and run_id=unknown spec-check guard | iterate | — | +0 | — | — | 2026-05-31 |
| 60 | iterate completion: test-completeness-gate | iterate | — | +0 | — | — | 2026-05-30 |
| 61 | iterate complete: P3.1 reviewer stack (spec-reviewer + doubt-reviewer cascade) | iterate | — | +0 | — | — | 2026-05-30 |
| 62 | Propagate canonical .shipwright artifact-ignore block to consuming projects via SSoT template + idempotent merge in adopt/project + drift test | iterate | — | +0 | — | — | 2026-05-30 |
| 63 | Add audit_compliance_on_stop.py: auto-emit/auto-dismiss source=compliance triage items on every iterate/changelog Stop, gated on full A-G audit coverage. | iterate | — | +0 | — | — | 2026-05-30 |
| 64 | Align 7 stale record_event tests to the C.1 FR-gate (gates all iterates incl. bug/intentless); surface CI shared-test gap (trg-f363b1ab) | iterate | — | +0 | — | — | 2026-05-30 |
| 65 | RTM: untested (0/0) events neutral; status from latest tested event (fixes 7 false FAILs); neutralize leaked verification event via event_amended | iterate | — | +0 | — | — | 2026-05-30 |
| 66 | SP3+OS2 post-Campaign-B reintegration — F-debug.md systematic-debugging sub-skill + assumptions-first interview pre-phase | iterate | unit | +0 | 317/317 | PASS | 2026-05-29 |
| 67 | suggest_iterate UserPromptSubmit hook: emit hookEventName on hookSpecificOutput (+ AST meta-test) | iterate | unit | +0 | 2558/2558 | PASS | 2026-05-29 |
| 68 | Bloat marker keyed off stdin-payload session_id (not env) in check_file_size.py + bloat_gate_on_stop.py | iterate | unit | +0 | 2549/2550 | FAIL | 2026-05-29 |
| 69 | P4.1 Skill Bootstrap Pack: using-shipwright SessionStart bootstrap + writing-plugin/plugin-cache Stop wave (SP2+SP4) | iterate | unit | +0 | 2545/2545 | PASS | 2026-05-29 |
| 70 | events.jsonl per-tree, PR-committed artifact (worktree iterate audit-log fix) | iterate | unit | +0 | 2449/2450 | FAIL | 2026-05-29 |
| 71 | Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings) | iterate | unit | +0 | 2449/2449 | PASS | 2026-05-28 |
| 72 | Correction event: spec_impact=none with proper justification field for the verifier (supersedes evt-13153a5c). | iterate | — | +0 | — | — | 2026-05-27 |
| 73 | Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check | iterate | — | +0 | — | — | 2026-05-27 |
| 74 | Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT) | iterate | — | +0 | — | — | 2026-05-27 |
| 75 | Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d). | iterate | — | +0 | — | — | 2026-05-27 |
| 76 | Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass + audit_staleness coverage extension + merge-not-rebase doc convention. | iterate | — | +0 | — | — | 2026-05-27 |
| 77 | B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | iterate | unit | +26 | 1104/1104 | PASS | 2026-05-26 |
| 78 | Pre-commit anti-ratchet hook + bloat-check CI workflow + bloat-exception ADR template + shared glossary (Campaign A.defense, closes Campaign A defense-in-depth layer) | iterate | mixed | +0 | 41/41 | PASS | 2026-05-25 |
| 79 | fix bloat_gate_on_stop.py Stop-hook schema violation | iterate | unit | +0 | 131/131 | PASS | 2026-05-25 |
| 80 | Campaign A.review: bloat reviewer prompts (Karpathy+Osmani+Shipwright) + Group H detective audit (H0-H6) | iterate | mixed | +0 | 14/14 | PASS | 2026-05-25 |
| 81 | Phase 0 bloat baseline inventory — activates A.foundation Stop-Gate | iterate | — | +0 | — | — | 2026-05-25 |
| 82 | Bloat Loop-Gate (Campaign A.foundation = A1+A2+A3): runtime-prompt classification, per-session marker writer, blocking Stop-Gate, registered in every plugin | iterate | unit | +0 | 2678/2678 | PASS | 2026-05-25 |
| 83 | SBOM triage producer cluster-collapse | iterate | mixed | +0 | 514/514 | PASS | 2026-05-23 |
| 84 | SBOM resolver pin to per-manifest .venv METADATA | iterate | mixed | +0 | 497/497 | PASS | 2026-05-23 |
| 85 | Resolve architecture.md merge-conflict markers (lines 90-94) + extend ALLOWLIST[compliance] to include finalize_security_compliance.py whose cross-plugin path comment trips the hyphen-segment regex blind spot | iterate | unit | +0 | 2/3 | FAIL | 2026-05-23 |
| 86 | C1 design verifier (and sister manifest-exists check) skip on scope=library projects via _is_no_ui_scope helper; audit translates ok=None to status=skip via existing check_result_to_finding | iterate | unit | +0 | 19/19 | PASS | 2026-05-23 |
| 87 | iterate finalization | iterate | — | +0 | — | — | 2026-05-23 |
| 88 | Architecture-md drift protection test + 11 historical drift entries backfilled + 3 discipline learnings in conventions.md (TDD RED-first, F0/F11 leak-guard symmetry, F2 flag-md coupling) | iterate | unit | +0 | 2/2 | PASS | 2026-05-23 |
| 89 | F11 verifier multi-commit-aware via run_id lookup (fixes false positives on iterate-f7-tracked-event-log-commit) | iterate | unit | +0 | 70/70 | PASS | 2026-05-23 |
| 90 | iterate skill F7b: seals tracked event-log appends to prevent silent reset wipe (commit_event_followup.py + SKILL.md + 6 tests) | iterate | unit | +0 | 6/6 | PASS | 2026-05-22 |
| 91 | compliance reconciliation: D1 spec-FR coverage — multi-FR event covering FR-01.03/04/05/06/07/08/09/12 (post-2026-05-04 watermark gap; no source/test/spec changes) | iterate | — | +0 | — | — | 2026-05-22 |
| 92 | mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | iterate | — | +0 | — | — | 2026-05-22 |
| 93 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 94 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 95 | Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | iterate | — | +0 | — | — | 2026-05-22 |
| 96 | deterministic render timestamps from max(event.ts) | iterate | unit | +34 | 34/34 | PASS | 2026-05-21 |
| 97 | empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | iterate | unit | +0 | 2621/2621 | PASS | 2026-05-21 |
| 98 | VERIFICATION: bug+change-type — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 99 | VERIFICATION artifact (amended: leaked from 2026-05-21 empirical-verification campaign; no real FR work) — neutralized by iterate-2026-05-30-rtm-covered-ignore-untested-events | iterate | — | +0 | — | — | 2026-05-21 |
| 100 | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 101 | Artifact-based GitHub security producer for Triage Inbox | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 102 | escape pipe and newline in markdown table cells | iterate | unit | +23 | 23/23 | PASS | 2026-05-20 |
| 103 | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | mixed | +0 | 3507/3507 | PASS | 2026-05-18 |
| 104 | triage detector dedup + auto-resolve (rebased onto #31) | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 105 | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | unit | +0 | 140/140 | PASS | 2026-05-16 |
| 106 | triage detector dedup + auto-resolve | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 107 | fix adopt external-review config defaults | iterate | mixed | +0 | 304/304 | PASS | 2026-05-16 |
| 108 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | mixed | +0 | 2519/2526 | FAIL | 2026-05-16 |
| 109 | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | mixed | +0 | 312/312 | PASS | 2026-05-15 |
| 110 | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | mixed | +0 | 40/40 | PASS | 2026-05-14 |
| 111 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 112 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 113 | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | unit | +0 | 16/16 | PASS | 2026-05-09 |
| 114 | evt-f66286bf | iterate | — | +0 | — | — | 2026-05-07 |
| 115 | evt-623a29ad | iterate | — | +0 | — | — | 2026-05-07 |
| 116 | F0.5 empirical-test backfill | iterate | unit | +0 | 1575/1575 | PASS | 2026-05-06 |
| 117 | F0.5 End-to-End Verification Gate | iterate | unit | +0 | 1548/1548 | PASS | 2026-05-06 |
| 118 | hooks-consistency parser handles quoted commands — 27/27 green | iterate | unit | +0 | 1297/1297 | PASS | 2026-05-06 |
| 119 | post-migration canon cleanup — 9 tests green | iterate | unit | +0 | 1270/1270 | PASS | 2026-05-06 |
| 120 | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | unit | +0 | 34/34 | PASS | 2026-05-05 |
| 121 | verifier accepts drop-dir entries + dashboard short-SHAs | iterate | unit | +0 | 32/32 | PASS | 2026-05-05 |
| 122 | adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | unit | +0 | 241/241 | PASS | 2026-05-05 |
| 123 | FR-table parser accepts 5-col adopt format + drift protection | iterate | unit | +0 | 1594/1628 | FAIL | 2026-05-05 |
| 124 | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | unit | +0 | 12/12 | PASS | 2026-05-05 |
| 125 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | unit | +0 | 1691/1716 | FAIL | 2026-05-05 |
| 126 | F runner contract mandates reviews (ADR-029) | iterate | unit | +0 | 188/188 | PASS | 2026-05-04 |
| 127 | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | unit | +0 | 1539/1539 | PASS | 2026-05-04 |
| 128 | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | unit | +19 | 19/19 | PASS | 2026-05-03 |
| 129 | changelog MSYS path-mangling linter | iterate | unit | +0 | 19/19 | PASS | 2026-05-03 |
| 130 | hooks.json quoting (deferred from ADR-020) | iterate | unit | +0 | 13/13 | PASS | 2026-05-03 |
| 131 | iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | unit | +0 | 53/53 | PASS | 2026-05-03 |
| 132 | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | unit | +0 | 47/47 | PASS | 2026-05-03 |
| 133 | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | unit | +0 | 249/249 | PASS | 2026-05-03 |
| 134 | fix hook_installer Shape A -> B | iterate | unit | +0 | 5/5 | PASS | 2026-05-03 |
| 135 | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | unit | +0 | 233/233 | PASS | 2026-05-02 |
| 136 | post-adoption framework cleanup (Sub-1A through 1D) | iterate | unit | +0 | 225/225 | PASS | 2026-05-02 |

## Full Suite Runs

| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |
|-----|---------|------|-------------|-------|-----|-------|------|
| 1 | iterate | 2545/2545 | — | — | — | — | 2026-05-29 |
| 2 | iterate | 2549/2550 | — | — | — | — | 2026-05-29 |
| 3 | iterate | 2558/2558 | — | — | — | — | 2026-05-29 |
| 4 | iterate | 317/317 | — | — | — | — | 2026-05-29 |
| 5 | iterate | 2771/2771 | — | — | — | — | 2026-05-31 |
| 6 | iterate | 2674/2675 | — | — | — | — | 2026-05-31 |
| 7 | iterate | 48/49 | — | — | — | — | 2026-06-01 |
| 8 | iterate | 41/41 | — | — | — | — | 2026-06-05 |
| 9 | iterate | 64/64 | — | — | — | — | 2026-06-05 |
| 10 | iterate | 320/320 | — | — | — | — | 2026-06-05 |
| 11 | iterate | 9/9 | — | — | — | — | 2026-06-05 |
| 12 | iterate | 44/44 | — | — | — | — | 2026-06-05 |
| 13 | iterate | 49/49 | — | — | — | — | 2026-06-05 |
| 14 | iterate | 19/19 | — | — | — | — | 2026-06-05 |
| 15 | iterate | 387/387 | — | — | — | — | 2026-06-05 |
| 16 | iterate | 617/617 | — | — | — | — | 2026-06-05 |
| 17 | iterate | 24/24 | — | — | — | — | 2026-06-05 |
| 18 | iterate | 2839/2839 | — | — | — | — | 2026-06-07 |
| 19 | iterate | 24/24 | — | — | — | — | 2026-06-07 |
| 20 | iterate | 312/312 | — | — | — | — | 2026-06-07 |
| 21 | iterate | 56/56 | — | — | — | — | 2026-06-07 |
| 22 | iterate | 2861/2861 | — | — | — | — | 2026-06-07 |
| 23 | iterate | 2884/2884 | — | — | — | — | 2026-06-07 |
| 24 | iterate | 2913/2913 | — | — | — | — | 2026-06-08 |
| 25 | iterate | 2954/2954 | — | — | — | — | 2026-06-08 |
| 26 | iterate | 6/6 | — | — | — | — | 2026-06-08 |
| 27 | iterate | 3457/3458 | — | — | — | — | 2026-06-10 |
| 28 | iterate | 3426/3445 | — | — | — | — | 2026-06-10 |
| 29 | iterate | 3442/3462 | — | — | — | — | 2026-06-10 |
| 30 | iterate | 3451/3471 | — | — | — | — | 2026-06-10 |

## Code Review Evidence

| Event | Review Type | Findings | Fixed | Status |
|-------|------------|----------|-------|--------|
| B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | external-iterate-review | 12 | 12 | PASS |
| Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | external-plan+external-code | 18 | 18 | PASS |
| evt-b9b5ddf2 | external-plan+code | 16 | 4 | OPEN |
| Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | plan+code | 20 | 8 | OPEN |

