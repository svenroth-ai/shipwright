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

- **Boundaries touched:** see Affected Boundaries.
- **Empirical probes:** _to be filled by runner_
  - Round-trip: `write_role(canonical) → read_role` returns identical
    dict.
  - BOM probe: write file, prepend `﻿` byte to bytes, re-read,
    assert no crash + role still detectable.
  - CRLF probe: write with explicit CRLF, re-read, assert intact.
  - Non-ASCII in `notes`: assert UTF-8 round-trip.
  - Empty `notes`: assert handled gracefully.
- **Edge cases NOT probed + why:** _to be filled by runner_
  - Concurrent writes from two processes: out of scope; locking is
    deliberately not added because parallel iterates are guided by
    role designation, not file locking. (Document the assumption.)
- **Confidence-pattern check:** _to be filled by runner_

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
