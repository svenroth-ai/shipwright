# Triage Inbox

> Auto-generated 2026-07-17T22:03:26.464116Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 316
- Triage: 6 | Promoted: 1 | Dismissed: 308 | Snoozed: 1

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

### Source: traceability-followup (1 item)

<a id="trg-6b4b6a33"></a>
- **STEP 2: Test-rot cleanup - triage 50 skipped/.only tests (quarantine-with-expiry or delete)** `id=trg-6b4b6a33 | severity=medium | kind=maintenance → P2/engineering`
  - ORDERED STEP 2 (independent of STEP 1; can run any time). === FIX-NOW: if run as an iterate, YOU (the agent) are the re…
  - Promote: `triage_promote.py --id trg-6b4b6a33 --task-ref EXT:<ref>`

### Source: webui-spec-audit (1 item)

<a id="trg-8e840ca0"></a>
- **FR taxonomy: capability-altitude FR minting (adopt) + Mint-vs-Fold gate (iterate) + FR-hygiene lint (compliance)** `id=trg-8e840ca0 | severity=medium | kind=improvement → P2/engineering`
  - Root cause of badly-scoped, wrongly-numbered FRs in adopted specs: two FR-minting engines with incompatible philosophy.…
  - Promote: `triage_promote.py --id trg-8e840ca0 --task-ref EXT:<ref>`

