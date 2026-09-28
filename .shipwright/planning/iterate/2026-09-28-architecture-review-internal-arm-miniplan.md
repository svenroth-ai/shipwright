# Mini-Plan: architecture-review-internal-arm

- **Run ID:** iterate-2026-09-28-architecture-review-internal-arm

## 1. Files to create/modify

| File | Change |
|---|---|
| `plugins/shipwright-plan/agents/architecture-internal-reviewer.md` | new — fresh-context agent, Read/Grep/Glob, model: inherit. Prompt explicitly forbids reading `plan.md`, `*-miniplan.md`, `decision_log.md`, or ADRs — judges only from the brief, the spec, and the codebase (anchoring defense; see item 4 below). |
| `shared/scripts/lib/review_record_schema.py` | edit — `REVIEW_TYPES`, `OPTIONAL_PRESENCE_TYPES` += `architecture_internal`, line-neutral (file is bloat `exception`, current 317/limit 300 — extend the existing tuple/frozenset literals in place, no new lines) |
| `shared/scripts/tools/verifiers/review_record_model_tier.py` | edit — `_ROLE_REVIEW_TYPES["plan_review"]` += `architecture_internal`; fix the stale "plan_review maps to plan_internal only" comment in the same edit |
| `shared/scripts/lib/review_payloads.py` | edit — comment only, name both metadata-only types |
| `shared/config/gate_catalog.json` (+ regenerated `gate_catalog.md`) | edit — new sibling auto-default entry, `default_answer` wording copied verbatim from the existing entry (only section names changed) |
| `plugins/shipwright-plan/skills/plan/references/step-5-external-review.md` | edit — new Step 5-int-arch; Step 5a re-reads/refreshes the existing brief instead of authoring it; explicit "does not carry the Pre-5b gate" sentence |
| `plugins/shipwright-plan/skills/plan/SKILL.md` | edit — one-line mention of Step 5-int-arch |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md` | edit — new step 0b (with degraded handling, resume reconciliation, mkdir, "does not carry the gate" sentence); step 2a re-reads/refreshes the existing brief |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` | edit — "Recording each review pass" table row (seven→eight); campaign sub-iterate rows table (new `not_run`-permanent row, folded onto the existing `plan_internal (3.5)` row where the bloat budget requires it) |
| `plugins/shipwright-iterate/skills/iterate/references/F11.md` | edit — "All seven" → "All eight"; `architecture_internal`'s trivial/small `not_applicable` disposition text, mirroring `plan_internal`'s |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md` | edit — "all seven types" → "all eight types" (Step 7) |
| `plugins/shipwright-iterate/agents/sub-iterate-runner.md` | edit — sibling `not_run` row for `architecture_internal`, folded into the existing `plan_internal (3.5)` row text if a net-new line would ratchet the bloat `exception` (current 528/limit 400) |
| `shared/prompts/codex_review_dispatch.md` | edit — document that `architecture_internal` has **no Codex transport yet**; the internal pass records `Ran: no (no Codex transport for architecture_internal yet)` under a Codex-driven session, same as any other degraded-handling reason. **No new `--role` value in this run** (see item 9, deferred). |
| `docs/hooks-and-pipeline.md` | edit — new agent block (x2 spawn sites), brief-authoring order, model-tier floor scope, Codex-deferred note |
| `docs/guide.md` | edit — light narrative mention |
| `shared/tests/test_review_record.py` | edit — cardinality 7→8 |
| `shared/tests/test_record_review_pass_cli.py` | edit — set membership + new CLI round-trip test |
| `shared/tests/test_review_record_model_tier_floor.py` | edit — new `architecture_internal` case, seeded `floors: {plan_review: ...}` config (see item 8) |
| `shared/tests/test_campaign_review_contract_prose.py` | edit — parallel prose assertion for the runner's new `not_run` invocation string |
| `shared/tests/test_review_payload_canonical_basenames.py` | edit — `- {"plan_internal", "architecture_internal"}` |
| `shared/tests/test_review_record_spec_promotion.py` | edit — `pending_types(...)` expected list gains `"architecture_internal"` at both call sites |
| `shared/tests/test_campaign_cascade_record_roundtrip.py` | edit — `_DELEGATED` gains the new type |
| `shared/tests/test_review_record_campaign_shape.py` | edit — new `CONTRACT_ROWS` row + disposition constant. File is bloat `grandfathered` (current 346/limit 300, no `exception`) — **must be net line-neutral**; offset by condensing an existing comment/blank line in the same file, not by requesting a baseline bump. |
| `shared/tests/test_review_record_roundtrip.py` | edit — hand-enumerated type list gains the new entry |
| `shared/tests/test_audit_e2e_integration.py` | edit — hand-enumerated type list gains the new entry |
| `shared/tests/test_compaction_state_audit_acceptance.py` | edit — hand-enumerated type list gains the new entry |
| `plugins/shipwright-security/tests/test_review_record_tier.py` | edit — hand-enumerated type list gains the new entry |
| `integration-tests/test_agent_model_frontmatter_unchanged.py` | edit — `EXPECTED_MODEL["plugins/shipwright-plan/agents/architecture-internal-reviewer.md"] = "inherit"` |
| `integration-tests/test_model_tier_spawn_instructions_present.py` | edit — new `SPAWN_ANCHORS` entries for both new spawn sites |
| new prose-contract test (name TBD at build time, sibling of `test_campaign_review_contract_prose.py`) | new — mechanically verifies AC1–AC4 (see item 8) |
| `.shipwright/planning/01-adopted/spec.md` | done — FR-01.03 AC22, FR-01.11 AC38 (this run) |

## 2. Work breakdown

1. **New agent.** Write `architecture-internal-reviewer.md`, modeled on
   `opus-plan-reviewer.md`'s frontmatter/shape but reviewing a brief + spec
   (not a plan), asking the existence/proportionality/simpler-alternative/
   ownership/forecloses question set from `shared/prompts/architecture_reviewer/system`,
   outputting the same `{reviewer, severity, findings[], summary}` JSON shape
   as `opus-plan-reviewer` (no verdict line — triage is fix/disclose/decline
   per finding, not approve/revise/reject). **Anchoring defense (fixes
   internal-review finding, medium; sharpened by this run's own external
   Branch A review, OpenAI finding #3 — "the fresh reviewer receives the
   full iterate spec, which already contains the Internal Plan Review
   section it is told to ignore"):** the prompt states explicitly that it
   must not read `plan.md`, `*-miniplan.md`, `decision_log.md`, or ADRs,
   AND that if the spec file it is handed contains an `## Internal Plan
   Review`, `## Self-Review`, or any other prior-review section, it must
   ignore that section's content entirely when forming its answer — judge
   the brief and the spec's Goal/ACs/Spec Impact/Out of Scope/Affected
   Boundaries as if the choice were open, exactly like the external
   architecture pass's own instruction. This defense is prose-only (the
   same softness the external pass itself accepts) — disclosed as a
   documented limitation in `docs/hooks-and-pipeline.md` (Branch A, GLM
   finding, low) rather than mechanically enforced. Test: none required for
   the prompt file itself; both prohibitions' presence is asserted by a
   small prose test (see item 8).
2. **Registry wiring.** Add `architecture_internal` to `REVIEW_TYPES` /
   `OPTIONAL_PRESENCE_TYPES` (`review_record_schema.py`, line-neutral — this
   file is a bloat `exception`) and to `_ROLE_REVIEW_TYPES["plan_review"]`
   (`review_record_model_tier.py`, fixing its stale comment in the same
   edit). `record_review_pass.py`'s `--review-type` choices and the F11
   `check_review_record` verifier both read these registries generically —
   confirmed no separate edit needed there. Test: update all 9 files listed
   in the Files table that hand-enumerate `REVIEW_TYPES`/`plan_internal`
   (`test_review_record.py`, `test_record_review_pass_cli.py`,
   `test_review_record_model_tier_floor.py`,
   `test_review_payload_canonical_basenames.py`,
   `test_review_record_spec_promotion.py`,
   `test_campaign_cascade_record_roundtrip.py`,
   `test_review_record_campaign_shape.py`,
   `test_review_record_roundtrip.py`, `test_audit_e2e_integration.py`,
   `test_compaction_state_audit_acceptance.py`,
   `plugins/shipwright-security/tests/test_review_record_tier.py`) plus the
   two `integration-tests` registries (`EXPECTED_MODEL`, `SPAWN_ANCHORS`).
3. **gate_catalog entry.** Add
   `plan.architecture-internal-review-high-severity-declined` (auto-default,
   `single_session`) alongside the existing `plan.internal-review-high-severity-declined`
   entry, `default_answer` copied verbatim (section names only changed). The
   `summary` states explicitly that this same `plan.`-prefixed id is reused
   unchanged by `/shipwright-iterate`'s own step 0b STOP (fixes Branch A
   finding, GLM medium — mirrors `plan_internal`'s existing reuse, no new
   `iterate.*` id minted). Regenerate `gate_catalog.md` via
   `resolve_gate_policy.py --render-doc` — never hand-edit it.
4. **Plan-side wiring.** In `step-5-external-review.md`: insert Step
   5-int-arch (write brief once, always, before branching; spawn the new
   agent; triage; write `## Internal Architecture Review`; log to
   `decision_log.md`; STOP on declined/disclosed high — the STOP reuses the
   existing `plan.internal-review-high-severity-declined`-sibling
   gate_catalog entry, see item 3). **Degraded handling and resume
   reconciliation (fixes Branch A finding, GLM #2 / OpenAI #4 — the first
   draft specified these for the iterate step but not the plan step):**
   mirror step 0b's rules exactly — same degraded reasons (capability
   failure / parse failure), same resume rule (`Ran: yes` section + pending
   row → record from the section, don't re-spawn; `Ran: no` → retry,
   replace the section in place, never append a second one). State
   explicitly: *this pass does not carry the Pre-5b Checkpoint / Step 5b
   gate — the checkpoint, `--findings-count`/`--reason`, and
   `plan_gate_extras`' decision-log count consider only Step 5-int and
   Branch A, unchanged.* Edit Step 5a: drop its own brief-authoring
   sub-step; instead **re-read the brief and, if Branch A's integration
   changed the options or the permanent additions, update it in place
   before the call** (never add rejection reasons — the one rule from
   `architecture_brief.md` stays binding). Edit `SKILL.md` Step 5's
   one-line summary to name both internal sub-steps.
5. **Iterate-side wiring.** In `iteration-planning.md`: insert step 0b
   (Internal Architecture Review, medium+ only, same gating as
   `plan_internal`), mirroring step 0's full shape — degraded-handling
   reasons (capability failure / parse failure / `shipwright-plan not
   installed`), resume reconciliation (section says `Ran: yes` but the row
   is still `pending` → record from the section, do not re-spawn; a
   recorded `Ran: no` is retried, replacing the section in place), and its
   own `mkdir -p` for the run's planning directory (step 0's `record` call
   creates it as a side effect but is skipped under degraded handling, so
   step 0b cannot rely on it having run). Same "does not carry the gate"
   sentence as item 4, scoped to iterate's own external-review branch logic.
   Edit step 2a to re-read/refresh the already-written brief instead of
   authoring it. Update `iteration-reviews.md`'s "Recording each review
   pass" table (seven → eight types) and its campaign sub-iterate rows
   table. Update `F11.md` ("All seven" → "All eight"; add
   `architecture_internal`'s trivial/small `not_applicable` disposition
   text). Update `SKILL.md` Step 7's "all seven types" → "all eight types".
6. **Campaign exclusion documentation.** Add the sibling `architecture_internal`
   row to `sub-iterate-runner.md` (permanently `not_run`, documented gap,
   identical wording pattern to the existing `plan_internal (3.5)` row) —
   fold onto the existing row's text (`plan_internal / architecture_internal
   (3.5)`) rather than adding a full new line, since this file is at its
   bloat `exception` cap (528/400) and a net-new line ratchets it. Test:
   extend `test_campaign_review_contract_prose.py` with the parallel
   invocation-string assertion.
7. **Docs.** `hooks-and-pipeline.md`: new agent blocks at both spawn sites,
   corrected brief-authoring-order prose, extended model-tier-floor scope
   note, and the Codex-deferred note (item 9). `guide.md`: light additive
   mention per this project's CLAUDE.md doc-update rule.
8. **Mechanical verification of AC1–AC4.** Add a small prose-contract test
   (sibling of `test_campaign_review_contract_prose.py`) asserting: "Step
   5-int-arch" appears after "Step 5-int" and before "## Branch A" in
   `step-5-external-review.md`; **no second `resolve_model_tier.py` call
   between Step 5-int and Branch A** (scoped assertion, not a brittle
   exact-count — fixes Branch A finding, GLM low: an exact-count assertion
   would break on any future unrelated second call in that file; the test's
   docstring/comment names the AC it enforces); Step 5a/step 2a no longer
   carry a "write ... architecture_brief.md from the template" instruction
   (only a re-read/refresh instruction); the new agent name + a `model=`
   anchor appear at both spawn sites (register both in
   `integration-tests/test_model_tier_spawn_instructions_present.py`'s
   `SPAWN_ANCHORS`); and both anchoring-defense prohibitions (item 1) are
   present in `architecture-internal-reviewer.md`'s prompt text. Before
   writing the model-tier floor probe, **read
   `test_review_record_model_tier_floor.py`'s existing `plan_internal` case
   first and mirror its exact `--model-tier` value and scratch-config
   shape** (fixes Branch A finding, GLM low — do not guess the expected
   outcome); extend it with an analogous `architecture_internal` case using
   a real `floors: {plan_review: opus}` entry in
   `shipwright_model_config.json`, plus a negative control (a Codex-driven
   record for `architecture_internal` produces no floor note, since Codex
   has no transport for this type yet — see item 9).
9. **Codex dispatch — explicitly deferred, not built.** Per operator
   confirmation (2026-09-28, in-session): under a Codex-driven session
   (Codextender or Codex Light), `architecture_internal` has no transport
   yet — reusing `review_via_codex.py --role plan_review` was considered and
   rejected because `plan_review` requires `--plan-file` (this pass reviews
   a brief, not a plan) and its canonical reply basename
   (`plan_review_reply.json`) would collide with the actual Internal Plan
   Review's own reply, silently corrupting one or the other. Instead: the
   Codex-driven degraded-handling path records
   `Ran: no (no Codex transport for architecture_internal yet)`, the same
   shape as any other degraded reason in step 0b / Step 5-int-arch. A
   follow-up card builds a fifth Codex role (own schema, own basename,
   `--brief-file` instead of `--plan-file`) mirroring how `external_review.py`
   added `--mode architecture` as a genuinely new mode rather than reusing
   `--mode plan` — that CLI never had this collision because it does not
   persist a canonical reply file at all; each call's JSON is consumed
   inline by its caller. Test: none new (a `Ran: no` branch, verified by the
   negative control in item 8).
10. **Bloat budget.** Three touched files sit at or near their
    anti-ratchet cap (`sub-iterate-runner.md` exception 528/400,
    `review_record_schema.py` exception 317/300,
    `test_review_record_campaign_shape.py` grandfathered 346/300 — see
    items 2, 5, 6). Keep the two `exception`-state files' edits line-neutral
    by extending existing literals in place; keep the `grandfathered` file's
    edit strictly line-neutral by condensing elsewhere in the same file
    (grandfathered files cannot have their baseline bumped — only
    `exception`-state entries can, and only with a proper ADR). Refresh the
    baseline last, per this repo's own rule, only if an exception-state
    file's edit turns out not to be achievable line-neutral.
11. **This run's own round-trip proof.** Exercise the new type for real:
    `record_review_pass.py record --review-type architecture_internal
    --status completed ...` then `... show` against a scratch run with a
    real `floors: {plan_review: ...}` config present, confirming the row
    appears, the model-tier floor verifier reads it and names it in its
    note, and `check_review_record` treats it as any other `REVIEW_TYPES`
    member. This is the Boundary Probe for the `touches_io_boundary` risk
    flag (JSON producer/consumer pair added to `reviews.json`) and doubles
    as this run's own E2E/CLI surface verification (Step 11a/11b, F0.5).
12. **webui-consumer confirmation (fixes Branch A finding, GLM medium).**
    This repo does not contain the webui — it is a separate repository
    (`shipwright-webui`, since v0.4.0) that reads `reviews.json` as a
    generic consumer. No cross-repo contract governs `REVIEW_TYPES`'s shape
    specifically (checked: `shared/contracts/compliance.py`,
    `shared/contracts/iterate.py` — neither references it); instead,
    FR-01.11 AC14 (`iterate-2026-08-03-p2-33-deepseek-zdr-review`) already
    requires every reader to treat an unrecognized-but-well-formed review
    type as readable, not an error — exactly the additive-growth guarantee
    this change relies on, and the same guarantee `plan_internal` itself
    relied on. No webui-side file or test is added; recorded here so it is
    not re-litigated at build time.

## 3. Component hierarchy
n/a — no UI.

## 4. Data model changes
None (no database). `reviews.json`'s `REVIEW_TYPES` enum gains one additive
member — backward-compatible, per the file's own documented growth pattern.

## 5. Test strategy
- Unit: the ~15 shared/plugin test files listed above, extended in place.
- New mechanical prose-contract test for AC1–AC4 (item 8).
- CLI round-trip (Boundary Probe + this run's E2E): item 11 above, with a
  seeded model-tier floor config and a Codex-transport negative control.
- Full test suite runs for the touched roots: `shared/tests`,
  `plugins/shipwright-plan/tests`, `plugins/shipwright-iterate/tests`,
  `plugins/shipwright-security/tests`, **and `integration-tests`** (missed
  in the first draft of this plan — the agent-frontmatter and spawn-anchor
  registries live there).
- No E2E/browser layer — this project has no startable web surface for this
  change; verification is the CLI round-trip above.

## 6. Alternative approaches considered — rejected

**Alternative A (the real design alternative): section-only, no
`REVIEW_TYPES` row** — like the external Architecture Review, which "adds no
review row and no marker" and records its outcome only in `plan.md` /
the iterate spec section. This was flagged by this run's own Internal Plan
Review as the alternative the mini-plan should actually have weighed, since
minting an 8th `REVIEW_TYPES` member ripples through ~15 test files, the
campaign runner contract, and the webui consumer, while the external pass
avoided all of that by staying section-only.

**Rejected because:** the operator's card decided this explicitly and named
the reason — "Without a marker row F11 cannot verify the pass ran, and the
measured truncation class (`llm_review.py` reported cut-off replies as
success) makes that a silent-failure path, not a bookkeeping nicety,"
adding "MODEL stays plan_review, resolved explicitly - the card's reasoning
is unchanged and binding." A section-only design (mirroring the external
pass) cannot be mechanically enforced by F11 the way a `REVIEW_TYPES` row
can — exactly the gap this pass exists to close for the *internal* plan
review, which is why `plan_internal` itself already made the same choice.
The ~15-file ripple is the accepted, named cost of that guarantee, not an
oversight.

**Alternative B: a dedicated `architecture_review` model-tier role** instead
of reusing `plan_review`. **Rejected because:** same moment, same artefact
family, same kind of agent as the internal plan review, so it takes the same
dial; minting a fifth role when `ROLES` is a flat set with no inheritance
would mean tracking two dials that should move together, and the card
explicitly names the silent-divergence risk of not doing this. Re-deriving
this from scratch was explicitly out of scope ("DO NOT RE-OPEN").

## 7. Internal Plan Review disposition (this run)

Ran: yes (opus-plan-reviewer, model tier `plan_review`=opus). Overall
severity: high. 11 findings — 9 fixed (integrated above), 1 disclosed
(Codex dispatch transport gap, item 9 — user-confirmed in-session, since it
is `severity: high`), 1 declined (the role-reuse framing of Alternative B
above was already answered by the operator's binding decision; no scope
change results). Per iterate's own Internal Plan Review protocol, this
outcome is written into the iterate spec's `## Internal Plan Review` section
(not `decision_log.md` directly — that is deferred to the iterate ADR at
F3) and recorded in this run's `reviews.json` (`--review-type plan_internal`).
