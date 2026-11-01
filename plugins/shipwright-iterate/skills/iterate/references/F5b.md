# F5b — Finalize Iterate Artifacts

Run **one** script that records the iterate's `work_completed` event,
regenerates compliance MDs, refreshes the build dashboard, and writes
the session handoff. Per
iterate-2026-05-23-compliance-md-single-producer the event is recorded
BEFORE the compliance regen so the regenerated MDs include the
iterate's own event — making the F6 commit snapshot self-consistent
(and eliminating the recurring E1-E5 staleness class).

`--event-extras-json` carries the SKILL.md F7-mandated fields (intent,
spec_impact, affected_frs/new_frs/change_type/none_reason, description,
changed_files). The event is recorded into **this worktree's own**
`shipwright_events.jsonl` (the per-tree, PR-committed model — see
events_log history, iterate-2026-05-29-events-jsonl-worktree-commit), with
`commit=""` since the F6 commit hasn't happened yet. **F6 stages
`shipwright_events.jsonl`** so the event ships in the iterate PR and merges to
`main` like every other artifact; the main tree is never written. The event
keeps `commit=""` (F6.5 SHA patch is skipped in the worktree flow — the
`Run-ID:` commit footer and `adr_id == run_id` carry the linkage).

**The finalize FR-gate (ADR-059) is enforced on this path** (since
`iterate-2026-06-05-fr-linkage-lifecycle`): the event is **rejected before
write** — finalize exits non-zero with guidance — unless it is classified. Set
**exactly one** of the two branches and **omit** the other keys; a leftover
placeholder such as `"change_type": "{docs|…}"` is itself a rejection (a present
`change_type` must be a recognized value paired with a valid `none_reason`):

- **FR-linked** (feature/change touching the spec) — set `affected_frs` and/or
  `new_frs`; **omit** `change_type`/`none_reason`.
- **No-FR** (docs/tooling/compliance/infra) — set `change_type` ∈
  `{docs,tooling,compliance,infra}` + a one-line `none_reason`; **omit**
  `affected_frs`/`new_frs`. The label is **checked against the diff**
  (merge-base with the trunk to the working tree, untracked files and both
  sides of a rename included): every changed path must fall under it.
  Every label covers docs, tests and Shipwright's own records; `docs`
  covers only those. Generic projects keep runtime code (`src/**`,
  `server/**`, …) outside every label; in the Shipwright monorepo
  `tooling`/`infra`/`compliance` also cover `plugins/**`, `shared/**`,
  `scripts/**`, while `docs` never covers the runtime prompts (skills,
  agents, `shared/prompts/**`, `shared/constitution.md`); under `src/**`,
  `app/**`, `server/**`, `pages/**` a `docs`/`test`/`e2e`/`sbom` directory
  name covers nothing (rules: `lib/change_type_paths.py`; no per-project
  override — a path no rule covers needs its FR linked; a requirement catalog
  `.shipwright/planning/<split>/spec.md` is covered by no label, so a run that mints AC ids or promotes layers links the FRs it touches). A stacked
  campaign unit adds `"stack_base_ref":"<parent unit branch>"` to its extras so
  the diff starts there. Refusals:
  `change_type_not_covered_by_diff` (names the paths) and
  `change_type_diff_unavailable` (git present, no trunk ref or one sharing
  no history with HEAD; not a git
  repo only warns).

**Every intent answers the spec impact — fixes too.** A feature, change or
bug with no `affected_frs`/`new_frs` must set `spec_impact: "none"`, a
one-line `spec_impact_justification` (or `none_reason`) **and**
`spec_impact_reason_code` ∈ `{behavior-preserving,
restores-specified-behavior, docs-only, tests-only, tooling-only,
infra-only, compliance-only}` (closed vocabulary, `lib/reason_codes.py`);
without it the event is refused with `spec_impact_none_requires_reason_code`.
A fix that brings code back to what the spec already says uses
`restores-specified-behavior`. **Every** recorded `spec_impact: "none"`
carries both, with or without FRs alongside it (the justification: one line
of text, max 280 chars). A `*-only` code next to a `change_type` must name the
same label (`docs-only` with `docs`, ...;
`spec_impact_reason_code_contradicts_change_type`). Leaving `intent` out does
not skip the rule: F5b takes it from this run's iterate entry `type`, and an
`intent` that contradicts the entry is refused (`spec_impact_intent_mismatch`).
Specs that exist but parse to zero requirements refuse any declared FR id
(`fr_gate_specs_unparsed`).

**Runtime-touching iterates declare `affected_acs`** (F11 `check_affected_acs_declared`, presence only). A feature/change/bug whose diff touches `plugins/**` or `shared/**` (only directories named `tests/` and `docs/` are excluded; SKILL.md, prompts, glossary and other markdown under `plugins/**` or `shared/**` count as runtime) puts on the event either `affected_acs` - a non-empty list, one entry per acceptance criterion that was changed, implemented, or checked and left unchanged, shaped `{"ac": "FR-01.03.AC05", "disposition": "changed|implemented|checked-unchanged", "why": "one line on why the promise holds"}` - or `"catalog_gap": true` with `"catalog_gap_fr": "FR-.."` (the nearest FR) when no AC covers the change. **A declared gap is then closed in the same run:** write the WHAT/WHY AC through the MINT/FOLD path (`shared/fr-authoring.md` section 3; FOLD into the nearest FR is the usual case) and list its id as `"catalog_gap_acs": ["FR-..ACnn"]`, or record the closed reason `"catalog_gap_reason": "how-only"` (the change is about how the product works, not what it does). An open gap is an advisory warning like a missing declaration. This holds for `spec_impact: none` too. F11 reports a missing declaration as an advisory warning; the declaration is still expected at F5b. The check never reads the content: whether the line is true is for the reviewers. `tools/affected_acs_replay.py` replays the rule over past iterates.

**Plan stub and spec chain (`plan_path`, `pr`).** Every feature/change/bug iterate writes its plan stub before F5b: write the values to a JSON file with the Write tool (`{"run_id": "...", "goal": "{WHAT}", "reason": "{WHY}", "ref": "{PR, plan or brief}"}`; optional `"tiny": true`, `"ac": ["FR-..ACnn"]`, `"gap_fr": "FR-.."`), then run `uv run "{shared_root}/scripts/tools/write_plan_stub.py" --project-root "{project_root}" --from-json "{json_file}"` (three lines; `tiny` for one; `ac` or `gap_fr` for a run that changes an AC or declares a catalog gap, which gets the full stub). goal, reason and ref are never interpolated into a shell command: free text with quotes, `$(...)` or backticks would be executed or mangled by the shell. The one filename is `.shipwright/planning/iterate/{run_id}/plan.md` (the spec-chain record; a mini-plan stays a working note and may keep its own name); F5b stamps it on the event as `plan_path` when the file exists (or pass `"plan_path"` in the extras). `"pr"` (the PR number) is optional on the event - the PR number exists only after the push. Record it once the PR is open with `record_event.py --type event_amended --amends {event_id} --fields '{"pr": N}'` (the lookup applies amendments); otherwise it is found from the squash commit that carries the `Run-ID`. F11 `check_plan_stub_recorded` reports a missing stub as an advisory warning. `tools/spec_chain_cli.py lookup --ac FR-01.03.AC05` answers which runs, plans and PRs shaped an AC.

**Independent gap check (after the event is recorded, before F6; every complexity; advisory).** One fresh-context call to a NON-Claude model (GPT or GLM, through the external-review OpenRouter route) reads the diff, the catalog's acceptance criteria and this event's declaration, and answers one narrow question: is the declaration a fair account of the diff? It looks for a wrong `none` and for catalog gaps; it is not an "AC untrue" detector. The diff (committed, staged and unstaged changes of tracked files; **untracked files are never sent**, so `git add -N <new file>` first; credential-shaped paths on either side of a rename or copy are withheld and named as incomplete input) and the whole catalog leave the machine for the review provider on every iterate: one extra paid call each time, so the call is skipped (`not_run`) when external review or code review is switched off or a gateway-only route is set. There is no separate switch: turning external review off turns this check off. `--driver` is the harness actually driving this session, resolved by the rule in [iteration-reviews.md](iteration-reviews.md) (the line starting "`--driver` is required") and [iteration-planning.md](iteration-planning.md) Step 3.5: a session run through Codex CLI's own agent loop is `codex`, a Claude Code session is `claude`, and `codex` also when `CODEXTENDER_ACTIVE` is set. Under `--driver codex` the reviewer is GLM, never a GPT-family model. It sends the whole catalog, not only the owning FRs' ACs, because a gap has no owning FR yet. It never blocks: no key, a provider outage or an unreadable reply record `status: "not_run"` with the reason and exit 0.

```bash
uv run --project "{plan_plugin_root}" "{shared_root}/scripts/tools/ai_gap_check.py" \
  --project-root "{project_root}" --run-id "{run_id}" --base-ref "origin/<default>" --driver "{driver}" \
  --out-dir "{project_root}/.shipwright/planning/iterate/{run_id}"
```

(`origin/<default>` is the fresh default-branch ref; a campaign sub-iterate passes its `{base_branch}` instead.) It writes `ai-gap-check.json` (F6 stages the run directory) and `ai-gap-check.md`, the one PR-body block (requirements changed, requirements checked, verdict agree/disagree, gap yes/no). Paste `ai-gap-check.md` into the PR body (F11); a `not_run` note goes in the same way, so a skipped check is visible, never silent. Free text is passed through files only (diff, event, specs), never interpolated into the shell. A `disagree` is a prompt for the PR reader, not a finding to argue away; do not edit the declaration to satisfy it. F11 `check_ai_gap_check_recorded` warns when no record exists. `tools/ai_gap_check_replay.py` replays the check over merged PRs.

**Behavior-affecting changes must be FR-linked.** If `spec_impact` is
`add`/`modify`/`remove` (the change alters an FR's observable behavior), the
No-FR branch is **not available** — the gate rejects it even with a valid
`change_type`/`none_reason`, because a real behavior change must name the FR it
touches. The No-FR branch is reserved for behavior-preserving work
(`spec_impact: none`). This rule is intent-independent (it also covers BUG and
intent-less events).

**FR-linked + behavior-affecting also needs test evidence**
(iterate-2026-08-16-fr-gate-test-evidence). If `spec_impact` is
`add`/`modify`/`remove` **and** `affected_frs`/`new_frs` is set, the event
also needs `tests.total > 0` — normally folded in automatically from this
run's own F5 ledger (`lib.iterate_tests_block.fold_into_event`, so you rarely
set `tests` by hand here) — **or** a one-line `no_tests_reason` when that fold
finds nothing (no ledger, or a stale/foreign `run_id` in
`shipwright_test_results.json`). A `spec_impact: none` event that still
*references* an existing FR via `affected_frs` (re-verifying it without
claiming to have changed its behavior — see BP-2's reconciliation mechanism)
is never gated by this rule. **`new_frs` is always gated regardless of
`spec_impact`** — minting a requirement is inherently an "add", so
`spec_impact: none` alongside a non-empty `new_frs` needs evidence too (or
`no_tests_reason`) rather than bypassing the rule.

```bash
# Example: FR-linked iterate. For a no-FR iterate, drop affected_frs/new_frs
# and instead set "change_type" + "none_reason" (see the two branches above).
# tests is usually folded in automatically (see above) — set no_tests_reason
# only if the fold found nothing and this event is behavior-affecting.
extras='{
  "intent": "{feature|change|bug}",
  "description": "{short_description}",
  "summary": "{one plain-language sentence a non-expert can read}",
  "spec_impact": "{add|modify|remove|none}",
  "spec_impact_justification": "{required when spec_impact=none}",
  "spec_impact_reason_code": "{required when spec_impact=none: closed code}",
  "affected_frs": ["FR-..."],
  "new_frs": ["FR-..."],
  "affected_acs": [{"ac": "FR-01.03.AC05", "disposition": "checked-unchanged", "why": "{one line}"}]
}'
uv run "{shared_root}/scripts/tools/finalize_iterate.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --reason "iterate: {short_description}" \
  --event-extras-json "$extras"
```

**Plain-language `summary` (readability).** The one-sentence, jargon-free
`summary` says what changed in terms a non-expert can read. The compliance Event
column (Test Evidence "Test Progression" + RTM "Verification Timeline") prefers
it over the technical `description`; omit it and the column falls back to
`description`. Merged verbatim via `--event-extras-json`; forward-only (it only
affects events recorded from now on).

**Campaign identity stamp (campaign 2026-06-07-tracked-campaign-status, S1):**
when the iterate is a campaign sub-iterate — spawned by the autonomous loop OR
hand-run via `--campaign <slug> --sub-iterate-id <id>` — add two extra keys to
the same `--event-extras-json` object: `"campaign": "<campaign-slug>"` and
`"sub_iterate_id": "<id>"`. They are additive metadata (merged verbatim,
idempotent per run_id like the rest of the event) and do NOT replace the
FR-gate classification above. The stamp makes `shipwright_events.jsonl`
self-sufficient for per-sub-iterate status projection — no slug-join
heuristics against branch names.

> **Step 6 — per-tree campaign board (campaign 2026-06-07, S3).** When the
> `campaign` stamp is present, `finalize_iterate` re-projects
> `.shipwright/planning/iterate/campaigns/<slug>/status.json` from this
> worktree's event log (the canonical `campaign_status` producer — byte-identical
> to the `campaign_progress regenerate` CLI) and writes it into the worktree, so
> **F6 stages it** and the producer-owned board ships in the PR. This replaces
> the old write-once main-tree file; the autonomous-loop 3g main-tree
> `campaign_progress update-status` is demoted to a local-board convenience.
> Best-effort + no-op for a non-campaign iterate. Reads back at
> `result["steps"]["campaign_status"]`.

**Iterate-Rail per-phase durations (M-Pre-1 iterate half, §6a).**
`finalize_iterate` also reads this run's boundary-mark sidecar
(`.shipwright/agent_docs/iterates/<run_id>.phase_timings.jsonl`, written by the
§6a `mark` calls) and folds the computed per-group durations into the
`work_completed` event as `phase_timings`
(`[{phase, started, duration_ms}]`, groups `scope build review test finalize`).
Additive + best-effort: a run with **no** sidecar (or an empty one) leaves the
event unchanged, so partial history and pre-M-Pre-1 runs are fine — the WebUI
Iterate-Rail reads the field only when present. You do **not** pass timings on the
CLI; the fold is automatic (`lib.iterate_phase_groups.fold_into_event`).

**Context-cost meter (context-cost-meter).** Same shape: `finalize_iterate`
also reads THIS session's per-`Stop` cost summary
(`.shipwright/compliance/context-cost/<SHIPWRIGHT_SESSION_ID>.json`, kept
current by the additive `track_context_cost.py` `Stop` hook) and folds it
into `work_completed.context_cost` (`lib.context_cost_core.fold_into_event`),
additive + best-effort like `phase_timings` — no session id or no summary
file (no `Stop` has fired yet) leaves the event unchanged. This is a READ of
that file, not a fresh recompute — F5b has no `transcript_path` to recompute
from — so it is current through the end of the previous assistant turn
(`Stop` fires at every turn end). The block is stamped `measured_through:
"F5b"` + `measured_at`: it cannot include F6-F12 (commit, PR delivery, CI
rework), so it is always a *floor* on the run's real cost, never the whole
session — read it as such, not as the final total. `context_cost_summary.py
show --session-id "{session_id}" --project-root "{project_root}"` prints the
same file directly if you want to see it at any point without waiting for
F5b.

Reads back: `result["steps"]["event"]["id"]` — capture it so F6 can confirm
the event is present before staging `shipwright_events.jsonl` (and for the
legacy F6.5 SHA patch, used only by non-worktree callers).

The script is idempotent per `run_id` — re-invocations return the
existing event_id rather than recording a duplicate. If you skip this
step, the Stop hook will run it automatically as a fallback when the
session ends — but **without** the event_extras, so the enforced FR-gate
**rejects that fallback write** (it would be an unclassified event): nothing
is recorded and the failure is logged to stderr. For a clean F11 you **must**
call F5b yourself with the full metadata.

> **Note:** F7 (separate `record_event.py` call) is REPLACED by F5b (event
> recording into the worktree log) + F6 (staging it into the commit). The
> historical F7 / F7b are kept for the rare out-of-band case (event replay,
> non-worktree phases) — NOT needed for a normal worktree iterate, where the
> event already ships in the PR.
