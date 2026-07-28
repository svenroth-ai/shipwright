# Iterate — the review cascade is a standing request; workflows are not

- **Run ID:** `iterate-2026-07-28-review-subagents-standing-request`
- **Intent:** CHANGE · **Complexity:** medium (`prior_source: keyword`)
- **Spec Impact:** NONE

## 1. Problem

Claude Code ships two lines as literal constants inside `claude.exe` (proven
2026-07-28: `grep -c -a "unless the user requested"` → exactly 2; reproduced in
an empty scratch directory outside any repo):

```
Do not call the AgentTool unless the user requested it
Do not use workflows or deep-research unless the user requested it
```

Nothing local can remove them — settings, both `CLAUDE.md`, the launcher and the
repo were all searched and ruled out. The result is that Shipwright's reviewer
cascade, which the constitution makes an **ALWAYS** rule and the phase matrix
makes *"medium+ → always"*, is gated behind a per-session request the operator
usually is not present to give. Five runs are on record recording
`code = not_run` for exactly this reason.

**The two halves are not the same thing, and Anthropic's own tool contracts say
so.** The Workflow tool carries an explicit opt-in requirement — *"ONLY call
this tool when the user has explicitly opted into multi-agent orchestration …
the user must request that scale, not have it inferred"* — with named criteria.
The Agent tool carries **no such gate**; its description simply says when
delegation is useful. The system-prompt line lumps them together; the contracts
do not. The concern the docs state is cost: *"Each active teammate keeps
consuming tokens until it exits"*, and `/usage` attributes spend per subagent.

So the honest reading is: **the scale decision belongs to the operator, and a
standing instruction is a legitimate way for the operator to make it once.**

## 2. Decision

- **AC1 — `CLAUDE.md` carries the standing request.** A section states plainly
  that spawning review subagents is requested by default for this project, so
  the session does not pause to re-request it and does not record a review
  `not_run` citing a session policy. Claude Code frames `CLAUDE.md` as
  instructions that *"OVERRIDE any default behavior"*, which is what makes this
  the right instrument rather than plugin prose.
- **AC2 — Dynamic workflows and deep-research are explicitly NOT covered.** The
  same section says the grant stops at subagents: workflows fan out to many
  agents with an open-ended cost, so that decision is asked for every time and
  must not be inferred from this grant.
- **AC3 — It ships.** The section exists in all three places that carry this
  text: `shared/templates/claude-md-template.md` (greenfield), the hardcoded
  f-string in `plugins/shipwright-adopt/scripts/lib/claude_md_renderer.py`
  (brownfield), and this repo's own `CLAUDE.md`. A drift test asserts the mirror,
  matching the pattern already used for the plain-language and keep-it-lean rules.
- **AC4 — The iterate prose defers to the grant, so there is no ambiguity.**
  #489 told Step 8 to ask before Stage 1 and gave `iteration-reviews.md` a
  four-blocker definition. With AC1 in place that instruction would contradict
  `CLAUDE.md`. Both now state the precedence explicitly: **a standing grant
  satisfies the policy — do not ask, spawn.** The ask-first path remains as the
  fallback for a project without the grant, and the four blockers are unchanged
  (a genuinely absent `Agent` tool, a tool error, an autonomous campaign
  sub-iterate, an in-session decline still block).

## 2a. What the external plan review changed

gemini `approve`, openai `revise`.

- **openai #1 (high) — the central assumption was unvalidated.** Fair: I was
  asserting that a checked-in `CLAUDE.md` satisfies a runtime gate. Measured
  instead — see §3c for the result that ships. (The first probe recorded here
  predated Stage 2's rewrite of the section; Stage 3 caught that this paragraph
  was citing a measurement of text that no longer exists. It has been re-run
  against the shipped wording, with a negative control.)
- **gemini #1 + openai #2 (medium) — other phase skills may contradict it.**
  Checked: `grep` for ask-first / session-policy / "cannot spawn" prose across
  the build, test, plan and security skills returns **nothing**. Only the iterate
  ever carried that language (#482/#489 put it there). `/shipwright-build`
  Step 6 describes the cascade without gating it, so the grant makes it
  consistent rather than conflicting. No change needed — recorded rather than
  acted on, so the next reader does not re-derive it.
- **gemini #2 (low) — phrasing must read as a request, not a preference.** The
  section says "this file is that request, and it stands for every session", and
  the probe above confirms it is read that way.

## 3. Alternative considered — and why not

**Leave it in the iterate skill only** (what #489 did). Rejected on the
operator's instruction and on the evidence: the cascade is not an iterate-only
concern — `/shipwright-build` Step 6 runs the same three reviewers — so a rule
living in one phase skill leaves every other phase asking. `CLAUDE.md` is
project-wide and is the instrument the harness designates for user instructions.

## 3c. Measured against the wording that actually ships

Stage 3's first high finding was that §2a cited a probe of the pre-Stage-2 text
and was never updated. Re-run 2026-07-28 against the **verbatim shipped section**
(922 bytes, extracted from `CLAUDE.md`), with the negative control the reviewer
asked for:

| fixture | `condition_satisfied` | `would_spawn_without_asking` | `workflows_granted` | `section_builder_fanout_granted` |
|---|---|---|---|---|
| shipped section, verbatim | **true** | **true** | false | false |
| no section (control) | **false** | **false** | false | false |

The control is what gives it discriminating power: absent the section the model
declines, so the `true` is caused by the section rather than by the question.
Both carve-outs hold in the positive case, including the `section-builder`
exclusion Stage 2 added.

Honest limits, stated rather than papered over: this is a self-report of policy
state, not an observed `Agent` call; n=1 per fixture; and the section sits alone
in the fixture whereas it ships as one of 199 lines. A behavioural probe — run a
real medium-complexity path and assert an `Agent` invocation appears — is the
stronger test and is not built here.

## 3d. What Stage 3 changed

11 doubts, 3 high. Two were hard disproofs of shipped claims.

- **The brownfield leg did not deliver (high).** `write_claude_md` refuses to
  overwrite an existing CLAUDE.md over ~1 KB and writes its render to a side-file
  the harness never loads — so every repo mature enough to be worth adopting
  received nothing, while the mirror test stayed green because it calls the
  renderer directly rather than the writer. **Fixed:** the section is now a single
  constant (`STANDING_REQUEST_SECTION`) that the renderer interpolates and
  `write_claude_md` **appends** to a preserved CLAUDE.md — additive, idempotent by
  heading, original bytes untouched, backup still taken. Pinned by two tests that
  go through the *writer*, and the two pre-existing preservation tests were
  updated to the new contract (they still assert the original survives
  byte-for-byte at the head; only "byte-identical" relaxed).
- **The framework authors the consent it cites (high).** For a generated or
  adopted project, *"this file is that request"* is written by the tool, not by
  that project's maintainer. **Operator decision, taken explicitly:** install it
  everywhere anyway, and leave the grant unbounded. Recorded here so it is not
  re-litigated — the alternatives offered were asking during onboarding, or
  suggesting rather than installing on a load-bearing file, and both were
  declined in favour of every project getting the full review quality by default.
  The opt-out remains one deleted section.
- **No cost bound (medium).** The worst case the reviewer constructed is real: a
  25-section autonomous build can spawn ~75 reviewers, order 7–14M tokens, with
  no question asked. Left unbounded by the same decision. `/usage` attribution
  stays the only feedback channel.
- Applied: F11's grant branch is now conditioned like Step 8's (the four blockers
  are explicitly unaffected by any grant — a runner with no `Agent` tool still
  cannot spawn); a **negative** assertion was added because equality plus
  substring markers cannot catch a regression applied identically to all three
  carriers; and the generated file no longer tells its reader both to keep
  sections lean and to leave this one alone without saying why.
- Not applied, recorded: the "reviewers vs fan-out" discriminator is a judgement
  call rather than a closed allowlist, and `section-builder` is serial in
  `autonomous-loop.md` while `migration-safety.md` calls it parallel. The wording
  ships as-is; tightening it to a named allowlist is a follow-up.

## 3e. One change made after the review cascade

Disclosed rather than folded in silently. At F6 the bloat anti-ratchet blocked
the commit: `artifact_writer.py` had gone 590 → 629, and it is already
*grandfathered* at roughly twice the 300-line limit. Writing a bloat-exception
ADR to bless a further 39 lines on that file is the rationalization the gate
exists to refuse, so the preferred remediation was taken instead — **shrink**.

`write_claude_md` and `_append_standing_request` moved verbatim into
`claude_md_renderer.py`, the module that already owns the section constant they
append; `artifact_writer` re-exports `write_claude_md`, exactly as it already
re-exports `write_spec` / `_render_spec_md` from `spec_document`. The function
bodies are unchanged. `artifact_writer.py` 629 → 548 (under its 590 baseline),
`claude_md_renderer.py` 146 → 238 (under the 300 limit), and the cohesion
improves: rendering and writing the same file now live together.

Re-verified after the move, not assumed: adopt 591 passed, `shared/tests` 6285
passed / 16 skipped — both identical to the pre-move counts — plus ruff clean
and F0.5 re-run against the final tree (34 tests, exit 0). The re-export is
pinned by row #21 below.

## 4. Out of scope

The three residual gaps observed in session `7c6c7b07` — the agent asked without
waiting, closed `code`/`doubt` before the answer arrived, and labelled an
unanswered question `Operator-declined`. With the standing grant those paths are
no longer the normal case; they remain reachable only in a project without the
grant. Tracked separately rather than folded in here.

## 5. Affected Boundaries

None. No serialized format, producer or consumer changes.

## 6. Confidence Calibration

- **Boundaries touched:** none (§5). No serialized format, producer or consumer
  changed shape. The one file *written* differently — an adopted project's
  preserved `CLAUDE.md` — is appended to, not reformatted, and the append is
  keyed on a heading rather than on any parsed structure.
- **Empirical probes run:**
  - *Does the section change the model's stated policy?* — §3c, against the
    verbatim shipped 922-byte section, with a no-section negative control. The
    control declines and the section grants, so the `true` is caused by the
    section. Both carve-outs (workflows, `section-builder`) hold in the positive
    case. Limits stated in §3c and not papered over.
  - *Does the brownfield leg actually deliver?* — ran `write_claude_md` against a
    >1 KB load-bearing fixture through the real writer. Before the fix: the grant
    reached the side-file only, and the project's own `CLAUDE.md` was untouched.
    After: appended, original bytes intact at the head. This is the Stage-3
    disproof that turned a green mirror test into a shipped delivery leg.
  - *Is the F11 guard scoped to the paragraph it claims?* — extracted paragraph
    measures 1 636 chars of a 12 070-char file and contains neither
    `watch_pr_delivery` nor `check_iterate_no_direct_decision_log`; stripping the
    two grant sentences fails the assertions. So the guard reads
    `check_review_record`, not the file at large.
  - *Do the carriers stay equal under a same-direction regression?* — appending
    "and dynamic workflows are covered too" to all three keeps equality and every
    marker green, which is why `_FORBIDDEN_GRANTS` exists as the negative half.
- **Test Completeness Ledger:** §7 — 20 behaviors, 18 `tested`, 2 `untestable`
  with closed-vocabulary reason codes, 0 untested-testable.
- **Confidence-pattern check:**
  - *Asymptote (depth).* The claim chain is: text exists → all three carriers
    carry the *same* text → the text does not grant fan-out → a preserved
    `CLAUDE.md` receives it → the model reads it as a request. The first four are
    pinned by tests through the real code path (the writer, not the renderer).
    The fifth is a self-report, n=1 per fixture, and is the honest ceiling here:
    a behavioural probe asserting a real `Agent` invocation is the stronger test
    and is not built. Stated in §3c, and recorded in §7 as `untestable` rather
    than quietly claimed.
  - *Coverage (breadth).* Three carriers × {grant present, carve-out present,
    mirror equal, fan-out not granted} plus the writer path × {first run, re-run,
    original preserved, log discloses it} plus three prose artifacts × {grant
    outranks ask, ask survives ungranted, blockers immune}. The breadth gap the
    Stage-3 pass found — a regression applied *identically* to all carriers —
    is closed by the negative assertion, which no equality or substring check
    can see.
  - *Integration composition.* Not applicable: `cross_component` does not fire —
    no merge/churn resolver, hook, phase validator or campaign-drain file is in
    the diff.

## 7. Test Completeness Ledger

**Principle: testable ⇒ tested.** 21 behaviors · 19 tested · 2 untestable · **0
untested-testable**. Enumeration basis: 4 ACs, all 4 covered.

| # | Behavior | Disposition | Evidence / reason |
|---|---|---|---|
| 1 | Greenfield template carries the grant | tested | `test_claude_md_template.py::test_template_carries_the_subagent_standing_request` PASSED |
| 2 | Greenfield template withholds workflows + fan-out | tested | `::test_template_does_not_grant_workflows` PASSED |
| 3 | This repo's own `CLAUDE.md` carries grant + carve-out | tested | `::test_own_claude_md_carries_the_same_grant_and_carveout` PASSED |
| 4 | Brownfield renderer emits the grant | tested | `::test_adopt_rendered_claude_md_mirrors_template_iterate_bullets` PASSED |
| 5 | All three carriers hold the *same* section, not just the markers | tested | `::test_the_three_carriers_hold_the_same_section_not_just_the_markers` PASSED |
| 6 | The section never affirmatively grants fan-out (negative half) | tested | `::test_the_section_never_affirmatively_grants_fan_out` PASSED |
| 7 | `STANDING_REQUEST_SECTION` is one constant, not three copies | tested | implied and enforced by #5 — equality across carriers is red if the constant is bypassed |
| 8 | A preserved load-bearing `CLAUDE.md` receives the grant | tested | `::test_a_preserved_loadbearing_claude_md_still_receives_the_grant` PASSED (goes through the writer) |
| 9 | The append is idempotent by heading | tested | `::test_appending_the_grant_is_idempotent` PASSED |
| 10 | Preserved original survives byte-for-byte at the head | tested | `test_artifact_writer_data_preservation.py` + `test_data_preservation_realistic.py` PASSED (both updated to the append contract) |
| 11 | The preservation log discloses the append as additive | tested | `::test_the_preservation_log_records_that_the_file_was_appended_to` PASSED |
| 12 | A re-run records a no-op, distinguishable from an append | tested | `::test_a_second_run_records_that_the_grant_was_already_present` PASSED |
| 13 | `SKILL.md` Step 8: a standing grant outranks the ask | tested | `test_iterate_skill_prose.py::test_step_8_lets_a_standing_grant_outrank_the_ask` PASSED |
| 14 | Step 8's ask survives, scoped to the ungranted project | tested | same test — asserts `only when no such grant exists` |
| 15 | `iteration-reviews.md` step 0: a grant satisfies the policy outright | tested | `test_iteration_reviews_prose.py::test_a_project_grant_satisfies_the_policy_outright` PASSED |
| 16 | …and is scoped to reviewers, with "read the file — do not assume it" | tested | `::test_the_grant_is_scoped_to_subagents_not_workflows` PASSED |
| 17 | `F11.md` defers to the grant instead of sending the run back to ask | tested | `test_f11_review_record_grant.py::test_f11_defers_to_a_standing_grant_instead_of_asking` PASSED |
| 18 | `F11.md`: the four blockers are immune to any grant | tested | `::test_the_four_blockers_are_immune_to_the_grant` PASSED |
| 19 | The model actually spawns an `Agent` under the grant, observed rather than self-reported | untestable | `requires-external-nondeterministic-service` — needs a live model session driven end-to-end; §3c ships the self-report plus a negative control and states this ceiling explicitly |
| 20 | `docs/guide.md` describes the grant accurately for a human reader | untestable | `requires-manual-visual-judgment` — the assertable invariants are pinned by #1–#18; whether the narrative reads correctly is editorial |
| 21 | After the §3e move, every existing importer still gets `write_claude_md` from `artifact_writer` | tested | `plugins/shipwright-adopt/tests` 591 passed — `test_artifact_writer.py` and `test_artifact_writer_data_preservation.py` both import it from `lib.artifact_writer`, and `shared/tests/test_claude_md_template.py` drives that import path in a subprocess |

Also re-verified, not new behavior: `CLAUDE.md` stays under the 200-line
hygiene cap (`group_f._CLAUDE_MD_LINE_CAP`, file at 199) and `SKILL.md` under
300 LOC (`test_kern_skill_md_under_300_loc`) — both `covered-by-existing-test`.

Rows #11, #12, #17 and #18 were written **at Step 7.5**, not before it:
the ledger is what surfaced that `F11.md`'s grant branch and the preservation
note had shipped unguarded while their two sibling prose files did not.
