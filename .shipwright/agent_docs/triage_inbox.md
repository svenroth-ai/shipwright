# Triage Inbox

> Auto-generated 2026-07-28T09:01:05.419913Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 476
- Triage: 20 | Promoted: 1 | Dismissed: 453 | Snoozed: 2

## Top 20 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-965c563e"></a>
- **Compliance: 5 open finding(s)** `id=trg-965c563e | severity=high | kind=compliance → P1/compliance`
  - 5 open compliance finding(s): D/D1, D/D3, F/F6, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Must:…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 5 open compliance finding(s): D/D1, D/D3, F/F6, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-965c563e --task-ref EXT:<ref>`

### Source: iterate (1 item)

<a id="trg-2f89afcf"></a>
- **Adopted repos inherit derived-snapshots-off-branch without a refresh producer** `id=trg-2f89afcf | severity=high | kind=improvement → P1/engineering`
  - shared/ syncs into the plugin-cache root that every adopted repo resolves, and the change lives in the iterate skill, s…
  - Promote: `triage_promote.py --id trg-2f89afcf --task-ref EXT:<ref>`

### Source: manual (3 items)

<a id="trg-10aa91e3"></a>
- **A grade snapshot cannot say whether the graded content matches the commit it names (dirty flag built, then withdrawn)** `id=trg-10aa91e3 | severity=medium | kind=improvement → P2/engineering`
  - Root cause, unfixed by design: grade and score are computed from the WORKING tree while lineage and base can only be de…
  - Promote: `triage_promote.py --id trg-10aa91e3 --task-ref EXT:<ref>`

<a id="trg-d190cc37"></a>
- **WebUI Grade-Trend must group grade_snapshot by tree attribution, not plot every point** `id=trg-d190cc37 | severity=medium | kind=bug → P2/engineering`
  - Producer side landed: every grade_snapshot now carries lineage (main\|branch\|unknown), branch and base (merge-base wit…
  - Promote: `triage_promote.py --id trg-d190cc37 --task-ref EXT:<ref>`

<a id="trg-1346abbd"></a>
- **Stamp the C3 event anchor in the iterate ledger writer** `id=trg-1346abbd | severity=low | kind=improvement → P3/engineering`
  - Canon C3 consults its clock only where a completion carries an event anchor. append_iterate_entry.py deliberately stamp…
  - Promote: `triage_promote.py --id trg-1346abbd --task-ref EXT:<ref>`

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

### Source: triage-consolidation-2026-07-28 (9 items)

<a id="trg-e3f79524"></a>
- **IT-9 Host-Checks: Gates die nichts gaten, das Verdict-Label, und kein CI-Job auf Windows** `id=trg-e3f79524 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-c7e5835b (das seinerseits trg-2f9865fb supersedete), KONSOLIDIERT zusaetzlich trg-9862202d + trg-80e3b3c…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-e3f79524 --task-ref EXT:<ref>`

<a id="trg-1a815ff2"></a>
- **IT-7 Die Review-Maschinerie schliesst ihren Kreis: totes Verdict blockt ewig, Sub-Iterates ohne Cascade** `id=trg-1a815ff2 | severity=high | kind=bug → P1/engineering`
  - KONSOLIDIERT trg-9e2ce202 + trg-71d7a4fa. ZWEI Iterates, ein Anker. 7a ZUERST und klein - trg-9e2ce202: wenn der Tier-3…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-1a815ff2 --task-ref EXT:<ref>`

<a id="trg-ffbf13de"></a>
- **IT-5 Klassifikation und Risiko-Erkennung: 79 Prozent aller Laeufe sind faelschlich medium** `id=trg-ffbf13de | severity=high | kind=improvement → P1/engineering`
  - KONSOLIDIERT trg-ee7b83e5 + trg-496e63a7. Beide aendern, WELCHE PHASEN FEUERN - gleicher Blast Radius, und der Hebel wi…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-ffbf13de --task-ref EXT:<ref>`

<a id="trg-e3ca4314"></a>
- **IT-3 F11 sagt die Wahrheit ueber den Lauf, den es prueft: vier Fail-Open-Pfade im selben Gate** `id=trg-e3ca4314 | severity=high | kind=bug → P1/engineering`
  - KONSOLIDIERT trg-81fbf8ed + trg-51a57370 + trg-64372769 + trg-ffddd6b9. Ein Blast Radius: shared/scripts/verifiers/ plu…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-e3ca4314 --task-ref EXT:<ref>`

<a id="trg-4bbbd233"></a>
- **IT-2 Grade-Snapshot-Attribution und Event-Log-Integritaet: eine Ursache, sechs Nachbeben** `id=trg-4bbbd233 | severity=high | kind=bug → P1/engineering`
  - KONSOLIDIERT trg-aea8c97e + trg-ca4fc0e7 + trg-1603000f + trg-5e945a39 + trg-465a2caf + trg-c97faa35 - alle sechs sind…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-4bbbd233 --task-ref EXT:<ref>`

<a id="trg-4ebc928e"></a>
- **IT-1 Triage-Store und Delivery haerten: 3 verifizierte High plus ~29 Audit-Befunde** `id=trg-4ebc928e | severity=high | kind=bug → P1/engineering`
  - KONSOLIDIERT trg-7b6f13df + trg-93ceb2b0 + trg-51f8e2a1 + trg-0a294ef3. DREI Iterates unter EINEM Anker, interleaved-se…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`
  - Promote: `triage_promote.py --id trg-4ebc928e --task-ref EXT:<ref>`

<a id="trg-71a381f5"></a>
- **IT-0 Hygiene-Sweep: die Gates entsperren, die die naechste Arbeit blockieren** `id=trg-71a381f5 | severity=high | kind=compliance → P1/engineering`
  - KONSOLIDIERT trg-8f022f38 + trg-17f53a39. Laeuft ALLEIN und ZUERST; IT-3, IT-5 und IT-7 haengen daran. GRUND (gemessen)…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-71a381f5 --task-ref EXT:<ref>`

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

