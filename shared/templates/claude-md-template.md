# {PROJECT_NAME}

## WHAT
- **Stack**: {TECH_STACK}
- **Purpose**: {PROJECT_PURPOSE}

## HOW
- **Build**: {BUILD_COMMAND}
- **Test**: {TEST_COMMAND}
- **Lint**: {LINT_COMMAND}
- **Deploy DEV**: git push (auto)
- **Deploy PROD**: /shipwright-deploy --env prod

## Ongoing Changes
**Use `/shipwright-iterate` for code changes — Do NOT edit code directly.**
The skill keeps specs, tests, ADRs, and the CHANGELOG in sync.

What `/shipwright-iterate` automates:
- ADR entry in `.shipwright/agent_docs/decision_log.md`
- CHANGELOG fragment under `CHANGELOG-unreleased.d/<category>/`
- Conventional Commits on an `iterate/<slug>` branch, merged to main on green tests
- FR / acceptance-criteria sync in `.shipwright/planning/`
- Compliance + dashboard refresh

Do NOT invoke `/shipwright-project`, `/shipwright-plan`, or `/shipwright-build` directly — those are pre-onboarding phases.

## Structure
{FOLDER_STRUCTURE}

## Key Files
{KEY_FILES}

## Gotchas
{GOTCHAS}

## Editing this file (keep it lean)

CLAUDE.md is **orientation + a terse invariant index** — it is loaded into
every session, so every line here costs context on every future change.

- **New invariant / DO-NOT rule:** add **one line + a pointer** to the ADR or
  conventions entry that carries the rationale (e.g. `- Never bypass X — see
  ADR-012`). The full reasoning lives in
  `.shipwright/agent_docs/decision_log.md` or `conventions.md`, **not here**.
- **No inline rationale:** if a rule needs more than ~2 lines to state, the
  extra lines belong in the ADR it cites. Keep lines short — a long paragraph
  on one line is still rationale.
- **Prefer updating an existing line** over adding a new one.
- **Growth is gated:** iterate finalization flags a change that net-grows this
  file by more than 30 lines (deliberate exception:
  `SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1`).

## Context

**Read first** (stable, always relevant):
- @.shipwright/agent_docs/architecture.md — system overview, layers, security model
- @.shipwright/agent_docs/conventions.md — code patterns, naming, git workflow

**Read on demand** (volatile, changes per session):
- @.shipwright/agent_docs/decision_log.md — when making or reviewing decisions
- @.shipwright/agent_docs/build_dashboard.md — when checking progress or planning next steps
- @.shipwright/agent_docs/session_handoff.md — when resuming after a pause or /clear

**Other references:**
- @.shipwright/planning/ — specs and section files

**Pipeline state** (machine-generated, do not edit manually):
- @shipwright_run_config.json — pipeline state (scope, profile, autonomy, current/completed steps)
- @shipwright_project_config.json — requirements splits, profile, project metadata
- @shipwright_plan_config.json — section references for build
- @shipwright_build_config.json — build progress per section
- @shipwright_security_config.json — security scan results
- @shipwright_compliance_config.json — compliance audit metadata

## Path-migration awareness

If you see `.shipwright/stale-folders.md` in this project, the Shipwright
drift detector flagged a legacy artefact directory at the project root that
should live under `.shipwright/` (e.g. legacy `planning/`, `designs/`,
`agent_docs/`, `compliance/`). The file contains the exact `git mv`
remediation commands — follow them, do not skip or delete it. The file
auto-clears when the next SessionStart runs cleanly. Per-artefact migration
guides live in the Shipwright repo under `docs/migrations/`.

## GitHub Actions pinning — DO NOT "fix" this

The workflows in `.github/workflows/` pin third-party actions to a full commit
SHA, and leave **GitHub-owned** actions (`actions/*`, `github/*`) on mutable
major tags (`@v4`). That asymmetry is deliberate. Do not "harden" it by pinning
everything.

**Why.** SHA-pinning trades a supply-chain risk for a maintenance one: a pinned
SHA never receives security patches, so it needs an automated updater to avoid
rotting. This project deliberately runs **no hosted dependency updater** — for
**portability**, not cost. That reasoning holds even where such a service is
free, so "but it's free" does not reopen it. GitHub-owned actions are the one
publisher whose mutable tags are trustworthy enough to carry that trade; every
other publisher is not, which is why third-party actions **are** SHA-pinned.

**What this means in practice:**

- Adding a third-party action → pin it to a full 40-character commit SHA, with
  the human-readable version in a trailing comment (`@71345be…  # v4`).
- Adding a GitHub-owned action → use the major tag (`@v4`). Pinning it to a SHA
  is a regression, not an improvement.
- Never add a dependency-updater config (`dependabot.yml` or equivalent).

If you believe this posture is wrong, raise it — do not silently invert it in a
PR. A well-meant "let's pin everything for supply-chain safety" is exactly how
this decision has been reversed before, in a repo that had the state right and
had never written down the reason.

## Asking the user questions (plain language)

When you ask the user a question — a clarification, a choice between options,
or a confirmation — phrase it so a **non-senior developer or a normal user**
can understand, from a functional standpoint, what is actually being decided.
The person answering may not know the internals; do not make them decode
jargon to reply.

- **Lead with the functional meaning:** say what the choice changes about how
  the app behaves or what the user gets — not the implementation detail.
- **Avoid unexplained jargon.** If a technical term is unavoidable, add a short
  plain-language gloss in parentheses (e.g. "idempotent — safe to run twice
  without doubling the effect").
- **Make options concrete and comparable.** Give each option in plain words
  with its real-world trade-off ("Option A is simpler but slower; Option B is
  faster but adds a setup step"), not a raw technical menu.
- **Rule of thumb:** a product owner should be able to answer without asking
  "what does that mean?". If they couldn't, rewrite it.

This governs *phrasing only* — the rigor of the work is unchanged.
