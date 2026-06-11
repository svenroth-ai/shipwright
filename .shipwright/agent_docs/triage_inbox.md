# Triage Inbox

> Auto-generated 2026-06-11T05:22:31.903130Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 165
- Triage: 15 | Promoted: 1 | Dismissed: 149 | Snoozed: 0

## Top 15 items (severity-sorted)

### Source: architecture (3 items)

<a id="trg-28e83840"></a>
- **Bloat Stop-gate reads MAIN baseline while re-measuring the WORKTREE file — false-block on a worktree iterate that bumps…** `id=trg-28e83840 | severity=medium | kind=bug → P2/engineering`
  - Reproduced 2026-06-10 in PR #184. trg-305e2aab was dismissed as FIXED in #150, but #150 fixed only the PATH-prefix half…
  - Promote: `triage_promote.py --id trg-28e83840 --task-ref EXT:<ref>`

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

<a id="trg-537334f1"></a>
- **Align bloat marker WRITER (check_file_size) to worktree baseline — delta label still main-keyed (harmless after the trg…** `id=trg-537334f1 | severity=low | kind=improvement → P3/engineering`
  - Follow-up to trg-28e83840 (Stop-gate reader fix). The recorder check_file_size.py computes the marker delta (anti-ratch…
  - Promote: `triage_promote.py --id trg-537334f1 --task-ref EXT:<ref>`

### Source: deep-audit (3 items)

<a id="trg-d689be5b"></a>
- **Audit 2 - Manual: deep-audit pipeline / concurrency / hook-contract fixes - 3 sub-iterates (run one-by-one with review)** `id=trg-d689be5b | severity=high | kind=bug → P1/engineering`
  - Campaign 2026-06-10-audit-2-manual: WP1 phase-hook-lifecycle (the v2 multi-session pipeline is silently dead), WP2 runc…
  - Evidence: `Spec/audits/2026-06-10-deep-audit.md`
  - Promote: `triage_promote.py --id trg-d689be5b --task-ref EXT:<ref>`

<a id="trg-346793e1"></a>
- **Audit 1 - Auto: deep-audit mechanical fixes (utf8, compliance gates, triage tooling, installer) - 7 sub-iterates** `id=trg-346793e1 | severity=high | kind=bug → P1/engineering`
  - Autonomous campaign 2026-06-10-audit-1-auto (independent branches): WP3 compliance-gates, WP5 hook-resolvers, WP6/7/8 u…
  - Evidence: `Spec/audits/2026-06-10-deep-audit.md`
  - Promote: `triage_promote.py --id trg-346793e1 --task-ref EXT:<ref>`

<a id="trg-1f94f285"></a>
- **Audit 3 - Final: deep-audit docs/SSoT reconcile + low-risk hardening - 2 sub-iterates (run last)** `id=trg-1f94f285 | severity=medium | kind=improvement → P2/engineering`
  - Campaign 2026-06-10-audit-3-final: WP11a docs/SSoT (the hooks.json Format doc section is inverted), WP11b low-risk hard…
  - Evidence: `Spec/audits/2026-06-10-deep-audit.md`
  - Promote: `triage_promote.py --id trg-1f94f285 --task-ref EXT:<ref>`

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

### Source: iterate (1 item)

<a id="trg-196f4aa6"></a>
- **Campaign status projection writes machine-absolute spec_path (non-portable)** `id=trg-196f4aa6 | severity=medium | kind=improvement → P2/engineering`
  - campaign_status projection + campaign_init fill a sub-iterate spec_path as an ABSOLUTE campaign_dir path, so a regenera…
  - Promote: `triage_promote.py --id trg-196f4aa6 --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-e2a0ebb3"></a>
- **Triage live-view: union the gitignored outbox so new items are visible/startable before sweep** `id=trg-e2a0ebb3 | severity=medium | kind=improvement → P2/engineering`
  - UX gap: a freshly-created triage item (manual triage_add or an idle-main background producer) routes to the gitignored…
  - Promote: `triage_promote.py --id trg-e2a0ebb3 --task-ref EXT:<ref>`

### Source: plugin-sync (1 item)

<a id="trg-9f3afc54"></a>
- **Plugin cache may be out of sync after plugin-side edits** `id=trg-9f3afc54 | severity=low | kind=maintenance → P3/engineering`
  - Plugin-side files were edited but the runtime plugin cache may not be re-synced. Run `bash scripts/update-marketplace.s…
  - Promote: `triage_promote.py --id trg-9f3afc54 --task-ref EXT:<ref>`

