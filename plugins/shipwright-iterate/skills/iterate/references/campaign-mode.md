# Campaign Mode (Autonomous Multi-Iterate)

When invoked with `--campaign <slug>` and `--autonomous`, run multiple
sub-iterates **interleaved-serially**: build ONE sub-iterate → open its PR →
wait for CI green → merge → build the NEXT from fresh `origin/main`. This
formalizes the ad-hoc orchestration pattern.

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

## Why interleaved-serial (and not build-all-then-merge)

Each campaign sub-iterate is its OWN PR to `main`, and every sub-iterate
regenerates the same *derived* artifacts (`shipwright_events.jsonl`,
`triage.jsonl`, compliance MDs, the dashboard). If you build all the PRs first
and merge at the end, siblings never see each other → every merge has to 3-way +
regenerate those snapshots against an advancing `origin/main` = recurring merge
theater. Interleaved-serial keeps **only ONE open PR at a time**: the next
sub-iterate branches off a `main` that already contains the prior merge, so
shared-file and snapshot edits compose naturally. There is **no end-stage drain**
and **no regenerate-at-merge**. (Contrast: shipwright-build sections ship as ONE
PR via `single-branch`, so their sequential model has nothing to drain.)

| `branch_strategy` | base for each unit | merge timing | used by |
|---|---|---|---|
| **`serial`** (campaign default) | fresh `origin/<default>` | each PR merged before the next builds | `/shipwright-iterate --campaign` |
| `stacked` | previous unit's branch | n/a (one stack) | shipwright-build sections; legacy campaigns |
| `independent` | local `main` | n/a | legacy campaigns |
| `single-branch` | current branch | one PR | shipwright-build |

## Campaign Setup (interactive, once)

If campaign directory doesn't exist yet:

1. User describes the overarching goal.
2. Together, decompose into sub-iterates (each should be
   trivial-medium complexity).
3. Initialize campaign structure (`--branch-strategy` defaults to `serial`):
   ```bash
   uv run "{plugin_root}/scripts/tools/campaign_init.py" \
     --project-root "$(pwd)" \
     --campaign-slug "{slug}" \
     --intent "{user_intent}" \
     --sub-iterates '{json_array}' \
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
   # The sub-iterate F11 must NOT self-arm GitHub auto-merge: the ORCHESTRATOR
   # owns the merge, one PR at a time, INSIDE the loop (step 3g), so it can verify
   # CI-green + let origin/<default> advance before the next sub-iterate builds.
   # (Arming is for standalone iterates; here it would race the serial sequence
   # and re-introduce the multi-open-PR cascade.) The runners inherit this env;
   # their F11 brings the branch current + pushes but leaves the PR for the
   # orchestrator to merge.
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
     --branch-strategy serial \
     --root-session-id "$SHIPWRIGHT_ROOT_SESSION_ID"
   ```
   `--branch-strategy serial`: `cmd_next` hands each sub-iterate the
   **freshly-fetched `origin/<default>`** as its base, so it branches off a `main`
   that already contains every merged sub-iterate (freshness is enforced in code,
   not by prose). Extract `loop_id` from stdout. Then:
   `export SHIPWRIGHT_LOOP_ID="{loop_id}"`.

   Then **mark the campaign started** (top-level lifecycle status
   `draft` → `active`, so the WebUI Campaigns lane shows it on the board —
   a `draft` campaign is planned-only / triage-only and stays hidden):
   ```bash
   uv run "{plugin_root}/scripts/tools/campaign_progress.py" start \
     --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}"
   ```

3. **Loop (repeat until exit code 2) — build, then MERGE before the next builds:**

   ```
   3a. uv run ... next --state .shipwright/loop_state.json
       → exit 2 = all sub-iterates built + merged → go to step 4 (Finalize)
       → Parse JSON: id, spec_path, base_branch (= fresh origin/<default>), attempt

   3b. export SHIPWRIGHT_LOOP_UNIT_ID="{id}"

   3c. Spawn sub-iterate-runner subagent:
       result = Task(subagent_type="shipwright-iterate:sub-iterate-runner",
                     prompt=<brief with sub_iterate_id, spec, base_branch, etc.>)
       The runner branches off base_branch (fresh origin/<default>), builds,
       finalizes, pushes, and leaves the PR OPEN (auto-merge deferred). The brief
       carries campaign slug (via campaign_path) + sub_iterate_id; the runner
       contract Step 4 STAMPS both into the work_completed event extras
       ("campaign" / "sub_iterate_id" — S1) so per-sub status is projectable
       from events.jsonl alone.

   3d. Wait for terminal marker (.shipwright/runs/{loop_id}/{id}/DONE, timeout 30s)

   3e. Parse result JSON defensively (fallback to runs/{loop_id}/{id}/result.json)

   3f. uv run ... record --state .shipwright/loop_state.json --unit {id} --result '{json}'
       → exit 3 = failure/escalation → STRICT-STOP: go to step 4 (Finalize). Do
         NOT merge, do NOT build the next. The already-MERGED sub-iterates are
         durable; the partial campaign is left for manual follow-up.

   3g. MERGE this sub-iterate's PR — verify CI-green first, then merge, one at a
       time (no shoot-and-forget). The orchestrator owns the merge (the PR did not
       self-arm, step 1):
         pr_url=$(gh pr view "{branch}" --json url -q .url)
         gh pr checks "$pr_url" --watch        # blocks until Required Checks finish
         #   non-zero exit = a check FAILED → STRICT-STOP (as 3f): do not merge,
         #   do not build the next; surface to the user. Merged subs stay durable.
         gh pr merge "$pr_url" --squash --delete-branch
         until [ "$(gh pr view "$pr_url" --json state -q .state)" = "MERGED" ]; do sleep 5; done
       A merge conflict / timeout is likewise non-delivered → STRICT-STOP.

   3h. Update the MAIN-tree campaign status.json (LOCAL-BOARD CONVENIENCE only,
       campaign S3): keeps the orchestrator's own board current BETWEEN
       sub-iterates. It is NOT the durable source — each sub-iterate's F5b Step 6
       already re-projected + committed a per-tree `status.json` that ships in its
       PR (tracked, churn-reconciled). This main-tree write is untracked and never
       reaches a PR; skipping it only affects the live orchestrator view.
       uv run "{plugin_root}/scripts/tools/campaign_progress.py" update-status \
         --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" \
         --sub-iterate-id {id} --status complete --commit {commit} --branch {branch}

   3i. Continue loop. The next `next` (3a) re-fetches and resolves a FRESH
       origin/<default> that now contains this just-merged sub-iterate, so the next
       build composes on it — no drain, no regenerate-at-merge.
   ```

4. **Finalize:**
   ```bash
   uv run ... finalize --state .shipwright/loop_state.json
   ```
   The campaign's top-level lifecycle status reaches `complete`
   **automatically** once every sub-iterate is `complete` — the
   never-downgrade projection (`campaign_status.all_subs_complete`) sets it in
   the per-tree `status.json` the LAST sub-iterate's F5b commits (the durable
   path, S3), and the local 3h `update-status` mirrors it for the live
   orchestrator view. A `complete` campaign is hidden from the board. If the loop
   strict-stopped on a failure / escalation / non-delivered PR (3f/3g), some
   sub-iterates are not `complete`, so the status stays `active` and the campaign
   remains visible (matching step 5's "campaign incomplete" branch). No explicit
   set-complete call is needed.

5. **Release prompt (F12, once):** Only if ALL sub-iterates are
   `complete` AND worktree is clean: count unreleased entries in
   `CHANGELOG.md`. If > 0: *"Run /shipwright-changelog to tag a release?"*
   If any sub-iterate failed, escalated, or its PR did not deliver:
   *"Campaign incomplete; no release prompt."*

**When NOT using `--autonomous`:** skip this section entirely, proceed
with normal single-iterate flow.
