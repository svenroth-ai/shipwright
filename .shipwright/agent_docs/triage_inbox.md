# Triage Inbox

> Auto-generated 2026-07-14T22:44:30.319245Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 295
- Triage: 5 | Promoted: 1 | Dismissed: 288 | Snoozed: 1

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

### Source: iterate (2 items)

<a id="trg-de6e736c"></a>
- **Phase skills detect invocation mode from the unmaintained v1 current_step, so a driven phase can wrongly conclude stand…** `id=trg-de6e736c | severity=medium | kind=bug → P2/engineering`
  - The 8 phase skills classify "pipeline vs standalone" in their First-Actions step C ("Detect Invocation Mode") by readin…
  - Promote: `triage_promote.py --id trg-de6e736c --task-ref EXT:<ref>`

<a id="trg-11196d99"></a>
- **shipwright-test suite leaks tests/fixtures/.shipwright/ into the working tree** `id=trg-11196d99 | severity=low | kind=improvement → P3/engineering`
  - Pre-existing test-hygiene leak, NOT caused by the F0 parallel runner: running 'pytest tests/' in plugins/shipwright-tes…
  - Promote: `triage_promote.py --id trg-11196d99 --task-ref EXT:<ref>`

### Source: manual (2 items)

<a id="trg-0e8e7f90"></a>
- **Remove the deprecated multi-session pipeline engine (single-session is now the sole mode)** `id=trg-0e8e7f90 | severity=low | kind=improvement → P3/engineering`
  - Decision 2026-07-08 (Sven): single-session is the sole pipeline mode; multi-session no longer needed (one user, no back…
  - Promote: `triage_promote.py --id trg-0e8e7f90 --task-ref EXT:<ref>`

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

