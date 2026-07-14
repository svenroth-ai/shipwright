# Triage Inbox

> Auto-generated 2026-07-14T20:13:46.958736Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 291
- Triage: 3 | Promoted: 1 | Dismissed: 286 | Snoozed: 1

## Top 3 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-869dc3fd"></a>
- **Compliance: 3 open finding(s)** `id=trg-869dc3fd | severity=high | kind=compliance → P1/compliance`
  - 3 open compliance finding(s): D/D1, D/D3, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must: FR-01.15 \|…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 3 open compliance finding(s): D/D1, D/D3, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-869dc3fd --task-ref EXT:<ref>`

### Source: manual (2 items)

<a id="trg-0e8e7f90"></a>
- **Remove the deprecated multi-session pipeline engine (single-session is now the sole mode)** `id=trg-0e8e7f90 | severity=low | kind=improvement → P3/engineering`
  - Decision 2026-07-08 (Sven): single-session is the sole pipeline mode; multi-session no longer needed (one user, no back…
  - Promote: `triage_promote.py --id trg-0e8e7f90 --task-ref EXT:<ref>`

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

