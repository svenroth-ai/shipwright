# Mini-Plan: claude-worktree-gate

- **Run ID:** iterate-2026-10-01-claude-worktree-gate
- **Spec:** `.shipwright/planning/iterate/2026-10-01-claude-worktree-gate.md`

## Files
| File | Change |
|---|---|
| `plugins/shipwright-iterate/scripts/hooks/iterate_worktree_gate.py` | new — arm + enforce, one script for both events |
| `plugins/shipwright-iterate/scripts/hooks/iterate_worktree_gate_policy.py` | new — shell-command allowlist |
| `plugins/shipwright-iterate/scripts/hooks/codex_pretooluse_matcher.py` | edit — extract `segment_script_basename` (behavior-preserving) + `has_unsafe_punctuation` hardening shared with the Claude gate (operator-approved scope expansion; regression tests in `test_codex_pretooluse_matcher.py`) |
| `plugins/shipwright-iterate/hooks/hooks.json` | edit — register on `UserPromptSubmit` + `PreToolUse` |
| `plugins/shipwright-iterate/tests/test_iterate_worktree_gate.py` | new — unit + registration + subprocess end-to-end |
| `plugins/shipwright-iterate/scripts/hooks/iterate_worktree_gate_state.py` | new — marker + isolation state |
| `plugins/shipwright-iterate/tests/test_iterate_worktree_gate_lifecycle.py` | new — release, re-arm, campaign, off switch, allowlist pinning |
| `plugins/shipwright-iterate/tests/test_iterate_worktree_gate_integration.py` | new — real `setup_iterate_worktree.py` releases the gate |
| `.shipwright/planning/01-adopted/spec.md` | edit — FR-01.11 AC40 |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md` | edit — one sentence in B1a |
| `docs/hooks-and-pipeline.md` | edit — registry rows |
| `CHANGELOG-unreleased.d/Added/…` | new — drop |

## Work breakdown (status)
1. Matcher refactor + policy module — **done pre-iterate**, Codex tests green.
2. Gate script (arm/enforce/isolation) — **done pre-iterate**.
3. hooks.json registration + docs + SKILL line + changelog — **done pre-iterate**.
4. Unit tests — **done pre-iterate** (112 pass in the neighbourhood).
5. **Remaining build work:** FR-01.11 AC40 in spec.md; `hooks-codex` negative assertion; subprocess end-to-end test; integration test with the real setup script (cross_component); round-trip test of the marker file (boundary probe, `touches_io_boundary`); AC tags (`@FR`) on tests per project convention.
6. Review cascade (spec → code → doubt, Opus), external plan/architecture review, F0–F11.

## Test strategy
Real git repo + real linked worktree; no mocks of "is a worktree". Registered-command subprocess test proves the shipped `uv run --no-project` shape. Integration test drives `setup_iterate_worktree.py` itself and asserts the gate flips from deny to allow without touching the gate's own state.

## Alternative approach (rejected)
**Enforce through the existing `validate_command.sh` / a project-level `.claude/settings.json` hook.** Rejected: `${CLAUDE_PLUGIN_ROOT}` expands only for plugin-registered hooks (ADR-019/020), and a per-project install is the model `iterate-20260505-plugin-hook-registration` retired.
**Mirror the Codex design exactly (one-shot first-call gate).** Rejected: Codex needs it because a hook there cannot be re-asked cheaply and runs on a different tool vocabulary; Claude Code can deny repeatedly, so a live-state check on every mutating call closes the "denied first call, then a different second call sails through" gap the Codex docstring explicitly accepts.
**Deny-by-default for all tools.** Rejected: Claude has many read-only and MCP tools; a default-deny would break the skill's own pre-setup steps and memory writes.
