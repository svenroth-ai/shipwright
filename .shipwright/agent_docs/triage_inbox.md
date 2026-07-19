# Triage Inbox

> Auto-generated 2026-07-18T23:19:00.375648Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 341
- Triage: 9 | Promoted: 1 | Dismissed: 330 | Snoozed: 1

## Top 9 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-ebe6705b"></a>
- **Compliance: 5 open finding(s)** `id=trg-ebe6705b | severity=high | kind=compliance → P1/compliance`
  - 5 open compliance finding(s): D/D1, D/D3, F/F5, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must:…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 5 open compliance finding(s): D/D1, D/D3, F/F5, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-ebe6705b --task-ref EXT:<ref>`

### Source: github (1 item)

<a id="trg-daa00ce3"></a>
- **GitHub security: 2 code-scanning + 0 Dependabot (medium)** `id=trg-daa00ce3 | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: 2 medium \| dependabot: 0 \| see https://github.com/svenroth-ai/shipwrigh…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: GitHub reports 2 open code-scanning finding(s) and 0 open Dependabot alert(s) for svenroth-ai/shipwright.
    Severity breakdown — code-scanning: 2 medium; dependabot: 0.
    Live state: https://github.com/svenroth-ai/shipwright/security
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-daa00ce3 --task-ref EXT:<ref>`

### Source: iterate (2 items)

<a id="trg-360e494f"></a>
- **Event-log readers: remaining sites still parse one record per physical line** `id=trg-360e494f | severity=medium | kind=improvement → P2/engineering`
  - iterate-2026-07-19-events-record-boundary-readers converted 11 read sites to the shared record-boundary SSoT (lib/jsonl…
  - Promote: `triage_promote.py --id trg-360e494f --task-ref EXT:<ref>`

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

### Source: iterate-2026-07-18-requirements-golden-corpus (2 items)

<a id="trg-183a304a"></a>
- **Flaky idempotency test: dashboard render compared across a minute boundary** `id=trg-183a304a | severity=medium | kind=bug → P2/engineering`
  - shared/tests/test_finalize_iterate.py::test_run_is_idempotent compares two generated dashboard renders for byte equalit…
  - Promote: `triage_promote.py --id trg-183a304a --task-ref EXT:<ref>`

<a id="trg-9532fa83"></a>
- **Three requirements-parser defects frozen by S1, fixed by campaign step S4** `id=trg-9532fa83 | severity=medium | kind=improvement → P2/engineering`
  - Three defects in the requirements table parsers, found while building the S1 golden corpus (campaign Requirements Catal…
  - Promote: `triage_promote.py --id trg-9532fa83 --task-ref EXT:<ref>`

### Source: operator (1 item)

<a id="trg-1b764b2c"></a>
- **REQ-2 - Campaign: requirements catalog (S2-S8) - run AFTER REQ-1** `id=trg-1b764b2c | severity=medium | kind=improvement → P2/engineering`
  - THIRD of three. Order: REQ-0 (FR existence gate) -> REQ-1 (test harness) -> REQ-2 (this campaign). Do NOT start before…
  - Promote: `triage_promote.py --id trg-1b764b2c --task-ref EXT:<ref>`

### Source: securityReview (1 item)

<a id="trg-0ce59c05"></a>
- **CI-Security 2/2: ship the action-pinning posture RULE to adopters (templates already correct)** `id=trg-0ce59c05 | severity=low | kind=improvement → P3/engineering`
  - CI-Security 2 of 2. This is what is LEFT of item 1 in anchor trg-9509c2e8 after verification - most of it turned out to…
  - Promote: `triage_promote.py --id trg-0ce59c05 --task-ref EXT:<ref>`

