# Triage Inbox

> Auto-generated 2026-09-20T21:40:38.587295Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 965
- Triage: 11 | Promoted: 8 | Dismissed: 942 | Snoozed: 4

## Top 11 items (severity-sorted)

### Source: board-split (1 item)

<a id="trg-14392ba5"></a>
- **11 \[auto\] P2.17a: run architecture review inside campaign sub-iterates \(after 10\)** `id=trg-14392ba5 | severity=medium | kind=improvement → P2/engineering`
  - PR #582 added external\_review.py --mode architecture as a second call in the external review step, wired into /shipwri…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.17a [GUIDED after P2.17] Campaign sub-iterates do not run the architecture review pass
    ```
  - Promote: `triage_promote.py --id trg-14392ba5 --task-ref EXT:<ref>`

### Source: cli (1 item)

<a id="trg-9edb20d8"></a>
- **07 \[auto\] Sweep the 129 orphaned .test-results.json evidence files** `id=trg-9edb20d8 | severity=low | kind=maintenance → P3/engineering`
  - The sibling-sweep fix \(this run\) stops NEW orphans; it does not touch the ones retention already left behind before t…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-9edb20d8 --task-ref EXT:<ref>`

### Source: external\_review\_degradation (1 item)

<a id="trg-3a35d342"></a>
- **20 \[auto\] Find out why the opus reviewer arm returns no usable reply** `id=trg-3a35d342 | severity=medium | kind=maintenance → P2/engineering`
  - The opus reviewer arm did not return a usable reply during an external code review \(provider=claude\_cli\), while at l…
  - Promote: `triage_promote.py --id trg-3a35d342 --task-ref EXT:<ref>`

### Source: github (1 item)

<a id="trg-575a6f7f"></a>
- **15 \[auto\] Resolve the 3 open code-scanning alerts, 1 of them high** `id=trg-575a6f7f | severity=high | kind=bug → P1/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: 1 high, 2 low \| dependabot: 0 \| see https://github.com/svenroth-ai/ship…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: GitHub reports 3 open code-scanning finding(s) and 0 open Dependabot alert(s) for svenroth-ai/shipwright.
    Severity breakdown — code-scanning: 1 high, 2 low; dependabot: 0.
    Live state: https://github.com/svenroth-ai/shipwright/security
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-575a6f7f --task-ref EXT:<ref>`

### Source: internal-plan-review (1 item)

<a id="trg-0a3c4edb"></a>
- **Extend Codex reasoning-effort contract to plan\_review** `id=trg-0a3c4edb | severity=low | kind=improvement → P3/engineering`
  - AGENTS.md's stated "high reasoning for required review subagents" policy now reaches codex exec for spec/code/doubt \(i…
  - Promote: `triage_promote.py --id trg-0a3c4edb --task-ref EXT:<ref>`

### Source: iterate-2026-09-12-t7-compliance-grade (1 item)

<a id="trg-6bda0dbb"></a>
- **09 \[guided\] Stop D5 hard-failing a no-FR behavior change that FR-01.10/AC06 exempts** `id=trg-6bda0dbb | severity=medium | kind=compliance → P2/engineering`
  - AC06 requires: a completed change that says it affects behaviour, names no requirement, and gives no exemption reason i…
  - Promote: `triage_promote.py --id trg-6bda0dbb --task-ref EXT:<ref>`

### Source: iterate-2026-09-16-opus-review-leg-codex-driver (1 item)

<a id="trg-475c572f"></a>
- **18 \[auto\] Generalize the Adopt Layer-3 reviewer roster the way the external roster already was** `id=trg-475c572f | severity=medium | kind=improvement → P2/engineering`
  - iterate-2026-09-16-opus-review-leg-codex-driver generalized the external-review roster to {glm,opus} under --driver cod…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-475c572f --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-c196ba32"></a>
- **19 \[guided\] Schedule campaign sub-iterates from a dependency graph instead of one campaign-wide strategy** `id=trg-c196ba32 | severity=low | kind=improvement → P3/engineering`
  - Today a campaign's sub-iterates only carry a single campaign-wide branch\_strategy \(serial/stacked/independent/single-…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate <id>
    ```
  - Promote: `triage_promote.py --id trg-c196ba32 --task-ref EXT:<ref>`

### Source: operator-request (1 item)

<a id="trg-a0d8c2cb"></a>
- **10 \[guided\] P2.50: add an internal architecture review to the plan\_review tier** `id=trg-a0d8c2cb | severity=high | kind=improvement → P1/engineering`
  - REQUIREMENT \(operator, 2026-08-08\). The architecture review exists only as an EXTERNAL call. Give it an internal arm…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: P2.50 [GUIDED] The architecture review has no internal path, so it silently disappears on three separate routes
    ```
  - Promote: `triage_promote.py --id trg-a0d8c2cb --task-ref EXT:<ref>`

### Source: pr-770-review (1 item)

<a id="trg-affcd29f"></a>
- **17 \[auto\] Extend the worktree-read safeguard to the whole review cascade, not just the Codex leg** `id=trg-affcd29f | severity=medium | kind=improvement → P2/engineering`
  - PR #770 \(Codex internal-review transport\) merged with an accepted, disclosed read-access risk on the real worktree du…
  - Promote: `triage_promote.py --id trg-affcd29f --task-ref EXT:<ref>`

### Source: req3-campaign (1 item)

<a id="trg-a2a45d38"></a>
- **12 \[guided\] REQ3.10: make the grader's change\_reconciliation real \(run last\)** `id=trg-a2a45d38 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv. Der Grader reserviert change\_reconciliation bereits als 'Shipwright-only'-Dimension \(kappt kalte…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate
    
    Work item: REQ3.10: Grader Lead-Magnet: change_reconciliation real machen
    ```
  - Promote: `triage_promote.py --id trg-a2a45d38 --task-ref EXT:<ref>`

## Deferred — decided, revisit later (4)

_Not gone: each of these was decided, with a date it comes back on._

- **release.py: rollback + smoke-input scope gaps deferred until first real Jelastic use** `id=trg-45213a11 | severity=medium | revisit=2026-11-16`
  - Reason: Revisit once release.py has a real caller/usage to design the smoke-url allowlist and commit-pinned rollback against.
  - Un-park: `triage_cli.py unpark trg-45213a11 --reason <why>`

- **P4.03 \[GUIDED\] IT-10 Plugin-Scope-Split: entry plugins global, 11 pipeline plugins project-scoped** `id=trg-84a84f4e | severity=medium | revisit=2026-12-01`
  - Reason: Parked 2026-09-06 by the operator, WITH a date: a snooze without revisitAt never returns. Every repo he works in IS a S…
  - Un-park: `triage_cli.py unpark trg-84a84f4e --reason <why>`

- **The delivery ladder's self-merge rung has never run against a real unprotected repository** `id=trg-5c62fa56 | severity=medium | revisit=(no revisit date recorded)`
  - Reason: Re-homed to trg-a678bd00 \(Adopt Automerge-Readiness\). Rung 3 is unreachable here: main is protected and self-merge on…
  - Un-park: `triage_cli.py unpark trg-5c62fa56 --reason <why>`

- **Changelog aggregator does not preserve BOM / line endings the plugin writer preserves** `id=trg-239ee0ad | severity=low | revisit=(no revisit date recorded)`
  - Reason: P3, in PR #472 bewusst akzeptiert und an zwei Stellen dokumentiert \(Modul-Docstring changelog\_splice.py + Iterate-Spe…
  - Un-park: `triage_cli.py unpark trg-239ee0ad --reason <why>`

