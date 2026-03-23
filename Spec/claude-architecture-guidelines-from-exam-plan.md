# Plan: Claude Architect Best Practices in Shipwright integrieren

## Context

Abgleich der offiziellen Claude Architect Certification Exam Guidelines (5 Domains, 30 Task Statements) mit dem Shipwright SDLC Framework. **3 von 5 Domains sind bereits gut abgedeckt**, aber 6 Gaps existieren — plus 3 zusätzliche Erkenntnisse aus dem detaillierten Exam Guide (MD-Version).

### Was bereits gut ist (keine Aktion nötig)
- **Tool Scoping (2.3)**: Alle Subagents haben 3 Tools (Read/Grep/Glob) — weit unter dem 4-5 Max
- **Hub-and-Spoke (1.2)**: Orchestrator delegiert an isolierte Subagents, gibt Kontext explizit weiter
- **Context Management (5.4)**: Session-Handoff-Pattern mit `generate_session_handoff.py`
- **Security Hooks (1.4/1.5)**: Force-Push-Prevention, destruktive SQL-Erkennung, Root-Deletion-Schutz
- **Task Decomposition (1.6)**: Prompt-Chaining in Plan + adaptive Decomposition in Build
- **Session Resumption (1.7)**: `shipwright_run_config.json` als State-Machine, resume per Section

---

## P1: Structured Error Propagation (Domain 2.2, 5.3)

**Problem**: Scripts wie `write-section-on-stop.py` geben bei Fehlern leere Listen/`{}` zurück — stille Unterdrückung. Kein standardisiertes Error-Schema.

**Cert-Regeln**:
- "Never return a generic error. Include what broke, what was tried, what could be done instead." (5.3)
- "`isError` flag, `errorCategory`, `isRetryable` für intelligente Recovery" (2.2)
- "Distinguish access failures from valid empty results" (2.2)

### Schritte

1. **Erstelle `shared/scripts/lib/errors.py`** — Shared Error-Modul:
   ```python
   def structured_error(
       what_failed: str,
       what_was_attempted: str,
       error_category: str,        # "transient" | "validation" | "business" | "permission"
       is_retryable: bool,
       partial_results: dict | None = None,
       alternatives: list[str] | None = None
   ) -> dict:
       return {
           "success": False,
           "error": {
               "what_failed": what_failed,
               "what_was_attempted": what_was_attempted,
               "error_category": error_category,
               "is_retryable": is_retryable,
               "partial_results": partial_results or {},
               "alternatives": alternatives or [],
           }
       }
   ```

2. **Migriere `plugins/shipwright-plan/scripts/hooks/write-section-on-stop.py`** (Lines 101-129):
   - JSON-Decode-Fehler → `error_category="validation"`, `is_retryable=False`
   - Transcript nicht gefunden → `error_category="transient"`, `is_retryable=True`
   - Leerer Content → `error_category="business"`, `is_retryable=False`, `alternatives=["re-run section-writer"]`

3. **Migriere weitere Scripts**:
   - `plugins/shipwright-design/scripts/checks/setup-design-session.py` (Lines 51, 60: `return {}`)
   - `plugins/shipwright-changelog/scripts/lib/git_utils.py` (Lines 78, 80, 85: `return []`)
   - `plugins/shipwright-run/scripts/lib/orchestrator.py` (Lines 31, 35: `return {}`)

4. **Tests**: `shared/scripts/tests/test_errors.py`

### Dateien
| Aktion | Datei |
|--------|-------|
| neu | `shared/scripts/lib/errors.py` |
| neu | `shared/scripts/tests/test_errors.py` |
| modify | `plugins/shipwright-plan/scripts/hooks/write-section-on-stop.py` |
| modify | `plugins/shipwright-design/scripts/checks/setup-design-session.py` |
| modify | `plugins/shipwright-changelog/scripts/lib/git_utils.py` |
| modify | `plugins/shipwright-run/scripts/lib/orchestrator.py` |

---

## P1: Compliance Hooks — Übersteuerbare Enforcement (Domain 1.4, 1.5)

**Problem**: `shipwright-compliance` ist rein observational. Meldet Lücken, blockiert aber nie.

**Cert-Regeln**:
- "When compliance must be 100%, use programmatic enforcement. Hooks are laws." (1.4)
- "PostToolUse hooks to enforce compliance rules" (1.5)

**User-Anforderung**: Hooks müssen **übersteuerbar** sein. Der User sagt "Continue anyway" → wird gelogged und bei nächster Gelegenheit wieder aufgenommen.

### Design: Soft-Block mit Override-Logging

```
Hook blockiert (Exit-Code 2) → Claude zeigt Warning + "Continue anyway?"
  → User sagt "Continue anyway" → Hook-Output enthält Override-Instruktion
  → Override wird in `agent_docs/compliance_overrides.log` gelogged:
      Timestamp | Hook | Reason | User-Confirmation
  → Compliance-Plugin nimmt Overrides bei nächstem Report-Run auf
```

**Implementierung**: Exit-Code 2 = Soft-Block (Claude Code zeigt Message, User kann übersteuern). NICHT Exit-Code 1 (Hard-Block, nicht übersteuerbar).

### Schritte

1. **Erstelle `plugins/shipwright-compliance/scripts/hooks/check_rtm_coverage.py`**
   - PreToolUse-Hook, matched Bash-Calls mit `git commit`
   - Liest RTM-Coverage aus Compliance-Reports
   - Coverage < Threshold (default 80%) → Exit-Code 2 (Soft-Block)
   - Hook-Output enthält:
     ```json
     {
       "blocked": true,
       "reason": "RTM coverage 62% < 80% threshold",
       "details": {"coverage": 0.62, "threshold": 0.80, "missing": ["REQ-007", "REQ-012"]},
       "override_instruction": "User may say 'Continue anyway'. If so, log override to agent_docs/compliance_overrides.log with timestamp and reason.",
       "resume_note": "Coverage gap will be flagged again at next compliance checkpoint."
     }
     ```
   - Keine Config vorhanden (frühes Pipeline-Stadium) → Allow (Exit 0)

2. **Erstelle `plugins/shipwright-compliance/scripts/hooks/check_security_scan.py`**
   - PreToolUse-Hook, matched Deploy-Commands (`deploy|jelastic|vercel`)
   - Blockiert Deploy bei unresolved Critical-Findings → Exit-Code 2
   - Gleicher Override-Pattern: User kann übersteuern, wird gelogged

3. **Erstelle `plugins/shipwright-compliance/scripts/lib/thresholds.py`**
   - Zentrale Threshold-Config, liest aus `shipwright_compliance_config.json` Feld `"enforcement"`
   - Defaults: `rtm_coverage_min=0.80`, `allowed_critical_findings=0`, `sbom_completeness_min=0.90`
   - Alle Thresholds per Config pro Projekt anpassbar

4. **Modifiziere `plugins/shipwright-compliance/hooks/hooks.json`** — füge PreToolUse hinzu

5. **Erstelle `plugins/shipwright-compliance/scripts/lib/override_logger.py`**
   - Utility zum Schreiben von Override-Einträgen in `agent_docs/compliance_overrides.log`
   - Format: `[ISO-Timestamp] OVERRIDE hook=check_rtm_coverage reason="User confirmed continue" details={...}`
   - Compliance-Plugin liest diese Datei bei Report-Generierung und listet Overrides auf

6. **Tests**: `plugins/shipwright-compliance/tests/test_enforcement_hooks.py`

### Dateien
| Aktion | Datei |
|--------|-------|
| modify | `plugins/shipwright-compliance/hooks/hooks.json` |
| neu | `plugins/shipwright-compliance/scripts/hooks/check_rtm_coverage.py` |
| neu | `plugins/shipwright-compliance/scripts/hooks/check_security_scan.py` |
| neu | `plugins/shipwright-compliance/scripts/lib/thresholds.py` |
| neu | `plugins/shipwright-compliance/scripts/lib/override_logger.py` |
| neu | `plugins/shipwright-compliance/tests/test_enforcement_hooks.py` |

---

## P2: Path-Specific CLAUDE.md Rules (Domain 3.1, 3.3)

**Problem**: `shipwright-project` generiert eine monolithische CLAUDE.md. Keine `.claude/rules/*.md`.

**Cert-Regeln**:
- "Split your monolith CLAUDE.md into three layers. Path-specific rules are the golden nugget." (3.1)
- "YAML frontmatter `paths` fields, glob patterns for file types" (3.3)
- "`@import` syntax for modular references" (3.1)

### Schritte

1. **Erstelle Rule-Templates** in `shared/templates/rules/`:
   Jedes Template nutzt das Claude-Code-Format:
   ```markdown
   ---
   description: Rules for test files
   globs: "**/tests/**,**/*.test.*,**/*.spec.*"
   ---

   ## Testing Conventions
   - Follow TDD: red-green-refactor cycle
   - ...
   ```

   Templates:
   - `tests.md.template` — TDD-Konventionen, Assertion-Style, Mock-Boundaries
   - `api.md.template` — Input-Validation, Error-Response-Format, Auth-Middleware
   - `migrations.md.template` — Down-Migrations, keine destruktiven Ops ohne Confirmation
   - `components.md.template` — Accessibility, Prop-Types, Storybook
   - `config.md.template` — Keine Secrets committen, Env-Vars dokumentieren

2. **Modifiziere `shared/profiles/*.json`** — neues Feld `"rules": ["tests", "api", ...]`

3. **Modifiziere `plugins/shipwright-project/skills/decompose/SKILL.md`** Step 7:
   - Nach CLAUDE.md-Generierung: `.claude/rules/` erstellen
   - Applicable Rules basierend auf Profil auswählen und aus Templates generieren

4. **Optional: `@import` in generierter CLAUDE.md** für Modularität:
   ```markdown
   @import agent_docs/conventions.md
   ```

### Dateien
| Aktion | Datei |
|--------|-------|
| neu | `shared/templates/rules/tests.md.template` |
| neu | `shared/templates/rules/api.md.template` |
| neu | `shared/templates/rules/migrations.md.template` |
| neu | `shared/templates/rules/components.md.template` |
| neu | `shared/templates/rules/config.md.template` |
| modify | `shared/profiles/*.json` |
| modify | `plugins/shipwright-project/skills/decompose/SKILL.md` |

---

## P2: Few-Shot Examples in Agents (Domain 4.1, 4.2)

**Problem**: Agents nutzen prozedurale Instruktionen + JSON-Schemas, aber keine Input→Output-Beispielpaare.

**Cert-Regeln**:
- "2-4 targeted examples for ambiguous scenarios with reasoning" (4.2)
- "Examples showing desired format, distinguishing acceptable patterns from issues" (4.2)
- "Explicit criteria > vague instructions; specific severity with code examples" (4.1)

### Schritte

1. **Modifiziere `plugins/shipwright-build/agents/code-reviewer.md`** — 3 Examples:
   - **Example 1** (Bug): Diff mit null-pointer → JSON `{severity: "high", category: "bug"}`
   - **Example 2** (Clean): Sauberer Diff → `{"review": []}`
   - **Example 3** (False-Positive-Vermeidung): Intentional Pattern das kein Bug ist → keine Finding

   Plus: Explizite Kriterien pro Kategorie statt vager "check for bugs"-Instruktionen (4.1)

2. **Modifiziere `plugins/shipwright-plan/agents/section-writer.md`** — 2 Examples:
   - Well-scoped Section mit Prerequisites + Tests-First
   - Edge Case: Section mit externer Dependency → Fallback-Strategie

3. **Modifiziere `plugins/shipwright-plan/agents/opus-plan-reviewer.md`** — 2 Examples:
   - Security Gap (fehlende Auth) → High-Finding
   - Solider Plan → Low-Summary mit positivem Assessment

**Constraint**: Beispiele kurz halten (10-15 Zeilen Input, 10-15 Zeilen Output).

### Dateien
| Aktion | Datei |
|--------|-------|
| modify | `plugins/shipwright-build/agents/code-reviewer.md` |
| modify | `plugins/shipwright-plan/agents/section-writer.md` |
| modify | `plugins/shipwright-plan/agents/opus-plan-reviewer.md` |

---

## P3: CI/CD mit separater Review-Session (Domain 3.6, 4.6)

**Problem**: Kein Claude Code CI/CD-Integration. Code-Review im selben Pipeline-Kontext = biased.

**Cert-Regeln**:
- "Session isolation: separate review instance from generation instance" (3.6)
- "Independent review instances > self-review or extended thinking" (4.6)
- "Multi-pass: per-file local analysis + cross-file integration passes" (4.6)

### Schritte

1. **Erstelle `shared/templates/github-actions/claude-review.yml.template`**
   - GitHub Actions Workflow auf PR-Trigger
   - `claude -p "Review this PR..." --output-format json`
   - Zwei Passes: per-file Analysis + cross-file Integration (4.6)
   - Post Results als PR-Comment

2. **Erstelle `shared/scripts/tools/format_review_comment.py`** — JSON → GitHub PR-Comment

3. **Modifiziere `plugins/shipwright-project/skills/decompose/SKILL.md`** Step 7 — Review-Workflow ins Scaffolding

### Dateien
| Aktion | Datei |
|--------|-------|
| neu | `shared/templates/github-actions/claude-review.yml.template` |
| neu | `shared/scripts/tools/format_review_comment.py` |
| modify | `plugins/shipwright-project/skills/decompose/SKILL.md` |

---

## P3: Validation Loop mit spezifischem Feedback (Domain 4.4)

**Problem**: "If stuck after 3 attempts, ask user" ist Prosa ohne Enforcement. Kein extract-validate-retry mit spezifischem Feedback.

**Cert-Regeln**:
- "Retry-with-error-feedback: append specific validation errors to guide correction" (4.4)
- "Retries ineffective when info is absent from source" (4.4)
- "`detected_pattern` field for systematic false-positive analysis" (4.4)

### Schritte

1. **Erstelle `shared/scripts/lib/validation_loop.py`** — Reusable Validation-Loop:
   ```python
   def validate_with_retry(
       extract_fn: Callable,
       validate_fn: Callable,       # returns (valid, specific_errors)
       max_retries: int = 3,
       stop_condition: Callable = None  # True wenn Retry sinnlos (fehlende Daten)
   ) -> dict:
       # Returns: {"success": bool, "data": ..., "attempts": N, "final_errors": [...]}
   ```

2. **Modifiziere `plugins/shipwright-build/skills/build/SKILL.md`** Steps 4-5:
   - Explizites Validation-Checkpoint-Protokoll
   - Stop-Conditions: fehlende API aus anderer Section = Dependency, kein Retry

3. **Erstelle Reference-Doc**: `plugins/shipwright-build/skills/build/references/validation-loop.md`

4. **Tests**: `shared/scripts/tests/test_validation_loop.py`

### Dateien
| Aktion | Datei |
|--------|-------|
| neu | `shared/scripts/lib/validation_loop.py` |
| neu | `shared/scripts/tests/test_validation_loop.py` |
| neu | `plugins/shipwright-build/skills/build/references/validation-loop.md` |
| modify | `plugins/shipwright-build/skills/build/SKILL.md` |

---

## Reihenfolge & Abhängigkeiten

```
Phase 1:  P1-Errors (shared/scripts/lib/errors.py)
             ↓
Phase 2:  P1-Compliance Hooks (nutzt errors.py)
             ↓
Phase 3:  P2-Few-Shot  ←── parallel ──→  P2-Path-Rules
             ↓
Phase 4:  P3-Validation Loop (nutzt errors.py)
          P3-CI/CD Review (unabhängig)
```

## Verification

| Gap | Test |
|-----|------|
| P1 Errors | `uv run pytest shared/scripts/tests/test_errors.py -v` |
| P1 Compliance | `uv run pytest plugins/shipwright-compliance/tests/test_enforcement_hooks.py -v` + manueller Override-Test |
| P2 Rules | Testprojekt scaffolden → prüfen ob `.claude/rules/` generiert wird |
| P2 Few-Shot | Subagent-Invocation vor/nach Examples vergleichen |
| P3 CI/CD | Test-PR erstellen → GitHub Action triggert |
| P3 Validation | `uv run pytest shared/scripts/tests/test_validation_loop.py -v` |
| Integration | `uv run pytest integration-tests/ -v` |
