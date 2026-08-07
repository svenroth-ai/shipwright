# Triage Inbox

> Auto-generated 2026-08-07T11:39:38.141439Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 771
- Triage: 35 | Promoted: 3 | Dismissed: 730 | Snoozed: 3

## Top 35 items (severity-sorted)

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

### Source: board-split (9 items)

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

<a id="trg-12f4a94d"></a>
- **P2.19h \[AUTO after P2.19b\] Drift-adoption gate strands the whole outbox on one glued line** `id=trg-12f4a94d | severity=medium | kind=bug → P2/engineering`
  - Residual of iterate-2026-08-06-triage-validate-deadends, found by its Stage-3 doubt review and deliberately left out of…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.19h [AUTO after P2.19b] Drift-adoption gate strands the whole outbox on one glued line
    ```
  - Promote: `triage_promote.py --id trg-12f4a94d --task-ref EXT:<ref>`

<a id="trg-6d8fbc10"></a>
- **P2.19i \[AUTO after P2.19d\] Lock-primitive tail: the measured Windows error code, and the third copy in shipwright-run** `id=trg-6d8fbc10 | severity=medium | kind=bug → P2/engineering`
  - BUNDLES trg-db1de213 and trg-2e961fee. Both fell out of iterate-2026-08-06-write-lock-primitives \(P2.19d, trg-dc013d82…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.19g [AUTO after P2.19d] Lock-primitive tail: the measured Windows error code, and the third copy in shipwright-run
    ```
  - Promote: `triage_promote.py --id trg-6d8fbc10 --task-ref EXT:<ref>`

<a id="trg-eed74a42"></a>
- **P3.05a \[AUTO after PR #571\] Two Windows-only F0 defects the first Windows CI job exposed** `id=trg-eed74a42 | severity=medium | kind=bug → P2/engineering`
  - BUNDLES trg-e82d8771 and trg-d0f585b2. Both were surfaced by IT-9 Unit 5 \(iterate-2026-08-05-windows-ci-tests, PR #571…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P3.05a [AUTO after PR #571] Two Windows-only F0 defects the first Windows CI job exposed
    ```
  - Promote: `triage_promote.py --id trg-eed74a42 --task-ref EXT:<ref>`

<a id="trg-e31066d8"></a>
- **P2.44 \[AUTO\] Three subprocess reads decode captured output strictly and can raise on non-UTF-8** `id=trg-e31066d8 | severity=low | kind=bug → P3/engineering`
  - Same class as the triage-log seam fixed in iterate-2026-08-06-gc-decode-parity, but in call sites that iterate did not…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.44 [AUTO] Three subprocess reads decode captured output strictly and can raise on non-UTF-8
    ```
  - Promote: `triage_promote.py --id trg-e31066d8 --task-ref EXT:<ref>`

<a id="trg-cf683351"></a>
- **P2.41a \[AUTO after P2.41\] Gate-mode reader and orchestrator reader still diverge on the read leg** `id=trg-cf683351 | severity=low | kind=bug → P3/engineering`
  - gate\_policy.read\_run\_config\_mode reads the run config with a plain Path.read\_text, while orchestrator\_pkg.config\…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.41a [AUTO after P2.41] Gate-mode reader and orchestrator reader still diverge on the read leg
    ```
  - Promote: `triage_promote.py --id trg-cf683351 --task-ref EXT:<ref>`

<a id="trg-d13da21d"></a>
- **P2.18b \[AUTO after P2.18\] Provenance stamp writes an LF line into a CRLF document** `id=trg-d13da21d | severity=low | kind=bug → P3/engineering`
  - FOUND 2026-08-06 by the Stage-2 code reviewer during iterate-2026-08-05-adopt-derived-evidence-rollout. NOT introduced…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.18b [AUTO after P2.18] Provenance stamp writes an LF line into a CRLF document
    ```
  - Promote: `triage_promote.py --id trg-d13da21d --task-ref EXT:<ref>`

<a id="trg-ab3e167f"></a>
- **P2.42a \[AUTO after P2.42\] Two phase-quality audit lifecycle gaps the run-id seam exposed** `id=trg-ab3e167f | severity=low | kind=bug → P3/engineering`
  - BUNDLES trg-276994a4 and trg-b36fd844. Both fell out of iterate-2026-08-06-resolve-run-id-seam \(P2.42\), both are life…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.42a [AUTO after P2.42] Two phase-quality audit lifecycle gaps the run-id seam exposed
    ```
  - Promote: `triage_promote.py --id trg-ab3e167f --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-9cd55b79"></a>
- **Compliance: 5 open finding\(s\)** `id=trg-9cd55b79 | severity=high | kind=compliance → P1/compliance`
  - 5 open compliance finding\(s\): D/D1, D/D3, F/F6, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Shou…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 5 open compliance finding(s): D/D1, D/D3, F/F6, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-9cd55b79 --task-ref EXT:<ref>`

### Source: context-cost-measurement (8 items)

<a id="trg-b364baa6"></a>
- **TC3.3 \(auto, serial 3/3\) Persist the iterate state that currently exists only in the conversation, so a compaction ca…** `id=trg-b364baa6 | severity=high | kind=improvement → P1/engineering`
  - AUTONOMOUS: yes.  OBSERVED 2026-08-07, two of two runs: both iterates compacted, one of them DURING its external review…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-b364baa6 --task-ref EXT:<ref>`

<a id="trg-77811f9b"></a>
- **TC3.1 \(auto, serial 1/3\) Stop ignoring the decision-drops folder in three places, including the template every adopte…** `id=trg-77811f9b | severity=high | kind=improvement → P1/engineering`
  - AUTONOMOUS: yes.  Re-filed to add the third location, which the earlier version missed: fixing only this repo would lea…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-77811f9b --task-ref EXT:<ref>`

<a id="trg-e6bbcf7b"></a>
- **TC1.3 \(auto\) opus-plan-reviewer is invoked by nothing, so the plan gate falls back to self-assessment** `id=trg-e6bbcf7b | severity=high | kind=bug → P1/engineering`
  - AUTONOMOUS: yes. Wiring only — model tiering is trg-88621183's job, not this card's.  Narrowed from an earlier version…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-e6bbcf7b --task-ref EXT:<ref>`

<a id="trg-a3880058"></a>
- **TC4.1 \(auto, last\) Document the strategies for keeping token cost controllable, organised by when a project needs them** `id=trg-a3880058 | severity=medium | kind=feature → P2/engineering`
  - AUTONOMOUS: yes.  Re-filed on operator direction: this must NOT read as a report of what we measured. It is a how-to, o…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-a3880058 --task-ref EXT:<ref>`

<a id="trg-c0d83dce"></a>
- **TC3.2 \(auto, serial 2/3\) A truncated mandated context load is never reported, so the governance guarantee voids itsel…** `id=trg-c0d83dce | severity=medium | kind=bug → P2/engineering`
  - AUTONOMOUS: yes. Small — a check, not an architecture.  WHAT "MANDATED LOAD" MEANS: \`references/context-loading.md\` i…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-c0d83dce --task-ref EXT:<ref>`

<a id="trg-f30e675e"></a>
- **TC2.1 \(auto\) Fill the context-index selection keys from the sources that already hold them, and declare the one that…** `id=trg-f30e675e | severity=medium | kind=improvement → P2/engineering`
  - AUTONOMOUS: yes.  LANDMINE: \`.shipwright/runtime/events-context-index.json\` has 815 entries and the right envelope wi…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-f30e675e --task-ref EXT:<ref>`

<a id="trg-cfa5521f"></a>
- **TC1.2 \(auto\) Extend the existing ADR index producer to decision\_log.md and the decision drops, reusing its drift gua…** `id=trg-cfa5521f | severity=medium | kind=improvement → P2/engineering`
  - AUTONOMOUS: yes.  Re-filed after verifying against the CODE rather than the card list. Two earlier versions of this car…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-cfa5521f --task-ref EXT:<ref>`

<a id="trg-9f21f727"></a>
- **TC1.1 \(auto\) Windows Tests job runs 25-28 min on double-billed runners with no xdist, while its own config proves 8 w…** `id=trg-9f21f727 | severity=low | kind=improvement → P3/engineering`
  - AUTONOMOUS: yes.  WHAT IT IS — it is new, which is why it looks unfamiliar: landed 2026-08-05 via #571 \(IT-9 Unit 5\).…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-9f21f727 --task-ref EXT:<ref>`

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

### Source: github (1 item)

<a id="trg-133f2ca6"></a>
- **GitHub prompt-injection: 1 finding\(s\) \(medium\)** `id=trg-133f2ca6 | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection \(prompt\_risks.json\): 1 medium \| run: https://github.com/svenroth-ai…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security prompt-injection scan reports 1 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 1 medium.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/31105738285
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-133f2ca6 --task-ref EXT:<ref>`

### Source: it1-audit-split (2 items)

<a id="trg-57d0d6d3"></a>
- **P2.19g \[AUTO\] Outbox buffer: superseded appends accumulate, and a deeply nested value is mis-read** `id=trg-57d0d6d3 | severity=medium | kind=bug → P2/engineering`
  - Zwei Reste aus iterate-2026-08-05-it1-audit-remainder, beide bewusst dort NICHT behoben. Ein Iterate kann beide ziehen…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-57d0d6d3 --task-ref EXT:<ref>`

<a id="trg-ca82a057"></a>
- **P2.19e \[AUTO after P2.19a\] Merge the duplicated git-state predicates \(IT-1 audit 29\)** `id=trg-ca82a057 | severity=low | kind=improvement → P3/engineering`
  - Aus trg-79102ee3 aufgeteilt; bewusst ein eigener kleiner Iterate, damit der Review der Datenverlust-Fixes nicht mit rei…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.19e [AUTO after P2.19a] Merge the duplicated git-state predicates (IT-1 audit 29)
    ```
  - Promote: `triage_promote.py --id trg-ca82a057 --task-ref EXT:<ref>`

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

### Source: iterate-2026-08-05-pr-review-fork-resolve (1 item)

<a id="trg-bbd17f4e"></a>
- **IT-9 workflow file: 5 more PR-review hardening items from webui#338, beyond the resolver fix** `id=trg-bbd17f4e | severity=medium | kind=improvement → P2/engineering`
  - BELONGS TO IT-9. IT-9 owns EVERY file under .github/workflows/ exclusively; no other card may touch a workflow file. it…
  - Promote: `triage_promote.py --id trg-bbd17f4e --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-88621183"></a>
- **P2.45 \[AUTO\]\[COST\] ModelConfig: per-run model-tier flags for review, finalization and execution** `id=trg-88621183 | severity=medium | kind=improvement → P2/engineering`
  - PROBLEM. Agent definitions carry model: inherit, so every subagent runs on whatever the main session runs on. When the…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate ModelConfig: add --review-model / --finalization-model / --execution-model flags plus a project default
    ```
  - Promote: `triage_promote.py --id trg-88621183 --task-ref EXT:<ref>`

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

### Source: required-checks (1 item)

<a id="trg-f3f5bd8c"></a>
- **must-pass check set does not match the checks the project has** `id=trg-f3f5bd8c | severity=medium | kind=improvement → P2/engineering`
  - Runs but gates nothing on svenroth-ai/shipwright@main — these checks report a result on every pull request and hold not…
  - Promote: `triage_promote.py --id trg-f3f5bd8c --task-ref EXT:<ref>`

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

