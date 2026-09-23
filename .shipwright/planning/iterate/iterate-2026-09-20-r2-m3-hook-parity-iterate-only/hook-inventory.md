# Hook Inventory — R2 (M3, `codex-plugin-execution-reliability`)

Static audit of every hook registered across all `plugins/*/hooks/hooks.json`
files, classified into the three relevance tiers `Spec/codex-runtime-integration-spec.md`
§M3 defines:

1. **global-safe** — may run for any Codex session; no selector needed at all.
2. **durable-state selected** — the hook's relevance/behavior is derivable
   from artifacts already on disk (`run_config.json`, phase-task state,
   `triage.jsonl`, compliance ledger, a review record, a run pointer) — it
   does not need to know which skill/slash-command was literally invoked
   this turn, only what state already exists.
3. **explicit-activation-required** — the hook truly needs current-skill
   identity that no durable artifact can supply (the chicken-and-egg case:
   nothing is written to disk yet at the moment identity would be needed).

**Scope note:** this is the STATIC part of Step 11 only. The "recommended
starting point for R2b" section below is a deliberate placeholder — it needs
Step 2/10's still-deferred live payload-capture probe (Stop-payload shape,
`iterate_stop_finalize.py`'s behavior under a real Codex Stop payload) before
it can be filled in honestly, per this run's own sequencing. This audit is
otherwise complete: every one of the 14 plugin directories was checked, and
the 12 that carry a `hooks.json` were read directly (not inferred from
`docs/hooks-and-pipeline.md`'s prose, which can drift from the actual JSON —
though that doc was used as a cross-reference for behavior descriptions).

## Plugin coverage

14 plugin directories exist under `plugins/`. **12 carry a `hooks.json`**;
`shipwright-grade` and `shipwright-preview` do not — confirmed via direct
directory listing, not an oversight in this audit. Nothing to classify for
those two.

## Per-tool-class matcher inventory

Every distinct `matcher` value found across all 12 files, by event:

| Event | Matchers in use |
|---|---|
| `SessionStart` | none (bare — fires for every session) |
| `UserPromptSubmit` | none (bare) — only `shipwright-iterate` registers this event |
| `PreToolUse` | `Bash` (shipwright-build, shipwright-compliance). shipwright-iterate's new gate (§R2) was originally a none/catch-all entry here too; it now registers Codex-only via `hooks-codex/hooks.json` (see "Runtime-scoped registration" below) and no longer appears in this audit's Claude-visible `hooks.json` set at all |
| `PostToolUse` | `Write\|Edit` (all 12 plugins); none/catch-all (shipwright-build's `track_tool_calls.py`); `Write\|Edit\|Bash` (shipwright-iterate's `mark_implementation_span.py`) |
| `Stop` | none (bare — fires for every session) |
| `SubagentStop` | agent-identity matchers only: `shipwright-build:spec-reviewer`, `shipwright-build:code-reviewer`, `shipwright-build:doubt-reviewer`, `shipwright-plan:section-writer` |

No plugin uses a matcher shape beyond these (no regex, no other tool-name
combination). The R1b Codex-bundle merge path (`codex_hook_inventory.py`)
buckets by `(event, matcher)` tuple — confirmed during Step 8's review that
`("PreToolUse", "Bash")` and `("PreToolUse", None)` survive as independent,
non-colliding groups in the built bundle, so this matcher set poses no known
merge-collision risk.

## Tier classification

### Tier 1 — global-safe (17 distinct scripts)

No selector needed; safe to run unconditionally on every session regardless
of what's being worked on. Mostly repo-wide hygiene/infra/telemetry that
already runs identically for every Claude session today, irrespective of
which of the 14 phase plugins is nominally active.

| Script | Event | Registered in |
|---|---|---|
| `run_if_cache_ready.py` | SessionStart | all 12 |
| `capture_session_id.py` | SessionStart | all 12 |
| `check_artifact_drift.py` | SessionStart | all 12 |
| `session_start_using_shipwright.py` | SessionStart | all 12 |
| `check_drift.py` | SessionStart | build, iterate, security |
| `check_file_size.py` | PostToolUse (`Write\|Edit`) | all 12 |
| `mark_plugin_edit.py` | PostToolUse (`Write\|Edit`) | all 12 |
| `validate_command.sh` | PreToolUse (`Bash`) | build |
| `check_secrets.sh` | PostToolUse (`Write\|Edit`) | build |
| `check_destructive_migration.sh` | PostToolUse (`Write\|Edit`) | build |
| `track_tool_calls.py` | PostToolUse (catch-all) | build |
| `bloat_gate_on_stop.py` | Stop | all 12 |
| `plugin_sync_reminder_on_stop.py` | Stop | all 12 |
| `generate_handoff_on_stop.py` | Stop | all 12 |
| `write_terminal_marker.py` | Stop | build, iterate |
| `track_context_cost.py` | Stop | build |
| `import_github_findings.py` | SessionStart | iterate |

Reasoning: each of these either inspects the tool-call/file content directly
(`validate_command.sh`, `check_secrets.sh`, `check_destructive_migration.sh`,
`check_file_size.py`), does generic session bookkeeping with no gating logic
at all (`capture_session_id.py`, `write_terminal_marker.py`,
`track_context_cost.py`, `track_tool_calls.py`), or performs a repo-wide
self-check independent of any particular skill (`check_drift.py`,
`check_artifact_drift.py`, `plugin_sync_reminder_on_stop.py`,
`bloat_gate_on_stop.py`, `import_github_findings.py`,
`generate_handoff_on_stop.py`, `run_if_cache_ready.py`,
`session_start_using_shipwright.py`, `mark_plugin_edit.py`).

### Tier 2 — durable-state selected (14 distinct scripts: 11 unconditional + 3 `SubagentStop`-matched, caveated below)

| Script | Event | Selector source |
|---|---|---|
| `audit_phase_quality_on_stop.py` | Stop | `phase_tasks[]`/`run.status` in durable run state |
| `audit_compliance_on_stop.py` | Stop | resolves the active iterate worktree via the run pointer (per its own docs row) |
| `check_required_checks_hook.py` | SessionStart | repo/CI required-checks state file |
| `check_rtm_coverage.py` | PreToolUse (`Bash`) | RTM/compliance durable state, gates only on a `git commit`-shaped call |
| `check_security_scan.py` | PreToolUse (`Bash`) | security-scan durable state, same gating shape |

> **Scope-broadening note for R2b — corrected:** an earlier pass of this note
> claimed these two only fire "within `shipwright-compliance`'s own plugin
> scope" under Claude Code. That premise is wrong: per
> `docs/hooks-and-pipeline.md`'s "Fan-out consolidation" section, Claude Code
> already fires every *enabled* plugin's hooks with no active-plugin filter —
> with `shipwright-compliance` enabled (the normal case; all 14 phase plugins
> install together) these two already fire on every `git commit`/deploy-shaped
> Bash call in every Claude session today, regardless of which workflow is
> nominally active. **What Codex's merged bundle actually broadens is PROJECT
> scope, not plugin scope:** its build writes one GLOBAL `~/.codex/hooks.json`
> (R1b), so the same two hooks fire on every matching Bash call in every Codex
> session on the machine, including sessions in unrelated repos that have
> nothing to do with this Shipwright project — a reach Claude's per-project
> plugin-cache install never had. That is the real scope-broadening worth
> flagging for R2b, independent of R2's own activation-record work, and it
> doesn't change either script's tier classification.
| `master_stop_check.py` | Stop | `phase_tasks[]`/`run.status` (v2 pipeline, observational only) |
| `check_documentation.py` | Stop | documentation-artifact state |
| `iterate_stop_finalize.py` | Stop | "resolves the session's active iterate worktree via the run pointer" (docs, verbatim) |
| `aggregate_triage_on_stop.py` | Stop | `.shipwright/triage.jsonl` |
| `mark_implementation_span.py` | PostToolUse (`Write\|Edit\|Bash`) | "the same per-session pointer B1a writes" (docs, verbatim) |
| `suggest_iterate.py` | UserPromptSubmit | project completion state (`shipwright_run_config.json`) + this turn's prompt text — does not need "which skill is active", only "is this project done and does the prompt look like a change request" |

**Caveated sub-group — the three `SubagentStop`-matched scripts:**

| Script | Matcher |
|---|---|
| `write-review-payload-on-stop.py` | `shipwright-build:spec-reviewer` / `:code-reviewer` / `:doubt-reviewer` |
| `cleanup-review-scratch-on-code-reviewer-failure.py` | `shipwright-build:code-reviewer` |
| `write-section-on-stop.py` | `shipwright-plan:section-writer` |

These are matched by Claude's own native `subagent_type` field on the
`SubagentStop` event — a per-call selector, not session-wide durable state,
so they fit the *spirit* of tier 2 (the selector is intrinsic to the
triggering event itself, no explicit-activation protocol needed) rather than
tier 1 or tier 3. **However, this audit found no confirmation that Codex's
hook system exposes an equivalent event at all** — R0's live probes
(cited in the mini-plan) confirmed only that Codex's `Agent`-class
`PreToolUse`/`PostToolUse` matcher also catches `spawn_agent`-shaped tool
calls, which is a different claim than "a `SubagentStop`-equivalent event
exists, fires after a sub-agent's own turn ends, and carries an
agent-identity-shaped matcher Codex can match on." This is a genuine open
question, not a live-probe-dependent answer being deferred out of laziness —
it's static uncertainty about Codex's hook *event* vocabulary, not about
this session's activation state. Recorded here for R2b/Step 2's live probe
to settle, not assumed either way.

### Tier 3 — explicit-activation-required (2 scripts, both new this run)

| Script | Event | Why durable state can't supply this |
|---|---|---|
| `codex_activation_mint.py` | UserPromptSubmit | "was THIS session's first prompt literally an iterate-envelope invocation" cannot be derived from any pre-existing artifact — nothing is written yet at the moment identity would be needed; this is the mint event itself |
| `codex_pretooluse_gate.py` | PreToolUse | consumes the record `codex_activation_mint.py` just minted; the whole reason R2 exists is that no durable artifact could answer this before R2 built one |

This is the correct, minimal set — R2's own design work (documented in this
run's `iterate-spec.md`) already established that these two are the only
hooks in the current inventory needing the new protocol; this audit's job
was to confirm the other 29 scripts genuinely don't, not to re-derive the
two from scratch, and that confirmation holds: no other script's decision
depends on same-turn skill identity that isn't already recoverable from a
durable artifact or a native per-call event field.

**Runtime-scoped registration (rule, settled mid-R2 after a design
pushback):** both Tier 3 scripts were first shipped as catch-all entries in
`plugins/shipwright-iterate/hooks/hooks.json` (matcher-less, so Claude Code
spawned a process for them on literally every tool call of every session,
Codex-only usefulness notwithstanding — code review flagged the per-call
cost this imposed on every Claude session for a check only Codex needs).
The fix is a second, sibling manifest,
`plugins/shipwright-iterate/hooks-codex/hooks.json`, read only by the Codex
bundle build (`codex_hook_inventory.py::_load_hooks`) and never by Claude
Code's own loader (a fixed, out-of-Shipwright's-control convention: Claude
only ever reads `hooks/hooks.json`). **Tier 3 registers Codex-only, in
`hooks-codex/hooks.json`; Tiers 1-2 stay in the shared `hooks/hooks.json`**
— Tier 1/2 scripts are useful (or already fire) under both runtimes, so
splitting them would only add a file with no cost benefit. This makes the
"zero cost under Claude" property of Tier 3 actually true instead of merely
intended.

## Summary counts

- **17** global-safe
- **14** durable-state selected (11 unconditionally + 3 caveated pending the
  `SubagentStop`-event-support question)
- **2** explicit-activation-required (both built and shipped in this run)
- **33** total distinct hook scripts across the 12 `hooks.json` files

## Doubt-review resolution (Stage 3, this run)

Four doubts raised against the activation protocol and the `hooks-codex`
split; addressed here rather than re-litigated inline at each call site.

- **HIGH, "zero cost under Claude" claim was asserted, not verified" —
  RESOLVED, verified.** Checked against Claude Code's own official plugin
  docs (`plugins-reference.md`, `hooks.md`): the loader reads hooks from
  exactly two places — `<plugin-root>/hooks/hooks.json`, or a `hooks` field
  embedded directly in `.claude-plugin/plugin.json` — never by scanning or
  globbing the plugin tree for other hooks.json-shaped files. `hooks-codex/`
  is therefore structurally invisible to it, not merely unobserved-so-far.
  This doesn't retroactively excuse the prior "scoped to one plugin" error
  this same run corrected elsewhere (a doc claim vs. a documented API
  contract are different confidence levels) — but this one now rests on the
  latter, not an internal assumption.
- **HIGH, the fail-open `consume()` race lets a losing/duplicate PreToolUse
  invocation through with zero inspection of its own payload — accepted
  residual risk, not fixed here.** True as described: whichever invocation
  loses the `.consumed` exclusive-create is unconditionally treated as
  "already correctly settled," identically to the normal single-call case,
  with no re-evaluation of that invocation's own `tool_input`. This is the
  SAME "cooperative enforcement, not an adversarial boundary" threat model
  already accepted for the matcher's basename-only bypass (R0's Contract,
  restated in `codex_pretooluse_gate.py`'s own module docstring) — extended
  here to a dispatch-concurrency assumption instead of a parse-precision one.
  Codex's actual PreToolUse dispatch concurrency (does it ever issue a
  batched/parallel call, or retry a slow hook invocation while the original
  is still pending?) is exactly the class of fact this run's own deferred
  live probe below exists to establish; a design choice cannot be tightened
  correctly against an unconfirmed dispatch model without risking solving
  the wrong problem. **R2b inherits this as a second required question for
  its live proof**, alongside the `SubagentStop`-equivalent-event question
  already deferred there.
- **MEDIUM, no purge/GC for activation-record files — FIXED.**
  `codex_activation_record.py` now has `_purge_expired_records`, mirroring
  `lib.event_once._purge_expired_claims`; runs opportunistically from
  `mint()`'s exclusive-create path (once per new session, not per turn).
- **MEDIUM, redundant `normalize_cwd()` subprocess calls on every turn for
  the whole session, even long after settlement — PARTIALLY fixed; residual
  cost corrected here (external review, glm medium: the doubt-review's own
  "FIXED... collapsed to once per session" claim below was not fully true).**
  `mint()`/`consume()` (the library, `codex_activation_record.py`) now
  short-circuit on a plain `Path.exists()` check before doing any INTERNAL
  `normalize_cwd()` work — this did eliminate the duplicate call each
  function previously made to build/compare a record. **But the two hook
  wrappers** (`codex_activation_mint.py`, `codex_pretooluse_gate.py`) each
  call their own `_resolve_project_root(cwd)` — itself `normalize_cwd()`, a
  git subprocess — UNCONDITIONALLY on every invocation, to locate the record
  file BEFORE the library's short-circuit can run (the record's storage path
  is keyed by `project_root`, so it can't be known without resolving cwd
  first — a real circular dependency, not an oversight). Every `PreToolUse`
  call in an armed Codex session still spawns one git process per turn, for
  the whole session. Fixing this for real needs a per-raw-cwd on-disk cache
  (mapping the unresolved cwd string straight to its resolved project_root),
  which is a new piece of state with its own staleness/invalidation
  questions — out of scope for this correction; **R2b inherits it** as an
  optional perf follow-up, not a correctness gap (the mechanism is still
  fail-open and correct either way, just not free).

## Recommended starting point for R2b

**Still PENDING** — the live payload-capture probe (Step 2/10) was attempted
2026-09-22 but diverged before reaching the `Stop`-payload capture step (the
probe session's `cwd` pointed at the real R2 worktree, so Codex's own
`/shipwright-iterate` resume logic took over instead of running the scripted
scratch-repo probe; stopped before any commit, no residue left in the repo —
see `iterate-spec.md`'s Live proof checklist for the full account). This
section still needs real evidence (Stop-payload shape,
`iterate_stop_finalize.py`'s behavior under a genuine Codex-shaped Stop
payload, whether Codex exposes a `SubagentStop`-equivalent event at all, and
— added by this run's doubt-review — whether Codex's `PreToolUse` dispatch
is ever batched/parallel or retried while a hook invocation is still
pending, which the `codex_pretooluse_gate.py` fail-open `consume()` race
currently assumes it is not) rather than a guess, and R2 is closing without
gathering it — a repeat attempt needs an isolated throwaway repo as `cwd`,
not this monorepo's own worktree, to avoid the same divergence. **R2b
inherits this as its own required live proof**, per `iterate-spec.md`'s
AC1a live-proof item.
