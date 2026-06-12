# Triage Inbox

> Auto-generated 2026-06-12T11:39:05.501518Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 177
- Triage: 13 | Promoted: 1 | Dismissed: 163 | Snoozed: 0

## Top 13 items (severity-sorted)

### Source: architecture (2 items)

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

<a id="trg-537334f1"></a>
- **Align bloat marker WRITER (check_file_size) to worktree baseline — delta label still main-keyed (harmless after the trg…** `id=trg-537334f1 | severity=low | kind=improvement → P3/engineering`
  - Follow-up to trg-28e83840 (Stop-gate reader fix). The recorder check_file_size.py computes the marker delta (anti-ratch…
  - Promote: `triage_promote.py --id trg-537334f1 --task-ref EXT:<ref>`

### Source: automerge-b45 (2 items)

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

