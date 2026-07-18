# Triage Inbox

> Auto-generated 2026-07-18T17:04:27.470053Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 329
- Triage: 8 | Promoted: 1 | Dismissed: 319 | Snoozed: 1

## Top 8 items (severity-sorted)

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

### Source: iterate (2 items)

<a id="trg-a20314c2"></a>
- **shipwright-webui: triage status writer must guarantee a trailing newline before appending** `id=trg-a20314c2 | severity=medium | kind=bug → P2/engineering`
  - The monorepo append boundary now guarantees the log ends with a newline before appending, and the reader recovers recor…
  - Promote: `triage_promote.py --id trg-a20314c2 --task-ref EXT:<ref>`

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

### Source: operator (3 items)

<a id="trg-94337862"></a>
- **REQ-1 - Iterate: requirements test harness (golden corpus) - run AFTER REQ-0, BEFORE REQ-2** `id=trg-94337862 | severity=high | kind=improvement → P1/engineering`
  - SECOND of three. Order: REQ-0 (FR existence gate) -> REQ-1 (this) -> REQ-2 (campaign trg-1b764b2c). This is the safety…
  - Promote: `triage_promote.py --id trg-94337862 --task-ref EXT:<ref>`

<a id="trg-946756d2"></a>
- **Triage outbox: missing trailing newline concatenates two records, silently dropping one** `id=trg-946756d2 | severity=high | kind=bug → P1/engineering`
  - A record in the triage outbox was written without a trailing newline, so the next writer appended onto the same physica…
  - Promote: `triage_promote.py --id trg-946756d2 --task-ref EXT:<ref>`

<a id="trg-1b764b2c"></a>
- **REQ-2 - Campaign: requirements catalog (S2-S8) - run AFTER REQ-1** `id=trg-1b764b2c | severity=medium | kind=improvement → P2/engineering`
  - THIRD of three. Order: REQ-0 (FR existence gate) -> REQ-1 (test harness) -> REQ-2 (this campaign). Do NOT start before…
  - Promote: `triage_promote.py --id trg-1b764b2c --task-ref EXT:<ref>`

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

