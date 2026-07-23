# Interview Protocol

> **Method is shared — this doc adds only the project-specific topics.** The
> elicitation method itself (relentless grilling to a shared understanding, one
> question at a time each with a recommended answer, looking facts up instead of
> asking, challenging terms against the glossary, edge-case stress-tests,
> capturing `CONTEXT.md` + ADRs, and the **coverage checklist that is not
> finished until every context dimension is answered or recorded `Basis:
> assumed`**) is binding and lives in `shared/requirement-elicitation.md`. Follow
> it. The topics below are `/shipwright-project`'s greenfield additions on top of
> that method — they extend the shared checklist, they do not replace it.

## Pre-Phase: Surface Inferred Assumptions First

**Before asking the first clarifying question, list your inferred assumptions
explicitly and ask the user to correct them.** Stating assumptions out loud is
cheaper than discovering one wrong three questions later, and it prevents
silent assumptions from hardening into specs. This runs ONCE, at the very top
of the interview — before the Core Topics, before any AskUserQuestion.

Surface at least these dimensions, each with your current best guess:

- **Surface:** web-app vs CLI vs library vs service/API vs mobile?
- **Stack:** language, framework, runtime (e.g. "Next.js + TypeScript",
  "Python CLI")?
- **Persistence:** none / file / SQLite / Postgres / external store?
- **Auth model:** none / single-user / session-cookies / OAuth / multi-tenant?
- **Scope & users:** single-user vs multi-user; internal tool vs public product?

Format it as a short, correctable list, for example:

> I'm inferring: **single-user web-app**, **Next.js + Postgres**,
> **session-cookie auth**, deployed as one service. Correct anything that's
> wrong before we go deeper.

Then proceed to the adaptive questions below. Re-surface a revised assumption
list only when an answer invalidates a foundational one. For Extension scope,
draw assumptions from the existing `CLAUDE.md` / `architecture.md` first.

## Context to Read

Before starting the interview:
- `{initial_file}` - The requirements file passed by user
- If Extension scope: existing `CLAUDE.md` and `.shipwright/agent_docs/architecture.md`

## Philosophy

The interview surfaces the user's mental model. Claude has freedom to ask questions adaptively - there's no fixed number of rounds. The goal is reconciling context from the user's brain with Claude's intelligence.

**One AskUserQuestion per question.** The host (Shipwright Command Center and any compatible CLI front-end) blocks on each AskUserQuestion call and waits for a `tool_result` reply before Claude can continue. Never batch multiple questions into a single markdown list — that bypasses the interactive interview and forces the user to parse and answer a wall of text.

## Scope-Aware Depth

### Full Application (deep interview)
- Cover all core topics below
- 5-15 questions, adaptive
- Build full understanding of the project

### Extension (light interview)
- Read existing CLAUDE.md + .shipwright/agent_docs first
- 1-3 focused questions
- Focus: what's changing, what's affected, dependencies on existing code
- Don't re-ask what's documented

## Core Topics to Cover

### 1. Natural Boundaries

Try to discover how the user naturally thinks about dividing the work while also providing your advice for how it might be split. Try to identify foundational systems.

**Listen for:**
- Repeated mentions of specific modules or features
- Clear separation in how they describe different parts
- "This part is about X, but that part is about Y"

### 2. Ordering Intuition

Understand what needs to come first or is foundational. Tease context out of the user's mind about dependencies and combine it with your advice.

**Listen for:**
- Mentions of "core" or "foundation"
- Dependencies: "X needs Y to work"
- Bootstrap requirements

### 3. Uncertainty Mapping

Identify what's clear vs. what needs exploration. Extract detail from the user on the most vague pieces while combining your knowledge.

**Listen for:**
- Hesitation or qualifiers ("maybe", "probably", "I think")
- Multiple alternatives being considered
- "I'm not sure how to..."

**Why it matters:**
Uncertain parts may need dedicated splits for /shipwright-plan exploration. Don't assume - flag it.

### 4. Existing Context

Capture constraints and integration points.

**Listen for:**
- Specific technologies, frameworks, or patterns
- API contracts or database schemas
- Organizational or deployment constraints

**Important:** Pass through to specs without researching. Your job is to capture context, not validate it.

## When to Stop

Stop the interview when you have enough information to:

1. **Propose a split structure the user will recognize**
2. **Identify dependencies between splits** (if multiple)
3. **Flag which splits could run in parallel** (if multiple)
4. **Capture key context and clarifications for /shipwright-plan**

> This is about interview **breadth** — when the split interview has enough to
> structure the work. It does not compete with the shared per-requirement
> **coverage** stop-condition, which binds **downstream**, where the FR rows are
> actually authored (spec-generation): a requirement's row is not settled until
> each of its context dimensions is answered or recorded `Basis: assumed`
> (`shared/requirement-elicitation.md` §8). Breadth here, per-requirement depth
> there — different stages, no conflict.

## Output

After the interview, write `{planning_dir}/shipwright_project_interview.md` with a complete transcript.

---

> The "Surface Inferred Assumptions First" pre-phase is adapted from
> [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
> `skills/spec-driven-development/SKILL.md` ("Surface assumptions immediately").
> MIT, © Addy Osmani.
