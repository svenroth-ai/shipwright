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
> iterates (Step 3.7). Skipping these review steps silently is a
> contract violation under ADR-029; the runner must record
> `reviews.{plan,code,external_code}.status` in its result-JSON with an
> explicit `skipped_*` value when applicable.
>
> **Where the internal cascade runs here.** The runner subagent has no
> `Agent` tool, so it cannot spawn `spec-reviewer` / `code-reviewer` /
> `doubt-reviewer` itself. ADR-029 named the **orchestrator** the
> delegate; step **`3f-bis`** below is where the delegate acts — after
> the result is recorded, before the PR is merged. That is the last
> point at which a REJECT can still stop delivery, because `3g` merges.
>
> The window is `3f-bis` and NOT "in parallel with the runner, after
> Build", which an earlier version of this note claimed. No such window
> exists: the orchestrator blocks at `3d` on the runner's **terminal**
> DONE marker, which the runner emits only after F6 (commit) and Step 5
> (push). Everything the cascade reviews is therefore already committed
> — which is why `3f-bis` gates the **merge** rather than the commit.
>
> The runner still records `spec` / `code` / `doubt` as `not_run`; that
> is true at the moment it writes them. `3f-bis` promotes those rows
> with `--force` once the passes have actually run, so the record names
> the actor that performed each one. (A hand-run `--sub-iterate-id`
> invocation is a normal standalone session WITH the `Agent` tool — it
> spawns the cascade itself per SKILL.md Step 8 and never reaches
> `3f-bis`.)

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

**Pre-requisite:** `.shipwright/planning/iterate/campaigns/{slug}/status.json` must exist.

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
   # orchestrator to merge. Since iterate-2026-07-31-f11-delivery-truth this ONE
   # variable also suppresses the delivery ladder's self-merge rung: a sub-iterate
   # that merged itself when the host could not arm would break exactly the
   # one-PR-at-a-time invariant this defer exists to hold.
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

   **Resolve model tiers once for the whole campaign** (not per sub-iterate —
   the operator's choice applies uniformly across every unit this loop
   drives):
   ```bash
   uv run "{shared_root}/scripts/tools/resolve_model_tier.py" \
     --project-root "$(pwd)" [--review-model {flag}] [--finalization-model {flag}]
   ```
   (The CLI also resolves `plan_review` — unconsumed here, since campaign
   sub-iterates' mini-plan review has no internal-arm spawn site of its own
   yet; `sub-iterate-runner` carries no `Agent` tool. Documented gap, not
   this call's to close.)
   Keep `review.resolved` for step 3f-bis's delegated cascade and
   `finalization.resolved` for step 3c's `sub-iterate-runner` spawn. Both
   values are substituted as literal `model=` Agent-tool parameters at each
   spawn below — never re-resolved by the runner or by the reviewers it
   receives, since neither reads `shipwright_model_config.json` itself; a
   config edit or worktree switch mid-campaign therefore cannot desync one
   unit's spawns from another's within the same run.

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
       Mint run_id HERE: `iterate-{today}-{id, LOWERCASED}-{desc}` (RUN_ID_STRICT, SKILL.md §C) — `id` may display uppercase (`R0`); LOWERCASE it in run_id, uppercase stays only in branch_name/PR title/`sub_iterate_id` (Step 3.4 now rejects a wrong one immediately, not F5c hours later).

   3c. Spawn sub-iterate-runner subagent:
       result = Task(subagent_type="shipwright-iterate:sub-iterate-runner",
                     model=<finalization tier resolved at loop step 2, omit if "inherit">,
                     prompt=<brief with sub_iterate_id, run_id (3b), spec, base_branch, plan_plugin_root (this session's shipwright-plan plugin root — resolved like plugin_root/shared_root; the runner needs it for `uv run --project` at 3.5/3.7), etc.>)
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

   3f-bis. REVIEW before merging — the delegated cascade (ADR-029). The
       orchestrator HAS the `Agent` tool the runner lacks, and this is the last
       step before 3g merges, so a REJECT here can still stop delivery.

       State crosses to 3g in a FILE, never a shell variable: these are separate
       steps and a fresh Bash call starts with an empty environment, so a `$sha`
       set here would silently expand to "" there — unpinning the merge in the
       exact window this step calls dangerous.
         run_dir=".shipwright/runs/{loop_id}/{id}"; rm -f "$run_dir/reviewed_head"
         pr_url=$(gh pr view "{branch}" --json url -q .url)
         [ -n "$pr_url" ] || STRICT-STOP   # no PR = nothing to review or merge

       FIRES on a trigger computed HERE, from the diff — not inherited from the
       runner. The runner classifies from its spec text alone and has no Stage-2
       Repo Scout, so diff-driven flags (`cross_component`, `touches_*`) are
       structurally never set for it; inheriting that verdict would make this
       gate NARROWEST on exactly the framework surface it exists to protect:
         diff=$(git diff "$(git merge-base origin/{default} HEAD)"...HEAD)
       Fire when the runner said medium+, OR the diff sets any risk flag, OR it
       exceeds 100 lines. Otherwise SKIP the rest of 3f-bis, leave the runner's
       `not_run` rows standing (they are honest), write no `reviewed_head`, and
       go to 3g — a below-threshold sub-iterate must still DELIVER.

       Review that same MERGE-BASE diff, never `origin/{default}`'s tip (a moved
       main yields false high findings):

       a) `spec-reviewer`  — Stage 1, HARD-GATE. A REJECT blocks the rest.
       b) `code-reviewer`  — Stage 2, only once Stage 1 PASSES.
       c) `doubt-reviewer` — Stage 3, conditional, advisory-must-address.

       Pass `model=<review tier resolved at loop step 2>` to each of the three
       spawns above (omit when `inherit`). **State the run_id in plain text in
       every spawn prompt** — the `SubagentStop` salvage hook
       (`write-review-payload-on-stop.py`) reads it only from the transcript,
       never an env var. **Write each subagent's reply to its payload file
       before any other reasoning or spawning the next reviewer** — a
       mitigation, not a guarantee; the salvage hook backstops the window this
       alone cannot close (see `iteration-reviews.md`).

       Promote the rows IN THAT ORDER. The runner already closed them and a
       closed row is immutable, so `--force` is REQUIRED (without it the CLI
       exits 3). A `code` row completed over a non-completed `spec` FAILS the
       gate, so Stage 1 must land first — `…` is the invocation prefix from
       `iteration-reviews.md`, and every call also carries
       `--model-tier "{resolved_review_tier}"`:
         … record --review-type spec  --status completed --from spec-reviewer              --payload-file "{reply}" --recorded-by spec-reviewer --model-tier "{resolved_review_tier}" --force
         … record --review-type code  --status completed --from code-reviewer   … --model-tier "{resolved_review_tier}" --force
         … record --review-type doubt --status completed --from doubt-reviewer  … --model-tier "{resolved_review_tier}" --force

       When Stage 3 does NOT fire (it is conditional), do not leave the runner's
       row standing — its disposition says the cascade did not run, which is now
       FALSE. Re-record it for the reason that actually applies:
         … record --review-type doubt --status not_applicable --force              --disposition "Stage 3 is conditional and did not trigger for this
             diff; Stage 2 passed at 3f-bis"

       Then ship the record with the PR. Every command is CHECKED: a promotion
       that does not reach the remote must STOP the loop, not shorten it. An
       unchecked `git commit` that the pre-commit hook blocks would otherwise
       leave the runner's head in place, the local record saying `completed`,
       and main saying `not_run` — the cascade silently un-shipped:
         git add ".shipwright/planning/iterate/{run_id}/reviews.json"
         git commit -m "chore(review): record the delegated cascade for {id}" || STRICT-STOP
         git push || STRICT-STOP
         git rev-parse HEAD > "$run_dir/reviewed_head"

       **This push restarts CI**, so 3g must watch THIS head. Wait for the PR
       object to catch up — BOUNDED, because an unbounded wait is a third
       outcome the loop has no name for (neither delivered nor stopped):
         for i in $(seq 1 60); do
           [ "$(gh pr view "$pr_url" --json headRefOid -q .headRefOid)" = "$(cat "$run_dir/reviewed_head")" ] && break
           sleep 5
         done
         # still not matching after the cap → STRICT-STOP, do not hand a stale
         # head to 3g.

       On a Stage-1 REJECT, or a Stage-2 high finding left unaddressed:
       STRICT-STOP exactly as 3f/3g — do NOT merge, do NOT build the next. The
       already-merged sub-iterates stay durable; this PR is left OPEN so a human
       can repair it.

       SHIP the REJECT before stopping, or the durable record stays the runner's
       `not_run` and the left-open PR reads as merely unreviewed rather than
       REJECTED. `completed` is wrong here — the native Stage-1 payload stores
       `spec_citations` and drops `verdict`, so a `completed` REJECT is
       byte-indistinguishable from a PASS to the next reader, human or gate:
         … record --review-type spec --status not_run --force \\
             --recorded-by spec-reviewer \\
             --disposition "Stage-1 spec-reviewer REJECTED at 3f-bis: {the
             citations, spec_ref -> divergence}. Delivery stopped; PR left open."
         git add ".shipwright/planning/iterate/{run_id}/reviews.json"
         git commit -m "chore(review): record the Stage-1 REJECT for {id}" || STRICT-STOP
         git push || STRICT-STOP
       Then STRICT-STOP. Write no `reviewed_head` — nothing may merge this.

   3g. MERGE this sub-iterate's PR — verify CI-green first, then merge, one at a
       time (no shoot-and-forget). The orchestrator owns the merge (the PR did not
       self-arm, step 1):
         # Re-resolve from the branch: shell state does NOT survive between steps,
         # so nothing set in 3f-bis is still in the environment here.
         pr_url=$(gh pr view "{branch}" --json url -q .url)
         # The pin comes from 3f-bis's FILE. Absent = 3f-bis pushed nothing (the
         # cascade skipped below its trigger), and that sub-iterate must still
         # deliver — so the pin is conditional, never unconditional.
         run_dir=".shipwright/runs/{loop_id}/{id}"
         head_pin=""
         [ -f "$run_dir/reviewed_head" ] && head_pin="--match-head-commit $(cat "$run_dir/reviewed_head")"
         gh pr checks "$pr_url" --watch        # blocks until Required Checks finish
         #   non-zero exit = a check FAILED → STRICT-STOP (as 3f): do not merge,
         #   do not build the next; surface to the user. Merged subs stay durable.
         gh pr merge "$pr_url" --squash --delete-branch $head_pin
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

---

## Step 3.4 — Diff-Driven Risk Re-Check (runner contract)

**The gap it closes.** A campaign unit classifies complexity exactly once, at
runner Step 2, from the sub-iterate spec **text**, before any code exists.
`classify()` takes `(message, sync_config_path, project_root)` and detects risk
with `detect_risk_flags(message)` — a regex sweep over that message. The four
*diff-driven* detectors in `risk_detectors.py` are imported by
`classify_complexity` but never called by `classify()`; their documented caller
is the **Stage-2 Repo Scout** (`iteration-planning.md`, Quick Scout step 3),
which the runner never reaches. So `cross_component`,
`touches_ci_supplychain` and the file-pattern halves of `touches_io_boundary` /
`touches_build` are *structurally* unable to fire for a campaign unit.

This is the same gap **3f-bis** already compensates for on the orchestrator
side, and for the same stated reason. 3f-bis can only protect what happens
*after* the runner returns; Step 3.4 protects what happens *inside* it.

**Two consequences, and they differ.** `check_ci_supplychain_ack` applies at
EVERY complexity and recomputes the flag from the diff, so a workflow-touching
unit **hard-fails its own F6-verify** with an error naming an artifact nobody
told it to produce. `check_integration_coverage` demands a `category:"integration"`
behavior in the F5c ledger for the same diff. A unit that never learns the flag
does not know to write one, and until 2026-08-01 that gate also green-SKIPped
below `medium`, so an under-classified unit reported green without evaluating.
That skip is gone (the gate now reads the ledger at every tier), but the unit is
still blind: it cannot produce coverage for a flag it was never told about, and
the recorded tier stays wrong. One dies loudly; the other passes quietly. Step
3.4 fixes both by re-deciding from the real change set.

**The change set is the working tree.** The runner commits at F6, *after* this
step, so a `base...HEAD` range is empty here. The CLI therefore diffs
`base_ref` → working tree (committed + staged + unstaged) and unions
`git ls-files --others --exclude-standard` — a brand-new hook file appears in no
diff at all. Getting this wrong reintroduces the exact blindness being removed.

**Orchestrator handling of a CI escalation.** The runner returns
`status: "escalated"` with `reason_code: "ci_supplychain_requires_operator"` and
a non-empty `ci_paths`. No special-casing is needed at 3f: `escalated` is
already a valid status (`autonomous_loop.VALID_STATUSES`), the whole result is
persisted to `runs/{loop_id}/{id}/result.json`, and any non-`complete` status
exits 3 → **STRICT-STOP** — no merge, no next unit, already-merged units stay
durable. `campaign_progress.py` counts escalated units separately from failed
ones, and `failure_reason` carries the escalation `reason` into `loop_state.json`,
where the orchestrator (and the WebUI board) read it. The operator resolves it by recording the acknowledgement with
`record_ci_supplychain_ack.py` — naming the posture decision the change agrees
with — and re-running the unit. **The re-run must terminate, and that is why the
CLI is ack-aware:** Build re-creates the same CI edit, so a re-check that only
looked at the diff would escalate again, forever. A recorded ack *for this run id*
therefore exits 0 while still reporting the flag and `ci_paths`. Presence is all
Step 3.4 checks; `check_ci_supplychain_ack` still validates the ack's content, its
run binding and the diff fingerprint at F11, so a bogus file buys nothing and a
previous run's ack cannot license this diff. **The runner must never write that ack
itself:**
it certifies that a human reasoned about a trust-boundary change, and a runner
authoring its own permission slip is precisely the failure the gate exists to
catch (webui #285 reversed an accepted-risk posture unnoticed *through* a full
medium iterate with external plan review).
