# Triage Inbox

> Auto-generated 2026-06-27T21:14:40.530729Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 232
- Triage: 1 | Promoted: 1 | Dismissed: 229 | Snoozed: 1

## Top 1 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-41380374"></a>
- **Compliance: 1 open finding(s)** `id=trg-41380374 | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — plugins/shipwright-c…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-41380374 --task-ref EXT:<ref>`

