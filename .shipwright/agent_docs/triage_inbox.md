# Triage Inbox

> Auto-generated 2026-09-10T19:27:01.283318Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 912
- Triage: 13 | Promoted: 4 | Dismissed: 892 | Snoozed: 3

## Top 13 items (severity-sorted)

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

### Source: cli (1 item)

<a id="trg-b536636e"></a>
- **Cross-tree foreign status events from ABANDONED worktrees resurrect dismissed triage cards** `id=trg-b536636e | severity=high | kind=bug → P1/engineering`
  - MEASURED 2026-09-10 on the main tree. \`triage.read\_all\_items\` resolves \`trg-74ef24ce\` \("Compliance: 7 open findi…
  - Promote: `triage_promote.py --id trg-b536636e --task-ref EXT:<ref>`

### Source: doubt-review (1 item)

<a id="trg-aedcfe7b"></a>
- **Binding-completeness F11 gate: transition rule for bindings that predate the gate's own rollout \(9 WebUI FRs already e…** `id=trg-aedcfe7b | severity=high | kind=compliance → P1/engineering`
  - The new check\_binding\_completeness HARD gate \(P3.3, iterate-2026-09-07-p3-3-producers-emit-and-require-binding\) was…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-aedcfe7b --task-ref EXT:<ref>`

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
- **\[SCOPE FIRST, not campaign-blocked\] P3.3 emit-half: producers must write a complete binding at requirement create/upd…** `id=trg-875104ac | severity=medium | kind=compliance → P2/engineering`
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

### Source: iterate-2026-09-10-p3-7-feeder-checks-anti-ratcheted (2 items)

<a id="trg-e69bf1ba"></a>
- **ITERATE A: P3.7 feeder \(a\) baseline lifecycle - no post-merge observation AND no cross-run provenance** `id=trg-e69bf1ba | severity=medium | kind=improvement → P2/engineering`
  - The feeder \(a\) coverage-ratchet baseline \(shipwright\_ac\_coverage\_baseline.json\) is only ever read and compared i…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-e69bf1ba --task-ref EXT:<ref>`

<a id="trg-33a474e2"></a>
- **ITERATE C: two ADVISORY checks - changed test body suspects its AC, and requirement links to its rationale \(p3.8\)** `id=trg-33a474e2 | severity=low | kind=improvement → P3/engineering`
  - P3.7 sub-iterate spec \(campaign req3-04c-ac-identity-wave2\) names a third, lower-priority item alongside the two hard…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-33a474e2 --task-ref EXT:<ref>`

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

