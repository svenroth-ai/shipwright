---
name: shipwright-changelog
description: "Parses Conventional Commits from git history, generates Keep-a-Changelog entries, creates version tags, and opens PRs.\nTRIGGER when: user wants to create a changelog, generate release notes, tag a version, create a release, bump version number, create a PR for release, or review unreleased changes.\nDO NOT TRIGGER when: user asks to write code (/shipwright-build), run tests (/shipwright-test), fix a bug (/shipwright-iterate), deploy (/shipwright-deploy), create requirements (/shipwright-project), plan implementation (/shipwright-plan), or design UI (/shipwright-design)."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required, gh CLI for PR creation and best-effort GitHub Release publishing
---

# Shipwright Changelog Skill

Generates changelogs from Conventional Commits and manages release workflow.

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

### A, B, D, Steps 0-2. Prepare: one call

The intro banner, the plugin root, the mode check, the setup script, the history and the commit types run in one call.
`{plugin_root}` is the `SHIPWRIGHT_PLUGIN_ROOT` the SessionStart hook injects.

```bash
uv run "{plugin_root}/scripts/release.py" prepare --project-root "$(pwd)" --phase-task-id "{phaseTaskId}"
```

Omit `--phase-task-id` if you were not handed one; add `--version "{X.Y.Z}"` only for a custom version an operator typed
(Step 3). The banner and the notices (`notices`) go to stderr: show them.
The JSON on stdout is the answer:

- `status` is `ok`, or `stop` with a `reason`: `mode_error` (see C), `setup_refused`, `gate_catalog_unavailable`, or
  `no_unreleased_changes` ("No unreleased changes"), or another reason it names (`parse_commits_failed`, `no_version`, `version_not_above_last_tag`, `upgrade_notes_query_failed`, `upgrade_note_drop_failed`). Report a stop and end the release.
- `mode`, `last_tag`, `branch`, `commits_since_tag`, `commits` (Steps 1-2), `version`, `suggested`, `version_reason` (Step 3).
  `trunk` (the remote's default branch, the PR base; `trunk_source`: `remote`, `local` or `fallback`) and `on_trunk` (Step 7).
  `previous_tag_has_release` is advisory, never a gate; its notice is already in `notices`.
- `gates`: what each question does (`version`, `preview`, `out_of_sequence`), `auto` or `ask`. **Do what `gates` says.** The
  rule behind it lives in the gate catalog, not here; the contract: [first-actions](references/first-actions.md).
- `release`: the date and the run id, stored once in `release_run.json` in the checkout's git directory. Every later call reads them:
  pass no date, export no run id.
- `upgrade_notes`: the upgrade-notes check of Step 4, already done.
- `skill_artifacts_to_read` (Step 0): with a `phaseTaskId`, read that list before going on.

### C. Detect Invocation Mode

**The `phaseTaskId` the orchestrator hands you at dispatch is the authority** — NOT any
state field inside `shipwright_run_config.json`; the rationale is in `shared/scripts/lib/phase_invocation_mode.py`.
**Never re-derive the mode yourself.** `prepare` asks the resolver
(`get_phase_context.py --phase-task-id "{phaseTaskId}" --phase changelog`). Set `invocation_mode` from the returned
`mode`, which is exactly one of:

- **`pipeline`** — you were dispatched. Enforce gates (Single-Session Gate Discipline: [first-actions](references/first-actions.md)), and do the phase's real work.
  Write no run state yourself: `close-phase` (Step 7) writes the phase's canon records, and `single-session-apply` owns
  phase completion (`plugins/shipwright-run/skills/run/SKILL.md`).
- **`standalone`** — no token, so this is a hand-invoked run (the normal case for a
  release: `/shipwright-changelog` is usually invoked by hand):
  - Write no pipeline state (`close-phase` writes none in this mode)
  - Still produce all artifacts (`CHANGELOG.md`, version tags, PRs)
  - If `out_of_sequence_warning` is `true`, a driven run is LIVE at `active_phases`. Warn that
    cutting a release out-of-band may collide with it, then do what `gates.out_of_sequence` says.
- **`error`** (`prepare` exits 2, `reason: "mode_error"`) — you were dispatched but the token does not resolve (stale,
  terminal, wrong phase, or an unreadable config). **STOP.** Do NOT continue as
  standalone: that is precisely what stamps a driven run's artifacts `"mode": "standalone"`
  and deadlocks the pipeline. Surface it to the orchestrator as an `ok: false` result.

---

## Step 3: Determine Version Bump

Do NOT compute the bump yourself. `version` is the setup script's `suggested_version` used verbatim (`version_reason` says why);
it comes from `git_utils.suggest_version_bump`, which applies FR-01.09 AC04 (a breaking change
raises the first number, or the second before 1.0; a `feat` the second; anything
else the third; no previous tag → `0.1.0`). The tag is `v{version}`.

Then do what `gates.version` says. `auto`: accept the suggestion, no prompt. `ask`:
```
Suggested version: v{version} (based on: {version_reason})
Accept or enter custom version:
```
A custom version is the `{version}` of every later call: run `prepare` again with `--version "{X.Y.Z}"` first, so the stored date and run id belong to that version (a run state is keyed on the version).
A leading `v` is cut off; a version that is no SemVer number (exit 2) or not higher than the last tag (`version_not_above_last_tag`) is refused: ask again.

---

## Step 4: Generate Changelog Entry

The upgrade-notes check already ran inside `prepare`, in every mode, before any aggregator call, so a drop it adds is picked up by
this release. Read `upgrade_notes.status` and do what [release-workflow.md](references/release-workflow.md) says for it (Upgrade-notes check).

Preview first: this call writes nothing (no `CHANGELOG.md` change, no drop consumed, no ADR numbered); `aggregate` owns the flags and the release date:

```bash
uv run "{plugin_root}/scripts/release.py" aggregate --project-root "$(pwd)" --version "{version}" --dry-run
```

The real run comes only after Step 5. The command owns the aggregator's flags (an empty release is refused only by the real run): add none by hand.

A hand-written bullet under `## [Unreleased]` moves into the release, in the category of the `### Added` ... `### Security` heading
it sits under (`hand_written`; the preview marks it `(hand-written)`). One under no such heading stays: a **stderr WARNING names its
text** (`legacy_unreleased_bullet_texts`); fold it in by hand or leave it.

Re-running a release is safe: [rerunning-a-release.md](references/rerunning-a-release.md) has the state table, the `--release-date` rule and why a disagreement stops with a non-zero exit. `section_action: "unchanged"` is a success.

### ADR decision-drops

The real run then numbers the ADR drops itself (`aggregate_decisions.py`, `decisions` in the JSON): iterate F3 writes one JSON
drop per ADR under `.shipwright/agent_docs/decision-drops/`, keyed by run_id, and release time is the ONE serialized point that
assigns the sequential `ADR-NNN`, so two parallel iterates can never claim the same number. It renders each drop into
`decision_log.md`, embeds a `Run-ID:` line for run-id ↔ ADR traceability, and deletes only the drops it aggregated; drops written
after the snapshot survive into the next release. Pending bullet drops fold first: `references/bullet-folding.md`.

Fallback for non-iterate commits: if this release includes bullets that weren't produced through iterate F4 (rare — e.g. a
cherry-pick from an unrelated branch), hand each one to the real run as `--fallback-entry "<Category>:<text>"` (repeatable); it is
written as a drop file before the aggregator runs, so it lands in this release.

---

## Step 5: Preview and Confirm

Do what `gates.preview` says. `auto`: no question; run the real call below, then `sync` (Steps 5.3 to 5.5), then Step 6, in that order. `ask`:
present the preview's full entry (`section_preview`, with `decisions_preview`, `upgrade_notes_pending` and `fallback_pending`) and ask:
```
AskUserQuestion:
  question: "Review the changelog entry. Proceed?"
  options:
    - Accept
    - Edit (describe changes)
    - Cancel
```

- **Accept:** run the real call below (it writes `CHANGELOG.md`, consumes the drops and numbers the ADRs).
- **Edit:** change the pending entry's drop file under `CHANGELOG-unreleased.d/` (never `CHANGELOG.md`), run Step 4's preview again, ask again.
- **Cancel:** run `cancel` (second block) and end the release: it puts back any drop file an Edit changed (`restored`); tell the operator every
  path in `left` (a drop file new since `prepare`: kept, never deleted). The run record stays, so the release guard blocks a push of the trunk or a tag for this release for 48 hours or until `SHIPWRIGHT_RELEASE_GUARD=off`.

```bash
uv run "{plugin_root}/scripts/release.py" aggregate --project-root "$(pwd)" --version "{version}"
```

```bash
uv run "{plugin_root}/scripts/release.py" cancel --project-root "$(pwd)" --version "{version}"
```

---

## Step 5.3: Fold Old Event Files, then Sync Manifests and Evidence (Steps 5.3 to 5.5, one call)

One call, in this order (a worktree write must not land in the staging-to-commit gap Step 6 warns about):

```bash
uv run "{plugin_root}/scripts/release.py" sync --project-root "$(pwd)" --version "{version}"
```

It folds old per-run event files into `.shipwright/events/archive/` in a commit of their own (never blocks; `fold.status`: add at most ONE line
to the closing summary, [event-fold.md](references/event-fold.md)), then syncs every declared published-package manifest to this version
([manifest-sync.md](references/manifest-sync.md); no declared manifests is a no-op), then refreshes the seven compliance evidence
documents ([compliance-evidence.md](references/compliance-evidence.md)). `status: "ok"` → proceed. **Anything else — stop, do not tag**
(`reason`: `manifest_sync_failed` or `evidence_refresh_failed`; the JSON names each tool's own status). The pathspecs Step 6 commits are kept in the
run state: copy nothing.

## Step 6: Commit and Tag

```bash
uv run "{plugin_root}/scripts/release.py" commit-and-tag --project-root "$(pwd)" --version "{version}"
```

It commits **by explicit pathspec** (never `.shipwright/compliance/`, which would widen the pinned seven; `.shipwright/planning/adr/` and
`decision-drops/` are directory pathspecs on purpose, see [compliance-evidence.md](references/compliance-evidence.md)), then runs the release
audit (`--verify-commit --release-audit`) and the manifest `--verify-commit` against the committed `HEAD`, and only when every step exited 0
makes the annotated tag `v{version}` on that commit. It then checks that the tag exists and names this release and that the CHANGELOG's top
version is this release; a mismatch removes the tag again. It writes
`.shipwright/runtime/release_state.json` (version, release commit, checks passed).

`status: "ok"` → continue. **Anything else — stop; no tag was made** (`reason` names the step; an audit that could not even start, such as
`uv`/PyYAML unavailable, reads as environmental: re-run once the dependency resolves). Never edit the worktree between `sync` and this call.

---

## Step 7: Create PR (Optional)

**Only if on a feature branch:** prepare returned `on_trunk: false`.

Write the PR body (`## Changelog` and this version's section) to a file; pass its `body_file` on (a refusal stops the release):
```bash
uv run "{plugin_root}/scripts/release.py" pr-body --project-root "$(pwd)" --version "{version}"
```
Push the branch (the host opens a PR only for a branch it has; `--no-follow-tags` keeps the tag here even with `push.followTags`):
```bash
git push origin HEAD --no-follow-tags
```
A failed push stops the release here: the tag stays on this machine; report it.
```bash
gh pr create \
  --title "Release v{version}" \
  --body-file "{body_file}" \
  --base "{trunk}"
```

**A failed `gh pr create` stops the release here:** the tag stays on this machine; report it.

**Record the changelog event — BEFORE the merge, so it ships in the release PR** (an append after the merge strands uncommitted in the main
checkout: webui v0.28.0, monorepo v0.34.0). On a feature branch it commits only the event paths and pushes the head; on the trunk it commits and
never pushes (the trunk is pushed once, with the tag). A non-zero exit (a rejected push too) **stops the release**: the tag stays local.

```bash
uv run "{plugin_root}/scripts/release.py" record-event --project-root "$(pwd)" --version "{version}" --pr-url "{PR_URL}"
```

Omit `--pr-url` on the trunk.

**A hand-invoked release with autonomy `autonomous` or `unattended`:** after recording the event, merge immediately; a failed merge stops the release:
```bash
gh pr merge --merge --delete-branch
```

**Any other hand-invoked release:** the PR stays open for manual review and merge. The order is: run `close-phase` now with `--release-status waiting
--release-note "waits for the PR merge"` (last block of this step); then, **after the PR is merged**, push the tag and make the release
page (the next two blocks). Neither is done before the merge, so a failed release can never leave a tag with no release.

**A driven run** neither merges nor waits: the master owns the PR. Go straight on.

**Push the tag.** Ask first; the call decides and never pushes:
```bash
uv run "{plugin_root}/scripts/release.py" push-tag --project-root "$(pwd)" --version "{version}"
```
`status: "ok"` gives the one `line` to run: from a feature branch `git push origin "refs/tags/v{version}"` (only the tag, never a local trunk,
never `--tags`), on the trunk `git push --atomic origin {branch} "refs/tags/v{version}"` (`{branch}` is the branch you are on, a trunk: run the printed line; the trunk and exactly this tag, together or not at all).
Run that line as printed. `status: "waiting_for_merge"` (exit 1) means a hand-invoked release's PR is not merged yet: run `push-tag` again after the merge.
`reason: "merge_state_unknown"` is retryable (origin could not be asked: run `push-tag` again). `status: "refused"` otherwise stops the release and names the `reason` (`merged_without_release_commit`: the PR was merged without the release commit, so
the tag would name a commit that is not on the trunk; do not run it again, report it). A refused push stops the release.

**Create GitHub Release (best-effort, never blocks this phase):** what it publishes, the LLM/mechanical split and every reported
outcome: [release-workflow.md](references/release-workflow.md).
```bash
uv run "{shared_root}/scripts/tools/publish_release_notes.py" \
  --project-root "$(pwd)" --version "{version}"
```
Read `status` from the JSON: `ok`/`exists` (with `url`), `skipped`/`failed` (with `reason`, verbatim — never swallowed, never a hard stop). If
the command exits non-zero with no JSON (uv could not fetch the script's packages, e.g. offline), that is `skipped` with the stderr line.

**Phase complete:** one call writes the phase's canon records where a driven run needs them, verifies the release read-only and prints the
closing summary (stderr). Pass what the release page step reported; in a release that waits for the merge this call comes first, with `--release-status waiting
--release-note "waits for the PR merge"`.

```bash
uv run "{plugin_root}/scripts/release.py" close-phase --project-root "$(pwd)" --version "{version}" --session-id "{SHIPWRIGHT_SESSION_ID}" \
  --release-status "{ok|exists|skipped|failed|waiting}" --release-url "{url}" --release-note "{reason}"
```

In a driven run it writes C2/C3 (with `--canon-marker --phase changelog`) and the `phase_history` entry the master's gate reads; in a hand-invoked
release it writes nothing and restores every derived snapshot to `HEAD`, so the tree is clean. `status: "ok"`
means every `verify` check passed (tag local and on origin, CHANGELOG matches the tag, event committed, no decision drops left, PR state fits
the mode, release page present or skipped with a reason); a failed check is exit 1 and names itself: report it, never ignore it. C4 and C5
are deliberately out: [release-workflow.md](references/release-workflow.md).

---

## Reference Documents

- [conventional-commits.md](references/conventional-commits.md) — Parsing rules
- [changelog-format.md](references/changelog-format.md) — Keep-a-Changelog format
- [compliance-evidence.md](references/compliance-evidence.md) — The seven evidence documents at release
- [manifest-sync.md](references/manifest-sync.md) — Published package manifest version sync + verify
- [release-workflow.md](references/release-workflow.md) — Parallel iterates; upgrade-notes check; canon stop at C3
