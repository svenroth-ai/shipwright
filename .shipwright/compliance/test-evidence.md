# Test Evidence Report

Generated: 2026-06-17T06:52:25.834092+00:00

## Summary

| Metric | Value |
|--------|-------|
| Total test checkpoints | 201 |
| Total unit tests (latest) | 20/20 |
| New tests from iterations | +191 |

## Test Progression

| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |
|---|-------|--------|-------|-----------|-------------|--------|------|
| 1 | launch PII / local-path scrub | iterate | unit | +0 | 20/20 | PASS | 2026-06-17 |
| 2 | launch version unification & Beta branding | iterate | unit | +0 | 28/29 | PASS (1 skipped) | 2026-06-17 |
| 3 | Compliance-artifact rendering fixes: shared normalize_intent() for the Type column (RTM Verification Timeline + Build Dashboard); skip-aware PASS/COVERED for merged-work passed<total gaps in Test Evidence + RTM (never a gap-driven FAIL); unconditional Audit Report + conditional Activity Dashboard links in the Compliance Dashboard. | iterate | unit | +25, 6 mod | 701/701 | PASS | 2026-06-16 |
| 4 | Lead README and guide openings with the brand tagline 'Ship right, not just fast.' and the vibe-coding-to-agentic-engineering positioning | iterate | unit | +0 | 24/24 | PASS | 2026-06-16 |
| 5 | Remove development-provenance references (ADRs, iterate IDs, version/campaign stamps) from docs/guide.md so it documents current behavior, not its origin history | iterate | unit | +0 | 85/85 | PASS | 2026-06-16 |
| 6 | tighten bloat baseline for iterate_checks.py (1122->1121) | iterate | unit | +0 | 94/94 | PASS | 2026-06-15 |
| 7 | SessionStart phase-quality consumer drops sentinel-run (run_id unknown) FAILs from a stale findings digest and caps AFTER filtering; raw parser left uncapped. Defense-in-depth mirroring load_actionable_findings. | iterate | — | +0 | — | — | 2026-06-15 |
| 8 | Repo-agnostic agent-doc entry-budget gate (lib.agent_doc_budget + check_agent_doc_budget.py + F11 verifier check), closed the run-id-slug date hole, fixed the blank-line ADR writer, and compacted/de-bolded architecture.md + conventions.md. | iterate | — | +0 | — | — | 2026-06-14 |
| 9 | Phase-quality rollups read load_actionable_findings (excludes sentinel run_id=unknown snapshots), so stale/degenerate audits stop driving false Tier-1 surfacing across the triage backlog, SessionStart injection, dashboard and report. | iterate | — | +0 | — | — | 2026-06-14 |
| 10 | Hook fan-out consolidation: once-per-event guard (claim_once_for_event) on audit/handoff/drift + session-state phase resolver (resolve_engaged_phases) | iterate | unit | +0 | 3473/3473 | PASS | 2026-06-14 |
| 11 | tighten bloat baseline for autonomous_loop.py (current 440 to 436) | iterate | unit | +0 | 96/96 | PASS | 2026-06-14 |
| 12 | Document the campaign interleaved-serial run-model in docs/guide.md (new Chapter 8 Campaign Mode section + Appendix B sharpening + stale drain-example fix) | iterate | unit | +0 | 7/7 | PASS | 2026-06-14 |
| 13 | tighten bloat baseline to actual LOC; prune 3 under-limit entries (clear Group H2) | iterate | unit | +0 | 3442/3442 | PASS | 2026-06-13 |
| 14 | Pin verifier CLI stdout to UTF-8 — fix Windows cp1252 UnicodeEncodeError on '→' in reports | iterate | mixed | +0 | 3441/3453 | PASS (12 skipped) | 2026-06-13 |
| 15 | interleaved-serial as the single documented campaign default (branch_strategy: serial) | iterate | unit | +0 | 3881/3881 | PASS | 2026-06-13 |
| 16 | Fold spec_checks _run_git/_git_available onto verifiers/git_helpers.py (optional timeout param, unified failure code) | iterate | unit | +0 | 69/69 | PASS | 2026-06-13 |
| 17 | Triage not for current-run work — drop plugin-sync + F0.5 triage producers | iterate | mixed | +0 | 3653/3665 | PASS (12 skipped) | 2026-06-13 |
| 18 | iterate finalization | iterate | — | +0 | — | — | 2026-06-13 |
| 19 | Extract duplicated cross-platform _FileLock into shared/scripts/lib/file_lock.py; both call sites import it; unify on the parent-dir-creating superset. | iterate | — | +0 | — | — | 2026-06-13 |
| 20 | unify the code-simplify gate with the bloat/reducibility catalog: relocate behavior_snapshot.py to shared/scripts/tools (SSoT), F-simplify adopts the catalog vocabulary, catalog cites the snapshot/verify gate as the mechanical G3 proof | iterate | unit | +0 | 3996/3996 | PASS | 2026-06-13 |
| 21 | Align the bloat marker writer (check_file_size) to key delta/was_in_allowlist off the worktree's own baseline via a shared worktree_root_for SSoT also used by the Stop gate (trg-537334f1). | iterate | unit | +0 | 3419/3419 | PASS | 2026-06-13 |
| 22 | code-simplify skill (OS1 / P3.2): SIMPLIFY sub-mode of CHANGE + behavior_snapshot snapshot/verify gate + F-simplify.md + guide docs | iterate | unit | +0 | 4082/4082 | PASS | 2026-06-13 |
| 23 | audit-3 WP11b low-risk hardening (F18/F32/F39/F40/F41) | iterate | unit | +0 | 4220/4236 | PASS (16 skipped) | 2026-06-13 |
| 24 | Read run-config standalone flag without triggering the unlocked legacy migration | iterate | unit | +0 | 164/164 | PASS | 2026-06-13 |
| 25 | durable atomic writes (fsync) across all atomic writers | iterate | unit | +0 | 4283/4283 | PASS | 2026-06-13 |
| 26 | sync 6 stale SKILL.md/code/config items to the corrected guide (C1-C6) | iterate | unit | +0 | 4343/4343 | PASS | 2026-06-13 |
| 27 | audit-3 WP11a docs/SSoT reconciliation (F3 hooks.json format, F4 registry drift, F9 outbox matrix, F28 F6 decision-drops staging) | iterate | unit | +0 | 3796/3796 | PASS | 2026-06-13 |
| 28 | guide.md correctness audit + 21 fixes vs code/ADRs | iterate | — | +0 | — | — | 2026-06-13 |
| 29 | docs install/Get-Started rewrite + GitHub/auto-merge guide + marketplace metadata parity | iterate | — | +0 | — | — | 2026-06-13 |
| 30 | hook block-channel (WP4): route PostToolUse security-guard reasons to stderr; SessionStart drift gate is honest warn-only via additionalContext | iterate | unit | +0 | 3400/3400 | PASS | 2026-06-13 |
| 31 | adopt scaffolds profile-aware CodeQL + AUTOMERGE_SETUP doc for brownfield automerge-readiness (bloat-check deferred) | iterate | mixed | +0 | 3737/3737 | PASS | 2026-06-13 |
| 32 | extract diff-driven risk detectors + integration-coverage verifier into dedicated modules to ratchet two bloat baselines down | iterate | unit | +0 | 3818/3830 | PASS (12 skipped) | 2026-06-13 |
| 33 | run-config concurrency & atomicity (WP2: F11/F12/F13) | iterate | unit | +0 | 162/162 | PASS | 2026-06-13 |
| 34 | WP1: phase-session hooks resolve identity from the stdin payload (F1); atomic event-log dedup (F14); phase_failed/stale_stop_rejected event types (F15) | iterate | unit | +0 | 3348/3362 | PASS (14 skipped) | 2026-06-12 |
| 35 | Coerce explicit-null affected_frs/new_frs (and tests/review) in WorkEvent.from_dict | iterate | unit | +0 | 697/697 | PASS | 2026-06-12 |
| 36 | Relocate resolve_main_repo_root from lib/events_log.py to lib/repo_root.py with a lazy back-compat re-export; migrate net-zero consumers; keep the two grandfathered consumers (iterate_checks, group_f) on the re-export to avoid ratcheting bloat. | iterate | — | +0 | — | — | 2026-06-12 |
| 37 | Intelligent bloat gate: LOC-as-router -> falsifiable reducibility reviewer (closed catalog D/A/X/C/S/M/P/T + guardrails G1-G6); shared SSoT catalog + per-language idiom-map + reviewer dimensions across 3 surfaces + drift-protection test. | iterate | — | +0 | — | — | 2026-06-12 |
| 38 | W2 phase-quality check SKIPs on an unresolvable run_id (mirror S2/S3); fixes the audit-context false-FAIL/false-PASS when no iterate run resolves; also fixes a latent empty-run_id crash | iterate | unit | +0 | 3289/3289 | PASS | 2026-06-12 |
| 39 | Clear bloat Group H1/H2: tighten 51 stale baseline entries to actual LOC + grandfather 8 oversize files (reducibility-catalog dogfood); follow-ups trg-af476d87 + trg-b9acb195. | iterate | — | +0 | — | — | 2026-06-12 |
| 40 | cross_component risk flag forces an integration-coverage test at medium+, enforced non-dodgeably by the F11 verifier recomputing the flag from the diff. Closes the composition axis of the empirical machinery. | iterate | — | +0 | — | — | 2026-06-12 |
| 41 | Windows: test-run the python3 probe so the Microsoft Store stub does not abort the marketplace cache sync | iterate | mixed | +0 | 3284/3284 | PASS | 2026-06-12 |
| 42 | End-to-end parallel-merge cascade integration test (3 concurrent iterates + a 3-sub campaign): proves curated-union + churn-regenerate + JSONL-union resolve together with no cascade. | iterate | — | +0 | — | — | 2026-06-12 |
| 43 | Delivery-Watch: F11 confirms the PR actually merges green before done (no shoot-and-forget); watch_pr_delivery.py + F2 budget-lint-before-push rule. | iterate | — | +0 | — | — | 2026-06-12 |
| 44 | merge=union for curated agent-docs (architecture.md + conventions.md) via a distinct CURATED_DOC_UNION_PATHS category; closes the parallel-iterate bullet-prepend cascade server-side (follow-up to automerge-serial-integrate). | iterate | — | +0 | — | — | 2026-06-12 |
| 45 | Serial integrate_main merge for campaign/parallel iterates: ensure_current.py refresh-if-behind guard at F11 + SHIPWRIGHT_ITERATE_AUTOMERGE defer with serial drain (auto-merge churn fix, Option A). | iterate | — | +0 | — | — | 2026-06-12 |
| 46 | Consolidate the project-detection predicate across all hooks onto one canonical lib.project_root.is_shipwright_project | iterate | unit | +0 | 3203/3203 | PASS | 2026-06-12 |
| 47 | config-reader BOM tolerance (read_config utf-8-sig) + integrate_main commit-failure branch tests; split two at-limit test modules under 300 LOC | iterate | unit | +0 | 19/19 | PASS | 2026-06-12 |
| 48 | compress agent-doc backlog to one-line pointers + retire convention-routing fallback + lower entry-budget cutoff | iterate | unit | +0 | 4279/4279 | PASS | 2026-06-12 |
| 49 | Scope the two whole-set arch-drift checkers (test_architecture_md_reflects_arch_impact + Group-F F5 detective) to decision-drops owned by this tree (run_id in committed shipwright_events.jsonl) so cross-branch campaign sibling drops no longer false-fail; fail-open when no event log. | iterate | — | +0 | — | — | 2026-06-12 |
| 50 | triage_gc union-residence under-lock recompute (a1-6/F19 follow-up) + source-derived drift meta-test + tty_sanitize extraction | iterate | unit | +0 | 3193/3193 | PASS | 2026-06-12 |
| 51 | Compact agent-doc entries + impact-aware routing SSoT (IMPACT_TARGETS) + forward-only 600-char entry-budget gate; conventions.md CONTRIBUTING de-dup | iterate | — | +0 | — | — | 2026-06-12 |
| 52 | WP9 triage tooling hardening: F30 phaseQualityRefreshed GC token + drift meta-test, F19 GC TOCTOU recompute-under-lock, F31 control-char sanitizer on title/detail/evidence (C0+C1) in both render surfaces, F29 promote/dismiss accept outbox-only items | iterate | unit | +0 | 3163/3164 | PASS (1 skipped) | 2026-06-12 |
| 53 | Installer/shell POSIX fixes (deep-audit WP10 F33-F38): set -e prereq counter, uv ~/.local/bin PATH, 13-plugin space-safe alias refresh, python3 resolver, dotenv-parse verify-setup | iterate | unit | +0 | 3157/3157 | PASS | 2026-06-12 |
| 54 | Fix two structurally-inert compliance gates (deep-audit WP3): Group H now in run_all default + on-stop coverage gate widened to A-H (F20); S4 FR-preservation join no longer raises TypeError (F21) | iterate | unit | +0 | 3146/3146 | PASS | 2026-06-12 |
| 55 | WP6 deep-audit fix: strict UTF-8 in resolve_churn/integrate_main git-I/O + structured commit-failure handling (F22 HIGH, F17 MED) | iterate | unit | +0 | 3147/3147 | PASS | 2026-06-12 |
| 56 | UTF-8 (utf-8-sig) in config readers + errors=replace on the F0.5 runner decode (deep-audit WP8/F24+F25) | iterate | unit | +0 | 3515/3516 | PASS (1 skipped) | 2026-06-12 |
| 57 | WP5 hook project-root/worktree resolvers + project guard (F5/F6/F7/F8/F10) | iterate | unit | +0 | 23/23 | PASS | 2026-06-12 |
| 58 | Pin UTF-8 on git-reading subprocess decodes (deep-audit WP7 F23/F26/F27) | iterate | unit | +0 | 8/8 | PASS | 2026-06-12 |
| 59 | triage.mark_status routes idle-main status flips to the outbox (symmetric with append_triage_item), completing campaign D1 for the status side; fixes undelivered tracked drift from WebUI/Stop-hook dismisses | iterate | unit | +0 | 3131/3131 | PASS | 2026-06-11 |
| 60 | F11 arms GitHub-native auto-merge for iterate/* PRs (gh pr merge --auto --squash --delete-branch), branch-scoped + fail-soft (B4.5 Phase 3) | iterate | unit | +0 | 363/363 | PASS | 2026-06-11 |
| 61 | Tier-3 PR review via OpenRouter custom-script (B4.5 Phase 2): pr-review.yml workflow + pr_review.py reviewer + pr_reviewer prompts + 4 snapshot/unit test files | iterate | unit | +0 | 414/417 | PASS (3 skipped) | 2026-06-11 |
| 62 | Add gh-pr-ci:{pr_number} action-unit: failed hard-gates on open PRs land in triage (B4.5 automerge loop-closing). Differentiated auto-resolve; session-wide symmetry; draft exclusion; truncation + filter=latest guards. | iterate | — | +0 | — | — | 2026-06-11 |
| 63 | Fix the check_security_scan PreToolUse deploy-gate: it substring-matched the whole command, so a trigger keyword (deploy/jelastic/vercel/...) inside a quoted argument VALUE — an iterate-finalization --justification, a commit message, or an echo string — false-blocked unrelated commands. New _is_deploy_command strips quoted spans ("..." / '...') before matching; main() uses it. Real deploy commands/scripts/paths stay visible and still gate. | iterate | unit | +0 | 669/679 | PASS (10 skipped) | 2026-06-11 |
| 64 | Make campaign sub-iterate spec_path repo-relative POSIX instead of machine-absolute (N1, trg-196f4aa6, follow-up of campaign 2026-06-07-tracked-campaign-status): new pure campaign_paths.py (relativize_spec_path / campaign_spec_path); campaign_init writes relative; the projection self-heals on regenerate (carry + fill); one-off idempotent migration rewrote the 7 tracked campaigns (44 sub-paths). | iterate | unit | +0 | 3468/3488 | PASS (20 skipped) | 2026-06-11 |
| 65 | Campaign status backfill + docs (S4): parse_campaign_skeleton strips markdown emphasis from id/slug cells so a legacy campaign.md (bold **C1**) matches the plain committed status.json ids (else re-projection drops completed subs); a read-only drift-guard test verifies every tracked campaign regenerates without downgrade; docs landed (hooks-and-pipeline glob-churn note, glossary Campaign-Status + token-vocab SSoT, ADR). Closes campaign 2026-06-07-tracked-campaign-status. | iterate | unit | +0 | 3451/3471 | PASS (20 skipped) | 2026-06-10 |
| 66 | Bloat Stop-gate resolves a file's ceiling from the worktree baseline it measures, not main (trg-28e83840) | iterate | unit | +0 | 3088/3088 | PASS | 2026-06-10 |
| 67 | Per-tree campaign status.json: F5b finalize wiring + scoped churn resolver (campaign S3) | iterate | unit | +0 | 3442/3462 | PASS (20 skipped) | 2026-06-10 |
| 68 | Campaign status projection: pure regenerate_campaign_status producer + campaign_progress regenerate CLI project per-sub-iterate status.json from the campaign.md skeleton and self-identifying work_completed events, with a never-downgrade guard (campaign 2026-06-07-tracked-campaign-status S2). | iterate | unit | +0 | 3426/3445 | PASS (19 skipped) | 2026-06-10 |
| 69 | Exempt session_handoff.md + build_dashboard.md (with triage_inbox.md) from artifact-path-canon in all migrations; drift test; dismiss trg-6ed063ae. | iterate | — | +0 | — | — | 2026-06-10 |
| 70 | triage_cli list pins stdout to UTF-8: fixes UnicodeEncodeError on Windows consoles for non-cp1252 item titles (found by the webui pending-delivery-badge boundary probe). | iterate | — | +0 | — | — | 2026-06-10 |
| 71 | History-calibrated complexity prior + cross-domain scope vocabulary for the iterate Stage-1 classifier | iterate | — | +0 | — | — | 2026-06-10 |
| 72 | Gate D2V evidence markdown write behind SHIPWRIGHT_D2V_WRITE_EVIDENCE; default runs assert without writing the tracked artifact. | iterate | — | +0 | — | — | 2026-06-10 |
| 73 | Add triage_cli.py list --json (unioned open items + pendingDelivery) as a WebUI contract. | iterate | — | +0 | — | — | 2026-06-10 |
| 74 | Campaign sub-iterates self-identify: runner Step 4 + manual --campaign/--sub-iterate-id stamp campaign/sub_iterate_id into the work_completed event via F5b --event-extras-json | iterate | mixed | +0 | 3457/3458 | PASS (1 skipped) | 2026-06-10 |
| 75 | Triage dedup collapses same-id appends keep-last (reader parity); unblocks outbox sweep on producer update re-append. | iterate | — | +0 | — | — | 2026-06-09 |
| 76 | Iterate-scoped external-review markers gitignored (not blanket); 6 tracked copies untracked. | iterate | — | +0 | — | — | 2026-06-09 |
| 77 | Relocate detective-audit JSON from repo root to .shipwright/compliance/audit-report.json; canon re-excludes audit-report.{md,json} (propagates to adopted repos); drop obsolete framework root ignore. | iterate | — | +0 | — | — | 2026-06-09 |
| 78 | Relocate phase-quality skill-compliance roll-ups under the gitignored FINDING_DIR; resolve main_repo_root (not cwd) in the bloat marker writer+reader via a shared fail-soft resolver; defensive nested-locks gitignore canon. | iterate | — | +0 | — | — | 2026-06-08 |
| 79 | evt-ec8e9621 | iterate | — | +0 | — | — | 2026-06-08 |
| 80 | Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | iterate | unit | +6 | 6/6 | PASS | 2026-06-08 |
| 81 | evt-b9b5ddf2 | iterate | unit | +36 | 2954/2954 | PASS | 2026-06-08 |
| 82 | Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | iterate | unit | +22 | 2913/2913 | PASS | 2026-06-08 |
| 83 | scaffold the append-log merge=union .gitattributes driver into managed repos (adopt E.13c + iterate self-heal) | iterate | unit | +0 | 2884/2884 | PASS | 2026-06-07 |
| 84 | triage main-tree drift reconcile-and-commit at integrate/sync | iterate | mixed | +0 | 2861/2861 | PASS | 2026-06-07 |
| 85 | Track campaign status.json for compliance-detective-realign + track-triage-jsonl (durable per-sub board on fresh clone / deployed WebUI; stopgap for trg-fda5f7a3). | iterate | — | +0 | — | — | 2026-06-07 |
| 86 | allowlist cafebabe:deadbeef in oss_backend generated gitleaks config (GAP-3) | iterate | unit | +0 | 56/56 | PASS | 2026-06-07 |
| 87 | Harden iterate finalization tooling: F11 verifier accepts none_reason as a spec_impact=none justification; F0.5 surface_verification rejects compound runners fast with a clear error; arch-drift sanity test no longer false-FAILs on a post-release tree. | iterate | — | +0 | — | — | 2026-06-07 |
| 88 | SBOM distinguishes not-installed from no-declared-license; not-installed is silent (no triage, dash in sbom.md), only resolved-but-no-license is surfaced. | iterate | — | +0 | — | — | 2026-06-07 |
| 89 | Add campaign_init --expands-triage / --from-triage so a triage item can be promoted to a campaign anchor; writes expands_triage into both status.json and the campaign.md frontmatter so the Command Center shows 'Start Campaign' on that triage card. | iterate | — | +0 | — | — | 2026-06-07 |
| 90 | adopt scaffolds .gitleaks.toml + hardens security.yml.template | iterate | unit | +0 | 312/312 | PASS | 2026-06-07 |
| 91 | GC machine-churn complianceRefreshed compliance-backlog dismissals (add token to triage_gc.MACHINE_REASONS) | iterate | unit | +0 | 24/24 | PASS | 2026-06-07 |
| 92 | triage docs + monorepo migration (campaign 2026-06-05-track-triage-jsonl, sub-iterate E) | iterate | unit | +0 | 2839/2839 | PASS | 2026-06-07 |
| 93 | F5 architecture-drift detector switched from a git-history oracle (dead on gitignored drops) to content reconciliation (incl. convention); new canon/blocking F11 gate check_architecture_documented sharing one oracle (shared/scripts/lib/architecture_doc.py); dead check_architecture_reviewed + run_cross_artifact_checks removed; 5 orphan architecture.md entries back-filled. | iterate | — | +0 | — | — | 2026-06-06 |
| 94 | adopt skill docs: triage.jsonl is tracked, not gitignored (D) | iterate | unit | +0 | 24/24 | PASS | 2026-06-05 |
| 95 | SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift) | iterate | unit | +0 | 617/617 | PASS | 2026-06-05 |
| 96 | triage_gc tool: machine-churn-only dismissed-pile compaction | iterate | unit | +0 | 387/387 | PASS | 2026-06-05 |
| 97 | git-track triage.jsonl: gitignore negation + scaffolder self-heal (C1) | iterate | unit | +0 | 19/19 | PASS | 2026-06-05 |
| 98 | triage.jsonl merge-safety + leak-guard exemption (like events) — C2 | iterate | unit | +0 | 49/49 | PASS | 2026-06-05 |
| 99 | Propagate degraded scanner legs (fatal/empty/truncated) via a scan_errors side-channel so the threshold/report/CI-gate layers fail closed instead of treating a dead leg as a clean 0-findings scan. | iterate | — | +0 | — | — | 2026-06-05 |
| 100 | B7 Rule E: exclude non-functional Conventional-Commit types (build/chore/ci/docs/style/test) from B7 by default (configurable); functional types still flagged. Supersedes the narrow Rule D + kills the ci/docs/chore backfill treadmill. | iterate | unit | +0 | 44/44 | PASS | 2026-06-05 |
| 101 | Make the bloat marker recorder + Stop gate worktree-aware: strip the .worktrees/<slug>/ prefix for the baseline lookup so a worktree iterate growing an already-baselined file (ADR+bump) is not mis-classified crossing and does not false-block Stop (trg-305e2aab) | iterate | unit | +0 | 9/9 | PASS | 2026-06-05 |
| 102 | gitleaks --report-path - wrote a stray file named - instead of stdout, so the secrets leg silently returned 0 findings everywhere; report now written to a temp file and read back; smoke positive-control converted to ADR-044 CI-gated fail | iterate | unit | +0 | 320/320 | PASS | 2026-06-05 |
| 103 | Add A5.8: execute the deployed critical-gate shell against dual-artifact fixtures (flavor-agnostic across SARIF/findings.json; skip-safe; env kill-switch). | iterate | — | +0 | — | — | 2026-06-05 |
| 104 | Enforce the FR-gate on the finalize write-path + accept same-event D3 delivery | iterate | unit | +0 | 64/64 | PASS | 2026-06-05 |
| 105 | Set security.yml.template checkout to fetch-depth: 1 (working-tree only) and correct the misleading diff-aware-secret-scans comment; no scanner reads git history. | iterate | — | +0 | — | — | 2026-06-05 |
| 106 | C1/C2 detective-realign doc + ledger closeout | iterate | unit | +0 | 41/41 | PASS | 2026-06-05 |
| 107 | Scope the bloat recorder to the project root so cross-repo edits do not leak into this project marker and block its Stop gate. | iterate | — | +0 | — | — | 2026-06-04 |
| 108 | Fix the adopt security-gate so it resolves SARIF severity at rule level, blocks on any secret, and fails closed — previously a structural false green in every adopted repo. | iterate | — | +0 | — | — | 2026-06-04 |
| 109 | Add producer-owned campaign lifecycle status (draft->active->complete): campaign_init writes status:draft to status.json + campaign.md frontmatter; campaign_progress gains a start subcommand (->active), update-status auto-sets complete when all sub-iterates complete, summary prints the top-level status; the autonomous campaign loop marks the campaign active at run start; missing status = legacy fallback to done<total. | iterate | — | +0 | — | — | 2026-06-03 |
| 110 | Dedup SessionStart Phase-Quality injection to once-per-event via event_once.claim_once (fail-open). | iterate | — | +0 | — | — | 2026-06-02 |
| 111 | Rewrote test_upload_sarif_action_used to assert the real upload-sarif uses: line (anchored regex, version-agnostic) instead of matching a stale comment; corrected the two @v3 permission comments in security.yml to @v4. | iterate | — | +0 | — | — | 2026-06-01 |
| 112 | Pinned third-party GitHub Actions (setup-uv, create-or-update-comment) to commit SHAs; added SHA256 verification for the Gitleaks binary download in ci.yml + security.yml; corrected stale SECURITY.md scope (webui) and Dependabot wording. | iterate | — | +0 | — | — | 2026-06-01 |
| 113 | Detective audit honors event_amended corrections (group_d applies shared apply_amendments SSOT before D1-D5; new shared/scripts/lib/events_amend.py, re-exported by config.py); D4 disabled for the framework monorepo (gating-CI stale-noise); evt-5aca940d corrected to spec_impact=none. | iterate | — | +0 | — | — | 2026-06-01 |
| 114 | Document the gating ruff CI lint step in CLAUDE.md Development section. | iterate | — | +0 | — | — | 2026-06-01 |
| 115 | D5 honors change_type+none_reason exemption; add audit_config.disabled_checks applicability gate; framework repo disables A5.6/B7/D1/G2 | iterate | — | +0 | — | — | 2026-06-01 |
| 116 | plugin-sync Stop-hook triage item written to durable main-repo log (worktree-aware) | iterate | unit | +0 | 48/49 | PASS (1 skipped) | 2026-06-01 |
| 117 | CI gate-coverage guard + workflow hardening (test-dir coverage, loose-gate allowlist, security fail-closed) | iterate | unit | +0 | 2674/2675 | PASS (1 skipped) | 2026-05-31 |
| 118 | Gate CI Python lint on a curated bug-focused ruff ruleset (pyflakes F + high-signal E/W); remove the \|\| true + continue-on-error neutering; provision ruff via pinned uvx; rename job to Python (lint + test). | iterate | — | +0 | — | — | 2026-05-31 |
| 119 | Wire shared/ test suites (shared/tests, shared/scripts/tests, shared/scripts/tools/tests) into ci.yml as blocking per-dir invocations; fix 2 non-hermetic validate_env tests via a dir conftest; make the born-red arch-md sibling skip when gitignored decision-drops are absent. | iterate | — | +0 | — | — | 2026-05-31 |
| 120 | remove vestigial "\|\| true" from CI integration step (gate failures) + add pathlib.Path import to clear 14 F821 in test_events_log.py | iterate | unit | +0 | 2771/2771 | PASS | 2026-05-31 |
| 121 | events=union + churn-merge resolver/integrate_main: auto-reconcile generated artifacts on origin/main merge | iterate | — | +0 | — | — | 2026-06-01 |
| 122 | Collapse the compliance detective-audit mirror into one rolling compliance:backlog action-unit (auto-dismiss + refresh + legacy retirement) | iterate | — | +0 | — | — | 2026-05-31 |
| 123 | Render unengaged phases as SKIP (not FAIL) in the persisted finding JSON so the skill-compliance dashboard agrees with the triage inbox | iterate | — | +0 | — | — | 2026-05-31 |
| 124 | Collapse phase-quality Tier-1 FAIL triage into one rolling phaseQuality:backlog action-unit; add phase-applicability gate and run_id=unknown spec-check guard | iterate | — | +0 | — | — | 2026-05-31 |
| 125 | iterate completion: test-completeness-gate | iterate | — | +0 | — | — | 2026-05-30 |
| 126 | iterate complete: P3.1 reviewer stack (spec-reviewer + doubt-reviewer cascade) | iterate | — | +0 | — | — | 2026-05-30 |
| 127 | Propagate canonical .shipwright artifact-ignore block to consuming projects via SSoT template + idempotent merge in adopt/project + drift test | iterate | — | +0 | — | — | 2026-05-30 |
| 128 | Add audit_compliance_on_stop.py: auto-emit/auto-dismiss source=compliance triage items on every iterate/changelog Stop, gated on full A-G audit coverage. | iterate | — | +0 | — | — | 2026-05-30 |
| 129 | Align 7 stale record_event tests to the C.1 FR-gate (gates all iterates incl. bug/intentless); surface CI shared-test gap (trg-f363b1ab) | iterate | — | +0 | — | — | 2026-05-30 |
| 130 | RTM: untested (0/0) events neutral; status from latest tested event (fixes 7 false FAILs); neutralize leaked verification event via event_amended | iterate | — | +0 | — | — | 2026-05-30 |
| 131 | SP3+OS2 post-Campaign-B reintegration — F-debug.md systematic-debugging sub-skill + assumptions-first interview pre-phase | iterate | unit | +0 | 317/317 | PASS | 2026-05-29 |
| 132 | suggest_iterate UserPromptSubmit hook: emit hookEventName on hookSpecificOutput (+ AST meta-test) | iterate | unit | +0 | 2558/2558 | PASS | 2026-05-29 |
| 133 | Bloat marker keyed off stdin-payload session_id (not env) in check_file_size.py + bloat_gate_on_stop.py | iterate | unit | +0 | 2549/2550 | PASS (1 skipped) | 2026-05-29 |
| 134 | P4.1 Skill Bootstrap Pack: using-shipwright SessionStart bootstrap + writing-plugin/plugin-cache Stop wave (SP2+SP4) | iterate | unit | +0 | 2545/2545 | PASS | 2026-05-29 |
| 135 | events.jsonl per-tree, PR-committed artifact (worktree iterate audit-log fix) | iterate | unit | +0 | 2449/2450 | PASS (1 skipped) | 2026-05-29 |
| 136 | Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings) | iterate | unit | +0 | 2449/2449 | PASS | 2026-05-28 |
| 137 | Correction event: spec_impact=none with proper justification field for the verifier (supersedes evt-13153a5c). | iterate | — | +0 | — | — | 2026-05-27 |
| 138 | Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check | iterate | — | +0 | — | — | 2026-05-27 |
| 139 | Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT) | iterate | — | +0 | — | — | 2026-05-27 |
| 140 | Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d). | iterate | — | +0 | — | — | 2026-05-27 |
| 141 | Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass + audit_staleness coverage extension + merge-not-rebase doc convention. | iterate | — | +0 | — | — | 2026-05-27 |
| 142 | B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | iterate | unit | +26 | 1104/1104 | PASS | 2026-05-26 |
| 143 | Pre-commit anti-ratchet hook + bloat-check CI workflow + bloat-exception ADR template + shared glossary (Campaign A.defense, closes Campaign A defense-in-depth layer) | iterate | mixed | +0 | 41/41 | PASS | 2026-05-25 |
| 144 | fix bloat_gate_on_stop.py Stop-hook schema violation | iterate | unit | +0 | 131/131 | PASS | 2026-05-25 |
| 145 | Campaign A.review: bloat reviewer prompts (Karpathy+Osmani+Shipwright) + Group H detective audit (H0-H6) | iterate | mixed | +0 | 14/14 | PASS | 2026-05-25 |
| 146 | Phase 0 bloat baseline inventory — activates A.foundation Stop-Gate | iterate | — | +0 | — | — | 2026-05-25 |
| 147 | Bloat Loop-Gate (Campaign A.foundation = A1+A2+A3): runtime-prompt classification, per-session marker writer, blocking Stop-Gate, registered in every plugin | iterate | unit | +0 | 2678/2678 | PASS | 2026-05-25 |
| 148 | SBOM triage producer cluster-collapse | iterate | mixed | +0 | 514/514 | PASS | 2026-05-23 |
| 149 | SBOM resolver pin to per-manifest .venv METADATA | iterate | mixed | +0 | 497/497 | PASS | 2026-05-23 |
| 150 | Resolve architecture.md merge-conflict markers (lines 90-94) + extend ALLOWLIST[compliance] to include finalize_security_compliance.py whose cross-plugin path comment trips the hyphen-segment regex blind spot | iterate | unit | +0 | 2/3 | PASS (1 skipped) | 2026-05-23 |
| 151 | C1 design verifier (and sister manifest-exists check) skip on scope=library projects via _is_no_ui_scope helper; audit translates ok=None to status=skip via existing check_result_to_finding | iterate | unit | +0 | 19/19 | PASS | 2026-05-23 |
| 152 | iterate finalization | iterate | — | +0 | — | — | 2026-05-23 |
| 153 | Architecture-md drift protection test + 11 historical drift entries backfilled + 3 discipline learnings in conventions.md (TDD RED-first, F0/F11 leak-guard symmetry, F2 flag-md coupling) | iterate | unit | +0 | 2/2 | PASS | 2026-05-23 |
| 154 | F11 verifier multi-commit-aware via run_id lookup (fixes false positives on iterate-f7-tracked-event-log-commit) | iterate | unit | +0 | 70/70 | PASS | 2026-05-23 |
| 155 | iterate skill F7b: seals tracked event-log appends to prevent silent reset wipe (commit_event_followup.py + SKILL.md + 6 tests) | iterate | unit | +0 | 6/6 | PASS | 2026-05-22 |
| 156 | compliance reconciliation: D1 spec-FR coverage — multi-FR event covering FR-01.03/04/05/06/07/08/09/12 (post-2026-05-04 watermark gap; no source/test/spec changes) | iterate | — | +0 | — | — | 2026-05-22 |
| 157 | mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | iterate | — | +0 | — | — | 2026-05-22 |
| 158 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 159 | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | — | +0 | — | — | 2026-05-22 |
| 160 | Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | iterate | — | +0 | — | — | 2026-05-22 |
| 161 | deterministic render timestamps from max(event.ts) | iterate | unit | +34 | 34/34 | PASS | 2026-05-21 |
| 162 | empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | iterate | unit | +0 | 2621/2621 | PASS | 2026-05-21 |
| 163 | VERIFICATION: bug+change-type — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 164 | VERIFICATION artifact (amended: leaked from 2026-05-21 empirical-verification campaign; no real FR work) — neutralized by iterate-2026-05-30-rtm-covered-ignore-untested-events | iterate | — | +0 | — | — | 2026-05-21 |
| 165 | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 166 | Artifact-based GitHub security producer for Triage Inbox | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 167 | escape pipe and newline in markdown table cells | iterate | unit | +23 | 23/23 | PASS | 2026-05-20 |
| 168 | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | mixed | +0 | 3507/3507 | PASS | 2026-05-18 |
| 169 | triage detector dedup + auto-resolve (rebased onto #31) | iterate | mixed | +0 | 1776/1783 | PASS (7 skipped) | 2026-05-16 |
| 170 | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | unit | +0 | 140/140 | PASS | 2026-05-16 |
| 171 | triage detector dedup + auto-resolve | iterate | mixed | +0 | 1776/1783 | PASS (7 skipped) | 2026-05-16 |
| 172 | fix adopt external-review config defaults | iterate | mixed | +0 | 304/304 | PASS | 2026-05-16 |
| 173 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | mixed | +0 | 2519/2526 | PASS (7 skipped) | 2026-05-16 |
| 174 | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | mixed | +0 | 312/312 | PASS | 2026-05-15 |
| 175 | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | mixed | +0 | 40/40 | PASS | 2026-05-14 |
| 176 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | unit | +0 | 1642/1649 | PASS (7 skipped) | 2026-05-11 |
| 177 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | unit | +0 | 1642/1649 | PASS (7 skipped) | 2026-05-11 |
| 178 | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | unit | +0 | 16/16 | PASS | 2026-05-09 |
| 179 | evt-f66286bf | iterate | — | +0 | — | — | 2026-05-07 |
| 180 | evt-623a29ad | iterate | — | +0 | — | — | 2026-05-07 |
| 181 | F0.5 empirical-test backfill | iterate | unit | +0 | 1575/1575 | PASS | 2026-05-06 |
| 182 | F0.5 End-to-End Verification Gate | iterate | unit | +0 | 1548/1548 | PASS | 2026-05-06 |
| 183 | hooks-consistency parser handles quoted commands — 27/27 green | iterate | unit | +0 | 1297/1297 | PASS | 2026-05-06 |
| 184 | post-migration canon cleanup — 9 tests green | iterate | unit | +0 | 1270/1270 | PASS | 2026-05-06 |
| 185 | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | unit | +0 | 34/34 | PASS | 2026-05-05 |
| 186 | verifier accepts drop-dir entries + dashboard short-SHAs | iterate | unit | +0 | 32/32 | PASS | 2026-05-05 |
| 187 | adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | unit | +0 | 241/241 | PASS | 2026-05-05 |
| 188 | FR-table parser accepts 5-col adopt format + drift protection | iterate | unit | +0 | 1594/1628 | PASS (34 skipped) | 2026-05-05 |
| 189 | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | unit | +0 | 12/12 | PASS | 2026-05-05 |
| 190 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | unit | +0 | 1691/1716 | PASS (25 skipped) | 2026-05-05 |
| 191 | F runner contract mandates reviews (ADR-029) | iterate | unit | +0 | 188/188 | PASS | 2026-05-04 |
| 192 | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | unit | +0 | 1539/1539 | PASS | 2026-05-04 |
| 193 | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | unit | +19 | 19/19 | PASS | 2026-05-03 |
| 194 | changelog MSYS path-mangling linter | iterate | unit | +0 | 19/19 | PASS | 2026-05-03 |
| 195 | hooks.json quoting (deferred from ADR-020) | iterate | unit | +0 | 13/13 | PASS | 2026-05-03 |
| 196 | iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | unit | +0 | 53/53 | PASS | 2026-05-03 |
| 197 | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | unit | +0 | 47/47 | PASS | 2026-05-03 |
| 198 | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | unit | +0 | 249/249 | PASS | 2026-05-03 |
| 199 | fix hook_installer Shape A -> B | iterate | unit | +0 | 5/5 | PASS | 2026-05-03 |
| 200 | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | unit | +0 | 233/233 | PASS | 2026-05-02 |
| 201 | post-adoption framework cleanup (Sub-1A through 1D) | iterate | unit | +0 | 225/225 | PASS | 2026-05-02 |

## Full Suite Runs

| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |
|-----|---------|------|-------------|-------|-----|-------|------|
| 1 | iterate | 3284/3284 | — | — | — | — | 2026-06-12 |
| 2 | iterate | 3289/3289 | — | — | — | — | 2026-06-12 |
| 3 | iterate | 697/697 | — | — | — | — | 2026-06-12 |
| 4 | iterate | 3348/3362 | — | — | — | — | 2026-06-12 |
| 5 | iterate | 162/162 | — | — | — | — | 2026-06-13 |
| 6 | iterate | 3818/3830 | — | — | — | — | 2026-06-13 |
| 7 | iterate | 3737/3737 | — | — | — | — | 2026-06-13 |
| 8 | iterate | 3400/3400 | — | — | — | — | 2026-06-13 |
| 9 | iterate | 3796/3796 | — | — | — | — | 2026-06-13 |
| 10 | iterate | 4343/4343 | — | — | — | — | 2026-06-13 |
| 11 | iterate | 4283/4283 | — | — | — | — | 2026-06-13 |
| 12 | iterate | 164/164 | — | — | — | — | 2026-06-13 |
| 13 | iterate | 4220/4236 | — | — | — | — | 2026-06-13 |
| 14 | iterate | 4082/4082 | — | — | — | — | 2026-06-13 |
| 15 | iterate | 3419/3419 | — | — | — | — | 2026-06-13 |
| 16 | iterate | 3996/3996 | — | — | — | — | 2026-06-13 |
| 17 | iterate | 3653/3665 | — | — | — | — | 2026-06-13 |
| 18 | iterate | 69/69 | — | — | — | — | 2026-06-13 |
| 19 | iterate | 3881/3881 | — | — | — | — | 2026-06-13 |
| 20 | iterate | 3441/3453 | — | — | — | — | 2026-06-13 |
| 21 | iterate | 3442/3442 | — | — | — | — | 2026-06-13 |
| 22 | iterate | 7/7 | — | — | — | — | 2026-06-14 |
| 23 | iterate | 96/96 | — | — | — | — | 2026-06-14 |
| 24 | iterate | 3473/3473 | — | — | — | — | 2026-06-14 |
| 25 | iterate | 94/94 | — | — | — | — | 2026-06-15 |
| 26 | iterate | 85/85 | — | — | — | — | 2026-06-16 |
| 27 | iterate | 24/24 | — | — | — | — | 2026-06-16 |
| 28 | iterate | 701/701 | — | — | — | — | 2026-06-16 |
| 29 | iterate | 28/29 | — | — | — | — | 2026-06-17 |
| 30 | iterate | 20/20 | — | — | — | — | 2026-06-17 |

## Code Review Evidence

| Event | Review Type | Findings | Fixed | Status |
|-------|------------|----------|-------|--------|
| B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor | external-iterate-review | 12 | 12 | PASS |
| Add .shipwright/triage.outbox.jsonl gitignored buffer; route 3 background producers via should_route_to_outbox; two-pass ts-primary union reader; tracked-only GC. ADR-100 bloat exception. | external-plan+external-code | 18 | 18 | PASS |
| evt-b9b5ddf2 | external-plan+code | 16 | 4 | OPEN |
| Real non-mocked empirical harness over the real D2 code + real git: 200 thread + 40 cross-process concurrency trials (multiset zero-loss/zero-dup), abandoned-branch e2e, exactly-once after a real merge, no main pollution; pytest_sessionfinish fails a partial gate. GATE PASS (all 5 methods). | plan+code | 20 | 8 | OPEN |

