# IREB-konformes spec.md Template fuer shipwright-project

> **Ziel**: Das `spec-generation.md` Reference im `shipwright-project` Skill mit einem
> IREB-konformen Template ausstatten, das definiert wie `spec.md` Dateien pro Split
> strukturiert werden.
> **Kontext**: Aktuell hat `spec-generation.md` nur 4 vage Guidelines ("self-contained",
> "reference don't duplicate", "capture decisions", "note dependencies") -- aber kein
> konkretes Template. Das fuehrt zu inkonsistenten Specs je nach LLM-Laune.
> **Ansatz**: IREB CPRE Foundation Level + RE@Agile -- pragmatisch fuer AI-generierte Specs.

---

## 1. IREB-Grundlagen (relevanter Ausschnitt)

### Drei Anforderungstypen (IREB-Kern)

| Typ | Kuerzel | Beschreibung | Beispiel |
|-----|---------|-------------|----------|
| **Funktionale Anforderung** | FR | Was das System tut | "User kann sich mit Email/Passwort einloggen" |
| **Qualitaetsanforderung** | QR | Wie gut es das tut | "Login muss unter 2s antworten" |
| **Constraint** | C | Rahmenbedingung | "Muss Supabase Auth verwenden" |

### Rupp's Requirement Template (IREB-Standard)

Die IREB-empfohlene Satzschablone fuer praezise Anforderungen:

```
[Bedingung:] The system {SHALL | SHOULD | MAY} {action} {object} [qualifier].
```

- **SHALL** = Must-have (nicht verhandelbar)
- **SHOULD** = Should-have (wichtig, aber verhandelbar)
- **MAY** = Nice-to-have (optional)

### Anforderungs-Attribute (IREB, pragmatisch reduziert)

IREB empfiehlt umfangreiche Attribute pro Requirement (ID, Priority, Source, Status,
Verification Method, Traceability, ...). Fuer AI-generierte Split-Specs reduzieren wir
auf das Wesentliche:

| Attribut | Warum relevant fuer shipwright |
|----------|-------------------------------|
| **ID** | Traceability von Spec -> Plan -> Section -> Code |
| **Prioritaet** | shipwright-plan braucht Reihenfolge |
| **Typ** | FR/QR/C Trennung verhindert, dass QRs "vergessen" werden |
| **Akzeptanzkriterien** | shipwright-build braucht testbare Kriterien fuer TDD |

---

## 2. Ist-Zustand: Aktuelles spec-generation.md

```
plugins/shipwright-project/skills/shipwright-project/references/spec-generation.md
```

**Inhalt (komplett):**
- Context to Read (welche Dateien vorher lesen)
- 4 Writing Guidelines: self-contained, reference don't duplicate, capture decisions, note dependencies
- Kein Template
- Kein definiertes Output-Format

**Problem:** Claude generiert `spec.md` Dateien in freier Form. Die Qualitaet haengt
vom Zufall ab. Downstream-Skills (shipwright-plan, shipwright-build) muessen raten,
wo sie welche Information finden.

---

## 3. Vorschlag: IREB-konformes spec.md Template

### Template-Struktur

```markdown
# {Split-Name}

> Split {NN} of {total} | Source: {requirements file or "interview"}

## 1. Purpose & Scope

{1-3 Saetze: Was ist das Ziel dieses Splits? Was wird gebaut?}

**In Scope:**
- {Was gehoert dazu}

**Out of Scope:**
- {Was gehoert explizit NICHT dazu (wichtig fuer Abgrenzung zu anderen Splits)}

## 2. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-{NN}.01 | The system SHALL ... | Must |
| FR-{NN}.02 | The system SHALL ... | Must |
| FR-{NN}.03 | The system SHOULD ... | Should |
| FR-{NN}.04 | The system MAY ... | May |

### Acceptance Criteria

**FR-{NN}.01: {Kurzname}**
- [ ] {Testbares Kriterium 1}
- [ ] {Testbares Kriterium 2}

**FR-{NN}.02: {Kurzname}**
- [ ] {Testbares Kriterium 1}
- [ ] ...

## 3. Quality Requirements

| ID | Requirement | Category |
|----|-------------|----------|
| QR-{NN}.01 | The system SHALL respond to ... within {X}ms | Performance |
| QR-{NN}.02 | The system SHALL handle {X} concurrent users | Scalability |
| QR-{NN}.03 | The system SHALL ... | Security |

## 4. Constraints

| ID | Constraint | Type |
|----|-----------|------|
| C-{NN}.01 | Must use {technology} | Technical |
| C-{NN}.02 | Must comply with {regulation} | Regulatory |
| C-{NN}.03 | Must integrate with {system} | Integration |

## 5. Dependencies

**Depends on:**
- Split {XX}: {what this split needs -- e.g., "database schema from 01-backend"}

**Provides to:**
- Split {XX}: {what this split delivers -- e.g., "API endpoints for 02-frontend"}

**Dependency type:** {models | APIs | schemas | patterns}

## 6. Key Decisions

{Entscheidungen aus dem Interview, die diesen Split geformt haben.
Nur Entscheidungen, die shipwright-plan braucht, um richtig zu planen.}

- **Decision:** {Was wurde entschieden}
  **Rationale:** {Warum}

## 7. References

- Requirements: `{path to requirements file}`
- Interview: `{path to interview transcript}`
- Related splits: {links to other split specs if relevant}
```

---

## 4. Anpassungen an spec-generation.md

### Was sich aendert

Das bestehende `spec-generation.md` wird erweitert um:

1. **Das Template oben** als verbindliche Struktur
2. **Klare Regeln** fuer die Befuellung jeder Sektion
3. **ID-Schema** fuer Requirements: `{FR|QR|C}-{Split-Nr}.{laufende Nr}`

### Vorgeschlagener neuer Inhalt fuer spec-generation.md

```markdown
# Spec File Generation

## Context to Read

Before writing spec files:
- `{initial_file}` - The original requirements
- `{planning_dir}/shipwright_project_interview.md` - Interview transcript
- `{planning_dir}/project-manifest.md` - Split structure and dependencies

**From setup-session.py output:**
- `split_directories` - Full paths to all split directories
- `splits_needing_specs` - Names of splits that still need spec.md written

## Template

Each `spec.md` MUST follow this structure (IREB-aligned):

### Required Sections

1. **Purpose & Scope** — What this split builds, explicit in/out of scope
2. **Functional Requirements** — Table with ID, requirement text, priority
3. **Quality Requirements** — Performance, security, scalability targets (if applicable)
4. **Constraints** — Technical, regulatory, integration constraints (if applicable)
5. **Dependencies** — What this split needs from / provides to other splits
6. **Key Decisions** — Interview decisions that shaped this split
7. **References** — Paths to source files

### Optional Sections (include when relevant)

- Quality Requirements: Skip for splits with no measurable quality targets
- Constraints: Skip if no specific constraints beyond the stack profile

### Requirement Format (Rupp's Template)

Write requirements using IREB's sentence template:

    The system {SHALL | SHOULD | MAY} {action} {object} [qualifier].

- **SHALL** = Must-have (maps to MoSCoW "Must")
- **SHOULD** = Should-have (maps to MoSCoW "Should")
- **MAY** = Nice-to-have (maps to MoSCoW "Could")

### ID Schema

    {Type}-{Split-Number}.{Sequential-Number}

Examples for Split 01:
- `FR-01.01` — First functional requirement
- `QR-01.01` — First quality requirement
- `C-01.01` — First constraint

### Acceptance Criteria Rules

- Every FR with Priority "Must" MUST have acceptance criteria
- Criteria must be testable (shipwright-build uses them for TDD)
- Use checkbox format: `- [ ] {criterion}`
- 2-5 criteria per requirement (not more)

### Writing Guidelines

- **Self-contained:** Each spec should stand alone for /shipwright-plan
- **Reference don't duplicate:** Point to requirements file for background context
- **Capture decisions:** Include interview answers that shaped this split
- **Note dependencies:** Be explicit about what this split needs/provides
- **Be specific:** "The system SHALL authenticate users via email/password"
  not "The system SHALL handle authentication"
- **Be testable:** Every SHALL/SHOULD must be verifiable
```

---

## 5. Beispiel: Ausgefuelltes spec.md

Fuer einen hypothetischen Split "01-auth" eines SaaS Time Tracking Projekts:

```markdown
# Authentication & Authorization

> Split 01 of 03 | Source: planning/requirements.md

## 1. Purpose & Scope

Build the authentication and authorization system for the time tracking
application. Users can sign up, log in, and access features based on their role.

**In Scope:**
- User registration (email/password)
- Login / logout
- Password reset flow
- Role-based access (admin, member)
- Session management

**Out of Scope:**
- OAuth/social login (planned for future iteration)
- Multi-tenancy (handled in Split 02)
- UI components (handled in Split 03)

## 2. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.01 | The system SHALL allow users to register with email and password | Must |
| FR-01.02 | The system SHALL authenticate users via email/password and return a session token | Must |
| FR-01.03 | The system SHALL support password reset via email link | Must |
| FR-01.04 | The system SHALL enforce role-based access control (admin, member) | Must |
| FR-01.05 | The system SHOULD rate-limit login attempts to 5 per minute per IP | Should |
| FR-01.06 | The system MAY support "remember me" for extended sessions | May |

### Acceptance Criteria

**FR-01.01: User Registration**
- [ ] User can register with valid email and password (min 8 chars)
- [ ] Duplicate email returns clear error message
- [ ] Registration creates user record in Supabase Auth
- [ ] Confirmation email is sent after registration

**FR-01.02: User Login**
- [ ] Valid credentials return session token
- [ ] Invalid credentials return 401 with generic error
- [ ] Session token expires after 24 hours

**FR-01.03: Password Reset**
- [ ] User receives reset link via email
- [ ] Reset link expires after 1 hour
- [ ] New password must meet minimum requirements

**FR-01.04: Role-Based Access**
- [ ] Admin can access all routes
- [ ] Member cannot access /admin/* routes
- [ ] Unauthenticated users are redirected to /login

## 3. Quality Requirements

| ID | Requirement | Category |
|----|-------------|----------|
| QR-01.01 | The system SHALL complete login requests within 500ms (p95) | Performance |
| QR-01.02 | The system SHALL store passwords using bcrypt with cost factor >= 10 | Security |

## 4. Constraints

| ID | Constraint | Type |
|----|-----------|------|
| C-01.01 | Must use Supabase Auth (GoTrue) as authentication backend | Technical |
| C-01.02 | Must use Row Level Security (RLS) for authorization | Technical |

## 5. Dependencies

**Depends on:**
- None (this is the foundation split)

**Provides to:**
- Split 02 (Data Model): Auth user IDs for foreign keys
- Split 03 (Frontend): Auth hooks and session context

**Dependency type:** APIs, schemas

## 6. Key Decisions

- **Decision:** Use Supabase Auth instead of custom auth
  **Rationale:** Reduces implementation effort, built-in email verification, PKCE flow

- **Decision:** Roles stored in user metadata, not separate table
  **Rationale:** Simpler RLS policies, sufficient for 2-role model

## 7. References

- Requirements: `planning/requirements.md`
- Interview: `planning/shipwright_project_interview.md`
- Related splits: `02-data-model/spec.md`, `03-frontend/spec.md`
```

---

## 6. Auswirkungen auf andere Skills

### shipwright-plan

Profitiert am meisten: Kann jetzt strukturiert auf FR-Tabelle zugreifen statt
Prosa zu parsen. Die IDs ermoeglichen Traceability von Requirement -> Plan Section -> Code.

### shipwright-build

Akzeptanzkriterien werden direkt zu Test-Cases. Der TDD-Loop hat klare,
testbare Kriterien statt vager Beschreibungen.

### shipwright-test

Kann Akzeptanzkriterien als Checkliste fuer E2E-Tests verwenden.
QR-Anforderungen (Performance, Security) werden zu messbaren Test-Targets.

---

## 7. Empfehlung

**Minimaler Aufwand, maximaler Impact:**

1. `spec-generation.md` mit dem Template aus Abschnitt 4 ersetzen
2. Die 4 bestehenden Guidelines bleiben als Teil des neuen Dokuments erhalten
3. Ein Beispiel (Abschnitt 5) als Referenz mit aufnehmen

Das Template ist bewusst **nicht ueberformalisiert**:
- Keine Status-Felder (Spec ist immer "Draft" wenn generiert)
- Keine Source-Felder pro Requirement (Source ist immer Interview + Requirements File)
- Keine Verification Method (ist immer "Test" bei shipwright)
- QR und C Sektionen sind optional (nicht jeder Split hat messbare Quality Targets)

Die IREB-Kernprinzipien sind trotzdem erfuellt:
- Klare Typisierung (FR/QR/C)
- Eindeutige IDs fuer Traceability
- Testbare Akzeptanzkriterien
- Rupp's Satzschablone fuer konsistente Formulierung
- Explizite Abgrenzung (In/Out of Scope)
