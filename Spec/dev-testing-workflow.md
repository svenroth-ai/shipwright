# Dev & Testing Workflow (Sven)

> Temporäres Dokument für die Demo-Case Testing Phase.
> Kann gelöscht werden sobald die Skills stabil sind.

## Wie Änderungen sofort wirksam werden

Der Shell-Alias `shipwright` zeigt direkt auf die Dateien im Repo.
**Kein Build, kein Copy, kein Install** — jede Dateiänderung ist sofort live.

### Was wann wirksam wird

| Geändert | Wann wirksam | Aktion nötig |
|----------|-------------|-------------|
| `SKILL.md` | Nächste Session | `exit` → `shipwright` neu starten |
| `references/*.md` | Nächste Session | `exit` → `shipwright` neu starten |
| `hooks.json` | Nächste Session | `exit` → `shipwright` neu starten |
| `scripts/*.py` | Sofort | Wird per `uv run` frisch geladen |
| `scripts/*.sh` | Sofort | Wird per `bash` frisch geladen |
| `config.json` | Sofort | Wird bei jedem Script-Aufruf gelesen |
| `shared/profiles/*.json` | Sofort | Wird bei Bedarf gelesen |
| `shared/templates/*` | Sofort | Wird bei Bedarf gelesen |

**Faustregel:** Markdown + JSON = neue Session. Python/Bash = sofort.

## Typischer Test-Zyklus

```
1. Starte: shipwright
2. Teste: /shipwright-run "Demo Case"
3. Beobachte was nicht funktioniert
4. Exit (Ctrl+C oder "exit")
5. Editiere die SKILL.md / Scripts
6. Starte: shipwright
7. Teste erneut
```

## Tests nach Änderungen laufen lassen

```bash
# Einzelnes Plugin testen (nach Script-Änderungen)
uv run pytest plugins/shipwright-project/tests/ -v

# Alle Plugin-Tests
for p in project plan build changelog test deploy run; do
  echo "=== $p ===" && uv run pytest plugins/shipwright-$p/tests/ -q
done

# Integration-Tests
uv run pytest integration-tests/ -v
```

## Änderungen committen

```bash
# Nur geänderte Dateien stagen
git add plugins/shipwright-project/skills/shipwright-project/SKILL.md
git commit -m "fix(project): improve interview question flow"

# Pushen
git push
```

## Häufige Situationen

### SKILL.md Änderung hat keinen Effekt
→ Claude Code cached Plugin-Dateien pro Session. **Neue Session starten.**

### Script wirft Fehler
→ Direkt testen ohne Claude Code:
```bash
uv run plugins/shipwright-project/scripts/checks/setup-session.py --help
```

### Hook feuert nicht
→ Hooks werden nur bei registrierten Events ausgeführt. Prüfe `hooks.json`.

### Profil-JSON ändern
→ Sofort wirksam, kein Neustart nötig. Wird bei jedem `inference.py` Aufruf gelesen.
