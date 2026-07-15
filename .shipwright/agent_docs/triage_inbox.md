# Triage Inbox

> Auto-generated 2026-07-15T19:39:08.832620Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 303
- Triage: 7 | Promoted: 1 | Dismissed: 294 | Snoozed: 1

## Top 7 items (severity-sorted)

### Source: campaign-anchor (3 items)

<a id="trg-9a782f7b"></a>
- **Trace-Campaign: requirement to test traceability across layers (unit/integration/E2E), autonomous** `id=trg-9a782f7b | severity=medium | kind=improvement → P2/engineering`
  - Main autonomous campaign 2026-07-15-test-traceability-layers (TT1..TT8). Runs after Trace-Prerequisite merges. Adds bid…
  - Promote: `triage_promote.py --id trg-9a782f7b --task-ref EXT:<ref>`

<a id="trg-f41043ec"></a>
- **Trace-Prerequisite: freeze contracts + build traceability test-harness (unlocks the autonomous campaign)** `id=trg-f41043ec | severity=medium | kind=improvement → P2/engineering`
  - Autonomous prerequisite iterate P1, independently adversarially panel-verified (Codex + GPT + Gemini). Freezes manifest…
  - Promote: `triage_promote.py --id trg-f41043ec --task-ref EXT:<ref>`

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

