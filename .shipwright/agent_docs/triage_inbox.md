# Triage Inbox

> Auto-generated 2026-06-13T16:28:23.007465Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 219
- Triage: 2 | Promoted: 1 | Dismissed: 215 | Snoozed: 1

## Top 2 items (severity-sorted)

### Source: architecture (1 item)

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-ec8891e8"></a>
- **Compliance: 8 open finding(s)** `id=trg-ec8891e8 | severity=medium | kind=compliance → P2/compliance`
  - 8 open compliance finding(s): E/E1, E/E2, E/E3, E/E5, E/E?, E/E?, E/E?, H/H2  - E/E1: RTM stale (regen vs snapshot) — f…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 8 open compliance finding(s): E/E1, E/E2, E/E3, E/E5, E/E?, E/E?, E/E?, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-ec8891e8 --task-ref EXT:<ref>`

