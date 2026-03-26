# Harness Engineering → Shipwright Integration Spec

**Datum**: 2026-03-26
**Quelle**: [LinkedIn Post](https://www.linkedin.com/posts/renaldi_claude-code-reminds-me-of-my-kids-at-times-share-7441989747381800960-SaZm) von John Renaldi + [GitHub Repo](https://github.com/jrenaldi79/harness-engineering)
**Referenzierte Quellen**: Andrej Karpathy, Boris Cherny (Claude Code Creator), OpenAI Codex Research, Factory.ai, Anthropic Best Practices

---

## 1. Research Summary

### Problem
AI-Agenten ignorieren geschriebene Regeln in CLAUDE.md trotz expliziter Instruktionen. Karpathy: "The agents do not listen to my instructions." Die Lösung: **mechanische Enforcement statt Advisory-Prose** — Git Hooks, Linter-Gates, Auto-generierte Docs.

### Harness Engineering Plugin
Zwei Skills:
- `/readiness` — Bewertet Codebases über 8 Pillars mit 5 Maturity Levels (Bare → Autonomous)
- `/setup` — Bootstrapped Projekte mit CLAUDE.md, Git Hooks, Linter, Secret Scanner

### 8 Bewertungs-Pillars
1. Style & Validation — Linter, Formatter, lint-on-commit
2. Testing — Runner, Colocation, Coverage, TDD Enforcement
3. Git Hooks & Enforcement — Pre-commit (Lint, Secrets, File-Size), Pre-push (Tests, Caching)
4. Documentation — CLAUDE.md Qualität (Commands, Architecture, Gotchas, AUTO-Sections)
5. Agent Configuration — settings.json, Allow/Deny Lists, Path-scoped Rules
6. Code Quality — 300-Zeilen File-Limit, Secret Scanning, Consistent Style
7. Dev Environment — .env.example, Build Commands, Dependency Health
8. Agentic Workflow — Planning System Integration, Plan-before-Build Validation

### Kern-Prinzipien (bestätigt durch Anthropic Best Practices)
- **"Linters over Instructions"** — Automatisierte Enforcement schlägt Prosa
- **"Map over Manual"** — CLAUDE.md kurz (~200-300 Zeilen), nicht enzyklopädisch
- **Progressive Disclosure** — Tier 1 (always loaded) → Tier 2 (on-demand) → Tier 3 (selten)
- **Drift Detection** — Warnung wenn Code sich ändert ohne CLAUDE.md Update
- **Secret Scanning** — Pre-commit Hook scannt nach Credentials
- **File Size Limits** — Große Files = schlechte Agent-Performance

---

## 2. GAP-Analyse: Shipwright vs. Harness Engineering

| Capability | Shipwright | Harness Engineering | GAP |
|------------|-----------|---------------------|-----|
| Dangerous Command Guard | ✅ `validate_command.sh` | ✅ | — |
| Destructive Migration Scan | ✅ `check_destructive_migration.sh` | ❌ | Shipwright besser |
| RTM Coverage Gate | ✅ `check_rtm_coverage.py` | ❌ | Shipwright besser |
| Security Findings Gate | ✅ `check_security_scan.py` | ❌ | Shipwright besser |
| Compliance Reports (RTM, SBOM) | ✅ | ❌ | Shipwright besser |
| Structured Errors | ✅ `errors.py` | ❌ | Shipwright besser |
| Override Logging / Audit Trail | ✅ `compliance_overrides.log` | ❌ | Shipwright besser |
| **Secret Scanning (Pre-commit)** | ❌ | ✅ | **GAP** |
| **File Size Guard** | ❌ | ✅ (300 Zeilen) | **GAP** |
| **Drift Detection (CLAUDE.md ↔ Code)** | ❌ | ✅ | **GAP** |
| **CLAUDE.md Progressive Disclosure** | Teilweise (Skills) | ✅ (Formale Tiers) | **GAP** |
| **Readiness Assessment** | ❌ | ✅ (8 Pillars, 5 Levels) | **GAP (Phase 2)** |
| **Linter Enforcement** | ❌ | ✅ | **GAP (Phase 2)** |
| Auto-Doc Generation | Via Compliance | ✅ (Commit-triggered) | Architekturentscheid |
| settings.json Scaffolding | Via Plugin-Hooks | ✅ | Architekturentscheid |
| Projekt-Bootstrapping | ✅ `/shipwright-project` | ✅ `/setup` | Shipwright besser |

---

## 3. Beurteilung

### ✅ In Shipwright integrieren

| Feature | Begründung | Aufwand |
|---------|-----------|---------|
| Secret Scanning | Security-kritisch. Geleaktes Secret im Commit = Incident. Shipwright hat Deploy-Gates aber keine Pre-commit Secret Detection. | Klein |
| File Size Guard | Agent-Performance. Anthropic bestätigt: "LLM performance degrades as context fills". 500-Zeilen Files sind Context-Killer. | Klein |
| Drift Detection | Veraltete CLAUDE.md = Agent arbeitet mit falschem Kontext. Besonders relevant für Shipwright's Multi-Session Architektur. | Mittel |
| CLAUDE.md Template Kürzen | Anthropic empfiehlt: "If your CLAUDE.md is too long, Claude ignores half of it." Template auf ~200 Zeilen optimieren, Details in agent_docs. | Klein |

### ⚠️ Bedingt empfohlen (Phase 2)

| Feature | Begründung | Einschränkung |
|---------|-----------|---------------|
| Readiness Assessment | Wertvolles Analyse-Tool für bestehende Repos. Erst sinnvoll wenn Shipwright die Enforcement-Features selbst liefert. | Pillars an Shipwright anpassen |
| Stack-spezifische Lint-Hooks | Sinnvoll aber komplex. Shipwright unterstützt viele Stacks → Pro Stack ein Template. | Über Stack-Profile konfigurierbar |

### ❌ Nicht übernehmen

| Feature | Begründung |
|---------|-----------|
| `/setup` Skill | `/shipwright-project` + `/shipwright-run` machen das bereits besser (IREB, Profiles, Compliance) |
| Auto-Doc Generation (Commit-triggered) | Shipwright's Compliance-Aggregator Architektur ist sauberer |
| settings.json Scaffolding | Plugin-Hooks sind flexibler und auditierbar |
| BMAD / Superpowers Integration | Shipwright IST bereits ein Full-Lifecycle Framework — würde duplizieren |

---

## 4. Implementierungsplan

### Phase 1: Enforcement Hooks (für generierte Projekte)

Alles was Shipwright in neu generierten Projekten enforcen kann.

#### 1.1 Secret Scanning Hook
**Dateien:**
- `shared/scripts/hooks/check_secrets.sh` — Regex-Scanner
- `plugins/shipwright-build/hooks/hooks.json` — PreToolUse Hook registrieren

**Pattern zu erkennen:**
```
AKIA[0-9A-Z]{16}          # AWS Access Key
['\"]sk-[a-zA-Z0-9]{20,}  # OpenAI/Anthropic API Key
-----BEGIN.*PRIVATE KEY    # Private Keys
password\s*=\s*['\"][^'\"]+  # Hardcoded Passwords
['\"][0-9a-f]{40}['\"]     # Generic 40-char hex tokens
```

**Verhalten:** Exit 2 (soft-block), User kann mit "Continue anyway" overriden, Override wird geloggt.

#### 1.2 File Size Guard
**Dateien:**
- `shared/scripts/hooks/check_file_size.sh` — Zeilen-Check
- `plugins/shipwright-build/hooks/hooks.json` — PostToolUse (Write|Edit) Hook
- Config: `max_file_lines: 300` (default), konfigurierbar in `shipwright_build_config.json`

**Verhalten:** Exit 2 (soft-block) wenn File > Threshold. Warnung mit aktuellem Zeilencount.

#### 1.3 Drift Detection
**Dateien:**
- `shared/scripts/hooks/check_drift.py` — Vergleicht Timestamps/Hashes
- `plugins/shipwright-build/hooks/hooks.json` — SessionStart Hook

**Logik:**
1. Bei Session-Start: Hash von CLAUDE.md und Key-Files (src/, package.json, pyproject.toml) berechnen
2. Vergleich mit gespeicherten Hashes aus letzter Session
3. Warnung wenn Key-Files sich geändert haben aber CLAUDE.md nicht

**Verhalten:** Exit 0 (Warnung, kein Block) — informiert den Agenten, blockt nicht.

#### 1.4 CLAUDE.md Template Refactoring
**Datei:** `shared/templates/claude-md-template.md`

**Änderungen:**
- Auf ~200 Zeilen kürzen
- Nur Tier 1 Infos: Stack, Build/Test/Deploy Commands, kritische Gotchas
- Tier 2 Verweis auf agent_docs/ für Architecture, Conventions, Decision Log
- `@`-Imports für Detailreferenzen statt inline

### Phase 2: Bestehende Repos (nach stabiler Phase 1)

#### 2.1 Readiness Assessment (`/shipwright-readiness`)
**Dateien:**
- `plugins/shipwright-project/skills/readiness/SKILL.md`
- `plugins/shipwright-project/scripts/tools/assess_readiness.py`

**Angepasste Pillars für Shipwright:**
1. Style & Validation
2. Testing
3. Git Hooks & Enforcement
4. Documentation (CLAUDE.md Qualität)
5. Agent Configuration
6. Code Quality
7. Dev Environment
8. **Compliance Readiness** (statt "Agentic Workflow") — IREB-Traceability, SBOM, Audit Trail

**Maturity Levels:**
| Level | Name | Kriterien |
|-------|------|-----------|
| 1 | Bare | Git + Manifest |
| 2 | Basic | Linter + Formatter + Test Runner |
| 3 | Enforced | Hooks aktiv, CLAUDE.md vorhanden, Agent Config |
| 4 | Automated | Drift Detection, Secret Scanning, Coverage Gates |
| 5 | Shipwright-Ready | Full Compliance, TDD enforced, RTM >80%, SBOM complete |

#### 2.2 Stack-spezifische Lint-Hooks
- Über Stack-Profile (`shared/profiles/`) konfigurierbar
- Python: ruff/flake8, Node: eslint, Go: golangci-lint
- Template-basiert, nicht hard-coded

---

## 5. Verifikation

### Phase 1 Tests
- [ ] Unit Test: Secret-Pattern erkennt AWS Key, OpenAI Key, Private Key
- [ ] Unit Test: Secret-Pattern ignoriert Test-Fixtures und Beispiel-Strings
- [ ] Unit Test: File Size Guard warnt bei >300 Zeilen
- [ ] Unit Test: Drift Detection erkennt geänderte Key-Files
- [ ] Integration Test: Commit mit Secret → soft-block
- [ ] Integration Test: Override → Eintrag in compliance_overrides.log
- [ ] CLAUDE.md Template: Diff reviewen, Zeilencount < 200

### Phase 2 Tests
- [ ] Readiness Assessment gegen Shipwright-Repo selbst ausführen
- [ ] Readiness Assessment gegen ein "nacktes" Repo → Level 1
- [ ] Readiness Assessment gegen ein konfiguriertes Repo → Level 3+

---

## 6. Fazit

**Harness Engineering liefert 3 konkrete Ideen die Shipwright sofort verbessern:**
1. **Secret Scanning** — Schliesst eine echte Security-Lücke
2. **File Size Guard** — Schützt Agent-Performance (von Anthropic Best Practices bestätigt)
3. **Drift Detection** — Verhindert veralteten Agent-Kontext

**Die Kern-Philosophie "Linters over Instructions" ist korrekt** und wird von Anthropics eigenen Best Practices bestätigt: "Unlike CLAUDE.md instructions which are advisory, hooks are deterministic and guarantee the action happens."

Shipwright ist in vielen Bereichen bereits weiter (Compliance, RTM, SBOM, Structured Errors, Override Logging). Die Integration fokussiert auf die echten Lücken, nicht auf Duplikation.
