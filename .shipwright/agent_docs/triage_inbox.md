# Triage Inbox

> Auto-generated 2026-06-28T20:55:31.664132Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 233
- Triage: 1 | Promoted: 1 | Dismissed: 230 | Snoozed: 1

## Top 1 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-d08194ed"></a>
- **Compliance: 4 open finding(s)** `id=trg-d08194ed | severity=medium | kind=compliance → P2/compliance`
  - 4 open compliance finding(s): E/E3, E/E4, E/E5, H/H2  - E/E3: Change-history stale — first diff at line 3; line delta +…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 4 open compliance finding(s): E/E3, E/E4, E/E5, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-d08194ed --task-ref EXT:<ref>`

