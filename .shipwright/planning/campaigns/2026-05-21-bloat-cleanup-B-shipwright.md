# Campaign — Bloat Cleanup Track B (Shipwright Cleanup)

> Cleanup der God-Module + SKILL.md im Shipwright-Hauptrepo.
> Quellplan:
> `c:\01_Development\shipwright\Spec\Launch preparation bloat cleanup.md`
> (Sektion 6.1 = Track B Inventur, Sektion 7.3 = Aufwand,
> Sektion 8 = Risk Register).
>
> **Voraussetzung:** Campaign A vollständig gemerged. Track-A-Self-
> Test (Loop-Gate blockt Übertretungen) findet bei jedem B-Iterate
> statt.

## Status

- **Started:** _not started_
- **Current iterate:** _pending kickoff (B1 first)_
- **Voraussetzung:** Campaign A merged
- **Baseline (Campaign-Start):** _wird beim ersten Iterate erfasst_

## Iterates

### B1 — SKILL.md-Splits (7 Mini-Iterates)

- **Status:** not started
- **Scope:** Sieben SKILL.md-Dateien splitten: Kern (~250 LOC) +
  `references/F*.md` on-demand. Pro Skill ein eigener
  Mini-Iterate, weil jeder ein **Probe-`/shipwright-X`-Smoke** braucht.
- **Reihenfolge (höchster Hebel zuerst):**
  1. B1.iterate — `plugins/shipwright-iterate/skills/iterate/SKILL.md` (1.611)
  2. B1.build — `plugins/shipwright-build/skills/build/SKILL.md` (1.162)
  3. B1.test — `plugins/shipwright-test/skills/test/SKILL.md` (986)
  4. B1.adopt — `plugins/shipwright-adopt/skills/adopt/SKILL.md` (809)
  5. B1.design — `plugins/shipwright-design/skills/design/SKILL.md` (695)
  6. B1.project — `plugins/shipwright-project/skills/project/SKILL.md` (612)
  7. B1.plan — `plugins/shipwright-plan/skills/plan/SKILL.md` (581)
- **Files pro Mini-Iterate:**
  - SKILL.md (kürzen auf ~250 LOC, Kern + Index)
  - `plugins/<skill>/skills/<skill>/references/F*.md` (NEU, ein File
    pro Phase F0..F11 falls vorhanden, sonst thematisch geschnitten)
  - Allowlist-Entry für die SKILL.md aus
    `shipwright_bloat_baseline.json` entfernen
- **Acceptance pro Mini-Iterate:**
  - Kern-SKILL.md ≤ 400 LOC.
  - Sub-references je ≤ 300 LOC.
  - **Probe-Iterate:** kleinen repräsentativen `/shipwright-<skill>`-
    Aufruf fahren; Verhalten muss matchen (z.B. `/shipwright-iterate`
    für einen 50-LOC-Fix → Boundary-Detection läuft sauber an).
  - Allowlist-Entry entfernt.
- **Risiko:** Mittel-Hoch (Prompt-Verhalten nicht unit-test-abdeckbar;
  Rollback bei Drift Pflicht).
- **Dependencies:** Campaign A merged.

### B8 — Adopt↔Compliance + Test↔Iterate stabiler Vertrag

- **Status:** not started
- **Scope:** Subprocess + Pfad-Walk durch direkte Python-Imports
  ersetzen. Stabilen Vertrag in `shared/contracts/`.
- **Files:**
  - `shared/contracts/compliance.py` (NEU, Public API)
  - `shared/contracts/iterate.py` (NEU, Public API)
  - `plugins/shipwright-adopt/scripts/lib/compliance_bridge.py`
    (Subprocess raus → Import from contract)
  - `plugins/shipwright-test/scripts/tools/boundary_coverage_report.py`
    (Pfad-Ref `_ITERATE_LIB` raus → Import from contract)
- **Acceptance:**
  - Adopt ruft Compliance über `shared/contracts/compliance.py` auf,
    kein Subprocess + kein Ancestor-Path-Walk mehr.
  - Test↔Iterate-Path-Reference entfernt.
  - Adopt-Tests und Test-Plugin-Tests grün.
- **Risiko:** Niedrig.
- **Dependencies:** B1 (parallel oder seriell — keine Datei-Konflikte).

### B2 — `data_collector.py` Split

- **Status:** not started
- **Scope:** 1.381 LOC → Pro Compliance-Doc ein Collector. Public
  Interface `from collectors import collect_all` bleibt rückwärts-
  kompatibel.
- **Files:**
  - `plugins/shipwright-compliance/scripts/lib/data_collector.py`
    (wird zu Re-Export-Modul ~50 LOC)
  - `plugins/shipwright-compliance/scripts/lib/collectors/rtm.py` (NEU)
  - `…/collectors/test_evidence.py` (NEU)
  - `…/collectors/change_history.py` (NEU)
  - `…/collectors/sbom.py` (NEU)
  - `…/collectors/dashboard.py` (NEU)
  - `…/collectors/_common.py` (NEU, shared helpers)
- **Acceptance:**
  - Jeder Collector ≤ 300 LOC.
  - `collect_all`-Aufrufer (RTM-Generator, Dashboard-Generator etc.)
    unverändert grün.
  - Allowlist-Entry entfernt.
- **Risiko:** Mittel.
- **Dependencies:** Campaign A merged.

### B6 — `github_triage.py` Split

- **Status:** not started
- **Scope:** 929 LOC → Producer / Consumer / State.
- **Files:**
  - `shared/scripts/lib/github_triage.py` (Re-Export ~50 LOC)
  - `shared/scripts/lib/github_triage/producer.py` (NEU)
  - `shared/scripts/lib/github_triage/consumer.py` (NEU)
  - `shared/scripts/lib/github_triage/state.py` (NEU)
- **Acceptance:** je Modul ≤ 300 LOC; bestehende Tests grün;
  Allowlist-Entry entfernt.
- **Risiko:** Mittel.
- **Dependencies:** parallel zu B2 möglich.

### B3 — `phase_quality.py` Split (+ Dashboard-Bloat-Spalte)

- **Status:** not started
- **Scope:** 1.104 LOC → Per Phasengruppe. **Trägt Dashboard-Spalte
  für Compliance-Group-G mit** (kommt aus A.review).
- **Files:**
  - `shared/scripts/lib/phase_quality.py` (Re-Export ~50 LOC)
  - `shared/scripts/lib/phase_quality/project.py`, `plan.py`,
    `build.py`, `test.py`, `security.py`, `deploy.py`, `iterate.py`
    (NEU)
  - `shared/scripts/lib/phase_quality/_dashboard_render.py` (NEU,
    enthält neue Bloat-Spalten-Render-Logik)
  - `shared/tests/test_phase_quality*.py` (Tests folgen Struktur)
- **Acceptance:**
  - Je Phase-Modul ≤ 300 LOC.
  - Dashboard zeigt drei Bloat-Zähler: über-Limit / in-Allowlist /
    Ratchet-Δ.
  - Compliance-Group-G-Daten werden korrekt visualisiert.
  - Allowlist-Entry entfernt.
- **Risiko:** Mittel-Hoch (zentrale Gate-Logik).
- **Dependencies:** B2 und A.review merged (G-Daten verfügbar).

### B4 — `dev_server.py` Split

- **Status:** not started
- **Scope:** 995 LOC + 1.125-LOC Test → Per Service-Handler.
- **Files:**
  - `shared/scripts/dev_server.py` (Re-Export ~50 LOC)
  - `shared/scripts/dev_server/spawn.py`, `health.py`,
    `multiservice.py`, `__main__.py` (NEU)
  - Tests entsprechend aufgeteilt
- **Acceptance:** Module + Tests je ≤ 300 LOC; bestehende
  Multiservice-Smoke-Tests grün; Allowlist-Entries entfernt
  (Source + Test).
- **Risiko:** Mittel.
- **Dependencies:** parallel zu B5 möglich.

### B5 — `orchestrator.py` Split

- **Status:** not started
- **Scope:** 983 LOC → Per-Phase-Orchestrierung.
- **Files:**
  - `plugins/shipwright-run/scripts/lib/orchestrator.py`
    (Re-Export + Router ~150 LOC)
  - `plugins/shipwright-run/scripts/lib/orchestrator/phases/*.py` (NEU)
- **Acceptance:** Module je ≤ 300 LOC; alle Run-Plugin-Tests grün;
  Integration-Tests grün; Allowlist-Entry entfernt.
- **Risiko:** Hoch (Orchestrator ist weitreichend).
- **Dependencies:** parallel zu B4; idealerweise letzter B-Iterate
  (sammelt Lernerfahrungen aus B2/B3/B4/B6).

## B7 — `shared/scripts/tools/` Konsolidierung

**Out-of-scope dieser Campaign** (siehe Plan §3.2 + §6.1).
60 Dateien / 16k LOC sind eine echte Migration mit Callsite-Umbau,
kein Datei-Split. Bleibt in Allowlist als `state=deferred-plan` mit
`plan_ref` auf einen späteren Spec-Plan, der nach Track-B-Abschluss
geschrieben wird.

## Phase-D-Akzeptanz für Campaign B

- `shipwright_bloat_baseline.json` enthält keine
  `state=grandfathered`-Einträge mehr für Shipwright-Source.
- Einzig erlaubt: `state=exception` (mit ADR) und
  `state=deferred-plan` (für `tools/`-Subtree).
- Alle Plugin-Test-Suites + Integration-Tests grün.
- Compliance-Dashboard zeigt für jeden gemergten Iterate
  „Allowlist: −1 Eintrag" als sichtbares Signal.

## Notes

_Cross-Iterate-Beobachtungen hier sammeln._
