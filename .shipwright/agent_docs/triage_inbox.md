# Triage Inbox

> Auto-generated 2026-07-27T08:23:12.722139Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 416
- Triage: 25 | Promoted: 1 | Dismissed: 389 | Snoozed: 1

## Top 25 items (severity-sorted)

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

### Source: github (1 item)

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

### Source: iterate (1 item)

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

### Source: iterate-2026-07-19-compliance-prework (1 item)

<a id="trg-8bf97fd4"></a>
- **S2b: converge the requirement-discovery filter semantics (~10 call-site decisions)** `id=trg-8bf97fd4 | severity=medium | kind=improvement → P2/engineering`
  - The tail of campaign step S2, not a new campaign - file it now so it is not lost between "S2 merged" and "somebody noti…
  - Promote: `triage_promote.py --id trg-8bf97fd4 --task-ref EXT:<ref>`

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

### Source: req3-phase2-walk (16 items)

<a id="trg-74b945bc"></a>
- **CRITICAL - going back to a previous version does not use the version you ask for, and reports success** `id=trg-74b945bc | severity=critical | kind=bug → P0/engineering`
  - OWNS: the hosting plugin, the liveness check and the target profiles. Independently executable. Supersedes trg-c9dc5a16…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-74b945bc --task-ref EXT:<ref>`

<a id="trg-6690d175"></a>
- **CRITICAL - release-note writer destroys an existing history file it does not recognise** `id=trg-6690d175 | severity=critical | kind=bug → P0/engineering`
  - OWNS: the changelog plugin. Independently executable. Supersedes trg-7ad0849b (title only, so the severity is visible w…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-6690d175 --task-ref EXT:<ref>`

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

<a id="trg-1aa5a8ab"></a>
- **onboarding: a derived catalogue must announce itself as derived, and ask to be questioned** `id=trg-1aa5a8ab | severity=high | kind=improvement → P1/engineering`
  - OWNS: the onboarding plugin's artifact writers and its handover step. Independently executable; touches no other plugin…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-1aa5a8ab --task-ref EXT:<ref>`

<a id="trg-10597d50"></a>
- **change workflow: a concurrency warning must outlive the session, and loudly** `id=trg-10597d50 | severity=high | kind=improvement → P1/engineering`
  - OWNS: the change workflow's parallel test-gate runner. Independently executable; touches no other plugin and no workflo…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-10597d50 --task-ref EXT:<ref>`

<a id="trg-3f4d6b57"></a>
- **orchestrator: a waved-through phase leaves no trace; the handoff hides state it already has** `id=trg-3f4d6b57 | severity=high | kind=improvement → P1/engineering`
  - OWNS: the orchestrator's step-advance path and the session-handoff renderer. Independently executable; touches no workf…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-3f4d6b57 --task-ref EXT:<ref>`

<a id="trg-15a43b6b"></a>
- **security phase: coverage, one register, comparable runs, ask the scope (supersedes trg-9305ff98)** `id=trg-15a43b6b | severity=high | kind=improvement → P1/engineering`
  - OWNS: the security plugin's scanner wiring, its report generator and the presentation of security findings to the opera…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-15a43b6b --task-ref EXT:<ref>`

<a id="trg-12b4cf3f"></a>
- **test phase: make the run record tell the truth (supersedes trg-0516e85e, stamping moved out)** `id=trg-12b4cf3f | severity=high | kind=improvement → P1/engineering`
  - OWNS: the test plugin, the test-phase validator branch, and the browser-test result reader. Does NOT own artifact stamp…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-12b4cf3f --task-ref EXT:<ref>`

<a id="trg-4d5b6a56"></a>
- **stamp produced artifacts with the state they describe (extracted so it is built once)** `id=trg-4d5b6a56 | severity=high | kind=improvement → P1/engineering`
  - OWNS: the stamping helper plus its two call sites — the test-results writer and the compliance document renderers. Extr…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-4d5b6a56 --task-ref EXT:<ref>`

<a id="trg-88f721be"></a>
- **plan phase: disagreement between reviewers is averaged away, and section order cannot be checked** `id=trg-88f721be | severity=high | kind=improvement → P1/engineering`
  - Per-plugin work unit from the FR-01.03 scenario pass, plus the gaps the earlier walk had already recorded. (1) Two inde…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-88f721be --task-ref EXT:<ref>`

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

<a id="trg-813d2305"></a>
- **triage inbox: the terminal cannot defer, and a failing check's own text is uncapped** `id=trg-813d2305 | severity=medium | kind=improvement → P2/engineering`
  - OWNS: the triage command-line surface and the code-host action-unit mappers (shared/scripts/tools/triage_cli.py, triage…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-813d2305 --task-ref EXT:<ref>`

<a id="trg-a1fd8125"></a>
- **compliance: disclose when the cross-check last ran (supersedes trg-bee08d80, stamping moved out)** `id=trg-a1fd8125 | severity=medium | kind=improvement → P2/engineering`
  - OWNS: the compliance dashboard and report renderers. Does NOT own artifact stamping — that moved to its own card so it…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-a1fd8125 --task-ref EXT:<ref>`

<a id="trg-a8110d84"></a>
- **project phase: no notion of how big a requirement should be, and the templates contradict the basis rule** `id=trg-a8110d84 | severity=medium | kind=improvement → P2/engineering`
  - Per-plugin work unit from the FR-01.02 scenario pass. (1) Requirement granularity has no guidance and no check. There i…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-a8110d84 --task-ref EXT:<ref>`

