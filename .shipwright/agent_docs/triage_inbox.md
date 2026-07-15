# Triage Inbox

> Auto-generated 2026-07-15T13:09:54.465587Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 298
- Triage: 4 | Promoted: 1 | Dismissed: 292 | Snoozed: 1

## Top 4 items (severity-sorted)

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

### Source: operator (1 item)

<a id="trg-b3296282"></a>
- **Admit ci-security.json to the churn CHURN_ALLOWLIST (ensure_current aborts on it)** `id=trg-b3296282 | severity=low | kind=improvement → P3/engineering`
  - CHURN_ALLOWLIST (shared/scripts/lib/churn_merge.py = DERIVED_MDS \| events/test_results/triage) omits .shipwright/compl…
  - Promote: `triage_promote.py --id trg-b3296282 --task-ref EXT:<ref>`

