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
> `doubt-reviewer` itself. ADR-029 named the **orchestrator** the delegate;
> step **`3f-bis`** below is where the delegate acts — after the result is
> recorded, before the PR is merged. That is the last point at which a
> REJECT can still stop delivery, because `3g` merges.
>
> The window is `3f-bis` and NOT "in parallel with the runner, after Build",
> which an earlier version of this note claimed. No such window exists: the
> orchestrator blocks at `3d` on the runner's **terminal** DONE marker,
> emitted only after F6 (commit) and Step 5 (push) — everything the cascade
> reviews is therefore already committed, which is why `3f-bis` gates the
> **merge** rather than the commit.
>
> The runner still records `spec` / `code` / `doubt` as `not_run`; that is
> true at the moment it writes them. `3f-bis` promotes those rows with
> `--force` once the passes have actually run, so the record names the actor
> that performed each one. (A hand-run `--sub-iterate-id` invocation is a
> normal standalone session WITH the `Agent` tool — it spawns the cascade itself per SKILL.md Step 8 and never reaches `3f-bis`.)

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
| `stacked` | previous unit's branch | n/a (one stack) | **deprecated** — shipwright-build sections; legacy campaigns |
| `independent` | local `main` | n/a | legacy campaigns |
| `single-branch` | current branch | one PR | shipwright-build |

**`depends_on` reconciliation with `branch_strategy`** (campaign-dag-scheduler
R1, detail: `references/campaign-dependency-graphs.md`): R1 gates only
*readiness* — `cmd_next` skips a unit until every `depends_on` edge is a
verified-merged commit; `resolve_base_branch` is untouched, so every unit
still bases off fresh `origin/<default>` under `serial`. A dependent basing
off its dependency's `merged_commit` directly is **not yet implemented** —
R4's job. `stacked` is deprecated in favor of explicit `depends_on`.

## Campaign Setup (interactive, once)

If campaign directory doesn't exist yet:

1. User describes the overarching goal.
2. Together, decompose into sub-iterates (each should be
   trivial-medium complexity). **Campaign-design conversation
   (campaign-dag-scheduler R1):** for each pair, ask "does X need Y first?"
   — a genuine ordering need becomes a `depends_on` edge on X; independent
   work stays edge-free so it can build in parallel once R5a lands. State
   the cost out loud: X cannot START until Y has *merged*, not just built —
   so an edge must reflect a genuine need. Full schema: "Dependency Graphs"
   below.
3. Initialize campaign structure (`--branch-strategy` defaults to `serial`):
   ```bash
   uv run "{plugin_root}/scripts/tools/campaign_init.py" \
     --project-root "$(pwd)" \
     --campaign-slug "{slug}" \
     --intent "{user_intent}" \
     --sub-iterates '{json_array}' \
     --expands-triage "{trg-id}"   # optional — anchor to a triage item
   ```
   Each sub-iterate object in `{json_array}` may carry `"depends_on":
   ["<id>", ...]` (bare sub-iterate ids from step 2's conversation, default
   `[]`) — validated at write time (see "Dependency Graphs" below).
4. Review generated
   `.shipwright/planning/iterate/campaigns/{slug}/campaign.md` with user.

## Dependency Graphs (`depends_on`)

See `references/campaign-dependency-graphs.md` for the full schema
(campaign-dag-scheduler R1): cell grammar + id charset, case-insensitive
collision, write vs. read severity, frozen-on-claim, the degraded
side-channel, ancestry-verified readiness, the squash-merge SHA-mismatch
limitation, and `cmd_next`'s narrow readiness guard — including the
**accepted interim-window gap** (a dependent finalizes UNBUILT within one
continuous single-session run, not merely delayed, until R4/R5b's
`cmd_mark_merged` lands — accepted through R4/R5b rather than pulled forward
into an R1.5) and the fact that `safe_project_campaign_status` /
`check_frozen_contracts` are R1's read-side primitives but have no caller on
the actual read path yet — R4's `cmd_next_batch` is the first wiring point.

**Exit-code loop-action table** (step 3a semantics, incl. future R4/R5b exit
codes and today's exit `2` while gating isn't live): `references/campaign-dependency-graphs.md`.

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

**Pre-requisite:** `.shipwright/planning/iterate/campaigns/{slug}/status.json` must exist. **Campaign Worktree + session lock (unconditional, first):** set up/resume the worktree and acquire the session-liveness lock per `references/campaign-worktree.md`; `{project_root}` below is that worktree, never main. A lock rejection aborts startup — see that reference for what to tell the operator.

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

2. **Initialize loop from the piped units list** — both sides are same-shell
   Python CLIs, so the list is piped straight through, no bare `/tmp/...`
   literal for bash and native Python to resolve differently on Windows:
   ```bash
   uv run "{plugin_root}/scripts/tools/campaign_progress.py" list-units \
     --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" | \
   uv run "{shared_root}/scripts/lib/autonomous_loop.py" init \
     --state .shipwright/loop_state.json \
     --kind sub_iterate \
     --units-from - \
     --branch-strategy serial \
     --root-session-id "$SHIPWRIGHT_ROOT_SESSION_ID"
   ```
   `--branch-strategy serial`: `cmd_next` hands each sub-iterate the
   **freshly-fetched `origin/<default>`** as its base (enforced in code, not
   by prose). Extract `loop_id` from stdout, then `export
   SHIPWRIGHT_LOOP_ID="{loop_id}"`.

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
   3a. Renew the session lock first (`uv run "{shared_root}/scripts/checks/check_campaign_session_lock.py" touch --campaign-worktree "{project_root}" --session-id "$SHIPWRIGHT_SESSION_ID"`, references/campaign-worktree.md; non-zero = **LOCK-LOST — distinct from STRICT-STOP: do NOT proceed to step 4**, because Finalize writes `loop_state.json` and a lock-loss means a second session may already be driving it; stop immediately, write nothing, and report to the operator that this session lost the campaign lock (see references/campaign-worktree.md)), then uv run ... next --state .shipwright/loop_state.json
       → exit 2 → check `blocked_pending_ids` FIRST — non-empty means STALLED,
         not done: STOP, report `blockers`, do not finalize (campaign-dependency-graphs.md
         § "Exit 2 is not always done"); empty/absent → step 4 (Finalize)
       → Parse JSON: id, spec_path, base_branch (= fresh origin/<default>), attempt

   3b. export SHIPWRIGHT_LOOP_UNIT_ID="{id}"
       Mint run_id HERE: `iterate-{today}-{id, LOWERCASED}-{desc}` (RUN_ID_STRICT, SKILL.md §C) — `id` may display uppercase (`R0`); LOWERCASE it in run_id, uppercase stays only in branch_name/PR title/`sub_iterate_id` (Step 3.4 now rejects a wrong one immediately, not F5c hours later).

   3c. **Worktree guard, then spawn.** Run the spawn-guard command from `references/campaign-worktree.md` first (non-zero = STRICT-STOP, go to step 4, do NOT spawn). Then, Spawn sub-iterate-runner subagent:
       result = Task(subagent_type="shipwright-iterate:sub-iterate-runner",
                     model=<finalization tier resolved at loop step 2, omit if "inherit">,
                     prompt=<brief with sub_iterate_id, run_id (3b), spec, base_branch, campaign_slug (this loop's `{slug}`), plan_plugin_root (this session's shipwright-plan plugin root — resolved like plugin_root/shared_root; the runner needs it for `uv run --project` at 3.5/3.7), campaign_worktree (= `{project_root}`, this loop's own campaign worktree — R2), state_path (= `{project_root}/.shipwright/loop_state.json` — R2), etc.>)
       The runner branches off base_branch (fresh origin/<default>), builds,
       finalizes, pushes, and leaves the PR OPEN (auto-merge deferred). The brief
       carries campaign_path + campaign_slug + sub_iterate_id; the runner
       contract Step 4 STAMPS campaign_slug + sub_iterate_id into the
       work_completed event extras ("campaign" / "sub_iterate_id" — S1) so
       per-sub status is projectable from events.jsonl alone. `campaign_worktree`/`state_path` feed the runner's own step-boundary liveness touches (references/campaign-worktree.md, R2).

   3d. Wait for terminal marker (.shipwright/runs/{loop_id}/{id}/DONE, timeout 30s)

   3e. Parse result JSON defensively (fallback to runs/{loop_id}/{id}/result.json)

   3f. uv run ... record --state .shipwright/loop_state.json --unit {id} --result '{json}'
       → exit 3 = failure/escalation → STRICT-STOP: go to step 4 (Finalize). Do
         NOT merge, do NOT build the next. The already-MERGED sub-iterates are
         durable; the partial campaign is left for manual follow-up.

   3f-bis. REVIEW before merging — the delegated cascade (ADR-029). The
       orchestrator HAS the `Agent` tool the runner lacks, and this is the last
       step before 3g merges, so a REJECT here can still stop delivery.

       **Dispatch rule, checked before spawning a) below:** see
       `shared/prompts/codex_review_dispatch.md` for the full Codex-driver
       procedure (add `--force` to every `record_review_pass.py record` call
       it describes, matching the promotions below). The ORCHESTRATOR here has
       no ordinary Agent-tool fallback of its own if Codex CLI is driving the
       campaign — a transport failure always lands on the doc's `not_run`
       branch. This rule belongs HERE, never inside the runner subagent's own
       instructions — the runner has no `Agent` tool either way and always
       defers to this step regardless of which harness drives the
       orchestrator.

       State crosses to 3g in a FILE, never a shell variable: these are separate
       steps and a fresh Bash call starts with an empty environment, so a `$sha`
       set here would silently expand to "" there — unpinning the merge in the
       exact window this step calls dangerous. The SAME hazard applies inside
       THIS step too: `fires` below is a model judgement read from the diff's
       own text, not something a shell script can decide on its own, which in
       practice forces a fresh Bash call before pin runs — so `$unit_wt`,
       `$diff_head`, `$fires`, and `$pr_json` are each dual-written to
       `$run_dir/` the moment they are known and re-read at the top of the pin
       block, rather than trusted to survive as shell variables from here to
       there. `$run_dir` itself is NOT one of the values this dual-write
       protects — it is a shell variable exactly like the others, and
       genuine boundaries here are real: a model judgement (`fires`, below)
       or an Agent-tool spawn (the a/b/c cascade) each force a fresh Bash
       call with an empty environment (code-review round 5, blocking:
       round 4 dual-wrote the values but re-read them through an
       un-re-derived `$run_dir`, so the fix did not survive the exact
       boundary it was built for). Proving WHICH specific reads and writes
       are safely same-call and which cross a boundary is exactly the
       reasoning that drew three consecutive REJECTs on this class
       (spec-review/code-review rounds 5-7): each fix correctly re-derived
       `run_dir` at the one site a reviewer had just named, then a
       DIFFERENT site — equally un-provably-same-call, just not yet
       flagged — turned out to have the identical gap. **The rule from here
       on is therefore not "re-derive at the one site a reviewer just
       named" but "exactly one `run_dir=` rebuild must OPEN every
       contiguous shell block that touches a `$run_dir/`-prefixed path,
       where a block ENDS at any model judgement (like `fires` below) or
       Agent-tool spawn (the a/b/c cascade) — never at a subprocess call, a
       `sleep`, or a shell loop, none of which return control to the
       model"** — a read or write inside a block that already opened with
       its own rebuild needs no second one; one extra template-string line
       costs nothing where a genuine boundary IS crossed (it is not a
       subprocess call, just a local reassignment to the same value), and
       the opening rebuild is what a mechanical test can verify (see
       `test_step_3f_bis_every_run_dir_use_opens_within_its_own_block` in
       `test_campaign_step_3f_bis.py`, which scans every double-quoted
       `$run_dir/`-prefixed occurrence in both 3f-bis and 3g generically,
       not one enumerated site at a time, and does not exempt either step).
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"; mkdir -p "$run_dir"; rm -f "$run_dir/reviewed_head" "$run_dir/unit_worktree" "$run_dir/diff_head" "$run_dir/fires" "$run_dir/diff_lines" "$run_dir/pr_json" "$run_dir/shipped_head"
       Clears EVERY handoff file this step writes, not `reviewed_head` alone
       (R3 doubt-round, round 4, medium: `diff_head`/`unit_worktree` are
       cross-checked downstream against the live diff/pin, so a stale value
       surviving a re-entry is caught there — but `fires`/`diff_lines` have NO
       such cross-check, only the fail-closed shape guard below, so a stale
       `fires=0`/`diff_lines` surviving a re-entry after new commits enlarged
       the diff would silently skip the cascade on a NEW, now-large diff
       using an OLD, no-longer-applicable verdict). All seven are re-derived
       or rewritten later in this same step on the path that uses them
       (`shipped_head` only on the `fires=1` path, which is the only path
       that reads it), so clearing them up front costs nothing.
       `$unit_wt` is resolved HERE, before pin ever runs — it does not need to
       wait for pin's own answer, because `worktree` is independently readable
       from `loop_state.json`'s row for this unit (the exact field
       `resolve_unit_identity()` reads). Since R2 (#784) the row normally
       CARRIES a `worktree` field — `check_unit_lease.py touch` writes it at
       every runner step boundary (`sub-iterate-runner.md`'s "Step-boundary
       liveness touches", `--worktree "{project_root}"`) — so the fallback
       below is for a row touched before R2's lease landed, or a lease touch
       that warned-and-continued past a failure, not the normal case
       (code-review round 4: the prior wording claimed no row carries the
       field pre-R5a, which stopped being true the moment R2 merged). It is
       the SAME fallback pin applies below, kept in lockstep by the equality
       check two paragraphs down (R3, spec-review round 2: the prior draft
       treated this as a structural ordering gap it could not close before
       pin; it was not one). The lookup is close to, not identical to,
       `resolve_unit_identity()`'s own case-insensitive match (Python's
       `.lower()` vs. jq's ASCII-only `ascii_downcase`) — both still fail
       closed on the one input they could disagree on (a non-ASCII-cased id),
       since a jq non-match falls through to the `{project_root}` fallback,
       which pin's own equality check below then catches on comparison.
       `.id? // ""` guards a null/non-string `.id` row from aborting the
       whole jq program for every unit's lookup, not just its own
       (code-review round 4, low); dropping `2>/dev/null` lets a genuine jq
       failure surface instead of silently reading as "no match" (code-review
       round 4, low):
         unit_wt=$(jq -r --arg id "{id}" \
           '[.units[]? | select(((.id? // "")|ascii_downcase)==($id|ascii_downcase)) | .worktree] | first // empty' \
           "{project_root}/.shipwright/loop_state.json") || STRICT-STOP
         [ -n "$unit_wt" ] || unit_wt="{project_root}"
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         echo "$unit_wt" > "$run_dir/unit_worktree" || STRICT-STOP
         pr_json=$(cd "$unit_wt" && gh pr view "{branch}" --json url,id,headRefName,baseRefName)
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         echo "$pr_json" > "$run_dir/pr_json" || STRICT-STOP
         pr_url=$(jq -r .url <<<"$pr_json")
         [ -n "$pr_url" ] && [ "$pr_url" != "null" ] || STRICT-STOP   # no PR = nothing to review or merge

       FIRES on a trigger computed HERE, from the diff — not inherited from the
       runner. The runner classifies from its spec text alone and has no Stage-2
       Repo Scout, so diff-driven flags (`cross_component`, `touches_*`) are
       structurally never set for it; inheriting that verdict would make this
       gate NARROWEST on exactly the framework surface it exists to protect.
       Every git command here (and every one below) is `git -C` a resolved
       path, never a bare `git` relying on cwd. **Unit-scoped, no fallback-only
       exceptions (R3, spec-review round 2; extended R3 doubt-round, round 4,
       high):** every NAMED 3f-bis/3g call site that touches the DIFF or the
       reviews.json artifact that certifies it — the diff itself, both
       `gh pr view` resolutions, reviews.json's add/commit/push, the
       REJECT-path's add/commit/push, `record`'s `--payload-file` root, AND
       `record`'s OWN `--project-root` (overridden below from `…`'s
       `{project_root}` default — see "Promote the rows" and the REJECT-path
       below) — runs against `$unit_wt`, THIS unit's own worktree, resolved
       from `loop_state.json`'s row (the SAME `jq` lookup above, before pin
       ever runs), dual-written to `$run_dir/unit_worktree` above so the
       steps and spawns that cross a shell boundary can re-read it rather
       than re-derive it independently (a second, divergent resolution is
       the exact bug class the equality check right after pin below exists
       to catch). Leaving `record`'s `--project-root` at the `…` prefix's
       default was itself exactly the fallback-only exception this same rule
       already forbids for `--payload-file`'s root: reviews.json must be
       written into the SAME worktree its own `git -C "$unit_wt"
       add/commit/push` operates on immediately after, or the two diverge the
       moment R5a gives a unit a genuinely distinct worktree — `record`
       landing reviews.json in `{project_root}` while `git -C "$unit_wt" add`
       looks for it in `$unit_wt` finds nothing to stage ("nothing to
       commit" on every unit, campaign-wide stall). `check_review_attribution.py`'s
       own `--project-root`/`--campaign-worktree` arguments (pin/ship/verify,
       below) are a DIFFERENT root and are untouched by this rule: they
       locate the orchestrator-owned `.shipwright/runs/{loop_id}/...`
       bookkeeping tree, which stays `{project_root}` — the shared campaign
       worktree — by design, not the per-unit diff; nothing here contradicts
       pin's own `--campaign-worktree "{project_root}"` argument.
       `record_review_pass.py`'s `--project-root` means something else
       entirely (where `.shipwright/planning/iterate/{run_id}/reviews.json`
       lives, beside the reviewed source), which is exactly why it is
       unit-scoped while pin/ship/verify's is not. Every row resolves to
       the SAME value `{project_root}` holds today (R5a hasn't yet given a
       unit a genuinely distinct worktree) — but the resolution reads the
       row, not a hardcoded alias, so a distinct worktree is honored
       automatically once R5a lands, not a future TODO.
       The diff itself is computed against `$unit_wt` — the SAME resolution
       used for the pre-pin `gh pr view` above, not `{project_root}` — because
       `$unit_wt`'s `worktree` field is independently readable from
       `loop_state.json` before pin ever runs; nothing here is a pin input, so
       nothing here needs to wait for pin. `merge-base` is captured explicitly
       and CHECKED before it builds the diff range — an unchecked failure
       collapses the range to `...{sha}` (i.e. `HEAD...{sha}`), an EMPTY diff
       for `diff_head==HEAD`, which fails OPEN (`fires=0`, cascade skipped,
       unit merges unreviewed — code-review round 4, low):
         diff_head=$(git -C "$unit_wt" rev-parse HEAD)
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         echo "$diff_head" > "$run_dir/diff_head" || STRICT-STOP
         base=$(git -C "$unit_wt" merge-base origin/{default} "$diff_head") || STRICT-STOP
         diff=$(git -C "$unit_wt" diff "$base"..."$diff_head") || STRICT-STOP
         diff_lines=$(printf '%s\n' "$diff" | wc -l | tr -d '[:space:]')
         echo "$diff_lines" > "$run_dir/diff_lines" || STRICT-STOP
       Fire when the runner said medium+, OR the diff sets any risk flag, OR
       `$diff_lines` exceeds 100. Only the first two clauses are a JUDGEMENT
       made by reading the diff — the line-count clause is NOT: it is computed
       mechanically above, dual-written for the SAME reason `$fires` itself is
       below (this is the fourth value the `fires`-judgement boundary hands
       across, not a fifth kind of thing), and enforced by an executable
       shell statement at the fires-assignment site below, not by a sentence
       claiming it is enforced (code-review round 11, high: a prior draft of
       this fix stated the floor in prose and added a test asserting the word
       "mandatory" appeared, while `$diff_lines` itself was computed but never
       echoed, dual-written, or read again anywhere — the model making the
       `fires` judgement never observed the number and nothing downstream
       could raise `fires` from it, so the "MANDATORY" claim was
       unenforceable; this re-opened the exact rounds-4-10 shell-variable-
       lifetime class on the one value this round's own fix introduced).
       `fires=1` is MANDATORY whenever `$diff_lines` is over 100, never left
       to the same read-and-decide judgement as the other two (the risk-flag
       and medium+ clauses still require actually reading the diff, since
       neither is mechanically decidable from line count alone). Once the
       digit is decided (by this mandatory floor or by judgement), the
       literal next command is an ACTUAL assignment of it (`fires=1` or
       `fires=0`), never a bare `echo "$fires"` with nothing upstream ever
       having assigned it (code-review
       round 5, blocking: the prior wording described the decision in prose
       and then wrote `$fires` as though an earlier line had set it — none
       had, so every unit's fires file was written EMPTY, unconditionally,
       independent of the spawn-boundary issue above; empty reads as "did not
       fire" on re-read, silently skipping the whole review cascade and
       merging the unit unreviewed — worse than the pre-fix behavior, where
       `fires` was at least a live, correctly-set variable). `diff_head`
       is resolved BEFORE the diff and the diff is computed explicitly against
       IT (not a second, later `HEAD`, which a concurrent commit could make a
       different SHA — code-review round 3, low). It is the tree the reviewers
       are about to read — the pin below must certify THIS SHA, not whatever
       its own independent worktree/branch resolution happens to land on (R3
       doubt-round, medium: the two resolved the tree independently with no
       equality check, so a divergence would let the pin certify a diff nobody
       reviewed — the exact bug R3 exists to prevent). The trigger judgement
       above is what forces the fresh Bash call the top-of-step warning
       names, so `$run_dir` from the block that resolves `$unit_wt` and
       computes the diff is gone here too — the WRITE side needs the same
       re-derivation the READ side already gets, not just the value being
       written (spec-review round 6, blocking: round 5 fixed every re-read
       site but left this one write dereferencing the stale `$run_dir` from
       that same block, so the write itself silently targeted `/fires` and
       the fail-closed guard below STRICT-STOPped every unit on the happy
       path). Dual-write the
       fires decision as the
       literal digit just assigned — it is the third value this paragraph
       hands across the boundary named at the top of this step (`$diff_lines`
       above is the fourth). Re-read `$diff_lines` here too, through the SAME
       re-derived `$run_dir`, and let it RAISE `fires` mechanically — a shell
       `-gt` test, not a sentence — never lower a judgement that already
       said 1 (code-review round 11, high: this statement is what actually
       closes D5; the prose alone, however emphatic, is not a guard). The
       re-read guard is a numeric check, not a bare non-empty test (code-
       review round 12, low: a non-GNU `wc -l`'s leading blanks would pass
       `-n` and then fail `-gt`'s arithmetic silently, skipping the floor):
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         diff_lines=$(cat "$run_dir/diff_lines" 2>/dev/null)
         case "$diff_lines" in ''|*[!0-9]*) STRICT-STOP;; esac   # numeric, not merely non-empty
         fires=<1 or 0>   # substitute the literal digit the risk-flag/medium+ judgement concluded
         [ "$diff_lines" -gt 100 ] && fires=1   # mechanical floor: the judgement above may only RAISE fires, never lower it
         echo "$fires" > "$run_dir/fires" || STRICT-STOP

       **Unit-scoped attribution pin (R3, unconditional).** Resolves THIS
       unit's own `worktree`/`branch`/`attempt_id` from `loop_state.json`
       (`shared/scripts/lib/review_attribution.py`), falling back to the
       campaign worktree when the row carries no `worktree` field (same
       narrow case the `$unit_wt` resolution above falls back on — see there
       for why that is the exception, not the rule, since R2); asserts the
       checked-out branch matches; records
       `HEAD` as `reviewed_head`, `base_sha` at pin time only, and (v5)
       `shipped_head`. Dual-writes the legacy `$run_dir/reviewed_head` file
       (the SAME reviewed_head SHA, immediately — closes the previously
       unpinned window between diff computation and the later commit/push
       below) so a crash before that later write still leaves a pin behind.
       Runs regardless of the trigger above (a PR already exists by this
       point, per the STRICT-STOP above) — `pr_json` crosses the SAME spawn
       boundary as `$unit_wt`/`$diff_head`/`$fires`, so its identity fields
       are resolvable here via the SAME dual-write/re-read below, not by
       trusting shell survival alone (code-review round 5: a prior draft
       claimed these were "always resolvable — never null" on the strength
       of the STRICT-STOP above, which guards existence at CAPTURE time, not
       survival across the boundary) — so a below-threshold unit still
       has a pin `built -> merging` (R4) can verify at merge time — pass
       `--review-skipped` exactly when the trigger above did NOT fire.
       **Which field a later verify uses is fixed, not left ambiguous:** a
       reviewed unit (`fires=1`) is verified via `shipped_head`, recorded
       explicitly by a `--mode ship` call once the reviews.json commit lands
       below (R3 doubt-round, high: a reviewed pin's `shipped_head` stays
       `null` until `ship` records it — `verify --against shipped_head`
       refuses to ALLOW on a `null` value rather than silently falling back to
       a content-blind parent check; today's 3g `--match-head-commit` is a
       git-native equivalent of the SAME check, not a substitute for
       recording it; R4/R5b call `verify --against shipped_head` directly); a
       below-threshold unit (`fires=0`) is verified via `reviewed_head`, since
       no further commit is expected to land on it at all, and its
       `shipped_head` is already set equal to `reviewed_head` at pin time
       (`--review-skipped`). Re-derive `run_dir`, then `$unit_wt`/`$diff_head`/
       `$fires`/`$pr_json` — the dual-writes above exist because the `fires`
       judgement between them and here may have started a fresh Bash call;
       re-reading is safe even when it did not, but only once `run_dir`
       itself is re-derived — it is a shell variable too, and reading
       `$run_dir/unit_worktree` through an EMPTY `$run_dir` silently reads
       `/unit_worktree` instead (code-review round 5, blocking: this was the
       exact gap round 4's fix left open):
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         unit_wt=$(cat "$run_dir/unit_worktree" 2>/dev/null); [ -n "$unit_wt" ] || unit_wt="{project_root}"
         diff_head=$(cat "$run_dir/diff_head" 2>/dev/null); [ -n "$diff_head" ] || STRICT-STOP
         fires=$(cat "$run_dir/fires" 2>/dev/null)
         [ "$fires" = "1" ] || [ "$fires" = "0" ] || STRICT-STOP   # fail closed: anything else means the write above never happened
         pr_json=$(cat "$run_dir/pr_json" 2>/dev/null); [ -n "$pr_json" ] || STRICT-STOP
         pin_json=$(uv run "{shared_root}/scripts/checks/check_review_attribution.py" --mode pin \
           --state "{project_root}/.shipwright/loop_state.json" --unit-id "{id}" \
           --project-root "{project_root}" --campaign-worktree "{project_root}" \
           --loop-id "{loop_id}" --default-branch "{default}" \
           --pr-node-id "$(jq -r .id <<<"$pr_json")" \
           --pr-head-ref "$(jq -r .headRefName <<<"$pr_json")" \
           --pr-base-ref "$(jq -r .baseRefName <<<"$pr_json")" --json \
           $([ "$fires" = "1" ] || echo --review-skipped)) || STRICT-STOP
       Non-zero = STRICT-STOP (as 3f) — an attribution failure (wrong branch
       checked out) means this unit's diff cannot be trusted at all.
       Confirm pin's OWN resolution agrees with the `$unit_wt` already
       resolved above and used for the pre-pin `gh pr view` and the diff (R3,
       spec-review round 2: comparing only `$unit_wt`'s HEAD sha against
       `diff_head`, as the prior draft did, would let a pin that walked a
       DIFFERENT worktree path to the same HEAD sha slip through unnoticed —
       this checks the resolved PATH itself, the "two divergent resolutions"
       hazard directly, not a proxy for it):
         pin_wt=$(jq -r .worktree <<<"$pin_json")
         [ "$pin_wt" = "$unit_wt" ] || STRICT-STOP
       `$run_dir/unit_worktree` already holds this resolution — dual-written
       above, before pin ran — so every later call site in this step and
       every spawn that crosses a shell boundary re-reads it rather than
       re-deriving its own. Then confirm the pin certifies the SAME tree the diff above was
       computed against — an inline check, not prose discipline alone (R3
       doubt-round) — against BOTH pin's own self-reported SHA and
       `$unit_wt`'s actual current HEAD, so a pin that resolved a different
       worktree than the diff read cannot pass on its self-report alone:
         [ "$(jq -r .reviewed_head <<<"$pin_json")" = "$diff_head" ] || STRICT-STOP
         [ "$(git -C "$unit_wt" rev-parse HEAD)" = "$diff_head" ] || STRICT-STOP

       When the trigger did NOT fire: SKIP the rest of 3f-bis, leave the
       runner's `not_run` rows standing (they are honest), and go to 3g — a
       below-threshold sub-iterate must still DELIVER. (The pin above already
       ran with `--review-skipped`, so 3g still has a `reviewed_head` file.)

       Review that same MERGE-BASE diff, never `origin/{default}`'s tip (a moved
       main yields false high findings):

       a) `spec-reviewer`  — Stage 1, HARD-GATE. A REJECT blocks the rest.
       b) `code-reviewer`  — Stage 2, only once Stage 1 PASSES.
       c) `doubt-reviewer` — Stage 3, conditional, advisory-must-address.

       Pass `model=<review tier resolved at loop step 2>` to each of the three
       spawns above (omit when `inherit`). **State the run_id in plain text in
       every spawn prompt** — the `SubagentStop` salvage hook
       (`write-review-payload-on-stop.py`) reads it only from the transcript,
       never an env var. **Write each subagent's reply to its CANONICAL
       payload file — `spec_review_reply.json` / `code_review_reply.json` /
       `doubt_review_reply.json` under `.shipwright/planning/iterate/{run_id}/`
       (trg-3b206c08; `record`'s own `--payload-file` validation rejects any
       other basename) — before any other reasoning or spawning the next
       reviewer.** A mitigation, not a guarantee; the salvage hook backstops
       the window this alone cannot close (see `iteration-reviews.md`).

       Promote the rows IN THAT ORDER. Re-derive `run_dir`, then `$unit_wt`
       from the file dual-written at the top of 3f-bis (code-review round 5:
       a prior draft attributed this file to pin — pin never writes it, this
       step does) — this runs after the a/b/c spawns, the same shell
       boundary `run_dir`/`pr_url` cross below, so the variables set at pin
       time do not survive to here either (code-review round 5: `run_dir`
       itself must be re-derived before the file it names can be read; a
       prior draft read `$run_dir/unit_worktree` here without first
       re-deriving `run_dir`, silently falling back to `{project_root}`):
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         unit_wt=$(cat "$run_dir/unit_worktree"); [ -n "$unit_wt" ] || unit_wt="{project_root}"
       The runner already closed the rows and a closed row is immutable, so
       `--force` is REQUIRED (without it the CLI exits 3). A `code` row
       completed over a non-completed `spec` FAILS the gate, so Stage 1 must
       land first — `…` is the invocation prefix from `iteration-reviews.md`,
       and every call also carries `--model-tier "{resolved_review_tier}"` AND
       `--project-root "$unit_wt"` (R3 doubt-round, round 4, high: overrides
       `…`'s own `{project_root}` default — see the "Unit-scoped, no
       fallback-only exceptions" paragraph above for why). Every call is
       CHECKED: a `record` failure must not fall through to the `git add`
       below on a payload that was never durably recorded:
         … record --project-root "$unit_wt" --review-type spec  --status completed --from spec-reviewer              --payload-file "$unit_wt/.shipwright/planning/iterate/{run_id}/spec_review_reply.json" --recorded-by spec-reviewer --model-tier "{resolved_review_tier}" --force || STRICT-STOP
         … record --project-root "$unit_wt" --review-type code  --status completed --from code-reviewer   … --model-tier "{resolved_review_tier}" --force || STRICT-STOP
         … record --project-root "$unit_wt" --review-type doubt --status completed --from doubt-reviewer  … --model-tier "{resolved_review_tier}" --force || STRICT-STOP

       When Stage 3 does NOT fire (it is conditional), do not leave the runner's
       row standing — its disposition says the cascade did not run, which is now
       FALSE. Re-record it for the reason that actually applies (same
       `--project-root "$unit_wt"` override, same `|| STRICT-STOP`):
         … record --project-root "$unit_wt" --review-type doubt --status not_applicable --force              --disposition "Stage 3 is conditional and did not trigger for this
             diff; Stage 2 passed at 3f-bis" || STRICT-STOP

       Then ship the record with the PR. `run_dir`/`pr_url`/`unit_wt` were
       set BEFORE the a/b/c spawns above and this block runs AFTER them —
       re-derive all three here, exactly as 3g does below, rather than trust
       shell state across that boundary (R3 doubt-round, round 2, medium:
       `run_dir`/`pr_url` are re-derived from scratch here, so which boundary
       they crossed is moot; `$diff_head`/`$fires`/`$pr_json` cross the
       earlier `fires`-judgement boundary and are handled by the dual-writes
       above; `$unit_wt` crosses BOTH, which is why it is re-read from its
       file here as well):
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         unit_wt=$(cat "$run_dir/unit_worktree"); [ -n "$unit_wt" ] || unit_wt="{project_root}"
         pr_url=$(cd "$unit_wt" && gh pr view "{branch}" --json url -q .url)
         [ -n "$pr_url" ] && [ "$pr_url" != "null" ] || STRICT-STOP   # mirrors the pre-pin guard (code-review round 4, low)
       Every command is CHECKED: a promotion that does not reach the remote
       must STOP the loop, not shorten it. An unchecked `git commit` that the
       pre-commit hook blocks would otherwise leave the runner's head in
       place, the local record saying `completed`, and main saying
       `not_run` — the cascade silently un-shipped:
         git -C "$unit_wt" add ".shipwright/planning/iterate/{run_id}/reviews.json" || STRICT-STOP
         git -C "$unit_wt" commit -m "chore(review): record the delegated cascade for {id}" -- ".shipwright/planning/iterate/{run_id}/reviews.json" || STRICT-STOP
         git -C "$unit_wt" push || STRICT-STOP
         shipped_head=$(git -C "$unit_wt" rev-parse HEAD)
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         echo "$shipped_head" > "$run_dir/shipped_head" || STRICT-STOP
       `git commit` with no pathspec commits the WHOLE index, so any other
       pre-existing staged content would ride along inside the commit whose
       entire purpose is to certify that a review happened — the `add` above
       is CHECKED and the commit is scoped to reviews.json's own path (R3
       doubt-round, round 4, low). Record the shipped SHA into the pin BEFORE
       touching the legacy file
       (R3 doubt-round, round 2, medium: ship-then-write, not write-then-ship
       — a STRICT-STOPped ship must never leave the legacy file holding a SHA
       the guard refused, which a human resuming at 3g would otherwise
       `--match-head-commit` on). Nothing had ever written `review_pin.json`'s
       own `shipped_head` field before this sub-iterate, so
       `verify --against shipped_head` fell back to a content-blind
       parent-of-tip check for every reviewed unit — silently weaker than the
       `--match-head-commit` it exists to replace. Not run for a
       `--review-skipped` unit: `pin` already set that unit's `shipped_head`
       equal to `reviewed_head`, and no further commit is expected on it.
       `$shipped_head` is dual-written above and re-read here through a
       re-derived `$run_dir` (R3 doubt-round, round 4, medium: the same
       treatment `$unit_wt`/`$diff_head`/`$fires`/`$pr_json` get above, applied
       here too rather than argued about — whether a genuine boundary
       separates the git push from this `ship` call is exactly the kind of
       ambiguity that drew three consecutive REJECTs on this class; closing it
       costs one file instead of resolving it in prose):
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         shipped_head=$(cat "$run_dir/shipped_head" 2>/dev/null); [ -n "$shipped_head" ] || STRICT-STOP
         uv run "{shared_root}/scripts/checks/check_review_attribution.py" --mode ship \
           --state "{project_root}/.shipwright/loop_state.json" --unit-id "{id}" \
           --project-root "{project_root}" --campaign-worktree "{project_root}" \
           --loop-id "{loop_id}" --shipped-head "$shipped_head" || STRICT-STOP
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         shipped_head=$(cat "$run_dir/shipped_head" 2>/dev/null); [ -n "$shipped_head" ] || STRICT-STOP
         echo "$shipped_head" > "$run_dir/reviewed_head" || STRICT-STOP

       **This push restarts CI**, so 3g must watch THIS head. Wait for the PR
       object to catch up — BOUNDED, because an unbounded wait is a third
       outcome the loop has no name for (neither delivered nor stopped):
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         for i in $(seq 1 60); do
           [ "$(gh pr view "$pr_url" --json headRefOid -q .headRefOid)" = "$(cat "$run_dir/reviewed_head")" ] && break
           sleep 5
         done
         [ "$(gh pr view "$pr_url" --json headRefOid -q .headRefOid)" = "$(cat "$run_dir/reviewed_head")" ] || STRICT-STOP
         # the loop above only ever `break`s early on a match; without this
         # re-check after it, exhausting the cap falls through to 3g with a
         # stale head instead of stopping (R3 doubt-round, round 3 — Stage-3
         # external review caught the same missing re-check at 3g below).

       On a Stage-1 REJECT, or a Stage-2 high finding left unaddressed:
       STRICT-STOP exactly as 3f/3g — do NOT merge, do NOT build the next. The
       already-merged sub-iterates stay durable; this PR is left OPEN so a human
       can repair it. "Addressing" a Stage-2 finding means a NEW commit on top
       of the pinned tree — which the `--mode ship` ancestry check above
       refuses BY DESIGN (R3 doubt-round, round 2, medium: the fix commit's
       parent is not `reviewed_head`, so `ship` STRICT-STOPs after the push,
       leaving a `completed` record on a diff nobody actually reviewed). The
       repair path is never "commit a fix here" — it is restarting 3f-bis
       from the top (the `rm -f` of the legacy `reviewed_head` file at this
       step's own start, re-diff, re-pin, re-run the cascade on the fixed
       tree) so the record and the reviewed diff agree again.

       SHIP the REJECT before stopping, or the durable record stays the runner's
       `not_run` and the left-open PR reads as merely unreviewed rather than
       REJECTED. `completed` is wrong here — the native Stage-1 payload stores
       `spec_citations` and drops `verdict`, so a `completed` REJECT is
       byte-indistinguishable from a PASS to the next reader, human or gate.
       This branch never reaches the ship path's own `run_dir` re-derivation
       above (it SKIPS ship entirely on a REJECT), so it re-derives its own
       here — the identical gap as the promote-rows block above, on a
       separate branch (code-review round 5, blocking):
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         unit_wt=$(cat "$run_dir/unit_worktree"); [ -n "$unit_wt" ] || unit_wt="{project_root}"
         … record --project-root "$unit_wt" --review-type spec --status not_run --force \
             --recorded-by spec-reviewer \
             --disposition "Stage-1 spec-reviewer REJECTED at 3f-bis: {the
             citations, spec_ref -> divergence}. Delivery stopped; PR left open." || STRICT-STOP
         git -C "$unit_wt" add ".shipwright/planning/iterate/{run_id}/reviews.json" || STRICT-STOP
         git -C "$unit_wt" commit -m "chore(review): record the Stage-1 REJECT for {id}" -- ".shipwright/planning/iterate/{run_id}/reviews.json" || STRICT-STOP
         git -C "$unit_wt" push || STRICT-STOP
       Then STRICT-STOP. The unconditional pin above already wrote a
       `reviewed_head` — that pinned diff is what was REJECTED; nothing may
       ship on top of it, and 3g never reaches this PR because the loop
       already stopped.

   3g. MERGE this sub-iterate's PR — verify CI-green first, then merge, one at a
       time (no shoot-and-forget). The orchestrator owns the merge (the PR did not
       self-arm, step 1):
         # Re-resolve from the branch: shell state does NOT survive between steps,
         # so nothing set in 3f-bis is still in the environment here.
         # The pin comes from 3f-bis's FILE (R3: written UNCONDITIONALLY now,
         # by check_review_attribution.py pin — even a below-threshold unit
         # that skipped the cascade gets one, with --review-skipped).
         run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"
         # By this point 3f-bis's post-record-commit write ("echo $shipped_head
         # > reviewed_head") has overwritten this file with the SHIPPED head,
         # not the original pin's reviewed_head. Its absence is no longer
         # tolerated (R3 doubt-round, high): the unconditional pin at 3f-bis
         # — itself STRICT-STOP-guarded — means every unit that reaches this
         # line has one, reviewed or skipped; a missing file means an earlier
         # guard should already have stopped the loop, so merging anyway would
         # be the exact unpinned merge the spec's acceptance criterion forbids.
         [ -f "$run_dir/reviewed_head" ] || STRICT-STOP
         # File EXISTENCE alone only proves pin ran — pin writes this file
         # UNCONDITIONALLY and BEFORE the review cascade even starts, so it
         # holds a SHA equal to the remote tip throughout the ENTIRE cascade
         # window, including every STRICT-STOP inside it (R3 doubt-round,
         # round 4, medium: a human or a resumed orchestrator invoking 3g
         # directly during/after an interrupted cascade would see this file
         # present and a matching --match-head-commit below, and merge an
         # unreviewed diff). verify --against shipped_head additionally
         # BLOCKs a reviewed (non-skipped) unit whose shipped_head was never
         # recorded — i.e. the cascade never actually shipped a record
         # commit — which file-existence alone cannot distinguish from a
         # genuine completed review; for a --review-skipped unit the same
         # call checks branch-tip-equals-reviewed_head instead (its own
         # internal branch, not a separate call here):
         uv run "{shared_root}/scripts/checks/check_review_attribution.py" --mode verify \
           --state "{project_root}/.shipwright/loop_state.json" --unit-id "{id}" \
           --project-root "{project_root}" --campaign-worktree "{project_root}" \
           --loop-id "{loop_id}" --against shipped_head || STRICT-STOP
         # Same unit-scoping as 3f-bis (R3): read $unit_wt back from the FILE
         # 3f-bis dual-wrote there (pin never writes this one — code-review
         # round 5) — a fresh Bash call, so nothing set in 3f-bis's own
         # shell survives to here — falling back to {project_root} if the file
         # is absent OR empty (a bare `2>/dev/null || echo` fallback catches
         # only a missing file, not a present-but-empty one — code-review
         # round 4, low).
         unit_wt=$(cat "$run_dir/unit_worktree" 2>/dev/null); [ -n "$unit_wt" ] || unit_wt="{project_root}"
         # $pr_url here is a fresh `gh pr view` call, not a value read from
         # 3f-bis's own $pr_url (R3 doubt-round, round 4, medium: unlike
         # $shipped_head above, there is no cross-step variable to dual-write
         # for this one — 3g always re-derives its own).
         pr_url=$(cd "$unit_wt" && gh pr view "{branch}" --json url -q .url)
         head_pin="--match-head-commit $(cat "$run_dir/reviewed_head")"
         uv run "{shared_root}/scripts/checks/check_campaign_session_lock.py" touch --campaign-worktree "{project_root}" --session-id "$SHIPWRIGHT_SESSION_ID" || LOCK-LOST  # as 3a — NOT step 4; --watch below is UNBOUNDED, 3a's heartbeat alone can't cover it
         gh pr checks "$pr_url" --watch || STRICT-STOP   # as 3f: do not merge, do not build the next; surface to the user. Merged subs stay durable.
         gh pr merge "$pr_url" --squash --delete-branch $head_pin || STRICT-STOP
         #   a merge refusal (e.g. $head_pin no longer matches the remote tip)
         #   must STOP, not fall through to an unbounded wait for a state that
         #   will never arrive (R3 doubt-round, round 2, low).
         for i in $(seq 1 60); do
           [ "$(gh pr view "$pr_url" --json state -q .state)" = "MERGED" ] && break
           sleep 5
         done
         [ "$(gh pr view "$pr_url" --json state -q .state)" = "MERGED" ] || STRICT-STOP
         # the loop above only ever `break`s early on MERGED; without this
         # re-check after it, exhausting the cap falls through to 3h with the
         # PR still open instead of stopping — a "third outcome" the loop has
         # no name for (neither delivered nor stopped) is exactly what this
         # bounded wait exists to rule out (Stage-3 external review, R3 PR
         # #787: flagged as a real control-flow defect, not prose-only).
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
   uv run "{shared_root}/scripts/checks/check_campaign_session_lock.py" release --campaign-worktree "{project_root}" --session-id "$SHIPWRIGHT_SESSION_ID"
   uv run ... finalize --state .shipwright/loop_state.json
   ```
   Release FIRST, always, on every path that reaches step 4 (never on the LOCK-LOST path above, which never reaches step 4 at all) — a no-op if this session doesn't hold the lock, so a completed or abandoned-and-repaired campaign never blocks a later, brand-new `SHIPWRIGHT_SESSION_ID` for up to `stale_after_seconds` (references/campaign-worktree.md, "the release step").
   The campaign's top-level lifecycle status reaches `complete`
   **automatically** once every sub-iterate is `complete` — the never-downgrade projection
   (`campaign_status.all_subs_complete`) sets it in the per-tree `status.json` the LAST
   sub-iterate's F5b commits (the durable path, S3), and the local 3h `update-status`
   mirrors it for the live orchestrator view. A `complete` campaign is hidden from the
   board. If the loop strict-stopped on a failure / escalation / non-delivered PR (3f/3g),
   some sub-iterates are not `complete`, so the status stays `active` and the campaign
   remains visible. No explicit set-complete call is needed.

5. **Release prompt (F12, once):** Only if ALL sub-iterates are
   `complete` AND worktree is clean: count unreleased entries in
   `CHANGELOG.md`. If > 0: *"Run /shipwright-changelog to tag a release?"*
   If any sub-iterate failed, escalated, or its PR did not deliver:
   *"Campaign incomplete; no release prompt."*

**When NOT using `--autonomous`:** skip this section entirely, proceed
with normal single-iterate flow.

---

## Step 3.4 — Diff-Driven Risk Re-Check (runner contract)

See `references/campaign-step-3-4-risk-recheck.md` for the full procedure:
the gap it closes (a campaign unit classifies complexity once, from spec
text, before Stage-2 Repo Scout ever runs, so every diff-driven risk
detector is structurally silent), the two failure shapes that follow from
missing it, and the CI-supply-chain-ack authorship guard (the runner must
never write its own acknowledgement — checked, not only stated in prose,
after trg-33d30377 / PR #718).
