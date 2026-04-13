# Iterate Spec: content-aware drift check for CLAUDE.md

- **Run ID:** iterate-2026-04-13-claude-md-drift
- **Type:** enhancement
- **Complexity:** small
- **Status:** draft

## Context

The Shipwright repo's own `CLAUDE.md` and `webui/CLAUDE.md` drifted badly in the first Early Access cycle — missing plugin folders, commands that don't exist (`cd webui && npm run dev` — there is no root `webui/package.json`), stale component names. Fixed manually in `b6ad217`.

The existing hook [shared/scripts/hooks/check_drift.py](shared/scripts/hooks/check_drift.py) did not catch it because it is timestamp-only (compares `mtime(CLAUDE.md)` against a hard-coded list of 8 files and 4 dirs) and is registered only on `shipwright-build` + `shipwright-security` SessionStart, neither of which runs when you iterate on the Shipwright repo itself.

## Goal

Extend the existing hook with content checks, and register it on `shipwright-iterate` so it also fires on the Shipwright repo.

## Changes (3 files)

### 1. `shared/scripts/hooks/check_drift.py`

Add two content checks after the existing timestamp check. Same exit-0 warning policy, findings appended to the same `additionalContext` output.

- **Structure check.** For each CLAUDE.md found at `./CLAUDE.md` and `*/CLAUDE.md` (one level down): regex-parse the first fenced code block under a `## Structure` or `### Structure` heading. Extract top-level entries (lines matching `^(\w[\w-]*)/?` before any `#` comment). Compare against `os.listdir()` of the CLAUDE.md's directory, ignoring dot-files and `node_modules`, `__pycache__`, `dist`, `build`, `.venv`. Report:
  - entries documented but missing on disk
  - directories on disk but not documented (skip if in `.gitignore`)

- **Command check.** In the same CLAUDE.md files: regex-parse `bash` fenced blocks under `### Development`. For each `npm run <script>` reference (including `cd X && npm run <script>` form), resolve the nearest `package.json` walking up from the CLAUDE.md location (or from `X/` if a `cd` prefix is present), and verify `<script>` exists in its `scripts` map. Report missing script references as `CLAUDE.md references 'npm run <x>' but not defined in <path>/package.json`.

- On parse failure (no Structure heading, malformed fenced block, missing package.json): skip that check for that file silently. No exceptions propagated.

- Keep all existing timestamp logic untouched.

### 2. `plugins/shipwright-iterate/hooks/hooks.json`

Add a SessionStart entry for `check_drift.py`, mirroring the existing entries in `shipwright-build` and `shipwright-security` (same path pattern using `${CLAUDE_PLUGIN_ROOT}`).

### 3. `docs/hooks-and-pipeline.md`

One-line update in the hooks registry: note that `check_drift.py` now also performs content-aware structure and command checks, and is registered on iterate/build/security SessionStart.

## Verification

1. `uv run shared/scripts/hooks/check_drift.py` from the Shipwright repo root → no findings (both CLAUDE.mds are fresh after `b6ad217`).
2. Temporarily delete `shipwright-iterate` from the Structure block of the root `CLAUDE.md` → re-run → warning fires naming `shipwright-iterate` → restore.
3. Temporarily insert `cd webui && npm run bogus` into `webui/CLAUDE.md` Development block → re-run → warning fires naming `bogus` and `webui/package.json` (or the missing-package-json case) → restore.
4. Start a `/shipwright-iterate` session in the Shipwright repo → check the SessionStart `additionalContext` contains the new format when drift is present and is absent when drift is not.

No unit tests. The hook is warning-only (exit 0) and the three manual verification steps above cover the behaviour end-to-end. If false positives show up after a week of use, add a small ignore list or tighten the regex in a follow-up — do not front-load test scaffolding for something that doesn't block anything.
