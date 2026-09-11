# Triage Inbox

> Auto-generated 2026-09-11T01:45:13.819477Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 919
- Triage: 17 | Promoted: 5 | Dismissed: 894 | Snoozed: 3

## Top 17 items (severity-sorted)

### Source: board-split (1 item)

<a id="trg-14392ba5"></a>
- **P2.17a \[GUIDED after P2.17\] Campaign sub-iterates do not run the architecture review pass** `id=trg-14392ba5 | severity=medium | kind=improvement → P2/engineering`
  - PR #582 added external\_review.py --mode architecture as a second call in the external review step, wired into /shipwri…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.17a [GUIDED after P2.17] Campaign sub-iterates do not run the architecture review pass
    ```
  - Promote: `triage_promote.py --id trg-14392ba5 --task-ref EXT:<ref>`

### Source: ci-observation (1 item)

<a id="trg-9b243652"></a>
- **Flaky: test\_ensure\_shared\_cache\_fanout\_join.py barrier timing on Windows CI** `id=trg-9b243652 | severity=medium | kind=bug → P2/engineering`
  - shared/tests/test\_ensure\_shared\_cache\_fanout\_join.py::test\_detected\_fanout\_waits\_for\_all\_installed\_hook\_pa…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-9b243652 --task-ref EXT:<ref>`

### Source: cli (1 item)

<a id="trg-33d30377"></a>
- **record\_ci\_supplychain\_ack.py has no operator-only guard - a sub-iterate runner wrote its own CI trust-boundary permi…** `id=trg-33d30377 | severity=high | kind=bug → P1/engineering`
  - MEASURED 2026-09-11 on PR #718 \(p3.8 rewritability-advisory\).  WHAT HAPPENED The sub-iterate runner's Step 3.4 re-che…
  - Promote: `triage_promote.py --id trg-33d30377 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-0801c0a8"></a>
- **Compliance: 2 open finding\(s\)** `id=trg-0801c0a8 | severity=high | kind=compliance → P1/compliance`
  - 2 open compliance finding\(s\): H/H1, H/H2  - H/H1: Bloat drift \(oversize file not in baseline\) — shared/scripts/ci\_…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 2 open compliance finding(s): H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-0801c0a8 --task-ref EXT:<ref>`

### Source: doubt-reviewer (1 item)

<a id="trg-dd297923"></a>
- **PR-review skip-gate: directory-prefix classification lacks provenance anchoring** `id=trg-dd297923 | severity=high | kind=bug → P1/engineering`
  - is\_safe\_to\_skip\_review's \_GENERATED\_PREFIXES check is a plain directory-prefix match with no closed-set/canonical…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-dd297923 --task-ref EXT:<ref>`

### Source: external-code-review (1 item)

<a id="trg-00b11bd7"></a>
- **ITERATE B \[AFTER Iterate A / trg-e69bf1ba\] P3.7 orphan-AC-binding check does not see a retired FR's surviving @covers…** `id=trg-00b11bd7 | severity=high | kind=compliance → P1/engineering`
  - External code review \(openai, HIGH\) on P3.7 feeder \(b\), check\_orphan\_ac\_binding.py \(campaign req3-04c-ac-identi…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-00b11bd7 --task-ref EXT:<ref>`

### Source: iterate-2026-09-07-p3-3-producers-emit-and-require-binding (1 item)

<a id="trg-875104ac"></a>
- **P3.3 emit-half: wire the EXISTING layer promotion into the iterate flow \(scope settled - no second writer\)** `id=trg-875104ac | severity=medium | kind=compliance → P2/engineering`
  - P3.3 \(campaign req3-04c-ac-identity-wave2\) delivered only the require half \(F11 check\_binding\_completeness\). The…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-875104ac --task-ref EXT:<ref>`

### Source: iterate-2026-09-09-p4-1-glossary-generator-review (1 item)

<a id="trg-6c3629d2"></a>
- **P4.1 follow-up: 5 low-severity polish items on write\_context\_term.py / interview-protocol.md** `id=trg-6c3629d2 | severity=low | kind=maintenance → P3/engineering`
  - From PR #699 review \(campaign req3-09-p4-grill-glossary, sub-iterate P4.1, run\_id iterate-2026-09-09-p4-1-glossary-ge…
  - Promote: `triage_promote.py --id trg-6c3629d2 --task-ref EXT:<ref>`

### Source: iterate-2026-09-10-p3-7-feeder-checks-anti-ratcheted (1 item)

<a id="trg-33a474e2"></a>
- **ITERATE C: two ADVISORY checks - changed test body suspects its AC, and requirement links to its rationale \(p3.8\)** `id=trg-33a474e2 | severity=low | kind=improvement → P3/engineering`
  - P3.7 sub-iterate spec \(campaign req3-04c-ac-identity-wave2\) names a third, lower-priority item alongside the two hard…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-33a474e2 --task-ref EXT:<ref>`

### Source: iterate-2026-09-11-binding-completeness-rollout-transition (1 item)

<a id="trg-1d9ed777"></a>
- **Extend rollout transition grace to evaluate\_cross\_layer / the AC-level keystone gate** `id=trg-1d9ed777 | severity=low | kind=improvement → P3/engineering`
  - check\_binding\_completeness \(P3.3\) now grants a one-time transition grace to a pre-existing, title-matched, superset…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-1d9ed777 --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-284c03a1"></a>
- **Triage cross-tree fold-in: 3 follow-ups after precedence fix** `id=trg-284c03a1 | severity=low | kind=maintenance → P3/engineering`
  - Filed alongside iterate-2026-09-10-triage-cross-tree-precedence \(fixed the read\_all\_items foreign-status-overrides-l…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-284c03a1 --task-ref EXT:<ref>`

### Source: operator-request (1 item)

<a id="trg-a0d8c2cb"></a>
- **P2.50 \[GUIDED after plan-reviewer-configurable\] Internal architecture review for plan and iterate, on the plan\_revie…** `id=trg-a0d8c2cb | severity=high | kind=improvement → P1/engineering`
  - REQUIREMENT \(operator, 2026-08-08\). The architecture review exists only as an EXTERNAL call. Give it an internal arm…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.50 [GUIDED] The architecture review has no internal path, so it silently disappears on three separate routes
    ```
  - Promote: `triage_promote.py --id trg-a0d8c2cb --task-ref EXT:<ref>`

### Source: req3-campaign (2 items)

<a id="trg-a2a45d38"></a>
- **REQ3.10 \[ITERATE\]\[STRICTLY LAST after REQ3.05/3.06\] Grader Lead-Magnet: change\_reconciliation real machen** `id=trg-a2a45d38 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv. Der Grader reserviert change\_reconciliation bereits als 'Shipwright-only'-Dimension \(kappt kalte…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.10: Grader Lead-Magnet: change_reconciliation real machen
    ```
  - Promote: `triage_promote.py --id trg-a2a45d38 --task-ref EXT:<ref>`

<a id="trg-c4f877ab"></a>
- **REQ3.05 \[CAMPAIGN AUTONOM - scaffold ready\] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-c4f877ab | severity=medium | kind=improvement → P2/engineering`
  - Der Coverage-Motor, eigener Anker damit er nicht nachgeschleift wird. Schreibt Tests fuer ACs, die heute keinen beweise…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.05: Test-Backfill: fehlende AC-Tests - Monorepo
    ```
  - Promote: `triage_promote.py --id trg-c4f877ab --task-ref EXT:<ref>`

### Source: req3-phase2-walk (1 item)

<a id="trg-0845a2f5"></a>
- **REQ3.06 \[CAMPAIGN AUTONOM\] Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only \(mechanisable\) - Monorepo** `id=trg-0845a2f5 | severity=high | kind=improvement → P1/engineering`
  - AUTONOME Kampagne. Der Anker, der die Enforcement-Liste des AC-Nachweis-Registers abarbeitet - das Register IST die Arb…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.06: Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only (mechanisable) - Monorepo
    ```
  - Promote: `triage_promote.py --id trg-0845a2f5 --task-ref EXT:<ref>`

### Source: stage3-doubt-review (1 item)

<a id="trg-a719e3b7"></a>
- **Keystone gate's SHARED helper modules \(imported by its \_keystone\_\*.py verifiers\) stay outside SENSITIVE\_PATH\_RE** `id=trg-a719e3b7 | severity=low | kind=improvement → P3/engineering`
  - iterate-2026-09-10-keystone-verifier-sensitive-path added the 8 \_keystone\_\*.py verifier modules and their ci.yml ent…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-a719e3b7 --task-ref EXT:<ref>`

### Source: t0-seam-survey (1 item)

<a id="trg-ff6ea5f0"></a>
- **req3-05 t4/t5/t8/t9 test-root count exceeds campaign's 2-root guidance — needs owner decision** `id=trg-ff6ea5f0 | severity=medium | kind=compliance → P2/engineering`
  - t0's seam survey \(.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md\) found FOUR units exceed campaign.md…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-ff6ea5f0 --task-ref EXT:<ref>`

## Deferred — decided, revisit later (3)

_Not gone: each of these was decided, with a date it comes back on._

- **P4.03 \[GUIDED\] IT-10 Plugin-Scope-Split: entry plugins global, 11 pipeline plugins project-scoped** `id=trg-84a84f4e | severity=medium | revisit=2026-12-01`
  - Reason: Parked 2026-09-06 by the operator, WITH a date: a snooze without revisitAt never returns. Every repo he works in IS a S…
  - Un-park: `triage_cli.py unpark trg-84a84f4e --reason <why>`

- **The delivery ladder's self-merge rung has never run against a real unprotected repository** `id=trg-5c62fa56 | severity=medium | revisit=(no revisit date recorded)`
  - Reason: Re-homed to trg-a678bd00 \(Adopt Automerge-Readiness\). Rung 3 is unreachable here: main is protected and self-merge on…
  - Un-park: `triage_cli.py unpark trg-5c62fa56 --reason <why>`

- **Changelog aggregator does not preserve BOM / line endings the plugin writer preserves** `id=trg-239ee0ad | severity=low | revisit=(no revisit date recorded)`
  - Reason: P3, in PR #472 bewusst akzeptiert und an zwei Stellen dokumentiert \(Modul-Docstring changelog\_splice.py + Iterate-Spe…
  - Un-park: `triage_cli.py unpark trg-239ee0ad --reason <why>`

