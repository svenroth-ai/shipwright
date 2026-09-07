# Mini-Plan: bloat-gate-subagent-marker-isolation

## Approach
Both `check_file_size.py` (PostToolUse marker writer) and `bloat_gate_on_stop.py`
(Stop gate) key the per-session marker file `bloat_pending.<key>.json` off
the hook payload's `session_id` alone. Claude Code shares one `session_id`
between a spawning session and every subagent it spawns via the Agent/Task
tool, and distinguishes them only via `agent_id`, present in the payload
only inside a subagent call. So a background `sub-iterate-runner` sharing
the orchestrator's git worktree also shares its marker file — its own
in-flight, uncommitted oversize edit blocks the orchestrator's unrelated
Stop event.

Fix: extend the marker key to `<session_id>` or `<session_id>.<agent_id>`
(new `bloat_baseline.marker_key`, in a new sibling module
`bloat_marker_key.py` to keep `bloat_baseline.py` under its own 300-line
ceiling). Both hook scripts delegate their existing `_session_id()` helper
to it. No `agent_id` → identical key to today (full backward compatibility,
zero migration).

## Alternative Considered
**Require `sub-iterate-runner` to self-resolve its own oversize touches
before yielding control back to the orchestrator** (the bug report's
"Alternative" suggestion). Rejected as the primary fix: it only addresses
`sub-iterate-runner` specifically, not any other current or future
background subagent sharing a worktree with its spawner, and it doesn't
fix the actual defect — the marker key conflating two distinct callers.
The `agent_id`-suffix fix is the general, root-cause-level fix; the
runner's own eventual Stop-class event (if/when wired) or its own F0/F11
finalization now naturally catches its own oversize files under its own
marker, without needing this extra process rule.

## Risk
Low. Two-line-of-defense change (composite key, sanitized, fully backward
compatible when `agent_id` is absent) to already heavily-tested hook
scripts; 47 pre-existing tests pass unmodified plus 5 new regression tests
covering the bug repro end-to-end.
