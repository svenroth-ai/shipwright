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

## Externe Referenzen (Quellbasis für Reviewer-Prompt, ADR-Template, Glossar)

Diese Campaign zitiert vier externe MIT-lizenzierte Quellen wörtlich
im code-reviewer-Prompt, im ADR-Template und im Glossar (Attribution
in den jeweiligen Files). Die Prinzipien sind Rule-Basis für die
Group-G-Audit-Findings und die Stop-Gate-Fehlermeldung.

| Quelle | Was übernommen wird | In welchem Slice |
|---|---|---|
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — `code-simplification` | Fünf Prinzipien (Preserve Behavior · Follow Conventions · Clarity over Cleverness · Maintain Balance · Scope to What Changed), Chesterton-Fence-Check, Line-Count-≠-Goal-Klausel | A.review (reviewer-Prompt), A.defense (Glossar) |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — `code-review-and-quality` | Change-Sizing-Tabelle (100/300/1000 LOC), Dead-Code-Artifact-Check, "Separate refactoring from feature work"-Regel, Five-Axis-Review als Header für Reviewer-Prompt | A.review (reviewer-Prompt) |
| [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | Vier Karpathy-Prinzipien (Think Before Coding · Simplicity First · Surgical Changes · Goal-Driven Execution) als Rule-Header | A.review (reviewer-Prompt), A.defense (Glossar) |
| [obra/superpowers](https://github.com/obra/superpowers) — `verification-before-completion`, `writing-plans` | Iron-Law-Sprache, Red-Flags-Tabelle, Rationalization-Prevention-Tabelle, DRY/YAGNI-Header | A.foundation (Stop-Gate-Fehlermeldung), A.defense (ADR-Template) |

> Multica-Hauptrepo (`multica-ai/multica`) ist *nicht* in dieser Liste:
> Apache-2.0-modifiziert mit Hosting-Restriktion. Architektur-Patterns
> davon laufen separat über die Spec
> `Spec/external-frameworks-integration.md` und Triage-Items
> (`source: external-frameworks`). Diese Campaign zitiert keinen
> Multica-Text.

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
  `shared/scripts/hooks/bloat_gate_on_stop.py` (≤200 LOC, blockend)
  **mit Iron-Law-Fehlermeldung im Superpowers-Stil** (Rule + Red-Flags-
  Tabelle + Rationalization-Tabelle als Block-Body). Quelle:
  [obra/superpowers](https://github.com/obra/superpowers)
  `skills/verification-before-completion/SKILL.md` (MIT, © Jesse
  Vincent) — adaptiert auf Bloat-Domäne, Attribution im Module-
  Docstring.
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
  Bloat-Checklist-Sektion mit **wörtlich zitierter Rule-Basis** aus
  Karpathy (4 Prinzipien) + Osmani (Five-Axis-Review-Header, Change-
  Sizing-Tabelle, Dead-Code-Artifact-Check). Neuer Audit `group_g.py`
  in Compliance, produziert G1–G5-Findings, kein UI-Touch an
  `phase_quality.py`.
- **Files:**
  - `plugins/shipwright-build/agents/code-reviewer.md` (Rule-Basis-
    Header + Bloat-Checklist anhängen, Attribution-Block am Ende)
  - `plugins/shipwright-iterate/agents/sub-iterate-runner.md` (analog)
  - `plugins/shipwright-compliance/scripts/audit/group_g.py` (NEU,
    ≤300 LOC; Struktur analog `group_e.py`)
  - `plugins/shipwright-compliance/tests/` (Tests für Group G)
- **Rule-Basis (wörtlich, mit Attribution-Footer):**
  - **Karpathy-Block** (4 Prinzipien, ~20 LOC) als Header der
    Reviewer-Checkliste. Quelle:
    [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
    (MIT, © 2025 multica-ai).
  - **Osmani-Block** (Change-Sizing-Tabelle 100/300/1000 + Five-Axis-
    Review-Stichworte + "Separate refactoring from feature work" +
    Dead-Code-Artifact-Check, ~30 LOC). Quelle:
    [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
    `skills/code-review-and-quality/SKILL.md` (MIT, © Addy Osmani).
  - **Bloat-spezifische Checklist** (Shipwright-eigen): Allowlist-
    Diff, Anti-Ratchet, neue Übertretungen ohne ADR.
- **Acceptance:**
  - code-reviewer rejected einen Probe-Iterate, der neue Übertretung
    ohne Allowlist einführt.
  - code-reviewer rejected einen Probe-Iterate, der Refactor + Feature
    in einem Commit mischt (Osmani-Regel).
  - code-reviewer rejected einen Probe-Iterate mit `_unused`-
    Artefakten oder `// removed`-Kommentaren (Osmani-Dead-Code-Regel).
  - Group G liefert alle fünf Klassen (G1 Drift, G2 Ratchet-
    Suggestion, G3 Bypass-Detection, G4 Exception-ohne-ADR, G5
    Deferred-ohne-Plan-Ref).
  - Keine Modifikation an `phase_quality.py` (Doppel-Churn-
    Vermeidung).
  - Attribution-Footer in beiden Reviewer-Files vorhanden und
    verlinkt auf die jeweiligen Repos.
- **Risiko:** Niedrig.
- **Dependencies:** A.foundation merged (Hook muss Marker schreiben,
  bevor Reviewer ihn prüft).

### A.defense — Pre-Commit + CI + ADR-Template + Glossar

- **Status:** not started
- **Scope:** Defense-in-Depth-Schicht für beide Repos. ADR-Template
  (mit zwei Pflichtfeldern aus externen Quellen: **YAGNI-Check** im
  Superpowers-`writing-plans`-Stil + **Chesterton-Fence-Check** im
  Osmani-`code-simplification`-Stil + **Incident-Reference** im
  Multica-CLAUDE.md-Stil — Multica nur als Pattern, kein Text-Zitat).
  Glossar mit explizitem "External References"-Block am Ende
  (Karpathy 4 Prinzipien, Osmani Five-Axis, Superpowers Iron-Law,
  jeweils mit Attribution + Lizenz). Diese Iterate berührt *beide*
  Repos.
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
  - ADR-Template enthält Ousterhout-Argument-Feld + Re-Review-Datum
    + YAGNI-Check + Chesterton-Fence-Check + Incident-Reference-Feld.
  - Glossar listet ≥30 Begriffe inkl. Allowlist, Ratchet,
    Anti-Ratchet, Producer, Action-Unit, Canon-Gate.
  - Glossar-Anhang "External References" enthält Karpathy-, Osmani-
    und Superpowers-Block mit MIT-Attribution + Repo-Link.
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

## Out of Scope (→ Spec: `Spec/external-frameworks-integration.md`)

Folgende Patterns aus den 4 externen Quellen sind *nicht* Teil dieser
Campaign, sondern landen als Spec-Items + Triage-Items für separate
Iterates:

- **Superpowers** — two-stage section review (Spec→Quality), using-
  shipwright Bootstrap, systematic-debugging-Skill, writing-skills-
  Skill, anti-slop PR template
- **Osmani** — `code-simplify` als standalone Shipwright-Skill,
  doubt-driven-development Pattern, spec-driven "assumptions-first"
  Header in `/shipwright-project`
- **Karpathy** — 4-Prinzipien-Block in `shared/constitution.md`
  (kommt durch A.defense's Glossar-Verweis indirekt rein; expliziter
  Constitution-Insert separat)
- **Multica (Patterns only, no code/text copy)** — `skills-lock.json`-
  Mechanik für Third-Party-Phasen, package-boundary-Check
  (`check_plugin_boundaries.py`), API-response Parse-don't-Cast für
  Plugin-Configs, WS-Streaming + Multi-Workspace + Runtime-Registry
  für WebUI

Diese Punkte sind in
`Spec/external-frameworks-integration.md` ausformuliert und als
Triage-Items mit `source: external-frameworks` im Triage-Inbox
erfasst.

## Notes

_Cross-Iterate-Beobachtungen hier sammeln._
