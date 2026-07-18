# Triage Inbox

> Auto-generated 2026-07-18T22:18:16.354557Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 335
- Triage: 7 | Promoted: 1 | Dismissed: 326 | Snoozed: 1

## Top 7 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-ebe6705b"></a>
- **Compliance: 5 open finding(s)** `id=trg-ebe6705b | severity=high | kind=compliance → P1/compliance`
  - 5 open compliance finding(s): D/D1, D/D3, F/F5, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must:…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 5 open compliance finding(s): D/D1, D/D3, F/F5, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-ebe6705b --task-ref EXT:<ref>`

### Source: iterate (1 item)

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

### Source: operator (2 items)

<a id="trg-94337862"></a>
- **REQ-1 - Iterate: requirements test harness (golden corpus) - run AFTER REQ-0, BEFORE REQ-2** `id=trg-94337862 | severity=high | kind=improvement → P1/engineering`
  - SECOND of three. Order: REQ-0 (FR existence gate) -> REQ-1 (this) -> REQ-2 (campaign trg-1b764b2c). This is the safety…
  - Promote: `triage_promote.py --id trg-94337862 --task-ref EXT:<ref>`

<a id="trg-1b764b2c"></a>
- **REQ-2 - Campaign: requirements catalog (S2-S8) - run AFTER REQ-1** `id=trg-1b764b2c | severity=medium | kind=improvement → P2/engineering`
  - THIRD of three. Order: REQ-0 (FR existence gate) -> REQ-1 (test harness) -> REQ-2 (this campaign). Do NOT start before…
  - Promote: `triage_promote.py --id trg-1b764b2c --task-ref EXT:<ref>`

### Source: securityReview (2 items)

<a id="trg-13b8283b"></a>
- **CI-Security 1b/2: converge an acceptance onto code-scanning + triage (GAP 2, root cause of #285)** `id=trg-13b8283b | severity=medium | kind=improvement → P2/engineering`
  - CI-Security 1b of 2. Phase 2 of the split out of trg-15a8e267 (CI-Security 1/2, which delivers the scanner-agnostic acc…
  - Promote: `triage_promote.py --id trg-13b8283b --task-ref EXT:<ref>`

<a id="trg-0ce59c05"></a>
- **CI-Security 2/2: ship the action-pinning posture RULE to adopters (templates already correct)** `id=trg-0ce59c05 | severity=low | kind=improvement → P3/engineering`
  - CI-Security 2 of 2. This is what is LEFT of item 1 in anchor trg-9509c2e8 after verification - most of it turned out to…
  - Promote: `triage_promote.py --id trg-0ce59c05 --task-ref EXT:<ref>`

