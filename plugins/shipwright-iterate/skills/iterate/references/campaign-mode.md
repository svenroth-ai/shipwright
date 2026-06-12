# Campaign Mode (Autonomous Multi-Iterate)

When invoked with `--campaign <slug>` and `--autonomous`, run multiple
sub-iterates sequentially without manual gates. This formalizes the
ad-hoc orchestration pattern.

**Flags:** `/shipwright-iterate --campaign <slug> [--autonomous] [--sub-iterate-id <id>]` (the last for a single hand-run sub-iterate — stamps the event per SKILL.md §5b)

> **Review steps in autonomous-loop briefing (ADR-029).** When briefing
> a sub-iterate-runner under `--autonomous`, include a reminder that the
> runner contract mandates **Step 3.5 (External Plan Review)** and
> **Step 3.7 (Code Review Cascade)** between Build and Finalization for
> medium+ iterates (Step 3.5) and for medium+ / risk-flag / >100-LOC
> iterates (Step 3.7). The runner has no `Agent` tool, so the internal
> code-reviewer subagent is delegated back to the orchestrator (campaign
> mode) — the orchestrator spawns it in parallel with the runner after
> Build, then merges findings into the iterate ADR. Skipping these
> review steps silently is a contract violation under ADR-029; the
> runner must record `reviews.{plan,code,external_code}.status` in its
> result-JSON with an explicit `skipped_*` value when applicable.

## Campaign Setup (interactive, once)

If campaign directory doesn't exist yet:

1. User describes the overarching goal.
2. Together, decompose into sub-iterates (each should be
   trivial-medium complexity).
3. Initialize campaign structure:
   ```bash
   uv run "{plugin_root}/scripts/tools/campaign_init.py" \
     --project-root "$(pwd)" \
     --campaign-slug "{slug}" \
     --intent "{user_intent}" \
     --sub-iterates '{json_array}' \
     --branch-strategy stacked \
     --expands-triage "{trg-id}"   # optional — anchor to a triage item
   ```
4. Review generated
   `.shipwright/planning/iterate/campaigns/{slug}/campaign.md` with user.

> **Promoting a triage item to a campaign.** When the campaign exists to
> work off a specific triage card, anchor it with `--expands-triage
> <trg-id>` (validated `trg-<8 hex>`). The id is stamped into BOTH
> `status.json` and the `campaign.md` frontmatter (`expands_triage:`),
> which is exactly what the WebUI joins on per-project
> (`fm.expandsTriage || fm.expands_triage == item.id`) to render the
> **"Start Campaign"** CTA on that card. The convenience flag
> `--from-triage <trg-id>` does the same anchor AND seeds `--intent` from
> the triage item's title/detail when `--intent` is omitted (reads
> `<project-root>/.shipwright/triage.jsonl`). Anchoring is strictly
> per-project: the campaign and its triage item must live in the same
> repo.

## Autonomous Campaign Loop

**Pre-requisite:**
`.shipwright/planning/iterate/campaigns/{slug}/status.json` must exist.

1. **Export env vars:**
   ```bash
   export SHIPWRIGHT_ROOT_SESSION_ID="${SHIPWRIGHT_SESSION_ID}"
   export SHIPWRIGHT_LOOP_ID=""  # set after init
   # Defer the F11 auto-merge arm for EVERY sub-iterate. Parallel sub-iterate PRs
   # that each commit regenerated derived snapshots cannot all auto-merge at once:
   # GitHub's server-side merge can't run the regenerate-at-merge resolver, so as
   # PRs merge serially the still-open ones cascade DIRTY (snapshot conflict) or
   # merge stale (Group-E staleness). The runners inherit this env; their F11
   # brings the branch current + pushes but does NOT arm. The Serial Merge Drain
   # (step 4) owns the merge instead.
   export SHIPWRIGHT_ITERATE_AUTOMERGE=0
   ```

2. **Generate units file and initialize loop:**
   ```bash
   uv run "{plugin_root}/scripts/tools/campaign_progress.py" list-units \
     --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" > /tmp/campaign_units.json

   uv run "{shared_root}/scripts/lib/autonomous_loop.py" init \
     --state .shipwright/loop_state.json \
     --kind sub_iterate \
     --units-from /tmp/campaign_units.json \
     --branch-strategy stacked \
     --root-session-id "$SHIPWRIGHT_ROOT_SESSION_ID"
   ```
   Extract `loop_id` from stdout. Then:
   `export SHIPWRIGHT_LOOP_ID="{loop_id}"`.

   Then **mark the campaign started** (top-level lifecycle status
   `draft` → `active`, so the WebUI Campaigns lane shows it on the board —
   a `draft` campaign is planned-only / triage-only and stays hidden):
   ```bash
   uv run "{plugin_root}/scripts/tools/campaign_progress.py" start \
     --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}"
   ```

3. **Loop (repeat until exit code 2):**

   ```
   3a. uv run ... next --state .shipwright/loop_state.json
       → exit 2 = all PRs built → go to step 4 (Serial Merge Drain)
       → Parse JSON: id, spec_path, base_branch, attempt

   3b. export SHIPWRIGHT_LOOP_UNIT_ID="{id}"

   3c. Spawn sub-iterate-runner subagent:
       result = Task(subagent_type="shipwright-iterate:sub-iterate-runner",
                     prompt=<brief with sub_iterate_id, spec, base_branch, etc.>)
       Brief carries campaign slug (via campaign_path) + sub_iterate_id; the
       runner contract Step 4 STAMPS both into the work_completed event extras
       ("campaign" / "sub_iterate_id" — S1) so per-sub status is projectable
       from events.jsonl alone.

   3d. Wait for terminal marker (.shipwright/runs/{loop_id}/{id}/DONE, timeout 30s)

   3e. Parse result JSON defensively (fallback to runs/{loop_id}/{id}/result.json)

   3f. uv run ... record --state .shipwright/loop_state.json --unit {id} --result '{json}'
       → exit 3 = failure/escalation → go to step 5 (Finalize), SKIP the drain
         (strict-stop, campaign incomplete — do not merge a partial campaign)

   3g. Update the MAIN-tree campaign status.json (LOCAL-BOARD CONVENIENCE only,
       campaign S3): keeps the orchestrator's own board current BETWEEN
       sub-iterates. It is NO LONGER the durable source — each sub-iterate's F5b
       Step 6 already re-projected + committed a per-tree `status.json` that
       ships in its PR (tracked, churn-reconciled), so the deployed/cloned board
       is correct from the merged artifacts. This main-tree write is untracked
       and never reaches a PR; skipping it only affects the live orchestrator view.
       uv run "{plugin_root}/scripts/tools/campaign_progress.py" update-status \
         --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" \
         --sub-iterate-id {id} --status complete --commit {commit} --branch {branch}

   3h. Continue loop
   ```

4. **Serial Merge Drain (autonomous campaigns).** The build loop left every
   sub-iterate PR open with auto-merge DEFERRED (`SHIPWRIGHT_ITERATE_AUTOMERGE=0`,
   step 1). Now **drain them serially** — merge ONE PR at a time, in dependency
   order (stacked: base-chain order; independent: any order) — so each merges from
   a tree that already regenerated its derived snapshots against the *just-merged*
   `origin/main`, instead of relying on GitHub's server-side merge that cannot run
   the regenerate-at-merge resolver. For each completed sub-iterate PR, in turn:

   ```bash
   # (a) Bring THIS branch current with the now-advanced origin/main and
   #     regenerate its derived snapshots (clean no-op if already current). Runs
   #     in the sub-iterate's own worktree; reuses integrate_main via the guard.
   uv run "{shared_root}/scripts/tools/ensure_current.py" \
     --project-root "{sub_iterate_worktree}" --run-id "{sub_iterate_run_id}" \
     --reason "campaign serial drain: {slug}/{sub_iterate_id}"
   #     Non-zero exit = a non-churn/source conflict → STOP the drain, leave the
   #     remaining PRs for a manual integrate; the already-merged ones are durable.
   # (b) Push any integrate commits, then merge THIS PR and WAIT for it to land
   #     before the next (so the next branch integrates an origin/main that already
   #     contains this one):
   git -C "{sub_iterate_worktree}" push
   gh pr merge "{pr_url}" --auto --squash --delete-branch   # arm on the now-current branch
   #     then poll `gh pr view "{pr_url}" --json state -q .state` until MERGED
   #     (or, if Required Checks are already green, `gh pr merge --squash` directly).
   ```
   Proceed to the next PR only after the prior PR has merged. This reuses the
   existing resolver — it is a merge-step addition, not new machinery — and is
   host-agnostic for the regeneration (only the final PR-merge *trigger* is `gh`).

5. **Finalize:**
   ```bash
   uv run ... finalize --state .shipwright/loop_state.json
   ```
   The campaign's top-level lifecycle status reaches `complete`
   **automatically** once every sub-iterate is `complete` — the
   never-downgrade projection (`campaign_status.all_subs_complete`) sets it in
   the per-tree `status.json` the LAST sub-iterate's F5b commits (the durable
   path, S3), and the local 3g `update-status` mirrors it for the live
   orchestrator view. A `complete` campaign is hidden from the board. If the loop
   strict-stopped on a failure / escalation (3f), some sub-iterates are not
   `complete`, so the status stays `active` and the campaign remains visible
   (matching step 6's "campaign incomplete" branch). No explicit set-complete
   call is needed.

6. **Release prompt (F12, once):** Only if ALL sub-iterates are
   `complete` AND worktree is clean: count unreleased entries in
   `CHANGELOG.md`. If > 0: *"Run /shipwright-changelog to tag a release?"*
   If any sub-iterate failed or escalated: *"Campaign incomplete; no
   release prompt."*

**When NOT using `--autonomous`:** skip this section entirely, proceed
with normal single-iterate flow.
