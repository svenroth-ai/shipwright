# Shipwright Glossary

> Shared vocabulary used by Shipwright agents, subagents, hooks, and
> compliance audits. Update incrementally — new terms join here, do not
> spread definitions across SKILL.md files.

## Core mechanics

- **Allowlist** — `shipwright_bloat_baseline.json`. Lists every file
  that currently exceeds the Shipwright LOC limit (300 source / 400
  runtime-prompt). Each entry carries `path`, `limit`, `current`,
  `state`, and (for exceptions) `adr`. Single producer:
  `shared/scripts/lib/bloat_baseline.py`.
- **Ratchet** — When a baseline-allowlisted file's measured LOC
  exceeds the `current` value recorded in the allowlist. Means
  "the file got bigger since we last froze it" — the trend Shipwright
  is wired to prevent.
- **Anti-Ratchet** — The hard rule that ratchets must not land. The
  pre-commit hook (this iterate, A.defense), the Stop hook
  (A.foundation), and the Group H detective audit (A.review) all
  enforce it at different gates.
- **LOC-as-Router** — The principle that a line-count crossing
  ROUTES (escalates) a file to the reducibility reviewer instead of
  ruling it bloated. LOC is the cheap trigger; the reviewer is the
  verdict. No concrete reducibility finding → PASS. See
  `shared/reducibility-catalog.md`.
- **Reducibility-Catalog** — The closed, falsifiable catalog the
  reviewer blocks on: **D** duplication · **A** needless-abstraction ·
  **X** dead-code · **C** control-flow · **S** data-shape ·
  **M** comment-restating-code · **P** dependency-footprint ·
  **T** test-repetition. Each finding cites what-to-remove +
  est-LOC-saved + keeps-tests-green; guardrails G1–G6 void any finding
  on long-but-coherent / coverage-weakening / generated code. SSoT:
  `shared/reducibility-catalog.md`; idiom-map:
  `shared/profiles/reducibility-idioms.json`.
- **Baseline** — Synonym for **Allowlist**. The file is named
  `…_baseline.json` for historical reasons (adoption-time
  "this-is-where-we-started" frozen state).
- **Producer** — The single code path authorised to write a given
  artifact. Every artifact Shipwright tracks has exactly one Producer
  to prevent format drift. Example: `shared/scripts/lib/bloat_baseline.py`
  is the sole Producer for the bloat baseline; everything else is a
  Consumer.
- **Consumer** — A reader of a Producer's artifact. Consumers MAY
  parse and act on the artifact but MUST NOT write it.
- **Canon-Gate** — The phase-quality gate inside the Stop-hook chain
  that refuses to finalize a phase whose artifacts violate the
  canon (size, schema, parity). See
  `shared/scripts/lib/phase_quality.py`.
- **Action-Unit** — A triage-inbox unit of work. Each Action-Unit
  is `Fix`, `Promote` (to iterate), or `Dismiss`. The unit, not the
  raw GitHub item, is what the operator decides on.

## Pipeline & lifecycle

- **Phase** — One of the seven orchestrator SDLC phases: project,
  design, plan, build, test, changelog, deploy (`PIPELINE_STEPS`). Each
  phase owns one plugin. Security and compliance are separate skills,
  not pipeline phases (out-of-band).
- **Profile** — Stack profile (`shared/profiles/<name>.json`) that
  parameterises a pipeline run: dev_url, test commands, migration
  apply / preflight commands, deploy flavour. Profile name lives in
  `shipwright_run_config.json.profile`.
- **Adopt** — `/shipwright-adopt` brownfield onboarding skill.
  Generates CLAUDE.md, `.shipwright/agent_docs`, planning specs,
  compliance artifacts, and the bloat-baseline for an existing repo.
- **Campaign** — A multi-iterate planning unit. Lives in
  `.shipwright/planning/campaigns/<date>-<slug>.md`. Each iterate in
  the campaign is a discrete `/shipwright-iterate` invocation. Track
  A (Prevention) is the first campaign that bundles three iterates
  (foundation / review / defense).
- **Campaign-Status** — A campaign's per-sub-iterate board: the tracked,
  per-tree `…/campaigns/<slug>/status.json` (producer-owned, authoritative for
  the Command Center Campaigns lane). **Projected from the event log** by
  `campaign_status.project_campaign_status` (campaign
  `2026-06-07-tracked-campaign-status`): the `campaign.md` `## Sub-Iterates`
  table is the **skeleton** (id/slug/order, markdown-emphasis stripped so a
  legacy `**C1**` matches the plain committed `C1`); each top-level-stamped
  `work_completed` event (`event["campaign"]`/`["sub_iterate_id"]`, S1) marks its
  sub `complete`; a **never-downgrade** guard merges over the committed file
  (`commit=""`/null-test no-clobber; non-skeleton subs dropped). Written at F5b
  Step 6 (`campaign_status_io.finalize_campaign_status`), reconciled by glob
  (`churn_merge.is_campaign_status`, regenerate **scoped to conflicted
  campaigns**). **Token-vocabulary SSoT (cross-repo, Producer ↔ Consumer must
  agree):** the **lifecycle** `draft|active|complete` is declared once in
  `campaign_progress.LIFECYCLE_STATUSES` (↔ WebUI `VALID_LIFECYCLE`); the
  **sub-status** `pending < in_progress < complete` ladder plus the explicit
  terminals `failed`/`escalated` live in `campaign_status.STATUS_LADDER` +
  `TERMINAL_STATUSES` (↔ WebUI `VALID_STATUSES`). Producers:
  `campaign_progress.py` (`start`/`update-status`/`regenerate`),
  `campaign_status_io`. Consumers: the WebUI Campaigns lane
  (`campaign-status-json.ts`). Related: Producer, Consumer, Churn-Artifact.
- **Triage-Inbox** — The cross-cutting pre-backlog intake. Its SSoT is
  the **git-tracked** append-only event log `.shipwright/triage.jsonl`
  (committed per-tree like `shipwright_events.jsonl` since campaign
  `2026-06-05-track-triage-jsonl`: staged by iterate-finalize F6,
  reconciled across worktrees by
  `resolve_churn_conflicts._reconcile_triage`). The tracked
  `.shipwright/agent_docs/triage_inbox.md` is a **derived view** of that
  log (regenerated by `aggregate_triage.py`), not a separate store.
  Source of Action-Units. Producers: phase-quality + compliance
  Stop-hooks, the drift / security / performance / F0.5 emitters, and the
  GitHub-findings importer.
- **Outbox** — The per-tree, **gitignored** background-triage buffer
  `.shipwright/triage.outbox.jsonl` (campaign
  `2026-06-08-triage-outbox-delivery`). When a background Producer would
  append to the tracked `.shipwright/triage.jsonl` but HEAD is on the
  default branch with an `origin` remote (idle main), it appends HERE
  instead — so idle main never accrues uncommitted tracked-log drift that
  would block a fast-forward pull. Kept ignored by the canon
  `/.shipwright/*` whitelist wildcard (pinned by an explicit
  `/.shipwright/triage.outbox.jsonl` line — never a `!`-re-include). The
  guarantee is scoped to the managed BEGIN/END block: a user `!`-rule placed
  AFTER the block (git honours the last matching pattern) can still override it,
  which is out of contract. The
  Outbox is **swept** into the iterate PR branch by
  `setup_iterate_worktree` (`lib.sweep_outbox`, under the canonical triage
  lock), then **GC'd** once the line is origin-delivered (by semantic `id`
  for appends, normalized text for status flips). `triage.read_all_items`
  **union-reads** tracked ∪ Outbox so Consumers see background findings
  immediately, before the sweep. The canon ignore block is self-healed
  into stale-cache managed repos by `lib.gitignore_selfheal` at the next
  iterate setup. Related: Producer, Consumer, Worktree-Isolation,
  Anti-Ratchet (the Outbox is NOT a ratchet of the tracked log — it is a
  staging buffer, drained exactly-once via `merge=union` + dedup).
- **Iterate** — A change to a completed project (`shipwright_run_config`
  status `complete`). Skills: `/shipwright-iterate`, with Path A
  (feature), Path B (change), Path C (bug). The medium+ flow lives
  in `plugins/shipwright-iterate/skills/iterate/SKILL.md`.
- **Run-ID** — Canonical identifier of a single SDLC or iterate run,
  shape `iterate-YYYY-MM-DD-<slug>` for iterates. Threaded through
  every artifact: spec, plan, ADR, event-log, iterate_history,
  session-handoff. Validated by
  `shared/scripts/lib/iterate_entry.RUN_ID_STRICT`.
- **Worktree-Isolation** — Every iterate run executes in
  `.worktrees/<slug>` on branch `iterate/<slug>`. Structural —
  no opt-in. Implemented by
  `shared/scripts/tools/setup_iterate_worktree.py`. Prevents two
  parallel iterates from ever sharing a working tree.
- **Decision-Drop** — A per-iterate ADR sketch written to
  `.shipwright/agent_docs/decision-drops/<run_id>.json` (gitignored,
  main-repo path). Aggregated into the canonical `decision_log.md`
  with a sequential `ADR-NNN` only at `/shipwright-changelog` release
  time — that's the single serialised point where ADR numbering is
  safe to assign.
- **F7b-Seal** — A follow-up commit that re-attaches the F7
  `work_completed` event to the branch tip in repos that track
  `shipwright_events.jsonl` (shipwright dev repo + downstreams that
  unblock the gitignore). Without it, a `git reset --hard` or rebase
  can silently wipe events appended after the iterate commit. Tool:
  `shared/scripts/tools/commit_event_followup.py`.
- **Spec Impact** — The Step-2 classification of how an iterate
  touches `spec.md`: `add | modify | remove | none`. Recorded in the
  iterate spec, carried via F7 `--spec-impact`, enforced post-commit
  by the F11 finalization verifier
  (`check_spec_impact_recorded`).
- **Phase-D-Acceptance** — Cross-iterate acceptance check at the
  end of a multi-iterate campaign — re-run all individual smoke
  tests after every campaign iterate has merged, confirm all
  defense layers still cooperate. Campaign A.defense's final step.

## Compliance & detective audits

- **Group A–H** — Compliance audit groups. Each group is a focused
  detective audit (single producer rule). The letter set widens as
  new audit categories ship. Current set: A (general), A5 (RTM), B
  (deploy), D (events), F (drift), G (bloat-reviewer-prompt
  parity, A.review), H (bloat-baseline post-merge drift, A.review).
- **Stop-Hook** — Claude Code lifecycle hook that fires when the
  agent finalises a turn. Shipwright's Stop hook chain runs the
  bloat anti-ratchet gate (A.foundation), the phase-quality gate,
  and the auto-handoff writer. See `docs/hooks-and-pipeline.md`.
- **PostToolUse-Hook** — Claude Code lifecycle hook that fires
  after each tool call (`Write`, `Edit`, `Bash`, …). Shipwright
  uses it to set the bloat marker so the Stop gate can fire on
  the same session that triggered the over-limit write.
- **Session-Marker** — `.shipwright/locks/bloat_pending.<sid>.json`,
  written atomically by the PostToolUse hook with TTL-filtered
  entries. Read by the Stop gate. Per-session by `SHIPWRIGHT_SESSION_ID`
  to prevent cross-session leakage.
- **RTM** — Requirement Traceability Matrix. Maps every FR-ID to
  the spec line, the implementing file, the test file, the
  changelog entry, and the deployment record. Producer:
  `plugins/shipwright-compliance/scripts/lib/rtm_generator.py`.
- **SBOM** — Software Bill of Materials. Producer:
  `plugins/shipwright-compliance/scripts/lib/sbom_generator.py`.
- **Drift** — Divergence between an artifact and its single
  producer's expected output. Detected by hooks (Canon-Gate),
  compliance audits (Group F), and the on-demand
  `/shipwright-compliance` skill.
- **External-Review** — `shared/scripts/tools/external_review.py` —
  reviews plans / iterate mini-plans / code diffs against the spec
  via an OpenRouter-routed LLM. Mandatory at medium-iterate plan
  stage and at code-review cascade for risk-flag iterates.
- **Surface-Verification** — `shared/scripts/surface_verification.py`,
  the F0.5 end-to-end gate. Empirically drives the user-erlebbare
  surface (web / cli / api / none) and writes the
  `iterate_latest.surface_verification` block downstream readers
  consume.

## External References

Verbatim attribution for the externally-sourced rule headers
adopted into shipwright's bloat-reviewer prompts, ADR template, and
constitution. Citations follow Campaign A.review's snapshot-date
convention.

- **Karpathy 4 Principles** — *Think Before Coding · Simplicity
  First · Surgical Changes · Goal-Driven Execution*. Source:
  [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills),
  MIT © 2025 multica-ai. Snapshot date: 2026-05-21. Used in:
  `plugins/shipwright-build/agents/code-reviewer.md` (Karpathy
  block, A.review).
- **Osmani Five-Axis Review + Change-Sizing + Dead-Code** — Source:
  [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills),
  MIT © Addy Osmani. Snapshot date: 2026-05-21. Used in:
  reviewer-prompts (A.review), this glossary, and the
  Chesterton-Fence-Check heading of
  `_template-bloat-exception.md` (A.defense).
- **Osmani `code-simplification`: Chesterton-Fence + Five
  Principles** (Preserve Behavior · Follow Conventions · Clarity
  over Cleverness · Maintain Balance · Scope to What Changed).
  Source: same Osmani repo, skill `code-simplification`. Snapshot
  date: 2026-05-21. Used in: ADR-template `Chesterton-Fence-Check`
  field (A.defense), reviewer prompts (A.review).
- **Superpowers Iron-Law + Red-Flags + Rationalization-Prevention
  + YAGNI Header** — Source:
  [obra/superpowers](https://github.com/obra/superpowers), skills
  `verification-before-completion` + `writing-plans`. MIT © Jesse
  Vincent. Snapshot date: 2026-05-21. Used in: Stop-Gate block-body
  (A.foundation), ADR-template `YAGNI-Check` field (A.defense),
  glossary External References (this section).

Multica main repo (`multica-ai/multica`) is *not* re-quoted here:
Apache-2.0 modified-with-hosting-restriction. Architecture patterns
are reusable; verbatim text is not. The shipwright glossary borrows
the **pattern** of an Incident-Reference field in
`_template-bloat-exception.md` without copying any text.
