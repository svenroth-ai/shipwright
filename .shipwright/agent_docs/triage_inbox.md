# Triage Inbox

> Auto-generated 2026-07-15T05:48:50.010334Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 297
- Triage: 5 | Promoted: 1 | Dismissed: 290 | Snoozed: 1

## Top 5 items (severity-sorted)

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

### Source: iterate (3 items)

<a id="trg-f6ceeb37"></a>
- **Iterate 2: bundle F1-F5c finalization into fewer LLM round-trips** `id=trg-f6ceeb37 | severity=low | kind=improvement → P3/engineering`
  - Iterate-duration campaign, part 2 of 3 (part 1 = F0 parallel runner, DELIVERED #371). The finalize phase is ~4.1 min in…
  - Promote: `triage_promote.py --id trg-f6ceeb37 --task-ref EXT:<ref>`

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

<a id="trg-11196d99"></a>
- **shipwright-test suite leaks tests/fixtures/.shipwright/ into the working tree** `id=trg-11196d99 | severity=low | kind=improvement → P3/engineering`
  - Pre-existing test-hygiene leak, NOT caused by the F0 parallel runner: running 'pytest tests/' in plugins/shipwright-tes…
  - Promote: `triage_promote.py --id trg-11196d99 --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

