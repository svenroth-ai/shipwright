# ADR: Codextender monorepo integration — Part C

**Run:** iterate-2026-09-23-codextender-monorepo-part-c

## Context

`Spec/codextender-integration.md` (design brief, private/internal, not
shipped in this repo — `Spec/` is gitignored) Part C scopes four monorepo-side
changes needed to support "Codextender" mode: a local proxy that re-points a
`claude`-driven session at a Codex-backed model via `ANTHROPIC_BASE_URL`,
without changing the driving binary. Under Codextender the harness stays
`claude`, but the diff/review content is authored by a Codex-backed model.

1. Internal reviews (spec/code/doubt-reviewer, plan_review) needed a way to
   route review subagents onto the same Codex-backed model as the main
   session.
2. `shared/scripts/tools/external_review.py`'s `--driver claude|codex` flag
   picks the independent-reviewer roster (`DRIVER_ROSTERS`:
   `claude` → `{glm, openai}`, `codex` → `{glm, opus}`). Every call site in
   the plugins hardcoded or resolved `claude` whenever the harness was Claude
   Code — correct pre-Codextender, wrong once the harness and the diff's
   authorship can diverge.
3. `external_review_opus_leg.py`'s `review_claude_cli` spawned the local
   `claude` CLI with `subprocess.run(argv, input=...)` and no `env=`,
   inheriting the parent process's `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`/
   `ANTHROPIC_MODEL` verbatim — a real, pre-existing bug independent of
   Codextender (anything with `ANTHROPIC_BASE_URL` set for unrelated reasons
   would misroute this leg).
4. `docs/hooks-and-pipeline.md`'s context-loading/config-data-flow tables
   needed the new env-var read documented, per this repo's standing rule.

## Decision

**C.1 — no new plumbing.** ADR-127's existing `inherit` tier already routes
a subagent onto whatever the spawning session runs on. Documented (in
`shared/schemas/model_config.schema.json`'s `Tier` description) that setting
`review`/`plan_review` to `"inherit"` in `shipwright_model_config.json` is the
correct operator action under Codextender. A new free-text Codex-alias tier
was considered and rejected in the spec's own Opus review: `agent_model_param()`
only accepts `opus|sonnet|haiku|fable`, and Claude Code resolves a tier to a
full concrete model id before the wire call, so an arbitrary alias like `sol`
would never reach the HTTP request LiteLLM sees.

**C.2 — driver selection, 11-site census.** Made `--driver` conditional on a
new `CODEXTENDER_ACTIVE` env var (`codex` when set, else the existing
harness-identity resolution):
- 7 hardcoded `--driver claude` sites edited directly: `plugins/shipwright-plan/
  skills/plan/references/external-review.md`, `step-5-external-review.md`
  (×2), `plugins/shipwright-plan/skills/plan/SKILL.md`,
  `plugins/shipwright-build/skills/build/references/code-review.md`,
  `plugins/shipwright-iterate/agents/sub-iterate-runner.md` (×2).
- 4 sites that resolve a `{driver}` template placeholder — fixed at the
  resolution source, not the call sites: `iteration-planning.md` (×2, the
  canonical Resolution rule), `iterate/SKILL.md`. A doubt-review pass (Stage
  3) found a 5th, uncensused resolution site: `iteration-reviews.md`'s own
  external-code-cascade paragraph restated the rule independently rather than
  purely deferring to `iteration-planning.md`, and is the ONLY driver-resolution
  text a non-medium+ iterate (like this one — small complexity, cascade
  triggered by diff size) ever reads, since `iteration-planning.md` Step 3.5
  is medium+ only. Fixed in the same pass.
- Two bash idioms used depending on each file's LOC/bloat-ceiling headroom:
  `DRIVER=claude; [ -n "${CODEXTENDER_ACTIVE:-}" ] && DRIVER=codex` where
  budget allowed, or an inline `--driver "$([ -n "${CODEXTENDER_ACTIVE:-}" ]
  && echo codex || echo claude)"` substitution where a file was already at
  its ceiling (`sub-iterate-runner.md`=512, `plan/SKILL.md`=300,
  `step-5-external-review.md`=400 — all re-verified to hold exactly at
  their pre-existing ceiling after edits).
- `codex_review_transport.py` explicitly untouched (out of scope — a
  different code path for when Codex CLI itself is the driving harness).

**C.2 — env-leak fix.** `external_review_opus_leg.py` gained
`_ANTHROPIC_ENV_SCRUB_KEYS` (`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_MODEL`) and `_real_anthropic_env()` (a filtered copy of
`os.environ`), passed as `review_claude_cli`'s `subprocess.run(..., env=...)`.
The first version scrubbed unconditionally; a CI-side PR-review pass (Tier-3,
round 2 post-push) found this would break a legitimate, non-Codextender
`ANTHROPIC_AUTH_TOKEN`-only installation (an enterprise bearer-token
credential with no separate `ANTHROPIC_API_KEY`) — the scrub has no way to
distinguish "these vars are a proxy override" from "this is the caller's own
config" without a signal, and `CODEXTENDER_ACTIVE` is exactly that signal.
Fixed: `_real_anthropic_env()` now returns `None` (subprocess.run's own
"inherit unchanged") when `CODEXTENDER_ACTIVE` is unset, and only filters
when it is set. A doubt-review pass separately raised (and the fix
discloses, rather than silently assumes) that scrubbing under Codextender
only *removes* the override — it does not itself prove `claude --bare`
resolves a usable credential via a stored `claude login` session with no
`ANTHROPIC_API_KEY` present; that resolution path predates this fix and is
unverified end-to-end in this codebase, same as it was before Codextender
existed. Regression tests:
`test_review_claude_cli_scrubs_anthropic_routing_env_vars_under_codextender`
+ `test_review_claude_cli_preserves_anthropic_auth_token_outside_codextender`
in `shared/tests/test_external_review_opus_leg_dispatch.py` (split out of
`test_external_review_opus_leg.py`'s `review_claude_cli` dispatch tests when
both that file and `integration-tests/test_external_review_driver_prose_contract.py`
crossed the 300-line bloat gate in this same run; the latter's
openai/opus-key-consistency tests moved to the new
`test_external_review_key_consistency_contract.py`). A local PR-review
preflight (round 3) further suggested also scrubbing generic proxy env vars
(`HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY`), reasoning that some HTTP client
could honor them and redirect the "real Anthropic" call even under this fix.
**Declined, disclosed rather than silently assumed away**: those vars are not
Codextender's routing mechanism (it targets `ANTHROPIC_BASE_URL` per this
ADR's Context), item 3's original scope named only the three `ANTHROPIC_*`
vars, and Sven confirmed shipping at that scope — proxy-var scrubbing, if
ever wanted, is separate future hardening, not this bug fix.

**C.4 — docs.** `docs/hooks-and-pipeline.md` gained a `CODEXTENDER_ACTIVE` row
in Config File Data Flow plus a short Context Loading paragraph, explicitly
stating any non-empty value counts as active (unset to disable — a
doubt-review finding) and that this is a **separate axis** from
`shared/scripts/lib/codex_runtime.py`'s `is_codex_runtime()` (added by
PR #786/R1b) — a different question (is the resolved plugin root a genuine
on-disk Codex-bundle shape?) that must not be folded into this one.
`docs/guide.md` got one clause syncing the `--driver` explanation.

## Consequences

- A Codextender-mode diff gets reviewed by the cross-vendor `{glm, opus}`
  roster instead of the same-vendor `{glm, openai}` roster, restoring the
  independence `DRIVER_ROSTERS` exists to provide.
- The opus-leg env-leak fix benefits every caller of `review_claude_cli`, not
  only Codextender sessions — any environment with a stray
  `ANTHROPIC_BASE_URL` set for unrelated reasons is now also protected.
- `CODEXTENDER_ACTIVE` and `is_codex_runtime()` are now both documented as
  distinct, non-overlapping signals, reducing the chance a future change
  folds them together and silently breaks the hooks-config-layer shim's
  bundle-shape detection.
- Residual, disclosed (not silently assumed): whether `claude --bare`
  actually authenticates via a stored `claude login` session once the
  Codextender override is scrubbed is unverified live in this codebase.

## Review record

Spec-reviewer (Stage 1): PASS. Code-reviewer (Stage 2): PASS, 3 low-severity
non-blocking notes (incomplete scrub-list coverage of non-spec'd routing
vars; a possible additional test assertion; two driver-resolution idioms in
use). Doubt-reviewer (Stage 3, advisory): 2 medium doubts (accepted-and-fixed:
the iteration-reviews.md gap above; accepted-and-fixed: the `=0`/`=false`
ambiguity doc clarification), 1 medium doubt disclosed rather than fixed (the
`--bare` auth-resolution assumption, pre-existing and out of scope for this
fix), 1 low doc-contract nit fixed.

**F11 local PR-review preflight** (threat-model gate, run before push) found
two further real gaps, both fixed in the same commit:
1. `test_sub_iterate_runner_resolves_its_own_driver_not_a_placeholder` only
   checked that `CODEXTENDER_ACTIVE` occurred anywhere in the fenced block,
   not that it was wired into the `--driver` argument itself — a hardcoded
   `--driver "claude"` with `CODEXTENDER_ACTIVE` mentioned elsewhere would
   still have passed. Tightened to extract and check the argument's own
   value.
2. `DRIVER_ROSTERS` keys `external_review.py`'s `reviews` JSON by each
   roster identity's own name (`{glm, openai}` for `--driver claude`,
   `{glm, opus}` for `--driver codex`), but two of the four consumer sites
   that parse that output (`code-review.md`, `sub-iterate-runner.md`) still
   hardcoded `reviews.openai.feedback` only — under Codextender the actual
   key is `reviews.opus`, so the second review would have been silently
   dropped. Fixed both sites to name the driver-conditional key (matching
   the pattern already correct in `iteration-planning.md` /
   `iteration-reviews.md`), and added a drift-protection test pair
   asserting every `reviews.openai.feedback` parse site also names
   `reviews.opus.feedback`.
3. `plan/SKILL.md`'s Branch A read as a hardcoded `--driver claude` literal
   with the Codextender behavior relegated to a trailing parenthetical —
   reworded to `--driver <claude|codex>` with the resolution rule stated as
   the primary clause, matching the census: this was one of the 7 direct-edit
   sites, and the parenthetical-only phrasing from the first pass under-stated
   that.
4. The runtime idiom test itself executed hand-copied duplicate constants
   rather than the actual markdown text, so a typo or regression in the real
   prose could have passed unnoticed. Rewrote it to extract each
   self-resolving block's own driver-resolution snippet (`_extract_live_idiom`)
   and execute that extracted text directly.
