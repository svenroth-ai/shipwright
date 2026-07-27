# Triage Inbox

> Auto-generated 2026-07-27T17:38:49.456380Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 424
- Triage: 20 | Promoted: 1 | Dismissed: 402 | Snoozed: 1

## Top 20 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-554786d0"></a>
- **Compliance: 4 open finding(s)** `id=trg-554786d0 | severity=high | kind=compliance → P1/compliance`
  - 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must: FR-01.…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-554786d0 --task-ref EXT:<ref>`

### Source: f0-suite (1 item)

<a id="trg-7a4c0da7"></a>
- **[f0] shipwright-run failed in parallel and passed alone - race or flaky test** `id=trg-7a4c0da7 | severity=high | kind=bug → P1/engineering`
  - shipwright-run: red in parallel (rc 1), GREEN alone (rc 0). It is NOT xdist-allowlisted, so this is inter-unit pollutio…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --type bug
    
    Context: F0 suite card f0-race:shipwright-run. The test unit shipwright-run failed while the units ran side by side and passed when re-run alone, so the gate stayed green and nothing else recorded it.
    Reproduce alone (expect GREEN): cd plugins/shipwright-run && uv run --with pytest --with pytest-mock pytest tests -q -p no:cacheprovider
    Reproduce in parallel (expect intermittent RED): uv run shared/scripts/tools/run_test_suite.py --project-root 'C:\01_Development\shipwright\.worktrees\adopt-derived-catalogue'
    Establish whether it is a race between units or an unreliable test, fix the cause, and close this card. Never weaken or delete the test to make it pass.
    ```
  - Promote: `triage_promote.py --id trg-7a4c0da7 --task-ref EXT:<ref>`

### Source: github (2 items)

<a id="trg-2b5ca5f5"></a>
- **GitHub security: 1 code-scanning + 0 Dependabot (high)** `id=trg-2b5ca5f5 | severity=high | kind=bug → P1/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: 1 high \| dependabot: 0 \| see https://github.com/svenroth-ai/shipwright/…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: GitHub reports 1 open code-scanning finding(s) and 0 open Dependabot alert(s) for svenroth-ai/shipwright.
    Severity breakdown — code-scanning: 1 high; dependabot: 0.
    Live state: https://github.com/svenroth-ai/shipwright/security
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-2b5ca5f5 --task-ref EXT:<ref>`

<a id="trg-8481c271"></a>
- **GitHub prompt-injection: 1 finding(s) (medium)** `id=trg-8481c271 | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection (prompt_risks.json): 1 medium \| run: https://github.com/svenroth-ai/sh…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security prompt-injection scan reports 1 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 1 medium.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/30276486297
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-8481c271 --task-ref EXT:<ref>`

### Source: iterate (2 items)

<a id="trg-bd4e75a9"></a>
- **Phase-canon C3 handoff freshness still keys on mtime** `id=trg-bd4e75a9 | severity=low | kind=improvement → P3/engineering`
  - The F11 iterate freshness check moved off filesystem mtime to a content key in iterate-2026-07-27-name-the-blocker (it…
  - Evidence: `shared/scripts/tools/verifiers/common.py`
  - Promote: `triage_promote.py --id trg-bd4e75a9 --task-ref EXT:<ref>`

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

### Source: iterate-2026-07-19-compliance-prework (1 item)

<a id="trg-8bf97fd4"></a>
- **S2b: converge the requirement-discovery filter semantics (~10 call-site decisions)** `id=trg-8bf97fd4 | severity=medium | kind=improvement → P2/engineering`
  - The tail of campaign step S2, not a new campaign - file it now so it is not lost between "S2 merged" and "somebody noti…
  - Promote: `triage_promote.py --id trg-8bf97fd4 --task-ref EXT:<ref>`

### Source: manual (3 items)

<a id="trg-2ca796f3"></a>
- **Release aggregator can write the same version twice on a re-run** `id=trg-2ca796f3 | severity=high | kind=bug → P1/engineering`
  - aggregate_changelog.py is the writer the release path actually invokes (changelog SKILL.md Step 4). _insert_section alw…
  - Evidence: `.shipwright/planning/iterate/iterate-2026-07-27-changelog-writer-preserve-history.md`
  - Promote: `triage_promote.py --id trg-2ca796f3 --task-ref EXT:<ref>`

<a id="trg-efca9de7"></a>
- **shared/tests and integration-tests fail 21 tests when run in one pytest session** `id=trg-efca9de7 | severity=medium | kind=bug → P2/engineering`
  - Running 'uv run pytest shared/tests integration-tests -m "not slow and not cross_plugin"' as a SINGLE invocation fails…
  - Promote: `triage_promote.py --id trg-efca9de7 --task-ref EXT:<ref>`

<a id="trg-c6e75011"></a>
- **shipwright-security tests write an untracked .shipwright/ dir into the repo tree** `id=trg-c6e75011 | severity=low | kind=bug → P3/engineering`
  - Running the F0 suite leaves an untracked directory in the working tree: plugins/shipwright-security/.shipwright/ contai…
  - Promote: `triage_promote.py --id trg-c6e75011 --task-ref EXT:<ref>`

### Source: req3-campaign (3 items)

<a id="trg-137f48b5"></a>
- **REQ3.05 [CAMPAIGN AUTONOM] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-137f48b5 | severity=medium | kind=improvement → P2/engineering`
  - Der Coverage-Motor, eigener Anker damit er nicht nachgeschleift wird. Schreibt Tests fuer ACs, die heute keinen beweise…
  - Promote: `triage_promote.py --id trg-137f48b5 --task-ref EXT:<ref>`

<a id="trg-b5bd4a0a"></a>
- **REQ3.10 [ITERATE] Grader Lead-Magnet: change_reconciliation real machen** `id=trg-b5bd4a0a | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv. Der Grader reserviert change_reconciliation bereits als 'Shipwright-only'-Dimension (kappt kalte R…
  - Promote: `triage_promote.py --id trg-b5bd4a0a --task-ref EXT:<ref>`

<a id="trg-7085d783"></a>
- **REQ3.04 [CAMPAIGN AUTONOM] Mechanik - Monorepo** `id=trg-7085d783 | severity=medium | kind=improvement → P2/engineering`
  - Phase 3, AUTONOME Kampagne. Sub-Iterates: Evidenzkette (CI regeneriert Manifest, muss matchen), AC-Identitaet, Manifest…
  - Promote: `triage_promote.py --id trg-7085d783 --task-ref EXT:<ref>`

### Source: req3-granularity-round (1 item)

<a id="trg-1d7d91d0"></a>
- **Spec-coherence check S5 is blind to the converged acceptance-criteria shape** `id=trg-1d7d91d0 | severity=medium | kind=bug → P2/engineering`
  - check_s5_fr_coherence reports every requirement in this repo's own catalogue as missing both description and acceptance…
  - Evidence: `.shipwright/planning/iterate/2026-07-27-project-granularity-basis.md`
  - Promote: `triage_promote.py --id trg-1d7d91d0 --task-ref EXT:<ref>`

### Source: req3-phase2-walk (5 items)

<a id="trg-b95ab887"></a>
- **REQ3.06 [CAMPAIGN AUTONOM] Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only (mechanisable) - Monorepo** `id=trg-b95ab887 | severity=high | kind=improvement → P1/engineering`
  - AUTONOME Kampagne. Der Anker, der die Enforcement-Liste des AC-Nachweis-Registers abarbeitet - das Register IST die Arb…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-b95ab887 --task-ref EXT:<ref>`

<a id="trg-c7e5835b"></a>
- **host checks: gates that gate nothing, plus the verdict label (supersedes trg-2f9865fb)** `id=trg-c7e5835b | severity=high | kind=improvement → P1/engineering`
  - OWNS: everything under the workflows directory, the shipped workflow templates, and the must-pass-check derivation help…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-c7e5835b --task-ref EXT:<ref>`

<a id="trg-12b4cf3f"></a>
- **test phase: make the run record tell the truth (supersedes trg-0516e85e, stamping moved out)** `id=trg-12b4cf3f | severity=high | kind=improvement → P1/engineering`
  - OWNS: the test plugin, the test-phase validator branch, and the browser-test result reader. Does NOT own artifact stamp…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-12b4cf3f --task-ref EXT:<ref>`

<a id="trg-e9e5188e"></a>
- **requirement write-back loop: design and build both need the same missing mechanism (supersedes trg-35785118, trg-ed419f…** `id=trg-e9e5188e | severity=high | kind=improvement → P1/engineering`
  - One work unit because it is ONE mechanism with two call sites, not two plugin problems. Bundling supersedes trg-3578511…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-e9e5188e --task-ref EXT:<ref>`

<a id="trg-e9fa7c49"></a>
- **REQ3.09 [ITERATE] Domaenen-Glossar erzeugen, Grill-Modul in Project, plus die Nachweis-Spur (supersedes trg-d5522f68)** `id=trg-e9fa7c49 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv, Follow-up nach der Kampagne. OWNS: die Elicitation-Oberflaeche von PROJECT, das geteilte Grill-Mod…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-e9fa7c49 --task-ref EXT:<ref>`

