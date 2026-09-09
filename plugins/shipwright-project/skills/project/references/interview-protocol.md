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

## Capturing sharpened terms — write CONTEXT.md as you go

`shared/requirement-elicitation.md` §4 fires the moment a term is **captured,
challenged, or replaced with a precise one** during this interview; §7
requires the result land in the target project's `CONTEXT.md` **the moment it
is resolved** — never batched until the interview ends. Concretely: the turn
in which you and the user settle a term's meaning (a definition confirmed, a
vague word like "account" forced to Customer-or-User, a synonym rejected) is
the same turn in which you write it — before the next `AskUserQuestion`, in
two steps:

1. Ensure the scratch directory exists (`mkdir -p
   "{project_root}/.shipwright/agent_docs/runtime"` — a fixed path only, no
   interview text, so this one line is safe to run as a shell command), then
   **use the Write tool** (never a shell command) to write the sharpened
   term as JSON to a scratch file at
   `{project_root}/.shipwright/agent_docs/runtime/context-term-payload.json`
   (overwrite it each time — it is disposable, not read by anything else):

   ```json
   {"term": "<Term>", "definition": "<the settled definition, plain prose>",
    "avoid": "<rejected synonym — why it's wrong>"}
   ```

   (omit `"avoid"`, or set it to `null`, when there is no rejected synonym.)

2. Then run the producer against that file:

   ```bash
   uv run "{shared_root}/scripts/tools/write_context_term.py" \
     --project-root "{project_root}" \
     --payload-file "{project_root}/.shipwright/agent_docs/runtime/context-term-payload.json"
   ```

**Why two steps, not one hand-assembled shell command:** ordinary interview
language routinely contains a single quote — "the customer's cart", "it's
the settled definition". Substituting such text directly into a
shell-quoted `--term '<value>'` argument breaks out of the quoting, and the
rest of the string is then interpreted as shell syntax — a real,
agent-triggerable vulnerability the moment this is run as a literal bash
command, not a theoretical one. The Write tool never invokes a shell, so
step 1 has no quote-breakout surface at all, and step 2's `bash` command
then contains only fixed, known strings (`{project_root}`, the scratch
path) — never the interview's free text. **Never hand-assemble a
`--term '<value>'` shell invocation from interview-dictated text.** JSON
needs only its own, much simpler escaping (`\"` for a literal double quote,
`\\` for a backslash) that you already produce correctly whenever you write
JSON.

This is the one producer for `CONTEXT.md` (format: `shared/context-format.md`)
— idempotent (re-running with the same term is a no-op) and safe to call once
per sharpened term, so a term revisited later just updates in place.
**Omitting `"avoid"` on a re-sharpen keeps the existing `_Avoid_` line** — it
does not clear it; set `"clear_avoid": true` in the payload explicitly if the
rejected-synonym note itself needs to be removed (mutually exclusive with
`"avoid"`). It is a plain write, not an `AskUserQuestion`: it does not block
the interview and it never substitutes for the confirm-before-acting step
(§9). The
`{planning_dir}/shipwright_project_interview.md` transcript (Checkpoints,
below) is written **in addition to** this per-term write, not instead of it —
the transcript is the record of the conversation, `CONTEXT.md` is the
project's glossary.

**Never hand-edit `CONTEXT.md` (Edit/Write) while an interview is running.**
The producer script above holds a file lock and replaces the whole file
atomically; a hand-edit is coordinated with neither, so a hand-edit racing
the script's write can silently drop a term either side loses. All
`CONTEXT.md` writes during elicitation go through
`write_context_term.py` — or wait for it to return before touching the file
by hand. **Known limitation:** the script only ever writes `Language`
entries. `Relationships` and `Flagged ambiguities` (also required by
`shared/requirement-elicitation.md` §4/§7) have no producer yet and still
require a hand-edit — do that hand-edit **after** the interview's
`write_context_term.py` calls are done for the session, never interleaved
with them.

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

> Any topic below can surface a term worth sharpening — when it does, follow
> "Capturing sharpened terms" above **in that same turn**, don't wait for a
> dedicated topic.

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
