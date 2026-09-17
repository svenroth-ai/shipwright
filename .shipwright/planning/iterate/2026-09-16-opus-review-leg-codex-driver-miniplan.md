# Mini-Plan: opus-review-leg-codex-driver

- **Run ID:** iterate-2026-09-16-opus-review-leg-codex-driver

Revised after Internal Plan Review (opus-plan-reviewer, severity: high) — see
the iterate spec's `## Internal Plan Review` section for full findings. This
version incorporates all 15 fixed + 1 disclosed findings; 2 are escalated to
Sven and pending his answer before build starts.

## Files to create/modify
- `shared/config/external_review.json` (edit) — new `opus_leg` block (mirrors
  `gpt_leg`), new `models.claude_cli`/`models.openrouter_opus` keys (pinned to
  the full model id `claude-opus-5`, not the floating `opus` alias — symmetric
  identity-lock with the OpenRouter leg's exact-slug pin), new `claude_cli`
  timeout/retry section (mirrors `codex`).
- `shared/scripts/lib/external_review_routing.py` (edit) — two new
  `_REVIEW_MODEL_BINDINGS` entries: `("opus","claude_cli") -> ("claude_cli",
  "claude-opus-5")` and `("opus","openrouter") -> ("openrouter_opus",
  "anthropic/claude-opus-5")`. No new ZDR allowlist function (Sven: not
  needed for this leg). `openrouter_extra_body`: add `if model_key ==
  "opus": return {}` branch. **Plus**: `DRIVER_CHOICES = ("claude", "codex")`
  and the driver→roster mapping (`{"claude": ("glm","openai"), "codex":
  ("glm","opus")}`) — the "middle path" from the driver-abstraction
  discussion: no new module, this file already owns "which identity answers
  which leg" policy.
- `shared/scripts/lib/external_review_opus_leg.py` (**new file**, not an edit
  to `external_review_default_legs.py` — that module is already near the
  300-line guideline; a sibling module avoids crossing it). Contains:
  `_resolve_claude_binary()` (BatBadBut cwd-guard, mirrors
  `_resolve_codex_binary()`, **plus**: refuse a resolved `.cmd`/`.bat` target
  outright — return `None` — since `subprocess`'s list-form argv quoting
  (`list2cmdline`) is not `cmd.exe`-batch-safe and a diff/spec containing
  `&`/`|`/`^`/`"` could break out of the argument on Windows; `review_codex()`
  is immune only because it pipes the prompt via stdin, which this leg's
  settled `-p` invocation shape cannot do), `is_claude_cli_available()`
  (`claude --version` liveness probe — installation only, not auth; documented
  limitation, not blocking), `claude_cli_settings()` (config timeout/retry,
  mirrors `codex_settings()`), `review_claude_cli()` (subprocess wrapper:
  pipes the diff/spec content via stdin as context data, passes the
  system+review-instructions as the `-p` argument per the confirmed
  stdin-is-data-only CLI contract; invokes `claude --bare -p "<instructions>"
  --model claude-opus-5 --output-format json --permission-mode dontAsk
  --max-turns 1 --strict-mcp-config <empty-config-path>` — the last flag plus
  an empty allowed-tools set close the sandbox-parity gap the review flagged;
  parses the `result` field per the confirmed JSON schema; applies
  `classify_reply`), `resolve_opus_route()` (mirrors `resolve_openai_route()`:
  prefer `claude_cli` when available, else OpenRouter — one link shorter than
  GPT's chain since there's no "direct Anthropic API" leg). **No
  `review_opus_openrouter()` wrapper** — the review correctly flagged step 5
  as self-cancelling; call `review_openrouter(..., model_key="opus")`
  directly, same as `"glm"`/`"openai"` already do.
- `shared/scripts/lib/external_review_config.py` (edit) — add `claude_cli` and
  `openrouter_opus` to `_VALID_MODEL_KEYS` unconditionally (not "if it holds
  accessors" — the review found `resolve_model()`'s bare `ValueError` isn't
  caught by callers expecting `ReviewModelPolicyError`, so an unlisted key
  would crash instead of degrading).
- `shared/scripts/tools/external_review.py` (edit) — new `--driver`
  arg, `choices=DRIVER_CHOICES`, `required=True` (no default — see Decisions);
  roster-selection block picks `{glm, opus}` via `resolve_opus_route` vs
  `{glm, openai}` via `resolve_openai_route`, branching entirely on `driver`
  with no fallthrough (closes the `gpt_leg.provider` leak risk structurally);
  **fix the empty-diff short-circuit** (currently hardcodes `{"glm": ...,
  "openai": ...}` before route resolution — must build from the selected
  roster instead); record `driver` in the output envelope for audit
  visibility.
- 8 plugin prose files (edit) — add `--driver claude` or `--driver codex` (per
  Decision #2's list) to every literal `external_review.py` invocation
  example. Exact files: `plugins/shipwright-iterate/skills/iterate/
  references/iteration-planning.md`, `.../references/iteration-reviews.md`,
  `.../SKILL.md`, `plugins/shipwright-iterate/agents/sub-iterate-runner.md`,
  `plugins/shipwright-plan/skills/plan/references/step-5-external-review.md`,
  `.../references/external-review.md`, `.../SKILL.md`,
  `plugins/shipwright-build/skills/build/references/code-review.md`.
- `shared/scripts/lib/review_verdict.py` (edit) — add
  `CURRENT_REVIEWER_ROSTERS = (frozenset(REVIEWERS), frozenset({"glm",
  "opus"}))`; update `_SUPPORTED_REVIEWER_SETS` (or wherever
  `contradiction_block()` validates) to derive from it instead of the bare
  `REVIEWERS` tuple — the review found this exact gate blocks every
  `{glm,opus}` run today; update its hard-coded "expected glm/openai" message
  string in the same edit. Keep `REVIEWERS` itself unchanged (still means
  "the Claude-driven roster").
- `shared/scripts/lib/review_companion.py` (edit) — classify current via
  `frozenset(verdicts) in CURRENT_REVIEWER_ROSTERS`, not `== frozenset(REVIEWERS)`.
- `shared/scripts/lib/review_payloads.py` (edit) — **corrected design**:
  `_verdicts_from_text` keys off `REVIEW_ENVELOPE_SCHEMA` (the payload
  envelope, always 2 — `external_review.py` emits it unconditionally), NOT
  marker schema. Widen schema-2's `expected_candidates` to include
  `{glm,opus}` directly — same precedent as the DeepSeek→GLM swap, whose
  envelope shape never bumped either. (The original plan conflated payload
  schema with marker schema; do not gate this on a marker-schema bump.)
- `shared/scripts/lib/review_record_schema.py` (edit) — `supported =
  {*CURRENT_REVIEWER_ROSTERS, *map(frozenset, HISTORICAL_REVIEWER_PAIRS)}`.
- `shared/scripts/lib/review_marker.py` (edit) — **corrected design, per the
  review's MEDIUM/architecture finding**: do NOT bump `MARKER_SCHEMA` (stays
  4, meaning exactly `{glm,openai}` — preserves the module's documented 1:1
  schema↔roster invariant, and avoids redding ~5 existing test files that
  assert `marker_schema == 4` on a fresh write). Instead add
  `OPUS_MARKER_SCHEMA = 5` meaning exactly `{glm,opus}`, and one
  `schema_for_roster(verdicts) -> int` helper (raises for an unrecognized
  roster) called from **both** `review_companion.write_markers` (which
  already derives schema from roster — extend its existing elif chain) and
  `shared/scripts/checks/mark-review-state.py` (which the review found
  **never passes `marker_schema` at all today** — a second, independent bug
  this surfaced; it would silently write schema 4 for an opus roster and then
  be rejected by its own reader). Allowed-schema set becomes `{2,3,4,5}`.
- `shared/scripts/checks/mark-review-state.py` (edit) — `parse_verdict_args`
  currently validates `name not in REVIEWERS` against the bare 2-tuple,
  rejecting `--verdict opus=…` outright. Validate against
  `CURRENT_REVIEWER_ROSTERS`'s union instead; wire in the `schema_for_roster`
  call above so this CLI's own marker writes get the right schema.
- Tests: `shared/scripts/tests/test_external_review_routing.py` (or wherever
  existing GPT/GLM binding tests live — grep first, don't duplicate), new
  `shared/scripts/tests/test_external_review_opus_leg.py` for
  `review_claude_cli`/`resolve_opus_route`/the `.cmd`-shim-refusal regression
  test, `shared/scripts/tools/tests/test_external_review.py` for `--driver`
  CLI wiring + the empty-diff-roster fix, plus one round-trip test per
  roster-identity module (`review_verdict`, `review_companion`,
  `review_payloads`, `review_record_schema`, `review_marker`,
  `mark-review-state`) proving `{glm,opus}` is now accepted as current
  without disturbing any existing `{glm,openai}` fixture/assertion.
- Docs/changelog (new step, was missing): `docs/guide.md` Appendix B (new CLI
  flag), `docs/hooks-and-pipeline.md` (already documents `marker_schema`
  around its existing entry — add the schema-5/opus-roster case),
  `CHANGELOG-unreleased.d/` drop.
- **Explicitly NOT touched** (disclosed known limitation, triage card filed
  at F12): `shared/scripts/lib/llm_review.py::run_review()` (lines ~183-223)
  — a second, parallel `{glm,openai}` + `resolve_openai_route` roster loop
  serving Adopt's Layer-3 review and `review_assistant_ui_plan.py`. Different
  consumer/feature surface; this iterate's spec never claimed it
  (scope-ratchet guard). Keeps today's self-review exposure for that surface
  until a follow-up iterate.

## Decisions (resolved — Sven + two Opus verification passes)
1. **Scope: wiring is IN this iterate.** Sven clarified the "Durchlauf-Prompt"
   memory reference was a pre-Codex-Light workaround, now obsolete — Codex
   Light's actual invocation surface is `AGENTS.md` + the shared iterate skill
   both drivers already follow. "Wiring" means: every place the iterate skill
   (and its siblings) tells an agent to run `external_review.py` must pass the
   right `--driver` value.
2. **`--driver` is `required=True`, no default.** Grep found `external_review.py`
   is invoked (as literal example commands) from 8 places across 3 plugins —
   not just `shipwright-iterate`'s own Step 4:
   - `plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md`
     (2 call sites: `--mode iterate`, `--mode architecture`)
   - `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md`
     (code-mode cascade reference)
   - `plugins/shipwright-iterate/skills/iterate/SKILL.md`
   - `plugins/shipwright-iterate/agents/sub-iterate-runner.md` (campaign mode)
   - `plugins/shipwright-plan/skills/plan/references/step-5-external-review.md`
   - `plugins/shipwright-plan/skills/plan/references/external-review.md`
   - `plugins/shipwright-plan/skills/plan/SKILL.md`
   - `plugins/shipwright-build/skills/build/references/code-review.md`
   Considered defaulting the structurally-Claude-only ones (plan/build/campaign)
   to `claude` and requiring it only where it can vary (iterate's own Step 4) —
   **rejected**: `sub-iterate-runner.md` IS an iterate; a Codex-driven campaign
   would silently self-review through a default there. Cheapest fail-closed
   price is 8 one-line prose edits (`--driver claude` on 7 of them,
   `--driver claude|codex` — resolved per the actual driver — on
   `iteration-planning.md`'s two iterate-mode calls and
   `sub-iterate-runner.md`). Enforced by a new grep-based contract test (see
   step 8b) rather than trusted to prose alone — mirrors this repo's existing
   `test_review_routing_contract.py`/`test_sub_iterate_runner_contract.py`
   shape.
3. **No new shared "driver" module.** All 8 call sites are Markdown prose, not
   Python — a shared Python resolver would have exactly one real importer
   (`external_review.py`'s own argparse). `DRIVER_CHOICES = ("claude",
   "codex")` + the driver→leg-set mapping goes directly into
   `external_review_routing.py`, which already owns this exact policy class
   (`resolve_reviewer_model`, `openrouter_extra_body`,
   `ReviewModelPolicyError`). Not co-located with `model_tier_config.py` —
   ADR-127 is scoped to "which Claude model tier a subagent gets"; "driver" is
   "which harness authored the diff" — a different axis, and co-locating would
   smear that boundary.
4. **New guard, caught by the second Opus pass**: `external_review.gpt_leg.provider
   == "codex"` (an existing, unrelated config knob routing the "openai" leg
   through the local Codex CLI transport for cost reasons) must never leak an
   "openai"-identity leg into a `driver=codex` roster. With the roster-selection
   design below (branch entirely on `driver`, never fall through to
   `resolve_openai_route()` when `driver == "codex"`), this can't structurally
   happen — but add an explicit regression test proving `gpt_leg.provider`'s
   value has zero effect on a `driver=codex` run's roster, since the review
   flagged it as a real, not hypothetical, risk.

## Work breakdown
1. **Config**: `external_review.json` — `opus_leg`, `models.claude_cli`
   (`"claude-opus-5"`)/`models.openrouter_opus`
   (`"anthropic/claude-opus-5"`), `claude_cli` timeout section, empty MCP
   config file this leg's `--strict-mcp-config` flag points at. Test: config
   loads, keys present, existing keys/tests unaffected.
2. **Routing bindings + extra_body**: the two new `_REVIEW_MODEL_BINDINGS`
   entries; `openrouter_extra_body`'s `"opus"` branch. Test: both bindings
   resolve correctly, mismatch raises `ReviewModelPolicyError`, extra_body
   returns `{}` for `"opus"`.
3. **`external_review_config.py`**: add both new keys to `_VALID_MODEL_KEYS`.
   Test: `resolve_model()` accepts them; a still-unlisted key still raises.
4. **`external_review_opus_leg.py`** (new module): `_resolve_claude_binary()`
   with `.cmd`/`.bat` refusal, `is_claude_cli_available()`,
   `claude_cli_settings()`, `review_claude_cli()`
   (stdin=content/context, `-p`=instructions, sandbox flags, JSON `result`
   parse, `classify_reply`), `resolve_opus_route()`. Test: mocked
   subprocess success/failure/timeout/`.cmd`-shim-refusal paths (mirror
   `test_review_codex`'s exact test shapes); `resolve_opus_route` mirrors
   `test_resolve_openai_route`'s cases.
5. **`external_review.py` wiring**: `--driver` arg (`required=True`,
   `choices=DRIVER_CHOICES`); roster-selection block branches entirely on
   `driver` (no fallthrough to `resolve_openai_route()` when
   `driver=="codex"` — closes the `gpt_leg.provider` leak); fix the
   empty-diff short-circuit to build from the selected roster; record
   `driver` in the output envelope. Test: `--driver codex` → `opus`+`glm`
   keys, no `openai`, regardless of `gpt_leg.provider`'s config value;
   `--driver claude` → unchanged `openai`+`glm`; omitted `--driver` → argparse
   error (regression test proving the required-flag contract); empty-diff
   under both drivers produces the matching roster's skip-shape.
5b. **8 prose call sites**: add the resolved `--driver` value to every
    literal invocation example (list in Decision #2). New contract test
    (mirroring `test_review_routing_contract.py`) grep-asserting every
    `external_review.py` invocation block under `plugins/**/*.md` includes
    `--driver` — the real anti-drift mechanism, not trust-the-prose.
6. **Roster-identity generalization**: `review_verdict.py`
   (`CURRENT_REVIEWER_ROSTERS` + the `contradiction_block()` gate + message
   string), `review_companion.py`, `review_payloads.py` (schema-2 widen, NOT
   marker-schema-gated), `review_record_schema.py`. Test: one round-trip per
   module, `{glm,opus}` accepted as current, all existing `{glm,openai}`
   tests still pass unmodified.
7. **Marker schema**: `review_marker.py`'s `OPUS_MARKER_SCHEMA = 5` +
   `schema_for_roster()` helper wired into both `review_companion.write_markers`
   and `mark-review-state.py` (including that CLI's `parse_verdict_args` fix).
   Test: a `{glm,openai}` write still produces schema 4 (regression floor,
   all ~5 existing schema-4-asserting tests pass unmodified); a `{glm,opus}`
   write produces schema 5 and round-trips through the reader.
8. Docs (`guide.md` Appendix B, `hooks-and-pipeline.md`) + changelog drop.
9. Full test suite run for the touched roots (`shared/scripts/tests`,
   `shared/scripts/tools/tests`) + `verify_local.py`.

## Test strategy
Unit tests only — no live network/subprocess calls in the suite (mock
`subprocess.run`, mock the OpenAI client the same way existing GPT/GLM tests
do; mock `_resolve_claude_binary()` to return both a `.exe`-shaped and a
`.cmd`-shaped path to exercise the new refusal branch). Confidence
Calibration empirical probes (informally already run this session, to be
formalized): a real `claude --bare -p ... --model claude-opus-5
--output-format json --strict-mcp-config <empty>` subprocess call in a
throwaway scratch dir, confirming (a) the pinned full model id works
identically to the `opus` alias, (b) the sandbox flags actually suppress
tool access against a prompt asking the model to use one; and, if
`OPENROUTER_API_KEY` is set, one real `anthropic/claude-opus-5` OpenRouter
completion.

## Alternative approach (rejected)
**Reuse `review_codex()`'s exact structure for Opus by making it generic
over "CLI binary + flags", parameterized per reviewer identity**, instead of
a second module. Rejected: the two CLIs' invocation shapes differ enough
(Codex reads its whole rendered prompt via stdin with `-o <file>` capture;
Claude CLI's headless contract takes its instructions only via `-p`, with
content/context piped over stdin as data rather than substituted into it —
not a stdin/no-stdin split, but a different split of what rides on stdin
versus argv; auth-check mechanics also differ — Codex has `login status`,
Claude CLI only a version probe) that a shared parameterized function would
need enough per-CLI branching to lose the clarity it was meant to buy —
echoing why `review_openai`/`review_openrouter` already stay separate rather
than one parameterized function. Per this project's own Quality Calibration
guidance ("three similar lines is better than a premature abstraction"), two
similar-but-not-identical functions stay clearer.
