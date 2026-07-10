# Triage Inbox

> Auto-generated 2026-07-10T09:34:20.841627Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 278
- Triage: 4 | Promoted: 1 | Dismissed: 272 | Snoozed: 1

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

### Source: manual (2 items)

<a id="trg-0e8e7f90"></a>
- **Remove the deprecated multi-session pipeline engine (single-session is now the sole mode)** `id=trg-0e8e7f90 | severity=low | kind=improvement → P3/engineering`
  - Decision 2026-07-08 (Sven): single-session is the sole pipeline mode; multi-session no longer needed (one user, no back…
  - Promote: `triage_promote.py --id trg-0e8e7f90 --task-ref EXT:<ref>`

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

### Source: operator (1 item)

<a id="trg-3a4c6a3d"></a>
- **CLAUDE.md content ungoverned: agents inline full ADR rationale instead of a terse index** `id=trg-3a4c6a3d | severity=low | kind=improvement → P3/engineering`
  - agent_doc_budget.py (600 chars/entry) governs architecture.md + conventions.md entries but NOT CLAUDE.md; claude-md-tem…
  - Promote: `triage_promote.py --id trg-3a4c6a3d --task-ref EXT:<ref>`

