# Campaign — Bloat Cleanup Track A (Prevention)

> Strukturelle Prävention für die Bloat-Limits. Blockierend für
> Campaigns B + C. Quellplan:
> `c:\01_Development\shipwright\Spec\Launch preparation bloat cleanup.md`
> (Sektion 5 = Track A Architektur, Sektion 7.3 = Iterate-Aufwand).

## Status

- **Started:** _not started_
- **Current iterate:** _pending kickoff_
- **Baseline (Campaign-Start):** _wird beim ersten Iterate erfasst_
- **Tolerierte Baseline-Failures:** keine

## Iterate-Bündelung

Die acht Plan-Slices A1–A8 werden zu **drei Iterates** gebündelt
(thematisch verwandt, geringes Konflikt-Risiko untereinander):

- **A.foundation** = A1 + A2 + A3 (Hook + Stop-Gate + Plugin-Registry)
- **A.review** = A4 + A5 (Subagent-Prompts + Compliance-Audit-G)
- **A.defense** = A6 + A7 + A8 (Pre-Commit + CI + ADR-Template + Glossar)

## Iterates

### A.foundation — Hook + Stop-Gate + Plugin-Registry

- **Status:** not started
- **Scope:** `shared/scripts/hooks/check_file_size.py` erweitern
  (Markdown-Klassifikation, Per-Filetype-Limit, Per-Session-Marker mit
  atomarem Write + TTL 1h). Neuer Hook
  `shared/scripts/hooks/bloat_gate_on_stop.py` (≤200 LOC, blockend).
  PostToolUse-Hook + Stop-Hook in *jeder* Plugin-`hooks.json`
  registrieren (oder zentral, falls Plugin-System es zulässt).
- **Files:**
  - `shared/scripts/hooks/check_file_size.py` (erweitern)
  - `shared/scripts/hooks/bloat_gate_on_stop.py` (NEU)
  - `shared/scripts/lib/bloat_baseline.py` (NEU — gemeinsamer
    Scan-Helper; von Phase-0, Stop-Gate und Adopt genutzt)
  - `plugins/shipwright-adopt/scripts/lib/baseline_generator.py`
    (NEU — Wrapper für Adopt-Onboarding; nutzt `bloat_baseline.py`)
  - `plugins/shipwright-adopt/skills/adopt/SKILL.md` (minimale
    Ergänzung: Schritt „Baseline generieren" vor „Hooks eintragen")
  - `shared/tests/test_hooks.py` (Test-Cases)
  - `plugins/*/hooks/hooks.json` (Hook-Registrierung)
- **Acceptance:**
  - Hook unterscheidet Source / Runtime-Prompt / Doc.
  - Marker-File ist Session-scoped, atomar geschrieben, TTL-gefiltert.
  - Stop-Gate-Smoke: Probe-Iterate mit neuer 350-LOC-Datei → Stop
    blockt vor Finalize.
  - Anti-Ratchet-Smoke: `current`-Erhöhung in
    `shipwright_bloat_baseline.json` → Stop blockt.
  - **No-Baseline-Smoke:** Baseline-File temporär umbenennen →
    Stop-Gate gibt `pass` zurück ohne zu blocken. Deckt neues
    Projekt und pre-Adopt-Zustand ab.
  - **Adopt-Sequenz:** `baseline_generator.py` schreibt Baseline
    mit allen Übertretungen als `grandfathered` *bevor* hooks.json
    im Ziel-Repo eingetragen wird.
  - Alle bestehenden Hook-Tests grün.
- **Risiko:** Mittel (Marker-Race, Hook-Registrierung in 12+
  Plugins).
- **Dependencies:** keine (Foundation).

### A.review — Subagent-Prompts + Compliance-Audit

- **Status:** not started
- **Scope:** `plugins/shipwright-build/agents/code-reviewer.md` und
  `plugins/shipwright-iterate/agents/sub-iterate-runner.md` bekommen
  Bloat-Checklist-Sektion. Neuer Audit `group_g.py` in Compliance,
  produziert G1–G5-Findings, kein UI-Touch an `phase_quality.py`.
- **Files:**
  - `plugins/shipwright-build/agents/code-reviewer.md`
  - `plugins/shipwright-iterate/agents/sub-iterate-runner.md`
  - `plugins/shipwright-compliance/scripts/audit/group_g.py` (NEU,
    ≤300 LOC; Struktur analog `group_e.py`)
  - `plugins/shipwright-compliance/tests/` (Tests für Group G)
- **Acceptance:**
  - code-reviewer rejected einen Probe-Iterate, der neue Übertretung
    ohne Allowlist einführt.
  - Group G liefert alle fünf Klassen (G1 Drift, G2 Ratchet-
    Suggestion, G3 Bypass-Detection, G4 Exception-ohne-ADR, G5
    Deferred-ohne-Plan-Ref).
  - Keine Modifikation an `phase_quality.py` (Doppel-Churn-
    Vermeidung).
- **Risiko:** Niedrig.
- **Dependencies:** A.foundation merged (Hook muss Marker schreiben,
  bevor Reviewer ihn prüft).

### A.defense — Pre-Commit + CI + ADR-Template + Glossar

- **Status:** not started
- **Scope:** Defense-in-Depth-Schicht für beide Repos. ADR-Template
  + Glossar. Diese Iterate berührt *beide* Repos.
- **Files (Shipwright):**
  - `.git/hooks/pre-commit` oder existierende Pre-Commit-Infra
    (erst in dieser Iterate verifizieren)
  - `.github/workflows/bloat-check.yml` (NEU)
  - `.shipwright/planning/adr/_template-bloat-exception.md` (NEU)
  - `shared/glossary.md` (NEU, ≤300 LOC, ~40 Begriffe)
  - `CLAUDE.md` (Glossar-Verweis als Pflicht-Read)
- **Files (WebUI):**
  - `shipwright-webui/.husky/pre-commit` (NEU oder erweitern)
  - `shipwright-webui/.github/workflows/bloat-check.yml` (NEU)
  - `shipwright-webui/CLAUDE.md` (Glossar-Verweis, Pfad zum
    Shipwright-Glossar oder Kopie)
- **Acceptance:**
  - Pre-Commit blockt Anti-Ratchet in beiden Repos.
  - GitHub-Action postet PR-Kommentar mit Allowlist-Diff; Exit 1
    nur bei Anti-Ratchet.
  - ADR-Template enthält Ousterhout-Argument-Feld + Re-Review-Datum.
  - Glossar listet ≥30 Begriffe inkl. Allowlist, Ratchet,
    Anti-Ratchet, Producer, Action-Unit, Canon-Gate.
- **Risiko:** Niedrig (Pre-Commit) bis Mittel (Glossar-Verweis-
  Konsistenz zwischen Repos).
- **Dependencies:** A.review merged (Compliance-Audit nutzt
  Glossar-Begriffe; Reviewer prüft gegen ADR-Template).

## Phase-D-Akzeptanz für Campaign A

- Smoke-Tests aus A.foundation + A.review wiederholt nach
  A.defense-Merge — alle drei Schichten greifen koordiniert.
- `shared/constitution.md:21` erweitert auf „300 LOC Source/Tests,
  400 LOC Runtime-Prompts, hart in CI für Anti-Ratchet,
  Exception-ADR-Pfad dokumentiert". (Update fällt in A.defense.)

## Notes

_Cross-Iterate-Beobachtungen hier sammeln._
