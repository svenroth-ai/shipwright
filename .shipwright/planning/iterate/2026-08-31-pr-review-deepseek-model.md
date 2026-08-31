# Iterate Spec: pr-review-deepseek-model

- **Run ID:** iterate-2026-08-31-pr-review-deepseek-model
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
Swap the Tier-3 CI PR-review gate's model from `anthropic/claude-sonnet-4.6`
to `deepseek/deepseek-v4-pro` — far cheaper and faster per call, at an
empirically confirmed working setup for this exact gate's payload shape
(verified live below; SWE-bench Verified near-parity was the original
motivation but is a patch-generation benchmark, not a review-quality one, so
it is not cited as evidence of review fitness) — while reusing this repo's
existing fail-closed ZDR (zero-data-retention) provider-routing policy for
DeepSeek calls specifically, so a DeepSeek-routed PR diff is never sent
through an unverified OpenRouter route. This is a property of the `deepseek/`
namespace, not of the gate generally: a non-DeepSeek model identity (including
a router/aggregator alias) never touches this policy at all, by AC-3's
short-circuit design, and carries whatever retention terms that model's own
OpenRouter route has.

## Acceptance Criteria
- [x] `plugins/shipwright-security/scripts/lib/pr_review_openrouter.py`'s
  `DEFAULT_MODEL` (via one named constant, `DEEPSEEK_MODEL`) is
  `deepseek/deepseek-v4-pro`; `.github/workflows/pr-review-run.yml`'s
  `SHIPWRIGHT_PR_REVIEW_MODEL` env var matches, and a test asserts the two
  are equal (not just that the env var exists) so they cannot drift apart.
- [x] When the resolved model is in the `deepseek/` vendor namespace
  (normalized: trimmed, casefolded, matched by namespace prefix — not exact
  string equality, so any `:variant` suffix or casing difference is still
  caught, since nothing after the namespace segment is required to match),
  the OpenRouter request body carries the same `provider` routing constraint
  (`only`/`order`: novita, together; `allow_fallbacks: false`,
  `data_collection: deny`, `zdr: true`) that
  `shared/scripts/lib/external_review_routing.deepseek_openrouter_extra_body`
  already enforces for the review cascade's DeepSeek arm — reused, not
  reimplemented.
- [x] When the resolved model is anything else (e.g. an operator override back
  to Sonnet, or a future model), no DeepSeek-specific provider constraint is
  applied and `shared/config/external_review.json` is never loaded — the
  free-form model override this gate has had since ADR-167 ("allows a model
  switch via SHIPWRIGHT_PR_REVIEW_MODEL") stays exactly as flexible as today
  for every non-DeepSeek identity; only the DeepSeek family gets a stricter,
  code-owned constraint layered on top.
- [x] If the model is in the DeepSeek family and
  `shared/config/external_review.json`'s `deepseek_routing` block is
  missing/malformed, the PR-review run fails closed (`EXIT_ERROR`, verified
  by asserting `call_openrouter` is never invoked — not just the exit code)
  before `fetch_pr_diff` or any network call — mirrors the cascade's own
  fail-closed contract.
- [x] `test_pr_review_openrouter.py` and `test_pr_review_script.py`'s
  hardcoded `anthropic/claude-sonnet-4.6` assertions are updated to import
  and use the new `DEEPSEEK_MODEL` constant, plus new coverage for: the ZDR
  body applying to `deepseek/deepseek-v4-pro` AND a variant suffix/casing
  form, no body/no config-load for a non-DeepSeek override, the fail-closed
  path on broken `deepseek_routing` config, and defensive payload merging
  (a hostile `extra_body` cannot overwrite `model`/`messages`/`response_format`).

## Spec Impact
- **Classification:** none
- **NONE justification:** FR-01.17 ("Independent re-check on the code host")
  describes the *business* behavior — every proposed change is reviewed
  automatically on the host before merge — in provider-neutral language. This
  change swaps which LLM performs that automated re-check; the FR's described
  behavior is unchanged, only the model/cost/latency profile changes.

## Out of Scope
- `shipwright_model_config.json`'s `review`/`finalization`/`execution`/
  `floors.review` fields — those select Claude Code's own internal subagent
  tier (Agent/Task tool calls) for build/review subagents, are Anthropic-only
  by construction, and are a wholly separate mechanism from this
  OpenRouter-based CI gate.
- `shared/config/external_review.json`'s `models`/`deepseek_routing` values
  themselves — read from, not modified. The plan/iterate/architecture review
  cascade keeps using GPT-5.6-Terra + DeepSeek v4 Pro exactly as configured
  today.
- Any change to which PRs are tiered into Tier-3 review (`review_record_tier.py`).

## Design Notes
n/a — no UI surface.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `.github/workflows/pr-review-run.yml` (env var) | `plugins/shipwright-security/scripts/tools/pr_review.py` (`os.environ.get("SHIPWRIGHT_PR_REVIEW_MODEL", DEFAULT_MODEL)`) | env var (string) |
| `shared/config/external_review.json` (`deepseek_routing` block) | `shared/scripts/lib/external_review_routing.deepseek_openrouter_extra_body` (reused by `pr_review_openrouter.py`) | JSON |

`touches_io_boundary` did not fire on classification (env-var/JSON reads here
are pre-existing, well-tested boundaries being reused, not new formats), but
both are listed for completeness since this run adds a new *consumer* of the
existing `deepseek_routing` JSON boundary.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Reusing `deepseek_openrouter_extra_body()` and failing closed
  before any network call are the right calls; three things had to change
  before build.
- **Findings:**
  - [high, security] Exact-string model match is a fail-open ZDR bypass for
    a variant suffix/casing (`deepseek/deepseek-v4-pro:free`, stray
    whitespace) — **fix**: match the normalized `deepseek/` vendor
    namespace, not a literal string.
  - [high, completeness] `MAX_DIFF_CHARS` was derived from Sonnet's context
    window; pinning to novita+together could have a smaller effective
    window — **fix**: queried OpenRouter's live endpoints metadata (below);
    confirmed, no cap change needed.
  - [high, architecture] No pre-merge canary/rollback for a required gate
    whose first live exercise would otherwise be some unrelated PR after
    merge — **mitigated**: ran a live probe against the exact production
    payload shape before merge (below); operator confirmed this is
    sufficient, no additional rollback machinery.
  - [medium, security] Adversarial-robustness properties (prompt-injection
    resistance) don't automatically transfer from Sonnet to DeepSeek even
    though the ZDR/retention properties do — **disclosed**: filed as a
    follow-up (a dedicated adversarial-diff test of the reviewer prompt,
    applicable to any reviewer model, not specific to this swap) rather than
    blocking this iterate.
  - [medium, architecture] `response_format: json_object` + the provider pin
    was an untested combination — **fix**: confirmed live (below); novita
    advertises `response_format` support and returned valid strict JSON.
  - [medium, completeness] `max_tokens`/`finish_reason` not surfaced —
    **decline both**: `pr_review.py` already omits `max_tokens` (unlike the
    cascade), which lets a real review use the provider's full completion
    budget instead of truncating — adding a cap would introduce a new
    truncation risk that does not exist today. With that risk absent,
    plumbing `finish_reason` through `call_openrouter`'s return contract
    (currently a bare content string) buys no live diagnostic value for the
    complexity of the interface change; a truncated/malformed reply already
    surfaces via the existing "could not parse review JSON" `EXIT_ERROR`
    path either way.
  - [medium, security] Payload merge semantics unspecified — **fix**: merge
    as `{**extra_body, **payload}` so transport keys (`model`, `messages`,
    `response_format`) always win over a config-derived body.
  - [medium, architecture] `resolve_extra_body`'s `shared/scripts/lib`
    sys.path wiring belongs in the tool (`pr_review.py`), not the pure-HTTP
    boundary module (`pr_review_openrouter.py`) — **fix**: relocated,
    matches this plugin's existing convention (`scan.py`,
    `generate_security_report.py`, ...).
  - [medium, completeness] Workflow/code model-string drift was checked by
    eyeball, not a test — **fix**: strengthened
    `test_pr_review_workflow_shape.py` to assert equality with
    `DEEPSEEK_MODEL`, not just the env var's presence.
  - [medium, completeness] `docs/hooks-and-pipeline.md`'s context-loading
    matrix — **checked, no change**: that matrix covers pipeline *phase
    skills'* startup reads (`PIPELINE_STEPS`); `pr_review.py` is a
    CI-triggered standalone tool outside the pipeline, the same carve-out
    `shipwright-grade` already documents there. Does not apply.
  - [low, architecture] Fail-closed path posts no PR comment — **fix**:
    clearer stderr distinguishing "reviewer misconfigured" from "your diff
    was rejected"; **decline** adding PR-comment posting on this path — same
    precedent as the existing no-API-key/prompt-dir `EXIT_ERROR` paths.
  - [low, completeness] Fail-closed test should assert `call_openrouter` was
    never invoked, not just the exit code — **fix**: incorporated.
  - [low, completeness] Goal cited SWE-bench (a patch-generation benchmark)
    as review-quality evidence — **fix**: reworded above.
- **Known limitations:** Adversarial-robustness parity with Sonnet is
  unverified (disclosed, follow-up filed, not blocking); the `together`
  provider in the approved ZDR allowlist currently has no live endpoint for
  `deepseek/deepseek-v4-pro` at all (discovered while re-deriving
  `MAX_DIFF_CHARS`, see below) — pre-existing in `shared/config/external_review.json`,
  shared by the review cascade's own DeepSeek arm, and out of scope here
  (this iterate does not modify `deepseek_routing`); filed as a triage card
  for the config's owner.
- **Status:** 3 fixed outright, 5 fixed after empirical verification, 3
  disclosed/declined with reasoning, 2 reworded.

## External LLM Review
- **Branch:** A (keys available)
- **Mode `iterate` (plan review) verdicts:** deepseek=revise, openai=revise
  (no contradiction — both converged on the same core issue)
- **Findings:** Both reviewers independently caught the same high-severity
  gap the internal review also found from a different angle: the original
  draft called `load_review_config()` **unconditionally for every model**,
  so a broken/absent `external_review.json` would break PR review even for a
  non-DeepSeek override — directly violating the "no DeepSeek-specific
  handling for another model" acceptance criterion. Also flagged (both):
  `extra_body` should be keyword-only and trailing (no positional-arg
  breakage); config-loader exceptions should be caught alongside
  `DeepSeekRoutingPolicyError`, not just the latter; one named model
  constant instead of a duplicated literal.
- **Reconciliation:** All integrated — `resolve_extra_body` now
  short-circuits to `{}` **before** any config import/load when the model is
  outside the DeepSeek namespace (mini-plan Work Breakdown step 1), closing
  the exact gap both reviewers named.
- **Mode `architecture` verdicts:** deepseek=approve, openai=approve, no
  findings — confirms this changes no standing mechanism (brief:
  `.shipwright/planning/iterate/iterate-2026-08-31-pr-review-deepseek-model/architecture_brief.md`).

## Confidence Calibration
- **Boundaries touched:** env var → `pr_review.py` (existing, reused);
  `deepseek_routing` JSON → `pr_review_openrouter.py` (new consumer, reuses
  the cascade's own reader/validator).
- **Empirical probes run:**
  - `shared/scripts/tools/probe_deepseek_zdr.py` (existing tool, live run) —
    `status: success`, `selected_provider: novita`, ZDR provider pin
    honored, response valid. Evidence:
    `.shipwright/planning/iterate/iterate-2026-08-31-pr-review-deepseek-model/deepseek-zdr-probe.json`.
  - Live call replicating the EXACT PR-review payload shape (system+user
    messages, `response_format: json_object`, the same `provider` ZDR body,
    against `deepseek/deepseek-v4-pro`) — `finish_reason: stop`,
    `provider: Novita`, valid strict JSON returned
    (`{"decision": "approve", "summary": "..."}`), cost $0.0005. Confirms
    `response_format` + the provider pin do not conflict (resolves the
    "untested combination" finding above) and that the DeepSeek/novita path
    produces schema-valid output on the reviewer's own contract.
  - `GET https://openrouter.ai/api/v1/models/deepseek/deepseek-v4-pro/endpoints`
    (public, no auth) — Novita: `context_length: 1,048,576`,
    `max_completion_tokens: 393,216`, `response_format` in
    `supported_parameters`. Both exceed the values `MAX_DIFF_CHARS` (1M
    chars) was derived from
    (`.shipwright/planning/iterate/2026-07-27-pr-review-diff-cap.md`:
    Sonnet's 1,000,000 context / 128,000 max completion) — **the existing
    cap needs no change**, and is now more conservative relative to novita's
    actual budget than it was relative to Sonnet's. `together` does not
    appear in the endpoint list at all for this model — noted as a
    known limitation above, out of scope for this iterate.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `resolve_extra_body` returns the ZDR body for `deepseek/deepseek-v4-pro` | tested | `test_pr_review_model_policy.py::TestResolveExtraBody::test_deepseek_model_returns_the_zdr_body` |
  | 2 | `is_deepseek_model`/`resolve_extra_body` match a variant/cased DeepSeek identity (`:free`, mixed case, padding whitespace) | tested | `test_pr_review_model_policy.py::TestIsDeepseekModel::test_matches_the_deepseek_namespace` (parametrized) + `TestResolveExtraBody::test_deepseek_variant_form_also_gets_the_zdr_body` |
  | 3 | `resolve_extra_body` returns `{}` for a non-DeepSeek model, without ever calling `load_review_config` | tested | `test_pr_review_model_policy.py::TestResolveExtraBody::test_non_deepseek_model_returns_empty_without_loading_config` |
  | 4 | `resolve_extra_body` propagates `DeepSeekRoutingPolicyError` on a malformed `deepseek_routing` block | tested | `test_pr_review_model_policy.py::TestResolveExtraBody::test_broken_routing_config_propagates` |
  | 5 | `_post_openrouter` merges `extra_body` into the payload, transport keys always winning over a hostile override | tested | `test_pr_review_openrouter.py::TestPostOpenRouter::test_merges_extra_body_defensively` |
  | 6 | `_post_openrouter` payload is byte-identical to today's shape when `extra_body` is omitted | tested | `test_pr_review_openrouter.py::TestPostOpenRouter::test_builds_authorized_json_request` (asserts the payload key set) |
  | 7 | `call_openrouter` passes `extra_body` through to `_post_openrouter` | tested | `test_pr_review_openrouter.py::TestCallOpenRouter::test_extra_body_is_passed_through` |
  | 8 | `pr_review.py main()` fails closed (`EXIT_ERROR`, `call_openrouter` never invoked) on a broken `deepseek_routing` config | tested | `test_pr_review_deepseek_routing.py::TestDeepSeekRoutingGate::test_fails_closed_before_any_network_call_on_broken_deepseek_routing` |
  | 9 | `pr_review.py main()` fails closed on a malformed/unreadable `external_review.json` | tested | `test_pr_review_deepseek_routing.py::TestDeepSeekRoutingGate::test_fails_closed_on_malformed_external_review_json` |
  | 10 | `pr_review.py main()` proceeds normally (no config touched) on a non-DeepSeek model override | tested | `test_pr_review_deepseek_routing.py::TestDeepSeekRoutingGate::test_non_deepseek_override_never_touches_the_review_config` |
  | 11 | `DEFAULT_MODEL`/`DEEPSEEK_MODEL` equal `deepseek/deepseek-v4-pro` | tested | `test_pr_review_openrouter.py::TestDefaults::test_default_model_is_deepseek` |
  | 12 | Every existing `pr_review.py` orchestration test (approve/block/comment/truncation/stale-verdict-cleanup/etc.) still passes with the new DeepSeek default and the new `extra_body` parameter threaded through | tested | full `test_pr_review_script.py` + `test_pr_review_deepseek_routing.py` + `test_pr_review_stale_verdicts.py` suites — 954 passed, 7 skipped (pre-existing, unrelated) across the whole plugin (post file-size-guideline split; see note below) |
  | 13 | Workflow's `SHIPWRIGHT_PR_REVIEW_MODEL` equals `pr_review_openrouter.DEFAULT_MODEL` | tested | `test_pr_review_workflow_shape.py::TestSecrets::test_model_env_matches_code_default` |
  | 14 | End-to-end DeepSeek+ZDR+`response_format` production payload produces valid strict JSON | tested | live probe above (not a CI-repeatable unit test — a paid external call; recorded as empirical evidence, not a regression-suite member) |
  | 15 | `pr_review.py main()` with the DEFAULT model (no override) threads the real ZDR provider body through to `call_openrouter` | tested | `test_pr_review_deepseek_routing.py::TestDeepSeekRoutingGate::test_the_default_deepseek_model_actually_delivers_the_zdr_body` (added per Stage 2 code-reviewer's medium finding) |

  **Post-write file-size-guideline split (behavior-preserving, no new spec
  divergence — Stage-1 spec-reviewer confirmed):** the Stop hook's 300-line
  guideline blocked completion on three files. `pr_review.py`'s `_post_verdict`
  body moved to `pr_review_verdict.post_verdict()` (poster functions
  dependency-injected so `pr_review.post_pr_comment`/`post_pr_review_state`
  monkeypatches keep working); `test_pr_review_workflow_shape.py`'s
  `TestHardening` class moved verbatim to `test_pr_review_workflow_hardening.py`;
  and the three DeepSeek-routing tests in rows 8-10 moved verbatim (with their
  own `_wire` copy) from `test_pr_review_script.py::TestMainOrchestration` to
  `test_pr_review_deepseek_routing.py::TestDeepSeekRoutingGate` — the evidence
  column above reflects their new location.

- **Confidence-pattern check:** Asymptote — the internal review's "are you
  confident in the fail-closed design?" produced a real finding (the
  unconditional-config-load gap) on the FIRST pass, so a second empirical
  probe (the live payload-shape call) was run before F0, per the
  anti-pattern rule. Coverage — all 15 ledger rows `tested`, 0
  untested-testable. `cross_component` did not fire on classification (no
  merge/hook/pipeline-validator machinery touched), so no separate
  integration-coverage row is required.

## Code Review (spec-reviewer + code-reviewer)

**Stage 1 (`spec-reviewer`, hard gate) — 3 passes, PASS on the 3rd:**
1. REJECT — AC-5's `DEEPSEEK_MODEL` constant wasn't reachable via `pr_review.py`
   (not imported, not in `__all__`) and `test_pr_review_script.py` still
   hardcoded the model literal instead of using it. Fixed: `DEEPSEEK_MODEL`
   added to `pr_review.py`'s import + `__all__`; the test now asserts
   `pr_review.DEFAULT_MODEL == pr_review.DEEPSEEK_MODEL`.
2. REJECT — the Test Completeness Ledger's rows 8-10 cited test node IDs that
   no longer existed after the Stop-hook-forced file-size split moved those
   three tests into `test_pr_review_deepseek_routing.py::TestDeepSeekRoutingGate`.
   Fixed: ledger rows 8, 9, 10, 12 repointed; a note added after row 14
   documenting the split.
3. PASS — both fixes confirmed; ACs 1-5 hold; the three splits
   (`pr_review_verdict.post_verdict`, `TestHardening` extraction,
   DeepSeek-routing tests extraction) confirmed behavior-preserving.

**Stage 2 (`code-reviewer`) — PASS with findings (0 high, 2 medium, 4 low).**
All 6 addressed:
- **medium** — `test_pr_review_model_policy.py`'s `_SHARED_LIB` used
  `parents[4]` (one level above the repo root) instead of `parents[3]`; the
  import only worked by accident because a sibling import had already inserted
  the correct path as a side effect. **Fixed** (`parents[3]`).
- **medium** — no end-to-end test proved the DEFAULT (DeepSeek) model actually
  delivers the ZDR body through `main()` to `call_openrouter` — only the
  negative (non-DeepSeek) case was pinned. **Fixed**: added
  `test_the_default_deepseek_model_actually_delivers_the_zdr_body`.
- **low** — `resolve_extra_body()`'s `except` tuple missed `UnicodeDecodeError`
  and `AttributeError` (a non-object config), which would escape as an
  unredacted traceback exiting 1 instead of the documented redacted
  `EXIT_ERROR`. **Fixed**: widened to `except Exception`, matching the two
  neighboring boundaries in `main()`.
- **low** — the fail-closed tests asserted only that `call_openrouter` was
  never invoked, not that `fetch_pr_diff`/`read_reviewed_head` were also
  unreached (the stricter ordering the AC actually requires). **Fixed**:
  `_wire` now counts all three and both tests assert all are 0.
- **low** — `post_verdict`'s `fn is post_review_state_fn` identity check
  becomes unreliable if a caller ever passed the same callable for both
  posters (unreachable before DI, reachable after). **Fixed**: carried an
  explicit `is_state` flag in the loop tuple instead of identity comparison.
- **low** — the generic orchestration suites (`test_pr_review_script.py`,
  `test_pr_review_stale_verdicts.py`) implicitly ran the REAL
  `resolve_extra_body` against the real `shared/config/external_review.json`,
  an undocumented coupling unrelated to what those suites test. **Fixed**:
  both `_wire` helpers now stub `resolve_extra_body` to `{}`.

Full suite re-verified green after all fixes: 955 passed, 7 skipped
(pre-existing, unrelated). Ruff clean on every touched file.

**External code-review cascade (medium+, mandatory):** openai leg succeeded
("No concrete defects found... ship-as-is", `SHIPWRIGHT_VERDICT: approve`);
deepseek leg returned `status: degraded` ("provider returned an empty reply",
transient, not a finding). Recorded `external_code` completed with openai's
verdict, `--contradiction-resolution` noting the single degraded leg is not
treated as a contradiction requiring escalation given the diff was already
independently covered by Stage 1/2/3.

## Doubt Review (Stage 3, advisory-must-address)

Triggered by cross-plugin imports (`pr_review_model_policy.py` reaches into
`shared/scripts/lib`). 1 high, 2 medium, 2 low — all addressed:

- **high (reversibility)** — ZDR's `allow_fallbacks:false` + the documented
  `together`-has-no-live-endpoint limitation leaves exactly one live provider
  (novita) serving a REQUIRED merge gate; rolling back is circular because
  `workflow_run` always runs the DEFAULT BRANCH's copy of `pr-review-run.yml`,
  so a rollback PR is reviewed by main's own still-broken logic. **Disposition:
  accepted, documented** — engineering redundancy (a second live ZDR provider)
  is out of scope per this iterate's own Out-of-Scope decision and the user's
  explicit choice not to build extra rollback machinery beyond the live test;
  the cheap, in-scope action is documentation, so a comment naming the
  circularity and the `gh pr merge --admin` recovery path was added directly
  above `SHIPWRIGHT_PR_REVIEW_MODEL` in `pr-review-run.yml`.
- **medium (hidden coupling)** — `shared/config/external_review.json` is now
  load-bearing for the required gate but wasn't in `review_record_tier.py`'s
  `SENSITIVE_PATH_RE`. **Fixed**: added, with a test
  (`test_review_record_tier.py`) asserting the path is sensitive.
- **medium (boundary/contract)** — the Goal's wording read as a property of
  the gate generally rather than of the `deepseek/` namespace specifically (a
  router/aggregator model identity gets no provider pin, by AC-3's deliberate
  design). **Fixed**: narrowed the Goal's wording.
- **low** — `post_verdict`'s injected posters were bare `Callable`, so an
  arity mismatch at a future call site would raise inside the best-effort
  `try`. **Fixed**: parameterized the `Callable` annotations.
- **low** — the broadened `except Exception` reports every failure as "ZDR
  routing policy misconfigured", masking a genuine code bug — but narrowing it
  back would be WRONG (ADR-045 dual-import means a raised
  `DeepSeekRoutingPolicyError` may not be `is`-identical to the imported
  class). **Fixed**: added `type(e).__name__` to the message and a comment
  explaining why the catch must stay broad.

Full suite re-verified green after all fixes: 955 passed, 7 skipped. Ruff
clean on every touched file.

## Verification (medium+)
- **Surface:** none
- **Justification (surface=none):** This is a CI-script backend change with
  no startable web/cli/api dev surface. The actual OpenRouter network call
  was still exercised live (see Confidence Calibration probes above) rather
  than only mocked — that live verification is the E2E-equivalent evidence
  for this surface; the remaining behavior (payload construction, fail-closed
  branching) is covered by mocked unit tests, the same strategy this file
  already uses for its existing model/timeout constants.
