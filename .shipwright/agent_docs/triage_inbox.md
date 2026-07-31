# Triage Inbox

> Auto-generated 2026-07-31T23:32:38.909412Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 544
- Triage: 27 | Promoted: 2 | Dismissed: 513 | Snoozed: 2

## Top 27 items (severity-sorted)

### Source: code-review-followup (1 item)

<a id="trg-36f182f3"></a>
- **dev_server derives its shared/scripts constant three ways and inserts it into sys.path twice** `id=trg-36f182f3 | severity=low | kind=improvement → P3/engineering`
  - After iterate-2026-07-31-shared-tests-parallel-flake, __init__.py derives shared/scripts with os.path at import (harden…
  - Promote: `triage_promote.py --id trg-36f182f3 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-fe236889"></a>
- **Compliance: 4 open finding(s)** `id=trg-fe236889 | severity=high | kind=compliance → P1/compliance`
  - 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must: FR-01.…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-fe236889 --task-ref EXT:<ref>`

### Source: f0-suite-followup (1 item)

<a id="trg-348386e4"></a>
- **F0 race card records THAT a unit raced but not WHICH test failed, so it cannot be diagnosed after the session ends** `id=trg-348386e4 | severity=medium | kind=improvement → P2/engineering`
  - suite_report.entry_detail composes the card from named scalars only and states outright that the failing output stayed…
  - Promote: `triage_promote.py --id trg-348386e4 --task-ref EXT:<ref>`

### Source: github (2 items)

<a id="trg-9b1a1286"></a>
- **[ci] Probe refresh-token bypass failing on main** `id=trg-9b1a1286 | severity=high | kind=bug → P1/engineering`
  - Workflow 'Probe refresh-token bypass' last concluded 'failure' on main@2a5b7d3 \| latest run: https://github.com/svenro…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --type bug
    
    Context: GitHub Actions workflow 'Probe refresh-token bypass' is failing on the default branch (main) in svenroth-ai/shipwright.
    Last conclusion: failure.
    Live workflow history: https://github.com/svenroth-ai/shipwright/actions/workflows/322548704
    Source: triage item gh-ci:322548704
    ```
  - Promote: `triage_promote.py --id trg-9b1a1286 --task-ref EXT:<ref>`

<a id="trg-c8d81fd7"></a>
- **GitHub prompt-injection: 1 finding(s) (high)** `id=trg-c8d81fd7 | severity=high | kind=bug → P1/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection (prompt_risks.json): 1 high \| run: https://github.com/svenroth-ai/ship…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security prompt-injection scan reports 1 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 1 high.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/30638995806
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-c8d81fd7 --task-ref EXT:<ref>`

### Source: iterate (1 item)

<a id="trg-e4156151"></a>
- **Promote the Stage-1 spec pass into reviews (webui reader is ready) -- NOT a one-liner** `id=trg-e4156151 | severity=medium | kind=improvement → P2/engineering`
  - The webui consumer half shipped 2026-07-31 (shipwright-webui PR #339, ce21323e): readReviewRecord now accepts review ty…
  - Evidence: `shared/scripts/lib/review_record_schema.py`
  - Promote: `triage_promote.py --id trg-e4156151 --task-ref EXT:<ref>`

### Source: iterate-2026-07-31-it5-classification-calibration (2 items)

<a id="trg-f872a6d7"></a>
- **F11 complexity gates turn two fail-closed coverage checks into green SKIPs below medium** `id=trg-f872a6d7 | severity=medium | kind=bug → P2/engineering`
  - Belongs to the IT-3 anchor (F11 fail-open paths). Two verifiers gate on the AGENT-REPORTED complexity before doing the…
  - Evidence: `.shipwright/planning/iterate/2026-07-31-it5-classification-calibration.md`
  - Promote: `triage_promote.py --id trg-f872a6d7 --task-ref EXT:<ref>`

<a id="trg-29b0f252"></a>
- **touches_build JS message patterns match inside longer filenames (Python half now guarded, JS half not)** `id=trg-29b0f252 | severity=low | kind=improvement → P3/engineering`
  - RISK_TAXONOMY['touches_build'] matches its patterns against the MESSAGE with re.search and no filename boundary, so the…
  - Evidence: `.shipwright/planning/iterate/2026-07-31-it5-classification-calibration.md`
  - Promote: `triage_promote.py --id trg-29b0f252 --task-ref EXT:<ref>`

### Source: iterate-2026-07-31-it7a-pr-review-stale-verdict F11 (1 item)

<a id="trg-758e62c0"></a>
- **F11 gate contradiction: 'session_handoff fresh' and 'no derived snapshots' cannot both be satisfied** `id=trg-758e62c0 | severity=low | kind=bug → P3/engineering`
  - Observed on PR #508, reproducible on any medium+ iterate.  verify_iterate_finalization runs both:   - 'session_handoff.…
  - Promote: `triage_promote.py --id trg-758e62c0 --task-ref EXT:<ref>`

### Source: iterate-measurement (1 item)

<a id="trg-6af8dc72"></a>
- **Triage-Delivery: eine aus CI gefilte Karte landet im gitignorierten Outbox und erreicht niemanden (gehoert zu IT-1)** `id=trg-6af8dc72 | severity=medium | kind=bug → P2/engineering`
  - GEHOERT ZU IT-1 (trg-4ebc928e, Triage-Store und Delivery haerten) - dort einhaengen, nicht separat abarbeiten.  MECHANI…
  - Promote: `triage_promote.py --id trg-6af8dc72 --task-ref EXT:<ref>`

### Source: manual (2 items)

<a id="trg-5c62fa56"></a>
- **The delivery ladder's self-merge rung has never run against a real unprotected repository** `id=trg-5c62fa56 | severity=medium | kind=improvement → P2/engineering`
  - PR #510 shipped a code path that MERGES a pull request when the code host structurally cannot arm auto-merge (base bran…
  - Promote: `triage_promote.py --id trg-5c62fa56 --task-ref EXT:<ref>`

<a id="trg-012db453"></a>
- **Derived compliance docs: build Weg B (release-time check-in + on-demand docs PR)** `id=trg-012db453 | severity=medium | kind=improvement → P2/engineering`
  - DECIDED 2026-07-30 by the operator: Weg B, with the open question answered ("does anyone read the evidence on main cont…
  - Evidence: `.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md`
  - Promote: `triage_promote.py --id trg-012db453 --task-ref EXT:<ref>`

### Source: req3-campaign (3 items)

<a id="trg-c396f7d8"></a>
- **REQ3.04 [CAMPAIGN AUTONOM] Mechanik Monorepo plus der Spec-Reader (supersedes trg-7085d783)** `id=trg-c396f7d8 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-7085d783, KONSOLIDIERT zusaetzlich trg-1d7d91d0 + trg-2ea0b99a + trg-8bf97fd4. Owner-Entscheidung 2026-0…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-c396f7d8 --task-ref EXT:<ref>`

<a id="trg-137f48b5"></a>
- **REQ3.05 [CAMPAIGN AUTONOM] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-137f48b5 | severity=medium | kind=improvement → P2/engineering`
  - Der Coverage-Motor, eigener Anker damit er nicht nachgeschleift wird. Schreibt Tests fuer ACs, die heute keinen beweise…
  - Promote: `triage_promote.py --id trg-137f48b5 --task-ref EXT:<ref>`

<a id="trg-b5bd4a0a"></a>
- **REQ3.10 [ITERATE] Grader Lead-Magnet: change_reconciliation real machen** `id=trg-b5bd4a0a | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv. Der Grader reserviert change_reconciliation bereits als 'Shipwright-only'-Dimension (kappt kalte R…
  - Promote: `triage_promote.py --id trg-b5bd4a0a --task-ref EXT:<ref>`

### Source: req3-phase2-walk (2 items)

<a id="trg-b95ab887"></a>
- **REQ3.06 [CAMPAIGN AUTONOM] Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only (mechanisable) - Monorepo** `id=trg-b95ab887 | severity=high | kind=improvement → P1/engineering`
  - AUTONOME Kampagne. Der Anker, der die Enforcement-Liste des AC-Nachweis-Registers abarbeitet - das Register IST die Arb…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-b95ab887 --task-ref EXT:<ref>`

<a id="trg-e9fa7c49"></a>
- **REQ3.09 [ITERATE] Domaenen-Glossar erzeugen, Grill-Modul in Project, plus die Nachweis-Spur (supersedes trg-d5522f68)** `id=trg-e9fa7c49 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv, Follow-up nach der Kampagne. OWNS: die Elicitation-Oberflaeche von PROJECT, das geteilte Grill-Mod…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-e9fa7c49 --task-ref EXT:<ref>`

### Source: shipwright-webui iterate-2026-07-29-accepted-risk-ci-gate (external + Codex review) (1 item)

<a id="trg-87174b37"></a>
- **SecFix-5 (monorepo, NOT AUTONOMOUS - schema decision): should the accepted-risk register gain an entry type for inline…** `id=trg-87174b37 | severity=low | kind=improvement → P3/engineering`
  - Filed from shipwright-webui. SecFix-1..5 are one family; this is the only member that must NOT run unattended, which is…
  - Promote: `triage_promote.py --id trg-87174b37 --task-ref EXT:<ref>`

### Source: triage-consolidation (2 items)

<a id="trg-fc173418"></a>
- **IT-7 (neu) Die Review-Maschinerie schliesst ihren Kreis: totes Verdict, fehlende Cascade, fehlender Architektur-Pass, s…** `id=trg-fc173418 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-1a815ff2 - 7a und 7b inhaltlich UNVERAENDERT, zwei Mitglieder kommen dazu. KONSOLIDIERT zusaetzlich trg-…
  - Promote: `triage_promote.py --id trg-fc173418 --task-ref EXT:<ref>`

<a id="trg-515060a6"></a>
- **IT-11 (neu nach dem Architektur-Review) Adoptierte Repos brauchen aktuelle Evidenz - aber wahrscheinlich OHNE Refresh-P…** `id=trg-515060a6 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-c5b05f31. Grund fuer die Neufassung: der alte Text sagt 'die Entscheidung muss fallen, BEVOR der Refresh…
  - Promote: `triage_promote.py --id trg-515060a6 --task-ref EXT:<ref>`

### Source: triage-consolidation-2026-07-28 (6 items)

<a id="trg-bd66b9b0"></a>
- **IT-9 (neu) Host-Checks: Gates die nichts gaten, das Verdict-Label, kein Windows-CI, und der Tier der sich auf Autorscha…** `id=trg-bd66b9b0 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-e3f79524 (das trg-c7e5835b supersedete, das trg-2f9865fb supersedete), KONSOLIDIERT zusaetzlich trg-51f6…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-bd66b9b0 --task-ref EXT:<ref>`

<a id="trg-4ebc928e"></a>
- **IT-1 Triage-Store und Delivery haerten: 3 verifizierte High plus ~29 Audit-Befunde** `id=trg-4ebc928e | severity=high | kind=bug → P1/engineering`
  - KONSOLIDIERT trg-7b6f13df + trg-93ceb2b0 + trg-51f8e2a1 + trg-0a294ef3. DREI Iterates unter EINEM Anker, interleaved-se…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`
  - Promote: `triage_promote.py --id trg-4ebc928e --task-ref EXT:<ref>`

<a id="trg-66b45477"></a>
- **IT-10 Plugin-Scope-Split: Einstiegs-Plugins global, 11 Pipeline-Plugins projekt-scoped** `id=trg-66b45477 | severity=medium | kind=improvement → P2/engineering`
  - SUPERSEDES trg-57317128 - inhaltlich unveraendert, nur in das IT-Schema umbenannt, damit das Board einheitlich ist. Spe…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-66b45477 --task-ref EXT:<ref>`

<a id="trg-ac4fc684"></a>
- **IT-2 (neu nach PR #490) Grade-Snapshot: Dirty-State erfassen statt messen, plus das Emissionsvolumen** `id=trg-ac4fc684 | severity=medium | kind=bug → P2/engineering`
  - SUPERSEDES trg-4bbbd233 (angelegt 2026-07-28 ~11:00), KONSOLIDIERT trg-10aa91e3 + trg-d190cc37. Grund fuer die Neufassu…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-ac4fc684 --task-ref EXT:<ref>`

<a id="trg-e0a00235"></a>
- **IT-8 Die lokale Entwicklungsschleife berichtet die Wahrheit (2 von 3 sind Dismiss-Kandidaten)** `id=trg-e0a00235 | severity=medium | kind=improvement → P2/engineering`
  - KONSOLIDIERT trg-ecddb31f + trg-410ef2a6 + trg-c6e75011. Drei Faelle, in denen das Dev-Setup dem Entwickler etwas Falsc…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-e0a00235 --task-ref EXT:<ref>`

<a id="trg-040223fe"></a>
- **IT-6 Run-Config-Integritaet: eine unlesbare Config schaltet drei Garantien gleichzeitig ab** `id=trg-040223fe | severity=medium | kind=bug → P2/engineering`
  - KONSOLIDIERT trg-f2d69527 + trg-d1e466aa. Gleiche Datei-Familie (config_factory plus run_config-Schema), deshalb gebuen…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-040223fe --task-ref EXT:<ref>`

### Source: webui-338-backport (1 item)

<a id="trg-94e71021"></a>
- **Backport webui#338: fork-PR resolution in the Tier-3 review is broken (belongs to IT-9)** `id=trg-94e71021 | severity=high | kind=bug → P1/engineering`
  - BELONGS TO IT-9 (trg-bd66b9b0), which holds exclusive ownership of everything under the workflows directory. This card…
  - Promote: `triage_promote.py --id trg-94e71021 --task-ref EXT:<ref>`

