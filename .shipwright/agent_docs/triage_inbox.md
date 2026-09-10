# Triage Inbox

> Auto-generated 2026-09-10T07:37:24.487825Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 903
- Triage: 16 | Promoted: 4 | Dismissed: 880 | Snoozed: 3

## Top 16 items (severity-sorted)

### Source: P4.2-plan-review (1 item)

<a id="trg-da67adbd"></a>
- **grill-trace fr\_trace\_coverage slug join: no collision/orphan detection** `id=trg-da67adbd | severity=low | kind=improvement → P3/engineering`
  - External plan review \(round 2, P4.2\) flagged that grill\_trace\_fr\_coverage.py's Name-to-requirement\_key slug join…
  - Promote: `triage_promote.py --id trg-da67adbd --task-ref EXT:<ref>`

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

### Source: doubt-review (1 item)

<a id="trg-aedcfe7b"></a>
- **\[WAIT for P3.8 / campaign req3-04c\] Binding-completeness F11 gate: blast radius unmeasured on non-adopt target projec…** `id=trg-aedcfe7b | severity=high | kind=compliance → P1/engineering`
  - The new check\_binding\_completeness HARD gate \(P3.3, iterate-2026-09-07-p3-3-producers-emit-and-require-binding\) was…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-aedcfe7b --task-ref EXT:<ref>`

### Source: iterate-2026-09-07-p3-3-producers-emit-and-require-binding (1 item)

<a id="trg-875104ac"></a>
- **\[WAIT for P3.5\] P3.3 emit-half: producers must write a complete binding at requirement create/update time** `id=trg-875104ac | severity=medium | kind=compliance → P2/engineering`
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

### Source: keystone-gate-p3.6 (1 item)

<a id="trg-f68795d2"></a>
- **Orphan-test detector: three named ways to unbind an AC without editing its criterion** `id=trg-f68795d2 | severity=medium | kind=improvement → P2/engineering`
  - The keystone AC gate only blocks when a criterion's own text changes in the same PR that removes its binding. Three kno…
  - Promote: `triage_promote.py --id trg-f68795d2 --task-ref EXT:<ref>`

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

### Source: req3-campaign (3 items)

<a id="trg-3be88962"></a>
- **REQ3.04c \[CAMPAIGN AUTONOM\] Welle 2: AC-Identitaet, Manifest v4, Bindung, Keystone-Gate \(Monorepo\)** `id=trg-3be88962 | severity=high | kind=improvement → P1/engineering`
  - === P3.4c DELIVERED, P3.5 RESTARTS 2026-09-09 === p3.4c merged as #691 \(093162664\): shared/scripts/ci\_provenance.py…
  - Evidence: `.shipwright/planning/campaigns/2026-08-23-req3-04-ac-identity-mono-BRIEF.md`
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --campaign req3-04c-ac-identity-mono --autonomous
    
    Work item: REQ3.04c Welle 2 - AC-Identitaet, Manifest v4, Bindung, Keystone-Gate. Design steht in Spec/design/2026-07-22-req3-campaign-SPEC.md §5 (P3.1-P3.8). Voraussetzung: REQ3.04a gemergt.
    ```
  - Promote: `triage_promote.py --id trg-3be88962 --task-ref EXT:<ref>`

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
- **REQ3.05 \[WAIT for P3.7\] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-c4f877ab | severity=medium | kind=improvement → P2/engineering`
  - Der Coverage-Motor, eigener Anker damit er nicht nachgeschleift wird. Schreibt Tests fuer ACs, die heute keinen beweise…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.05: Test-Backfill: fehlende AC-Tests - Monorepo
    ```
  - Promote: `triage_promote.py --id trg-c4f877ab --task-ref EXT:<ref>`

### Source: req3-phase2-walk (2 items)

<a id="trg-0845a2f5"></a>
- **REQ3.06 \[CAMPAIGN AUTONOM\] Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only \(mechanisable\) - Monorepo** `id=trg-0845a2f5 | severity=high | kind=improvement → P1/engineering`
  - AUTONOME Kampagne. Der Anker, der die Enforcement-Liste des AC-Nachweis-Registers abarbeitet - das Register IST die Arb…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.06: Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only (mechanisable) - Monorepo
    ```
  - Promote: `triage_promote.py --id trg-0845a2f5 --task-ref EXT:<ref>`

<a id="trg-9c9c0792"></a>
- **REQ3.09 \[ITERATE\] Domaenen-Glossar erzeugen, Grill-Modul in Project, plus die Nachweis-Spur \(supersedes trg-d5522f68…** `id=trg-9c9c0792 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv, Follow-up nach der Kampagne. OWNS: die Elicitation-Oberflaeche von PROJECT, das geteilte Grill-Mod…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.09: Domaenen-Glossar erzeugen, Grill-Modul in Project, plus die Nachweis-Spur (supersedes trg-d5522f68)
    ```
  - Promote: `triage_promote.py --id trg-9c9c0792 --task-ref EXT:<ref>`

### Source: ruling-q5-p3.6 (1 item)

<a id="trg-a05c4aba"></a>
- **Post-merge detective control: verify main's tip actually satisfied the keystone gate** `id=trg-a05c4aba | severity=low | kind=improvement → P3/engineering`
  - The keystone AC gate is a preventive, in-run check: same CI job, same evidence, no commit boundary and no machine bound…
  - Promote: `triage_promote.py --id trg-a05c4aba --task-ref EXT:<ref>`

### Source: session-observation (1 item)

<a id="trg-a99ee30d"></a>
- **A PR whose diff is 100% generated paths can never get a green PR Review - the compliance refresh and triage-delivery pa…** `id=trg-a99ee30d | severity=high | kind=bug → P1/engineering`
  - OBSERVED TWICE IN ONE HOUR, 2026-09-10, on two DIFFERENT supported delivery paths:   PR #707  chore\(compliance\): refr…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: A PR whose diff is 100% generated paths can never get a green PR Review - the compliance refresh and triage-delivery paths both deadlock on an admin o
    ```
  - Promote: `triage_promote.py --id trg-a99ee30d --task-ref EXT:<ref>`

### Source: stage2-code-review (1 item)

<a id="trg-6769326b"></a>
- **Keystone gate: spec\_text\_was\_read is repo-wide, not per-spec-path** `id=trg-6769326b | severity=low | kind=improvement → P3/engineering`
  - In the keystone AC-identity gate's per-AC change-set builder, the flag that suppresses the new-FR-without-criteria arm…
  - Promote: `triage_promote.py --id trg-6769326b --task-ref EXT:<ref>`

### Source: stage3-doubt-review (1 item)

<a id="trg-9967000f"></a>
- **Keystone gate's own verifier source not covered by the CI-supply-chain sensitive-path detector** `id=trg-9967000f | severity=low | kind=improvement → P3/engineering`
  - The keystone AC gate's trust-posture statement claims parity with every other merge gate here \(ruff, the diff-coverage…
  - Promote: `triage_promote.py --id trg-9967000f --task-ref EXT:<ref>`

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

