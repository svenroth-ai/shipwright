# Iterate Spec: opus-review-leg-codex-driver

- **Run ID:** iterate-2026-09-16-opus-review-leg-codex-driver
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented

## Goal
Today, `external_review.py`'s roster is hard-coded to `{glm, openai}` regardless of
which harness drove the diff. When a Codex-CLI-driven iterate runs external review,
the "openai" leg (`gpt-5.6-terra`, whether via OpenRouter, direct API, or the Codex
CLI transport) reviews code that Codex itself — the same vendor, frequently the same
model — just wrote. That is not independent review; it is a vendor-mode self-review
that happens to look identical to the genuinely independent case where Claude drives
and GPT reviews. Add a third, Anthropic-backed reviewer leg ("opus": local `claude`
CLI primary transport, OpenRouter `anthropic/claude-opus-5` fallback) and an explicit
`--driver {claude|codex}` flag so the caller can swap it in for the "openai" leg
specifically when Codex is the driver — keeping external review provider-independent
from whoever authored the diff, in both directions this framework now supports.

**Explicitly NOT a bug (ruled out during scoping, recorded so it doesn't resurface):**
`AGENTS.md`'s existing internal-cascade split — `gpt-5.6-terra` for
execution/finalization, `gpt-5.6-sol` for the internal `spec-reviewer`/
`code-reviewer`/`doubt-reviewer` cascade — is correct as-is and unrelated to the
self-review problem above. It mirrors Claude's own same-vendor internal tier split
(a stronger tier, `opus`, reviewing a cheaper one, `sonnet`) — same-vendor-by-design,
not a self-review bug. `shipwright_model_config.json`'s tier system
(`opus`/`sonnet`/`haiku`/`inherit`) is structurally Claude-Code-Agent-tool-only
(ADR-127; AGENTS.md's own line 54 already says not to reinterpret those values as
Codex model names) and stays untouched by this iterate. *External* review is the
one surface that is cross-provider **by design** — that is the surface this iterate
fixes.

## Acceptance Criteria
- [x] `external_review.py --driver codex` runs the roster `{glm, opus}` (not
      `{glm, openai}`) — the "openai" reviewer identity is replaced, not added to.
- [x] `external_review.py --driver claude` runs today's unchanged
      `{glm, openai}` roster, byte-identical to pre-existing behavior once the
      flag is supplied. `--driver` itself has no default — omitting it is an
      argparse usage error (exit 2), not a silent fallback to `claude`; every
      existing CLI-invocation call site and test gets a one-line `--driver`
      addition as part of this change (not a regression-floor violation —
      the regression floor is behavioral parity of the `{glm, openai}` roster
      itself, not the CLI's own argv shape). Superseded, corrected against
      External Plan Review finding #1 below (external plan review, 2026-09-17).
- [x] The "opus" leg resolves via a new `resolve_reviewer_model(config, "opus", route)`
      binding, identity-locked the same way `("openai", ...)` bindings are — a
      configured/env-overridden model that doesn't match the expected string raises
      `ReviewModelPolicyError` before any client/subprocess is constructed.
- [x] `review_claude_cli()` (local transport): spawns `claude --bare -p "<prompt>"
      --model {the identity-locked pinned model string resolved via
      `resolve_reviewer_model(config, "opus", "claude_cli")`, currently
      `claude-opus-5` — never a literal `opus` alias, for identity-lock
      symmetry with the OpenRouter leg's exact slug} --output-format json
      --permission-mode dontAsk --max-turns 1 --strict-mcp-config <empty mcp
      config> --allowedTools ""` as a subprocess, content/context piped over
      stdin (never argv — the untrusted diff/spec text never appears in argv,
      closing the BatBadBut risk even against a hostile shim), parses its
      JSON stdout for the final assistant text, and applies the same
      `classify_reply` empty/truncated check every other leg uses.
- [x] The OpenRouter fallback route calls the existing
      `review_openrouter(..., model_key="opus")` directly — no separate
      `review_opus_openrouter()` wrapper (dropped per opus-plan-reviewer LOW
      finding; wrapping a single parameterized call added no clarity). Model
      `anthropic/claude-opus-5`, **no ZDR provider-allowlist required** (Sven's
      explicit call — unlike `glm_routing`/`deepseek_routing`, this leg does not need
      a `provider_allowlist`/`zero_retention_verified` block).
- [x] A new `resolve_opus_route(config, has_openrouter_key)` mirrors
      `resolve_openai_route`'s shape: prefer local `claude` CLI when available
      (an `is_claude_cli_available()` check analogous to `is_codex_available()`),
      fall back to OpenRouter, `note` explaining any fallback the same way the
      existing GPT-leg fallback does.
- [x] `--driver` is `required=True` with `choices=("claude","codex")` — no
      default; omitting it is an argparse error, not a silent fallback.
- [x] All 8 plugin prose call sites (`shipwright-iterate`'s `SKILL.md` +
      `iteration-planning.md` + `iteration-reviews.md` + `sub-iterate-runner.md`,
      `shipwright-plan`'s `SKILL.md` + `external-review.md` +
      `step-5-external-review.md`, `shipwright-build`'s `code-review.md`) pass
      the correct `--driver` value; a grep-based contract test enforces this
      mechanically (not prose-trust alone).
- [x] `external_review.gpt_leg.provider == "codex"` has zero effect on a
      `driver=codex` run's roster (regression test) — the roster-selection
      branch never falls through to `resolve_openai_route()` when
      `driver=="codex"`.

## Spec Impact
- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.11 — append an AC line: the external-review roster stays
  provider-independent from whichever CLI drove the diff (Claude vs Codex), not
  fixed to a single hard-coded pair.
- **REMOVE:** none
- **NONE justification:** n/a

- The *internal* review cascade (`spec-reviewer`/`code-reviewer`/`doubt-reviewer`)
  and `AGENTS.md`'s existing `gpt-5.6-terra`/`gpt-5.6-sol` split — confirmed
  correct as-is during scoping (see Goal section), not touched here.
- The *separate* `iterate-2026-09-13-codex-internal-review-transport` plan —
  opposite direction (a Claude-Code-driven session redirected to GLM/Qwen
  calling OUT to Codex CLI for internal review). No overlap with this iterate.
- `shipwright_model_config.json` / the Claude-only agent-tier resolver
  (`model_tier_config.py`, ADR-127) — untouched; structurally Agent-tool-only.
- Auto-detecting the driver from the environment. Sven explicitly chose an
  explicit, required `--driver` CLI flag over env-var sniffing or per-project
  config or a default value. Wiring it into the 8 real call sites IS in this
  iterate's scope (revised — see Decisions in the mini-plan); the earlier
  "Durchlauf-Prompt" follow-up idea was based on a stale/obsolete memory
  reference Sven has since clarified doesn't apply to Codex Light's actual
  invocation surface (AGENTS.md + the shared iterate skill).
- A generic, pluggable multi-driver "agent system" architecture (config
  schema + resolver + framework-wide wiring, extensible to a hypothetical
  future third driver). Explicitly rejected as premature (this project's own
  "don't design for hypothetical future requirements" guidance) in favor of a
  plain closed `DRIVER_CHOICES = ("claude","codex")` enum inside
  `external_review_routing.py` — cheap to extend later if a real third driver
  ever appears, per the second Opus verification pass.
- Any webui-side change. This is monorepo-only (`shared/scripts/`,
  `shared/config/`).

## Design Notes
n/a — no UI surface; this is a CLI/config/library-only change.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/config/external_review.json` (new `opus_leg`/`models.opus`/`models.openrouter_opus` keys, project) | `shared/scripts/lib/external_review_routing.py::resolve_reviewer_model`, `shared/scripts/lib/external_review_default_legs.py::review_claude_cli`/`review_opus_openrouter` | JSON |
| `external_review.py`'s new `--driver` CLI argument (operator/caller) | `external_review.py::main`'s roster-selection block | CLI arg (str) |

## Confidence Calibration
{Populated before F0 — empirical probes (a real `claude --bare -p ... --model opus
--output-format json` subprocess call, a real OpenRouter completion against
`anthropic/claude-opus-5`) run during Build, table filled in at Step 7.5.}

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Direction correct; roster-identity scope confirmed real, but the
  build sequence as drafted has 7 hard breakers (argv injection on Windows via
  `claude.cmd`, missing sandbox hardening parity with `review_codex()`, 4
  additional call sites that block or corrupt a `{glm,opus}` run, and the fix
  not actually taking effect this iterate since `--driver` defaults to
  `claude` and nothing wires it into a real Codex run yet) plus a
  test-breaking marker-schema design (dual-accept-bump violates the existing
  1:1 schema↔roster invariant and reds ~5 test files asserting
  `marker_schema == 4`).
- **Findings:**
  - HIGH/security — `claude -p "<diff>"` on Windows: `claude.cmd` shim +
    `list2cmdline` argv quoting is not `cmd.exe`-safe (BatBadBut class); a
    diff containing `&`/`|`/`^`/`"` can break out. **fix** — reject a
    resolved `.cmd`/`.bat` target in `_resolve_claude_binary()`, fall back to
    OpenRouter; add a regression test.
  - HIGH/security — `--permission-mode dontAsk --max-turns 1` alone doesn't
    match `review_codex()`'s isolation posture (no MCP/settings/hooks
    stripping). **fix** — add empty-tools/`--strict-mcp-config` equivalents,
    verify empirically in Confidence Calibration, record exact flags in spec.
  - HIGH/completeness — `review_verdict._SUPPORTED_REVIEWER_SETS` not
    updated → every `{glm,opus}` run blocks at `contradiction_block()`.
    **fix** — derive it from `CURRENT_REVIEWER_ROSTERS`, update the hard-coded
    message string.
  - HIGH/completeness — `mark-review-state.py`'s `parse_verdict_args` rejects
    `--verdict opus=…` (validates against bare `REVIEWERS` tuple). **fix** —
    validate against the roster union; add to file list + CLI test.
  - HIGH/completeness — `external_review_config._VALID_MODEL_KEYS` whitelist
    blocks `claude_cli`/`openrouter_opus` keys; `resolve_model()`'s bare
    `ValueError` isn't caught by `except ReviewModelPolicyError`. **fix** —
    add both keys unconditionally (not "if it holds accessors").
  - HIGH/completeness — step 9's `review_payloads` guidance was backwards:
    `_verdicts_from_text` keys off `REVIEW_ENVELOPE_SCHEMA` (payload envelope,
    always 2), not marker schema; conflating them would `ReviewFindingsError`
    every `{glm,opus}` run at F5c. **fix** — widen schema-2's
    `expected_candidates` to include `{glm,opus}`, same precedent as
    DeepSeek→GLM (envelope shape didn't bump then either).
  - HIGH/completeness — the fix doesn't take effect this iterate: `--driver`
    defaults to `claude`, AGENTS.md/Durchlauf wiring deferred to a
    (non-blocking) triage card — real Codex runs stay exposed after merge
    while the ACs read green. **STOP — asked the user** (see below).
  - MEDIUM/architecture — `MARKER_SCHEMA` 4→5 dual-accept-bump breaks the
    schema's documented 1:1 schema↔roster invariant AND reds ~5 existing test
    files asserting `marker_schema == 4` on a fresh `{glm,openai}` write —
    directly contradicts this iterate's own regression-floor AC. **fix
    (adopted)** — keep `MARKER_SCHEMA = 4`; add `OPUS_MARKER_SCHEMA = 5`; one
    `schema_for_roster(verdicts)` helper called from both
    `review_companion.write_markers` and `mark-review-state.py` (which
    currently never passes `marker_schema` at all — a second bug this
    surfaced). `CURRENT_REVIEWER_ROSTERS` stays the right generalization for
    `review_verdict`/`review_record_schema`/`review_companion`; only the
    *marker* schema stays roster-exact.
  - MEDIUM/security — driver fail-open is bidirectional (a spurious
    `--driver codex` on a Claude-driven run = Opus-reviews-Claude, the
    mirror-image bug, equally undetected). Recording `driver` alone is
    necessary but not sufficient. **STOP — asked the user** (see below).
  - MEDIUM/completeness — `llm_review.run_review()` (Adopt's Layer-3 review,
    `review_assistant_ui_plan.py`) is a second, untouched `{glm,openai}` +
    `resolve_openai_route` copy. **disclose** — different consumer/feature
    surface, scope-ratchet guard applies; filed as a follow-up triage card,
    not this iterate's build.
  - MEDIUM/completeness — the code-mode empty-diff short-circuit in
    `external_review.py` hardcodes `{glm,openai}` before route resolution.
    **fix** — build that dict from the selected roster; add to step 7's test
    matrix.
  - MEDIUM/completeness — no docs/changelog step (new CLI flag →
    `docs/guide.md` Appendix B; marker-schema change → `hooks-and-pipeline.md`
    already documents `marker_schema`). **fix** — added as step 9b.
  - MEDIUM/architecture — CLI leg pins the floating alias `opus` while the
    OpenRouter leg pins the exact slug `anthropic/claude-opus-5` — asymmetric
    identity-lock. **fix** — CLI docs already confirm `--model claude-opus-5`
    (full pinned ID) works identically to `--model opus`; bind the CLI leg to
    the pinned ID too.
  - LOW — spec/mini-plan key-name drift (`models.opus` vs
    `models.claude_cli`). **fix** — `claude_cli`, matching the `codex` key
    convention.
  - LOW — `is_claude_cli_available()` has no auth check (`claude --version`
    proves installation, not authentication); worst case is a full
    `(max_retries+1)*timeout` burn before fallback. **disclose** — documented
    limitation in the function's own docstring, not blocking.
  - LOW — `external_review_default_legs.py` is already near the 300-line
    guideline; five new functions would cross it. **fix** — new sibling
    module `external_review_opus_leg.py`.
  - LOW — mini-plan step 5 proposed `review_opus_openrouter()` then argued it
    may be unnecessary. **fix** — drop the wrapper, call
    `review_openrouter(..., model_key="opus")` directly; the spec AC naming
    the wrapper function is corrected to not force an unneeded abstraction.
- **Known limitations:** `llm_review.run_review()`'s parallel `{glm,openai}`
  roster (Adopt/Layer-3, `review_assistant_ui_plan.py`) keeps today's
  self-review exposure for that surface — tracked as a follow-up triage card,
  not fixed here (scope-ratchet guard: different consumer, this iterate's
  spec never claimed that surface).
- **Status:** 15 fixed, 1 disclosed, 2 high/medium-severity findings escalated
  to the user before build (see below).

**High/medium-severity findings escalated — user asked, per Step 0's
STOP-before-build rule — both resolved before build:**
1. **Resolved: stays a separate follow-up, not this iterate's scope.**
   `--driver`/`AGENTS.md` wiring into a real Codex-CLI-driven run ships
   dormant this iterate — filed as `trg-a27ab4d9` (high), not built here.
   Reason: wiring it now would require deciding Codex CLI's own
   subagent-model-pinning mechanism (`.codex/agents/*.toml` /
   `agents.default_subagent_model`), a separate, not-yet-empirically-verified
   question this iterate does not answer.
2. **Resolved: `--driver` is `required=True`, no default.** Closes the
   fail-open gap in both directions (a spurious `claude` on a Codex-driven
   run, and the mirror-image `codex` on a Claude-driven one) at the CLI-shape
   level — every caller must declare it. This is what AC #7 (line 61-62)
   already specified; the earlier AC #2 wording implying a `claude` default
   was the stale half, corrected above and by External Plan Review below.

## External Plan Review (external, `--driver claude`, 2026-09-17)
- **Ran:** yes
- **Verdicts:** glm=revise, openai=revise (no contradiction — both `revise`)
- **Provider:** codex (GPT leg routed via `external_review.gpt_leg.provider:
  codex`, per shipped config)
- **Findings (both reviewers independently converged on #1 and #2):**
  - HIGH/approach (both) — Acceptance Criteria contradicted the resolved
    decisions above (AC #2 still described a `claude` default; AC #4 pinned
    a literal `--model opus`; AC #5 named a dropped `review_opus_openrouter()`
    wrapper). **fix (applied above)** — rewrote all three ACs to match the
    actual shipped code and the two resolved escalations.
  - HIGH/edge-case (glm) — nothing in the plan gives the *executing agent* a
    deterministic way to know which driver it is, so `{driver}` in the prose
    call sites could silently resolve to `claude` on a Codex-driven session,
    reintroducing the exact self-review bug this iterate fixes. **fix** —
    added an explicit resolution rule to `iteration-planning.md`: the value is
    self-evident to whichever program is executing these instructions (a
    Claude Code session is always `claude`; a session invoked through Codex
    CLI's own agent loop is always `codex`), never inferred from an
    environment variable or config file — consistent with Sven's explicit
    rejection of env-sniffing (see Rejected Alternatives above).
  - MEDIUM/edge-case (glm) — on Windows, the `.cmd`/`.bat` shim refusal means
    the local Claude CLI transport will effectively never be selected, making
    `OPENROUTER_API_KEY` load-bearing (not merely a fallback) for every
    `driver=codex` run on that platform. **disclose** — already fails loudly
    with a named reason (`resolve_opus_route`'s `"none"` branch → `"skipped"`
    status with an explicit reason string, verified in code); documenting the
    Windows-specific framing is the only gap, added as a known limitation
    below.
  - MEDIUM/dependency (openai, glm) — new `driver` envelope key and marker
    schema 5 might have un-updated strict-key/reader consumers elsewhere.
    **verified, no fix needed** — grepped `REVIEW_ENVELOPE_SCHEMA` and
    `marker_schema` consumers repo-wide: no strict-key envelope validator
    exists, and the only three `marker_schema` readers/writers
    (`mark-review-state.py`, `review_companion.py`, `review_marker.py`) are
    all already updated by this iterate. Full test suite (11,000+ tests
    across every root) passed green with both new fields present.
  - MEDIUM/dependency (openai) — empty MCP config path resolution by CWD
    could fail outside the repo root. **verified, no fix needed** — already
    resolved via `Path(__file__).resolve().parents[2]` in
    `external_review_opus_leg.py`, never CWD.
  - LOW/approach (glm) — mini-plan's Rejected Alternatives section claimed
    Claude CLI "cannot take the prompt via stdin at all", which contradicts
    the adopted design's own stdin content/context piping. **fix** —
    corrected the mini-plan wording to the accurate distinction
    (instructions via `-p`, content/context via stdin — not a stdin/no-stdin
    split).
  - LOW/edge-case (glm) — contract test's block-extraction should reuse
    `test_review_routing_contract.py`'s parsing approach. **disclose** — the
    new `test_external_review_driver_prose_contract.py` uses its own
    fenced-code-block regex (CRLF-aware, any language tag) rather than
    importing that file's helper; both independently pass and the two tests
    check different things (routing identity vs. flag presence). Not unified
    — acceptable duplication per this project's own "three similar lines"
    guidance, not a correctness gap.
- **Known limitations (added by this pass):** on Windows, `driver=codex`
  effectively requires `OPENROUTER_API_KEY` (the local Claude CLI transport
  is unreachable behind the `.cmd`/`.bat` shim refusal) — not a bug, since the
  failure is loud and named, but worth stating plainly rather than leaving it
  implicit in the fallback-route code.
- **Status:** 2 fixed (stale ACs, mini-plan wording), 1 fixed (driver
  self-identification prose), 3 verified as already correct in the shipped
  code, 1 disclosed as a known limitation, 1 disclosed as acceptable
  duplication.

## Architecture Review (external, brief instead of plan, 2026-09-17)
- **Ran:** yes
- **Verdicts:** openai=approve, glm=revise (no contradiction — within one step)
- **Findings:**
  - HIGH/ownership (glm) — this iterate incurs the full standing cost of the
    new mechanism (third identity, second marker schema, flag, contract test)
    while the bug it exists to fix (Codex self-review) stays live after merge,
    since AGENTS.md/Durchlauf wiring is deferred to `trg-a27ab4d9`. **disclose**
    — the same trade-off already escalated to and decided by Sven (see
    "High/medium-severity findings escalated" resolution #1 above): wiring now
    would require deciding Codex CLI's own subagent-model-pinning mechanism
    first, a separate, unverified question. Not an oversight surfacing twice —
    the same informed decision, reached independently by a second review.
  - MEDIUM/simpler-alternative (glm) — the local Claude CLI transport (binary
    resolution, `.cmd`/`.bat` refusal, isolation-flag parity, a Windows known
    limitation) is the largest share of new standing surface; an
    OpenRouter-only "opus" leg would cost roughly half as much to maintain.
    **decline** — mirrors the existing "openai" leg's own established
    CLI-primary/OpenRouter-fallback shape (flat-cost-under-subscription
    primary, paid fallback); the spec's Goal section specifies this shape
    explicitly, not incidentally. Architectural consistency with the leg it
    parallels outweighs the maintenance-cost argument here.
  - LOW/proportionality (glm) — the 8-site grep-based prose contract test is
    itself a standing, rot-prone mechanism. **disclose** — accepted;
    the test matches on flag presence within a fenced block, not exact block
    shape, which is already the loose form GLM's suggestion asks for.
- **Status:** 2 disclosed (informed, already-decided trade-offs), 1 declined
  (architectural consistency), 0 fixed — no new action beyond the External
  Plan Review section above.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run pytest shared/scripts/tests/ shared/scripts/tools/tests/ -k "external_review or opus_leg or driver"`
- **Evidence path:** `.shipwright/agent_docs/iterates/iterate-2026-09-16-opus-review-leg-codex-driver.test-results.json`
