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

**The `phaseTaskId` the orchestrator hands you at dispatch is the authority** — NOT any
state field inside `shipwright_run_config.json`. The pipeline's v1 state fields are no
longer advanced, so keying on them made every driven phase past the first misclassify
itself as standalone; the rationale is in `shared/scripts/lib/phase_invocation_mode.py`.
**Never re-derive the mode yourself.** Ask the resolver:

```bash
uv run "{shared_root}/scripts/tools/get_phase_context.py" \
  --phase-task-id "{phaseTaskId}" --phase changelog --project-root "{project_root}"
```

Omit `--phase-task-id` if you were not handed one. Set `invocation_mode` from the returned
`mode`, which is exactly one of:

- **`pipeline`** — you were dispatched. Enforce gates, and do the phase's real work.
  **Do NOT call `orchestrator.py update-step`** (nor any other run-state write): in a
  driven run `single-session-apply` owns phase completion — it records your status when
  it applies your result. See `plugins/shipwright-run/skills/run/SKILL.md`. (`update-step`
  is inert in a driven run anyway, but do not rely on that.)
- **`standalone`** — no token, so this is a hand-invoked run (the normal case for a
  release: `/shipwright-changelog` is usually invoked by hand):
  - Skip pipeline state updates (no `orchestrator.py update-step` calls)
  - Still produce all artifacts (`CHANGELOG.md`, version tags, PRs)
  - Print: `"Running in standalone mode — pipeline state will not be updated."`
  - If `requires_out_of_sequence_warning` is `true`, a driven run is LIVE at
    `active_phases`. Warn that cutting a release out-of-band may collide with it, and
    **ask the user before continuing**. (The `changelog` phase has no cataloged gate id yet
    — it is a tracked `pending_phases` follow-up in `shared/config/gate_catalog.json` — so
    ask interactively rather than resolving a gate policy.)
- **`error`** (exit code 2) — you were dispatched but the token does not resolve (stale,
  terminal, wrong phase, or an unreadable config). **STOP.** Do NOT continue as
  standalone: that is precisely what stamps a driven run's artifacts `"mode": "standalone"`
  and deadlocks the pipeline. Surface it to the orchestrator as an `ok: false` result.

### D. Run Setup Script

```bash
uv run "{plugin_root}/scripts/checks/setup-changelog.py" \
  --plugin-root "{plugin_root}"
```

Parse JSON output for git state, last tag, and unreleased commits.

---

## Step 0: Phase Session Context Recovery

If the orchestrator handed you a `phaseTaskId`, the `get_phase_context.py` call you
already made in **Detect Invocation Mode** is the one this step needs — reuse that
payload and read its `skill_artifacts_to_read` list before proceeding. No
`phaseTaskId` → standalone; continue with Step 1.

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
uv run "{plugin_root}/scripts/lib/git_utils.py" parse-commits \
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

Since the file-per-iterate refactor, iterate F4 writes one Markdown file
per bullet under `CHANGELOG-unreleased.d/<category>/`. Release time
reads those drop files, renders a versioned Keep-a-Changelog section,
inserts it at the structural point in `CHANGELOG.md` (above the first
existing `## [version]` heading, NOT blindly at the top — that would
corrupt the `# Changelog` title), and deletes only the drop files that
were actually aggregated.

```bash
uv run "{shared_root}/scripts/tools/aggregate_changelog.py" \
  --project-root "{project_root}" \
  --version "{version}" \
  [--release-date "{YYYY-MM-DD}"] \
  [--dry-run]
```

Use `--dry-run` first to preview the rendered section without modifying
disk. When the aggregator encounters legacy bullets under
`## [Unreleased]` (e.g. from pre-refactor iterates that wrote directly
to `CHANGELOG.md`), it prints a **loud stderr WARNING** with the count.
Those bullets are NOT migrated automatically — the operator chooses
whether to fold them into the new version manually or accept the
split-brain.

**Re-running a release is safe.** The changelog is written before the
drop files are consumed, so an interruption in that window leaves the
section written and the drops still pending. Running the same version
again **replaces** that section rather than adding a second one — but
only when what is on record is still what the drops say. Otherwise it
**stops with a non-zero exit** and names the disagreement, changing
neither `CHANGELOG.md` nor any drop file. That is a prompt to reconcile
by hand, not a transient error to retry.

`changelog_updated` means *bytes were written*, not *the run succeeded*:
a converging re-run reports `"section_action": "unchanged"` with
`"changelog_updated": false` and is a **success**. See
[rerunning-a-release.md](references/rerunning-a-release.md) for the full
state table, the `--release-date` rule, and why it refuses instead of
overwriting.

### ADR decision-drops

Iterate F3 no longer appends ADRs directly to `decision_log.md`. Since
the unconditional-worktree refactor it writes one JSON drop per ADR
under `.shipwright/agent_docs/decision-drops/`, keyed by run_id. Release
time is the ONE serialized point that assigns the sequential `ADR-NNN`,
so two parallel iterates can never claim the same number:

```bash
uv run "{shared_root}/scripts/tools/aggregate_decisions.py" \
  --project-root "{project_root}" \
  [--dry-run]
```

It renders each drop into `decision_log.md` (continuing the ADR
numbering), embeds a `Run-ID:` line for run-id ↔ ADR traceability, and
deletes only the drops it aggregated. Run with `--dry-run` first to
preview the numbers that will be assigned. Drops written after the
snapshot survive into the next release.

Fallback for non-iterate commits: if this release includes bullets that
weren't produced through iterate F4 (rare — e.g. a cherry-pick from an
unrelated branch), write them with `append_changelog_entry.py` BEFORE
running the aggregator; they land in the legacy `[Unreleased]` block
and surface as a warning at aggregation time.

See [changelog-format.md](references/changelog-format.md) for output
format details.

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

## Step 5.5: Refresh the Compliance Evidence Documents

The seven documents under `.shipwright/compliance/` ship *with* the release
instead of standing frozen. Why, and every refusal: [compliance-evidence.md](references/compliance-evidence.md).

```bash
uv run "{shared_root}/scripts/tools/refresh_compliance_docs.py" \
  --project-root "$(pwd)" --stage --release "v{version}"
```

`status: "ok"` → proceed. **Anything else → stop, do not tag.**

## Step 6: Commit and Tag

Commit **by explicit pathspec** — never `.shipwright/compliance/`, which commits
every tracked file under it and widens the pinned seven. Use Step 5.5's
`evidence_pathspec`: it omits any path this project lacks, and a pathspec matching
no file aborts the whole commit.

```bash
git add CHANGELOG.md
git add .shipwright/agent_docs/decision_log.md .shipwright/agent_docs/decision_log_index.md  # if Step 4 folded/refreshed
git add .shipwright/planning/adr/                         # if dirty - see below
git commit -m "chore(release): v{version}" -- \
  CHANGELOG.md .shipwright/agent_docs/decision_log.md .shipwright/agent_docs/decision_log_index.md \
  .shipwright/planning/adr/ <every path from evidence_pathspec>
git tag -a v{version} -m "Release v{version}"

# `git commit -- <paths>` records the WORKTREE, not the index: a writer between
# Step 5.5 and here substitutes unstamped bytes silently. Non-zero → do not tag.
uv run "{shared_root}/scripts/tools/refresh_compliance_docs.py" \
  --project-root "$(pwd)" --verify-commit "$(git rev-parse HEAD)"
```

> `.shipwright/planning/adr/` is a DIRECTORY pathspec deliberately, and leaving it unstaged breaks CI — both in [compliance-evidence.md](references/compliance-evidence.md). `decision_log_index.md` needs the same treatment (Step 4 refreshes it every non-dry-run pass, drops or not) — leaving it unstaged reds `test_decision_log_index_producers.py::test_committed_index_is_not_stale` on main.

---

## Step 7: Create PR (Optional)

**Only if on a feature branch** (not main/develop).

```bash
gh pr create \
  --title "Release v{version}" \
  --body "## Changelog\n\n{entry}" \
  --base main
```

> **Parallel iterates:** rebase-per-PR is expected, tagging is single-writer,
> and `CHANGELOG.md [Unreleased]` is the one merge hotspot. Detail:
> [release-workflow.md](references/release-workflow.md); full conventions live
> in `/shipwright-iterate` B1a.

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
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" \
  --type phase_completed \
  --phase changelog \
  --detail "v{version} — {PR_URL}"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

If no PR was created (on main), use `--detail "v{version} — tagged on main"`.

**Phase complete — update pipeline state:**

Canon C1/C2/C3 only — C4 and C5 are deliberately out; why:
[release-workflow.md](references/release-workflow.md).

```bash
: "${SHIPWRIGHT_RUN_ID:=changelog-v{version}-$(date +%Y%m%d-%H%M%S)}"
export SHIPWRIGHT_RUN_ID

# C1 — already emitted as the phase_completed event above.

# C2 — delivery dashboard
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase changelog --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.4) — canon-marker handoff
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase changelog \
  --reason "release v{version}"

# C4 — SKIPPED by policy.
# C5 — n/a (this plugin prepends the released version block; adding a
#      new [Unreleased] bullet would collide with the next release).

# phase_history (NEW 12.4)
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase changelog --run-id "$SHIPWRIGHT_RUN_ID" \
  --entry-json '{"version":"v{version}","outcome":"tagged"}'

# Mark changelog phase complete (triggers compliance update automatically).
# _validate_changelog() now runs test_checks + the new check_git_tag_exists
# and check_changelog_version_matches_tag Sonder-Checks, so a broken tag
# push or a CHANGELOG drift blocks this call.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step changelog --status complete

# update-step regenerates the seven evidence documents a SECOND time — unstamped,
# at a different commit than the one just tagged. Put the committed copies back.
uv run "{shared_root}/scripts/tools/refresh_compliance_docs.py" \
  --project-root "$(pwd)" --restore
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
- [compliance-evidence.md](references/compliance-evidence.md) — The seven evidence documents at release
- [release-workflow.md](references/release-workflow.md) — Parallel iterates; why the canon stops at C3
