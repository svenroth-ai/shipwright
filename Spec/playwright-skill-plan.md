# Plan: Playwright Browser Testing Integration

## Context

Shipwright hat Playwright überall in der Architektur referenziert (Profile, SKILL.md, test_runner.py), aber nichts ist tatsächlich implementiert. Die Tests sind nur Script-Level (pytest). Sven will Replit-style Browser-Testing: nach jedem grösseren Build-Change einen visuellen Browser-Check. Dazu eine Full E2E Suite für shipwright-test.

## Zwei Capabilities

| | Browser Verify (in Build) | Full E2E (in Test) |
|---|---|---|
| **Trigger** | Nach jeder Section in shipwright-build | `/shipwright-test` oder `--e2e-only` |
| **Scope** | Seite laden, Screenshot, Console-Errors prüfen | Alle `e2e/*.spec.ts` ausführen |
| **Dauer** | 5-15 Sekunden | 30s-5min |
| **Auto-Fix** | Ja (Screenshot + DOM → browser-fixer Agent, max 3 Retries) | Ja (gleicher Mechanismus) |
| **Output** | Screenshot + pass/fail JSON | Playwright Report JSON |

## Neue Dateien

### Shared Infrastructure (3 Dateien)

1. **`shared/scripts/dev_server.py`** — Start/Stop/Status für Dev-Server des Zielprojekts
   - `uv run dev_server.py start --profile supabase-nextjs --cwd /project`
   - `uv run dev_server.py stop --cwd /project`
   - Trackt PID in `shipwright_dev_server.json`
   - Port-Check bevor Start (kein Konflikt)
   - Windows-kompatibel (`CREATE_NEW_PROCESS_GROUP`, `taskkill`)

2. **`shared/scripts/playwright_setup.py`** — Idempotentes Setup im Zielprojekt
   - Generiert `playwright.config.ts` aus Template (falls nicht vorhanden)
   - Installiert `@playwright/test` als devDependency (falls nicht vorhanden)
   - Installiert nur Chromium (`npx playwright install chromium`)
   - Erstellt `e2e/` Ordner
   - Output: `{"success": true, "config_path": "...", "browsers": ["chromium"]}`

3. **`shared/templates/playwright.config.ts.template`** — Playwright Config
   - Nur Chromium, JSON Reporter, `webServer` mit `reuseExistingServer: true`
   - `testDir: './e2e'`, `baseURL: localhost:3000`

### Browser Verify (2 Dateien)

4. **`shared/templates/browser-verify.ts.template`** — TypeScript Helper
   - Wird nach `e2e/browser-verify.ts` im Zielprojekt kopiert
   - Navigiert zu URL, wartet auf Network Idle, macht Screenshot
   - Sammelt Console-Errors, schreibt JSON-Ergebnis
   - Ausgeführt via `npx tsx e2e/browser-verify.ts`

5. **`plugins/shipwright-test/scripts/lib/browser_verify.py`** — Python Wrapper
   - Ruft den TypeScript Helper auf
   - Parsed JSON-Ergebnis
   - Gibt Screenshot-Pfad + Console-Errors zurück

### Auto-Fix Agent (1 Datei)

6. **`plugins/shipwright-test/agents/browser-fixer.md`** — Subagent
   - Empfängt: Screenshot (Bild), Console-Errors, DOM-Snapshot (letzte 5000 Zeichen)
   - Analysiert visuell (Claude ist multimodal)
   - Gibt strukturierte Fix-Empfehlung zurück
   - Retry-Loop (max 3) wird von SKILL.md gesteuert, nicht vom Script

### Full E2E Runner (1 Datei)

7. **`plugins/shipwright-test/scripts/lib/playwright_runner.py`** — Wraps `npx playwright test`
   - Parsed `e2e-results.json` (Playwright JSON Reporter Output)
   - Gibt strukturiertes Ergebnis zurück (passed/failed/skipped)

### Tests (3 Dateien)

8. **`shared/tests/test_dev_server.py`**
9. **`plugins/shipwright-test/tests/test_browser_verify.py`**
10. **`plugins/shipwright-test/tests/test_playwright_runner.py`**

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `shared/profiles/supabase-nextjs.json` | Neuer `dev_server` Abschnitt: `{"command": "npm run dev", "port": 3000, "ready_timeout_seconds": 60}` |
| `plugins/shipwright-build/skills/build/SKILL.md` | Neuer Step 4.5 "Browser Verify" nach Green Phase: Dev-Server starten, Screenshot, bei Fehler → browser-fixer Agent, max 3 Retries |
| `plugins/shipwright-test/skills/test/SKILL.md` | Step 3 ausbauen: Playwright Setup prüfen, E2E Tests ausführen, `--fix` Mode mit browser-fixer Agent |
| `plugins/shipwright-test/scripts/lib/test_runner.py` | E2E-Pfad auf `playwright_runner.py` umleiten, Setup-Check vor E2E |
| `plugins/shipwright-test/skills/test/references/test-layers.md` | Layer 3 mit echten Playwright-Details aktualisieren |

## Umsetzungsreihenfolge

**Phase 1: Infrastructure**
1. `shared/scripts/dev_server.py` + Test
2. `shared/scripts/playwright_setup.py` (kein Test nötig — Setup ist CLI-Wrapper)
3. `shared/templates/playwright.config.ts.template`
4. `shared/templates/browser-verify.ts.template`
5. `dev_server` Abschnitt in `supabase-nextjs.json`

**Phase 2: Browser Verify in Build**
6. `browser_verify.py` + Test
7. `browser-fixer.md` Agent
8. `SKILL.md` von shipwright-build erweitern (Step 4.5)

**Phase 3: Full E2E in Test**
9. `playwright_runner.py` + Test
10. `test_runner.py` anpassen
11. `SKILL.md` von shipwright-test erweitern (Step 3)
12. `test-layers.md` aktualisieren

## Verifikation

1. Alle bestehenden Tests weiterhin grün (~236)
2. `dev_server.py start/stop/status` funktioniert (Unit Test mit Mocks)
3. `browser_verify.py` parsed TypeScript-Output korrekt
4. `playwright_runner.py` parsed `e2e-results.json` korrekt
5. shipwright-build SKILL.md enthält Browser Verify Step
6. shipwright-test SKILL.md enthält echte Playwright-Anweisungen
7. browser-fixer Agent hat Screenshot-Analyse-Prompt
