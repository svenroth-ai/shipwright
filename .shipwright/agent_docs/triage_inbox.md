# Triage Inbox

> Auto-generated 2026-06-11T11:21:32.265008Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 173
- Triage: 16 | Promoted: 1 | Dismissed: 156 | Snoozed: 0

## Top 16 items (severity-sorted)

### Source: architecture (2 items)

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

<a id="trg-537334f1"></a>
- **Align bloat marker WRITER (check_file_size) to worktree baseline — delta label still main-keyed (harmless after the trg…** `id=trg-537334f1 | severity=low | kind=improvement → P3/engineering`
  - Follow-up to trg-28e83840 (Stop-gate reader fix). The recorder check_file_size.py computes the marker delta (anti-ratch…
  - Promote: `triage_promote.py --id trg-537334f1 --task-ref EXT:<ref>`

### Source: automerge-b45 (5 items)

<a id="trg-bdc160e2"></a>
- **B4.5 Phase 3 — F11 Patch (gh pr merge --auto)** `id=trg-bdc160e2 | severity=high | kind=feature → P1/engineering`
  - Iterate-Plugin F11 patcht so dass nach `gh pr create` automatisch `gh pr merge --auto --squash --delete-branch` aufgeru…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Brief: Patch iterate F11 to arm auto-merge on Iterate-PRs. Spec: Spec/early-access-readiness-plan.md → B4.5 → Implementation Order → Phase 3.
    
    Files to touch:
    - plugins/shipwright-iterate/skills/iterate/references/F11.md: nach `gh pr create ...` zusätzlich `gh pr merge "$PR_URL" --auto --squash --delete-branch` aufrufen
    - plugins/shipwright-iterate/skills/iterate/SKILL.md: F11-Phase-Index-Zeile erweitern (Z. 290 in der aktuellen Datei)
    - ggf. Tests in plugins/shipwright-iterate/tests/
    
    Constraint (defensiv):
    - `gh pr merge --auto` NUR aufrufen wenn Branch-Name mit `iterate/` startet — manuelle Sven-PRs sollen sich NICHT selbst arm-mergen (Opt-in pro PR via manuellem `gh pr merge --auto` oder Label `automerge`)
    - Precedent: plugins/shipwright-changelog/skills/release/SKILL.md macht `gh pr merge --merge --delete-branch` in autonomous mode (andere Semantik — `--merge` statt `--squash`, kein `--auto`, aber ähnlicher Pattern)
    
    Complexity hint: trivial-small
    ```
  - Promote: `triage_promote.py --id trg-bdc160e2 --task-ref EXT:<ref>`

<a id="trg-52cd3143"></a>
- **B4.5 Phase 2 — pr_review.py Custom-Script + Workflow (OpenRouter)** `id=trg-52cd3143 | severity=high | kind=feature → P1/engineering`
  - Tier-3-PR-Review via OpenRouter + Custom-Script. Iterate-PRs (Tier 1) und Sven's manuelle PRs (Tier 2) bekommen KEINE A…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Brief: Implement tiered PR-Review via OpenRouter + Custom-Script. Spec: Spec/early-access-readiness-plan.md → B4.5 → Components.
    
    Files to create:
    - shared/prompts/pr_reviewer/system/ + user/ (Verzeichnis-Form analog zu code_reviewer/, iterate_reviewer/ — etabliert seit PR #119)
    - plugins/shipwright-security/scripts/tools/pr_review.py (~120-150 LOC):
      * fetch PR diff via `gh pr diff`
      * POST to https://openrouter.ai/api/v1/chat/completions mit model $SHIPWRIGHT_PR_REVIEW_MODEL (default anthropic/claude-sonnet-4.6)
      * strict JSON response: {decision: approve|comment|block, summary, blocking[], comments[]}
      * post via `gh pr comment` + optional `gh pr review --request-changes|--comment`
      * exit 0 für approve/comment, 1 für block, 2 für errors
      * Diff > 200k chars: defensiv truncaten + im Body vermerken
    - .github/workflows/pr-review.yml: zwei Jobs (decide + review) mit Tier-Filtern
      * decide: external author? sensitive path? labels (skip-pr-review/needs-review)?
      * review: needs: decide, if needs.decide.outputs.needs_review == 'true'
      * Job-Name `PR Review` (Branch-Protection-Required-Check)
      * Fork-PR-Guard: head.repo.full_name == github.repository
    - plugins/shipwright-security/tests/test_pr_review_workflow_shape.py + test_pr_review_script.py
    
    Smoke-Tests vor merge (Spec → Phase 2 Steps 5-6):
    1. Test-PR aus svroch Account (Tier 2) → review-Job skipped, Required-Check trotzdem grün
    2. Test-PR mit Änderung in plugins/*/hooks/ → Tier 3, Script reviewt, postet Comment, Exit-Code matched Decision
    
    Complexity hint: small-medium
    ```
  - Promote: `triage_promote.py --id trg-52cd3143 --task-ref EXT:<ref>`

<a id="trg-52f1fecb"></a>
- **B4.5 Phase 1 — gh-pr-ci Producer (Loop-Closing für Automerge)** `id=trg-52f1fecb | severity=high | kind=feature → P1/engineering`
  - Loop-Closing für Automerge: failed Hard-Gates auf OFFENEN PRs landen ins Triage. Heute fängt der github_triage-Producer…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Brief: Add gh-pr-ci action-unit producer to capture failed Hard-Gates on open PRs (Automerge loop-closing). Spec: Spec/early-access-readiness-plan.md → B4.5 → Loop-Closing.
    
    Files to touch (github_triage is now a 7-file package since PR #98):
    - shared/scripts/github_api.py: add fetch_open_prs() and fetch_pr_check_runs(head_sha), both returning list[dict] | None (None on any failure, same semantics as existing fetches)
    - shared/scripts/github_triage/producer.py: add PREFIX_PR_CI = 'gh-pr-ci:' and append it to _OWNED_PREFIXES (currently 4 entries: SECURITY, SECRETS, CI, PROMPT — PR-CI becomes 5th)
    - shared/scripts/github_triage/mappers.py: add pr_ci_action_unit(pr_info, *, owner_repo) (analog zu ci_action_unit) + open_prs_with_failed_checks(prs) reducer
    - shared/scripts/github_triage/consumer.py: wire new fetch + emit + auto-resolve into import_findings()
    - docs/triage-inbox.md: 5. action-unit row in der Tabelle
    - shared/tests/test_github_triage_*.py: tests analog zu existierenden
    
    Constraints (kritisch):
    - Dedup key gh-pr-ci:{pr_number} (KEIN head_sha, KEIN workflow_id — Operator-Action ist 'fix PR #N')
    - launchPayload startet mit '/shipwright-iterate --type bug' + PR-URL
    - Emit/resolve symmetry (Code-Review-MED-#1 aus iterate-2026-05-20): wenn IRGENDEIN per-PR-checkrun-Fetch None war, sperre den ganzen resolve-sweep für gh-pr-ci dieser Session
    - Auto-resolve reasons: prClosed, prMerged, prChecksResolved
    
    Complexity hint: medium (touches shared infra)
    ```
  - Promote: `triage_promote.py --id trg-52f1fecb --task-ref EXT:<ref>`

<a id="trg-c2a700a7"></a>
- **B4.5-W WebUI — Align PR Review Architecture (OpenRouter + tiered, drop develop)** `id=trg-c2a700a7 | severity=medium | kind=feature → P2/engineering`
  - Aktuell hat shipwright-webui ein claude-review.yml das (a) anthropics direct via @anthropic-ai/claude-code npm package…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Brief: Align shipwright-webui PR-Review architecture with monorepo B4.5 Phase 2 — replace claude-review.yml (anthropics-direct, always-on) with pr-review.yml (OpenRouter, tiered).
    
    RUN THIS AGAINST shipwright-webui repo, NOT shipwright monorepo.
    
    Files to touch in WebUI repo:
    - .github/workflows/claude-review.yml: DELETE (replaced by pr-review.yml)
    - .github/workflows/pr-review.yml: NEW, ported from monorepo B4.5 Phase 2 pattern:
      * Job-Name 'PR Review' (Branch-Protection-Required-Check match)
      * Two-Job-Struktur: decide (Tier-Filter) + review (gated)
      * Fork-PR-Guard: head.repo.full_name == github.repository
      * Tier 3 trigger: external author (NOT 'svroch' / 'dependabot[bot]') OR sensitive paths (client/**, server/**, .github/workflows/**) OR label 'needs-review'
      * Skip override: label 'skip-pr-review'
      * Trigger: branches: [main] only (NOT [main, develop] — develop existiert nicht)
    - scripts/pr_review.py: NEW, WebUI-side adaption (~120-150 LOC):
      * Same JSON contract, same exit-code semantics als monorepo
      * OpenRouter call via $OPENROUTER_API_KEY
      * Default model 'anthropic/claude-sonnet-4.6' via $SHIPWRIGHT_PR_REVIEW_MODEL
      * tsx + node available on ubuntu-latest runner — script kann pure-Python sein
    - prompts/pr_reviewer/system/ + user/: NEW, WebUI-spezifische Heuristiken (Vite + Hono Stack, React-Components, Server-Routes, RLS, etc.) — analog zur monorepo system/user Verzeichnis-Form (PR #119 Pattern)
    - Tests in tests/: pr_review_workflow_shape.test.ts + pr_review_script.test.ts (vitest)
    
    Smoke-Tests vor merge:
    1. Test-PR aus svroch Account (Tier 2) → review-Job skipped, Required-Check trotzdem grün
    2. Test-PR mit Änderung in client/components/ → Tier 3 (sensitive path), Script reviewt
    
    Nach merge (manuelle Sven-Aktion):
    - OPENROUTER_API_KEY als Repo-Secret in shipwright-webui (separate Spend-Limit!)
    - Branch Protection neu setzen mit 6 Required Checks:
        * Client (type + lint + test)
        * Server (type + lint + test)
        * Shipwright Security Scan
        * Analyze (javascript-typescript)
        * Anti-ratchet + allowlist diff
        * PR Review (NEW, ersetzt 'Claude Code Review')
    - KEIN develop Branch in Protection target (existiert nicht, war dead config)
    - Allow auto-merge wie monorepo
    
    Constraint (defensiv):
    - ANTHROPIC_API_KEY Secret im WebUI nach Migration NICHT löschen sofort — falls rollback gewünscht, ist es eine 1-Zeilen-Git-Revert. Erst nach 1-2 erfolgreichen Tier-3-Reviews löschen.
    
    Complexity hint: small-medium (Port + Adapt, kein neues Architektur-Design)
    ```
  - Promote: `triage_promote.py --id trg-c2a700a7 --task-ref EXT:<ref>`

<a id="trg-a678bd00"></a>
- **B4.6 Adopt — Automerge-Readiness Pack** `id=trg-a678bd00 | severity=medium | kind=feature → P2/engineering`
  - Adopt scaffoldet heute ci.yml + security.yml + claude-review.yml + .gitleaks.toml, aber KEIN codeql.yml + KEIN bloat-ch…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Brief: Extend /shipwright-adopt to scaffold full automerge-readiness pack for brownfield repos. Spec: Spec/early-access-readiness-plan.md → B4.5 Loop-Closing → Adopt-Erweiterung.
    
    Files to create:
    - shared/templates/github-actions/codeql.yml.template: Matrix-Sprache parametrisierbar nach detektiertem Stack (Python → 'python', JS/TS → 'javascript-typescript', mixed → matrix). Adopt Step E parametrisiert basierend auf Profile-Detection (B-Step).
    - shared/templates/github-actions/bloat-check.yml.template: analog zur monorepo Version, aber opt-in (Adopt-Frage 'enable anti-ratchet bloat discipline?'). Skip-default für Repos die das nicht wollen.
    - shared/templates/AUTOMERGE_SETUP.md.template: profile-aware Doc die nach Adopt im Repo landet. Listet die TATSÄCHLICH scaffoldedten Required-Check-Job-Namen (parametrisiert!) + Schritt-für-Schritt Branch-Protection-UI-Anleitung + 'Allow auto-merge' Setting + `gh pr merge --auto --squash` Default-Pattern
    
    Adopt SKILL.md anpassen:
    - Step E erweitern um codeql + bloat-check + AUTOMERGE_SETUP.md scaffolding
    - Step C Interview optional erweitern: 'Enable anti-ratchet bloat-check?' (default no, weil non-Shipwright Repos meist keine bloat-baseline.json haben)
    - references/artifact-templates.md: 3 neue Template-Slots dokumentieren
    
    Out of scope für dieses Iterate:
    - Automatische Branch-Protection-Config via gh api — DOC-only bleibt, weil User-Settings nicht ungefragt geändert werden sollen
    - WebUI claude-review.yml.template Migration auf OpenRouter — separates Iterate falls Sven Provider-Konsistenz möchte
    
    Constraint (defensiv):
    - Profile-Detection MUSS die Required-Check-Namen korrekt parametrisieren — falsche Job-Namen in AUTOMERGE_SETUP.md führen zu Branch-Protection-Configs die nie greifen (silent broken). Tests: pytest gegen sample-adopted-projects mit allen 3 Profilen.
    
    Complexity hint: medium (touches adopt + 3 new templates + test surface)
    ```
  - Promote: `triage_promote.py --id trg-a678bd00 --task-ref EXT:<ref>`

### Source: external-frameworks (6 items)

<a id="trg-db3e0a9c"></a>
- **[P5.1] WebUI Quick Wins: optimistic mutations + self-hosting tier docs** `id=trg-db3e0a9c | severity=medium | kind=improvement → P2/engineering`
  - \## Intent  Bundle P5.1 from Spec/external-frameworks-integration.md (MU4 + MU6). Two small WebUI wins: (a) optimistic…
  - Promote: `triage_promote.py --id trg-db3e0a9c --task-ref EXT:<ref>`

<a id="trg-6289f9a6"></a>
- **[P3.2] Code-Simplify Skill (standalone, behavior-preserving)** `id=trg-6289f9a6 | severity=medium | kind=feature → P2/engineering`
  - \## Intent  P3.2 (OS1) from Spec/external-frameworks-integration.md. Standalone Code-Simplify Skill that runs behavior-…
  - Promote: `triage_promote.py --id trg-6289f9a6 --task-ref EXT:<ref>`

<a id="trg-dfca97e9"></a>
- **[P7.1] Plugin Boundary Hardening: import-boundary + Pydantic configs** `id=trg-dfca97e9 | severity=low | kind=improvement → P3/engineering`
  - \## Intent  Bundle P7.1 from Spec/external-frameworks-integration.md (MU-PL2 + MU-PL3). Two hardening patterns: (a) AST…
  - Promote: `triage_promote.py --id trg-dfca97e9 --task-ref EXT:<ref>`

<a id="trg-41f0c3ab"></a>
- **[P6.2] WebUI: Multi-Workspace isolation** `id=trg-41f0c3ab | severity=low | kind=feature → P3/engineering`
  - \## Intent  P6.2 (MU2) from Spec/external-frameworks-integration.md. Multi-Workspace layer: organize Shipwright project…
  - Promote: `triage_promote.py --id trg-41f0c3ab --task-ref EXT:<ref>`

<a id="trg-c1b41dae"></a>
- **[P6.1] WebUI: WebSocket streaming for iterate progress** `id=trg-c1b41dae | severity=low | kind=feature → P3/engineering`
  - \## Intent  P6.1 (MU1) from Spec/external-frameworks-integration.md. New /api/ws/iterate/<projectId> endpoint that stre…
  - Promote: `triage_promote.py --id trg-c1b41dae --task-ref EXT:<ref>`

<a id="trg-aecf9cde"></a>
- **[P8.1] Architecture Research Sprint: internal-packages + daemon + skills-lock** `id=trg-aecf9cde | severity=low | kind=maintenance → P3/engineering`
  - \## Intent  Bundle P8.1 from Spec/external-frameworks-integration.md (MU5 + MU7 + MU-PL1). Single research iterate prod…
  - Promote: `triage_promote.py --id trg-aecf9cde --task-ref EXT:<ref>`

### Source: manual (3 items)

<a id="trg-9b9a2b9d"></a>
- **Audit bug-fixes - final batch, run last (docs/SSoT + low-risk hardening)** `id=trg-9b9a2b9d | severity=medium | kind=improvement → P2/engineering`
  - Launch surface only. The work plan + details live in the LOCAL, gitignored campaign dir (not in git). Start via the Sta…
  - Promote: `triage_promote.py --id trg-9b9a2b9d --task-ref EXT:<ref>`

<a id="trg-32ef7005"></a>
- **Audit bug-fixes - manual batch, run one-by-one (hook contracts + run-config concurrency)** `id=trg-32ef7005 | severity=medium | kind=improvement → P2/engineering`
  - Launch surface only. The work plan + details live in the LOCAL, gitignored campaign dir (not in git). Start via the Sta…
  - Promote: `triage_promote.py --id trg-32ef7005 --task-ref EXT:<ref>`

<a id="trg-d7661cfb"></a>
- **Audit bug-fixes - auto batch (encoding/Windows, compliance gates, triage tooling, installer)** `id=trg-d7661cfb | severity=medium | kind=improvement → P2/engineering`
  - Launch surface only. The work plan + details live in the LOCAL, gitignored campaign dir (not in git). Start via the Sta…
  - Promote: `triage_promote.py --id trg-d7661cfb --task-ref EXT:<ref>`

