# Mini-Plan: register suggest_iterate as a plugin-level hook

- **Run ID:** iterate-20260505-plugin-hook-registration
- **Spec:** `.shipwright/planning/iterate/2026-05-05-plugin-hook-registration.md`
- **Branch:** `iterate/plugin-hook-registration` (off main)
- **Complexity:** medium
- **Risk flags:** `touches_io_boundary` (hooks.json + settings.json)

## Approach

**Strategy A (chosen):** Register `suggest_iterate.py` in the
`shipwright-iterate` plugin's own `hooks/hooks.json` and retire the
project-level installer entirely. Claude Code already loads plugin
hooks from `~/.claude/plugins/cache/shipwright/<plugin>/hooks.json`
for every enabled plugin, with `${CLAUDE_PLUGIN_ROOT}` correctly bound
to the plugin's cache directory. The same script (suggest_iterate.py)
runs unchanged — only the registration channel changes.

The script already reads project root from the hook payload's
`cwd` (stdin JSON, line 172 of suggest_iterate.py), and walks up to
the monorepo root via `Path(__file__).resolve().parent.parent.parent.parent`
to import `classify_intent` (line 128). Both behaviors continue to
work in the new registration model: `cwd` comes from Claude Code at
runtime and `__file__` resolves under the plugin cache (`~/.claude/
plugins/cache/shipwright/shared/scripts/hooks/suggest_iterate.py`),
which has the same `parent.parent.parent.parent` → `~/.claude/plugins/
cache/shipwright/` shape, with `plugins/shipwright-iterate/scripts/lib/`
present (verified from cache layout).

## Alternative considered

**Strategy B:** Keep the project-level installer; switch the writer's
command from `${CLAUDE_PLUGIN_ROOT}/...` to
`${CLAUDE_PROJECT_DIR}/...` and copy `suggest_iterate.py` into every
adopted project at adopt time.

- **Rejected** for three reasons:
  1. Code duplication — every adopted project carries a copy of the
     hook script, which goes stale on Shipwright upgrades. Today's
     plugin model lets a single update propagate via
     `update-marketplace.sh`. Strategy B trades that for N project-
     local copies that each need explicit update.
  2. Same blast radius as the bug being fixed. The script depends on
     `classify_intent.py` from the monorepo (line 128 path arithmetic).
     Inside an adopted project, that path doesn't exist and the
     classifier import silently fails (script returns None at line
     137). Either we copy the entire `plugins/shipwright-iterate/
     scripts/lib/classify_intent.py` tree too, or we rely on a parallel
     monorepo checkout. Both options are worse than plugin
     registration.
  3. Compliance verifier A6 stays as-is, locking in the project-
     level invariant. The follow-up memo
     (`project_hook_path_resolution_followup.md`) already analyzed
     this and called Strategy A "the likely correct fix" with
     Strategy B explicitly identified as "worse because it duplicates
     the script across every adopted project and breaks on plugin
     upgrades."

The memo's conclusion holds. Strategy A.

## Files to change

### Adds

| File                                                 | Change |
|---|---|
| `plugins/shipwright-iterate/hooks/hooks.json`        | Add `UserPromptSubmit` matcher group with the canonical command literal. Preserve existing `SessionStart` + `Stop` entries verbatim. |
| `plugins/shipwright-iterate/tests/test_hooks_json_registration.py` | NEW: assert `UserPromptSubmit` entry exists with canonical Shape-B + quoted + `--no-project` form; AC-1 + AC-11 round-trip. |

### Deletes

| File                                                              | Why |
|---|---|
| `plugins/shipwright-adopt/scripts/lib/hook_installer.py`          | Module retired (AC-2). |
| `plugins/shipwright-adopt/tests/test_hook_installer.py`           | All 11 tests target a module that no longer exists (AC-2). |

### Edits

| File                                                                          | Change                                                                                                                                                              |
|---|---|
| `plugins/shipwright-adopt/scripts/tools/generate_adoption_artifacts.py`       | Remove `from hook_installer import install_suggest_iterate_hook` and the call site at line 506. Add a comment line referencing this iterate's run_id (AC-3).        |
| `shared/scripts/tools/verifiers/adopt_compliance.py`                          | Delete `check_a6_hook_installed` and its registration. AC-4 LOCKED to remove (not rewrite) per user decision 2026-05-05. Claude Code itself surfaces disabled plugins; A6 duplicated that. |
| `plugins/shipwright-build/skills/build/SKILL.md`                              | Remove the "Hook auto-install" stanza (AC-5).                                                                                                                       |
| `plugins/shipwright-changelog/skills/changelog/SKILL.md`                      | Same as above (AC-5).                                                                                                                                               |
| `plugins/shipwright-deploy/skills/deploy/SKILL.md`                            | Same (AC-5).                                                                                                                                                        |
| `plugins/shipwright-design/skills/design/SKILL.md`                            | Same (AC-5).                                                                                                                                                        |
| `plugins/shipwright-plan/skills/plan/SKILL.md`                                | Same (AC-5).                                                                                                                                                        |
| `plugins/shipwright-project/skills/project/SKILL.md`                          | Remove the per-section "Hook auto-install" stanza (AC-5) AND remove the larger "Install phase-router hook" sub-step block at line ~389-405 (AC-6).                  |
| `plugins/shipwright-test/skills/test/SKILL.md`                                | Same as build (AC-5).                                                                                                                                               |
| `plugins/shipwright-run/skills/run/SKILL.md`                                  | Remove "Step 4.5: Install Phase-Router Hook" (lines ~162-185) entirely. Replace with a one-line note: "Hook is registered in `shipwright-iterate` plugin's `hooks/hooks.json`; no project-level install needed." (AC-6) |
| `plugins/shipwright-adopt/skills/adopt/SKILL.md`                              | Update front-matter description and the artifact list to remove the suggest_iterate-hook bullet (AC-7).                                                              |
| `.claude/settings.json` (this monorepo's own)                                 | Remove the `hooks.UserPromptSubmit` block (lines 7-18). Keep `permissions.additionalDirectories` intact. (AC-9)                                                     |
| `.shipwright/planning/01-adopted/spec.md`                                     | Realign FR-01.13 / FR-01.02 / FR-01.01 ACs (mark ADR-019/020 carrier-shape + quoted-path ACs obsolete with a one-liner referencing this iterate's ADR). Add new FR-01.11 AC for plugin-hook ownership. (AC-8) |
| `docs/hooks-and-pipeline.md`                                                  | Add a row in the hooks registry for `suggest_iterate.py` under `shipwright-iterate` plugin's `UserPromptSubmit` registration. Cross-reference this iterate's ADR. (AC-10) |

## Work breakdown (rough order, single session)

1. **Branch.** `git checkout -b iterate/plugin-hook-registration` from `main`.
2. **RED — write failing tests first.**
   - `plugins/shipwright-iterate/tests/test_hooks_json_registration.py`:
     loads `plugins/shipwright-iterate/hooks/hooks.json`, asserts
     `UserPromptSubmit` key exists, asserts inner command literal
     equals canonical. Run pytest — expect failure (key not yet
     present).
   - Boundary round-trip test (AC-11) in same file or sibling.
   - Adopt-side: rewrite `test_generate_adoption_artifacts.py` (or
     equivalent) to assert NO UserPromptSubmit entry is written by
     the adopt scaffold. Run — expect failure.
3. **GREEN — register the hook + retire the installer.**
   - Add `UserPromptSubmit` block to plugin hooks.json.
   - Delete `hook_installer.py` + `test_hook_installer.py`.
   - Edit `generate_adoption_artifacts.py` to drop the import + call.
   - Edit verifier A6.
   - Run pytest — expect green at this point for the test plugin and
     the adopt plugin. (Spec/SKILL.md edits don't affect tests.)
4. **Sweep SKILL.md edits (AC-5, AC-6, AC-7).** Apply the deletions to
   the 7 SKILL.md files + verbose snippets in run/project + adopt
   artifact list.
5. **Spec realignment (AC-8).** Edit
   `.shipwright/planning/01-adopted/spec.md` — mark obsolete ACs +
   add new FR-01.11 AC.
6. **Docs update (AC-10).** Edit `docs/hooks-and-pipeline.md`.
7. **Local workaround removal (AC-9).** Edit this monorepo's
   `.claude/settings.json` to drop the local UserPromptSubmit entry.
8. **Sync marketplace cache.** `bash scripts/update-marketplace.sh` so
   the new `plugins/shipwright-iterate/hooks/hooks.json` lands in
   `~/.claude/plugins/cache/shipwright/shipwright-iterate/.../hooks/hooks.json`.
9. **Manual smoke test.** New Claude Code session in this monorepo;
   send a non-slash UserPromptSubmit ("hello"); confirm:
   - No "hook is not associated with a plugin" error.
   - `[Shipwright] Detected:` additionalContext appears when prompt
     matches a routing pattern (pick a phrase that fires the test
     pattern, e.g. "tests laufen lassen" → `[Shipwright] Detected
     intent: test`).
   - Otherwise hook exits silently (script's guards 1–4).
10. **Boundary Probe + Self-Review + Confidence Calibration.**
11. **Full Code Review** (medium → always).
12. **Full pytest suite** (medium → full suite).
13. **External LLM Review** (Step 4 — runs BEFORE build per skill, but
    the deferred-from-spec wording in this skill suggests the review
    runs against the iterate spec + mini-plan; perform this step
    actually before step 3 of this work breakdown).
14. **Architecture update.** F2: structural impact (new write surface
    for hooks.json registration; removal of legacy
    install-into-project pattern). Update `architecture.md` Data Flow
    section.
15. **Finalization F0–F12.**

## Step 13 ordering correction

Per skill's Phase Matrix, External LLM Review fires at Step 4 of the
FEATURE/CHANGE path, BEFORE build. For BUG path it lists Step 4 as
Mini-Plan but external review still applies at medium per the matrix.
Run external review immediately after this mini-plan + spec are
approved by the user (Step 3b), THEN proceed to "Branch + RED" (work
breakdown step 1).

Final order: Spec → Mini-Plan → User Approval → External LLM Review
→ Branch + RED → GREEN → SKILL.md sweep → Spec realignment → Docs
→ Workaround removal → Cache sync → Smoke → Boundary Probe →
Self-Review → Confidence Calibration → Full Code Review → Full
pytest → architecture.md → F0–F12.

## Test strategy summary

- **Unit:** new test in `plugins/shipwright-iterate/tests/` for the
  registration assertion (replaces the deleted `test_hook_installer.py`
  semantically — both test "the hook ends up wired correctly", just
  via different channels).
- **Round-trip (AC-11):** spawn the hook with stub
  `${CLAUDE_PLUGIN_ROOT}` + UserPromptSubmit-shaped JSON on stdin.
- **Smoke (manual, recorded in self-review):** monorepo session with
  the local workaround removed; confirm hook fires from plugin path.
- **Full pytest:** medium → full suite.
- **Verifier:** updated A6 logic gets its own assertion in the
  verifier test suite.

## Migration / runtime risk

- **No DB schema changes** (n/a — no DB).
- **No breaking config changes** for users — they don't see the
  hook as a config surface, only the symptom.
- **Adopted projects with legacy entries stay dirty until manually
  cleaned up.** Documented in spec Risks. Optional follow-up iterate
  for a one-shot cleanup verb.
- **Plugin disable = hook stops firing** (intentional new semantics;
  documented in FR-01.11 AC).

## Done criteria

- All 11 ACs from the spec checked off.
- Full pytest green from monorepo root + each plugin.
- Manual smoke test in monorepo confirms hook fires without error.
- ADR written; `iterate_history` updated; CHANGELOG-unreleased.d/
  drop file recorded.
