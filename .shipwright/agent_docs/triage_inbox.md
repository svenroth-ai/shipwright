# Triage Inbox

> Auto-generated 2026-07-18T09:03:28.926965Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 320
- Triage: 7 | Promoted: 1 | Dismissed: 311 | Snoozed: 1

## Top 7 items (severity-sorted)

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

### Source: github (1 item)

<a id="trg-eb2d15ea"></a>
- **GitHub security: 1 shipwright-security finding(s) (medium)** `id=trg-eb2d15ea | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: (unavailable) \| dependabot: (unavailable) \| shipwright-security: 1 medi…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security CI workflow reports 1 open finding(s) for svenroth-ai/shipwright (GHAS Code Scanning is not configured).
    Severity breakdown — shipwright-security: 1 medium.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/29619381657
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-eb2d15ea --task-ref EXT:<ref>`

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

### Source: webui-spec-audit (1 item)

<a id="trg-f7d38388"></a>
- **Adopt: mint capability-level FRs (route grouping + Area) and unify the greenfield/brownfield spec-table shape** `id=trg-f7d38388 | severity=medium | kind=improvement → P2/engineering`
  - Deferred remainder of trg-8e840ca0 / trg-44d23d63, split out of iterate-2026-07-18-fr-authoring-rules (which delivered…
  - Promote: `triage_promote.py --id trg-f7d38388 --task-ref EXT:<ref>`

### Source: webui-traceability-handoff (1 item)

<a id="trg-0c14afe6"></a>
- **Fold-aware traceability: resolve @covers folded FR IDs via FR-Fold-Map before orphan-flagging** `id=trg-0c14afe6 | severity=medium | kind=improvement → P2/engineering`
  - The test_links collector, D-orphan (_group_d_traceability) and backfill_scan read only survivor FR-table rows and do NO…
  - Promote: `triage_promote.py --id trg-0c14afe6 --task-ref EXT:<ref>`

