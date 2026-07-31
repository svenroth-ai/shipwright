# Triage Inbox

> Auto-generated 2026-07-31T05:50:52.994375Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 526
- Triage: 23 | Promoted: 1 | Dismissed: 500 | Snoozed: 2

## Top 23 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-1d752697"></a>
- **Compliance: 4 open finding(s)** `id=trg-1d752697 | severity=high | kind=compliance → P1/compliance`
  - 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must: FR-01.…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 4 open compliance finding(s): D/D1, D/D3, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-1d752697 --task-ref EXT:<ref>`

### Source: f0-suite (1 item)

<a id="trg-f64d1c27"></a>
- **[f0] shared/tests failed in parallel and passed alone - race or flaky test** `id=trg-f64d1c27 | severity=high | kind=bug → P1/engineering`
  - shared/tests: red in parallel (rc 1), GREEN alone (rc 0). It IS on the suite.xdist allowlist, so the fan-out inside the…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --type bug
    
    Context: F0 suite card f0-race:shared/tests. The test unit shared/tests failed while the units ran side by side and passed when re-run alone, so the gate stayed green and nothing else recorded it.
    Reproduce alone (expect GREEN): uv run --with pytest --with pytest-mock --with diff-cover==10.3.0 pytest shared/tests -q -p no:cacheprovider -m 'not slow and not cross_plugin'
    Reproduce in parallel (expect intermittent RED): uv run shared/scripts/tools/run_test_suite.py --project-root 'C:\01_Development\shipwright\.worktrees\derived-gate-sees-the-pr' --run-id iterate-2026-07-30-derived-gate-sees-the-pr
    Establish whether it is a race between units or an unreliable test, fix the cause, and close this card. Never weaken or delete the test to make it pass.
    ```
  - Promote: `triage_promote.py --id trg-f64d1c27 --task-ref EXT:<ref>`

### Source: iterate-2026-07-31-adr-index-producer code review (1 item)

<a id="trg-1acb5304"></a>
- **ADR INDEX.md has no merge-reconciliation entry for parallel iterates** `id=trg-1acb5304 | severity=medium | kind=improvement → P2/engineering`
  - Since iterate-2026-07-31-adr-index-producer, .shipwright/planning/adr/INDEX.md is regenerated on a BRANCH at iterate F3…
  - Promote: `triage_promote.py --id trg-1acb5304 --task-ref EXT:<ref>`

### Source: iterate-measurement (1 item)

<a id="trg-6af8dc72"></a>
- **Triage-Delivery: eine aus CI gefilte Karte landet im gitignorierten Outbox und erreicht niemanden (gehoert zu IT-1)** `id=trg-6af8dc72 | severity=medium | kind=bug → P2/engineering`
  - GEHOERT ZU IT-1 (trg-4ebc928e, Triage-Store und Delivery haerten) - dort einhaengen, nicht separat abarbeiten.  MECHANI…
  - Promote: `triage_promote.py --id trg-6af8dc72 --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-012db453"></a>
- **Derived compliance docs: build Weg B (release-time check-in + on-demand docs PR)** `id=trg-012db453 | severity=medium | kind=improvement → P2/engineering`
  - DECIDED 2026-07-30 by the operator: Weg B, with the open question answered ("does anyone read the evidence on main cont…
  - Evidence: `.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md`
  - Promote: `triage_promote.py --id trg-012db453 --task-ref EXT:<ref>`

### Source: operator (1 item)

<a id="trg-386bd01c"></a>
- **ADR INDEX.md silently drifts: rebuild_adr_index runs only when there are decision-drops to fold** `id=trg-386bd01c | severity=low | kind=bug → P3/engineering`
  - MECHANISM. aggregate_decisions.py calls rebuild_adr_index() only INSIDE aggregate()'s `if valid:` branch, i.e. exclusiv…
  - Promote: `triage_promote.py --id trg-386bd01c --task-ref EXT:<ref>`

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

### Source: shipwright-webui iterate-2026-07-29-accepted-risk-ci-gate (external + Codex review) (2 items)

<a id="trg-7d18bb0b"></a>
- **SecFix-3 (monorepo, AUTONOMOUS-READY): accepted-risk gate - reconcile with no register, and honour the ignore-file expi…** `id=trg-7d18bb0b | severity=medium | kind=bug → P2/engineering`
  - Filed from shipwright-webui, where the accepted-risk gate was first wired into CI (webui PR #332). SecFix-1..5 are one…
  - Promote: `triage_promote.py --id trg-7d18bb0b --task-ref EXT:<ref>`

<a id="trg-87174b37"></a>
- **SecFix-5 (monorepo, NOT AUTONOMOUS - schema decision): should the accepted-risk register gain an entry type for inline…** `id=trg-87174b37 | severity=low | kind=improvement → P3/engineering`
  - Filed from shipwright-webui. SecFix-1..5 are one family; this is the only member that must NOT run unattended, which is…
  - Promote: `triage_promote.py --id trg-87174b37 --task-ref EXT:<ref>`

### Source: triage-consolidation (3 items)

<a id="trg-fc173418"></a>
- **IT-7 (neu) Die Review-Maschinerie schliesst ihren Kreis: totes Verdict, fehlende Cascade, fehlender Architektur-Pass, s…** `id=trg-fc173418 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-1a815ff2 - 7a und 7b inhaltlich UNVERAENDERT, zwei Mitglieder kommen dazu. KONSOLIDIERT zusaetzlich trg-…
  - Promote: `triage_promote.py --id trg-fc173418 --task-ref EXT:<ref>`

<a id="trg-515060a6"></a>
- **IT-11 (neu nach dem Architektur-Review) Adoptierte Repos brauchen aktuelle Evidenz - aber wahrscheinlich OHNE Refresh-P…** `id=trg-515060a6 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-c5b05f31. Grund fuer die Neufassung: der alte Text sagt 'die Entscheidung muss fallen, BEVOR der Refresh…
  - Promote: `triage_promote.py --id trg-515060a6 --task-ref EXT:<ref>`

<a id="trg-5387cafb"></a>
- **IT-3b F11 sagt die Wahrheit ueber die ZUSTELLUNG: nie geliefert, und falsch gewarnt** `id=trg-5387cafb | severity=high | kind=improvement → P1/engineering`
  - NACHFOLGER von IT-3 (trg-e3ca4314, geschlossen). Beide Befunde entstanden NACH dessen Abschluss und treffen exakt desse…
  - Promote: `triage_promote.py --id trg-5387cafb --task-ref EXT:<ref>`

### Source: triage-consolidation-2026-07-28 (7 items)

<a id="trg-bd66b9b0"></a>
- **IT-9 (neu) Host-Checks: Gates die nichts gaten, das Verdict-Label, kein Windows-CI, und der Tier der sich auf Autorscha…** `id=trg-bd66b9b0 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-e3f79524 (das trg-c7e5835b supersedete, das trg-2f9865fb supersedete), KONSOLIDIERT zusaetzlich trg-51f6…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-bd66b9b0 --task-ref EXT:<ref>`

<a id="trg-ffbf13de"></a>
- **IT-5 Klassifikation und Risiko-Erkennung: 79 Prozent aller Laeufe sind faelschlich medium** `id=trg-ffbf13de | severity=high | kind=improvement → P1/engineering`
  - KONSOLIDIERT trg-ee7b83e5 + trg-496e63a7. Beide aendern, WELCHE PHASEN FEUERN - gleicher Blast Radius, und der Hebel wi…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-ffbf13de --task-ref EXT:<ref>`

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

