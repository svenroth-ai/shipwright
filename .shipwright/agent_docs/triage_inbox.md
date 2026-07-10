# Triage Inbox

> Auto-generated 2026-07-10T06:39:25.542491Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 277
- Triage: 4 | Promoted: 1 | Dismissed: 271 | Snoozed: 1

## Top 4 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-b7b361da"></a>
- **Compliance: 1 open finding(s)** `id=trg-b7b361da | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — plugins/shipwright-c…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-b7b361da --task-ref EXT:<ref>`

### Source: manual (3 items)

<a id="trg-0e8e7f90"></a>
- **Remove the deprecated multi-session pipeline engine (single-session is now the sole mode)** `id=trg-0e8e7f90 | severity=low | kind=improvement → P3/engineering`
  - Decision 2026-07-08 (Sven): single-session is the sole pipeline mode; multi-session no longer needed (one user, no back…
  - Promote: `triage_promote.py --id trg-0e8e7f90 --task-ref EXT:<ref>`

<a id="trg-ff0b2049"></a>
- **WebUI single-session design-review mockup loop (convergence S5)** `id=trg-ff0b2049 | severity=low | kind=improvement → P3/engineering`
  - Single-session design human-gate loop (convergence spec S5). In single_session the design gate is orchestrator-approve…
  - Promote: `triage_promote.py --id trg-ff0b2049 --task-ref EXT:<ref>`

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

