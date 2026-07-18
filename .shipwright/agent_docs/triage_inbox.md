# Triage Inbox

> Auto-generated 2026-07-18T16:54:04.466947Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 327
- Triage: 10 | Promoted: 1 | Dismissed: 315 | Snoozed: 1

## Top 10 items (severity-sorted)

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

### Source: operator (5 items)

<a id="trg-94337862"></a>
- **REQ-1 - Iterate: requirements test harness (golden corpus) - run AFTER REQ-0, BEFORE REQ-2** `id=trg-94337862 | severity=high | kind=improvement → P1/engineering`
  - SECOND of three. Order: REQ-0 (FR existence gate) -> REQ-1 (this) -> REQ-2 (campaign trg-1b764b2c). This is the safety…
  - Promote: `triage_promote.py --id trg-94337862 --task-ref EXT:<ref>`

<a id="trg-946756d2"></a>
- **Triage outbox: missing trailing newline concatenates two records, silently dropping one** `id=trg-946756d2 | severity=high | kind=bug → P1/engineering`
  - A record in the triage outbox was written without a trailing newline, so the next writer appended onto the same physica…
  - Promote: `triage_promote.py --id trg-946756d2 --task-ref EXT:<ref>`

<a id="trg-8deb2213"></a>
- **FR gate accepts requirement ids that do not exist (false green)** `id=trg-8deb2213 | severity=high | kind=bug → P1/engineering`
  - The finalization FR gate validates only that the declared requirement list is non-empty. is_non_empty_fr_list checks th…
  - Promote: `triage_promote.py --id trg-8deb2213 --task-ref EXT:<ref>`

<a id="trg-1b764b2c"></a>
- **REQ-2 - Campaign: requirements catalog (S2-S8) - run AFTER REQ-1** `id=trg-1b764b2c | severity=medium | kind=improvement → P2/engineering`
  - THIRD of three. Order: REQ-0 (FR existence gate) -> REQ-1 (test harness) -> REQ-2 (this campaign). Do NOT start before…
  - Promote: `triage_promote.py --id trg-1b764b2c --task-ref EXT:<ref>`

<a id="trg-16d79da2"></a>
- **Requirements Catalog campaign: one catalog, one table shape, one discovery path** `id=trg-16d79da2 | severity=medium | kind=improvement → P2/engineering`
  - Umbrella anchor for the Requirements-Catalog campaign (S0-S8). Full spec + evidence + risk register: Spec/design/2026-0…
  - Promote: `triage_promote.py --id trg-16d79da2 --task-ref EXT:<ref>`

### Source: securityReview (1 item)

<a id="trg-9509c2e8"></a>
- **CI supply-chain guardrails + make an accepted risk actually stick (from webui #285 revert)** `id=trg-9509c2e8 | severity=medium | kind=improvement → P2/engineering`
  - webui iterate-2026-07-18-unpin-actions-no-dependabot reverted PR #285 (SHA-pinned all first-party GitHub Actions + adde…
  - Launch payload (copy into a new Claude session):
    ```text
    Framework follow-up to webui iterate-2026-07-18-unpin-actions-no-dependabot.
    Start with item 3 (touches_ci_supplychain in classify_complexity.RISK_TAXONOMY) -
    smallest diff, and it is the guard that would have caught #285. Then item 2
    (acceptance must converge triage AND code-scanning), then item 1 (strip hosted
    services from the shipped CI template), then item 4 (scanner-agnostic accepted-risk
    register). Leave item 5 unless the others land cheaply. Read the webui ADR first so
    this does not re-decide the posture - it is already decided and recorded.
    ```
  - Promote: `triage_promote.py --id trg-9509c2e8 --task-ref EXT:<ref>`

