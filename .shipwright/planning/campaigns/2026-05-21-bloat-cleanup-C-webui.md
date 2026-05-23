# Campaign — Bloat Cleanup Track C (WebUI Cleanup)

> Cleanup der God-Files in shipwright-webui. Quellplan:
> `c:\01_Development\shipwright\Spec\Launch preparation bloat cleanup.md`
> (Sektion 6.2 = Track C Inventur, Sektion 7.3 = Aufwand,
> Sektion 8 = Risk Register).
>
> **Voraussetzung:** Campaign A vollständig gemerged (Pre-Commit + CI
> in WebUI aus A.defense). WebUI hat **kein Loop-Gate** —
> Enforcement nur commit-time. PR-Beschreibung pro Iterate muss
> Allowlist-Diff zeigen.

## Status

- **Started:** _not started_
- **Current iterate:** _pending kickoff (C1 first)_
- **Voraussetzung:** Campaign A merged
- **Baseline (Campaign-Start):** _wird beim ersten Iterate erfasst_
- **Repo:** `c:\01_Development\shipwright-webui`

## Iterates

### C1 — `CLAUDE.md` Split

- **Status:** not started
- **Scope:** ~1.600 LOC → Kern + `references/`. ADRs nur referenziert.
- **Files:**
  - `CLAUDE.md` (Kern ~200 LOC, Index auf references/ + ADR-Liste)
  - `references/architecture.md` (NEU)
  - `references/hard-rules.md` (NEU, alle 22 DO-NOTs)
  - `references/adr-index.md` (NEU, Links auf
    `.shipwright/planning/adr/`)
  - `references/regression-guards.md` (NEU)
- **Acceptance:**
  - Kern ≤ 400 LOC.
  - Jede reference-Datei ≤ 300 LOC.
  - 22 DO-NOT-Regeln vollständig in `hard-rules.md`.
  - Allowlist-Entry entfernt.
- **Risiko:** Niedrig.
- **Dependencies:** Campaign A merged.

### C8 — ADR `pty-manager.ts` als Exception

- **Status:** not started
- **Scope:** Nur Doku. Kein Code-Touch.
- **Files:**
  - `.shipwright/planning/adr/NNN-pty-manager-deep-module.md` (NEU,
    nutzt Template aus A.defense)
  - `bloat-baseline.json` (Entry-State von `grandfathered` →
    `exception` mit `adr`-Verweis)
- **Acceptance:**
  - ADR enthält Ousterhout-Argument (PTY-Lifecycle = atomare
    Modulkohäsion: Spawn/Backpressure/Idle/Scrollback gehören
    zusammen).
  - Akzeptanzkriterium für künftigen Split definiert (z.B. „Auth-
    Layer hinzukommt").
  - Re-Review-Datum gesetzt (typischerweise +6 Monate).
- **Risiko:** Null.
- **Dependencies:** Campaign A merged (Template existiert).

### C6 — `TaskDetailHeader.tsx` Split (+ C8 ADR mit drin)

- **Status:** not started
- **Scope:** 1.015 LOC → Header-Shell + 4 Sub-Komponenten.
- **Files:**
  - `client/src/components/external/TaskDetailHeader.tsx`
    (Shell ~250)
  - `…/external/header/StateBadge.tsx` (NEU)
  - `…/external/header/LaunchCTA.tsx` (NEU)
  - `…/external/header/ResumeCTA.tsx` (NEU)
  - `…/external/header/TitleEdit.tsx` (NEU)
  - Vitest-Tests für jede Sub-Komponente
- **Acceptance:** je Komponente ≤ 300 LOC; Vitest + bestehende E2E-
  Specs grün; Allowlist-Entry entfernt.
- **Risiko:** Niedrig-Mittel.
- **Dependencies:** parallel zu C3/C4/C7 möglich.

### C3 — `BubbleTranscript.tsx` Split

- **Status:** not started
- **Scope:** 1.618 LOC → Shell + 4 Sub-Komponenten + Hook.
- **Files:**
  - `client/src/components/external/BubbleTranscript.tsx`
    (Shell ~200)
  - `…/external/transcript/TranscriptRow.tsx` (NEU)
  - `…/external/transcript/ToolOutputBlock.tsx` (NEU)
  - `…/external/transcript/MarkdownChunk.tsx` (NEU)
  - `…/external/transcript/AnsiText.tsx` (NEU)
  - `client/src/hooks/useTranscriptScroll.ts` (NEU)
- **Acceptance:** je Komponente ≤ 400 LOC (UI-Toleranz); bestehende
  E2E-Specs (Bubble-Rendering, Tool-Folding, Markdown, ANSI) grün;
  Allowlist-Entry entfernt.
- **Risiko:** Mittel.
- **Dependencies:** parallel zu C4/C6/C7 möglich.

### C4 — `NewIssueModal.tsx` Split

- **Status:** not started
- **Scope:** 1.492 LOC → Modal-Shell + 3 Modus-Komponenten.
- **Files:**
  - `client/src/components/external/NewIssueModal.tsx`
    (Modus-Router, ~150 LOC, wählt Sub-Modal je nach Modus)
  - `…/external/new-issue/ModalShell.tsx` (NEU, shared layout)
  - `…/external/new-issue/NewPipelineModal.tsx` (NEU)
  - `…/external/new-issue/NewIterateModal.tsx` (NEU)
  - `…/external/new-issue/NewTaskModal.tsx` (NEU)
- **Acceptance:** je Sub-Modal ≤ 400 LOC; Vitest + E2E für alle drei
  Modi grün; Allowlist-Entry entfernt.
- **Risiko:** Mittel.
- **Dependencies:** parallel.

### C7 — `InboxPage.tsx` Split

- **Status:** not started
- **Scope:** 967 LOC → Page-Shell + Sections + Data-Hook.
- **Files:**
  - `client/src/pages/InboxPage.tsx` (Page-Shell ~250)
  - `…/pages/inbox/PendingSection.tsx` (NEU)
  - `…/pages/inbox/HistorySection.tsx` (NEU)
  - `…/pages/inbox/InboxFilters.tsx` (NEU)
  - `client/src/hooks/useInboxData.ts` (NEU)
- **Acceptance:** je Komponente ≤ 300 LOC; Inbox-E2E-Specs grün;
  Allowlist-Entry entfernt.
- **Risiko:** Mittel.
- **Dependencies:** parallel.

### C5 — `EmbeddedTerminal.tsx` Split

- **Status:** not started
- **Scope:** 1.479 LOC → Wrapper + Sub-Hooks (useTerminalSocket
  existiert bereits separat, ~438 LOC).
- **Files:**
  - `client/src/components/terminal/EmbeddedTerminal.tsx`
    (Wrapper ~250)
  - `client/src/hooks/usePasteImage.ts` (NEU)
  - `client/src/hooks/useTerminalResize.ts` (NEU)
  - `client/src/lib/terminal/xtermAddons.ts` (NEU, Addon-Registry)
- **Acceptance:** Wrapper ≤ 300 LOC; xterm + WS + paste-image
  Smoke-Tests grün; Live-Replay-E2E grün; Allowlist-Entry entfernt.
- **Risiko:** Hoch (xterm.js + WS sind fragil; ADR-087/088-
  Constraints prüfen).
- **Dependencies:** nach C3/C4/C6/C7 (sammelt Lernerfahrungen).

### C2 — `external/routes.ts` Split (letzter, größter Hebel)

- **Status:** not started
- **Scope:** 2.877 LOC → 9 Sub-Router. `external/index.ts` bündelt
  nur Hono-Sub-App-Registrierung.
- **Files:**
  - `server/src/external/index.ts` (Sub-App-Registry, ~80 LOC)
  - `server/src/external/tasks/routes.ts` (NEU)
  - `…/external/launch/routes.ts` (NEU)
  - `…/external/transcript/routes.ts` (NEU)
  - `…/external/inbox/routes.ts` (NEU)
  - `…/external/actions/routes.ts` (NEU)
  - `…/external/preview/routes.ts` (NEU)
  - `…/external/file/routes.ts` (NEU)
  - `…/external/tree/routes.ts` (NEU)
  - `…/external/run-config/routes.ts` (NEU)
  - Tests entsprechend aufgeteilt (`routes.test.ts` 775 LOC schrumpft
    auf je ~150 LOC pro Sub-Router)
- **Acceptance:**
  - Je Sub-Router ≤ 400 LOC.
  - URL-Pfade unverändert (Backward-Compat-Check via E2E gegen alle
    bestehenden Endpoints).
  - Frontend-Callsites unverändert grün (`externalApi.ts`, alle
    Hooks, alle Komponenten).
  - Allowlist-Entries entfernt (Source + Test).
- **Risiko:** Hoch (zentrale API-Surface, viele Frontend-Callsites).
- **Dependencies:** alle anderen C-Iterates merged (sammelt Tooling-
  und Vitest/Playwright-Lernerfahrungen aus C3/C4/C5/C6/C7).

## Phase-D-Akzeptanz für Campaign C

- `bloat-baseline.json` enthält keine `state=grandfathered`-Einträge
  mehr.
- Einzig erlaubt: `state=exception` (erwartet: nur
  `pty-manager.ts` aus C8).
- `npm run build`, `npm test`, `npm run lint`, `npm run typecheck`
  in `server/` und `client/` grün.
- Alle Playwright-E2E-Specs grün, insbesondere ADR-gehärteten:
  `35-no-chat-panel.spec.ts`, `v0-9-6-live-pty-replay.spec.ts`,
  `triage-fix-now.spec.ts`.
- CI postet PR-Kommentar mit Allowlist-Diff pro Iterate-PR;
  Anti-Ratchet-Block grün getestet.

## Notes

_Cross-Iterate-Beobachtungen hier sammeln._
