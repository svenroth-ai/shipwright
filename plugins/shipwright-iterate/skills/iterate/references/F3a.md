# F3a — Reflection — Capture Learnings

Apply the reflection protocol (`references/reflection.md`):

1. Review the work done in this iterate run.
2. Check: new patterns, gotchas, corrections, tool/infra insights?
3. **Decisions** (pattern chosen, convention corrected) → ADR with
   `--architecture-impact convention` (handled via F3); the one-line
   `## Convention Updates` pointer in `conventions.md` is the ADR's anchor — see
   `references/F2.md` for the routing + compact format.
4. **Observations** (gotchas, framework quirks) → append ONE compact bullet to
   `.shipwright/agent_docs/conventions.md` under `## Learnings`:
   `- ({YYYY-MM-DD}) {phase} — {one-line rule}. [→ ADR/run_id for detail]`
   `conventions.md` is always-loaded Layer-1 context — keep it to a single
   line (≤ 600 chars; a forward-only gate enforces NEW entries). If it needs a
   paragraph, it is a **decision**: write an ADR (step 3) and leave a one-line
   pointer here.
5. **Cross-project insights** → save Claude Code feedback/project Memory.
6. If no learnings: skip — do not force entries.
