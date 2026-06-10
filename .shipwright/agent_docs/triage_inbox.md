# Triage Inbox

> Auto-generated 2026-06-10T08:00:55.145129Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 153
- Triage: 11 | Promoted: 1 | Dismissed: 141 | Snoozed: 0

## Top 11 items (severity-sorted)

### Source: architecture (2 items)

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

<a id="trg-fda5f7a3"></a>
- **Durable producer-maintained campaign status (tracked SSoT)** `id=trg-fda5f7a3 | severity=low | kind=improvement → P3/engineering`
  - WebUI reads per-sub campaign status from status.json, which is authoritative per the campaign-store.ts contract + PR #1…
  - Evidence: `.shipwright/planning/iterate/proposed-tracked-campaign-status.md`
  - Promote: `triage_promote.py --id trg-fda5f7a3 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-a315f60c"></a>
- **Compliance: 1 open finding(s)** `id=trg-a315f60c | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): F/F5  - F/F5: Architecture marker vs arch-impact drops — 1 arch-impact drop(s) not docume…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): F/F5.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-a315f60c --task-ref EXT:<ref>`

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

### Source: manual (2 items)

<a id="trg-e2a0ebb3"></a>
- **Triage live-view: union the gitignored outbox so new items are visible/startable before sweep** `id=trg-e2a0ebb3 | severity=medium | kind=improvement → P2/engineering`
  - UX gap: a freshly-created triage item (manual triage_add or an idle-main background producer) routes to the gitignored…
  - Promote: `triage_promote.py --id trg-e2a0ebb3 --task-ref EXT:<ref>`

<a id="trg-6ed063ae"></a>
- **artifact-path-canon: exempt generated triage_inbox.md cache from legacy-path lint** `id=trg-6ed063ae | severity=low | kind=improvement → P3/engineering`
  - The artifact-path-canon Layer-1 lint (test_no_legacy_artifact_paths) scans tracked .md/.py for bare legacy artifact-dir…
  - Promote: `triage_promote.py --id trg-6ed063ae --task-ref EXT:<ref>`

