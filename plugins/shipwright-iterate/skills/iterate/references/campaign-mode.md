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
       → exit 2 = all done → go to step 4
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
       → exit 3 = failure/escalation → go to step 4 (strict-stop)

   3g. Update campaign status.json:
       uv run "{plugin_root}/scripts/tools/campaign_progress.py" update-status \
         --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" \
         --sub-iterate-id {id} --status complete --commit {commit} --branch {branch}

   3h. Continue loop
   ```

4. **Finalize:**
   ```bash
   uv run ... finalize --state .shipwright/loop_state.json
   ```
   The campaign's top-level lifecycle status reaches `complete`
   **automatically** — the `update-status` call in 3g flips it to
   `complete` once every sub-iterate is `complete`, which hides the
   campaign from the board. If the loop strict-stopped on a failure /
   escalation (3f), some sub-iterates are not `complete`, so the status
   stays `active` and the campaign remains visible (matching step 5's
   "campaign incomplete" branch). No explicit set-complete call is needed.

5. **Release prompt (F12, once):** Only if ALL sub-iterates are
   `complete` AND worktree is clean: count unreleased entries in
   `CHANGELOG.md`. If > 0: *"Run /shipwright-changelog to tag a release?"*
   If any sub-iterate failed or escalated: *"Campaign incomplete; no
   release prompt."*

**When NOT using `--autonomous`:** skip this section entirely, proceed
with normal single-iterate flow.
