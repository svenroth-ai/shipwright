# Triage Inbox

> Auto-generated 2026-07-16T10:09:06.401339Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 305
- Triage: 8 | Promoted: 1 | Dismissed: 295 | Snoozed: 1

## Top 8 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

### Source: campaign-anchor (2 items)

<a id="trg-9a782f7b"></a>
- **Trace-Campaign: requirement to test traceability across layers (unit/integration/E2E), autonomous** `id=trg-9a782f7b | severity=medium | kind=improvement → P2/engineering`
  - Main autonomous campaign 2026-07-15-test-traceability-layers (TT1..TT8). Runs after Trace-Prerequisite merges. Adds bid…
  - Promote: `triage_promote.py --id trg-9a782f7b --task-ref EXT:<ref>`

<a id="trg-17aaaccd"></a>
- **Trace-Webui: retrofit traceability in the webui repo (handoff, run after monorepo campaign ships)** `id=trg-17aaaccd | severity=low | kind=improvement → P3/engineering`
  - Handoff reminder: the webui retrofit is a separate single iterate that runs IN the webui repo from webui's own triage,…
  - Promote: `triage_promote.py --id trg-17aaaccd --task-ref EXT:<ref>`

### Source: code-review (1 item)

<a id="trg-ac428050"></a>
- **Harden regenerate_tracked_snapshots to stage ci-security.json on a fresh-scan rewrite (forward parity with the rollback…** `id=trg-ac428050 | severity=low | kind=improvement → P3/engineering`
  - Pre-existing (independent of #375): regenerate_tracked_snapshots stages only its out set (derived MDs + agent MDs + cam…
  - Promote: `triage_promote.py --id trg-ac428050 --task-ref EXT:<ref>`

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

<a id="trg-c3f016c2"></a>
- **GitHub security: 1 shipwright-security finding(s) (medium)** `id=trg-c3f016c2 | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: (unavailable) \| dependabot: (unavailable) \| shipwright-security: 1 medi…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security CI workflow reports 1 open finding(s) for svenroth-ai/shipwright (GHAS Code Scanning is not configured).
    Severity breakdown — shipwright-security: 1 medium.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/29476710363
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-c3f016c2 --task-ref EXT:<ref>`

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

