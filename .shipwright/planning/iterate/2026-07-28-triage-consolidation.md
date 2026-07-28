# Triage-Konsolidierung 2026-07-28

40 offene Triage-Items → **10 Anker**, 7 unangetastet, 1 deferred, 32 dismissed.
Gruppiert nach **Blast Radius** (welche Dateien), nicht nach Thema.

Diese Datei ist die Evidenz-Quelle der zehn Anker (`evidencePath`). Sie trägt die
Messungen der absorbierten Karten, damit sie den Dismiss überleben.

---

## Serialisierungs-Zwang (gemessen, nicht geschätzt)

`shipwright_bloat_baseline.json` ist **nicht** in `CHURN_ALLOWLIST`
(`shared/scripts/lib/churn_merge.py:71` — Allowlist = `DERIVED_MDS` + events,
test_results, triage, ci-security, test-traceability). Ein Konflikt darauf ist
**ausserhalb** der auto-auflösbaren Menge → `resolve_churn_conflicts` **bricht ab**.

Drei Ring-1-Anker müssen je einen Eintrag in genau diese Datei schreiben:

| Anker | Datei, die er anfassen muss | Zeilen | Baseline |
|---|---|---:|---|
| IT-3 | `shared/scripts/tools/record_review_pass.py` | 395 | **fehlt** → neue Überschreitung |
| IT-5 | `plugins/shipwright-iterate/tests/test_classify_complexity.py` | 317 | **fehlt** → neue Überschreitung |
| IT-7b | `plugins/shipwright-iterate/agents/sub-iterate-runner.md` | 479 | **fehlt** → neue Überschreitung |

Der Stop-Hook blockt bei **Berührung** einer nicht-baselineten Übergrösse — auch
wenn der Iterate die Datei verkleinert. Parallel gestartet kollidieren alle drei
auf einer nicht-mergebaren Datei.

**Folge:** IT-0 läuft **allein und zuerst** und baselined diese drei Dateien mit
(plus die zehn aus H1). Danach sind IT-3 / IT-5 / IT-7 dateidisjunkt:

```
IT-3   shared/scripts/verifiers/ + record_review_pass.py
IT-5   plugins/shipwright-iterate/scripts/lib/{classify_complexity,risk_detectors}.py
IT-7a  plugins/shipwright-security/scripts/{tools,lib}/pr_review*
IT-7b  plugins/shipwright-iterate/agents/ + skills/iterate/references/campaign-mode.md
```

IT-5 und IT-7b liegen beide unter `plugins/shipwright-iterate/`, aber in
disjunkten Unterbäumen (`scripts/lib` vs. `agents/` + `skills/`) — kein Konflikt.
IT-7b fasst `agents/` + `skills/` an → Tier-3a, PR-Review nicht überspringbar.

**Reihenfolge:**

```
IT-0                    ── allein, entsperrt die drei Dateien
├── IT-3 ┐
├── IT-5 ├── 3-breit parallel
└── IT-7 ┘
──────────────────────── ab hier REQ-3 fortsetzbar
IT-1 / IT-2 / IT-6 / IT-8 / IT-9   parallel zu REQ-3, disjunkt
```

---

## Warum IT-1 keine Kampagne ist

Drei Gründe, alle heute gültig:

1. Der `sub-iterate-runner` hat **kein** Agent-Tool — spec-reviewer (HARD-GATE)
   und doubt-reviewer laufen für Kampagnen-Sub-Iterates **nicht**. Genau das ist
   IT-7b. Ausgerechnet die datenverlustkritischste Oberfläche des Repos durch den
   einen Modus zu schicken, dem das Spec-Compliance-Gate fehlt, ist verkehrt herum.
2. Der Runner überspringt F5/F5c+F2 → F11 schlägt fehl, solange die volle
   Finalisierung nicht explizit gebrieft wird. Bei drei Einheiten mehr Reibung
   als Nutzen.
3. Kampagnen-Maschinerie (status.json, autonome Schleife) zahlt sich ab ~5
   gleichförmigen Einheiten aus. Hier haben die drei völlig verschiedene Form:
   S1 = sieben kleine Fail-Safe-Fixes · S2 = ein Mechanismus über vier Aufrufer ·
   S3 = fünfteiliges Feature mit Contract-Bump und Cross-Repo-Konsument.

**Also:** ein Anker, drei normale Iterates, interleaved-serial
(build → PR → grün → merge → nächster). Nach IT-7b wäre eine Kampagne technisch
möglich — bei drei Einheiten lohnt sie trotzdem nicht.

---

## Die zehn Anker

### IT-0 — Hygiene-Sweep *(1 Iterate, zuerst, allein)*
Absorbiert `trg-8f022f38`, `trg-17f53a39`.

- Bloat-Baseline H1/H2: zehn Dateien >300 ohne Eintrag, zehn Ratchet-Suggestions.
  **Zusätzlich pflicht:** die drei Dateien aus der Tabelle oben, sonst blockiert
  IT-3/IT-5/IT-7 am Stop-Hook. Ebenfalls messen:
  `shared/scripts/tools/triage_gc.py` = 300 (Grenzfall) und
  `shared/scripts/lib/worktree_isolation.py` = 371 gegen Baseline `current: 370`
  → Anti-Ratchet blockt den nächsten Commit, der sie staged (relevant für IT-1).
- F6: `CLAUDE.md` = 213 Zeilen, Cap 200.
- D1/D3: FR-01.17 ohne Event-Coverage, FR-01.18 ohne Test-Totals.
- `trg-17f53a39`: `check_security_scan` heisst nach Security, liest aber die
  RTM-Zeile *Unresolved findings* (66 / 24). Ursache steht in der IT-1-Audit-Datei:
  `review.fixed` wird bei F5b geschrieben — **bevor** die Remediation-Commits
  existieren, Log ist append-only, also unterberichtet der Zähler
  konstruktionsbedingt; nur 4 von 389 `work_completed` tragen überhaupt einen
  `review`-Block. Entscheidung: Zähler zurückziehen, Gate umbenennen/umhängen.
  **Korrektur zur Ursprungskarte:** ihre Behauptung „kein Commit ist in diesem
  Repo mehr möglich" ist **falsch** — es wird laufend committet. Die Namens- und
  Zählerfrage ist real, die Blockierungsbehauptung nicht.

### IT-1 — Triage-Store & Delivery härten *(3 Iterates, ein Anker)*
Absorbiert `trg-7b6f13df`, `trg-93ceb2b0`, `trg-51f8e2a1`, `trg-0a294ef3`.
Detail: `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`
— seit `1f8364b6` **getrackt und gepusht**. (Der IT-1-Kartentext sagt noch
„untracked": Stand beim Anlegen, während dieser Session überholt. Der
`evidencePath` zeigt korrekt, nichts ist zu tun.)

- **S1 — die drei verifizierten High + billige Nachbarn.** Strikter Decode im
  Sweep-Reader (`sweep_text.py:50`, kein `errors=`) crasht `setup_iterate_worktree`
  Schritt 5, nachdem `git worktree add` bereits erfolgreich war → verwaister
  Worktree. Truncate-then-Write auf dem getrackten SSoT (`triage_header.py:48-52`,
  einziger Ganzdatei-Rewrite, der `durable_atomic_write` umgeht, auf einem
  *Recovery*-Pfad). GC publiziert die Outbox aus einem Read von **vor** einem
  `git commit` mit `timeout=120` (`sweep_outbox.py:133 → :233`) — jeder Append im
  Fenster ist weg, Sweep meldet Erfolg; der Schwester-Pfad
  `commit_main_tracked_drift:256` liest 20 Zeilen früher genau deswegen neu.
  Dazu Befunde 4/6/7/8 (gleiche Dateien).
- **S2 — `expected_status` unter dem Lock.** Deckt `trg-93ceb2b0` (Operator-
  Entscheidung wird vom Auto-Resolver überschrieben, Kommando meldet trotzdem
  Erfolg, exit 0) und Audit-Befund 19 (vier Aufrufer, identische Ursache) mit
  **einem** Mechanismus ab.
- **S3 — „defer" heisst defer** (`trg-51f8e2a1`, fünf Teile, Operator-
  Entscheidungen liegen seit 2026-07-27 vor): Revisit-Datum pflicht, Selbstschluss
  bei verschwundenem Befund, Sichtbarkeit auf allen Oberflächen
  (Contract-Versionsbump + WebUI-Konsument), Un-Park-Kommando, Cap mit
  Elided-Count.
- `trg-0a294ef3` (stiller erfolgreicher atomic-write-Retry — die eine
  Observable, die das „unlocked readers are safe"-Design beim Degradieren zeigen
  würde) reitet auf S1 mit: gleiche Primitive, gleiche Datei.
- **Bleibt Restliste IM Anker, nicht als eigene Karten:** Audit-Befunde 14 und
  20–29 (Design-Änderungen + ~34 LOC Duplikation). Sonst produziert die
  Konsolidierung sofort 15 neue Items.

### IT-2 — Grade-Snapshot-Attribution & Event-Log-Integrität *(1 Iterate)*
Absorbiert `trg-aea8c97e`, `trg-ca4fc0e7`, `trg-1603000f`, `trg-5e945a39`,
`trg-465a2caf`, `trg-c97faa35` — alle sechs sind Nachbeben von PR #485.

`trg-aea8c97e` benennt die **eine** gemeinsame Ursache: Attribution liest
*committed ancestry*, Grade/Score messen den *Working Tree*.

- `trg-ca4fc0e7` ist dort explizit als **superseded** markiert.
- `trg-1603000f` (nichts misst den Default-Branch; 18 von 18 gesampelten
  Snapshots kamen per Squash auf main) wird ausdrücklich **re-scoped**.
- `trg-5e945a39`: 172 von 587 Event-Zeilen sind grade_snapshots, 16 distinkte
  Werte bei 29 Übergängen in 16 Tagen → ~83 % ohne neue Information; am
  2026-07-27 allein 35 Snapshots aus 15 Sessions, alle identisch. Plus der
  Verlustpfad für einen Main-Root-Append. **Falls die Spec >5 ACs wird: diese
  Hälfte als zweiten Iterate abspalten.**
- `trg-465a2caf`: die 18/18-Probe, auf der die Design-Entscheidung hing, kann
  nicht diskriminieren (dieses Repo squash-merged alles) — Entscheidung
  wahrscheinlich richtig, muss aber auf ihre zwei tragfähigen Argumente neu
  aufgehängt werden. Reine Record-Arbeit, gleicher PR.
- `trg-c97faa35`: `event_amended --fields` kann Attribution **und Score**
  überschreiben (reproduziert: `lineage=branch score=12` liest zurück als
  `lineage=main score=99.9`), und `docs/hooks-and-pipeline.md` behauptet das
  Gegenteil. Anderer Code, derselbe Doc-Absatz → gleicher PR.

### IT-3 — F11 sagt die Wahrheit über den Lauf, den es prüft *(1 Iterate)*
Absorbiert `trg-81fbf8ed`, `trg-51a57370`, `trg-64372769`, `trg-ffddd6b9`.
Vier Fail-Open-Pfade im **selben Gate**; zwei davon in derselben Datei.

- `trg-81fbf8ed` (high): die Ledger-Prüfung vergleicht nie
  `iterate_latest.run_id` mit dem geprüften Lauf. Da die Datei in
  `DERIVED_SNAPSHOTS` liegt, setzt der vom Verifier selbst vorgeschriebene
  Restore sie auf den **Vorlauf** zurück — beobachtet: „complete: 30 tested,
  1 untestable", während der Lauf 6 Verhalten hatte. Für eine autonome Kampagne
  der gefährlichste Einzelbefund im Backlog.
- `trg-51a57370`: Review-Floor akzeptiert `external_code=completed` ohne jede
  Evidenz (findings_count 0 / provider null / raw_excerpt null); und die Prüfung
  gibt *skipped* zurück, wenn der Iterate-Eintrag fehlt.
- `trg-64372769`: `REVIEW_TYPES` hat kein `spec` → der Stage-1-HARD-GATE kann
  nicht beweisen, dass er lief. Fasst dieselbe Datei und denselben Contract an
  wie `trg-51a57370` — getrennt geschickt überschreiben sie sich.
- `trg-ffddd6b9` (low): drei Verengungen am no-silent-revert-Check.

### IT-5 — Klassifikation & Risiko-Erkennung *(1 Iterate)*
Absorbiert `trg-ee7b83e5`, `trg-496e63a7`. Beide ändern, **welche Phasen feuern**.

- `trg-ee7b83e5` (gemessen über 67 Läufe): 79 % medium, 16 % small, 3 % trivial,
  1 % large. Der Fall-Through-Default ist der Median der jüngsten Historie und
  wird selbst zur Historie — selbstverstärkend. Probe: „add a missing docstring"
  → medium mit `prior_source=history`, keine Risk-Flags. Zeremonie-Anteil pro
  gemergtem Iterate: 54 % Median vor der Derived-Snapshot-Änderung, ~34 % danach.
- `trg-496e63a7`: `TOUCHES_BUILD_FILE_PATTERNS` ist JS-only — `uv.lock`,
  `poetry.lock`, `requirements*.txt` lösen in einem Python-Monorepo kein
  `touches_build` aus.

*Risiko:* eine Kalibrierungsänderung mitten in einer Kampagne verschiebt Gates.
Klar vor REQ-3 oder klar danach, nicht mittendrin.

### IT-6 — Run-Config-Integrität *(1 Iterate)*
Absorbiert `trg-f2d69527`, `trg-d1e466aa`. Gleiche Datei-Familie
(`config_factory` + Schema).

- `trg-f2d69527`: eine unlesbare Config wird wie eine fehlende behandelt →
  „standalone", und damit schalten sich Phase-Gate, `--force`-Begründungspflicht
  und `validation_overrides[]` **gleichzeitig** ab — genau im degradierten
  Zustand, in dem Evidenz zählt. Der Folge-Bootstrap ersetzt die Datei dann
  atomar und verwirft `phase_tasks`. Unter ADR-114 als „Rejected" erfasst.
- `trg-d1e466aa` (P3): `current_step` / `completed_steps` sind write-once mit
  zwei Lesern (`phase_quality._resolution.resolve_source`, compliance
  `mermaid.py`) — beide auf `phase_tasks[]` migrieren, dann Felder ziehen.

### IT-7 — Die Review-Maschinerie schliesst ihren Kreis *(2 Iterates, ein Anker)*
Absorbiert `trg-9e2ce202`, `trg-71d7a4fa`.

- **7a, klein, zuerst:** ein Fail-Closed-Verdict überlebt seine Ursache.
  `CHANGES_REQUESTED` wird von einem späteren `COMMENTED` nicht aufgehoben →
  `mergeStateStatus BLOCKED` bei grünen Checks und null offenen Threads. PR #446
  hing an fünf veralteten Verdicts (bdd788a1, 720f0de8, 75e538c1, 2ea75602,
  1086cf4e), überlebte den Fix in #461 und sechs saubere Reviews; gemergt erst
  nach manuellem Dismiss. Symptom ist **Stille** — nichts benennt den Blocker.
  *Schwanz:* das gevendorte pr_review im WebUI-Repo braucht denselben Fix.
- **7b:** `sub-iterate-runner` hat kein Agent-Tool, und die Kampagnenschleife
  (campaign-mode.md 3a–3i) spawnt die Cascade nirgends — der Orchestrator
  blockiert bei 3d auf dem DONE-Marker, der erst nach F6-Commit und Push kommt.
  Verschachteltes Spawnen ist am 2026-07-28 gemessen (nested child → `NESTED_OK`).
  Offen ist nur noch ADR-029s eigentlicher Einwand: **Token-Kosten**, nicht
  Machbarkeit. Abwägen gegen die Kosten, Kampagnen-Sub-Iterates ohne
  Spec-Compliance-Gate auszuliefern. Voraussetzung für IT-1-als-Kampagne und
  für REQ3.04/05/06.

### IT-8 — Die lokale Entwicklungsschleife berichtet die Wahrheit *(1 Iterate)*
Absorbiert `trg-ecddb31f`, `trg-410ef2a6`, `trg-c6e75011`.
**Zwei sind Dismiss-Kandidaten — erst messen:**

| Item | Vorprüfung 2026-07-28 | Vorgehen |
|---|---|---|
| `trg-c6e75011` | `plugins/shipwright-security/.shipwright/` **existiert nicht mehr**; PR #474 hat den Leak gefixt | Unit einmal laufen lassen; sauber → dismissen |
| `trg-410ef2a6` | Ursache war ein Windows-`os.replace`-Bug, gefixt in `run-unit-parallel-race`; Karte am 2026-07-28 **neu** gefeuert | Suite parallel messen. Grün → dismissen. Rot → echte neue Race |
| `trg-ecddb31f` | offen | der eigentliche Inhalt: `update-marketplace.sh` schreibt in die Version aus `installed_plugins.json`, `check_plugin_cache_sync.py` vergleicht gegen Repo-HEAD → „up to date" vs. „drifted" für dieselbe Lage |

Greifen beide Dismisses, schrumpft IT-8 auf einen Einzeiler — dann an IT-0
anhängen statt eigener Iterate.

### IT-9 — Host-Checks *(1–2 Iterates)*
Supersedes `trg-c7e5835b`, absorbiert `trg-9862202d`, `trg-80e3b3cd`.

`trg-c7e5835b` beanspruchte bereits **alle** Workflow-Dateien exklusiv — damit
ist die Zuordnung erzwungen, nicht gewählt. Teil 1 ist als PR #475 gelandet.

- Restpunkte der Ursprungskarte: gescaffoldeter Reviewer soll fail-closed werden
  statt grosse Änderungen zu überspringen; Fork-PRs ohne Credentials über den
  zweistufigen Artefakt-Weg; must-pass-Ableitung; Verdict-Label am Security-Gate;
  `scripts/verify_contract_surface.py` ist an nichts verdrahtet.
- `trg-9862202d`: zwei Checks laufen auf jedem PR und halten nichts auf
  („Empirical calibration", „Prepare review request") — Ruleset-Änderung bei
  GitHub, kein Code. **LANDMINE:** ein Check, der *nicht* auf jedem PR läuft,
  blockiert als Required **jeden** PR für immer; `grade-empirical.yml` erst
  prüfen. Danach dasselbe im WebUI-Repo.
- `trg-80e3b3cd`: **kein** CI-Job läuft auf Windows. Ein Windows-only-Defekt ist
  bereits grün auf main gelandet (`97392eea`, shipwright-changelog: Kindprozess
  kodiert stderr mit Locale-Codec, jeder Leser dekodiert utf-8); und
  Windows-Fixes werden von plattform-gegateten Tests „verifiziert", die CI immer
  skippt. Muss hierher, weil es eine Workflow-Datei ist.

### REQ3.04 *(neu, supersedes)* — Mechanik Monorepo + der Spec-Reader
Supersedes `trg-7085d783`, absorbiert `trg-1d7d91d0`, `trg-2ea0b99a`, `trg-8bf97fd4`.

Entscheidung des Owners 2026-07-28: das frühere IT-4 wird **nicht** eigener
Anker, sondern Teil von REQ3.04 — beide fassen AC-Parsing an, parallel geht nicht.

- Unverändert aus REQ3.04: Evidenzkette, AC-Identität, Manifest v4,
  AC-Test-Bindung, Layers-Promotion, KEYSTONE-GATE, Zubringer-Checks,
  Rewritability-Link, Track R diff-scoped.
- **Neu, als Vorarbeit:** `trg-1d7d91d0` — `check_s5_fr_coherence` meldet 19 von
  19 Requirements als „ohne Beschreibung und ohne Acceptance Criteria", alle
  falsch. Der `spec_parser` kennt nur `**Acceptance Criteria:**`; ausgeliefert
  wird von /shipwright-project **und** /shipwright-adopt `### FR-XX.YY — Titel`
  mit blanken Bullets. Ein AC-Identitäts-Manifest auf einem Parser zu bauen, der
  die eigene Ausgabeform nicht liest, ist der falsche Boden.
- **Neu:** `trg-2ea0b99a` — das Cross-Layer-Gate erkennt Verhaltensänderung an
  einer geänderten FR-**Tabellenzeile**; die geltende Mint-Regel fügt Kriterien
  **unter** einer unveränderten Zeile hinzu. Beobachtet an PR #446: vier
  geminzte Kriterien, 95 neue Tests, Gate sagt „could-not-determine". Feuert bei
  **jedem** kriterien-mintenden Iterate → genau die Gewöhnung an Rot, gegen die
  FR-01.06 gerade gehärtet wurde.
- **Neu, abspaltbar:** `trg-8bf97fd4` (S2b) — ~10 Call-Site-Entscheidungen zur
  Requirement-Discovery. Aus dem Korpus gemessen: ≥10 von 15 Walks laufen in
  versteckte Verzeichnisse, ≥7 in `iterate/`, 2 rekursiv, 4 crashen wenn der
  Planning-Pfad eine Datei ist, 2 sortieren nicht — welches Dokument sie treffen
  hängt an der Dateisystem-Reihenfolge. Zehn bewusste Verhaltensänderungen sind
  zehn Entscheidungen, kein Refactor. Voraussetzung: S2 gemergt.
  **Loseste Kopplung der drei** — wenn REQ3.04 zu breit wird, als eigener
  Sub-Iterate herauslösen.

---

## Unangetastet

| Item | Grund |
|---|---|
| `trg-137f48b5` REQ3.05 · `trg-b95ab887` REQ3.06 · `trg-e9fa7c49` REQ3.09 · `trg-b5bd4a0a` REQ3.10 | die fortzusetzende Arbeit, keine Konsolidierungsmasse |
| `trg-57317128` Plugin-Scope-Split | vollständige Spec + ACs + 3 benannte Blocker, extern reviewed (GPT-5.4 + Gemini), Entscheidungen getroffen — fertig zum Bauen |
| `trg-2f89afcf` adoptierte Repos ohne Refresh-Producer | **zeitkritisch**: „decide before the refresh-producer iterate ships"; betrifft fremde gemanagte Repos, eigene Entscheidung |
| `trg-d190cc37` WebUI Grade-Trend | **anderes Repo** — kann kein Teil eines Monorepo-Iterates sein; gekoppelt an IT-2 |

## Deferred

`trg-239ee0ad` — Changelog-Aggregator erhält BOM/Zeilenenden nicht. P3, in
PR #472 bewusst akzeptiert, im Modul-Docstring **und** in der Iterate-Spec
dokumentiert, kein natürlicher Bündelpartner. `defer` mit Revisit-Datum statt
dismiss, sonst geht die Notiz verloren.

---

## Nachtrag: zwei Beobachtungen aus der Durchführung (2026-07-28)

Beide beim Anlegen/Dismissen selbst angefallen, beide gehören inhaltlich zu
schon angelegten Ankern — deshalb **keine** neuen Karten.

### 1. Der Compliance-Rollup mintet bei identischem `dedupKey` eine neue Karte

Gemessen über `.shipwright/triage.jsonl`: der `dedupKey`
`compliance:backlog:e67682c0a667` trägt **fünf** verschiedene Karten-Ids —
`trg-a5b167f4` (07-27 17:14) · `trg-bc786d2a` (07-27 22:40) · `trg-a886b420`
(07-28 07:45) · `trg-8f022f38` (07-28 08:05) · `trg-965c563e` (07-28 08:18).
Drei davon innerhalb von 33 Minuten. `compliance:backlog:1899f8c34ff5` steht
sogar 14-mal. Offen ist jeweils nur die letzte — die Vorgänger werden
geschlossen, aber die Id wandert bei jedem Regen.

Das ist eine frisch gemessene Instanz genau des Mechanismus, den `trg-51f8e2a1`
Punkt (1) beschreibt (Dedup unterdrückt nur, solange der Treffer *offen* ist) —
gehört damit zu **IT-1/S3** und braucht keine eigene Karte. Wert für S3: das
Verhalten ist nicht theoretisch, es passiert mehrmals täglich.

**Konsequenz für IT-0:** `trg-965c563e` (dieselben fünf Befunde wie das von IT-0
absorbierte `trg-8f022f38`) bleibt bewusst **offen**. Sie ist produzenten-erzeugt
und schliesst sich selbst, wenn D1/D3/F6/H1/H2 behoben sind — also wenn IT-0
fertig ist. Sie zu dismissen würde beim nächsten Compliance-Regen nur die nächste
Id erzeugen.

### 2. Das Status-Precondition der CLI hat einen Doppelschreiber abgefangen

`trg-8f022f38` wurde um 10:07Z **im WebUI** dismissed (`by: "webui"`, `reason: null`),
während diese Konsolidierung lief. Der anschliessende CLI-Dismiss verweigerte
sauber: *„has status='dismissed'; only `triage` is dismissable"*.

Bemerkenswert, weil die IT-1-Audit-Datei genau diesen Schreiber als den
nicht-kooperierenden benennt (`proper-lockfile`, komponiert nicht mit dem
Python-Byte-Lock). Hier ist es in die **sichere** Richtung ausgegangen — die
Vorbedingung hat gegriffen. Das ist Evidenz *für* den S2-Ansatz
(`expected_status` unter dem Lock), nicht dagegen: derselbe Schutz existiert für
`mark_status` heute nicht.
