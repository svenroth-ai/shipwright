# Shipwright Glossary

> Shared vocabulary used by Shipwright agents, subagents, hooks, and
> compliance audits. Update incrementally — new terms join here, do not
> spread definitions across SKILL.md files.

## Core mechanics

- **Command Center** — the **product-facing** name of Shipwright's web
  interface: what a user sees, what marketing and user documentation call it,
  and the right term in the requirements catalog and in anything a user reads.
- **WebUI** — the **repository and codebase** behind the Command Center
  (`shipwright-webui`, split out at v0.4.0). The right term in code, commit
  messages, contracts and internal notes: `VALID_LIFECYCLE`, the vendored gates,
  "a webui-side iterate". One product, two registers — Command Center outward,
  WebUI inward. Do **not** invent a third ("companion app", "the dashboard"):
  each variant costs a reader a lookup to confirm they are the same thing.
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
  "this-is-where-we-started" frozen state). **Not the contract-gate baseline**
  (see **Output-Contract**): that one is a published *shape* read from
  `origin/main`, not allowlisted line counts. One word, two senses.
- **Output-Contract (cross-repo)** — The published, versioned shape of a payload
  this repo hands to a DIFFERENT repo. `lib/contract_skeleton` diffs it against
  the shape at `origin/main` (`lib/contract_baseline` — read from there because a
  pin beside the code is editable in the same change) and fails until the version
  matches: removed/retyped ⇒ major, and a container gaining `null` IS a retype.
  Binds the PRODUCING side only. FR-01.15.
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
- **Phase task** — the *record* of one phase's run inside a pipeline, held in
  `run_config.phase_tasks[]`. **Not the same as a Phase** (the entry above, which
  is the kind of work): a Phase is `build`; a phase task is *this* build, with
  its own status, mutated **only** through `phase_task_lifecycle`. It is the
  **authoritative** per-phase status — anything else showing phase state is a
  view of it.
- **Dev-server state** — `<project>/shipwright_dev_server.json`, the record of
  which local preview processes this project has running. **Per project
  directory**, which is what makes reuse safe: a foreign process answering on the
  same address is simply absent from it, so it can never be handed back as this
  project's preview. **Not to be confused with Loop state** (below), which is the
  orchestrator's own pointers — "state" alone is ambiguous between them.
- **Loop state** — the orchestrator's own pointers and counters for a
  single-session run (`currentPhaseTaskId`, its lifecycle status). Deliberately
  **not** authoritative for phase status: it says which phase is being
  dispatched, the phase task says how that phase is doing. Belongs to one run —
  a loop state whose run id does not match the configuration is refused.
- **`needs_validation`** — the state a step enters when it is asked to be marked
  finished but its phase validator raised something needing a decision. The step
  is *not* complete; the run pauses for a person. Note the escape hatch's shape:
  forcing completion **skips** the validation rather than overriding it, so a
  forced step has no findings to show.
- **Profile** — Stack profile (`shared/profiles/<name>.json`) that
  parameterises a pipeline run: dev_url, test commands, migration
  apply / preflight commands, deploy flavour. Profile name lives in
  `shipwright_run_config.json.profile`.
- **Adopt** — `/shipwright-adopt` brownfield onboarding skill.
  Generates CLAUDE.md, `.shipwright/agent_docs`, planning specs,
  compliance artifacts, and the bloat-baseline for an existing repo.
- **Split** — One self-contained part of a project, planned and
  delivered on its own. `/shipwright-project` decomposes a project into
  splits (`01-adopted/`, `02-task-board/`), each with its own `spec.md`
  and its own plan. A split owns a requirement **group**: the digit in
  `FR-{group}.{NN}` IS its split, so `FR-03.xx` belongs to split `03-…`
  (`shared/fr-authoring.md` §4). Not to be confused with a **Section**,
  which is one chunk *inside* a single split's plan.
- **Section** — One buildable chunk of a plan, and the unit
  `/shipwright-build` consumes: one section per invocation, one branch,
  one commit. Declared in the plan's `SECTION_MANIFEST` as `NN-slug`
  and written to `sections/NN-slug.md`. The `NN` carries the intended
  build order. **Overloaded term — mind the context:** in
  `/shipwright-changelog` and `CHANGELOG.md`, "section" means a block of
  release notes (`## [1.2.0]`, `### Added`), which is unrelated. Where
  both could be meant, say *build section* or *release-note section*.
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
  GitHub-findings importer. **Always both words:** the Command Center has a
  separate **Inbox** (agent questions), and bare "Triage" names the *activity*.
  Never "buffer" — the operator did not recognise that word.
- **Triage status is per-tree** — a worktree's `triage.jsonl` carries only the
  status events made **on that branch**. An item dismissed on `main` after the
  branch point still reads `triage` inside the worktree, so a listing taken
  there shows closed items as open. Resolve status against the **main repo
  root** (or merge `origin/main` in first). The mirror of this is the
  **outbox**: items filed *in* a worktree are invisible in the Command Center
  until the PR merges. Two different directions, same cause — the log is
  per-tree, the view is not.

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
- **Defer (Snooze)** — the third triage decision beside promote and dismiss:
  decided, but deliberately not now. Stored as `snoozed`, writable from both
  surfaces (`triage_cli.py defer <id> --reason …` and the Command Center),
  and shown by the CLI listing in its own section — deferred is not the same
  as gone. Neither surface can un-defer.
- **Machine-Churn (triage)** — a dismissal a Producer set on itself
  (`MACHINE_DISMISSERS` **and** an exact `MACHINE_REASONS` token, so a human
  dismissal reusing a token survives). The only thing compaction may drop.
  **Not a Churn-Artifact** — one word, two senses.
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

## Requirements & elicitation

- **Functional Requirement (FR)** — A stable capability the product guarantees,
  in business language; one catalog row `FR-{group}.{NN}`. Rules: `fr-authoring.md`.
- **Acceptance Criterion** — One testable behaviour of an FR,
  `- (E) Given … when … then …`; the unit REQ-3 binds tests to. `TBD` = a gap.
- **Basis** — Catalog column, *how we know* a requirement:
  `interview|code|observed|tests|assumed|other:<reason>`. Graded by `I5`. `fr-authoring.md` §4a.
- **Layers** — Catalog column, test layers covering an FR (`{unit,integration,e2e}`);
  bare = binding, `(inferred)` = advisory. `fr-authoring.md` §4a.
- **Intent (`fix` · `feature` · `change`)** — what kind of work a change is,
  detected from its description. It decides two things: how deep the workflow
  goes, and whether a **requirement impact** is owed. A `fix` is **deliberately
  exempt** — repairing behaviour back to what was intended moves no requirement.
  That exemption is also the escape hatch: work that *does* shift intended
  behaviour but is labelled a fix records nothing.
- **Requirement impact** — what a change did to the requirements: `add`,
  `modify`, `remove`, or `none` **with a one-line reason**. Recorded on the work
  event, and a feature or change that records neither an affected requirement nor
  a justified `none` is **rejected at the moment it is recorded** — not caught
  later by an audit.
- **Requirement Elicitation (grilling)** — The shared method project/adopt/iterate
  use to pull out a complete requirement: one question at a time, facts looked up,
  terms challenged, edges stress-tested, done only when the Coverage Checklist is
  met. FR-01.16; `requirement-elicitation.md` (after Matt Pocock).
- **Coverage Checklist** — The seven dimensions every requirement must cover:
  outcome (with a fit criterion) · purpose · boundaries & edge cases · failure ·
  glossary terms · rationale · out-of-scope; none silently blank (greenfield:
  none `assumed`). §8 of the method doc.
- **Context Glossary (`CONTEXT.md`)** — The **target project's** domain glossary,
  separate from THIS framework glossary; no implementation detail. `context-format.md`.
  **Format only — nothing creates it yet** (`trg-e9fa7c49` item 1).
- **Grill-Trace** — The record an elicitation produces per requirement: which
  Coverage-Checklist dimension was answered where, which scenarios were put.
  **Does not exist yet** — the trace + completeness gate that would make
  Requirement Elicitation checkable rather than prompt-only. `trg-e9fa7c49`;
  design under `.shipwright/planning/campaigns/`.
- **Fit Criterion** — The yes/no measure that settles whether an outcome is met
  ("loads within 2 s", not "fast") — makes a requirement verifiable (Volere).
- **Assumptions-first** — Project/adopt state what they *inferred but weren't
  told* (web-vs-CLI, stack, persistence, auth) before clarifying questions.
  Drift-tested (`test_assumptions_first_block.py`).

## Design artifacts

- **Screen / Mockup** — A standalone HTML mockup of one screen
  (`.shipwright/designs/screens/NN-name.html`), opens in a browser, no
  build/server/install.
- **Flow (user flow)** — A multi-screen mockup showing the path across screens for
  one journey (`.shipwright/designs/flows/*.html`) — the route, not isolated
  screens.
- **Chrome (definition)** — Shared page furniture (nav/header/footer/branding)
  defined once (`chrome-definition.md`) so screens match and one change updates all.
- **Visual Guidelines / Design Tokens** — Colours, typography and spacing the
  build consumes to match the design (`.shipwright/designs/visual-guidelines.md`).

## Build & delivery

- **TDD (Red-Green-Refactor)** — Write a failing test (red), make it pass
  (green), then tidy without changing behaviour (refactor). The build discipline;
  `/shipwright-build` Steps 3–5.
- **Feature branch** — One branch per section or change (`build/{slug}`,
  `iterate/{slug}`); never committing straight to the default branch. One section
  = one branch = one commit.
- **Migration (`up.sql` / `down.sql`)** — A stored-data schema change: `up.sql`
  applies it, `down.sql` reverses it. Build requires the reverse alongside the
  forward.
- **Destructive migration** — A schema change that can lose data (DROP
  TABLE/COLUMN, TRUNCATE, DELETE without WHERE, lossy ALTER TYPE). A PostToolUse
  hook soft-blocks it and requires explicit confirmation.
- **Browser verify** — Loading the built app in a real browser (Playwright) to
  capture console errors and a screenshot; mandatory when frontend files change.
  `shared/scripts/browser_verify.py`.
- **Review cascade** — Build Step 6's three stages: **spec-reviewer** (Stage 1,
  hard-gate — does the code match the spec; REJECT blocks the rest),
  **code-reviewer** (Stage 2, quality), **doubt-reviewer** (Stage 3, advisory —
  an adversarial disprove pass for risky touches).
- **Drop file** — One pending release-note entry written as its own file under
  `CHANGELOG-unreleased.d/`, aggregated into a **release-note section** (see
  **Section**, the overloaded term) when the release is assembled. Per-file
  rather than per-line so parallel changes never collide on the same lines; the
  older habit of writing straight into the pending section is reported at
  release rather than folded in silently.
- **Version bump** — Which of the three numbers the next version raises, derived
  from the kinds of change since the last release: a break in compatibility
  raises the first, a new capability the second, anything else the third.
  Proposed by the tool from the commit types, not decided by it.
- **Conventional Commits** — The `type(scope): description` commit format
  (`feat`/`fix`/`refactor`/`test`/`docs`/`chore`) that makes history
  machine-readable for the changelog.
- **Smoke test** — A minimal post-deploy check that the running app is alive
  (e.g. a health endpoint returns 200); gates deploy success and triggers
  rollback on failure. `shared/scripts/smoke_test.py`.

## Testing

- **Test layer** — (the thing the catalog's **Layers** column names — that entry
  is the column, this one is the level itself.) One level of the test pyramid:
  unit, integration (real DB),
  pgTAP (database/RLS), smoke (is it alive), end-to-end (browser). Each catches a
  different class of bug; which layers block the pipeline is the constitution's
  Test Layer Boundaries table. A criterion must be tested at the layer that can
  actually falsify it — one layer too low looks like coverage and proves nothing.
- **Suite unit** — the change workflow's **parallelisation** unit: one plugin's
  or shared directory's test folder, run as its own process. **"Unit" is badly
  overloaded — mind which one:** a *suite unit* is a directory being run; a
  **unit test** is a test *layer* (see **Test layer**); an **Action-Unit** is a
  triage decision; a **Section** and a **Campaign** are units of work. Where
  confusion is possible, say *suite unit*. Two properties worth knowing: units
  are **discovered**, not listed (a new plugin is picked up automatically, and a
  parity test guards that against CI), and **execution is proven, not guessed** —
  each unit writes a report file that exists *iff* the tests actually ran, so a
  non-zero exit with no report is an infrastructure fault, not a test failure.
- **Honest skip** — A layer recorded as *not run, with a stated reason*, as
  opposed to silently absent or counted as passed. The reason must come from the
  closed list in `completion-gate.md`; a skip with no reason blocks phase
  completion. A check that failed to start is an honest skip, never a pass.
- **Boundary (Producer · Consumer · Format)** — A declared pair of code that
  *writes* a stored format and code that *reads* it, plus the format between
  them; declared in an iterate spec's `## Affected Boundaries` table (ADR-024).
  The unit the round-trip audit reasons about.
  **Careful — `Producer` here is NOT the `Producer` defined above.** The
  framework's Producer is a **rule**: exactly one code path is *authorised* to
  write a given artifact. A boundary row's Producer is a **description**:
  whatever code writes that format, and there may be several. So a boundary row
  never asserts single-writer authority, and a row listing two writers is a
  finding for the single-Producer rule — not a contradiction in the table.
- **Round-trip test** — A test proving a value survives being written out by the
  producer and read back by the consumer. The boundary report's
  `round_trip_tested` is a **name-mention heuristic**, not proof: three states —
  `true` / `false` / `"unknown"` (the matched commit's event lacked
  `changed_files`, so absence of evidence ≠ evidence of absence).
- **Drift signal (boundary)** — A change whose commits or spec text touched
  stored-format files but declared **no** `## Affected Boundaries` row. The audit
  hook for skipped declarations — the detective half of the boundary report, and
  the more valuable half.
- **Gate posture (`warn` / `block`)** — Whether a failed check reports and
  continues (`warn`) or fails the phase (`block`). The performance budget's
  per-project setting; `warn` ships honest signal before budgets are calibrated.
  Orthogonal to whether the failure is *recorded* — a warn-posture failure still
  files a tracked follow-up.

## Security & release

- **Scanner backend** — a pluggable scanner implementation behind one interface
  (`aikido` cloud, `oss` = Semgrep + Trivy + Gitleaks). Auto-detected; the rest
  of the chain (classify → remediate → report) only ever sees normalized
  findings, never a tool's native output.
- **Normalized finding** — the single shape every check emits (`id`, `severity`,
  `type`, `rule`, `source`, …) so four different tools merge into one report.
  The prompt-injection scanner emits it too, which is why it merges
  transparently.
- **Degraded leg** — a scanner that *was invoked* but produced no parseable
  output (fatal, timeout, truncated report, missing binary). Recorded on a
  separate control-plane channel from the findings, with a reason from a closed
  vocabulary, so it can never read as a clean "0 findings". A degraded run
  exits non-zero. Contrast **honest skip** (a layer that legitimately did not
  run) and note the open gap: a scanner that was never *installed* is currently
  neither — it is silent.
- **Accepted-risk register** — the file, kept **with the project**, recording
  findings it has formally accepted (`.trivyignore.yaml`, `.gitleaks.toml`). The
  point is visibility: an accepted finding stops resurfacing without vanishing
  from the record. One register per scanner, and every path that scans must
  honour it — otherwise the same repo answers differently depending on who asked.
- **Prompt-injection scan** — the fourth check class: attempts to hijack the
  assistant's own instructions hidden in the files that configure it (skill
  markdown, hook configs, scripts, suspicious dependency additions). Catches
  what the code/dependency/secret scanners structurally cannot.
- **Deploy Profile** — the per-target declarative record of *how* a hosting
  target does the things the discipline requires (way back, data handling),
  validated against a shared schema. Today it is reference documentation: the
  runtime still reads hardcoded procedure.
- **Restore point** — a copy of the working environment taken *before* a change,
  so a known-good state exists to return to.
- **Application-tier vs data-tier rollback** — putting the previous code back is
  not putting the previous data back. Stored data that already moved forward
  stays moved; an app returned to an older version can then meet a shape it does
  not expect. Two different problems, and only the first is what "rollback"
  usually means.
- **Required check** — a check on the code host that must report green before a
  change can merge. Silence counts as not-green, not as green.
- **Review tier** — the rule deciding how much scrutiny a proposed change earns
  (touching sensitive paths, coming from outside the team, or explicitly
  labelled), evaluated by rule rather than by whoever opened it.

## Compliance & detective audits

- **Evidence document** — One of the five readable artifacts the compliance
  phase produces under `.shipwright/compliance/`: the traceability matrix
  (requirement ↔ test), the test-evidence report, the change history, the
  dependency inventory, and the dashboard. Written by iterate-finalize, which is
  their **single Producer** in the strict sense (see **Producer**); a fresh
  regeneration can be inspected on demand but is not the tracked artifact.
- **Snapshot integrity (stale)** — How an evidence document is judged: not
  "does a fresh render match" but "does the file on disk match the version
  committed in the last finalize". Divergence — a hand edit, a partial
  regeneration — makes it **stale**, and stale means *no longer evidence*. The
  earlier fresh-render comparison was abandoned because any unrelated commit
  shifted live state and produced a perpetual stream of false positives.
- **Group A–H** — Compliance audit groups. Each group is a focused
  detective audit (single producer rule). The letter set widens as
  new audit categories ship. Current set: A (general), A5 (RTM), B
  (deploy), D (events), F (drift), G (bloat-reviewer-prompt
  parity, A.review), H (bloat-baseline post-merge drift, A.review).
- **Constitution enforcement register** — The per-rule declaration of *whether
  and by what* each constitution rule is enforced (`hook` · `validator` · `test`
  · `prompt-only (mechanisable)` · `prompt-only (judgement)` · `unimplemented`) —
  the same vocabulary as the AC evidence ledger. Its gate is **declaration
  completeness**: a rule added with no register entry fails CI. It cannot make
  enforcement exist; it makes prompt-only rules stay visibly prompt-only. Not
  built — REQ-3 Phase 3; copies the `gate_catalog.json` pattern.
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
- **RTM** — Requirement Traceability Matrix. Maps every FR-ID to its
  spec line, its work/verification events, and its **per-layer test
  coverage** (`Unit | Integration | E2E`, sourced from the
  test-traceability manifest — `ok` = an executed-passing tagged test,
  `MISSING`, `n/a`, or `?` when the display id is shared across
  namespaces so the frozen un-namespaced `@FR` tag is fanned and its
  coverage cannot be credited — the namespaced row key resolves the
  right node but the node's value is already fanned; the disambiguation
  remedy is deferred to TT5), plus the reconciliation status and any
  open triage. Producer:
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
