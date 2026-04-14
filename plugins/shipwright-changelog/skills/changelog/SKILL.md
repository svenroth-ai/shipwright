---
name: shipwright-changelog
description: "Parses Conventional Commits from git history, generates Keep-a-Changelog entries, creates version tags, and opens PRs.\nTRIGGER when: user wants to create a changelog, generate release notes, tag a version, create a release, bump version number, create a PR for release, or review unreleased changes.\nDO NOT TRIGGER when: user asks to write code (/shipwright-build), run tests (/shipwright-test), fix a bug (/shipwright-iterate), deploy (/shipwright-deploy), create requirements (/shipwright-project), plan implementation (/shipwright-plan), or design UI (/shipwright-design)."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required, gh CLI for PR creation
---

# Shipwright Changelog Skill

Generates changelogs from Conventional Commits and manages release workflow.

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-CHANGELOG: Release Management
================================================================================
Analyzes git history, generates changelog, creates PR.

Usage: /shipwright-changelog
   or: /shipwright-changelog --from v0.1.0
   or: Invoked by /shipwright-run (orchestrator)

Steps:
  1. Analyze commits since last tag
  2. Categorize by Conventional Commits type
  3. Generate changelog entry
  4. Preview and confirm with user
  5. Commit changelog + create tag
  6. Create PR (if feature branches exist)
================================================================================
```

### B. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>`. Use it directly.

### C. Detect Invocation Mode

Determine if running within the pipeline or standalone:

1. Read `shipwright_run_config.json` (if exists)
2. **Pipeline mode**: `status == "in_progress"` AND `current_step == "changelog"`
   - Full pipeline integration (update orchestrator state, enforce gates)
3. **Standalone mode**: file missing OR `status == "complete"` OR `current_step != "changelog"`
   - Skip pipeline state updates (no `orchestrator.py update-step` calls)
   - Still produce all artifacts (`CHANGELOG.md`, version tags, PRs)
   - Print: `"Running in standalone mode — pipeline state will not be updated."`
4. If `status == "in_progress"` AND `current_step != "changelog"`:
   - Warn: `"Pipeline is in progress at step {current_step}. Running /shipwright-changelog out of sequence may cause issues."`
   - Ask user before continuing.

**Hook auto-install**: If `shipwright_run_config.json` exists but `.claude/settings.json` does not contain the `UserPromptSubmit` hook for `suggest_iterate.py`, install it now (one-time, idempotent).

Store the detected mode in a variable `invocation_mode` = `"pipeline"` | `"standalone"` for use in later steps.

### D. Run Setup Script

```bash
uv run {plugin_root}/scripts/checks/setup-changelog.py \
  --plugin-root "{plugin_root}"
```

Parse JSON output for git state, last tag, and unreleased commits.

---

## Step 1: Analyze Git History

**Goal:** Collect all commits since the last version tag.

The setup script returns:
- `last_tag` — most recent semver tag (or null if none)
- `commits_since_tag` — list of commit messages + hashes
- `branch` — current branch name

If no commits since last tag: print "No unreleased changes" and stop.

---

## Step 2: Categorize Commits

See [conventional-commits.md](references/conventional-commits.md) for parsing rules.

**Goal:** Parse each commit message into type, scope, and description.

```bash
uv run {plugin_root}/scripts/lib/git_utils.py parse-commits \
  --since "{last_tag}" \
  --format json
```

Categories:
| Type | Changelog Section |
|------|------------------|
| `feat` | Added |
| `fix` | Fixed |
| `refactor` | Changed |
| `docs` | Documentation |
| `test` | Testing |
| `chore` | Maintenance |
| `BREAKING CHANGE` | Breaking Changes |

---

## Step 3: Determine Version Bump

**Goal:** Suggest next version based on commit types.

Rules:
- `BREAKING CHANGE` in any commit → **major** bump
- Any `feat` → **minor** bump
- Only `fix`, `refactor`, `docs`, etc. → **patch** bump

If no previous tag exists: suggest `v0.1.0`.

**Autonomous mode** (check `autonomy` in `shipwright_run_config.json`):
Accept the suggested version automatically. No prompt.

**Guided mode** (default):
Present suggestion to user:
```
Suggested version: v{X.Y.Z} (based on: {reason})
Accept or enter custom version:
```

---

## Step 4: Generate Changelog Entry

See [changelog-format.md](references/changelog-format.md) for output format.

```bash
uv run {plugin_root}/scripts/lib/changelog.py generate \
  --version "{version}" \
  --commits-json "{commits_json_path}" \
  --changelog-path "CHANGELOG.md"
```

This prepends the new entry to CHANGELOG.md (or creates it if missing).

---

## Step 5: Preview and Confirm

**Goal:** Show the generated changelog entry to the user.

**Autonomous mode** (check `autonomy` in `shipwright_run_config.json`):
Skip preview confirmation. Proceed directly to Step 6.

**Guided mode** (default):
Present the full entry and ask:
```
AskUserQuestion:
  question: "Review the changelog entry. Proceed?"
  options:
    - Accept
    - Edit (describe changes)
    - Cancel
```

If edit: apply changes and re-preview.

---

## Step 6: Commit and Tag

```bash
git add CHANGELOG.md
git commit -m "chore(release): v{version}"
git tag -a v{version} -m "Release v{version}"
```

---

## Step 7: Create PR (Optional)

**Only if on a feature branch** (not main/develop).

```bash
gh pr create \
  --title "Release v{version}" \
  --body "## Changelog\n\n{entry}" \
  --base main
```

**Autonomous mode:** After creating the PR, merge it immediately:
```bash
gh pr merge --merge --delete-branch
```

**Guided mode:** PR stays open for manual review and merge.

If already on main: skip PR, just push tag.

**Push tags and updated main to remote:**
```bash
git push --tags origin main
```

**Record changelog event** (captures version and PR URL for downstream consumers):
```bash
uv run {shared_root}/scripts/tools/record_event.py \
  --project-root "$(pwd)" \
  --type phase_completed \
  --phase changelog \
  --detail "v{version} — {PR_URL}"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

If no PR was created (on main), use `--detail "v{version} — tagged on main"`.

**Phase complete — update pipeline state:**

Iterate 12.4 wires the changelog plugin into the Minimum Phase
Completion Canon at C1/C2/C3 only. **C4 is skipped by policy** —
release tagging is process management, not an architectural decision.
**C5 is not applicable** — this plugin IS the one that writes
`[Unreleased]` prepends; appending to `[Unreleased]` after a release
would pollute the next version.

```bash
: "${SHIPWRIGHT_RUN_ID:=changelog-v{version}-$(date +%Y%m%d-%H%M%S)}"
export SHIPWRIGHT_RUN_ID

# C1 — already emitted as the phase_completed event above.

# C2 — delivery dashboard
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --phase changelog --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.4) — canon-marker handoff
uv run {shared_root}/scripts/tools/generate_session_handoff.py \
  --project-root "$(pwd)" --canon-marker --phase changelog \
  --reason "release v{version}"

# C4 — SKIPPED by policy.
# C5 — n/a (this plugin prepends the released version block; adding a
#      new [Unreleased] bullet would collide with the next release).

# phase_history (NEW 12.4)
uv run {shared_root}/scripts/tools/append_phase_history.py \
  --project-root "$(pwd)" --phase changelog --run-id "$SHIPWRIGHT_RUN_ID" \
  --entry-json '{"version":"v{version}","outcome":"tagged"}'

# Mark changelog phase complete (triggers compliance update automatically).
# _validate_changelog() now runs test_checks + the new check_git_tag_exists
# and check_changelog_version_matches_tag Sonder-Checks, so a broken tag
# push or a CHANGELOG drift blocks this call.
uv run {plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py \
  update-step --project-root "$(pwd)" --step changelog --status complete
```

**Print Summary:**
```
================================================================================
SHIPWRIGHT-CHANGELOG COMPLETE
================================================================================
Version:    v{version}
Commits:    {N} categorized
Changelog:  CHANGELOG.md updated
Tag:        v{version} created
PR:         {PR_URL | "skipped (on main)"}

Tags + main pushed to origin
================================================================================
```

---

## Reference Documents

- [conventional-commits.md](references/conventional-commits.md) — Parsing rules
- [changelog-format.md](references/changelog-format.md) — Keep-a-Changelog format
