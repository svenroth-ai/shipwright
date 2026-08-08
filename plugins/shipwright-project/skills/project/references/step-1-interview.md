# Step 1: Interview

See [interview-protocol.md](interview-protocol.md) for detailed guidance.

**Goal:** Surface the user's mental model of the project and combine it with Claude's intelligence.

## Context to read (depends on input mode)

- **File mode**: Read `{initial_file}` — the requirements file seeds the conversation
- **Inline mode**: Use `{inline_description}` as starting context
- **Chat mode**: No pre-existing context — interview is the primary source
- If Extension scope, read ALL existing project context:
  - `CLAUDE.md` — stack, conventions, commands
  - `.shipwright/agent_docs/architecture.md` — app structure, component tree
  - `.shipwright/agent_docs/conventions.md` — coding standards, naming, patterns
  - `.shipwright/agent_docs/decision_log_index.md` — compact index of past
    architectural decisions (title + one-line summary). Read a full entry in
    `.shipwright/agent_docs/decision_log.md` only when the index, or an
    `ADR-NNN` already in context, points to it — grep the `### ADR-NNN`
    heading, or an offset/limit read, never the whole file (a single `Read`
    call caps at 2,000 lines; the log already exceeds it). No index match →
    grep `decision_log.md` directly rather than assume nothing exists.
  - `shipwright_sync_config.json` — existing file-to-FR mappings (if exists)
  - `.shipwright/planning/*/spec.md` — every existing spec across all splits.
    Run the coverage check first (small — a check, not an architecture;
    TC3.2, trg-c0d83dce):
    ```bash
    uv run "{shared_root}/scripts/tools/check_mandated_load_coverage.py" \
      --project-root "{project_root}" --glob ".shipwright/planning/*/spec.md"
    ```
    `exceeds_cap: false` means one ordinary `Read` covers the file.
    `exceeds_cap: true` means it is longer than a single `Read` call returns
    — the applied limit is the row's own `cap_lines` — read it via
    `offset`/`limit` across enough calls to cover every line, or declare
    explicitly "read K of N lines of {path} — not fully read" instead of
    proceeding as if it were fully seen. A row carrying an `error` key could
    not be checked at all — report that too, never assume it was read.
    `exists: false` means the mandate
    names a path that is not on disk — say so rather than treating it as read.
  - Run: `git log --oneline -20` — recent project history

## Interview depth by scope and input mode

| Scope | Input | Depth | Focus |
|-------|-------|-------|-------|
| Full App | File | Medium (5-10) | Clarify and deepen what's in the file |
| Full App | Inline | Deep (8-15) | Build full picture from brief description |
| Full App | Chat | Deep (8-15) | Discover everything from scratch |
| Extension | Any | Light (1-3) | What's changing, what's affected |

## Approach

- Use AskUserQuestion adaptively
- **One AskUserQuestion per question.** Do NOT batch multiple questions in a single markdown list — the host (Shipwright Command Center and any compatible CLI front-end) blocks on each AskUserQuestion call and waits for a `tool_result` reply before you can continue. Batching produces a fallback list that the user has to parse and answer manually, which defeats the point of the interactive interview.
- No fixed number of questions — stop when you have enough to propose splits
- Build understanding incrementally
- For Chat/Inline: start broad ("What are you building?"), then narrow down
- For File: start with clarifying questions about the document
- For Extensions: leverage existing CLAUDE.md context, don't re-ask what's documented

## Checkpoints

1. Write `{planning_dir}/shipwright_project_interview.md` with full interview transcript
2. **For Inline/Chat modes only:** Also write `{planning_dir}/requirements.md` — a consolidated requirements document synthesized from the interview. This ensures downstream skills have a file to reference.

## Step 2: Split Analysis (related)

See [split-heuristics.md](split-heuristics.md) for evaluation criteria.

**Goal:** Determine if project benefits from multiple splits or is a single coherent unit.

**Context to read:**
- `{initial_file}` - The original requirements
- `{planning_dir}/shipwright_project_interview.md` - Interview transcript

## Step 3: Dependency Discovery & project-manifest.md (related)

See [project-manifest.md](project-manifest.md) for manifest format.

**Goal:** Summarize splits, map relationships and write the project manifest.

**Checkpoint:** Write `{planning_dir}/project-manifest.md` with Claude's proposal.
