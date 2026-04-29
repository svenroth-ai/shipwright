# Interview Protocol

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

## Output

After the interview, write `{planning_dir}/shipwright_project_interview.md` with a complete transcript.
