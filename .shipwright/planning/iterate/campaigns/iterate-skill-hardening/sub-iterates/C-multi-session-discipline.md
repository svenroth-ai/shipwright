# Sub-Iterate C — Multi-Session Discipline

> Part of campaign `iterate-skill-hardening`. **Independent of A and B**
> at the dependency level (it builds session-role machinery, not
> boundary tests). Runs stacked on B per branch strategy, but does not
> consume B's outputs.

## Context

When two Claude Code sessions run in parallel against the same repo
(e.g. one in main repo, one in a `.worktrees/<slug>/` worktree), one
must be designated canonical for cleanup/push. The non-canonical one
must NOT commit-and-push artifacts that would race the canonical side.

iterate-2026-05-03-adopt-env-local-scaffold demonstrated the failure
mode: a non-canonical commit (`71c47c3`, the BOM fix) was created
locally even though the canonical side had already announced it would
integrate that fix. The phrasing *"wollen wir hier commiten?"* read
as an open invitation but was actually a zustimmung-check.

C encodes the discipline structurally:

1. Detect when this iterate is running in parallel with another (B1c
   detection at lifecycle start).
2. Persist a session-role marker.
3. Guard pushes from non-canonical sessions until explicit auth.

## Scope

1. **B1c phase** in SKILL.md (extends B1 — the existing in-progress
   detection): detect parallel sessions by scanning
   `.worktrees/<slug>/.shipwright/iterate_session_role.json` files
   and the main-repo equivalent. Print role to user; ask once for
   designation if ambiguous.
2. `.shipwright/iterate_session_role.json` — JSON marker with fields
   `role: "canonical" | "secondary"`, `set_at`, `set_by_session_id`,
   `worktree_path`, `notes`.
3. Push guardrail: `shared/scripts/checks/check_session_role.py`
   (consulted by F11/runner Step 5 push, blocks `git push` from a
   `secondary` role unless `SHIPWRIGHT_SECONDARY_PUSH_AUTH=1` is set).
4. SKILL.md doc snippet: B1a section (already discussed parallel
   worktree conventions) gets a sibling B1c snippet for session
   roles + the push-guard rule + how to designate roles.

## Acceptance Criteria

- [ ] `shared/scripts/lib/session_role.py` (new) with:
      - `read_role(project_root) -> dict | None`
      - `write_role(project_root, role: str, session_id: str,
        worktree_path: str, notes: str = "") -> dict`
      - `detect_parallel_sessions(project_root) -> list[dict]`
        (scans main repo + `.worktrees/*/.shipwright/iterate_session_role.json`
         for any active session-role markers).
      - Idempotent writes (re-running with same role = no-op).
- [ ] `shared/scripts/checks/check_session_role.py` (new) with:
      - Reads role for current `cwd`.
      - Exits 0 if role is `canonical` OR if
        `SHIPWRIGHT_SECONDARY_PUSH_AUTH=1` is set.
      - Exits 1 with a clear message otherwise.
      - Designed to be called pre-push in CI hooks or manually before
        `git push`.
- [ ] `plugins/shipwright-iterate/skills/iterate/SKILL.md`:
      - New B1c phase added under B1, describing the detection +
        designation flow.
      - New B1a addendum about session roles (the rule from
        memory feedback_parallel_session_source_of_truth.md):
        "If canonical side has been declared elsewhere, this session
         is secondary by default. DO NOT git commit/push without
         explicit user auth."
      - F11 (Push step) gains a one-line check: "Run
        `check_session_role.py` first; non-zero → STOP."
- [ ] Tests:
      - `shared/tests/test_session_role.py` (new):
        - `write → read` round-trip (Affected Boundary test for the
          JSON shape; covers BOM + CRLF + non-ASCII per A's
          `boundary-probes.md`).
        - `detect_parallel_sessions` returns canonical + secondary
          when both markers exist in different worktrees.
        - Idempotency: write same role twice = no-op.
      - `shared/tests/test_check_session_role.py` (new):
        - secondary role + no env var → exit 1.
        - secondary role + `SHIPWRIGHT_SECONDARY_PUSH_AUTH=1` → exit 0.
        - canonical role → exit 0 always.
        - missing marker → exit 0 (default permissive — no marker
          means single-session, common case).

## Implementation Plan

1. `shared/scripts/lib/session_role.py`
   - JSON shape:
     ```json
     {
       "role": "canonical|secondary",
       "set_at": "<ISO-8601 UTC>",
       "set_by_session_id": "<SHIPWRIGHT_SESSION_ID>",
       "worktree_path": "<absolute>",
       "notes": "<optional>"
     }
     ```
   - Atomic write via `Path.write_text` with `tmp.replace(target)`
     pattern (matches autonomous_loop.py).
   - File location: `.shipwright/iterate_session_role.json` (project
     root).

2. `shared/scripts/checks/check_session_role.py`
   - argparse: `--project-root` default cwd.
   - Read role; apply gate; print rationale; exit 0 or 1.

3. `SKILL.md` edits — keep terse:
   - B1c block ~25 lines.
   - B1a addendum: a 5-line callout box.
   - F11 push: a 2-line addition.

4. Tests as listed in AC. Round-trip test exercises ALL probes from A's
   `boundary-probes.md` against the JSON marker file (BOM, CRLF,
   non-ASCII in `notes` field, etc.).

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `session_role.write_role` | `session_role.read_role` (and `check_session_role.py`, and B1c phase) | JSON file `.shipwright/iterate_session_role.json` |
| `session_role.detect_parallel_sessions` | B1c phase printout (SKILL.md) | List of dicts |
| `check_session_role.py` exit code | F11 push gate, runner Step 5 (after override lifts) | shell exit 0/1 |
| `SHIPWRIGHT_SECONDARY_PUSH_AUTH` env var | `check_session_role.py` reader | env string "1" or unset |

The JSON marker file is the highest-risk boundary: it's persisted to
disk, read across sessions, and may be edited by the user. All 8 probe
categories from A apply (BOM, CRLF, non-ASCII in `notes`, empty
strings, etc.).

## Confidence Calibration

- **Boundaries touched:** see Affected Boundaries — JSON marker file
  (`.shipwright/iterate_session_role.json`) is the highest-risk
  surface; check_session_role.py exit code is the secondary boundary;
  `SHIPWRIGHT_SECONDARY_PUSH_AUTH` env var is the tertiary one.
- **Empirical probes run** (all in `shared/tests/test_session_role.py`
  + `shared/tests/test_check_session_role.py`, 29 tests total, all
  green at runner-time before F0):
  - Round-trip canonical: `write_role → read_role` returns the same
    role/session/path/notes dict (no finding).
  - Round-trip secondary: same, with role=secondary (no finding).
  - **UTF-8 BOM probe:** prepend `\xef\xbb\xbf` to JSON bytes, re-read,
    role still parsed — no finding (reader strips BOM).
  - **CRLF probe:** write JSON with CRLF line endings, re-read, role
    still parsed — no finding (json.loads is line-ending agnostic).
  - **Non-ASCII probe:** notes field with `München — primärer Worktree
    (ä ö ü)` round-trips intact via `ensure_ascii=False`.
  - **Empty-notes probe:** `notes=""` round-trips; no IndexError /
    KeyError.
  - **Idempotency probe:** rewriting same role + worktree_path leaves
    file mtime + bytes unchanged + preserves original `set_at` /
    `set_by_session_id` (audit-trail invariant).
  - **Role-change probe:** canonical → secondary writes a fresh
    marker (no stale-marker bug).
  - **Invalid-role probe:** `write_role(role="leader")` raises
    ValueError BEFORE touching disk (no partial write).
  - **Garbage-bytes probe:** non-JSON marker file → `read_role`
    returns None (default permissive — no crash).
  - **Unknown-role probe:** marker with `role: "leader"` →
    `read_role` returns None (rejected outside VALID_ROLES).
  - **detect_parallel_sessions probes:** main-only (1), main +
    worktree (2 with both roles), worktree without marker (skipped
    silently), no markers anywhere (empty list).
  - **check_session_role.py exit-code matrix** (parametrized 4-corner
    test, subprocess invocation):
    - missing marker → exit 0 (`reason: no_marker`)
    - canonical, no env → exit 0 (`reason: canonical`)
    - canonical, env=1 → exit 0 (env is no-op when allowed)
    - secondary, no env → exit 1 (`reason: secondary_no_override`)
    - secondary, env=1 → exit 0 (`reason: secondary_with_override`)
  - **Human-readable output probe:** without `--json`, BLOCK/ALLOW
    prefix on stdout + detail on stderr (matches pre-push hook
    grep patterns).
- **Edge cases NOT probed + why acceptable:**
  - **POSIX `export KEY=value` prefix** — JSON has no shell-export
    syntax; not applicable.
  - **Inline `# comment`** — JSON has no comment syntax; an operator
    `#` would simply produce JSONDecodeError → `read_role` returns
    None (default permissive) — covered by the garbage-bytes probe.
  - **`#` inside a value / quoted-`#`** — JSON's quoting model
    handles `#` inside strings natively (`json.loads` parses it),
    not applicable.
  - **Concurrent writes from two processes:** explicitly out of
    scope. Locking is deliberately not added because parallel
    iterates are guided by role designation (canonical writes,
    secondary reads), not file locking. Adding `file_lock` would be
    a yak-shave. Documented as the assumption in
    `session_role.py` module docstring.
  - **Race between `read_role` and `write_role` in the same
    process:** Python's GIL serializes attribute access; the only
    cross-process window is the `tmp.replace(target)` step, which
    is atomic on POSIX and Windows. No probe needed.
- **Confidence-pattern check:** No "are you confident?" question
  has produced "yes + a subsequent finding" in this run. Probes
  ran in this order — round-trip → BOM → CRLF → non-ASCII → empty
  → idempotency → garbage → matrix → output-shape — and the most
  recent probe (the parametrized 4-corner matrix) found nothing
  new beyond what the earlier probes covered. Asymptote condition
  satisfied: last probe found nothing AND every applicable
  category is covered. **Declared exhausted.**

## Runner Overrides

1. NO push (Step 5). Orchestrator handles all pushes at campaign-end.
2. NO commit amends.
3. After F7, write result.json and exit.
4. Branch name: `iterate/skill-hardening-C-multi-session-discipline`.
   Branched from `base_branch =
   iterate/skill-hardening-B-confidence-calibration` (stacked).

## DOG-FOOD Notes

- **Boundary Tests:** Round-trip + 4 of A's 8 probes are real tests
  here against the JSON marker.
- **Confidence Calibration:** template above; runner populates pre-F0.
- **Multi-Session Discipline:** ironically applies to itself — but
  this campaign session is canonical, so no conflict. The push guard
  added in this sub-iterate WILL be respected at campaign-end push.
- **Boundary-Coverage Awareness:** Affected Boundaries populated.
