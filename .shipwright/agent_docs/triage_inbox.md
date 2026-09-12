# Triage Inbox

> Auto-generated 2026-09-12T06:11:08.013737Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 934
- Triage: 15 | Promoted: 5 | Dismissed: 911 | Snoozed: 3

## Top 15 items (severity-sorted)

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

<a id="trg-4fac93bf"></a>
- **Iterate retention deletes the entry file but never its .test-results.json sibling - main carries 127 orphans against 53…** `id=trg-4fac93bf | severity=medium | kind=bug → P2/engineering`
  - MEASURED 2026-09-12 on origin/main while pruning the entry backlog \(PR #736\).  THE NUMBERS   .shipwright/agent\_docs/…
  - Promote: `triage_promote.py --id trg-4fac93bf --task-ref EXT:<ref>`

### Source: code-review (2 items)

<a id="trg-9583d3a8"></a>
- **Decide extension-scope treatment for FR-01.02 #5/#10 gates** `id=trg-9583d3a8 | severity=medium | kind=improvement → P2/engineering`
  - Stage-2 code review \(e2-checks-project-elicitation, PR #729, round 3\) found that check\_criteria\_free\_of\_implement…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-9583d3a8 --task-ref EXT:<ref>`

<a id="trg-a287d575"></a>
- **step-8-completion.md/SKILL.md say agent\_docs needs 5 files; project-scaffolding.md's producer writes 4** `id=trg-a287d575 | severity=low | kind=maintenance → P3/engineering`
  - Step 8's completion checklist \(item 4\) says '.shipwright/agent\_docs/ directory exists with all 5 files \(Full Applic…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-a287d575 --task-ref EXT:<ref>`

### Source: doubt-reviewer (2 items)

<a id="trg-3b206c08"></a>
- **Review-evidence filenames have no canonical name per artifact kind** `id=trg-3b206c08 | severity=high | kind=improvement → P1/engineering`
  - Review-evidence files under the planning tree are written with ad-hoc, per-run filenames chosen by each producer instea…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-3b206c08 --task-ref EXT:<ref>`

<a id="trg-dd297923"></a>
- **PR-review skip-gate: directory-prefix classification lacks provenance anchoring** `id=trg-dd297923 | severity=high | kind=bug → P1/engineering`
  - is\_safe\_to\_skip\_review's \_GENERATED\_PREFIXES check is a plain directory-prefix match with no closed-set/canonical…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-dd297923 --task-ref EXT:<ref>`

### Source: e3-checks-test-security (1 item)

<a id="trg-2f7a840a"></a>
- **Wire check\_e2e\_specs\_exist\_when\_journeys\_planned to per-journey coverage \(weak oracle\)** `id=trg-2f7a840a | severity=low | kind=improvement → P3/engineering`
  - FR-01.06 #6's floor check \(sub-iterate e3-checks-test-security\) only confirms SOME \*.spec.ts exists when a plan decl…
  - Promote: `triage_promote.py --id trg-2f7a840a --task-ref EXT:<ref>`

### Source: iterate-2026-09-07-p3-3-producers-emit-and-require-binding (1 item)

<a id="trg-875104ac"></a>
- **P3.3 emit-half: wire the EXISTING layer promotion into the iterate flow \(scope settled - no second writer\)** `id=trg-875104ac | severity=medium | kind=compliance → P2/engineering`
  - P3.3 \(campaign req3-04c-ac-identity-wave2\) delivered only the require half \(F11 check\_binding\_completeness\). The…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-875104ac --task-ref EXT:<ref>`

### Source: iterate-2026-09-11-binding-completeness-rollout-transition (1 item)

<a id="trg-1d9ed777"></a>
- **\[DECIDED - tracked deferral, not awaiting a ruling\] Extend the rollout transition grace to evaluate\_cross\_layer and…** `id=trg-1d9ed777 | severity=low | kind=improvement → P3/engineering`
  - check\_binding\_completeness \(P3.3\) now grants a one-time transition grace to a pre-existing, title-matched, superset…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-1d9ed777 --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-42edfde6"></a>
- **Iterate retention orphans a run's .test-results.json when its entry file is pruned \(127 orphans measured on origin/mai…** `id=trg-42edfde6 | severity=medium | kind=maintenance → P2/engineering`
  - MEASURED 2026-09-12 on origin/main, following PR #736's entry-backlog pruning. Under .shipwright/agent\_docs/iterates/:…
  - Promote: `triage_promote.py --id trg-42edfde6 --task-ref EXT:<ref>`

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

