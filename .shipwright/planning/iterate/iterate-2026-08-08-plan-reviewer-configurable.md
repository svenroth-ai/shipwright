# Iterate Spec: plan-reviewer-configurable

- **Run ID:** iterate-2026-08-08-plan-reviewer-configurable
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal
Two gaps, one fix. `opus-plan-reviewer`'s model is hard-wired to `opus` in its
own agent frontmatter, immune to the per-run/per-project model-tier mechanism
(`trg-88621183` / P2.45, PR #599) the rest of the review cascade now has — a
mistaken dismissal (`trg-cb2b8cb9`, 2026-08-07) assumed this was already
covered under the shared `review` role; VERIFIED 2026-08-08 it is not (`grep
opus-plan-reviewer` over `model_tier_config.py` + `resolve_model_tier.py`:
zero hits; `plugins/shipwright-plan/` has zero references to the resolver).
Second, `/shipwright-iterate`'s own mini-plan review (`iteration-planning.md`,
`external_review.py --mode iterate`) has the exact asymmetry Step 5 had
before `iterate-2026-08-07-plan-reviewer-wiring`: external-only, with a
Self-Review Fallback when unavailable, no internal reviewer arm at all.

This iterate: (1) adds a dedicated `plan_review` role to the model-tier
mechanism — not the shared `review` role, because this repo's own
`shipwright_model_config.json` already pins `review: sonnet` and reusing it
would silently downgrade the internal plan reviewer instead of making it
configurable; (2) wires `/shipwright-plan` Step 5-int's `opus-plan-reviewer`
spawn to resolve it; (3) gives `/shipwright-iterate`'s own mini-plan review an
equivalent internal arm, mirroring the Pre-5b-Checkpoint pattern, wired to the
same role. `plan_review` follows the existing precedence exactly (flag >
project config > unset/inherit) and ships no default tier of its own — this
repo's config sets `plan_review: opus` as ITS worked example, to keep this
repo's own behavior unchanged, not as a shipped default for consumers.

## Acceptance Criteria
- [ ] AC-1: `model_tier_config.py`'s `ROLES` gains `plan_review` as a fourth
      member; `load_model_config`, `resolve_model_tier`, `agent_model_param`
      and the `floors` handling all work for it with no role-specific code
      (they already iterate `ROLES` generically).
- [ ] AC-2: `resolve_model_tier.py` CLI gains `--plan-review-model`, resolves
      all four roles in one call, same JSON shape. The `_warn` path in
      `resolve_model_tier` interpolates the role name into an invalid-tier
      message (`--{role}-model=...`); with `role == "plan_review"` that reads
      `--plan_review-model` (underscore), a flag that does not exist. Add a
      role→flag-name mapping (`role.replace("_", "-")`) so the warning names
      the real flag, `--plan-review-model`.
- [ ] AC-3: `model_config.schema.json` gains `plan_review` (`Tier`) and
      `floors.plan_review` (`RankedTier`), same as the other three roles.
- [ ] AC-4: `/shipwright-plan` Step 5-int (`step-5-external-review.md`)
      resolves `plan_review` (via `resolve_model_tier.py`) before spawning
      `opus-plan-reviewer` and passes the resolved tier as the Agent tool's
      `model=` parameter when it is not `inherit`; when `inherit`, the
      parameter is omitted (today's behavior, unchanged for an unconfigured
      project). `opus-plan-reviewer.md`'s frontmatter changes `model: opus` →
      `model: inherit`, matching every other agent under `plugins/*/agents/`
      (`model_tier_config.py`'s own docstring: "Every agent definition...
      carries `model: inherit`"). Without this, AC-4/AC-6 rest on an unverified
      assumption — that an explicit Agent-tool `model=` beats a frontmatter
      pin — that this iterate has no way to test from inside a session; removing
      the pin removes the question. `opus-plan-reviewer.md`'s prompt body,
      JSON output contract, and `tools:` line are unchanged (still out of
      scope — see below).
- [ ] AC-5: `/shipwright-iterate`'s mini-plan review (`iteration-planning.md`)
      gains an internal reviewer arm, structurally mirroring Step 5-int: runs
      before Branch A/B/C, **medium+ complexity only** (trivial/small have no
      iterate spec and no mini-plan file for the reviewer to read),
      `Ran: yes|no` recorded in the iterate ADR, findings triaged
      fix/disclose/decline (decline needs a recorded reason), a declined
      `severity: high` finding STOPs and asks the user before Step 6.
      **Verified 2026-08-08: unlike `/shipwright-plan`, iterate has no
      Self-Review Fallback to gate** — its own self-review already runs
      unconditionally at every complexity (`iteration-planning.md` line 189:
      "Self-review is mandatory for ALL complexity levels"), so this arm adds
      an independent layer alongside it rather than replacing or triggering
      a fallback; a missed internal pass means one fewer independent review,
      not an unreviewed run. Reuses the existing `opus-plan-reviewer` agent via a
      cross-plugin `Agent` spawn (`shipwright-plan:opus-plan-reviewer`) rather
      than a duplicate agent definition — confirmed spawnable from within a
      `/shipwright-iterate`-driven session (empirical probe: this iterate's
      own internal plan review, spawned during its own planning phase,
      2026-08-08). Consumers who install only `shipwright-iterate` (no
      `shipwright-plan`) will have the spawn fail; `iteration-planning.md`
      and `docs/hooks-and-pipeline.md` document the cross-plugin dependency
      explicitly, and a failed spawn is reported as `Ran: no (shipwright-plan
      not installed)` rather than an unexplained skip.
- [ ] AC-6: The internal arm's spawn in `/shipwright-iterate` also resolves
      `plan_review` for its model, identically to AC-4.
- [ ] AC-7: A new, additive `REVIEW_TYPES` member `plan_internal` is minted in
      `review_record_schema.py` (the module's own docstring: the tuple "is
      additive" — no `SCHEMA_VERSION` bump needed). **Verified 2026-08-08:**
      `record_review_pass.py` is never called anywhere under
      `plugins/shipwright-plan/` — the review-record system
      (`reviews.json`, `record_review_pass.py`) is exclusively an
      `/shipwright-iterate` artifact, keyed by iterate `run_id`. Step 5-int
      (`/shipwright-plan`, used standalone inside `/shipwright-project`'s
      greenfield pipeline) genuinely has no run to record a row against —
      "no marker of its own" is correct as already written and stays
      unchanged. Only **AC-5's new iterate-side internal arm** records a
      `plan_internal` row, via `record_review_pass.py --review-type
      plan_internal --model-tier <tier>`, when it actually runs. This is a
      *new*, dedicated row — not the existing `plan` type,
      which is the external plan/iterate review's own row (`MARKER_TYPES =
      {"plan": "iterate", ...}` in `review_companion.py`; `iteration-planning.md`
      step 5 writes it from `external_review.py` output only, and today's
      internal fallback pass — per `step-5-external-review.md` — writes no
      record row of its own at all: "No marker of its own... Provenance is
      plan.md + decision_log.md"). Pointing a floor at `plan` would silently
      misjudge the wrong pass, or flag the external non-Claude call as
      missing a Claude model tier. `review_record_model_tier.py`'s floor-note
      generalizes from a single hardcoded `review`-role check to a small
      `{role: review_types}` map: `{"review": ("spec", "code", "doubt"),
      "plan_review": ("plan_internal",)}` — same advisory-only contract, no
      new blocking behavior.
- [ ] AC-8: This repo's own `shipwright_model_config.json` gains
      `"plan_review": "opus"`, so this repo's actual behavior is unchanged by
      the wiring (today: always opus, hardcoded; after: opus, via config).
      **Verified 2026-08-08 this file is currently untracked** at the main
      repo root (`.gitignore` has `!/shipwright_*_config.json`, making it
      eligible, but it has never been `git add`ed) — this AC includes
      `git add`ing it as part of this iterate's commit, so the change is a
      real, reviewable diff rather than a local-only edit invisible to CI
      and reviewers.
- [ ] AC-9: `docs/guide.md` and `docs/hooks-and-pipeline.md` reflect the new
      role and iterate's internal arm. **Verified 2026-08-08:** `/shipwright-plan`
      has no invocation-level flags at all today (`@spec.md` only) — Step
      5-int resolves `plan_review` from project config alone, no
      `--plan-review-model` flag invented for it; its Appendix B row instead
      notes the reviewer's model is now project-configurable. `/shipwright-iterate`'s
      Appendix B row (it already has `--review-model`/`--finalization-model`)
      gains `--plan-review-model` for real, consistent with those. Also
      updated (stale runtime prose an agent actually reads, not cosmetic):
      `model_tier_config.py`'s module docstring + `#: The three spawn roles`
      comment (now four); `resolve_model_tier.py`'s docstring/usage/example
      output; `model_config.schema.json`'s top-level description and its
      `floors` description ("Only the 'review' role has a consuming check
      today" — now two); `shipwright-iterate` `SKILL.md`'s `Usage:` line and
      §F model-tiers summary; `iteration-planning.md`'s §F block;
      `campaign-mode.md`'s invocation line. Note in the changelog entry that
      a stale plugin-cache install may log `unrecognized key(s)
      ['plan_review']` for a project config carrying the new key — benign,
      resolved by `bash scripts/update-marketplace.sh`.
- [ ] AC-10: AC-5's STOP-and-ask path (a declined high-severity internal-review
      finding) reuses the existing gate id
      `plan.internal-review-high-severity-declined` rather than minting a new
      one. **Verified 2026-08-08:** `gate_policy.py`'s `COVERED_PHASES =
      ("project", "design", "plan", "build", "deploy")` has no `"iterate"`
      entry, and `validate_catalog` rejects both an unrecognized phase and an
      id not prefixed by its own phase — an `iterate.*` id would fail CI's
      catalog validation outright. No `gate_catalog.json` change is needed.
- [ ] AC-11: Test coverage for AC-1/2/3/7. Update
      `test_resolve_model_tier_cli.py`'s existing "all three roles" assertion
      and docstring to four roles; add `plan_review` cases to
      `test_model_tier_config.py`; add a `plan_internal`/`plan_review` case to
      the model-tier floor-note test; add a test asserting the AC-2 warning
      names `--plan-review-model` (not `--plan_review-model`); the Boundary
      Probe round-trip test named in Confidence Calibration below.

## Spec Impact
- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.03 (`/shipwright-plan`) — folds "and the reviewer's model
  is configurable via the project's model-tier config, defaulting to the
  session model when unset" onto the existing independent-reviewer AC.
  FR-01.11 (`/shipwright-iterate`) — folds the same internal-arm + model-tier
  behavior onto its existing review-pass AC (line ~739: "the plan review, the
  code review, the doubt pass and the outside review").
- **REMOVE:** none
- **NONE justification:** n/a

## Out of Scope
- Any change to the `review`/`finalization`/`execution` roles' own resolution,
  precedence, or shipped defaults.
- Model-tier configuration for anything beyond `plan_review` (no fifth role).
- Campaign sub-iterates' mini-plan review — `sub-iterate-runner` has no
  `Agent` tool (per SKILL.md 5b); the internal arm there is a documented gap
  (`trg-71d7a4fa`/`trg-d6cc3d3d`), not this card's to close.
- `opus-plan-reviewer.md`'s own prompt body, JSON output contract, and
  `tools:` line — only its `model:` frontmatter field (AC-4) and its
  consuming spawn sites change.

## Internal Plan Review

**Ran: yes** — `shipwright-plan:opus-plan-reviewer` spawned (model=opus,
explicit) against this iterate's own spec + mini-plan during planning,
2026-08-08. This doubled as the empirical probe for AC-5's cross-plugin-reuse
design question (confirmed spawnable — see AC-5).

Findings (severity: high) and disposition:
1. AC-7 pointed the floor at the external `plan` review-record row instead of
   the internal pass — **fixed**: new `plan_internal` review type (AC-7,
   above).
2. AC-10's `iterate.*` gate id would fail `gate_policy.py`'s `COVERED_PHASES`
   validation — **fixed**: reuse the existing `plan.*` gate id instead (AC-10,
   above).
3. AC-4/AC-6 rested on an unverified assumption that the Agent tool's
   `model=` parameter beats `opus-plan-reviewer.md`'s `model: opus`
   frontmatter pin — **fixed**: bring the frontmatter line into scope, change
   it to `model: inherit` (AC-4, above), removing the pin instead of relying
   on unverifiable precedence.

Findings (severity: medium), all **fixed** by folding into the ACs above:
missing test coverage for the new role (AC-11), ambiguous complexity gating
for the iterate internal arm (AC-5: medium+ only), silent degradation when
`shipwright-plan` isn't installed (AC-5: explicit `Ran: no` message),
`shipwright_model_config.json` untracked at the main root (AC-8: `git add`
it), and a role-name→flag-name bug in the CLI's warning path (AC-2).

Findings (severity: low): doc/docstring drift across six additional
runtime-prose locations — folded into AC-9. A forward-compat stderr warning
on a stale plugin cache — noted in AC-9's changelog guidance, no code change
needed.

No findings were declined. Full review transcript available in this
session's Agent tool call log if needed.

## Design Notes
n/a — no UI. Agent-instruction wiring + a shared-lib role addition + one
schema file + one repo-config file.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shipwright_model_config.json` (operator-authored) | `model_tier_config.load_model_config` | JSON, `plan_review` key added |
| `resolve_model_tier.py` CLI stdout | `/shipwright-plan` Step 5-int, `/shipwright-iterate` internal-review step (skill prose reading tool output) | JSON, `plan_review` key added |
| `record_review_pass.py` → `reviews.json` | F11's `check_review_record`; cross-repo, `shipwright-webui`'s `review-record.ts` (versioned contract, floor `>=1`) | JSON, new `REVIEW_TYPES` member `plan_internal`. AC-7's `validate_record` presence-check exemption for `plan_internal` (`review_record_schema.py`) is the minimal ripple this addition forces: without it, "every `REVIEW_TYPES` member present" would call all 65+ pre-existing, immutable, git-tracked records corrupt. `test_every_record_on_disk_still_validates` (`test_review_record_spec_promotion.py`) is the round-trip probe — it re-validates the actual on-disk corpus, not a reconstruction, so a regression here is caught mechanically rather than by inspection. No webui-side change needed: unrecognized `reviews` keys already render as rows (the `spec` promotion's own release condition, above) |

`touches_io_boundary` (small min floor): `shipwright_model_config.json` and
`model_config.schema.json` both match the `*_config.json`/schema patterns —
Boundary Probe required (round-trip test on the new `plan_review` key through
`load_model_config` → `resolve_model_tier` → `agent_model_param`).

## Confidence Calibration
- **Boundaries touched:** see Affected Boundaries above.
- **Empirical probes run:** (recorded after Step 6/7 — see ADR)
- **Test Completeness Ledger:** (recorded after Step 6/7 — see ADR)
- **Confidence-pattern check:** (recorded after Step 6/7 — see ADR)

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (only if surface=none):** Shared-lib + schema + agent-
  instruction prose; no startable web/cli/api surface. Verified via the
  pytest suites, the CLI's own smoke tests, and a live cross-plugin dogfood
  spawn of `opus-plan-reviewer` from within `/shipwright-iterate` context.

## External Plan Review (Branch A)
- **Verdicts:** deepseek=approve · openai=revise (not contradictory — within
  one step; `requires_resolution: false`).
- **Findings and disposition:**
  1. HIGH (openai) / MEDIUM (deepseek) — `review_record_schema.py` needs a
     `validate_record` presence-check exemption for `plan_internal`, or the
     historical corpus reads as corrupt — **already fixed**: AC-7's inline
     `t != "plan_internal"` exemption, proven by
     `test_every_record_on_disk_still_validates` (65+ records).
  2. MEDIUM (openai) — `--plan-review-model` risked being documented as a
     `/shipwright-plan` flag it cannot accept — **already fixed**:
     `step-5-external-review.md` explicitly states no such flag exists there;
     the real flag lives on `/shipwright-iterate` only (AC-2, AC-5).
  3. MEDIUM (openai) — unclear where `/shipwright-iterate` parses and
     forwards `--plan-review-model` — **already fixed** for the standalone
     path: SKILL.md's banner + `iteration-planning.md`'s "Model Tier
     Resolution" section forward the invocation flag verbatim into
     `resolve_model_tier.py`. Campaign-mode propagation stays **declined**
     — explicitly Out of Scope in this spec (`trg-71d7a4fa`/`trg-d6cc3d3d`).
  4. MEDIUM (openai + deepseek) — `opus-plan-reviewer`'s `model: opus` →
     `model: inherit` is a real behavior change for an unconfigured project,
     not "today's behavior, unchanged" — **already fixed**: both
     `step-5-external-review.md` and the CHANGELOG entry state the change
     explicitly. This repo's own `shipwright_model_config.json` sets
     `plan_review: opus` by decision (AC-8), so THIS repo's own behavior is
     unaffected by the frontmatter change — a consumer project that leaves
     `plan_review` unset is the one whose behavior actually changes.
  5. MEDIUM (openai) — failure classification should distinguish
     agent-unavailable / parse-failure / not-installed rather than lumping
     them — **already fixed**: `iteration-planning.md`'s degraded-handling
     paragraph already names all three reasons distinctly, and a
     `plan_internal` review-record row is written only on `Ran: yes`.
  6. LOW (openai) — spec/mini-plan should be confirmed finalized before the
     reviewer is spawned — **disclosed**: true by construction (this step
     runs after Steps 1-3 in the phase order), no new gate needed.
  7. LOW (openai) — webui compatibility for the new `plan_internal` row
     should be fixture-verified, not assumed — **disclosed**: relies on the
     already-proven precedent (`iterate-2026-07-31-review-record-spec-promotion`'s
     own release condition — unrecognized `reviews` keys already render as
     rows); adding a new fixture is out of scope for this card.
  8. LOW (deepseek) — the exact spec+mini-plan invocation shape for the
     reviewer prompt wasn't spelled out — **disclosed**: `iteration-planning.md`
     step 0 names both file paths explicitly; the prompt-construction detail
     is left to the calling agent, same as every other subagent spawn in
     this skill.
  9. LOW (deepseek) — `shipwright_model_config.json` going from untracked to
     tracked affects every developer — **disclosed**: intentional and covered
     by AC-8; the file's contents stay minimal (`plan_review: opus`, the one
     key this iterate adds, preserving today's behavior for this repo).
- No high-severity finding was declined — the one HIGH (openai's #1) was
  already fixed by the implementation, so no STOP-and-ask was needed.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-08-plan-reviewer-configurable/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — add
  `plan_review` to the existing generic model-tier mechanism, drop the
  agent's hard-coded pin, reuse the existing reviewer agent and
  review-record infrastructure.
- **Findings:** none.
- **Reconciliation:** n/a — both reviewers confirmed the smallest-thing
  framing the mini-plan already used; no alternative was proposed to
  reconcile against.
- **Status:** proceeding as planned.

## External-Code-Review-Findings
- **Verdicts:** deepseek=revise · openai=revise (both cite the same two HIGH
  findings; contradiction check: not required, verdicts agree).
- **HIGH — `iteration-planning.md:206`, Internal Plan Review step reads as
  ungated.** Both reviewers read step 0's "always, before Branch A/B/C" as
  running at every complexity. In the actual file it sits under the
  `### Medium / large complexity` heading (line 202), so AC-5's medium+ gate
  was already structurally correct (confirmed independently by spec-reviewer)
  — but the wording was genuinely ambiguous read on its own. **Fixed:**
  reworded the step-0 heading to state the gate inline: "(medium+ only —
  always before Branch A/B/C at this complexity; never runs for trivial/small,
  which close `plan_internal` as `not_applicable` per Step 7 instead)".
- **HIGH — `shipwright_model_config.json` "missing from diff".** Both
  reviewers flagged the repo-root config as absent. **Partially correct, and
  the first disposition written here was wrong.** The file does exist in this
  worktree with `{"plan_review": "opus", ...}`, untracked (`??`) until F6's
  commit, so the diff both external reviewers were given (`git diff`, which
  omits untracked files) never showed it to them — that half is a
  diff-generation gap, not a spec gap. But code-reviewer's Stage 2 pass (see
  its BLOCKING finding) caught that the **main repo root's own copy of the
  same file** (`C:\01_Development\shipwright\shipwright_model_config.json`,
  a separate untracked file from the worktree's) had no `plan_review` key at
  all — and `model_tier_config._config_path()` resolves from the MAIN repo
  root, never the worktree's own copy, by documented contract. So until this
  fix, `resolve_model_tier("plan_review", ...)` genuinely returned
  `("inherit", "unset")` from every context, worktree included, and the
  original "verified by this run's `plan_internal` row" evidence was false —
  that row's `model_tier: opus` came from the then-still-present agent
  frontmatter pin, not from the config mechanism this iterate exists to add.
  **Fixed:** added `plan_review: opus` to the main repo root's copy too (now
  byte-identical to the worktree's); re-verified empirically via
  `resolve_model_tier.py --project-root .` from the worktree, which now
  prints `"plan_review": {"resolved": "opus", "source": "project_config",
  "agent_param": "opus"}`. AC-8's ledger evidence updated to cite this
  command output instead of the earlier unverified assertion.
- **LOW (deepseek) — `test_plan_review_invalid_flag_warns_with_hyphenated_flag_name`
  only asserted the flag name, not that the "invalid tier" message survived.**
  **Fixed:** added `assert "is not a valid tier" in err`; re-ran
  `shared/tests/test_model_tier_config.py` — 24/24 passed.

## Doubt-Reviewer Findings (Stage 3)
Triggered by the cross-plugin spawn (`shipwright-iterate` → `shipwright-plan:opus-plan-reviewer`).
Two of the four attacked lenses (F11 hard-failing a `shipwright-plan`-less
consumer; the `OPTIONAL_PRESENCE_TYPES` exemption's blast radius) were traced
end-to-end and **disproven** — see the agent's own report for the file:line
chain. 5 doubts survived (3 medium, 2 low), none blocking (advisory-must-address):

- **MEDIUM — reversibility: editing the MAIN repo root's `shipwright_model_config.json`
  is invisible to the worktree-isolation leak-guard** (it compares dirty paths
  by PATH, not content — an already-dirty path's content edit is structurally
  unseen). **Disclosed, not fixed in code** — this is an operator-environment
  concern outside this PR's diff, not something a worktree-scoped iterate
  should try to "fix" by touching main-tree state further. **Confirmed live
  during this same run:** the main-root file's `review` key changed from
  `sonnet` to `opus` in a concurrent, independent edit (not made by this
  iterate) while this fix round was in progress — the two copies now
  genuinely diverge on `review` (this PR's committed copy keeps `review:
  sonnet`, unchanged, since that key is out of this iterate's scope). Per
  the doubt's own prediction, this **may** produce a `git pull` "untracked
  working tree file would be overwritten by merge" abort in the main tree
  after this PR merges, if the operator's copy still differs from the
  merged one at that time. Operator note for the handoff: reconcile with
  `git diff` before pulling, or accept the incoming (post-merge) content if
  the concurrent edit was itself meant to be short-lived.
- **MEDIUM — concurrency: the iterate-spec section and the `plan_internal`
  review-record row are two separate writes; a crash between them could
  produce a record that contradicts the spec.** **Fixed:** added resume
  reconciliation prose to `iteration-planning.md` step 0 (record the row
  from the existing section on resume, don't re-spawn) and made retry
  overwrite the section in place instead of appending a second heading.
- **MEDIUM — reversibility: F6's explicit staging list has no line for
  root-level configs a run itself modified, and the cited re-verification
  (`resolve_model_tier.py`) reads the working tree, not the commit.**
  **Disclosed, not a durable F6.md change** — a root-level operator config
  isn't a per-run F6 artifact every iterate touches (this run's is a one-off
  worked example per AC-8), so hard-coding it into F6's general list would
  over-scope. This run's own F6 step explicitly `git add`s the worktree's
  `shipwright_model_config.json`; the real post-commit evidence (`git show
  --stat HEAD -- shipwright_model_config.json`) is captured at F6 below.
- **LOW — boundary: the `plan_internal` row's `findings_count: 0` reads as
  "clean" to a consumer that never sees the skill-prose caveat.** **Fixed:**
  re-recorded the row with `--disposition "findings live in the iterate
  spec's ## Internal Plan Review section; this row is metadata-only
  (findings_count is structurally always 0)"` so the caveat travels with the
  artifact itself, not just the skill prose.
- **LOW — hidden coupling: this diff's two halves (agent frontmatter in
  `shipwright-plan`, spawn-time `model=` wiring in `shipwright-iterate`)
  live in different plugin trees; a partial `update-marketplace.sh` sync
  after push would silently run the reviewer on the session tier with no
  error.** **Disclosed** — already covered by the project's standing
  post-push requirement (`CLAUDE.md`: run `scripts/update-marketplace.sh`
  after every push touching `plugins/*`, verify with
  `check_plugin_cache_sync.py --strict`); flagged here only because this
  run's cross-plugin split makes a *partial* sync uniquely easy to miss.
