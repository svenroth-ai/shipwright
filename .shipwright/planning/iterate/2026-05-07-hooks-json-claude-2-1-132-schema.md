# Iterate Spec: Wrap plugins/*/hooks/hooks.json under top-level `hooks` key for Claude Code 2.1.132+

- **Run ID:** iterate-2026-05-07-hooks-json-claude-2-1-132-schema
- **Type:** bug
- **Complexity:** small (mechanical sweep across 12 files + 12 plugin.json version bumps; structural rewrap, no logic change)
- **Status:** draft

## Goal

Restore plugin loadability under Claude Code 2.1.132+. The new harness validates `plugins/*/hooks/hooks.json` against a schema that requires a top-level `"hooks"` wrapper object whose keys are event names. Existing files (post-ADR-019/020) place event names at the top level of the JSON document directly. Loading fails with:

```
Hook load failed: expected record, received undefined at path ["hooks"]
```

After the failure, no `SessionStart`, `UserPromptSubmit`, `Stop`, `PreToolUse`, `PostToolUse`, or `SubagentStop` hooks fire for any Shipwright plugin. The SDLC pipeline silently breaks for every Claude Code 2.1.132+ user (i.e. all current users, post that release).

## Bug detail

Pre-2.1.132 schema (Shape A — what Shipwright shipped through v0.17.0):

```json
{
  "SessionStart": [ { "hooks": [ { "type": "command", "command": "..." } ] } ],
  "UserPromptSubmit": [ ... ],
  "Stop": [ ... ]
}
```

2.1.132+ schema (Shape B — required):

```json
{
  "hooks": {
    "SessionStart": [ { "hooks": [ { "type": "command", "command": "..." } ] } ],
    "UserPromptSubmit": [ ... ],
    "Stop": [ ... ]
  }
}
```

The change is purely structural — the *contents* of each event array (matchers, hook arrays, command strings, ${CLAUDE_PLUGIN_ROOT} quoting from ADR-022) are untouched. Only the carrier shape changes.

This is a Shape-only fix in the same lineage as ADR-019 (matcher-group shape) and ADR-020 (command-literal quoting). The lurking failure mode is identical (silently-failing hooks block the SDLC pipeline) but the trigger is the harness version, not the install path.

## Acceptance Criteria

- [x] **AC-1 — All 12 plugin hooks.json files wrap their event-name dict under a top-level `"hooks"` key.** Repo-wide invariant: `JSON.parse(hooks.json).hooks` is a non-array object whose keys are event names (`SessionStart`, `UserPromptSubmit`, `Stop`, `PreToolUse`, `PostToolUse`, `SubagentStop`).
- [x] **AC-2 — JSON validity preserved.** All 12 `plugins/*/hooks/hooks.json` files still parse as valid JSON; event-array contents (matchers, hook arrays, command strings) byte-for-byte equivalent semantically.
- [x] **AC-3 — Plugin versions bumped.** Every patched plugin's `.claude-plugin/plugin.json` `version` field is bumped (10 × `0.2.0`→`0.2.1`, `shipwright-iterate` `0.4.0`→`0.4.1`, `shipwright-plan` `0.3.0`→`0.3.1`). Allows `claude plugin update <name>@shipwright` to pull the fix. `shipwright-preview` is correctly NOT bumped (no hooks.json — no fix needed).
- [x] **AC-4 — Regression test.** New parametrized test asserts the AC-1 invariant repo-wide. Catches future hooks added under the old (top-level-event-name) shape at test time, not at user install time.
- [x] **AC-5 — Existing quoting test still green.** `shared/tests/test_hooks_json_quoting.py` (ADR-022 regression) keeps passing — its recursive `_collect_command_strings` traverses the new wrapper depth without modification.

## Out of Scope

- **Bumping the monorepo top-level version** beyond per-plugin bumps. The release tag (`v0.17.0`) governs the marketplace bundle; per-plugin versions govern what `claude plugin update` resolves. The next release tag will bundle this fix automatically.
- **Empirical `claude plugin install/update/list` round-trip on this PC.** The user reports that shipwright is not installed on this PC pending this fix, and a second PC is not available. Verification is structural (JSON-parse + schema check) + the documented expectation from the bug report. The end-to-end smoke (`claude plugin update shipwright-iterate@shipwright` → status ✔ enabled) is the user's verify-step at install time.
- **Migrating any non-plugin `hooks.json` files** (e.g. `~/.claude/settings.json` user/project hooks). Out of scope — those files have always used the wrapper shape; only `plugins/*/hooks/hooks.json` shipped under the legacy shape.
- **Touching `shipwright-preview`** — has no hooks.json and is not affected.

## Affected FRs

- **FR-01.01 through FR-01.13** indirectly — every plugin's between-phase hooks fall under its FR. As with ADR-022, this is a mechanical schema migration; no FR semantics change. No new ACs needed in spec.md (per the iterate skill's "Spec Update" guidance: this is not an FR-level behavior change).

## Affected Boundaries

| Producer | Artifact | Consumer | Probe |
|---|---|---|---|
| Shipwright (this iterate writes) | `plugins/*/hooks/hooks.json` | Claude Code 2.1.132+ harness (parses on plugin load) | Round-trip empirical: `claude plugin update <name>@shipwright` + `claude plugin list` shows ✔ enabled. **Cannot run on this PC** (shipwright not installed pending this fix) — substituted with structural schema-conformance test (AC-4). |

The substitution is the right call here: the consumer is closed-source binary external to the repo, and the harness's documented schema is what we're conforming to. A unit-level structural assertion is the strongest in-repo gate available.

## Confidence Calibration

1. **Boundaries touched:** see Affected Boundaries above. Single producer/consumer pair: shipwright-repo writes `hooks.json` → Claude Code reads on plugin load.
2. **Empirical probes run:**
   - JSON-parse of all 12 patched files via `ConvertFrom-Json` in PowerShell — all 12 returned non-null `.hooks` object with correct event count (12/12, see verify step in F0).
   - Event-count cross-check vs. pre-patch counts (manual diff) — 36 events total preserved across 12 files, no drops or additions.
   - `_collect_command_strings` traversal sanity: existing ADR-022 test traverses any depth of nested dicts/lists; wrapping under `.hooks` adds one level but doesn't break the recursion.
3. **Edge cases NOT probed + why acceptable:**
   - **Live `claude plugin install/update`** — out of scope per spec; user is the verifier on install (it's the one machine where shipwright is not yet installed).
   - **Non-default Claude Code versions (< 2.1.132)** — the new shape is documented as the v2.1.132 schema. Older Claude Code versions are unsupported; bug report does not request backwards-compat.
4. **Confidence-pattern check:** No "are you confident?" question received "yes" + a subsequent finding in this run. Single concern surfaced and resolved structurally (`shipwright-preview` correctly skipped — no hooks.json).

## Verification (small)

- **Surface:** none (plugin-metadata change; no startable surface in this repo).
- **Justification (mandatory at surface=none):** The consumer of `hooks.json` is the Claude Code 2.1.132+ binary, not any code in this repo. There is no "dev stack" against which to drive the file empirically — the only round-trip is `claude plugin update` on a machine where shipwright can be installed. Per the user's bug report, this PC has shipwright deinstalled pending this fix; a second machine is unavailable. Substituted with structural regression test (AC-4) + the bug-report verify-step which the user runs on install.
- **Runner command (post-install, run by user):**
  ```bash
  claude plugin update shipwright-iterate@shipwright
  claude plugin list | grep -A1 shipwright-iterate
  # expected: ✔ enabled (was ✘ failed to load before fix)
  ```
- **Fail-closed:** if `claude plugin list` still shows ✘ failed to load on user's PC after `update`, escalate — bug detail is wrong about the schema or partial coverage was missed.
