# Triage Inbox

> Auto-generated 2026-07-23T06:42:49.892025Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 352
- Triage: 15 | Promoted: 1 | Dismissed: 335 | Snoozed: 1

## Top 15 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

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

### Source: improvement (2 items)

<a id="trg-c1419d00"></a>
- **CI-Security 3: ship the accepted-risk register + converge to adopted repos** `id=trg-c1419d00 | severity=medium | kind=improvement → P2/engineering`
  - The third step named as out-of-scope in iterate-2026-07-18-accepted-risk-alert-convergence, whose precondition ('worth…
  - Promote: `triage_promote.py --id trg-c1419d00 --task-ref EXT:<ref>`

<a id="trg-6e8121e7"></a>
- **CI supply-chain ack gate is blind to SHIPPED CI templates** `id=trg-6e8121e7 | severity=medium | kind=improvement → P2/engineering`
  - CI_SUPPLYCHAIN_FILE_PATTERNS (risk_detectors.py:149) matches only THIS repo's .github/**. An edit to shared/templates/g…
  - Promote: `triage_promote.py --id trg-6e8121e7 --task-ref EXT:<ref>`

### Source: iterate (3 items)

<a id="trg-360e494f"></a>
- **Event-log readers: remaining sites still parse one record per physical line** `id=trg-360e494f | severity=medium | kind=improvement → P2/engineering`
  - iterate-2026-07-19-events-record-boundary-readers converted 11 read sites to the shared record-boundary SSoT (lib/jsonl…
  - Promote: `triage_promote.py --id trg-360e494f --task-ref EXT:<ref>`

<a id="trg-92c0c36b"></a>
- **WebUI: Mission Requirement artifact should read events.jsonl for full iterate history** `id=trg-92c0c36b | severity=low | kind=improvement → P3/engineering`
  - The shared iterates/<run_id>.json store is a bounded 50-entry recency window by design (append_iterate_entry retention)…
  - Promote: `triage_promote.py --id trg-92c0c36b --task-ref EXT:<ref>`

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

### Source: iterate-2026-07-19-compliance-prework (2 items)

<a id="trg-8bf97fd4"></a>
- **S2b: converge the requirement-discovery filter semantics (~10 call-site decisions)** `id=trg-8bf97fd4 | severity=medium | kind=improvement → P2/engineering`
  - The tail of campaign step S2, not a new campaign - file it now so it is not lost between "S2 merged" and "somebody noti…
  - Promote: `triage_promote.py --id trg-8bf97fd4 --task-ref EXT:<ref>`

<a id="trg-eb19ada4"></a>
- **REQ-3: make the Layers column authoritative - establish the missing test links first** `id=trg-eb19ada4 | severity=medium | kind=improvement → P2/engineering`
  - The substantive half of the requirements work, deliberately left open by the catalog campaign (REQ-2).  After REQ-2 the…
  - Promote: `triage_promote.py --id trg-eb19ada4 --task-ref EXT:<ref>`

### Source: operator (1 item)

<a id="trg-1b764b2c"></a>
- **REQ-2 - Campaign: requirements catalog (S2-S8) - run AFTER REQ-1** `id=trg-1b764b2c | severity=medium | kind=improvement → P2/engineering`
  - THIRD of three. Order: REQ-0 (FR existence gate) -> REQ-1 (test harness) -> REQ-2 (this campaign). Do NOT start before…
  - Promote: `triage_promote.py --id trg-1b764b2c --task-ref EXT:<ref>`

### Source: requirements-catalog (2 items)

<a id="trg-5f2037b7"></a>
- **S5 must surface specs whose rows all fail the canonical FR-id form (zero-row parse, third state)** `id=trg-5f2037b7 | severity=medium | kind=compliance → P2/engineering`
  - S4 converged the FR-id tier onto the canonical FR-XX.YY form. That creates a state the traceability T1 guard still cann…
  - Promote: `triage_promote.py --id trg-5f2037b7 --task-ref EXT:<ref>`

<a id="trg-c9669d6a"></a>
- **Adopt FR-id generation has no cap: more than 99 detected routes emits a non-canonical FR-01.100** `id=trg-c9669d6a | severity=low | kind=bug → P3/engineering`
  - generate_adoption_artifacts and feature_inferrer both emit f"FR-01.{i:02d}" with no upper bound on i. Past 99 the forma…
  - Promote: `triage_promote.py --id trg-c9669d6a --task-ref EXT:<ref>`

### Source: webui-mission-campaign (1 item)

<a id="trg-dd48a810"></a>
- **sub-iterate-runner finalizes without F3 decision-drop / F5c iterate record, and F11 does not catch it** `id=trg-dd48a810 | severity=high | kind=bug → P1/engineering`
  - Evidence from webui campaign 2026-07-18-mission-artifacts (4 sub-iterates, all run by the sub-iterate-runner subagent u…
  - Promote: `triage_promote.py --id trg-dd48a810 --task-ref EXT:<ref>`

