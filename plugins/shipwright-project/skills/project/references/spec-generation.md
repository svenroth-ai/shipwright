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

**The sentence is plain business language** — read `shared/fr-authoring.md`
before writing requirements. It must name a *capability* the product offers, in
words a product owner understands, and carry no implementation detail (no file
paths, ADR numbers, HTTP verbs, or code symbols).

- ❌ The system SHALL expose a POST `/api/leave_request` handler writing to
  `leave_requests` with a `proper-lockfile` guard.
- ✅ The system SHALL let an employee request time off for a chosen date range,
  and SHALL refuse a request that overlaps one they already have.

Both say the same thing. The second one can be signed off by the person who
asked for the feature. Never drop a guarantee (here: the overlap rule) to make
a sentence plainer — plain wording, full meaning.

### ID Schema

    {Type}-{Split-Number}.{Sequential-Number}

Examples for Split 01:
- `FR-01.01` — First functional requirement
- `QR-01.01` — First quality requirement
- `C-01.01` — First constraint

### Acceptance Criteria Rules

- Every FR with Priority "Must" MUST have acceptance criteria
- QRs with measurable targets (e.g., "within 500ms", "10 concurrent users") SHOULD also have acceptance criteria — these drive performance/load tests in shipwright-build
- Criteria must be testable (shipwright-build uses them for TDD)
- Use checkbox format: `- [ ] {criterion}`
- 2-5 criteria per requirement (not more)

### Removed Requirements

When an iterate REMOVES a user-visible capability, its FR is **never silently
deleted** — `/shipwright-iterate` moves the row into a `### Removed
Requirements` subsection placed last under `## 2. Functional Requirements`.
This preserves traceability: the FR id keeps a home, and the RTM stops
reporting the retired capability as an uncovered/failing requirement.

Rules:
- Each row keeps the original FR id, requirement text, and priority, and adds
  the run_id that removed it plus a `status` cell whose value is the literal
  string `status: deprecated`.
- The literal `status: deprecated` is **mandatory**: the Phase-Quality
  Stop-hook check S4 (`check_s4_fr_preservation`) scans for it within a few
  lines of any FR id that disappeared from the live table. Omitting it raises
  a spurious "removed FR without status=deprecated" warning.
- The FR parsers (`shared/scripts/lib/drift_parsers.py:parse_fr_table` and
  the compliance `data_collector.collect_requirements`) skip this whole
  subsection — removed FRs do not count as live requirements.
- Omit the subsection entirely while no FR has been removed.

### Writing Guidelines

- **Self-contained:** Each spec should stand alone for /shipwright-plan
- **Reference don't duplicate:** Point to requirements file for background context
- **Capture decisions:** Include interview answers that shaped this split
- **Note dependencies:** Be explicit about what this split needs/provides
- **Be specific:** "The system SHALL authenticate users via email/password"
  not "The system SHALL handle authentication"
- **Be testable:** Every SHALL/SHOULD must be verifiable
- **Be readable by a non-engineer:** a product owner who has never seen the
  code must be able to read the requirement and say what the product does —
  see `shared/fr-authoring.md`. Specific and plain are not in tension: the *what*
  gets sharper, the *how* moves to `architecture.md`.
- **One requirement, one capability:** a route, a bugfix, a polish pass, or a
  "Phase 2" is not its own requirement — it is acceptance criteria on the
  capability it belongs to (`fr-authoring.md` §3).

## Template Structure

```markdown
# {Split-Name}

> Split {NN} of {total} | Source: {requirements file or "interview"}

## 1. Purpose & Scope

{1-3 sentences: What is the goal of this split? What gets built?}

**In Scope:**
- {What belongs here}

**Out of Scope:**
- {What explicitly does NOT belong here (important for split boundaries)}

## 2. Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-{NN}.01 | {Area} | {Short capability name} | Must | The system SHALL ... | interview | unit, e2e |
| FR-{NN}.02 | {Area} | {Short capability name} | Must | The system SHALL ... | interview | unit, integration |
| FR-{NN}.03 | {Area} | {Short capability name} | Should | The system SHOULD ... | assumed | unit |
| FR-{NN}.04 | {Area} | {Short capability name} | May | The system MAY ... | assumed | unit |

This header is the **one converged shape**, emitted byte-identically by
`/shipwright-project` and `/shipwright-adopt`. Do not add, drop, rename or
reorder a column: the reader resolves columns by name, so a renamed column is
not a cosmetic choice — it is a column that no longer exists.

**`Area`** is the requirement's capability group, **rendered from the group digit
of its ID** — `FR-03.xx` belongs to split `03-…`, and the Area cell is that
split's name. It is a display label, never a second grouping axis: if you find
yourself choosing an Area that disagrees with the ID's group, the ID is
authoritative and the requirement is filed in the wrong split.

Add `### {Area}` sub-sections **only when one split genuinely holds more than one
area**. A greenfield split already carries its grouping in the ID, so in the
normal case the sections would restate what the IDs already say.

**`Name`** is a short capability name (2–5 words, a noun phrase — "Password
reset", not "The system SHALL reset passwords"). **`Description`** carries the
full Rupp/IREB sentence. They are separate columns because the name fence in
`shared/fr-authoring.md` §5 applies to the name only.

**`Basis`** records **how we know this requirement**, from a closed vocabulary:

| Value | Meaning |
|---|---|
| `interview` | a human told us |
| `code` | read from source |
| `observed` | seen in the running application |
| `tests` | derived from existing tests |
| `assumed` | **nobody confirmed this — needs checking** |
| `other` | special case; add the reason as `other: <reason>` |

`assumed` is the load-bearing value, and the one to reach for when you are
tempted to guess. Its whole job is to stop a guess from later reading as
established fact — if an interviewee could not recall *why* a limit is 90 and you
wrote down a plausible number, that requirement's basis is `assumed`, not
`interview`. A value outside this vocabulary is a hard error (it is a typo, not a
special case); `other` never blocks. Known values take no qualifier: write
`code`, not `code (auth.ts)` — the file path is exactly what this column replaced.

**`Layers`** declares the test layers this requirement MUST be covered at, from
`{unit, integration, e2e}` — the set compliance checks per-layer coverage against
(a UI requirement that only ever gets a unit test is then a visible gap, not tribal
knowledge). Emit it with these defaults, then let the author override:

- **every FR ⇒ `unit`.**
- a **UI / user-flow** requirement (a page, screen, click, form, navigation) **⇒ add `e2e`.**
- a **CRUD / persistence / DB** requirement (store, query, migrate a row) **⇒ add `integration`.**

Comma-separate multiple layers. The column is **backward-compatible**: an FR authored
without it still parses — a UI-worded FR defaults to `e2e`, everything else to `unit` —
but a requirement created after this field ships SHOULD declare it explicitly, so its
provenance reads as author-chosen rather than legacy-inferred.

**Write the layers bare when the requirement is one you are about to build.** A
bare cell is an author's declaration, and compliance treats it as binding: a
missing layer becomes a hard coverage failure rather than a warning. That is the
intended contract for a requirement a human wrote — you are stating what this
must be tested at, and in the normal flow the tests follow immediately, because
`/shipwright-project` feeds `/shipwright-build`, which is TDD.

**When you are auto-deriving a cell from the defaults above rather than deciding
it, mark it `(inferred)`** — see the next paragraph. The defaults are a starting
guess about a requirement nobody has planned tests for yet, and a guess written
bare is a binding claim you cannot back.

You will also see cells ending in `(inferred)`, e.g. `unit, e2e (inferred)`.
**That marker means "nobody has verified these layers", and it keeps the
requirement advisory** — reported, never blocking. It is *usually* written by a
tool (`/shipwright-adopt` for reverse-engineered requirements, and migrations),
because a tool is usually what produces an unverified guess — but the marker
describes the cell's **standing**, not who typed it.

So: **declare bare when you know, mark `(inferred)` when you do not.** Writing
`(inferred)` by hand for layers you have not established is honest and is the
form that does not hard-block; writing a bare cell you have not established
asserts a binding requirement you cannot back. See `shared/fr-authoring.md` §4a,
which is the binding rulebook for this column.

**Do not reach for `Basis: assumed` to express "I don't know the layers".** They
are different columns answering different questions: `Basis` records how we know
the **requirement**; `Layers` records what it must be **tested** at. A
requirement can be `Basis: interview` (a human told us, plainly) and still have
entirely unverified layers.

Only the literal word `inferred` in parentheses counts — `(auto)` or `(guess)` do
not, and a cell marked that way is read as a binding declaration. Mind the
space: `unit (inferred)` parses, `unit(inferred)` silently yields no layers.

### Acceptance Criteria

**FR-{NN}.01: {Short name}**
- [ ] {Testable criterion 1}
- [ ] {Testable criterion 2}

**FR-{NN}.02: {Short name}**
- [ ] {Testable criterion 1}
- [ ] ...

### Removed Requirements

{Only present once a REMOVE-classified iterate has retired an FR.
Omit this subsection entirely while empty.}

| ID | Requirement | Priority | Removed by | status |
|----|-------------|----------|------------|--------|
| FR-{NN}.{YY} | {original requirement text} | {Must/Should/May} | {run_id} | status: deprecated |

## 3. Quality Requirements

| ID | Requirement | Category |
|----|-------------|----------|
| QR-{NN}.01 | The system SHALL respond to ... within {X}ms | Performance |
| QR-{NN}.02 | The system SHALL handle {X} concurrent users | Scalability |
| QR-{NN}.03 | The system SHALL ... | Security |

**Acceptance Criteria** (for QRs with measurable targets):

**QR-{NN}.01: Response Time**
- [ ] API responds within {X}ms at p95 under normal load
- [ ] No endpoint exceeds {Y}ms at p99

## 4. Constraints

| ID | Constraint | Type |
|----|-----------|------|
| C-{NN}.01 | Must use {technology} | Technical |
| C-{NN}.02 | Must comply with {regulation} | Regulatory |
| C-{NN}.03 | Must integrate with {system} | Integration |

## 5. Dependencies

**Depends on:**
- Split {XX}: {what this split needs — e.g., "database schema from 01-backend"}

**Provides to:**
- Split {XX}: {what this split delivers — e.g., "API endpoints for 02-frontend"}

**Dependency type:** {models | APIs | schemas | patterns}

## 6. Key Decisions

{Decisions from the interview that shaped this split.
Only decisions that shipwright-plan needs to plan correctly.}

- **Decision:** {What was decided}
  **Rationale:** {Why}

## 7. UI Requirements (optional)

{Include only if this split has user-facing screens.
Used by shipwright-design to generate mockups.}

| Screen | Description | Key Elements |
|--------|-------------|-------------|
| {Screen name} | {What the user sees} | {Key UI elements: forms, tables, cards, etc.} |

**Layout preference:** {Sidebar | Top-nav | Centered | Full-width}
**Design references:** {Link to existing mockups in .shipwright/designs/uploads/ if any}

## 8. References

- Requirements: `{path to requirements file}`
- Interview: `{path to interview transcript}`
- Related splits: {links to other split specs if relevant}
- Designs: `{path to design-manifest.md if available}`
```

## Example: Filled spec.md

For a hypothetical split "01-auth" of a SaaS Time Tracking project:

```markdown
# Authentication & Authorization

> Split 01 of 03 | Source: .shipwright/planning/requirements.md

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

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.01 | Authentication | User registration | Must | The system SHALL allow users to register with email and password | interview | unit, integration, e2e |
| FR-01.02 | Authentication | User login | Must | The system SHALL authenticate users via email/password and return a session token | interview | unit, integration, e2e |
| FR-01.03 | Authentication | Password reset | Must | The system SHALL support password reset via email link | interview | unit, integration, e2e |
| FR-01.04 | Authentication | Role-based access | Must | The system SHALL enforce role-based access control (admin, member) | interview | unit, e2e |
| FR-01.05 | Authentication | Login rate limiting | Should | The system SHOULD rate-limit login attempts to 5 per minute per IP | assumed | unit |
| FR-01.06 | Authentication | Remember me | May | The system MAY support "remember me" for extended sessions | assumed | unit, e2e (inferred) |

Both `Layers` forms appear above on purpose — copying either should be a choice,
not an accident:

- **FR-01.01–.05 are bare** — binding declarations. This is the recommended form:
  you are building these, so the tests land with them. Until they do, the missing
  layer hard-aborts finalization.
- **FR-01.06 carries `(inferred)`** — advisory, for a `May` capability whose
  layers nobody has verified yet. Reported, never blocking.

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

### Removed Requirements

| ID | Requirement | Priority | Removed by | status |
|----|-------------|----------|------------|--------|
| FR-01.07 | The system SHALL support social login via Google OAuth | Should | iterate-20260120-drop-oauth | status: deprecated |

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

- Requirements: `.shipwright/planning/requirements.md`
- Interview: `.shipwright/planning/shipwright_project_interview.md`
- Related splits: `02-data-model/spec.md`, `03-frontend/spec.md`
```
