---
name: changelog
description: Parses Conventional Commits from git history, generates Keep-a-Changelog entries, creates version tags, and opens PRs. Use after /shipwright-build completes all sections.
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required, gh CLI for PR creation
---

# Shipwright Changelog Skill

Generates changelogs from Conventional Commits and manages release workflow.

---

## CRITICAL: First Actions

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

### C. Run Setup Script

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

If already on main: skip PR, just push tag.

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

Next: git push --tags origin main
================================================================================
```

---

## Reference Documents

- [conventional-commits.md](references/conventional-commits.md) — Parsing rules
- [changelog-format.md](references/changelog-format.md) — Keep-a-Changelog format
