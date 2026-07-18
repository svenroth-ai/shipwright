# Triage Inbox

> Auto-generated 2026-07-17T22:46:16.286789Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 317
- Triage: 6 | Promoted: 1 | Dismissed: 309 | Snoozed: 1

## Top 6 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-4a615381"></a>
- **Compliance: 4 open finding(s)** `id=trg-4a615381 | severity=high | kind=compliance → P1/compliance`
  - 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must: FR-01.…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-4a615381 --task-ref EXT:<ref>`

### Source: iterate (1 item)

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

### Source: webui-spec-audit (2 items)

<a id="trg-44d23d63"></a>
- **FR descriptions must be plain business language (adopt/project/iterate prompt rule)** `id=trg-44d23d63 | severity=medium | kind=improvement → P2/engineering`
  - Atomic business requirement: whenever the framework generates or updates a Functional Requirement, its description is p…
  - Promote: `triage_promote.py --id trg-44d23d63 --task-ref EXT:<ref>`

<a id="trg-8e840ca0"></a>
- **FR taxonomy: capability-altitude FR minting (adopt) + Mint-vs-Fold gate (iterate) + FR-hygiene lint (compliance)** `id=trg-8e840ca0 | severity=medium | kind=improvement → P2/engineering`
  - Root cause of badly-scoped, wrongly-numbered FRs in adopted specs: two FR-minting engines with incompatible philosophy.…
  - Promote: `triage_promote.py --id trg-8e840ca0 --task-ref EXT:<ref>`

