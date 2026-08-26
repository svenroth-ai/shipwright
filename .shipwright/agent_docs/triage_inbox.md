# Triage Inbox

> Auto-generated 2026-08-26T14:26:44.593029Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 877
- Triage: 16 | Promoted: 4 | Dismissed: 855 | Snoozed: 2

## Top 16 items (severity-sorted)

### Source: board-merge (1 item)

<a id="trg-f8ae782f"></a>
- **Kampagnen-Worktree-Guard: die zwei Known-limitations aus PR #653 schliessen - Session-Lock und Branch-Identitaet** `id=trg-f8ae782f | severity=medium | kind=improvement → P2/engineering`
  - ZUSAMMENGELEGT 2026-08-26 aus trg-16bec646 \(P2\) und trg-50bd22a1 \(P3\). Beide sind die ZWEI BULLETS DESSELBEN ABSCHN…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: Kampagnen-Worktree-Guard: die zwei Known-limitations aus PR #653 schliessen - Session-Lock und Branch-Identitaet
    ```
  - Promote: `triage_promote.py --id trg-f8ae782f --task-ref EXT:<ref>`

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

### Source: code-review (1 item)

<a id="trg-16075b99"></a>
- **FR-table description exemption uses a value-comparison, not structural, gap check** `id=trg-16075b99 | severity=low | kind=improvement → P3/engineering`
  - compute\_fr\_coherence's Name-only fallback fix \(iterate-2026-08-25-fr-criteria-parser-pin\) compares the picked descr…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-16075b99 --task-ref EXT:<ref>`

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

### Source: iterate-2026-08-26-b-pure-hardening (2 items)

<a id="trg-12f6ab89"></a>
- **S2b pass B follow-up: stale test/probe naming and doc nits from code-review** `id=trg-12f6ab89 | severity=low | kind=improvement → P3/engineering`
  - Code-review of S2b pass B \(pure hardening, PR #655\) found 5 cosmetic/documentation issues, none correctness bugs: \(1…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-12f6ab89 --task-ref EXT:<ref>`

<a id="trg-a95e6fdf"></a>
- **Direct spec.md bypass reads \(top-level agent\_docs + repo-root\) still use exists\(\) not is\_file\(\)** `id=trg-a95e6fdf | severity=low | kind=improvement → P3/engineering`
  - External code review of S2b pass B \(pure hardening\) found that the top-level agent\_docs/spec.md check in \_test\_lin…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-a95e6fdf --task-ref EXT:<ref>`

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

### Source: req3-campaign (3 items)

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

