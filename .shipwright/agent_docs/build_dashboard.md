# Project Activity Dashboard
> Updated: 2026-06-10 20:21 UTC | Session: 88b11785-06c5-4d46-b7a2-7fd1b6b60402 | Run: iterate-2026-06-10-status-projection

## Recent Changes (134 iterations)

| Type | Description | Tests | Commit | FRs | Date |
|------|-------------|-------|--------|-----|------|
| feature | Campaign status projection: pure regenerate_campaign_status producer + campaign_progress regenerate CLI project per-sub-iterate status.json from the campaign.md skeleton and self-identifying work_completed events, with a never-downgrade guard (campaign 2026-06-07-tracked-campaign-status S2). | 3426/3445 |  | tooling | 2026-06-10 |
| change | Exempt session_handoff.md + build_dashboard.md (with triage_inbox.md) from artifact-path-canon in all migrations; drift test; dismiss trg-6ed063ae. | 0/0 |  | infra | 2026-06-10 |
| bug | triage_cli list pins stdout to UTF-8: fixes UnicodeEncodeError on Windows consoles for non-cp1252 item titles (found by the webui pending-delivery-badge boundary probe). | 0/0 |  | tooling | 2026-06-10 |
| change | History-calibrated complexity prior + cross-domain scope vocabulary for the iterate Stage-1 classifier | 0/0 |  | infra | 2026-06-10 |
| change | Gate D2V evidence markdown write behind SHIPWRIGHT_D2V_WRITE_EVIDENCE; default runs assert without writing the tracked artifact. | 0/0 |  | infra | 2026-06-10 |
| feature | Add triage_cli.py list --json (unioned open items + pendingDelivery) as a WebUI contract. | 0/0 |  | infra | 2026-06-10 |
| feature | Campaign sub-iterates self-identify: runner Step 4 + manual --campaign/--sub-iterate-id stamp campaign/sub_iterate_id into the work_completed event via F5b --event-extras-json | 3457/3458 |  | tooling | 2026-06-10 |
| change | Triage dedup collapses same-id appends keep-last (reader parity); unblocks outbox sweep on producer update re-append. | 0/0 |  | infra | 2026-06-09 |
| change | Iterate-scoped external-review markers gitignored (not blanket); 6 tracked copies untracked. | 0/0 |  | infra | 2026-06-09 |
| change | Relocate detective-audit JSON from repo root to .shipwright/compliance/audit-report.json; canon re-excludes audit-report.{md,json} (propagates to adopted repos); drop obsolete framework root ignore. | 0/0 |  | infra | 2026-06-09 |
| change | Relocate phase-quality skill-compliance roll-ups under the gitignored FINDING_DIR; resolve main_repo_root (not cwd) in the bloat marker writer+reader via a shared fail-soft resolver; defensive nested-locks gitignore canon. | 0/0 |  | infra | 2026-06-08 |
| change | — | 0/0 | 77cc652 | tooling | 2026-06-08 |
| D2V empirical verification gate — prove the D2 outbox sweep/GC loses no triage line (HARD insurance before D3) | Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | +6 new, 6/6 | 7a31e33 | tooling | 2026-06-08 |
| Sweep triage outbox into PR branch + abandoned-branch-safe GC; drop integrate_main reconcile | — | +36 new, 2954/2954 | 005f643 | tooling | 2026-06-08 |
| Gitignored per-tree triage outbox + reroute background producers + union reader | Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | +22 new, 2913/2913 | 2293a76 | tooling | 2026-06-08 |
| change | scaffold the append-log merge=union .gitattributes driver into managed repos (adopt E.13c + iterate self-heal) | 2884/2884 |  | infra | 2026-06-07 |
| change | triage main-tree drift reconcile-and-commit at integrate/sync | 2861/2861 |  | tooling | 2026-06-07 |
| change | Track campaign status.json for compliance-detective-realign + track-triage-jsonl (durable per-sub board on fresh clone / deployed WebUI; stopgap for trg-fda5f7a3). | 0/0 |  | compliance | 2026-06-07 |
| change | allowlist cafebabe:deadbeef in oss_backend generated gitleaks config (GAP-3) | 56/56 |  | tooling | 2026-06-07 |
| change | Harden iterate finalization tooling: F11 verifier accepts none_reason as a spec_impact=none justification; F0.5 surface_verification rejects compound runners fast with a clear error; arch-drift sanity test no longer false-FAILs on a post-release tree. | 0/0 |  | tooling | 2026-06-07 |
| change | SBOM distinguishes not-installed from no-declared-license; not-installed is silent (no triage, dash in sbom.md), only resolved-but-no-license is surfaced. | 0/0 |  | tooling | 2026-06-07 |
| feature | Add campaign_init --expands-triage / --from-triage so a triage item can be promoted to a campaign anchor; writes expands_triage into both status.json and the campaign.md frontmatter so the Command Center shows 'Start Campaign' on that triage card. | 0/0 |  | tooling | 2026-06-07 |
| change | adopt scaffolds .gitleaks.toml + hardens security.yml.template | 312/312 |  | tooling | 2026-06-07 |
| change | GC machine-churn complianceRefreshed compliance-backlog dismissals (add token to triage_gc.MACHINE_REASONS) | 24/24 |  | tooling | 2026-06-07 |
| change | triage docs + monorepo migration (campaign 2026-06-05-track-triage-jsonl, sub-iterate E) | 2839/2839 |  | docs | 2026-06-07 |
| change | F5 architecture-drift detector switched from a git-history oracle (dead on gitignored drops) to content reconciliation (incl. convention); new canon/blocking F11 gate check_architecture_documented sharing one oracle (shared/scripts/lib/architecture_doc.py); dead check_architecture_reviewed + run_cross_artifact_checks removed; 5 orphan architecture.md entries back-filled. | 0/0 |  | compliance | 2026-06-06 |
| change | adopt skill docs: triage.jsonl is tracked, not gitignored (D) | 24/24 |  | docs | 2026-06-05 |
| change | SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift) | 617/617 |  | compliance | 2026-06-05 |
| feature | triage_gc tool: machine-churn-only dismissed-pile compaction | 387/387 |  | tooling | 2026-06-05 |
| change | git-track triage.jsonl: gitignore negation + scaffolder self-heal (C1) | 19/19 |  | infra | 2026-06-05 |
| change | triage.jsonl merge-safety + leak-guard exemption (like events) — C2 | 49/49 |  | infra | 2026-06-05 |
| change | Propagate degraded scanner legs (fatal/empty/truncated) via a scan_errors side-channel so the threshold/report/CI-gate layers fail closed instead of treating a dead leg as a clean 0-findings scan. | 0/0 |  | tooling | 2026-06-05 |
| change | B7 Rule E: exclude non-functional Conventional-Commit types (build/chore/ci/docs/style/test) from B7 by default (configurable); functional types still flagged. Supersedes the narrow Rule D + kills the ci/docs/chore backfill treadmill. | 44/44 |  | compliance | 2026-06-05 |
| change | Make the bloat marker recorder + Stop gate worktree-aware: strip the .worktrees/<slug>/ prefix for the baseline lookup so a worktree iterate growing an already-baselined file (ADR+bump) is not mis-classified crossing and does not false-block Stop (trg-305e2aab) | 9/9 |  | tooling | 2026-06-05 |
| bug | gitleaks --report-path - wrote a stray file named - instead of stdout, so the secrets leg silently returned 0 findings everywhere; report now written to a temp file and read back; smoke positive-control converted to ADR-044 CI-gated fail | 320/320 |  | tooling | 2026-06-05 |
| change | Add A5.8: execute the deployed critical-gate shell against dual-artifact fixtures (flavor-agnostic across SARIF/findings.json; skip-safe; env kill-switch). | 0/0 |  | tooling | 2026-06-05 |
| change | Enforce the FR-gate on the finalize write-path + accept same-event D3 delivery | 64/64 |  | tooling | 2026-06-05 |
| change | Set security.yml.template checkout to fetch-depth: 1 (working-tree only) and correct the misleading diff-aware-secret-scans comment; no scanner reads git history. | 0/0 |  | infra | 2026-06-05 |
| change | C1/C2 detective-realign doc + ledger closeout | 41/41 |  | docs | 2026-06-05 |
| bug | Scope the bloat recorder to the project root so cross-repo edits do not leak into this project marker and block its Stop gate. | 0/0 |  | fix | 2026-06-04 |
| bug | Fix the adopt security-gate so it resolves SARIF severity at rule level, blocks on any secret, and fails closed — previously a structural false green in every adopted repo. | 0/0 |  | fix | 2026-06-04 |
| feature | Add producer-owned campaign lifecycle status (draft->active->complete): campaign_init writes status:draft to status.json + campaign.md frontmatter; campaign_progress gains a start subcommand (->active), update-status auto-sets complete when all sub-iterates complete, summary prints the top-level status; the autonomous campaign loop marks the campaign active at run start; missing status = legacy fallback to done<total. | 0/0 |  | tooling | 2026-06-03 |
| change | Dedup SessionStart Phase-Quality injection to once-per-event via event_once.claim_once (fail-open). | 0/0 |  | tooling | 2026-06-02 |
| change | Rewrote test_upload_sarif_action_used to assert the real upload-sarif uses: line (anchored regex, version-agnostic) instead of matching a stale comment; corrected the two @v3 permission comments in security.yml to @v4. | 0/0 |  | tooling | 2026-06-01 |
| change | Pinned third-party GitHub Actions (setup-uv, create-or-update-comment) to commit SHAs; added SHA256 verification for the Gitleaks binary download in ci.yml + security.yml; corrected stale SECURITY.md scope (webui) and Dependabot wording. | 0/0 |  | infra | 2026-06-01 |
| change | Detective audit honors event_amended corrections (group_d applies shared apply_amendments SSOT before D1-D5; new shared/scripts/lib/events_amend.py, re-exported by config.py); D4 disabled for the framework monorepo (gating-CI stale-noise); evt-5aca940d corrected to spec_impact=none. | 0/0 |  | compliance | 2026-06-01 |
| change | Document the gating ruff CI lint step in CLAUDE.md Development section. | 0/0 |  | docs | 2026-06-01 |
| change | D5 honors change_type+none_reason exemption; add audit_config.disabled_checks applicability gate; framework repo disables A5.6/B7/D1/G2 | 0/0 |  | compliance | 2026-06-01 |
| bug | plugin-sync Stop-hook triage item written to durable main-repo log (worktree-aware) | 48/49 |  | tooling | 2026-06-01 |
| feature | CI gate-coverage guard + workflow hardening (test-dir coverage, loose-gate allowlist, security fail-closed) | 2674/2675 |  | infra | 2026-05-31 |
| change | Gate CI Python lint on a curated bug-focused ruff ruleset (pyflakes F + high-signal E/W); remove the \|\| true + continue-on-error neutering; provision ruff via pinned uvx; rename job to Python (lint + test). | 0/0 |  | chore | 2026-05-31 |
| change | Wire shared/ test suites (shared/tests, shared/scripts/tests, shared/scripts/tools/tests) into ci.yml as blocking per-dir invocations; fix 2 non-hermetic validate_env tests via a dir conftest; make the born-red arch-md sibling skip when gitignored decision-drops are absent. | 0/0 |  |  | 2026-05-31 |
| change | remove vestigial "\|\| true" from CI integration step (gate failures) + add pathlib.Path import to clear 14 F821 in test_events_log.py | 2771/2771 |  | infra | 2026-05-31 |
| change | events=union + churn-merge resolver/integrate_main: auto-reconcile generated artifacts on origin/main merge | 0/0 |  |  | 2026-06-01 |
| change | Collapse the compliance detective-audit mirror into one rolling compliance:backlog action-unit (auto-dismiss + refresh + legacy retirement) | 0/0 |  | compliance | 2026-05-31 |
| change | Render unengaged phases as SKIP (not FAIL) in the persisted finding JSON so the skill-compliance dashboard agrees with the triage inbox | 0/0 |  | compliance | 2026-05-31 |
| change | Collapse phase-quality Tier-1 FAIL triage into one rolling phaseQuality:backlog action-unit; add phase-applicability gate and run_id=unknown spec-check guard | 0/0 |  | compliance | 2026-05-31 |
| change | iterate completion: test-completeness-gate | 0/0 |  |  | 2026-05-30 |
| change | iterate complete: P3.1 reviewer stack (spec-reviewer + doubt-reviewer cascade) | 0/0 |  |  | 2026-05-30 |
| change | Propagate canonical .shipwright artifact-ignore block to consuming projects via SSoT template + idempotent merge in adopt/project + drift test | 0/0 |  | tooling | 2026-05-30 |
| feature | Add audit_compliance_on_stop.py: auto-emit/auto-dismiss source=compliance triage items on every iterate/changelog Stop, gated on full A-G audit coverage. | 0/0 |  | compliance | 2026-05-30 |
| bug | Align 7 stale record_event tests to the C.1 FR-gate (gates all iterates incl. bug/intentless); surface CI shared-test gap (trg-f363b1ab) | 0/0 |  | tooling | 2026-05-30 |
| bug | RTM: untested (0/0) events neutral; status from latest tested event (fixes 7 false FAILs); neutralize leaked verification event via event_amended | 0/0 |  | tooling | 2026-05-30 |
| feature | SP3+OS2 post-Campaign-B reintegration — F-debug.md systematic-debugging sub-skill + assumptions-first interview pre-phase | 317/317 |  | docs | 2026-05-29 |
| bug | suggest_iterate UserPromptSubmit hook: emit hookEventName on hookSpecificOutput (+ AST meta-test) | 2558/2558 |  | tooling | 2026-05-29 |
| bug | Bloat marker keyed off stdin-payload session_id (not env) in check_file_size.py + bloat_gate_on_stop.py | 2549/2550 | 4adfd44 | tooling | 2026-05-29 |
| feature | P4.1 Skill Bootstrap Pack: using-shipwright SessionStart bootstrap + writing-plugin/plugin-cache Stop wave (SP2+SP4) | 2545/2545 | e788870 | tooling | 2026-05-29 |
| bug | events.jsonl per-tree, PR-committed artifact (worktree iterate audit-log fix) | 2449/2450 |  | tooling | 2026-05-29 |
| bug | Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings) | 2449/2449 | 9d9b1e5 | tooling | 2026-05-28 |
| change | Correction event: spec_impact=none with proper justification field for the verifier (supersedes evt-13153a5c). | 0/0 | 25fd988 | docs | 2026-05-27 |
| change | Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check | 0/0 | 25fd988 | docs | 2026-05-27 |
| change | Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT) | 0/0 | b3ff2eb | compliance | 2026-05-27 |
| change | Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d). | 0/0 | 54ecb17 | fix | 2026-05-27 |
| change | Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass + audit_staleness coverage extension + merge-not-rebase doc convention. | 0/0 | 54ecb17 | fix | 2026-05-27 |
| change | B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | +26 new, 1104/1104 | fbde435 | tooling | 2026-05-26 |
| feature | Pre-commit anti-ratchet hook + bloat-check CI workflow + bloat-exception ADR template + shared glossary (Campaign A.defense, closes Campaign A defense-in-depth layer) | 41/41 | 55be715 | tooling | 2026-05-25 |
| bug | fix bloat_gate_on_stop.py Stop-hook schema violation | 131/131 | 193b7f5 | tooling | 2026-05-25 |
| feature | Campaign A.review: bloat reviewer prompts (Karpathy+Osmani+Shipwright) + Group H detective audit (H0-H6) | 14/14 | babf9fc | infra | 2026-05-25 |
| change | Phase 0 bloat baseline inventory — activates A.foundation Stop-Gate | 0/0 | 66ec453 | infra | 2026-05-25 |
| feature | Bloat Loop-Gate (Campaign A.foundation = A1+A2+A3): runtime-prompt classification, per-session marker writer, blocking Stop-Gate, registered in every plugin | 2678/2678 | bfd4e63 | infra | 2026-05-25 |
| change | SBOM triage producer cluster-collapse | 514/514 | 6be7aae | compliance | 2026-05-23 |
| bug | SBOM resolver pin to per-manifest .venv METADATA | 497/497 | fc1a7a8 | compliance | 2026-05-23 |
| bug | Resolve architecture.md merge-conflict markers (lines 90-94) + extend ALLOWLIST[compliance] to include finalize_security_compliance.py whose cross-plugin path comment trips the hyphen-segment regex blind spot | 2/3 | 9e26a9c | tooling | 2026-05-23 |
| change | C1 design verifier (and sister manifest-exists check) skip on scope=library projects via _is_no_ui_scope helper; audit translates ok=None to status=skip via existing check_result_to_finding | 19/19 | c7b1b29 | tooling | 2026-05-23 |
| change | iterate finalization | 0/0 |  |  | 2026-05-23 |
| change | Architecture-md drift protection test + 11 historical drift entries backfilled + 3 discipline learnings in conventions.md (TDD RED-first, F0/F11 leak-guard symmetry, F2 flag-md coupling) | 2/2 | 1429aee | FR-01.11 | 2026-05-23 |
| change | F11 verifier multi-commit-aware via run_id lookup (fixes false positives on iterate-f7-tracked-event-log-commit) | 70/70 | c1c8820 | FR-01.11 | 2026-05-23 |
| change | iterate skill F7b: seals tracked event-log appends to prevent silent reset wipe (commit_event_followup.py + SKILL.md + 6 tests) | 6/6 | 24d77be | FR-01.11 | 2026-05-22 |
| change | compliance reconciliation: D1 spec-FR coverage — multi-FR event covering FR-01.03/04/05/06/07/08/09/12 (post-2026-05-04 watermark gap; no source/test/spec changes) | 0/0 | 1ca566a | FR-01.03, FR-01.04, FR-01.05 | 2026-05-22 |
| Fix partial-run audit incorrectly dismissing out-of-scope compliance triage items | mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | 0/0 | 09fedde | tooling | 2026-05-22 |
| Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | 0/0 | 69f1498 | compliance | 2026-05-22 |
| Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | 0/0 | 69f1498 | compliance | 2026-05-22 |
| Clear 5 compliance triage bloat items (G2 stoplist + G3 ADR stubs + 3x artifact-stale) from artifact-polish/empirical-verification campaigns | Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | 0/0 | c3057ff | compliance | 2026-05-22 |
| bug | deterministic render timestamps from max(event.ts) | +34 new, 34/34 | d325fd6 | tooling | 2026-05-21 |
| change | empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | 2621/2621 | d8f3c05 | tooling | 2026-05-21 |
| bug | VERIFICATION: bug+change-type — should pass | 0/0 | 376c870 | tooling | 2026-05-21 |
| feature | VERIFICATION: with affected-frs — should pass | 0/0 | 376c870 | FR-01.01 | 2026-05-21 |
| feature | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | 122/122 | 861c0fd | FR-01.14 | 2026-05-20 |
| feature | Artifact-based GitHub security producer for Triage Inbox | 122/122 | 6f5dd5f | FR-01.14 | 2026-05-20 |
| bug | escape pipe and newline in markdown table cells | +23 new, 23/23 | 9dd6c8b |  | 2026-05-20 |
| bug | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | 3507/3507 | 21cef22 | tooling | 2026-05-18 |
| bug | triage detector dedup + auto-resolve (rebased onto #31) | 1776/1783 | cd957a0 | FR-01.14 | 2026-05-16 |
| feature | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | 140/140 | c16d711 | FR-01.11, FR-01.10, FR-01.02 | 2026-05-16 |
| bug | triage detector dedup + auto-resolve | 1776/1783 | 931e6b5 | FR-01.14 | 2026-05-16 |
| bug | fix adopt external-review config defaults | 304/304 | 3f5777d | FR-01.13 | 2026-05-16 |
| bug | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | 2519/2526 | 34a7987 | FR-01.11 | 2026-05-16 |
| bug | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | 312/312 | ea24bf4 | FR-01.10 | 2026-05-15 |
| feature | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | 40/40 | aab9bd7 | FR-01.14 | 2026-05-14 |
| feature | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | 1642/1649 | f638908 | FR-01.14 | 2026-05-11 |
| feature | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | 1642/1649 | 6ba7df1 | FR-01.14 | 2026-05-11 |
| bug | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | 16/16 | f8d44da | compliance | 2026-05-09 |
| change | — | 0/0 | 99fc87b | tooling | 2026-05-07 |
| change | — | 0/0 | 686e7cc | tooling | 2026-05-07 |
| change | F0.5 empirical-test backfill | 1575/1575 | 0df63f2 | FR-01.11 | 2026-05-06 |
| feature | F0.5 End-to-End Verification Gate | 1548/1548 | 88f3398 | FR-01.11 | 2026-05-06 |
| bug | hooks-consistency parser handles quoted commands — 27/27 green | 1297/1297 | c5e6cb3 | FR-01.11 | 2026-05-06 |
| bug | post-migration canon cleanup — 9 tests green | 1270/1270 | 7383c18 | tooling | 2026-05-06 |
| bug | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | 34/34 | 49eca25 | FR-01.11 | 2026-05-05 |
| bug | verifier accepts drop-dir entries + dashboard short-SHAs | 32/32 | f1f0447 | FR-01.11 | 2026-05-05 |
| bug | adopt writes shipwright_iterate_config.json with documented opt-out schema | 241/241 | f4f7229 | FR-01.13, FR-01.11 | 2026-05-05 |
| bug | FR-table parser accepts 5-col adopt format + drift protection | 1594/1628 | 656f96f | FR-01.10, FR-01.13 | 2026-05-05 |
| bug | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | 12/12 | afb3b63 | FR-01.11 | 2026-05-05 |
| bug | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | 1691/1716 | a05ff22 | FR-01.11, FR-01.13, FR-01.02 | 2026-05-05 |
| feature | F runner contract mandates reviews (ADR-029) | 188/188 | f6a14fc | FR-01.11 | 2026-05-04 |
| bug | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | 1539/1539 | 5415ed6 | FR-01.11 | 2026-05-04 |
| feature | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | +19 new, 19/19 | 216f8b3 | FR-01.06 | 2026-05-03 |
| bug | changelog MSYS path-mangling linter | 19/19 | a13fd64 | FR-01.09 | 2026-05-03 |
| bug | hooks.json quoting (deferred from ADR-020) | 13/13 | 6ca369d | FR-01.01, FR-01.02, FR-01.03 | 2026-05-03 |
| fix | iterate fix: parse_env_file inline-comment stripping + lib copy sync | 53/53 | 1a9c7f4 | FR-01.11 | 2026-05-03 |
| feature | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | 47/47 | 9953008 | FR-01.13 | 2026-05-03 |
| bug | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | 249/249 | b24f804 | FR-01.13, FR-01.02, FR-01.01 | 2026-05-03 |
| bug | fix hook_installer Shape A -> B | 5/5 | 1ddf9ae | FR-01.11 | 2026-05-03 |
| change | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | 233/233 | cffe191 | FR-01.13 | 2026-05-02 |
| change | post-adoption framework cleanup (Sub-1A through 1D) | 225/225 | 3db485b | FR-01.01, FR-01.02, FR-01.03 | 2026-05-02 |

## Test Status
Last run: 2026-06-10 | Unit: 3426/3445 | Smoke: not_run | (iterate)

## Pipeline

| Phase | Status | Completed |
|-------|--------|-----------|
| project | — | — |
| design | — | — |
| plan | — | — |
| build | — | — |
| test | — | — |
| changelog | complete | 2026-05-03 |
| compliance | — | — |
| deploy | — | — |
