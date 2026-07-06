# Triage Inbox

> Auto-generated 2026-07-06T20:44:43.547322Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 271
- Triage: 4 | Promoted: 1 | Dismissed: 265 | Snoozed: 1

## Top 4 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-c99d9547"></a>
- **Compliance: 1 open finding(s)** `id=trg-c99d9547 | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — plugins/shipwright-c…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-c99d9547 --task-ref EXT:<ref>`

### Source: grader-campaign (1 item)

<a id="trg-e68e9901"></a>
- **Build shipwright-grade: repo-agnostic Control Grade grader (lead magnet)** `id=trg-e68e9901 | severity=high | kind=improvement → P1/engineering`
  - New standalone read-only plugin that grades ANY git repo (incl. non-Shipwright) with the same Control Grade rubric by p…
  - Promote: `triage_promote.py --id trg-e68e9901 --task-ref EXT:<ref>`

### Source: manual (2 items)

<a id="trg-9beb9669"></a>
- **shipwright-grade G6: calibrate cold-repo projection heuristics (real repos mis-grade F, ordering inverted)** `id=trg-9beb9669 | severity=high | kind=improvement → P1/engineering`
  - G5's empirical launch gate is RED: the cold-repo projector mis-grades well-run repos. Evidence (5 real repos): pallets/…
  - Evidence: `plugins/shipwright-grade/tests/empirical/CALIBRATION.md`
  - Promote: `triage_promote.py --id trg-9beb9669 --task-ref EXT:<ref>`

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

