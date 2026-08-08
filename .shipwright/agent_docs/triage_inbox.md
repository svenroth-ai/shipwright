# Triage Inbox

> Auto-generated 2026-08-08T22:25:58.209294Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 828
- Triage: 25 | Promoted: 4 | Dismissed: 796 | Snoozed: 3

## Top 25 items (severity-sorted)

### Source: board-normalization (2 items)

<a id="trg-8e0b4dd5"></a>
- **P2.34 \[GUIDED\]\[CROSS-REPO\]\[SPLIT BEFORE BUILD\] Align WebUI and Python triage transition locking** `id=trg-8e0b4dd5 | severity=high | kind=bug → P1/engineering`
  - Follow-up to PR #539 / iterate-2026-08-01-triage-defer-lifecycle. Python writers use the shared FileLock while shipwrig…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.34: Align WebUI and Python triage transition locking
    ```
  - Promote: `triage_promote.py --id trg-8e0b4dd5 --task-ref EXT:<ref>`

<a id="trg-9e7b50e8"></a>
- **P3.06 \[SERIAL 6/6 after P3.05\]\[UNBLOCKED\] Tier must use review evidence, not maintainer authorship** `id=trg-9e7b50e8 | severity=medium | kind=improvement → P2/engineering`
  - Final IT-9 workflow unit, still serial after P3.05 because all six units own .github/workflows. The former review-recor…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P3.06: Tier must use review evidence, not maintainer authorship
    ```
  - Promote: `triage_promote.py --id trg-9e7b50e8 --task-ref EXT:<ref>`

### Source: board-split (7 items)

<a id="trg-c8073edd"></a>
- **P2.54 \[AUTO\] A dismissed recurring finding comes straight back under a new id, so an operator decision cannot stick** `id=trg-c8073edd | severity=medium | kind=bug → P2/engineering`
  - OBSERVED DIRECTLY ON THIS BOARD, 2026-08-08 — not inferred:    \* trg-f3f5bd8c \("must-pass check set does not match th…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.54 [AUTO] A dismissed recurring finding comes straight back under a new id, so an operator decision cannot stick
    ```
  - Promote: `triage_promote.py --id trg-c8073edd --task-ref EXT:<ref>`

<a id="trg-36ceef43"></a>
- **P3.07 \[AUTO after P3.06\]\[SERIAL\] IT-9: five more PR-review hardening items from webui#338** `id=trg-36ceef43 | severity=medium | kind=improvement → P2/engineering`
  - BELONGS TO IT-9. IT-9 owns EVERY file under .github/workflows/ exclusively; no other card may touch a workflow file. it…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P3.07 [AUTO after P3.06][SERIAL] IT-9: five more PR-review hardening items from webui#338
    ```
  - Promote: `triage_promote.py --id trg-36ceef43 --task-ref EXT:<ref>`

<a id="trg-8a2f49df"></a>
- **P2.52 \[AUTO\] Three small shared/scripts fixes: a fail-open probe, an unscanned writer, an unbounded cache** `id=trg-8a2f49df | severity=medium | kind=bug → P2/engineering`
  - BUNDLES trg-fd3fa3c1, trg-a382b3a2 and trg-3b88e1c2. Combined at the operator's standing request to group small items e…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.52 [AUTO] Three small shared/scripts fixes: a fail-open probe, an unscanned writer, an unbounded cache
    ```
  - Promote: `triage_promote.py --id trg-8a2f49df --task-ref EXT:<ref>`

<a id="trg-be3fb8a6"></a>
- **P2.49 \[AUTO\] Iterate-history retention evicts the F5c entries P1.14 permanently pins** `id=trg-be3fb8a6 | severity=medium | kind=bug → P2/engineering`
  - MERGES trg-09922c92 and trg-1120c898 - the SAME defect filed twice, nine hours apart, from two angles. Both name append…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.49 [AUTO] Iterate-history retention evicts the F5c entries P1.14 permanently pins
    ```
  - Promote: `triage_promote.py --id trg-be3fb8a6 --task-ref EXT:<ref>`

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

<a id="trg-e67264d7"></a>
- **P2.53 \[AUTO\] Six small defects in one run: the plan-reviewer wiring tail plus three fragile reader/writer sites** `id=trg-e67264d7 | severity=low | kind=bug → P3/engineering`
  - MERGES P2.47 \(trg-f210096e\) and P2.48 \(trg-f97b5e99\). Both were already three-item bundles of low-severity defects;…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.53 [AUTO] Six small defects in one run: the plan-reviewer wiring tail plus three fragile reader/writer sites
    ```
  - Promote: `triage_promote.py --id trg-e67264d7 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-3555e7c8"></a>
- **Compliance: 5 open finding\(s\)** `id=trg-3555e7c8 | severity=high | kind=compliance → P1/compliance`
  - 5 open compliance finding\(s\): D/D1, D/D3, F/F6, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Shou…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance

    Context: 5 open compliance finding(s): D/D1, D/D3, F/F6, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-3555e7c8 --task-ref EXT:<ref>`

### Source: context-cost-measurement (3 items)

<a id="trg-b364baa6"></a>
- **TC3.3 \(auto, serial 3/3\) Persist the iterate state that currently exists only in the conversation, so a compaction ca…** `id=trg-b364baa6 | severity=high | kind=improvement → P1/engineering`
  - AUTONOMOUS: yes.  OBSERVED 2026-08-07, two of two runs: both iterates compacted, one of them DURING its external review…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-b364baa6 --task-ref EXT:<ref>`

<a id="trg-e6d1cc5e"></a>
- **TC5.1 \(auto\) Two thirds of an iterate's wall clock sits inside no timing span, and one span stayed open for nine hours** `id=trg-e6d1cc5e | severity=medium | kind=improvement → P2/engineering`
  - AUTONOMOUS: yes. See CONTENTION before starting.  Measured on main 2026-08-08 over the 14 runs finalized since 2026-08-…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-e6d1cc5e --task-ref EXT:<ref>`

<a id="trg-a3880058"></a>
- **TC4.1 \(auto, last\) Document the strategies for keeping token cost controllable, organised by when a project needs them** `id=trg-a3880058 | severity=medium | kind=feature → P2/engineering`
  - AUTONOMOUS: yes.  Re-filed on operator direction: this must NOT read as a report of what we measured. It is a how-to, o…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-a3880058 --task-ref EXT:<ref>`

### Source: doubt-reviewer (1 item)

<a id="trg-b8537d8f"></a>
- **P2.39 \[AUTO after the F11 ladder settles\] verify\_local.py runs at F0, but CI judges a different tree** `id=trg-b8537d8f | severity=medium | kind=improvement → P2/engineering`
  - Raised by the Stage-3 doubt review of iterate-2026-08-05-wire-local-guard-scripts, which wired scripts/verify\_local.py…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.39 [AUTO after the F11 ladder settles] verify_local.py runs at F0, but CI judges a different tree
    ```
  - Promote: `triage_promote.py --id trg-b8537d8f --task-ref EXT:<ref>`

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

### Source: operator-request (2 items)

<a id="trg-a0d8c2cb"></a>
- **P2.50 \[GUIDED after plan-reviewer-configurable\] Internal architecture review for plan and iterate, on the plan\_revie…** `id=trg-a0d8c2cb | severity=high | kind=improvement → P1/engineering`
  - REQUIREMENT \(operator, 2026-08-08\). The architecture review exists only as an EXTERNAL call. Give it an internal arm…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.50 [GUIDED] The architecture review has no internal path, so it silently disappears on three separate routes
    ```
  - Promote: `triage_promote.py --id trg-a0d8c2cb --task-ref EXT:<ref>`

<a id="trg-a7682989"></a>
- **P2.56 \[AUTO\] An outbox-buffered amend that has not reached origin is invisible in the envelope** `id=trg-a7682989 | severity=low | kind=improvement → P3/engineering`
  - Split out of trg-d5ef8039 on 2026-08-08. This is the half that is NOT urgent — it is about operator visibility of an am…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: P2.56 [AUTO] An outbox-buffered amend that has not reached origin is invisible in the envelope
    ```
  - Promote: `triage_promote.py --id trg-a7682989 --task-ref EXT:<ref>`

### Source: phaseQuality (1 item)

<a id="trg-6830cace"></a>
- **Phase-quality: 1 open Tier-1 FAIL\(s\) across 1 phase\(s\)** `id=trg-6830cace | severity=high | kind=bug → P1/engineering`
  - 1 open phase-quality Tier-1 FAIL\(s\) across 1 phase\(s\): iterate.  - iterate:W3 \(W3 F5a/F5b work\_completed + test-e…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance

    Context: 1 open phase-quality Tier-1 FAIL(s): iterate:W3.
    Dashboard: .shipwright/compliance/skill-compliance/_dashboard.md
    Each FAIL + remediation is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-6830cace --task-ref EXT:<ref>`

### Source: req3-campaign (3 items)

<a id="trg-a8f4b029"></a>
- **REQ3.04 \[CAMPAIGN AUTONOM\] Mechanik Monorepo plus der Spec-Reader \(supersedes trg-7085d783\)** `id=trg-a8f4b029 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-7085d783, KONSOLIDIERT zusaetzlich trg-1d7d91d0 + trg-2ea0b99a + trg-8bf97fd4. Owner-Entscheidung 2026-0…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate

    Work item: REQ3.04: Mechanik Monorepo plus der Spec-Reader (supersedes trg-7085d783)
    ```
  - Promote: `triage_promote.py --id trg-a8f4b029 --task-ref EXT:<ref>`

<a id="trg-a2a45d38"></a>
- **REQ3.10 \[ITERATE\] Grader Lead-Magnet: change\_reconciliation real machen** `id=trg-a2a45d38 | severity=medium | kind=improvement → P2/engineering`
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

## Deferred — decided, revisit later (3)

_Not gone: each of these was decided, with a date it comes back on._

- **P1.13 Persist an atomic F0 completion receipt** `id=trg-b9f1c27c | severity=high | revisit=2026-08-10`
  - Reason: Conditional only: first measure the P1.12 execution heartbeat in both the agent tool channel and the integrated Codex t…
  - Un-park: `triage_cli.py unpark trg-b9f1c27c --reason <why>`

- **The delivery ladder's self-merge rung has never run against a real unprotected repository** `id=trg-5c62fa56 | severity=medium | revisit=(no revisit date recorded)`
  - Reason: Re-homed to trg-a678bd00 \(Adopt Automerge-Readiness\). Rung 3 is unreachable here: main is protected and self-merge on…
  - Un-park: `triage_cli.py unpark trg-5c62fa56 --reason <why>`

- **Changelog aggregator does not preserve BOM / line endings the plugin writer preserves** `id=trg-239ee0ad | severity=low | revisit=(no revisit date recorded)`
  - Reason: P3, in PR #472 bewusst akzeptiert und an zwei Stellen dokumentiert \(Modul-Docstring changelog\_splice.py + Iterate-Spe…
  - Un-park: `triage_cli.py unpark trg-239ee0ad --reason <why>`

