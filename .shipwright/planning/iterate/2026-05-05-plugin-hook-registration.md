# Iterate Spec: register suggest_iterate as a plugin-level hook (retire hook_installer)

- **Run ID:** iterate-20260505-plugin-hook-registration
- **Type:** bug
- **Complexity:** medium (manual override — wide-area refactor across 8
  plugins, FR-spec ACs obsoleted, verifier rewrite, hook-installer
  module retirement)
- **Status:** draft

## Context

Closes the deferred follow-up to ADR-019 / ADR-020. ADR-019 fixed the
hook-installer's *carrier shape* (Shape A → Shape B). ADR-020 fixed
the *command literal* (quoting + `--no-project` + upgrade-in-place).
Both layered patches accept the underlying premise that
`suggest_iterate.py` is installed into project-level
`.claude/settings.json` with the command:

```
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"
```

That premise is wrong. Per Claude Code's hook contract the variable
`${CLAUDE_PLUGIN_ROOT}` is **only** expanded for hooks registered in a
plugin's own `hooks/hooks.json`. In a project-level `settings.json` the
variable has no plugin context — Claude Code now surfaces an explicit
runtime error:

```
UserPromptSubmit hook error
└ Failed to run: Hook command references ${CLAUDE_PLUGIN_ROOT} but the
  hook is not associated with a plugin. This variable is only available
  in hooks defined in a plugin's hooks/hooks.json file, not in [project
  settings].
```

Symptom: every `UserPromptSubmit` in any project that ran
`/shipwright-adopt`, `/shipwright-project`, or `/shipwright-run` is
gated by a hook that errors out before it can resolve a path. The
shipwright monorepo itself was masked by a hand-edited workaround in
its own `.claude/settings.json` (`${CLAUDE_PROJECT_DIR}/shared/...`);
every other adopted project has the broken form.

The premise was always wrong; ADRs 019 and 020 only patched symptoms.
This iterate fixes the architecture: register the hook in the
`shipwright-iterate` plugin's own `hooks/hooks.json` and retire the
project-level installer.

## Goal

Move `suggest_iterate.py` from "installed per-project into
`.claude/settings.json` by an installer module" to "registered once in
`plugins/shipwright-iterate/hooks/hooks.json`, fired by Claude Code for
every UserPromptSubmit in every project where the
`shipwright-iterate@shipwright` plugin is enabled". Retire the
installer module and every SKILL.md / verifier / spec AC that codifies
the project-level install path. Remove the hand-edited
`${CLAUDE_PROJECT_DIR}` workaround from this monorepo's own
`.claude/settings.json` because the plugin-hook supersedes it.

## Bug detail

The deferred bug from `project_hook_path_resolution_followup.md`:

- **Bug:** `plugins/shipwright-adopt/scripts/lib/hook_installer.py:32-35`
  emits a project-level hook command that references
  `${CLAUDE_PLUGIN_ROOT}` — a variable Claude Code only expands inside
  plugin-context hooks. In project settings.json the value is
  unresolved; Claude Code now hard-errors instead of silently failing.
- **Why broken in the first place:** No plugin's `hooks.json` registers
  `suggest_iterate.py`. A grep across `**/hooks.json` in the monorepo
  confirms the install path through `hook_installer.py` is the only
  distribution channel — but that channel expands a plugin-context-only
  variable.
- **Why ADRs 019/020 didn't fix it:** Both stayed within the project-
  level installer model. ADR-019 fixed the carrier-shape parse error
  that was masking the variable-expansion error; ADR-020 fixed an
  orthogonal quoting issue; neither changed the distribution channel.
  Listed explicitly as deferred during ADR-019 because changing the
  channel widens the scope to "register hook in plugin instead" and
  needs its own iterate.

## Acceptance Criteria

- [ ] **AC-1 — Plugin-level hook registration is the only install
  channel.** `plugins/shipwright-iterate/hooks/hooks.json` contains a
  `UserPromptSubmit` matcher group whose inner `hooks[*].command` is
  exactly:
  `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"`.
  Plugin-context expansion of `${CLAUDE_PLUGIN_ROOT}` produces the
  cached path of `shipwright-iterate`, and `../../shared/...` resolves
  to the cached `shared/` directory next to the plugin caches. The
  Shape-B matcher-group form is preserved (per ADR-019); the quoted
  path + `--no-project` is preserved (per ADR-020).
- [ ] **AC-2 — `hook_installer.py` and its tests are retired.**
  `plugins/shipwright-adopt/scripts/lib/hook_installer.py` and
  `plugins/shipwright-adopt/tests/test_hook_installer.py` are removed.
  No callable in the monorepo references
  `install_suggest_iterate_hook` after this iterate (verified via grep).
- [ ] **AC-3 — `/shipwright-adopt` no longer writes the hook into
  project-level settings.json.** `generate_adoption_artifacts.py` is
  updated so the adopt scaffold neither imports
  `hook_installer` nor calls `install_suggest_iterate_hook`. A fresh
  `/shipwright-adopt` run on a previously-clean target project produces
  no `UserPromptSubmit` entry under `.claude/settings.json` (the entry
  comes from the plugin instead).
- [ ] **AC-4 — Compliance verifier A6 is removed (LOCKED 2026-05-05).**
  `check_a6_hook_installed` and its registration in the verifier's
  check-list are deleted from
  `shared/scripts/tools/verifiers/adopt_compliance.py`. The plugin-
  enabled invariant is already enforced by Claude Code itself at
  session start (a disabled plugin = no hook fired); a custom A6
  duplicates that enforcement. The decision log entry for this
  iterate notes A6's retirement and the obsolete invariant. Any
  test in the verifier test suite that asserts A6 runs is removed
  along with the check.
- [ ] **AC-5 — All seven SKILL.md "Hook auto-install" stanzas are
  removed.** The verbatim sentence
  `"Hook auto-install: If shipwright_run_config.json exists but
  .claude/settings.json does not contain the UserPromptSubmit hook for
  suggest_iterate.py, install it now (one-time, idempotent)."` is gone
  from every plugin SKILL.md it appears in
  (`shipwright-build`, `shipwright-changelog`, `shipwright-deploy`,
  `shipwright-design`, `shipwright-plan`, `shipwright-project`,
  `shipwright-test`). Anyone reading those plugins' SKILL.md no longer
  reaches a step that routes them to the retired installer.
- [ ] **AC-6 — Verbose copy-paste install snippets are removed.**
  - `plugins/shipwright-run/skills/run/SKILL.md` Step 4.5 (Install
    Phase-Router Hook) is removed in full and a one-line note replaces
    it: "Hook is registered in `shipwright-iterate` plugin's
    `hooks/hooks.json`; no project-level install needed."
  - The corresponding "Install phase-router hook" sub-step in
    `plugins/shipwright-project/skills/project/SKILL.md` is removed
    with the same one-line replacement.
- [ ] **AC-7 — `/shipwright-adopt` artifact list reflects the new
  reality.** `plugins/shipwright-adopt/skills/adopt/SKILL.md` no longer
  lists "the suggest_iterate hook" as part of the adopt scaffold
  contract (the corresponding bullet near "installs the suggest_iterate
  hook" is removed or rephrased to "no per-project hook install
  needed; hook is registered in shipwright-iterate plugin"), and the
  artifact-list bullet `6. .claude/settings.json with the suggest_iterate
  UserPromptSubmit hook (idempotent merge)` is removed.
- [ ] **AC-8 — Spec ACs are realigned.** The FR-01.13 / FR-01.02 /
  FR-01.01 acceptance criteria added by ADR-019 / ADR-020 (carrier-
  shape, quoted-path, upgrade-legacy-in-place) are marked obsolete:
  the relevant `(E) Given … when … then …` lines are either deleted
  or rewritten so they describe the new reality (plugin-level
  registration). FR-01.11 (`/shipwright-iterate`) gains a new AC that
  asserts ownership of the `UserPromptSubmit` hook: "given the plugin
  is enabled, every UserPromptSubmit in any project where
  `shipwright_run_config.json` exists fires `suggest_iterate.py`".
- [ ] **AC-9 — Local workaround in this monorepo is removed.** The
  hand-edited `UserPromptSubmit` entry in this repo's own
  `.claude/settings.json` (line 7-18 in the repo's settings.json,
  using `${CLAUDE_PROJECT_DIR}` form) is removed. After removal, the
  plugin-registered hook handles UserPromptSubmits for this monorepo
  too; manually triggering a UserPromptSubmit (any non-slash-command
  prompt) does not surface the Claude Code "hook is not associated
  with a plugin" error.
- [ ] **AC-10 — `docs/hooks-and-pipeline.md` is updated.** The hook
  registry section gains a row for `suggest_iterate.py` under the
  `shipwright-iterate` plugin's `UserPromptSubmit` registration, with
  a one-line description of intent routing. CLAUDE.md mandates this
  update for any hook change.
- [ ] **AC-11 — Round-trip boundary probe.** A new test asserts the
  end-to-end producer→file→consumer chain for the plugin-hook
  distribution: `plugins/shipwright-iterate/hooks/hooks.json` parses
  as JSON, contains a `UserPromptSubmit` key, the inner command
  string equals the canonical literal from AC-1, and a hand-rolled
  "execute this hooks.json by spawning the command via the host's
  shell, with `${CLAUDE_PLUGIN_ROOT}` set to a temp dir mirroring
  the cache layout (`plugin-cache/shipwright-iterate/<v>/` adjacent
  to `plugin-cache/shared/scripts/hooks/suggest_iterate.py` and
  `plugin-cache/plugins/shipwright-iterate/scripts/lib/`), and feeding
  a UserPromptSubmit-shaped JSON payload on stdin" round-trip exits
  0 and produces non-empty stdout / a valid JSON `hookSpecificOutput`
  payload when the prompt matches a routing pattern. The test fixture
  uses a tightly-controlled environment (no host-leaking env vars)
  per external-review-finding-10 to avoid masking quoting issues.

- [ ] **AC-12 — Legacy-entry cleanup guidance is shipped to users.**
  The replacement one-line note in
  `plugins/shipwright-run/skills/run/SKILL.md` (formerly Step 4.5)
  AND in `plugins/shipwright-project/skills/project/SKILL.md`
  (formerly the "Install phase-router hook" sub-step) AND in
  `plugins/shipwright-adopt/skills/adopt/SKILL.md` (artifact list +
  scaffold contract) explicitly tells users with a previously-adopted
  project how to remove the dead `${CLAUDE_PLUGIN_ROOT}`-referencing
  legacy entry from their project's `.claude/settings.json` —
  precise JSON path, example diff, and the trigger-symptom (the
  Claude Code "hook is not associated with a plugin" error). Without
  this, adopted projects continue to surface that red-banner error
  even after the plugin-hook starts firing alongside the broken
  legacy entry. A one-shot cleanup verb is explicitly out-of-scope
  for this iterate (Sven's scope decision 2026-05-05).

- [ ] **AC-13 — Cache-vs-source verification.** A separate test
  in `plugins/shipwright-iterate/tests/` runs
  `bash scripts/update-marketplace.sh` (or skips with explicit reason
  if the dev environment cannot run the sync), then inspects the
  cache directory layout to assert that the canonical command
  literal from AC-1 resolves to a real file under
  `~/.claude/plugins/cache/shipwright/shared/scripts/hooks/suggest_iterate.py`
  AND that `plugins/shipwright-iterate/scripts/lib/classify_intent.py`
  is reachable from the cache copy via the script's
  `parent.parent.parent.parent` arithmetic. This catches packaging
  drift independent of the source-tree round-trip in AC-11.

## Out of Scope

- `${CLAUDE_PLUGIN_ROOT}` quoting in `plugins/*/hooks/hooks.json`
  bodies — already fixed in ADR-022 (separate iterate
  `iterate/hooks-json-quoting`). This iterate touches the
  `shipwright-iterate` plugin's hooks.json only to ADD a new entry; the
  existing entries in that file already use the quoted form.
- Removing `${CLAUDE_PROJECT_DIR}` quoting fixes elsewhere — the bug
  report mentioned both, but the only failure surface today is the
  plugin-context misuse in project settings.json. `CLAUDE_PROJECT_DIR`
  is consumed inside Python where shell quoting does not apply.
- Re-pointing the dev-vs-cache invariant (the cache copy of
  `suggest_iterate.py` is what fires; the dev copy in the monorepo
  fires only after `update-marketplace.sh`). The existing
  `update-marketplace.sh` invariant in CLAUDE.md is unchanged. If a
  developer wants live edits to suggest_iterate.py to fire in the
  monorepo's own iterates, they must run the sync script — that's
  pre-existing behavior, not a regression.
- Auditing whether other Shipwright hooks have a similar plugin-
  context misuse. `audit_phase_quality_on_stop.py`,
  `track_tool_calls.py`, etc., already live inside plugin `hooks.json`
  files (verified via grep) — no other distribution channel uses
  `${CLAUDE_PLUGIN_ROOT}` outside plugin context.

## In-scope sweep (Category B)

The 7 plugin SKILL.md files carrying the "Hook auto-install" stanza
all share the same one-sentence text. A single sweep removes each
copy. No prose change beyond the deletion (the surrounding
`invocation_mode` paragraph stays).

## Affected FRs

- **FR-01.11** (`/shipwright-iterate`): plugin gains formal ownership
  of the `UserPromptSubmit` hook; new AC documents the invariant.
- **FR-01.13** (`/shipwright-adopt`): per-project hook install is
  removed from the scaffold contract; ADR-019/020 ACs become obsolete.
- **FR-01.02** (`/shipwright-project`): documented install snippet is
  removed; ADR-019/020 documentation-parity AC becomes obsolete.
- **FR-01.01** (`/shipwright-run`): same as FR-01.02 — install
  snippet removed.

## Affected Boundaries

The hook is itself a boundary primitive. Both producer/consumer pairs
covered:

| Producer (writes)                              | Consumer (reads)                | Format            |
|---|---|---|
| this iterate writes plugin hooks.json (UserPromptSubmit entry) | Claude Code at session start (loads hooks/hooks.json) | JSON                                          |
| this iterate REMOVES `.claude/settings.json` UserPromptSubmit entry from monorepo (AC-9) | Claude Code at session start                          | JSON                                          |
| Claude Code at runtime (spawns hook with stdin payload) | `suggest_iterate.py` (reads stdin) | JSON-on-stdin (UserPromptSubmit hook payload) |

Round-trip test (AC-11) covers the third row.

## Confidence Calibration

(Populated before F0 Fresh Verification Gate per SKILL.md Step 7.5.
Mandatory at medium per Phase Matrix; also Safety-enforced because
`touches_io_boundary` fires.)

- **Boundaries touched:** three producer/consumer pairs from
  "Affected Boundaries":
  1. iterate-run → `plugins/shipwright-iterate/hooks/hooks.json`
     → Claude Code at session start.
  2. iterate-run REMOVES monorepo `.claude/settings.json`
     UserPromptSubmit block → Claude Code at session start.
  3. Claude Code at runtime → `suggest_iterate.py` (JSON-on-stdin).

- **Empirical probes run:**
  1. Pre-build: 5 probes against plan premises (cache layout exists,
     existing 5 hooks already use the same `${CLAUDE_PLUGIN_ROOT}/
     ../../shared/...` pattern, `readlink -f` resolves to
     `cache/shared/scripts/hooks`, `parent.parent.parent.parent`
     reaches `classify_intent.py`, plugin hooks get target-project
     CWD via `os.getcwd()`). All clean (one false-positive from MSYS
     path-mangling resolved on re-probe).
  2. Build: `test_user_prompt_submit_uses_canonical_command`
     verified literal byte-for-byte equality.
  3. Build: `test_round_trip_routing_match_emits_additional_context`
     spawned canonical command via `uv run --no-project` against a
     fake-cache-layout fixture; got exit 0 + JSON
     `hookSpecificOutput`.
  4. Build: 4 negative-path round-trip tests (non-Shipwright project,
     slash command, short prompt, malformed stdin) all exit 0 silent
     — proves Guards 1/3/4 + JSONDecodeError handler intact.
  5. Build: `test_no_unquoted_plugin_root_in_any_hook_command` —
     drift guard against ADR-022 quoting regression.
  6. Build: `test_cache_layout_resolves_canonical_command_target` —
     skipped when no cache present (CI default), ran locally and
     confirmed the live cache exposes both
     `cache/shared/scripts/hooks/suggest_iterate.py` AND
     `cache/plugins/shipwright-iterate/scripts/lib/classify_intent.py`.
  7. Verifier-test suite (8/8) green after A6 removal.
  8. Adopt-pipeline subprocess test asserts `.claude/settings.json`
     is NOT written — round-trip from generator to filesystem.

- **Edge cases NOT probed + why acceptable:**
  - **Plugin disable triggers no-hook-fired** — claim, not test.
    Acceptable: Claude Code's enabledPlugins enforcement is the
    framework's responsibility, not ours; any test we wrote would
    have to mock Claude Code itself.
  - **Coexistence of legacy project-level entry + new plugin entry**
    — documented in Risks but not unit-tested. Acceptable:
    empirically observed in this very session (the user saw the
    Claude-Code-error-on-broken-entry alongside other hooks
    continuing to function); writing a test would require
    instantiating Claude Code's hook host. Mitigated by AC-12
    cleanup snippet.
  - **Marketplace sync of new hooks.json into runtime cache** —
    deferred to F11 post-push, since `update-marketplace.sh` pulls
    from GitHub and pre-push the cache stays at the old version.
    Acceptable: no production user is consuming the un-pushed
    branch. Self-review notes this as a known order constraint.

- **Confidence-pattern check:** Sven asked "bist du confident?"
  earlier. I refused self-attestation and ran 5 probes — none
  produced findings. External review later produced 12 findings;
  I addressed HIGH-1 (spec/mini-plan drift, fixed by mini-plan
  edit) and added AC-11/12/13 to operationalize the rest.
  HIGH-2 (legacy-entry coexistence) became spec Risks +
  AC-12 cleanup. No yes-then-bug pattern fired in the build phase
  (`%SystemDrive%` test-side artifact was caught by self-inspection
  of git status, not by a probe — but caught nonetheless and
  forward-fixed by env-var harden + .gitignore). Asymptote
  stopping rule met: most recent build-time probe (the test
  re-run after env-fix) returned no finding, all categories
  applicable to the format covered.

## Relationship to ADR-019 + ADR-020

This iterate **supersedes** the install-into-project-settings.json
premise that ADR-019 + ADR-020 were patching. ADR-019 fixed the
carrier shape. ADR-020 fixed the command literal. Both stayed within
the project-level installer model and so neither could fix the
underlying plugin-context-only variable expansion. This iterate
retires the installer entirely; the carrier-shape and command-literal
fixes survive verbatim in the new plugin hooks.json registration
(Shape B matcher-group + quoted + `--no-project`), they just live in
the plugin instead of the per-project settings.json.

## Test Strategy

- **Delete `plugins/shipwright-adopt/tests/test_hook_installer.py`.**
  All 11 tests in that file assert behavior of a module that no
  longer exists. Verify the rest of the adopt test suite still passes
  after deletion.
- **Delete the hook installer call in `generate_adoption_artifacts.py`
  AND its import.** Add a test asserting that the adopt scaffold no
  longer touches `.claude/settings.json` UserPromptSubmit entries.
- **New test in `plugins/shipwright-iterate/tests/`**: assert that
  `plugins/shipwright-iterate/hooks/hooks.json` contains a
  `UserPromptSubmit` entry with the canonical Shape-B + quoted +
  `--no-project` command literal.
- **Boundary round-trip test (AC-11):** spawn the hook command with
  a stub `${CLAUDE_PLUGIN_ROOT}` and a UserPromptSubmit-shaped JSON
  payload. Assert exit 0 + (when prompt matches a pattern) a parseable
  JSON `hookSpecificOutput`.
- **Regression test for verifier A6:** if A6 is rewritten, add a test
  for the new invariant. If A6 is removed, update the verifier test
  suite to assert it no longer runs.
- **Smoke test (manual, recorded in self-review):** in this monorepo,
  remove the local `${CLAUDE_PROJECT_DIR}` workaround from
  `.claude/settings.json`, run `bash scripts/update-marketplace.sh`,
  start a fresh Claude Code session, and confirm `suggest_iterate.py`
  fires for a non-slash-command UserPromptSubmit (look for
  `[Shipwright] Detected:` in additionalContext) AND no
  "hook not associated with a plugin" error appears.
- **Full pytest suite** (`uv sync && uv run pytest` from repo root +
  each plugin) — medium complexity → full suite per Phase Matrix.
- **External LLM Review** at Step 4 (medium → auto).

## Risks

- **Plugin-cache staleness on dev side.** After this iterate ships,
  the plugin-hook only fires from the cache copy. Live edits to
  `suggest_iterate.py` in the monorepo do NOT take effect until
  `update-marketplace.sh` runs. The CLAUDE.md rule already mandates
  this; nothing new — but the local-workaround removal closes one of
  the previous safety nets. Mitigate by adding a one-line note to
  CLAUDE.md's "When editing plugin-side files" section explicitly
  calling out the suggest_iterate hook as an example.
- **Adopted projects with the legacy hook entry remain dirty.** This
  iterate stops writing the entry going forward but does NOT
  retroactively remove existing legacy entries in already-adopted
  target projects. Those projects continue to produce the Claude
  Code "hook not associated with a plugin" error until manually
  cleaned up, OR the plugin re-runs adopt-style cleanup. Mitigate
  by documenting the manual cleanup step in the SKILL.md replacement
  one-liner: "If your project has an old UserPromptSubmit entry from
  a pre-{this version} adopt run, delete it from `.claude/settings.json`."
  Optional follow-up iterate could add a one-shot cleanup verb.
- **Plugin not enabled = no hook fires.** If a user disables
  `shipwright-iterate@shipwright` in their `~/.claude/settings.json`
  `enabledPlugins` map, the hook stops firing for that user
  globally. That is the intended semantics — they opted out of the
  plugin — but it differs from the per-project model where disabling
  the plugin still left the hook entry in place (running a stale,
  dangling command). The new model is cleaner; the spec's FR-01.11
  AC documents the invariant. **Prerequisite documented in
  installation guide (docs/guide.md §2):** users adopting Shipwright
  must enable `shipwright-iterate@shipwright` (the marketplace install
  flow does this automatically; confirm if onboarding manually).
- **Coexistence with legacy project-level entry (HIGH-2 from
  external review).** When a previously-adopted target project still
  carries the `${CLAUDE_PLUGIN_ROOT}`-referencing legacy entry in
  `.claude/settings.json` AND the new plugin-hook is registered via
  this iterate, both hooks register against `UserPromptSubmit`.
  Empirically (the user observed this exact error mid-session
  before this iterate started), Claude Code surfaces the
  "hook is not associated with a plugin" error for the broken
  project-level entry but does NOT short-circuit other registered
  hooks for the same event — meaning the plugin-hook still fires
  correctly. Net effect on adopted projects: red-banner error
  noise persists, but routing functionality is restored. AC-12
  ships precise cleanup guidance to users so they can delete the
  dead legacy entry without further code churn.
