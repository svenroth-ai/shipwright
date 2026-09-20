# Iterate Spec: m4-codex-subagent-dispatch

- **Run ID:** iterate-2026-09-20-m4-codex-subagent-dispatch
- **Type:** feature
- **Complexity:** medium (overridden from classifier's Stage-1 `small` —
  message-only signal; real scope is a cross-cutting change to the Codex
  review-dispatch contract, which warrants the mini-plan + external review
  medium buys)
- **Status:** draft
- **Campaign:** codex-plugin-execution-reliability, sub-iterate R3 (M4)

## Goal

Close the gap where AGENTS.md's stated Codex reasoning-effort policy ("high
reasoning for required review subagents") never actually reached the
`codex exec` dispatch call, and prove with a fixture that three sequential
Codex-driven review passes (`spec-reviewer` → `code-reviewer` →
`doubt-reviewer`) land in `reviews.json` as genuinely distinct passes, not
one session's self-report reformatted three times
(`Spec/codex-plugin-execution-reliability.md` §4 AC2).

**Scope note (see External Review below):** this iterate originally also
built a `.codex/agents/shipwright-*.toml` generator per M4's literal "map
review roles to approved Codex subagent profiles" bullet. It was fully
built, internally reviewed, and fixed to a high standard — then cut after
the dedicated architecture review (both legs, unanimous) found it added a
permanent maintenance surface for files nothing automated actually
consumes, and the user confirmed the cut. The model/effort/sandbox contract
those files would have rendered already lives, and stays, in
`codex_review_roles.py` — a single canonical Python source, not duplicated
into a second, unused artifact.

## Acceptance Criteria

- [ ] `run_codex_review` (`codex_review_transport.py`) passes
  `model_reasoning_effort` to `codex exec` via `-c
  model_reasoning_effort=<value>`, sourced from
  `codex_review_roles.CODEX_REVIEW_REASONING_EFFORT`, for every role in
  `codex_review_roles.REASONING_EFFORT_ROLES` (`spec`/`code`/`doubt`) —
  closing the gap where AGENTS.md's stated policy was never actually
  reaching the dispatch call. `plan_review`'s argv stays byte-identical
  (out of scope, see below).
- [ ] A fixture drives `run_codex_review` for all three review roles with
  three distinct mocked `codex exec` outputs, records each through
  `record_review_pass.py record --transport codex`, and asserts the
  resulting `reviews.json` carries three distinct rows — each correctly
  keyed by `review_type`, each carrying its own distinct payload content
  (never one row's content reformatted into the other two), not one row
  duplicated three ways. This is the AC2 fixture the parent spec names.
- [ ] `run_codex_review`'s returned `transport_note` (and the `reviews.json`
  row it is recorded into) names the effective model plus reasoning effort
  and sandbox for a `REASONING_EFFORT_ROLES` role — the parent spec's
  "evidence records the actual role, model, effort, sandbox" bar — and
  reflects a `model=` override when one is given, not just the hardcoded
  default.
- [ ] Claude-driven Agent-tool dispatch (iterate Step 8 / build Step 6's
  three `Task(...)` spawns) is untouched — no SKILL.md prose changes, no
  changes to the Claude spawn path.

## Spec Impact

- **Classification:** modify
- **MODIFY** (existing FR changed): FR-01.11 — add AC37 (three distinct
  recorded passes, not one reformatted three ways), alongside AC31
  (iterate-2026-09-13-codex-internal-review-transport, which this iterate
  builds directly on top of). AC36 (a canonical, synced `.codex/agents/`
  role manifest) is **not** added — that was the TOML-generator AC the
  Architecture Review found disproportionate; see below.
- **ADD:** none
- **REMOVE:** none

## Out of Scope

- **`sub-iterate-runner` and `section-builder`** (execution-worker roles,
  not review roles). M4's own bullet list scopes the Codex subagent-profile
  mapping to review roles only ("Map review roles in Codex to approved
  Codex subagent profiles/models; keep Claude role/model behavior
  unchanged"). Those two are Agent-tool-less execution workers with no
  Codex dispatch equivalent today, and campaign orchestration (M8, which
  owns `sub-iterate-runner`'s one Task() call site) is explicitly excluded
  from the whole `codex-plugin-execution-reliability` campaign
  (`campaign.md`: "Explicitly excludes W1-W7/M6/M8/M9/M10/M11/W4").
- **`opus-plan-reviewer`** (shipwright-plan plugin, not iterate/build — out
  of this sub-iterate's stated scope). Its own Codex dispatch already
  exists via the `plan_review` role in the same transport and is unaffected
  by this iterate — it also therefore keeps no reasoning-effort contract,
  the one remaining gap in AGENTS.md's "high reasoning for required review
  subagents" policy; tracked as a named follow-up rather than left silently
  implied (`trg-0a3c4edb`, Internal Plan Review, low, 2026-09-20).
- **The `.codex/agents/shipwright-*.toml` generator, the three committed
  profile files, and their drift test — built, then cut.** M4's literal
  text ("map review roles to approved Codex subagent profiles... rendered
  as Shipwright-managed project files under `.codex/agents/shipwright-
  *.toml`") was fully implemented: a generator, three committed TOML files,
  a `--check` drift gate, and 25+ regression tests, all reviewed to a high
  standard by an opus-tier Internal Plan Review (10 findings, all fixed).
  The dedicated Architecture Review (`external_review.py --mode
  architecture`, run specifically to ask "should this exist at all" — see
  below) then found, on both legs independently, that these files have no
  automated consumer: `codex exec` (Shipwright's only real dispatch path)
  cannot invoke a named custom agent from a non-interactive session (the
  same upstream gap the Design Notes below already document), so the
  generator's permanent maintenance cost (contributor workflow rule, drift
  gate, collision-state machine) bought only speculative value for a
  hypothetical future interactive-TUI user. The user confirmed cutting it
  and asked how the model is defined without it — answer: it already was,
  independently of the TOML files, in `codex_review_roles.py` (see Design
  Notes) — nothing about model/effort/sandbox definition was lost by the
  cut.
- **Native Codex named-agent invocation** (`spawn_agent` addressed by a
  named custom-agent profile) as an actual dispatch transport. **Empirically
  verified not to work from non-interactive / tool-backed Codex sessions**
  — see Design Notes. The already-shipped prompt-only `codex exec`
  transport (`review_via_codex.py`, iterate-2026-09-13-codex-internal-
  review-transport) remains, and stays, the real dispatch mechanism.

## Design Notes

**Load-bearing empirical finding — the primary M4 premise needed
verification before build, not after.** `codex-runtime-integration-spec.md`
§7 M4 frames `.codex/agents/shipwright-*.toml` as giving "Codex... a real
dispatch target instead of improvising a substitute when it hits skill
prose assuming Task(...)". Checked against OpenAI's own current docs
(`developers.openai.com/codex/subagents`, redirects to
`learn.chatgpt.com/docs/agent-configuration/subagents`) and a tracked
upstream gap (`github.com/openai/codex/issues/15250`,
"Custom subagents in .codex/agents are not accessible from tool-backed
Codex sessions as docs imply"): **project-scoped custom agents are real and
schema-documented, but non-interactive / tool-backed sessions — exactly
`codex exec`, which is how every Shipwright Codex dispatch call already
runs — cannot reference a named custom agent.** Only the interactive TUI's
agent picker and explicit in-prompt spawn requests can. This single finding
did double duty in this iterate: first as the reason the TOML files were
scoped as *documentation*, not the dispatch mechanism, when they were still
being built (the parent spec's own fallback clause already covers this:
"Prompt-only spawning is a documented fallback only when it can pass and
record the same explicit role/model/effort/sandbox contract"); then, when
the dedicated Architecture Review asked "should this exist at all" against
a brief built from this same finding, as the reason both external legs
recommended cutting the files entirely — documentation with no automated
reader and a real, permanent maintenance cost is not obviously worth
carrying, and the user agreed.

**The model/effort/sandbox contract is not — and never was — TOML-defined.**
`codex_review_roles.py` is the one canonical Python source:
`CODEX_REVIEW_MODEL` (in `codex_review_transport.py`), the shared
`REASONING_EFFORT_ROLES`/`CODEX_REVIEW_REASONING_EFFORT`, and
`CODEX_REVIEW_SANDBOX_MODE` all live there, and `run_codex_review` reads
them directly. The TOML generator, while it existed, only ever *rendered* a
duplicate of that same contract for Codex's interactive surface — it was
never the source of truth, so cutting it changes nothing about how the
model is defined or resolved.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `codex_review_roles.py` (canonical constants) | `codex_review_transport.run_codex_review` | Python (in-process, not a serialized boundary) |
| `run_codex_review`'s `-c model_reasoning_effort=` argv | `codex exec` subprocess | CLI argv |

No serialized producer/consumer pair crosses a process/file boundary in the
final shipped scope — the `.codex/agents/*.toml` row from the earlier,
larger scope was cut along with the generator (see Out of Scope); the
Boundary Probe sub-step in Build TDD does not fire.

## Internal Plan Review (opus-plan-reviewer)

**Two passes, both against the larger scope that included the TOML
generator.** The first ran under this session's own inherited Sonnet tier
by mistake (`shipwright_model_config.json` sets `plan_review: "opus"`, but
the `Agent(...)` call omitted `model="opus"`; self-caught post-hoc, a
process gap, not a finding on the plan itself). The second, correctly
opus-tiered, found 10 real issues (1 high, 4 medium, 5 low) in the
generator and dispatch code as it stood then — all fixed at the time.

**Disposition after the scope cut:** of the 10 fixed findings, those about
the generator's own correctness (AC4's drift test, `--check`-on-collision,
the injection-boundary/tools-allowlist gap, TOML self-validation, the two
uncaught-exception paths, the `CODEX_REVIEW_MODEL` module placement) are
now moot — that code no longer exists. Two findings remain load-bearing in
the shipped scope and are still reflected in the code and tests below:

- **architecture/medium** (reasoning-effort injection is keyed on role,
  independent of a model override, untested together) — still fixed:
  `test_reasoning_effort_flag_still_added_under_an_explicit_model_override`
  in `shared/tests/test_codex_review_transport_reasoning_effort.py`;
  constraint documented in `codex_review_model_resolution.py`'s docstring.
- **completeness/low** (`plan_review` keeps no reasoning-effort contract,
  no named follow-up) — still fixed: `trg-0a3c4edb` filed, noted above.

The `transport_note`-distinctness finding (AC3's wording vs. the shipped
fixture) is superseded by the External Review's own, later finding on the
same field (see below) — `transport_note` now correctly reflects a `model=`
override, tested directly.

## External Review

Two calls, per Step 3.5: an **iterate-mode** review (mini-plan vs. this
spec, `--driver claude`) and a dedicated **architecture-mode** review (a
brief, not the plan — see `shared/templates/architecture_brief.md`) asking
whether the TOML-generator subsystem should exist at all. Both ran against
the larger scope, before the cut.

**Iterate-mode (mini-plan vs. spec):** GLM `approve` (6 findings, mostly
about the generator's edge cases and a contributor-workflow note); OpenAI/
Codex leg `revise` (2 high, 2 medium, 2 low) — its two HIGH findings turned
out to describe code that was already different from what the plan implied
(`--sandbox` was already explicitly passed to `codex exec`, sourced from
the same constant the TOML would have rendered — this iterate-mode leg only
sees the plan/spec text, not the diff, so it could not know that). Of the
findings that identified real, still-relevant gaps: the `transport_note`-
under-a-model-override gap (GLM, low) is fixed and tested (see above); the
generator-specific findings are moot post-cut.

**Architecture-mode (brief vs. spec — "should this exist at all"):**
**Both legs independently rejected** the TOML-generator subsystem
(`SHIPWRIGHT_VERDICT: reject`, GLM severity high, OpenAI severity medium).
Core argument, made independently by both: the generated `.codex/agents/
*.toml` files have no automated consumer — `codex exec` cannot invoke a
named custom agent from a non-interactive session (the same upstream gap
this file's own Design Notes had already verified) — so their permanent
drift/collision-state maintenance surface bought documentation and
speculative future compatibility, not current execution reliability. Both
recommended the smallest thing that would do: the reasoning-effort flag,
the model/effort/sandbox evidence, and the distinctness fixture, without
the generator.

**Reconciliation:** the sub-iterate's own literal AC1 ("`.codex/agents/
shipwright-*.toml` profiles exist for every subagent role") and the user's
initial instruction both named the TOML-profile mapping explicitly, so this
was not a call to make unilaterally — the generator was fully built and
internally reviewed before this question was put to the user directly,
with both reviews' reasoning laid out plainly. **The user's decision:** cut
it. Asked how the model is then "cleanly defined" for the reviewer without
the generator, the answer is that it already was — `codex_review_roles.py`
was always the canonical source; the TOML files only ever rendered a copy
of it for a consumer that cannot read it today. Nothing about model
definition, override precedence, or evidence recording was lost by the cut;
what was cut was a redundant, unused rendering of the same already-single
source of truth.

**Iterate-mode re-run (mini-plan vs. spec, post-cut):** the first
iterate-mode call above ran against the pre-cut plan and its raw payload was
never persisted to `.shipwright/planning/iterate/{run_id}/` before the cut
landed, so the `plan` review row was still unrecorded once the mini-plan and
this spec were rewritten to the shipped scope. Re-ran `--mode iterate`
against the final mini-plan/spec (`external-plan-review-raw.json`, same
directory) to produce the payload the `plan` row is recorded from. GLM
`approve` (5 low findings); OpenAI/Codex leg `revise` (1 high, 2 medium, 1
low).

Disposition, finding by finding:
- GLM low, AC2 fixture "partially tautological" (proves the recording
  pipeline doesn't collapse rows, not that the upstream Codex session itself
  answered independently three times): accepted as an accurate limitation,
  noted here rather than reworked — the upstream-session half is outside
  what an offline fixture can prove at all.
- GLM low, `transport_note` format-stability: verified by grep — no
  consumer outside this iterate's own tests and docs/prompts parses or
  string-matches it; no fix needed.
- GLM low, encoding fix (`PYTHONIOENCODING=utf-8`) missing from the
  mini-plan's file list: fixed — added to the mini-plan's file-4 entry.
- GLM low, `REASONING_EFFORT_ROLES` only tested as a subset: fixed — added
  `test_reasoning_effort_roles_is_exactly_the_review_cascade`, asserting the
  exact set.
- GLM low, `plan_review` gap framing: no action; the follow-up
  (`trg-0a3c4edb`) already tracks it.
- OpenAI high, "production call site untested" (claims the fixture could
  pass even if the real Codex-dispatch path drops `transport_note`):
  **rejected, verified stale** — `--mode iterate` reviews plan/spec text
  only, not the diff, so it could not see that the fixture's own `record`
  call (`--from {role}-reviewer --payload-file {canonical_path} --transport
  codex --transport-note {transport_note}`) is byte-for-byte the same shape
  `codex_review_dispatch.md` instructs a production Codex-driven pass to
  run — confirmed by re-reading both files side by side.
- OpenAI medium, `subprocess.run` monkeypatch could intercept the harness's
  own recorder subprocess too: **rejected, verified stale** — the shipped
  fixture already scopes the monkeypatch per-role via `monkeypatch.context()`
  (see the fixture's own inline comment), a review-tool blind spot for the
  same reason as above.
- OpenAI medium, `plan_review` "byte-identical" claim under-tested (only an
  absence assertion): fixed — added
  `test_plan_review_role_full_argv_is_byte_identical_to_pre_iterate_shape`,
  a full-argv snapshot.
- OpenAI low, `CODEX_REVIEW_MODEL` living in `codex_review_transport.py`
  while `codex_review_roles.py` is called "the" canonical contract source:
  accepted as a real, previously-undocumented nuance — `CODEX_REVIEW_MODEL`
  moved there specifically to avoid a circular import
  (`codex_review_model_resolution.py` already imports from
  `codex_review_roles.py`); `codex_review_roles.py` owns role/effort/sandbox
  *policy*, not the literal model-slug default. Noted here rather than
  reworked — moving the constant back would reintroduce the cycle this
  session already resolved once.

## Doubt Review (Stage 3)

Fresh-context, disprove-biased pass over `codex_review_transport.py`/
`codex_review_roles.py`/`codex_review_dispatch.md` — triggered because the
diff touches `subprocess.run` dispatch to an external CLI on a file with a
documented history of prior doubt-reviewer HIGH findings. 7 doubts (2 high,
4 medium, 1 low). Advisory-must-address; every doubt answered below, in
writing, before commit.

- **HIGH, no capability guard on the new `-c` flag — an override to a model
  that rejects `model_reasoning_effort` turns all three required reviews
  `not_run`:** **rebutted by live experiment, not accepted as claimed.** Ran
  two `codex exec` probes with the exact shipped production argv (same
  order, same flags including `--ignore-user-config`): (1) `-c
  model_reasoning_effort=high` → banner prints `reasoning effort: high`,
  completes; (2) `-c totally_bogus_unrecognized_key=nonsense` → completes
  (`reasoning effort: none`, exit 0) rather than failing launch. Codex CLI
  silently ignores an unrecognized `-c` key; it does not fail closed. The
  catastrophic "all three reviews `not_run`" scenario the doubt describes
  is empirically not what happens. This does not make the flag risk-free —
  see the next doubt, which the same experiment makes MORE relevant, not
  less.
- **HIGH, `transport_note` records intent, never observation, and the argv
  decision + the evidence decision are two independent evaluations of the
  same `role in REASONING_EFFORT_ROLES` check that could silently drift
  apart:** accepted, fixed. Because an unrecognized `-c` key is silently
  ignored (previous doubt's finding) rather than erroring, `transport_note`
  claiming `effort=high` when the model actually ignored the flag is a real,
  undetectable-by-error failure mode. Added
  `test_argv_reasoning_effort_flag_and_transport_note_effort_agree_for_every_role`
  — asserts, for every role in `ROLE_SCHEMAS`, that the argv actually
  carries the flag iff the recorded note claims `effort=`, so deleting one
  side without the other now fails a test. A full fix (having
  `run_codex_review` read back Codex's own banner/log to confirm the effort
  was honored) was considered and rejected as disproportionate to this
  iterate's scope — no such read-back mechanism exists anywhere in this
  transport today for any of its other argv flags either.
- **MEDIUM, `transport_note_for`'s docstring states no precondition on
  `effective_model` despite formatting it into a shell-interpolated
  string:** fixed — added the precondition sentence to the docstring
  (`codex_review_roles.py`).
- **MEDIUM, `transport_note` is now a 3-word value interpolated via
  `--transport-note "{transport_note}"`; the AC2 fixture passes it as a
  Python list element and cannot exercise shell quoting:** fixed — added an
  explicit callout to `codex_review_dispatch.md` that the quotes are now
  load-bearing, not decorative (a real shell round-trip test was considered
  and rejected: the fixture's own convention, matching the rest of this
  test family, is to drive `record_review_pass.py` as a real subprocess via
  argv lists, never via a shell string — adding one `shell=True` path here
  would be a new, unmirrored pattern for a single doc-quoting concern).
- **MEDIUM, Test Completeness Ledger row 5 claimed `plan_review`'s
  `transport_note` is "covered by row 6's fixture", but that fixture's loop
  never includes `plan_review`:** fixed — added
  `test_plan_review_transport_note_is_the_bare_model`, and the ledger row
  below now cites it directly instead of the AC2 fixture.
- **MEDIUM, the live smoke probe's own comment claimed verification "in
  this exact argv position" without stating the probe's actual argv, and
  the first probe omitted `--ignore-user-config` (a config-file confound):**
  fixed — re-ran with the full shipped production argv (see the first doubt
  above); the comment in `codex_review_roles.py` now states both probes'
  argv shape and results directly instead of a bare claim.
- **LOW, the `REASONING_EFFORT_ROLES <= ROLE_SCHEMAS` guard used `assert`
  (stripped under `python -O`), which the sibling module
  `codex_review_model_resolution.py` already documents rejecting for this
  exact class of import-time table guard:** fixed — converted to `if ...:
  raise RuntimeError(...)`, matching the sibling module's own pattern. The
  second, tautological assert (`CODEX_REVIEW_REASONING_EFFORT == "high"`)
  is kept deliberately, per the doubt's own offered resolution — documented
  as a tripwire, not withdrawn as dead code.

## Cited Source Excerpts

`Spec/codex-plugin-execution-reliability.md`, `codex-runtime-integration-
spec.md`, and `campaign.md` are **not reachable from this worktree** —
`Spec/` is gitignored (local-only design reference per `.gitignore`) and
campaign planning docs (`campaign.md`/`status.json`) are deliberately
local-only too (`.gitignore`: "Campaign planning dirs... are local-only").
Quoted verbatim here so `code-reviewer`/`doubt-reviewer`/F11 can verify this
spec's scope claims without leaving the tree:

> **`Spec/codex-plugin-execution-reliability.md` §4, item 2 (the AC2 this
> iterate targets):** "The review cascade (spec-reviewer → code-reviewer →
> doubt-reviewer) runs as real, separate subagent invocations under Codex
> (via the M4 role mapping), not as the driving session silently answering
> for itself in place of a subagent it has no way to spawn. A fixture
> proves the cascade's evidence record (`reviews.json`) shows genuinely
> distinct review passes, not a single session's self-report reformatted
> three ways."

> **`codex-runtime-integration-spec.md` §7, M4 bullet list (the scope this
> iterate deliberately narrows to):** "Map review roles in Codex to
> approved Codex subagent profiles/models; keep Claude role/model behavior
> unchanged." ... "Codex roles are rendered as Shipwright-managed project
> files under `.codex/agents/shipwright-*.toml`, the documented
> project-scoped custom-agent surface." ... "Prompt-only spawning is a
> documented fallback only when it can pass and record the same explicit
> role/model/effort/sandbox contract." (The rendering half of this bullet
> was built, reviewed, then cut per the Architecture Review above; the
> fallback-as-load-bearing-path half is what this iterate ships.)

> **`.shipwright/planning/iterate/campaigns/codex-plugin-execution-
> reliability/campaign.md` (the exclusion list this iterate's Out-of-Scope
> section relies on):** "Close the Codex-execution-reliability gap per
> Spec/codex-plugin-execution-reliability.md: pull forward M1-M5 from
> codex-runtime-integration-spec.md so a Codex-driven iterate is enforced
> (hooks + activation protocol), not merely instructed via prose.
> Explicitly excludes W1-W7/M6/M8/M9/M10/M11/W4 (see spec Section 2)."

## Confidence Calibration

- **Boundaries touched:** `codex_review_roles.REASONING_EFFORT_ROLES` /
  `CODEX_REVIEW_REASONING_EFFORT` / `CODEX_REVIEW_SANDBOX_MODE` →
  `codex_review_transport.run_codex_review`'s argv and `transport_note`
  (in-process, not serialized — see Affected Boundaries).
- **Empirical probes run:**
  - Reproduced a real Windows-console encoding failure live in the AC2
    fixture test (`record_review_pass.py show` echoing an em-dash the
    `doubt-reviewer` adapter always inserts, decoded as UTF-8 against a
    cp1252-encoded child stdout) — root-caused to a specific byte offset
    before fixing it, not patched blind.
  - Ran both external review calls (`external_review.py --mode iterate`
    and `--mode architecture`) against the real diff/spec/brief, not
    simulated — the architecture-mode rejection is a real, independent
    two-model verdict, not an assumed outcome.
  - Verified directly (`grep`) that `--sandbox` was already explicitly
    passed to `codex exec`, sourced from the same `CODEX_REVIEW_SANDBOX_MODE`
    constant, before dismissing the External Review's HIGH finding #2 as
    reviewed-against-a-plan-only premise rather than a real code gap.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | a review-cascade role's argv carries `-c model_reasoning_effort=high` | tested | `test_review_cascade_role_gets_reasoning_effort_flag` PASSED |
  | 2 | `plan_review`'s argv is byte-identical to before (no flag added) | tested | `test_plan_review_role_has_no_reasoning_effort_flag` PASSED |
  | 3 | all three review-cascade roles (spec/code/doubt) carry the flag | tested | `test_all_three_review_cascade_roles_get_the_flag` PASSED |
  | 4 | `model_reasoning_effort` injection is still added under an explicit non-default `model=` override (the two axes are independent) | tested | `test_reasoning_effort_flag_still_added_under_an_explicit_model_override` PASSED |
  | 5 | `run_codex_review`'s returned `transport_note` names model+effort+sandbox for a `REASONING_EFFORT_ROLES` role, and is the bare model for `plan_review` | tested | row 6's fixture (`expected_note`, spec/code/doubt only) + `test_plan_review_transport_note_is_the_bare_model` PASSED for `plan_review` specifically (doubt-reviewer, medium, 2026-09-20: row previously cited only row 6, whose fixture never calls `plan_review`) |
  | 6 | three sequential Codex-dispatched review passes land in `reviews.json` as three genuinely distinct rows, keyed by `review_type`, each carrying its own distinct payload content (AC2) | tested | `test_three_codex_dispatched_passes_are_genuinely_distinct_in_reviews_json` PASSED |
  | 7 | `transport_note` names the RESOLVED (overridden) model, never the hardcoded default | tested | `test_reasoning_effort_flag_still_added_under_an_explicit_model_override`'s `transport_note` assertion PASSED (External Review, GLM leg, low, 2026-09-20) |
  | 8 | `REASONING_EFFORT_ROLES` stays a subset of `ROLE_SCHEMAS`; `CODEX_REVIEW_REASONING_EFFORT` stays a documented Codex value | tested | import-time `assert`/`raise` guards, exercised by every test above that imports `codex_review_roles` |
  | 9 | Claude-driven Agent-tool dispatch (iterate Step 8 / build Step 6) is unaffected | tested | no `SKILL.md`/agent-spawn code changed; the full pre-existing `codex_review_transport`/`record_review_pass` suites pass unchanged (11,182 passed, 0 failed, full `shared/tests` run) |
  | 10 | the argv reasoning-effort flag and the recorded `transport_note`'s `effort=` clause never disagree, for any role | tested | `test_argv_reasoning_effort_flag_and_transport_note_effort_agree_for_every_role` PASSED (doubt-reviewer, high, 2026-09-20) |

- **Confidence-pattern check:** Asymptote (depth) — yes: the TOML
  generator was treated as "should be fine" after its own internal review
  passed with all findings fixed, until the dedicated Architecture Review —
  run specifically to ask the question a correctness review does not ask —
  found the entire subsystem disproportionate. One more probe (asking
  "should this exist" as its own pass, not folded into "is this built
  correctly") was what caught it; a correctness-only review of the same
  code would have kept approving it indefinitely. Coverage (breadth) —
  every ledger row is `tested`; 0 untested-testable; no `cross_component`
  machinery is touched, so Integration Coverage does not fire.
