# Triage Inbox

> Auto-generated 2026-06-12T08:48:05.654486Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 179
- Triage: 14 | Promoted: 1 | Dismissed: 164 | Snoozed: 0

## Top 14 items (severity-sorted)

### Source: architecture (2 items)

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

<a id="trg-537334f1"></a>
- **Align bloat marker WRITER (check_file_size) to worktree baseline — delta label still main-keyed (harmless after the trg…** `id=trg-537334f1 | severity=low | kind=improvement → P3/engineering`
  - Follow-up to trg-28e83840 (Stop-gate reader fix). The recorder check_file_size.py computes the marker delta (anti-ratch…
  - Promote: `triage_promote.py --id trg-537334f1 --task-ref EXT:<ref>`

### Source: automerge-b45 (1 item)

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

### Source: compliance (1 item)

<a id="trg-671bb0a2"></a>
- **Compliance: 9 open finding(s)** `id=trg-671bb0a2 | severity=medium | kind=compliance → P2/compliance`
  - 9 open compliance finding(s): E/E1, E/E2, E/E3, E/E4, E/E5, E/E?, E/E?, E/E?, F/F5  - E/E1: RTM stale (regen vs snapsho…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 9 open compliance finding(s): E/E1, E/E2, E/E3, E/E4, E/E5, E/E?, E/E?, E/E?, F/F5.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-671bb0a2 --task-ref EXT:<ref>`

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

### Source: manual (4 items)

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

<a id="trg-7580f4fe"></a>
- **Emit a tracked terminal campaign-completion event so consumers can auto-hide finished campaigns** `id=trg-7580f4fe | severity=low | kind=improvement → P3/engineering`
  - The tracked shipwright_events.jsonl carries only per-sub-iterate 'work_completed' events (top-level campaign + sub_iter…
  - Promote: `triage_promote.py --id trg-7580f4fe --task-ref EXT:<ref>`

