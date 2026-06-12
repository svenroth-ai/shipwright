# Test Evidence Report

Generated: 2026-06-12T21:06:53.297329+00:00

## Summary

| Metric | Value |
|--------|-------|
| Total test checkpoints | 164 |
| Total unit tests (latest) | 0/0 |
| New tests from iterations | +166 |

## Test Progression

| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |
|---|-------|--------|-------|-----------|-------------|--------|------|
| 1 | Intelligent bloat gate: LOC-as-router -> falsifiable reducibility reviewer (closed catalog D/A/X/C/S/M/P/T + guardrails G1-G6); shared SSoT catalog + per-language idiom-map + reviewer dimensions across 3 surfaces + drift-protection test. | iterate | — | +0 | — | — | 2026-06-12 |
| 2 | W2 phase-quality check SKIPs on an unresolvable run_id (mirror S2/S3); fixes the audit-context false-FAIL/false-PASS when no iterate run resolves; also fixes a latent empty-run_id crash | iterate | unit | +0 | 3289/3289 | PASS | 2026-06-12 |
| 3 | Clear bloat Group H1/H2: tighten 51 stale baseline entries to actual LOC + grandfather 8 oversize files (reducibility-catalog dogfood); follow-ups trg-af476d87 + trg-b9acb195. | iterate | — | +0 | — | — | 2026-06-12 |
| 4 | Windows: test-run the python3 probe so the Microsoft Store stub does not abort the marketplace cache sync | iterate | mixed | +0 | 3284/3284 | PASS | 2026-06-12 |
| 5 | End-to-end parallel-merge cascade integration test (3 concurrent iterates + a 3-sub campaign): proves curated-union + churn-regenerate + JSONL-union resolve together with no cascade. | iterate | — | +0 | — | — | 2026-06-12 |
| 6 | Delivery-Watch: F11 confirms the PR actually merges green before done (no shoot-and-forget); watch_pr_delivery.py + F2 budget-lint-before-push rule. | iterate | — | +0 | — | — | 2026-06-12 |
| 7 | merge=union for curated agent-docs (architecture.md + conventions.md) via a distinct CURATED_DOC_UNION_PATHS category; closes the parallel-iterate bullet-prepend cascade server-side (follow-up to automerge-serial-integrate). | iterate | — | +0 | — | — | 2026-06-12 |
| 8 | Serial integrate_main merge for campaign/parallel iterates: ensure_current.py refresh-if-behind guard at F11 + SHIPWRIGHT_ITERATE_AUTOMERGE defer with serial drain (auto-merge churn fix, Option A). | iterate | — | +0 | — | — | 2026-06-12 |
| 9 | Consolidate the project-detection predicate across all hooks onto one canonical lib.project_root.is_shipwright_project | iterate | unit | +0 | 3203/3203 | PASS | 2026-06-12 |
| 10 | config-reader BOM tolerance (read_config utf-8-sig) + integrate_main commit-failure branch tests; split two at-limit test modules under 300 LOC | iterate | unit | +0 | 19/19 | PASS | 2026-06-12 |
| 11 | compress agent-doc backlog to one-line pointers + retire convention-routing fallback + lower entry-budget cutoff | iterate | unit | +0 | 4279/4279 | PASS | 2026-06-12 |
| 12 | Scope the two whole-set arch-drift checkers (test_architecture_md_reflects_arch_impact + Group-F F5 detective) to decision-drops owned by this tree (run_id in committed shipwright_events.jsonl) so cross-branch campaign sibling drops no longer false-fail; fail-open when no event log. | iterate | — | +0 | — | — | 2026-06-12 |
| 13 | triage_gc union-residence under-lock recompute (a1-6/F19 follow-up) + source-derived drift meta-test + tty_sanitize extraction | iterate | unit | +0 | 3193/3193 | PASS | 2026-06-12 |
| 14 | Compact agent-doc entries + impact-aware routing SSoT (IMPACT_TARGETS) + forward-only 600-char entry-budget gate; conventions.md CONTRIBUTING de-dup | iterate | — | +0 | — | — | 2026-06-12 |
| 15 | WP9 triage tooling hardening: F30 phaseQualityRefreshed GC token + drift meta-test, F19 GC TOCTOU recompute-under-lock, F31 control-char sanitizer on title/detail/evidence (C0+C1) in both render surfaces, F29 promote/dismiss accept outbox-only items | iterate | unit | +0 | 3163/3164 | FAIL | 2026-06-12 |
| 16 | Installer/shell POSIX fixes (deep-audit WP10 F33-F38): set -e prereq counter, uv ~/.local/bin PATH, 13-plugin space-safe alias refresh, python3 resolver, dotenv-parse verify-setup | iterate | unit | +0 | 3157/3157 | PASS | 2026-06-12 |
| 17 | Fix two structurally-inert compliance gates (deep-audit WP3): Group H now in run_all default + on-stop coverage gate widened to A-H (F20); S4 FR-preservation join no longer raises TypeError (F21) | iterate | unit | +0 | 3146/3146 | PASS | 2026-06-12 |
| 18 | WP6 deep-audit fix: strict UTF-8 in resolve_churn/integrate_main git-I/O + structured commit-failure handling (F22 HIGH, F17 MED) | iterate | unit | +0 | 3147/3147 | PASS | 2026-06-12 |
| 19 | UTF-8 (utf-8-sig) in config readers + errors=replace on the F0.5 runner decode (deep-audit WP8/F24+F25) | iterate | unit | +0 | 3515/3516 | FAIL | 2026-06-12 |
| 20 | WP5 hook project-root/worktree resolvers + project guard (F5/F6/F7/F8/F10) | iterate | unit | +0 | 23/23 | PASS | 2026-06-12 |
| 21 | Pin UTF-8 on git-reading subprocess decodes (deep-audit WP7 F23/F26/F27) | iterate | unit | +0 | 8/8 | PASS | 2026-06-12 |
| 22 | triage.mark_status routes idle-main status flips to the outbox (symmetric with append_triage_item), completing campaign D1 for the status side; fixes undelivered tracked drift from WebUI/Stop-hook dismisses | iterate | unit | +0 | 3131/3131 | PASS | 2026-06-11 |
| 23 | F11 arms GitHub-native auto-merge for iterate/* PRs (gh pr merge --auto --squash --delete-branch), branch-scoped + fail-soft (B4.5 Phase 3) | iterate | unit | +0 | 363/363 | PASS | 2026-06-11 |
| 24 | Tier-3 PR review via OpenRouter custom-script (B4.5 Phase 2): pr-review.yml workflow + pr_review.py reviewer + pr_reviewer prompts + 4 snapshot/unit test files | iterate | unit | +0 | 414/417 | FAIL | 2026-06-11 |
| 25 | Add gh-pr-ci:{pr_number} action-unit: failed hard-gates on open PRs land in triage (B4.5 automerge loop-closing). Differentiated auto-resolve; session-wide symmetry; draft exclusion; truncation + filter=latest guards. | iterate | — | +0 | — | — | 2026-06-11 |
| 26 | Fix the check_security_scan PreToolUse deploy-gate: it substring-matched the whole command, so a trigger keyword (deploy/jelastic/vercel/...) inside a quoted argument VALUE — an iterate-finalization --justification, a commit message, or an echo string — false-blocked unrelated commands. New _is_deploy_command strips quoted spans ("..." / '...') before matching; main() uses it. Real deploy commands/scripts/paths stay visible and still gate. | iterate | unit | +0 | 669/679 | FAIL | 2026-06-11 |
| 27 | Make campaign sub-iterate spec_path repo-relative POSIX instead of machine-absolute (N1, trg-196f4aa6, follow-up of campaign 2026-06-07-tracked-campaign-status): new pure campaign_paths.py (relativize_spec_path / campaign_spec_path); campaign_init writes relative; the projection self-heals on regenerate (carry + fill); one-off idempotent migration rewrote the 7 tracked campaigns (44 sub-paths). | iterate | unit | +0 | 3468/3488 | FAIL | 2026-06-11 |
| 28 | Campaign status backfill + docs (S4): parse_campaign_skeleton strips markdown emphasis from id/slug cells so a legacy campaign.md (bold **C1**) matches the plain committed status.json ids (else re-projection drops completed subs); a read-only drift-guard test verifies every tracked campaign regenerates without downgrade; docs landed (hooks-and-pipeline glob-churn note, glossary Campaign-Status + token-vocab SSoT, ADR). Closes campaign 2026-06-07-tracked-campaign-status. | iterate | unit | +0 | 3451/3471 | FAIL | 2026-06-10 |
| 29 | Bloat Stop-gate resolves a file's ceiling from the worktree baseline it measures, not main (trg-28e83840) | iterate | unit | +0 | 3088/3088 | PASS | 2026-06-10 |
| 30 | Per-tree campaign status.json: F5b finalize wiring + scoped churn resolver (campaign S3) | iterate | unit | +0 | 3442/3462 | FAIL | 2026-06-10 |
| 31 | Campaign status projection: pure regenerate_campaign_status producer + campaign_progress regenerate CLI project per-sub-iterate status.json from the campaign.md skeleton and self-identifying work_completed events, with a never-downgrade guard (campaign 2026-06-07-tracked-campaign-status S2). | iterate | unit | +0 | 3426/3445 | FAIL | 2026-06-10 |
| 32 | Exempt session_handoff.md + build_dashboard.md (with triage_inbox.md) from artifact-path-canon in all migrations; drift test; dismiss trg-6ed063ae. | iterate | — | +0 | — | — | 2026-06-10 |
| 33 | triage_cli list pins stdout to UTF-8: fixes UnicodeEncodeError on Windows consoles for non-cp1252 item titles (found by the webui pending-delivery-badge boundary probe). | iterate | — | +0 | — | — | 2026-06-10 |
| 34 | History-calibrated complexity prior + cross-domain scope vocabulary for the iterate Stage-1 classifier | iterate | — | +0 | — | — | 2026-06-10 |
| 35 | Gate D2V evidence markdown write behind SHIPWRIGHT_D2V_WRITE_EVIDENCE; default runs assert without writing the tracked artifact. | iterate | — | +0 | — | — | 2026-06-10 |
| 36 | Add triage_cli.py list --json (unioned open items + pendingDelivery) as a WebUI contract. | iterate | — | +0 | — | — | 2026-06-10 |
| 37 | Campaign sub-iterates self-identify: runner Step 4 + manual --campaign/--sub-iterate-id stamp campaign/sub_iterate_id into the work_completed event via F5b --event-extras-json | iterate | mixed | +0 | 3457/3458 | FAIL | 2026-06-10 |
| 38 | Triage dedup collapses same-id appends keep-last (reader parity); unblocks outbox sweep on producer update re-append. | iterate | — | +0 | — | — | 2026-06-09 |
| 39 | Iterate-scoped external-review markers gitignored (not blanket); 6 tracked copies untracked. | iterate | — | +0 | — | — | 2026-06-09 |
| 40 | Relocate detective-audit JSON from repo root to .shipwright/compliance/audit-report.json; canon re-excludes audit-report.{md,json} (propagates to adopted repos); drop obsolete framework root ignore. | iterate | — | +0 | — | — | 2026-06-09 |
| 41 | Relocate phase-quality skill-compliance roll-ups under the gitignored FINDING_DIR; resolve main_repo_root (not cwd) in the bloat marker writer+reader via a shared fail-soft resolver; defensive nested-locks gitignore canon. | iterate | — | +0 | — | — | 2026-06-08 |
| 42 | evt-ec8e9621 | iterate | — | +0 | — | — | 2026-06-08 |
| 43 | Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | iterate | unit | +6 | 6/6 | PASS | 2026-06-08 |
| 44 | evt-b9b5ddf2 | iterate | unit | +36 | 2954/2954 | PASS | 2026-06-08 |
| 45 | Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | iterate | unit | +22 | 2913/2913 | PASS | 2026-06-08 |
| 46 | scaffold the append-log merge=union .gitattributes driver into managed repos (adopt E.13c + iterate self-heal) | iterate | unit | +0 | 2884/2884 | PASS | 2026-06-07 |
| 47 | triage main-tree drift reconcile-and-commit at integrate/sync | iterate | mixed | +0 | 2861/2861 | PASS | 2026-06-07 |
| 48 | Track campaign status.json for compliance-detective-realign + track-triage-jsonl (durable per-sub board on fresh clone / deployed WebUI; stopgap for trg-fda5f7a3). | iterate | — | +0 | — | — | 2026-06-07 |
| 49 | allowlist cafebabe:deadbeef in oss_backend generated gitleaks config (GAP-3) | iterate | unit | +0 | 56/56 | PASS | 2026-06-07 |
| 50 | Harden iterate finalization tooling: F11 verifier accepts none_reason as a spec_impact=none justification; F0.5 surface_verification rejects compound runners fast with a clear error; arch-drift sanity test no longer false-FAILs on a post-release tree. | iterate | — | +0 | — | — | 2026-06-07 |
| 51 | SBOM distinguishes not-installed from no-declared-license; not-installed is silent (no triage, dash in sbom.md), only resolved-but-no-license is surfaced. | iterate | — | +0 | — | — | 2026-06-07 |
| 52 | Add campaign_init --expands-triage / --from-triage so a triage item can be promoted to a campaign anchor; writes expands_triage into both status.json and the campaign.md frontmatter so the Command Center shows 'Start Campaign' on that triage card. | iterate | — | +0 | — | — | 2026-06-07 |
| 53 | adopt scaffolds .gitleaks.toml + hardens security.yml.template | iterate | unit | +0 | 312/312 | PASS | 2026-06-07 |
| 54 | GC machine-churn complianceRefreshed compliance-backlog dismissals (add token to triage_gc.MACHINE_REASONS) | iterate | unit | +0 | 24/24 | PASS | 2026-06-07 |
| 55 | triage docs + monorepo migration (campaign 2026-06-05-track-triage-jsonl, sub-iterate E) | iterate | unit | +0 | 2839/2839 | PASS | 2026-06-07 |
| 56 | F5 architecture-drift detector switched from a git-history oracle (dead on gitignored drops) to content reconciliation (incl. convention); new canon/blocking F11 gate check_architecture_documented sharing one oracle (shared/scripts/lib/architecture_doc.py); dead check_architecture_reviewed + run_cross_artifact_checks removed; 5 orphan architecture.md entries back-filled. | iterate | — | +0 | — | — | 2026-06-06 |
| 57 | adopt skill docs: triage.jsonl is tracked, not gitignored (D) | iterate | unit | +0 | 24/24 | PASS | 2026-06-05 |
| 58 | SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift) | iterate | unit | +0 | 617/617 | PASS | 2026-06-05 |
| 59 | triage_gc tool: machine-churn-only dismissed-pile compaction | iterate | unit | +0 | 387/387 | PASS | 2026-06-05 |
| 60 | git-track triage.jsonl: gitignore negation + scaffolder self-heal (C1) | iterate | unit | +0 | 19/19 | PASS | 2026-06-05 |
| 61 | triage.jsonl merge-safety + leak-guard exemption (like events) — C2 | iterate | unit | +0 | 49/49 | PASS | 2026-06-05 |
| 62 | Propagate degraded scanner legs (fatal/empty/truncated) via a scan_errors side-channel so the threshold/report/CI-gate layers fail closed instead of treating a dead leg as a clean 0-findings scan. | iterate | — | +0 | — | — | 2026-06-05 |
| 63 | B7 Rule E: exclude non-functional Conventional-Commit types (build/chore/ci/docs/style/test) from B7 by default (configurable); functional types still flagged. Supersedes the narrow Rule D + kills the ci/docs/chore backfill treadmill. | iterate | unit | +0 | 44/44 | PASS | 2026-06-05 |
| 64 | Make the bloat marker recorder + Stop gate worktree-aware: strip the .worktrees/<slug>/ prefix for the baseline lookup so a worktree iterate growing an already-baselined file (ADR+bump) is not mis-classified crossing and does not false-block Stop (trg-305e2aab) | iterate | unit | +0 | 9/9 | PASS | 2026-06-05 |
| 65 | gitleaks --report-path - wrote a stray file named - instead of stdout, so the secrets leg silently returned 0 findings everywhere; report now written to a temp file and read back; smoke positive-control converted to ADR-044 CI-gated fail | iterate | unit | +0 | 320/320 | PASS | 2026-06-05 |
| 66 | Add A5.8: execute the deployed critical-gate shell against dual-artifact fixtures (flavor-agnostic across SARIF/findings.json; skip-safe; env kill-switch). | iterate | — | +0 | — | — | 2026-06-05 |
| 67 | Enforce the FR-gate on the finalize write-path + accept same-event D3 delivery | iterate | unit | +0 | 64/64 | PASS | 2026-06-05 |
| 68 | Set security.yml.template checkout to fetch-depth: 1 (working-tree only) and correct the misleading diff-aware-secret-scans comment; no scanner reads git history. | iterate | — | +0 | — | — | 2026-06-05 |
| 69 | C1/C2 detective-realign doc + ledger closeout | iterate | unit | +0 | 41/41 | PASS | 2026-06-05 |
| 70 | Scope the bloat recorder to the project root so cross-repo edits do not leak into this project marker and block its Stop gate. | iterate | — | +0 | — | — | 2026-06-04 |
| 71 | Fix the adopt security-gate so it resolves SARIF severity at rule level, blocks on any secret, and fails closed — previously a structural false green in every adopted repo. | iterate | — | +0 | — | — | 2026-06-04 |
| 72 | Add producer-owned campaign lifecycle status (draft->active->complete): campaign_init writes status:draft to status.json + campaign.md frontmatter; campaign_progress gains a start subcommand (->active), update-status auto-sets complete when all sub-iterates complete, summary prints the top-level status; the autonomous campaign loop marks the campaign active at run start; missing status = legacy fallback to done<total. | iterate | — | +0 | — | — | 2026-06-03 |
| 73 | Dedup SessionStart Phase-Quality injection to once-per-event via event_once.claim_once (fail-open). | iterate | — | +0 | — | — | 2026-06-02 |
| 74 | Rewrote test_upload_sarif_action_used to assert the real upload-sarif uses: line (anchored regex, version-agnostic) instead of matching a stale comment; corrected the two @v3 permission comments in security.yml to @v4. | iterate | — | +0 | — | — | 2026-06-01 |
| 75 | Pinned third-party GitHub Actions (setup-uv, create-or-update-comment) to commit SHAs; added SHA256 verification for the Gitleaks binary download in ci.yml + security.yml; corrected stale SECURITY.md scope (webui) and Dependabot wording. | iterate | — | +0 | — | — | 2026-06-01 |
| 76 | Detective audit honors event_amended corrections (group_d applies shared apply_amendments SSOT before D1-D5; new shared/scripts/lib/events_amend.py, re-exported by config.py); D4 disabled for the framework monorepo (gating-CI stale-noise); evt-5aca940d corrected to spec_impact=none. | iterate | — | +0 | — | — | 2026-06-01 |
| 77 | Document the gating ruff CI lint step in CLAUDE.md Development section. | iterate | — | +0 | — | — | 2026-06-01 |
| 78 | D5 honors change_type+none_reason exemption; add audit_config.disabled_checks applicability gate; framework repo disables A5.6/B7/D1/G2 | iterate | — | +0 | — | — | 2026-06-01 |
| 79 | plugin-sync Stop-hook triage item written to durable main-repo log (worktree-aware) | iterate | unit | +0 | 48/49 | FAIL | 2026-06-01 |
| 80 | CI gate-coverage guard + workflow hardening (test-dir coverage, loose-gate allowlist, security fail-closed) | iterate | unit | +0 | 2674/2675 | FAIL | 2026-05-31 |
| 81 | Gate CI Python lint on a curated bug-focused ruff ruleset (pyflakes F + high-signal E/W); remove the \|\| true + continue-on-error neutering; provision ruff via pinned uvx; rename job to Python (lint + test). | iterate | — | +0 | — | — | 2026-05-31 |
| 82 | Wire shared/ test suites (shared/tests, shared/scripts/tests, shared/scripts/tools/tests) into ci.yml as blocking per-dir invocations; fix 2 non-hermetic validate_env tests via a dir conftest; make the born-red arch-md sibling skip when gitignored decision-drops are absent. | iterate | — | +0 | — | — | 2026-05-31 |
| 83 | remove vestigial "\|\| true" from CI integration step (gate failures) + add pathlib.Path import to clear 14 F821 in test_events_log.py | iterate | unit | +0 | 2771/2771 | PASS | 2026-05-31 |
| 84 | events=union + churn-merge resolver/integrate_main: auto-reconcile generated artifacts on origin/main merge | iterate | — | +0 | — | — | 2026-06-01 |
| 85 | Collapse the compliance detective-audit mirror into one rolling compliance:backlog action-unit (auto-dismiss + refresh + legacy retirement) | iterate | — | +0 | — | — | 2026-05-31 |
| 86 | Render unengaged phases as SKIP (not FAIL) in the persisted finding JSON so the skill-compliance dashboard agrees with the triage inbox | iterate | — | +0 | — | — | 2026-05-31 |
| 87 | Collapse phase-quality Tier-1 FAIL triage into one rolling phaseQuality:backlog action-unit; add phase-applicability gate and run_id=unknown spec-check guard | iterate | — | +0 | — | — | 2026-05-31 |
| 88 | iterate completion: test-completeness-gate | iterate | — | +0 | — | — | 2026-05-30 |
| 89 | iterate complete: P3.1 reviewer stack (spec-reviewer + doubt-reviewer cascade) | iterate | — | +0 | — | — | 2026-05-30 |
| 90 | Propagate canonical .shipwright artifact-ignore block to consuming projects via SSoT template + idempotent merge in adopt/project + drift test | iterate | — | +0 | — | — | 2026-05-30 |
| 91 | Add audit_compliance_on_stop.py: auto-emit/auto-dismiss source=compliance triage items on every iterate/changelog Stop, gated on full A-G audit coverage. | iterate | — | +0 | — | — | 2026-05-30 |
| 92 | Align 7 stale record_event tests to the C.1 FR-gate (gates all iterates incl. bug/intentless); surface CI shared-test gap (trg-f363b1ab) | iterate | — | +0 | — | — | 2026-05-30 |
| 93 | RTM: untested (0/0) events neutral; status from latest tested event (fixes 7 false FAILs); neutralize leaked verification event via event_amended | iterate | — | +0 | — | — | 2026-05-30 |
| 94 | SP3+OS2 post-Campaign-B reintegration — F-debug.md systematic-debugging sub-skill + assumptions-first interview pre-phase | iterate | unit | +0 | 317/317 | PASS | 2026-05-29 |
| 95 | suggest_iterate UserPromptSubmit hook: emit hookEventName on hookSpecificOutput (+ AST meta-test) | iterate | unit | +0 | 2558/2558 | PASS | 2026-05-29 |
| 96 | Bloat marker keyed off stdin-payload session_id (not env) in check_file_size.py + bloat_gate_on_stop.py | iterate | unit | +0 | 2549/2550 | FAIL | 2026-05-29 |
| 97 | P4.1 Skill Bootstrap Pack: using-shipwright SessionStart bootstrap + writing-plugin/plugin-cache Stop wave (SP2+SP4) | iterate | unit | +0 | 2545/2545 | PASS | 2026-05-29 |
| 98 | events.jsonl per-tree, PR-committed artifact (worktree iterate audit-log fix) | iterate | unit | +0 | 2449/2450 | FAIL | 2026-05-29 |
| 99 | Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings) | iterate | unit | +0 | 2449/2449 | PASS | 2026-05-28 |
| 100 | Correction event: spec_impact=none with proper justification field for the verifier (supersedes evt-13153a5c). | iterate | — | +0 | — | — | 2026-05-27 |
| 101 | Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check | iterate | — | +0 | — | — | 2026-05-27 |
| 102 | Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT) | iterate | — | +0 | — | — | 2026-05-27 |
| 103 | Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d). | iterate | — | +0 | — | — | 2026-05-27 |
| 104 | Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass + audit_staleness coverage extension + merge-not-rebase doc convention. | iterate | — | +0 | — | — | 2026-05-27 |
| 105 | B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | iterate | unit | +26 | 1104/1104 | PASS | 2026-05-26 |
| 106 | Pre-commit anti-ratchet hook + bloat-check CI workflow + bloat-exception ADR template + shared glossary (Campaign A.defense, closes Campaign A defense-in-depth layer) | iterate | mixed | +0 | 41/41 | PASS | 2026-05-25 |
| 107 | fix bloat_gate_on_stop.py Stop-hook schema violation | iterate | unit | +0 | 131/131 | PASS | 2026-05-25 |
| 108 | Campaign A.review: bloat reviewer prompts (Karpathy+Osmani+Shipwright) + Group H detective audit (H0-H6) | iterate | mixed | +0 | 14/14 | PASS | 2026-05-25 |
| 109 | Phase 0 bloat baseline inventory — activates A.foundation Stop-Gate | iterate | — | +0 | — | — | 2026-05-25 |
| 110 | Bloat Loop-Gate (Campaign A.foundation = A1+A2+A3): runtime-prompt classification, per-session marker writer, blocking Stop-Gate, registered in every plugin | iterate | unit | +0 | 2678/2678 | PASS | 2026-05-25 |
| 111 | SBOM triage producer cluster-collapse | iterate | mixed | +0 | 514/514 | PASS | 2026-05-23 |
| 112 | SBOM resolver pin to per-manifest .venv METADATA | iterate | mixed | +0 | 497/497 | PASS | 2026-05-23 |
| 113 | Resolve architecture.md merge-conflict markers (lines 90-94) + extend ALLOWLIST[compliance] to include finalize_security_compliance.py whose cross-plugin path comment trips the hyphen-segment regex blind spot | iterate | unit | +0 | 2/3 | FAIL | 2026-05-23 |
| 114 | C1 design verifier (and sister manifest-exists check) skip on scope=library projects via _is_no_ui_scope helper; audit translates ok=None to status=skip via existing check_result_to_finding | iterate | unit | +0 | 19/19 | PASS | 2026-05-23 |
| 115 | iterate finalization | iterate | — | +0 | — | — | 2026-05-23 |
| 116 | Architecture-md drift protection test + 11 historical drift entries backfilled + 3 discipline learnings in conventions.md (TDD RED-first, F0/F11 leak-guard symmetry, F2 flag-md coupling) | iterate | unit | +0 | 2/2 | PASS | 2026-05-23 |
| 117 | F11 verifier multi-commit-aware via run_id lookup (fixes false positives on iterate-f7-tracked-event-log-commit) | iterate | unit | +0 | 70/70 | PASS | 2026-05-23 |
| 118 | iterate skill F7b: seals tracked event-log appends to prevent silent reset wipe (commit_event_followup.py + SKILL.md + 6 tests) | iterate | unit | +0 | 6/6 | PASS | 2026-05-22 |
| 119 | compliance reconciliation: D1 spec-FR coverage — multi-FR event covering FR-01.03/04/05/06/07/08/09/12 (post-2026-05-04 watermark gap; no source/test/spec changes) | iterate | — | +0 | — | — | 2026-05-22 |
| 120 | mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | iterate | — | +0 | — | — | 2026-05-22 |
| 121 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 122 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 123 | Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | iterate | — | +0 | — | — | 2026-05-22 |
| 124 | deterministic render timestamps from max(event.ts) | iterate | unit | +34 | 34/34 | PASS | 2026-05-21 |
| 125 | empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | iterate | unit | +0 | 2621/2621 | PASS | 2026-05-21 |
| 126 | VERIFICATION: bug+change-type — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 127 | VERIFICATION artifact (amended: leaked from 2026-05-21 empirical-verification campaign; no real FR work) — neutralized by iterate-2026-05-30-rtm-covered-ignore-untested-events | iterate | — | +0 | — | — | 2026-05-21 |
| 128 | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 129 | Artifact-based GitHub security producer for Triage Inbox | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 130 | escape pipe and newline in markdown table cells | iterate | unit | +23 | 23/23 | PASS | 2026-05-20 |
| 131 | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | mixed | +0 | 3507/3507 | PASS | 2026-05-18 |
| 132 | triage detector dedup + auto-resolve (rebased onto #31) | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 133 | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | unit | +0 | 140/140 | PASS | 2026-05-16 |
| 134 | triage detector dedup + auto-resolve | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 135 | fix adopt external-review config defaults | iterate | mixed | +0 | 304/304 | PASS | 2026-05-16 |
| 136 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | mixed | +0 | 2519/2526 | FAIL | 2026-05-16 |
| 137 | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | mixed | +0 | 312/312 | PASS | 2026-05-15 |
| 138 | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | mixed | +0 | 40/40 | PASS | 2026-05-14 |
| 139 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 140 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 141 | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | unit | +0 | 16/16 | PASS | 2026-05-09 |
| 142 | evt-f66286bf | iterate | — | +0 | — | — | 2026-05-07 |
| 143 | evt-623a29ad | iterate | — | +0 | — | — | 2026-05-07 |
| 144 | F0.5 empirical-test backfill | iterate | unit | +0 | 1575/1575 | PASS | 2026-05-06 |
| 145 | F0.5 End-to-End Verification Gate | iterate | unit | +0 | 1548/1548 | PASS | 2026-05-06 |
| 146 | hooks-consistency parser handles quoted commands — 27/27 green | iterate | unit | +0 | 1297/1297 | PASS | 2026-05-06 |
| 147 | post-migration canon cleanup — 9 tests green | iterate | unit | +0 | 1270/1270 | PASS | 2026-05-06 |
| 148 | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | unit | +0 | 34/34 | PASS | 2026-05-05 |
| 149 | verifier accepts drop-dir entries + dashboard short-SHAs | iterate | unit | +0 | 32/32 | PASS | 2026-05-05 |
| 150 | adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | unit | +0 | 241/241 | PASS | 2026-05-05 |
| 151 | FR-table parser accepts 5-col adopt format + drift protection | iterate | unit | +0 | 1594/1628 | FAIL | 2026-05-05 |
| 152 | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | unit | +0 | 12/12 | PASS | 2026-05-05 |
| 153 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | unit | +0 | 1691/1716 | FAIL | 2026-05-05 |
| 154 | F runner contract mandates reviews (ADR-029) | iterate | unit | +0 | 188/188 | PASS | 2026-05-04 |
| 155 | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | unit | +0 | 1539/1539 | PASS | 2026-05-04 |
| 156 | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | unit | +19 | 19/19 | PASS | 2026-05-03 |
| 157 | changelog MSYS path-mangling linter | iterate | unit | +0 | 19/19 | PASS | 2026-05-03 |
| 158 | hooks.json quoting (deferred from ADR-020) | iterate | unit | +0 | 13/13 | PASS | 2026-05-03 |
| 159 | iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | unit | +0 | 53/53 | PASS | 2026-05-03 |
| 160 | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | unit | +0 | 47/47 | PASS | 2026-05-03 |
| 161 | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | unit | +0 | 249/249 | PASS | 2026-05-03 |
| 162 | fix hook_installer Shape A -> B | iterate | unit | +0 | 5/5 | PASS | 2026-05-03 |
| 163 | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | unit | +0 | 233/233 | PASS | 2026-05-02 |
| 164 | post-adoption framework cleanup (Sub-1A through 1D) | iterate | unit | +0 | 225/225 | PASS | 2026-05-02 |

## Full Suite Runs

| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |
|-----|---------|------|-------------|-------|-----|-------|------|
| 1 | iterate | 312/312 | — | — | — | — | 2026-06-07 |
| 2 | iterate | 56/56 | — | — | — | — | 2026-06-07 |
| 3 | iterate | 2861/2861 | — | — | — | — | 2026-06-07 |
| 4 | iterate | 2884/2884 | — | — | — | — | 2026-06-07 |
| 5 | iterate | 2913/2913 | — | — | — | — | 2026-06-08 |
| 6 | iterate | 2954/2954 | — | — | — | — | 2026-06-08 |
| 7 | iterate | 6/6 | — | — | — | — | 2026-06-08 |
| 8 | iterate | 3457/3458 | — | — | — | — | 2026-06-10 |
| 9 | iterate | 3426/3445 | — | — | — | — | 2026-06-10 |
| 10 | iterate | 3442/3462 | — | — | — | — | 2026-06-10 |
| 11 | iterate | 3088/3088 | — | — | — | — | 2026-06-10 |
| 12 | iterate | 3451/3471 | — | — | — | — | 2026-06-10 |
| 13 | iterate | 3468/3488 | — | — | — | — | 2026-06-11 |
| 14 | iterate | 669/679 | — | — | — | — | 2026-06-11 |
| 15 | iterate | 414/417 | — | — | — | — | 2026-06-11 |
| 16 | iterate | 363/363 | — | — | — | — | 2026-06-11 |
| 17 | iterate | 3131/3131 | — | — | — | — | 2026-06-11 |
| 18 | iterate | 8/8 | — | — | — | — | 2026-06-12 |
| 19 | iterate | 23/23 | — | — | — | — | 2026-06-12 |
| 20 | iterate | 3515/3516 | — | — | — | — | 2026-06-12 |
| 21 | iterate | 3147/3147 | — | — | — | — | 2026-06-12 |
| 22 | iterate | 3146/3146 | — | — | — | — | 2026-06-12 |
| 23 | iterate | 3157/3157 | — | — | — | — | 2026-06-12 |
| 24 | iterate | 3163/3164 | — | — | — | — | 2026-06-12 |
| 25 | iterate | 3193/3193 | — | — | — | — | 2026-06-12 |
| 26 | iterate | 4279/4279 | — | — | — | — | 2026-06-12 |
| 27 | iterate | 19/19 | — | — | — | — | 2026-06-12 |
| 28 | iterate | 3203/3203 | — | — | — | — | 2026-06-12 |
| 29 | iterate | 3284/3284 | — | — | — | — | 2026-06-12 |
| 30 | iterate | 3289/3289 | — | — | — | — | 2026-06-12 |

## Code Review Evidence

| Event | Review Type | Findings | Fixed | Status |
|-------|------------|----------|-------|--------|
| B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | external-iterate-review | 12 | 12 | PASS |
| Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | external-plan+external-code | 18 | 18 | PASS |
| evt-b9b5ddf2 | external-plan+code | 16 | 4 | OPEN |
| Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | plan+code | 20 | 8 | OPEN |

