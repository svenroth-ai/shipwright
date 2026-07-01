# Triage Inbox

> Auto-generated 2026-06-30T20:26:19.491004Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 236
- Triage: 3 | Promoted: 1 | Dismissed: 231 | Snoozed: 1

## Top 3 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-362ab7e0"></a>
- **Compliance: 2 open finding(s)** `id=trg-362ab7e0 | severity=medium | kind=compliance → P2/compliance`
  - 2 open compliance finding(s): E/E?, H/H2  - E/E?: session_handoff — first diff at line 1; line delta -13; snapshot 459b…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 2 open compliance finding(s): E/E?, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-362ab7e0 --task-ref EXT:<ref>`

### Source: scorecard-followup (2 items)

<a id="trg-317a84ab"></a>
- **Tighten GitHub Actions workflow token permissions** `id=trg-317a84ab | severity=high | kind=improvement → P1/engineering`
  - Workflows request broader GITHUB_TOKEN scopes than needed (OpenSSF Scorecard Token-Permissions = 0). Declare a minimal…
  - Promote: `triage_promote.py --id trg-317a84ab --task-ref EXT:<ref>`

<a id="trg-287b194b"></a>
- **Supply-chain hardening: pin Actions by SHA + review branch protection** `id=trg-287b194b | severity=medium | kind=improvement → P2/engineering`
  - OpenSSF Scorecard flagged Pinned-Dependencies (Actions not pinned by hash) and Branch-Protection (not maximal). Pin Git…
  - Promote: `triage_promote.py --id trg-287b194b --task-ref EXT:<ref>`

