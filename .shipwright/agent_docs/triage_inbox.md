# Triage Inbox

> Auto-generated 2026-06-28T06:18:50.409295Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 232
- Triage: 1 | Promoted: 1 | Dismissed: 229 | Snoozed: 1

## Top 1 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-9cb3ffa7"></a>
- **Compliance: 2 open finding(s)** `id=trg-9cb3ffa7 | severity=high | kind=compliance → P1/compliance`
  - 2 open compliance finding(s): D/D1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must: FR-01.01, FR-01.02…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 2 open compliance finding(s): D/D1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-9cb3ffa7 --task-ref EXT:<ref>`

