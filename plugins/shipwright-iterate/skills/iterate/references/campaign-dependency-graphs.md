# Dependency Graphs (`depends_on`)

campaign-dag-scheduler R1. `campaign.md`'s `## Sub-Iterates` table gains an
optional `Depends On` column, header-indexed (any position; a table with no
recognizable header falls back to the legacy fixed id/slug/title positions,
`depends_on` defaulting to `[]`).

- **Cell grammar:** comma-separated bare sub-iterate ids; an empty cell is
  `[]`. Markdown emphasis is stripped per token, matching the id/slug cells'
  existing treatment (`` **A**, `B` `` -> `["A", "B"]`).
- **Id charset (`id_charset_ok`):** `[A-Za-z0-9._-]`, bounded to 64 chars, no
  leading/trailing separator, no `..` segment, no literal `--` (reserved as
  the campaign-slug/unit-id path separator — R2's per-unit worktree naming).
  `R0` / `15.0` / `14.2` / `p3.8` all pass.
- **Case-insensitive collision (external plan review, both reviewers
  converged):** `validate_dependency_graph` folds case for BOTH duplicate-id
  detection and `depends_on` existence resolution — `R0` and `r0` are a
  structural duplicate even though each independently passes the charset
  check, because Windows worktree directories case-fold (R2's per-unit
  worktree naming would otherwise collide on disk); a `depends_on: [r0]`
  referencing `R0` resolves correctly rather than reporting a spurious
  "unknown id". Messages always keep the author's original casing.
- **Severity is scope-dependent, not a single global rule:** `campaign_init.py`
  hard-rejects BOTH a structural violation (duplicate id / unknown reference /
  self-dependency / cycle of any length) AND a charset violation at WRITE
  time — this is where "canonical" is actually enforced. The READ side
  (`lib.campaign_graph.safe_project_campaign_status`, the resume-safe
  projector `campaign_progress.py`'s callers use) treats a structural
  violation as a hard degrade (see below) but only WARNS on charset, since a
  pre-existing campaign.md predating this schema must still project.
- **Frozen-on-claim rule:** once a unit's `loop_state.json` row leaves
  `pending` (`in_progress` / `merged` / `failed`), its `depends_on` can no
  longer change — a later edit to that unit's row in `campaign.md` is
  reverted to the frozen value, and a `warnings` entry names it. This
  degrades ONLY that one unit's row, never the whole campaign projection —
  a single bad edit must never brick unrelated DAG branches. A `pending`
  unit's dependencies remain freely editable up to the moment it's claimed.
- **Degraded side-channel:** `safe_project_campaign_status` returns
  `(status, summary)` exactly like `regenerate_campaign_status` — on a
  structural violation it returns the LAST SUCCESSFUL `status.json`
  verbatim, plus a `summary["degraded_reason"]` string and a `warnings`
  entry. It never invents a new top-level `status` token (that enum is also
  consumed by the out-of-scope WebUI repo).
- **Readiness (`lib.loop_state.is_unit_ready`):** every one of a unit's
  `depends_on` ids must be `merged` in `loop_state.json` — with its
  `merged_commit` VERIFIED by a fresh fetch-then-ancestry-check against
  `origin/<default>`, never trusted blindly from a stale record. A dependency
  that no longer exists in the campaign (a stale edge) blocks rather than
  being silently ignored; `describe_blocker` names the specific blocking
  unit/edge for operator-facing messages.
- **KNOWN LIMITATION — squash-merge SHA mismatch (external plan review,
  flagged for R4/R5b to close):** step 3g merges via `gh pr merge --squash`,
  which mints a BRAND NEW commit on `origin/<default>`; the pre-merge branch
  commit `update-status --commit {commit}` records at step 3h is genuinely
  NEVER an ancestor of `origin/<default>` afterward (unlike a fast-forward or
  a true merge). Until a later sub-iterate teaches step 3h to record the
  ACTUAL post-merge SHA (`gh pr view --json mergeCommit -q .mergeCommit.oid`
  after 3g, not the runner's own pre-merge commit), `verify_merged_commit_ancestry`
  correctly-but-uselessly returns unverified for every REAL squash-merged
  unit — `depends_on` gating degrades SAFELY (stays blocked, never falsely
  unblocks) but is not yet load-bearing end to end against a live campaign.
- **`cmd_next`'s narrow guard (R1 — the interim window before R4/R5a):**
  `autonomous_loop.py::cmd_next` gained ONE `kind == "sub_iterate"`-gated
  guard clause: a `pending` unit that `is_unit_ready` rejects is skipped in
  favor of the next FIFO candidate, exactly as if it weren't there. No new
  flag, no new exit code on `cmd_next` itself — `kind == "section"`
  (shipwright-build) is completely untouched. **Doubt review correction
  (high, campaign-dag-scheduler R1 3f-bis):** this guard is NOT a working
  resume-safety net today — it is currently inert on BOTH paths a campaign
  can take. Within one continuous run a unit's `loop_state.json` row stays
  `complete` (never flips to `merged` mid-run); the mapping only applies at
  a fresh `cmd_init`. But a genuinely fresh `cmd_init` does not close the
  gap either: nothing anywhere writes a unit's status as `merged` WITH a
  truthy `merged_commit` — the bullet above's squash-merge SHA-mismatch
  limitation means `verify_merged_commit_ancestry` returns `None` for every
  real squash-merged unit on that path too, so `is_unit_ready` is `False`
  for every `depends_on` edge, in every code path, until R4/R5b's
  `cmd_mark_merged` lands. R1 is schema + validators + a correctly
  fail-closed predicate, not a working gate yet, on any path. If EVERY
  remaining pending unit is blocked,
  `cmd_next` falls through to its existing `{"done": true}` / exit 2 tail. In
  a REAL single-session campaign with any `depends_on` edge, a dependent that
  would previously have simply built (no gating existed) now does not build
  at that pass (external code review, round 4, GLM — "R1 actively breaks
  single-session campaigns"; independently converged on across 4 review
  rounds). **This no longer silently finalizes as done** — the orchestrator's
  step 3a checks `blocked_pending_ids` before Finalize and STOPs instead (see
  "Exit 2 is not always done" below) — but the dependent still never gets
  BUILT within that run; closing that requires the same live promotion
  mechanism below. This is accepted as an interim-window gap ONLY because the
  one safe fix requires the REAL post-merge promotion mechanism the plan
  already assigns to R4/R5b (`loop_claim.py::cmd_mark_merged`, fencing-token
  + hex-SHA validated) — a "trust `cmd_record`'s own pre-merge commit"
  shortcut was evaluated and rejected as unsafe (it would let a dependent
  start on a unit that merely finished its OWN build/tests but never passed
  PR review, the exact "wrongly unblocked" failure mode this whole mechanism
  exists to prevent). **Before building further campaign work that assumes
  `depends_on` gating is live-effective within one continuous run, the
  campaign owner should explicitly decide: accept this gap through R4/R5b,
  or pull `cmd_mark_merged`'s live-promotion piece forward into an R1.5.**
  (R4's `cmd_next_batch` is where exit code `4` correctly distinguishes
  "blocked" from "finished" for its OWN callers — that alone does not close
  this gap unless something also performs the live `complete -> merged`
  promotion after a real merge.)
  **Observable, not silent (external plan review, GLM finding):** the exit
  code stays 2 unchanged, but the printed JSON now additionally carries
  `blocked_pending_ids` + `blockers` (via `describe_blocker`) whenever a
  `pending`-but-blocked unit remains at that fallthrough — a log reader is no
  longer blind to "campaign silently stalled, not actually finished".

### Exit 2 is not always done

**External Tier-3 PR review (block, campaign-dag-scheduler R1):** leaving the
orchestrator's step 3a to treat every exit `2` as unconditional Finalize was
rejected as a live correctness bug, not merely a documented interim gap — a
`depends_on` campaign run before R4/R5b lands would silently finalize with
pending, never-built units. `campaign-mode.md` step 3a now reads the JSON
body FIRST: a non-empty `blocked_pending_ids` means the campaign is STALLED,
not complete — the orchestrator STOPs and reports `blockers` instead of
finalizing. This is wired in THIS sub-iterate (not deferred to R4/R5a); R4's
`cmd_next_batch` + exit code `4` later gives its OWN callers a distinct
exit code for the same distinction, but does not supersede this check for
`cmd_next`'s existing callers.

## Exit-code loop-action table

`campaign-mode.md` step 3a; extended by R4/R5b as those sub-iterates land:

| Exit code | Command | Meaning | Orchestrator action |
|---|---|---|---|
| `0` | `next` | Unit claimed | Proceed to spawn (step 3c) |
| `2` | `next` | All units processed, OR all remaining `pending` units are blocked on an unmerged `depends_on` edge | Check `blocked_pending_ids` first: non-empty → STALLED, STOP and report `blockers` (do not finalize); empty/absent → Finalize (step 4) |
| `3` | `record` | Failure/escalation | STRICT-STOP: Finalize (step 4), do not merge, do not build the next |
| `4` (R4) | `cmd_next_batch` | Ready set empty, `pending` units remain — by construction every independent branch already scheduled, so the rest are exactly `describe_blocker`'s transitively-blocked set | Sweep that set to `held` (`reason_code: "swept_never_started"`), name the blocker to the operator, then Finalize |
| `5` (R4, at `cmd_record`) | `record` | This unit's payload discarded, reclaim rule applied | Continue processing the rest of the wave — never a loop-level stop |
| `6` (R4) | — | Lock-lost-style condition | One bounded retry, then stop with no state write |
