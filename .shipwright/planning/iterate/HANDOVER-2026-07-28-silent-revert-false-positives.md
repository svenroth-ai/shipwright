# Übergabe: `check_no_silent_revert` meldet zwei Dinge als Revert, die keiner sind

**Stand 2026-07-28.** Gefunden während `iterate-2026-07-27-checks-that-gate-nothing`
(PR #475, gemergt als `1786fc59`). Der Fehler ist **nicht** aus diesem Lauf — er kam
mit **#477** (`5b351ed4`) herein, während der Branch offen war. Ich war nur der Erste,
der ihn getroffen hat, weil mein Branch `main` viermal integrieren musste.

## Wo

- **Code:** `shared/scripts/tools/verifiers/silent_revert.py` — `dropped_lines()`
  (Z. 113 ff.), die Schleife über `_integration_merges()` (Z. 78 ff.).
  Die entscheidenden drei Zeilen sind 163–167:
  ```python
  gained  = theirs - (_file_lines(root, base, path) or set())
  ours    = _file_lines(root, head, path)
  missing = gained if ours is None else gained - ours
  ```
- **Tests:** `shared/tests/test_silent_revert.py`
- **Notausgang:** `iterate_latest.declared_removals[{path, reason}]`, geprüft von
  `_covered()` (Z. 174 ff.)

## Was der Prüfer tut

Pro Integrations-Merge fragt er: *„Trägt HEAD noch jede Zeile, die die `main`-Seite
dieses Merges hatte und dessen Basis nicht?"* Das ist die richtige Frage — sie ist der
Grund, warum die echte Landmine (ein `git reset --soft` auf eine weitergezogene Basis,
siehe #436) überhaupt auffällt. **Der Check ist erhaltenswert. Nicht abschwächen.**

## Die zwei falschen Treffer

### (A) `main` hat den Text später selbst gelöscht — leicht zu beheben

Merge 1 holt `main@X`. Ein späterer `main`-Commit entfernt oder ersetzt diesen Text.
Man integriert erneut. HEAD hat ihn korrekt nicht mehr — aber der Check bewertet
Merge 1 weiterhin gegen HEAD und meldet Verlust.

Real getroffen: `cf6d326b` brachte den Text, `f7eee6f4` ersetzte ihn
(`test_record_review_pass_cli.py` wurde aufgeteilt, ein Iterate-Spec umgeschrieben).

**Beweis, dass nichts verloren ging:**
```bash
git diff origin/main HEAD -- <pfad>          # LEER  → identisch mit main
MSYS_NO_PATHCONV=1 git show "origin/main:<pfad>" | grep -F "<gemeldete zeile>"  # nicht da
```

**Denkbarer Fix:** Zeilen herausfiltern, die auch die **aktuelle** Spitze des
Default-Branch nicht mehr hat. Was `main` selbst weggeworfen hat, kann dieser Branch
nicht zurücknehmen.

### (B) Eine Zeile wurde *bearbeitet* — hier liegt die eigentliche Arbeit

Der Vergleich läuft über ganze Zeilen. Wer einer Tabellenzeile einen Satz hinzufügt,
dessen alte Zeile gilt als fallengelassen. **Der Filter aus (A) greift hier nicht**:
`main` hat die alte Fassung ja noch.

Real getroffen: `docs/hooks-and-pipeline.md`, die `triage.outbox.jsonl`-Zeile.
Nachweis, dass nichts fehlte — die eigene Zeile **minus** dem hinzugefügten Satz war
zeichengleich mit `main`s Zeile.

**Das ist eine Entwurfsfrage, kein Einzeiler.** Mengen-Subtraktion über Zeilen kann
„geändert" nicht von „gelöscht" unterscheiden. Vermutlich braucht es einen echten
Drei-Wege-Vergleich (`git merge-tree` gegen die aktuelle Spitze und prüfen, ob das
Ergebnis für diese Datei HEADs Inhalt entspricht) statt `gained - ours`.
**Genau dafür ist der Doubt-Reviewer da — bitte nicht die erste Idee bauen.**

## Reproduktionsfälle

Vier davon liegen fertig in `1786fc59` unter
`shipwright_test_results.json → iterate_latest.declared_removals`, jeder mit seinem
Beweis in `reason`. Drei sind Fall (A), einer ist Fall (B).
(`iterate_latest` wird vom nächsten Lauf überschrieben — aus dem Commit lesen,
nicht aus der Arbeitskopie.)

## Warum das zählt

Ein Tor, dessen Notausgang zur Routine wird, ist auf dem Weg zur Deko — dieselbe
Krankheit, die Karte `trg-c7e5835b` behandelt hat. Vier `declared_removals` in einem
einzigen Lauf sind kein Betriebsgeräusch, sondern das Signal.

Und: der Check meldet sich **nur** bei Branches, die `main` mehr als einmal
integrieren — also genau bei den langlaufenden, wo eine echte Rücknahme am
teuersten wäre. Dort ist er heute am unzuverlässigsten.

## Ablauf für die neue Sitzung

```
/shipwright-iterate --type bug "check_no_silent_revert meldet bearbeitete Zeilen und
von main selbst gelöschte Inhalte als Revert — siehe
.shipwright/planning/iterate/HANDOVER-2026-07-28-silent-revert-false-positives.md"
```

- **Pfad C (BUG)** — erst Ursachenforschung (`references/F-debug.md`), dann Fix.
  Der Iron Law gilt: kein Fix ohne Ursache, und ein Test, der den Fehler festnagelt,
  **bevor** er behoben wird.
- **Die Review-Kaskade läuft diesmal.** Der Operator hat die Subagenten am
  2026-07-28 ausdrücklich angefordert (`spec-reviewer` → `code-reviewer` →
  `doubt-reviewer`). Die Regel im System-Prompt lautet *„unless the user requested
  it"* — diese Bedingung ist erfüllt. Beim Doubt-Reviewer liegt der Schwerpunkt auf
  Fall (B). Alle fünf Review-Typen wie üblich in `reviews.json` schließen.
- **`touches_ci_supplychain` feuert nicht** (kein `.github/workflows/**`), also kein
  `ci_supplychain_ack`. Damit auch **kein** Rule-4-Block: der PR kann normal grün
  werden und regulär mergen — anders als #475.
- **Vor dem Verdrahten prüfen:** Der Fix ändert einen Prüfer, der auf *dieser* Sorte
  Branch läuft. Ihn gegen den eigenen Branch laufen lassen, nachdem `main` integriert
  wurde — sonst wiederholt sich #475s Lehre (lokal grün ≠ grün in der Umgebung, in
  der das Tor läuft, siehe `feedback_gate_must_be_verified_in_its_own_environment`).

## Offene Punkte aus #475 (nicht Teil dieses Bugs)

1. **`Prepare review request`** läuft bei jedem PR und hält nichts auf. Eintragen ist
   eine Ruleset-Änderung bei GitHub — Operator-Entscheid. Dass er immer läuft, ist
   geprüft, ein Deadlock also ausgeschlossen.
2. **WebUI-Karte `trg-9e6c0b66`** — Zwei-Stufen-Review portieren.
3. **`ADVISORY_CONTEXTS` bleibt leer.** Nicht vorsorglich füllen.
