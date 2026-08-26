# Triage Inbox

> Auto-generated 2026-08-25T22:40:37.030916Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 871
- Triage: 15 | Promoted: 4 | Dismissed: 850 | Snoozed: 2

## Top 15 items (severity-sorted)

### Source: board-split (2 items)

<a id="trg-14392ba5"></a>
- **P2.17a \[GUIDED after P2.17\] Campaign sub-iterates do not run the architecture review pass** `id=trg-14392ba5 | severity=medium | kind=improvement → P2/engineering`
  - PR #582 added external\_review.py --mode architecture as a second call in the external review step, wired into /shipwri…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.17a [GUIDED after P2.17] Campaign sub-iterates do not run the architecture review pass
    ```
  - Promote: `triage_promote.py --id trg-14392ba5 --task-ref EXT:<ref>`

<a id="trg-d76ab0d9"></a>
- **P2.18a \[GUIDED after P2.18\] Adopted repos render Source-State: run=\(unknown\)** `id=trg-d76ab0d9 | severity=medium | kind=improvement → P2/engineering`
  - MEASURED 2026-08-06 while building iterate-2026-08-05-adopt-derived-evidence-rollout. An adopted repository's complianc…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.18a [GUIDED after P2.18] Adopted repos render Source-State: run=(unknown)
    ```
  - Promote: `triage_promote.py --id trg-d76ab0d9 --task-ref EXT:<ref>`

### Source: iterate-2026-08-01-drop-write-once-step-fields (1 item)

<a id="trg-61438a67"></a>
- **P4.04 \[CAMPAIGN\] Retire the write-once current\_step / completed\_steps fields** `id=trg-61438a67 | severity=medium | kind=improvement → P2/engineering`
  - Successor to trg-be24ff6f, which asked to migrate two phase\_quality readers to phase\_tasks\[\] and 'then drop the fie…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: Retire the write-once current_step / completed_steps fields (campaign, not a P3 unit)
    ```
  - Promote: `triage_promote.py --id trg-61438a67 --task-ref EXT:<ref>`

### Source: iterate-2026-08-01-grade-snapshot-dirty-capture (1 item)

<a id="trg-9fe7c8b1"></a>
- **P4.02 \[GUIDED\] grade\_snapshot dirty: the orchestrator's sibling-process residual** `id=trg-9fe7c8b1 | severity=low | kind=improvement → P3/engineering`
  - Left open deliberately by iterate-2026-08-01-grade-snapshot-dirty-capture, which shipped grade\_snapshot.dirty captured…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P4.02: grade_snapshot dirty: the orchestrator's sibling-process residual
    ```
  - Promote: `triage_promote.py --id trg-9fe7c8b1 --task-ref EXT:<ref>`

### Source: iterate-req3-04-ac-identity-mono-R0 (1 item)

<a id="trg-b85ebe2e"></a>
- **project/adopt emit no per-FR description block — decide whether they should** `id=trg-b85ebe2e | severity=low | kind=improvement → P3/engineering`
  - R0 \(campaign req3-04-ac-identity-mono\) converged the three FR-criteria readers on the shipped shape: a heading follow…
  - Promote: `triage_promote.py --id trg-b85ebe2e --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-b17e5878"></a>
- **S2b-C \[ITERATE GEFUEHRT\] Discovery-Konvergenz: guard-Befund und include\_iterate** `id=trg-b17e5878 | severity=medium | kind=improvement → P2/engineering`
  - DER GEFUEHRTE TEIL VON S2b. Bewusst NICHT autonom: dieser Iterate beginnt mit einer Entscheidung, die der Operator tref…
  - Promote: `triage_promote.py --id trg-b17e5878 --task-ref EXT:<ref>`

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

### Source: req3-campaign (5 items)

<a id="trg-3be88962"></a>
- **REQ3.04c \[CAMPAIGN AUTONOM\] Welle 2: AC-Identitaet, Manifest v4, Bindung, Keystone-Gate \(Monorepo\)** `id=trg-3be88962 | severity=high | kind=improvement → P1/engineering`
  - DIES IST DER EIGENTLICHE REQ3.04-MECHANISMUS. Am 2026-08-23 aus trg-a8f4b029 herausgeloest, damit er nicht mit dem Absc…
  - Evidence: `.shipwright/planning/campaigns/2026-08-23-req3-04-ac-identity-mono-BRIEF.md`
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --campaign req3-04c-ac-identity-mono --autonomous
    
    Work item: REQ3.04c Welle 2 - AC-Identitaet, Manifest v4, Bindung, Keystone-Gate. Design steht in Spec/design/2026-07-22-req3-campaign-SPEC.md §5 (P3.1-P3.8). Voraussetzung: REQ3.04a gemergt.
    ```
  - Promote: `triage_promote.py --id trg-3be88962 --task-ref EXT:<ref>`

<a id="trg-8849311b"></a>
- **S2b-AB \[CAMPAIGN AUTONOM\] Discovery-Konvergenz: Netz weiten, dann Haertung landen** `id=trg-8849311b | severity=medium | kind=improvement → P2/engineering`
  - ANKER DER VORBEREITETEN KAMPAGNE s2b-discovery-convergence \(serial, 2 Sub-Iterates\). Ein Befehl, zwei PRs, dann Halt.…
  - Evidence: `.shipwright/planning/campaigns/2026-08-23-req3-04-ac-identity-mono-BRIEF.md`
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: S2b - die ~10 Call-Site-Entscheidungen zur Requirement-Discovery. Entscheidungen ZUERST treffen, dann bauen.
    ```
  - Promote: `triage_promote.py --id trg-8849311b --task-ref EXT:<ref>`

<a id="trg-8d6b49d9"></a>
- **REQ3.04b \[ITERATE GEFUEHRT\] CI regeneriert das Traceability-Manifest und vergleicht - erst nach der Messung aus REQ3.…** `id=trg-8d6b49d9 | severity=medium | kind=improvement → P2/engineering`
  - Zweite Haelfte von SPEC-Entscheidung D8 \(Spec/design/2026-07-22-req3-campaign-SPEC.md §4 P0a / §5 P3.0\). Am 2026-08-2…
  - Evidence: `.shipwright/planning/campaigns/2026-08-23-req3-04-ac-identity-mono-BRIEF.md`
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.04b: CI regeneriert das Traceability-Manifest und vergleicht. NUR starten, wenn REQ3.04a gemergt ist und dessen Messung vorliegt.
    ```
  - Promote: `triage_promote.py --id trg-8d6b49d9 --task-ref EXT:<ref>`

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
- **REQ3.05 \[CAMPAIGN AUTONOM\] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-c4f877ab | severity=medium | kind=improvement → P2/engineering`
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

### Source: triage-consolidation-2026-07-28 (1 item)

<a id="trg-84a84f4e"></a>
- **P4.03 \[GUIDED\] IT-10 Plugin-Scope-Split: entry plugins global, 11 pipeline plugins project-scoped** `id=trg-84a84f4e | severity=medium | kind=improvement → P2/engineering`
  - SUPERSEDES trg-57317128 - inhaltlich unveraendert, nur in das IT-Schema umbenannt, damit das Board einheitlich ist. Spe…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: IT-10: Plugin-Scope-Split: Einstiegs-Plugins global, 11 Pipeline-Plugins projekt-scoped
    ```
  - Promote: `triage_promote.py --id trg-84a84f4e --task-ref EXT:<ref>`

## Deferred — decided, revisit later (2)

_Not gone: each of these was decided, with a date it comes back on._

- **The delivery ladder's self-merge rung has never run against a real unprotected repository** `id=trg-5c62fa56 | severity=medium | revisit=(no revisit date recorded)`
  - Reason: Re-homed to trg-a678bd00 \(Adopt Automerge-Readiness\). Rung 3 is unreachable here: main is protected and self-merge on…
  - Un-park: `triage_cli.py unpark trg-5c62fa56 --reason <why>`

- **Changelog aggregator does not preserve BOM / line endings the plugin writer preserves** `id=trg-239ee0ad | severity=low | revisit=(no revisit date recorded)`
  - Reason: P3, in PR #472 bewusst akzeptiert und an zwei Stellen dokumentiert \(Modul-Docstring changelog\_splice.py + Iterate-Spe…
  - Un-park: `triage_cli.py unpark trg-239ee0ad --reason <why>`

