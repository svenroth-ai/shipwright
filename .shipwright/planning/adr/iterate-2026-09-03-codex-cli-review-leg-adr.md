# Codex CLI as a second GPT review leg

**Run ID:** iterate-2026-09-03-codex-cli-review-leg
**Spec:** `.shipwright/planning/iterate/iterate-2026-09-03-codex-cli-review-leg.md`
**Mini-Plan:** `.shipwright/planning/iterate/iterate-2026-09-03-codex-cli-review-leg-MINIPLAN.md`

## Context

Both consumers of the "openai" (GPT) reviewer identity — `external_review.py`
(CLI) and `llm_review.py` (library) — called OpenAI's Chat Completions API,
metered per token, via OpenRouter or direct. The operator has a flat-cost
ChatGPT/Codex subscription and wants the option to route that leg through
the Codex CLI instead, at zero marginal per-review cost, without changing
behavior for operators who don't have Codex.

## Decision

Add `review_codex()` beside `review_openrouter()`/`review_openai()` in
`external_review_default_legs.py`. It shells out to
`codex exec -m <model> --sandbox read-only --ephemeral --cd <isolated tmp>
-o <tmpfile>`, feeding the same system+user prompt text via stdin, and
parses the captured final message through the existing `classify_reply()`
helper — no new output schema, since the shipped prompts already ask for
free-form prose ending in one `SHIPWRIGHT_VERDICT:` sentinel line. Route
selection is config-only (`external_review.gpt_leg.provider`, default
`"api"`), model identity is locked via a new `("openai", "codex")` binding
in `resolve_reviewer_model`, and `is_codex_available()` gives a
never-raising availability check with graceful fallback to the existing
API route (or a stated skip) when Codex is configured but unavailable.

## Consequences

Operators with a Codex subscription can zero out the GPT leg's per-review
API cost; operators without one see byte-identical routing behavior
(verified against the full existing test suite, AC7). One new external
process dependency (`codex` CLI) and its own timeout/retry budget
(worst case `(max_retries + 1) * timeout_seconds`, default 1200s) — larger
than the API route's, since an agentic CLI call is a different transport
than a metered HTTP completion, and invoking skills must budget above it.

## Rationale

Codex CLI is agentic and returns free-form text, not a JSON API response —
it cannot slot into the existing OpenRouter routing/identity-lock machinery
unmodified, so it gets its own leg function reusing the pipeline's existing
prose+sentinel contract rather than inventing a second output schema.

## Rejected alternatives

**Route selection via env var** (`SHIPWRIGHT_REVIEW_GPT_LEG=codex`),
matching the `SHIPWRIGHT_REVIEW_MODEL_*` override pattern used elsewhere.
Rejected: the task requires the provider choice to be config-driven, not
silently overridable — existing env-var overrides in this system are for
*model identifiers* (validated and rejected by `resolve_reviewer_model` if
they'd change the locked identity); an env var choosing the *transport* has
no such backstop and would let a stray environment variable silently change
which system answers a review, invisibly to anyone reading the project's
committed config.

## Internal Plan Review (opus-plan-reviewer)

**Ran:** no (not spawned) — **Status:** not_run

This medium-complexity run's mandatory internal plan-review sub-step
(`opus-plan-reviewer`, `references/iteration-planning.md`) was not spawned
before build began, in the earlier (pre-compaction) portion of this session.
Per project memory (`project_architecture_review_run_order.md`: "retroactive
at finalization defeats 'ask before building'"), it is not being run
retroactively now — doing so after the code is already built and reviewed
would not deliver the sub-step's actual purpose (catching a flawed plan
*before* implementation cost is sunk). This is disclosed honestly here
rather than backfilled. The external plan review (GLM approve, GPT revise,
both addressed) and the full self/spec/code/doubt/external-code review
cascade below covers the same design surface after the fact.

## External-Code-Review-Findings

Three cascade passes (GLM 5.3 + GPT-5.6, both via OpenRouter) ran over this
diff — the first over an incomplete diff (untracked new test files excluded
by `git diff HEAD`), the second and third over the full diff after
`git add -N .`. Findings converged across passes with no new HIGH/MEDIUM
beyond the stable set below (asymptote reached after pass 3).

| Finding | Severity | Disposition |
|---|---|---|
| `gpt_leg_provider()` raises `TypeError` on an unhashable config value (e.g. `"provider": []`) | HIGH | accepted-and-fixed — `isinstance(value, str)` guard before the `in` membership test |
| `codex_settings()` raises `AttributeError` on `config["codex"]` being a non-mapping | HIGH | accepted-and-fixed — coerce to `{}` when not a `dict` before `.get()` |
| `mark-review-state.py` usage docstring omits `codex` from `--provider` | LOW | accepted-and-fixed — doc-only string update (no `choices=` restriction existed) |
| Two tests wrote a real config file but also stubbed `resolve_openai_route` directly, making the config write decorative | MEDIUM | accepted-and-fixed — dropped the redundant stub, kept only `is_codex_available` stubbed, so the real on-disk config drives route resolution |
| `_resolve_codex_binary()`/`is_codex_available()` didn't catch `RuntimeError` from a symlink-loop `Path.resolve()`, violating the "never raises" contract | MEDIUM | accepted-and-fixed — widened to `except (OSError, RuntimeError)` |
| `--sandbox read-only` restricts writes only, not reads/network — a prompt-injected diff still runs against whatever network access the operator's environment grants the `codex` process | HIGH/MEDIUM | rejected-with-reason — documented plainly in the docstring rather than further restricted; Shipwright does not control Codex CLI's own sandbox internals beyond the flags it exposes, and the content sent is no more sensitive than what the OpenRouter/direct-OpenAI legs already transmit to a third-party LLM |
| TOCTOU: `review_codex()`'s internal re-check of availability returns `"error"` rather than looping back through `resolve_openai_route()`'s API fallback | MEDIUM | rejected-with-reason — restructuring both consumers' dispatch (or threading key-availability state into `review_codex`) for a narrow race window is architecturally invasive relative to the risk; the current behavior is pinned by `test_review_codex_errors_when_unavailable_at_toctou_recheck` rather than hidden |
| Orphaned Codex tool-subprocesses can survive a `subprocess.run(timeout=...)` kill — only the direct child is terminated, not a process group | MEDIUM | rejected-with-reason — platform-specific process-group/Job-Object handling is out of scope for this iterate; noted as a follow-up |

## Self-Review

Self-review recorded via `record_review_pass.py` (`--review-type self
--status completed --from self-review`) at
`.shipwright/planning/iterate/iterate-2026-09-03-codex-cli-review-leg/self_review.json` —
8 items (Spec Compliance, Error Handling, Security Basics, Test Quality,
Performance Basics, Naming & Structure, Affected Boundaries, Test Hygiene
Probe), all `pass`. Full review cascade (spec → code → doubt →
external_code) also recorded `completed`; doubt-reviewer's 10-item
adversarial pass fixed 9 directly and verified the 10th
(`is_degraded`/`is_partially_degraded` signature-change blast radius) safe
within this monorepo by exhaustive grep, leaving one documented,
unverifiable external-repo unknown as a follow-up rather than a defect.
