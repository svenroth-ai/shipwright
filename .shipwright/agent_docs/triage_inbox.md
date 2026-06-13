# Triage Inbox

> Auto-generated 2026-06-13T16:03:19.756877Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 217
- Triage: 3 | Promoted: 1 | Dismissed: 212 | Snoozed: 1

## Top 3 items (severity-sorted)

### Source: architecture (1 item)

<a id="trg-721b1765"></a>
- **Hook fan-out across plugins — collapse to phase-aware dispatchers (Start+Stop+Prompt+PostTool; PreToolUse separate) [ca…** `id=trg-721b1765 | severity=medium | kind=improvement → P2/engineering`
  - [SCOPE EXPANDED 2026-06-02 -> campaign .shipwright/planning/iterate/campaigns/2026-06-02-hook-consolidation/; this item…
  - Promote: `triage_promote.py --id trg-721b1765 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-a906e79b"></a>
- **Compliance: 1 open finding(s)** `id=trg-a906e79b | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — shared/tests/test_ev…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-a906e79b --task-ref EXT:<ref>`

### Source: reducibility-review (1 item)

<a id="trg-6529b9fd"></a>
- **Consolidate duplicated shared infrastructure helpers (file-lock, read_events, git wrappers)** `id=trg-6529b9fd | severity=low | kind=improvement → P3/engineering`
  - Reducibility-catalog D-findings in shared/scripts: _FileLock duplicated in record_event.py + triage.py; read_events dup…
  - Promote: `triage_promote.py --id trg-6529b9fd --task-ref EXT:<ref>`

