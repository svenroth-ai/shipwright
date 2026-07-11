# Triage Inbox

> Auto-generated 2026-07-11T03:31:16.405620Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 284
- Triage: 5 | Promoted: 1 | Dismissed: 277 | Snoozed: 1

## Top 5 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-d263a2bc"></a>
- **Compliance: 2 open finding(s)** `id=trg-d263a2bc | severity=medium | kind=compliance → P2/compliance`
  - 2 open compliance finding(s): G/G3, H/H2  - G/G3: Commit-body ADR refs exist in decision_log.md — 16b1da88 → ADR-310; 1…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 2 open compliance finding(s): G/G3, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-d263a2bc --task-ref EXT:<ref>`

### Source: iterate-B1-review-nit (1 item)

<a id="trg-14d6ba20"></a>
- **Per-split phase-duration accuracy: multi-split pipeline phases (build/plan) undercount in the tracked log** `id=trg-14d6ba20 | severity=low | kind=improvement → P3/engineering`
  - B1 emits N phase_started (one per split phase_task, not deduped) but record_event dedups phase_completed by phase (firs…
  - Promote: `triage_promote.py --id trg-14d6ba20 --task-ref EXT:<ref>`

### Source: iterate-B1-scope-deferral (1 item)

<a id="trg-8efeb3d7"></a>
- **M-Pre-1 iterate half: per-phase phase_started for the iterate F-phases (WebUI Iterate-Rail)** `id=trg-8efeb3d7 | severity=low | kind=improvement → P3/engineering`
  - B1 emitted phase_started + paired phase_completed for the 7 PIPELINE phases (both run modes). The iterate flow (F0-F12)…
  - Promote: `triage_promote.py --id trg-8efeb3d7 --task-ref EXT:<ref>`

### Source: manual (2 items)

<a id="trg-0e8e7f90"></a>
- **Remove the deprecated multi-session pipeline engine (single-session is now the sole mode)** `id=trg-0e8e7f90 | severity=low | kind=improvement → P3/engineering`
  - Decision 2026-07-08 (Sven): single-session is the sole pipeline mode; multi-session no longer needed (one user, no back…
  - Promote: `triage_promote.py --id trg-0e8e7f90 --task-ref EXT:<ref>`

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

