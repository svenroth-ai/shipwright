# Triage Inbox

> Auto-generated 2026-08-05T20:23:09.795210Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 641
- Triage: 28 | Promoted: 2 | Dismissed: 608 | Snoozed: 3

## Top 28 items (severity-sorted)

### Source: board-normalization (2 items)

<a id="trg-93374d55"></a>
- **P2.34 \[GUIDED\]\[CROSS-REPO\]\[SPLIT BEFORE BUILD\] Align WebUI and Python triage transition locking** `id=trg-93374d55 | severity=high | kind=bug → P1/engineering`
  - Follow-up to PR #539 / iterate-2026-08-01-triage-defer-lifecycle. Python writers use the shared FileLock while shipwrig…
  - Promote: `triage_promote.py --id trg-93374d55 --task-ref EXT:<ref>`

<a id="trg-b59168ec"></a>
- **P3.06 \[SERIAL 6/6 after P3.05\]\[UNBLOCKED\] Tier must use review evidence, not maintainer authorship** `id=trg-b59168ec | severity=medium | kind=improvement → P2/engineering`
  - Final IT-9 workflow unit, still serial after P3.05 because all six units own .github/workflows. The former review-recor…
  - Promote: `triage_promote.py --id trg-b59168ec --task-ref EXT:<ref>`

### Source: board-split (14 items)

<a id="trg-66cb695e"></a>
- **P2.18 \[GUIDED\] Adopted repos need current evidence, scope shrank after Weg B** `id=trg-66cb695e | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-515060a6, whose text says 'do not start before the architecture decision falls'. It has fallen: Weg B is…
  - Promote: `triage_promote.py --id trg-66cb695e --task-ref EXT:<ref>`

<a id="trg-210fde7b"></a>
- **P3.05 \[SERIAL 5/6 after P3.04\] No CI job runs on Windows** `id=trg-210fde7b | severity=high | kind=improvement → P1/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-210fde7b --task-ref EXT:<ref>`

<a id="trg-faa3857c"></a>
- **P2.17 \[GUIDED\] No review pass asks whether the architecture is the right one** `id=trg-faa3857c | severity=high | kind=improvement → P1/engineering`
  - Split out of anchor trg-fc173418 \(7a delivered, 7b delivered PR #514, 7d is trg-e4156151\). The cascade checks the dif…
  - Promote: `triage_promote.py --id trg-faa3857c --task-ref EXT:<ref>`

<a id="trg-55e3bdb8"></a>
- **P2.36 \[AUTO\] F0 console report dies on a Windows codepage when captured test output is non-cp1252** `id=trg-55e3bdb8 | severity=medium | kind=bug → P2/engineering`
  - SUPERSEDES trg-96a0ac9f - same content, placed in the phase scheme. Raised by iterate-2026-08-05-iterate-timings-derive…
  - Promote: `triage_promote.py --id trg-55e3bdb8 --task-ref EXT:<ref>`

<a id="trg-0bb180f6"></a>
- **P2.30 \[SERIAL after P2.26\] F11 refuses a previous-run fallback when current evidence is unreadable** `id=trg-0bb180f6 | severity=medium | kind=bug → P2/engineering`
  - SUPERSEDES trg-e0a0f569 and preserves its measured finding. spec\_checks.\_read\_iterate\_entry and iterate\_compliance…
  - Promote: `triage_promote.py --id trg-0bb180f6 --task-ref EXT:<ref>`

<a id="trg-2c958bad"></a>
- **P2.29 \[AUTO\] Cross-plugin mirror tree joins the cache drift check** `id=trg-2c958bad | severity=medium | kind=improvement → P2/engineering`
  - SUPERSEDES trg-5005bf57 and preserves its scope. P1.07 and P1.08 are delivered, so this is now unblocked. The plugin ca…
  - Promote: `triage_promote.py --id trg-2c958bad --task-ref EXT:<ref>`

<a id="trg-abd0a247"></a>
- **P3.04 \[SERIAL 4/6 after P3.03\] The security gate reports a blank pass while high findings are open** `id=trg-abd0a247 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-abd0a247 --task-ref EXT:<ref>`

<a id="trg-14d46892"></a>
- **P3.02 \[SERIAL 2/6 after P3.01\] Fork PRs get no model review, the host withholds credentials** `id=trg-14d46892 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-14d46892 --task-ref EXT:<ref>`

<a id="trg-569bc60b"></a>
- **P3.01 \[SERIAL 1/6\] The scaffolded reviewer skips large changes instead of failing closed** `id=trg-569bc60b | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-569bc60b --task-ref EXT:<ref>`

<a id="trg-8b5f8f40"></a>
- **P2.16 \[GUIDED\] An unreadable run config reads as standalone** `id=trg-8b5f8f40 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-040223fe. \_read\_standalone\_flag treats an unparseable config like a missing one and answers…
  - Promote: `triage_promote.py --id trg-8b5f8f40 --task-ref EXT:<ref>`

<a id="trg-5b45c165"></a>
- **P2.19 \[GUIDED\] Remaining IT-1 audit findings 14 and 20-29** `id=trg-5b45c165 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-4ebc928e, which is now closed. These were deliberately kept in the anchor rather than filed as…
  - Promote: `triage_promote.py --id trg-5b45c165 --task-ref EXT:<ref>`

<a id="trg-095cd2bf"></a>
- **P2.20 \[GUIDED\] Accepted-risk register: should it gain a schema field** `id=trg-095cd2bf | severity=low | kind=improvement → P3/engineering`
  - SUPERSEDES trg-87174b37 - retitled into the phase scheme, content unchanged \(full text on the original\). Monorepo onl…
  - Promote: `triage_promote.py --id trg-095cd2bf --task-ref EXT:<ref>`

<a id="trg-01cd6aef"></a>
- **P2.15 \[GUIDED\] F11 handoff freshness and the derived-snapshot gate contradict** `id=trg-01cd6aef | severity=low | kind=bug → P3/engineering`
  - SUPERSEDES trg-758e62c0 - retitled into the phase scheme, content unchanged \(full text on the original\). Pairs with P…
  - Promote: `triage_promote.py --id trg-01cd6aef --task-ref EXT:<ref>`

<a id="trg-a089c9f7"></a>
- **P3.03 \[SERIAL 3/6 after P3.02\] The must-pass set is never compared against the checks that exist** `id=trg-a089c9f7 | severity=low | kind=improvement → P3/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-a089c9f7 --task-ref EXT:<ref>`

### Source: code-review (1 item)

<a id="trg-2b14d892"></a>
- **Stale triage claim trg-0ce59c05: adopt templates already on codeql-action v4** `id=trg-2b14d892 | severity=low | kind=maintenance → P3/engineering`
  - trg-0ce59c05 \(2026-07-18\) asserted shared/templates/github-actions/\*.template already shipped github/codeql-action/.…
  - Promote: `triage_promote.py --id trg-2b14d892 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-76320e3a"></a>
- **Compliance: 5 open finding\(s\)** `id=trg-76320e3a | severity=high | kind=compliance → P1/compliance`
  - 5 open compliance finding\(s\): D/D1, D/D3, F/F6, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Shou…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 5 open compliance finding(s): D/D1, D/D3, F/F6, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-76320e3a --task-ref EXT:<ref>`

### Source: doubt-reviewer (1 item)

<a id="trg-486cb11c"></a>
- **P2.27 \[GUIDED after P2.08\] Decide how verify\_local.py gets run: pre-push hook, F0 step, or manual** `id=trg-486cb11c | severity=medium | kind=improvement → P2/engineering`
  - verify\_local.py mirrors ci.yml's three bespoke merge guards locally, but nothing invokes it: no hook, no SKILL.md step…
  - Promote: `triage_promote.py --id trg-486cb11c --task-ref EXT:<ref>`

### Source: github (1 item)

<a id="trg-5d409a6a"></a>
- **GitHub prompt-injection: 2 finding\(s\) \(medium\)** `id=trg-5d409a6a | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection \(prompt\_risks.json\): 2 medium \| run: https://github.com/svenroth-ai…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security prompt-injection scan reports 2 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 2 medium.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/30996996377
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-5d409a6a --task-ref EXT:<ref>`

### Source: iterate-2026-08-01-drop-write-once-step-fields (1 item)

<a id="trg-8d52a965"></a>
- **Retire the write-once current\_step / completed\_steps fields \(campaign, not a P3 unit\)** `id=trg-8d52a965 | severity=medium | kind=improvement → P2/engineering`
  - Successor to trg-be24ff6f, which asked to migrate two phase\_quality readers to phase\_tasks\[\] and 'then drop the fie…
  - Promote: `triage_promote.py --id trg-8d52a965 --task-ref EXT:<ref>`

### Source: iterate-2026-08-01-grade-snapshot-dirty-capture (1 item)

<a id="trg-709828ad"></a>
- **P4.02 \[GUIDED\] grade\_snapshot dirty: the orchestrator's sibling-process residual** `id=trg-709828ad | severity=low | kind=improvement → P3/engineering`
  - Left open deliberately by iterate-2026-08-01-grade-snapshot-dirty-capture, which shipped grade\_snapshot.dirty captured…
  - Promote: `triage_promote.py --id trg-709828ad --task-ref EXT:<ref>`

### Source: req3-campaign (3 items)

<a id="trg-c396f7d8"></a>
- **REQ3.04 \[CAMPAIGN AUTONOM\] Mechanik Monorepo plus der Spec-Reader \(supersedes trg-7085d783\)** `id=trg-c396f7d8 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-7085d783, KONSOLIDIERT zusaetzlich trg-1d7d91d0 + trg-2ea0b99a + trg-8bf97fd4. Owner-Entscheidung 2026-0…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-c396f7d8 --task-ref EXT:<ref>`

<a id="trg-137f48b5"></a>
- **REQ3.05 \[CAMPAIGN AUTONOM\] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-137f48b5 | severity=medium | kind=improvement → P2/engineering`
  - Der Coverage-Motor, eigener Anker damit er nicht nachgeschleift wird. Schreibt Tests fuer ACs, die heute keinen beweise…
  - Promote: `triage_promote.py --id trg-137f48b5 --task-ref EXT:<ref>`

<a id="trg-b5bd4a0a"></a>
- **REQ3.10 \[ITERATE\] Grader Lead-Magnet: change\_reconciliation real machen** `id=trg-b5bd4a0a | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv. Der Grader reserviert change\_reconciliation bereits als 'Shipwright-only'-Dimension \(kappt kalte…
  - Promote: `triage_promote.py --id trg-b5bd4a0a --task-ref EXT:<ref>`

### Source: req3-phase2-walk (2 items)

<a id="trg-b95ab887"></a>
- **REQ3.06 \[CAMPAIGN AUTONOM\] Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only \(mechanisable\) - Monorepo** `id=trg-b95ab887 | severity=high | kind=improvement → P1/engineering`
  - AUTONOME Kampagne. Der Anker, der die Enforcement-Liste des AC-Nachweis-Registers abarbeitet - das Register IST die Arb…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-b95ab887 --task-ref EXT:<ref>`

<a id="trg-e9fa7c49"></a>
- **REQ3.09 \[ITERATE\] Domaenen-Glossar erzeugen, Grill-Modul in Project, plus die Nachweis-Spur \(supersedes trg-d5522f68…** `id=trg-e9fa7c49 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv, Follow-up nach der Kampagne. OWNS: die Elicitation-Oberflaeche von PROJECT, das geteilte Grill-Mod…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-e9fa7c49 --task-ref EXT:<ref>`

### Source: triage-consolidation-2026-07-28 (1 item)

<a id="trg-66b45477"></a>
- **IT-10 Plugin-Scope-Split: Einstiegs-Plugins global, 11 Pipeline-Plugins projekt-scoped** `id=trg-66b45477 | severity=medium | kind=improvement → P2/engineering`
  - SUPERSEDES trg-57317128 - inhaltlich unveraendert, nur in das IT-Schema umbenannt, damit das Board einheitlich ist. Spe…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-66b45477 --task-ref EXT:<ref>`

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

