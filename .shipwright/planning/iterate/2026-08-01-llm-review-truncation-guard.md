# Iterate — External review: truncation guard + reasoning budget

- **run_id:** `iterate-2026-08-01-llm-review-truncation-guard`
- **Intent:** BUG (Path C → F-debug)
- **Complexity:** medium (Stage 1 `small` → Stage-2 Repo Scout upgrade)
- **Status:** implemented
- **Spec Impact:** NONE — behavior of a quality gate is repaired, no FR changes
- **Affected FRs:** none (framework-internal review tooling)

## Problem

All three Gemini legs of `iterate-2026-08-01-coverage-gate-recompute-order`
came back degraded — twice truncated, once empty. That run's own review record
states it verbatim:

> `gemini = degraded (reply cut off, finish_reason=length) — recorded degraded,
> NOT counted as an approval.`

External plan review is the highest-yield pass measured across the fleet
(0.94 unique HIGH findings per run over 66 records, vs doubt 0.53,
external_code 0.20, code 0.18). Losing the Gemini leg loses that yield.

## Root cause (F-debug Phase 4 — one sentence)

**Reasoning tokens are billed against the same `max_tokens` ceiling as visible
output, and on both measured uncapped runs the model consumed essentially the
whole ceiling on reasoning, so the 4096 cap left ~600 characters for the answer; `llm_review.py` then
reports that truncated answer as `status: "success"` because — unlike its
sibling `external_review.py` — it never inspects `finish_reason`.**

Two defects, one mechanism.

## Measured evidence (F-debug Phase 2 — real OpenRouter calls)

Live `google/gemini-3.1-pro-preview` calls against a 209,549-char review
prompt (the `45860067` diff plus a demand for an exhaustive structured review):

| `max_tokens` | reasoning cap | reasoning_tokens | visible chars | `finish_reason` |
|---|---|---|---|---|
| 4096 | none | 3928 / 4092 (96%) | 621 | `length` ❌ |
| 16000 | none | 15360 / 15996 (96%) | 2352 | `length` ❌ |
| 16000 | 2000 | 3332 | **13448** | `stop` ✅ |

Two findings that **change the fix** relative to the filing brief:

1. **Raising the budget alone did not fix either measured run.** The reasoning
   share was ~96% at *both* 4096 and 16000 — whether demand scales or merely
   exceeds both ceilings is not distinguished by two points. The explicit cap is the load-bearing
   lever, not the budget. The brief listed these as two co-equal fixes; they
   are not, and shipping only the budget raise would have looked like a fix
   while changing nothing.
2. **The reasoning cap is a soft hint, not a hard limit** — 2000 requested
   yielded 3332 actual (1.7× overshoot). So the total budget must still carry
   margin above `cap + expected answer`; the cap cannot be relied on to bound
   the total by itself.

## Correction to the brief's blast-radius claim

The brief states the silent fail-open is live on the iterate path
("P1.07 is cross_component and therefore medium, so it invokes this path").
That is **not** the case: iterate/plan/build call the `external_review.py`
CLI, which already classifies correctly — which is exactly why the referenced
run recorded `degraded` rather than a false green.

`llm_review.py` is reached by:
- `plugins/shipwright-adopt/scripts/lib/review_runner.py` (Layer-3 adopt review)
- `shared/scripts/tools/review_assistant_ui_plan.py`
- `plugins/shipwright-build/agents/code-reviewer.md` — a shipped agent prompt
  telling the reviewer subagent to call `run_review`. Found by the doubt review,
  which correctly refuted the "exactly two consumers" claim. Its snippet is
  `uv run -c "…"`, not a valid invocation, so the path is dead in practice; left
  dead deliberately (see disposition 8).

So the fail-open is real and worth fixing, but its blast radius is the **adopt**
Layer-3 gate, not iterate's external review. What iterate suffers is the budget
bug, which fails *loudly* (degraded) and costs review coverage rather than
producing a false pass. Filed severity is unchanged; the affected surface is
corrected.

## Dual-import-name hazard (ADR-045)

`llm_review.py` is imported under **two** module names:
- bare `import llm_review` — adopt, after `sys.path.insert(0, <lib dir>)`
- `from lib.llm_review import ...` — `review_assistant_ui_plan.py:53`

Verified empirically: a bare sibling import inside `llm_review.py` raises
`ModuleNotFoundError` under the `lib.llm_review` name. The fix therefore
tries the bare sibling for adopt and falls back to
`lib.external_review_degraded` only on `ModuleNotFoundError`; the narrow
exception keeps a stale sibling that lacks an imported name loud.

## Acceptance Criteria

- **AC-1** — `run_review` reports provider-declared incomplete replies as
  degraded, not success: truncation plus known abnormal terminal reasons such
  as every current non-success OpenAI reason and every current non-success
  Gemini enum are covered; top-level
  `success` is `False` when every leg is degraded.
- **AC-2** — an empty reply is degraded: stubbed response with `content=""`
  and `finish_reason="stop"` yields `status == "degraded"`.
- **AC-3** — every call site draws its budget from the shared constants: the
  budget kwarg captured from a stubbed client equals `MAX_OUTPUT_TOKENS` at all
  six call sites (`max_tokens` / `max_output_tokens` / `max_completion_tokens`
  as each API requires).
- **AC-4** — the reasoning cap ships on the arm that needed it, and only there:
  `openrouter_extra_body("gemini")` equals
  `{"reasoning": {"max_tokens": REASONING_MAX_TOKENS}}` and
  `openrouter_extra_body("openai")` equals `{}`; for a given `model_key` both
  files pass the same value. *(Narrowed from "both arms" after the code and
  doubt reviews — see disposition 1.)*
- **AC-11** — the two paths and their active consumers wait the same length:
  `DEFAULT_TIMEOUT_SECONDS`, `llm_review.run_review`'s `timeout` default, and
  the shipping config's `llm_client.timeout_seconds` are all equal;
  `review_assistant_ui_plan` uses that constant rather than overriding it.
- **AC-12** — a dropped reasoning cap is machine-readable, not just logged:
  when the direct-Gemini fallback fires, the returned dict carries
  `reasoning_cap_dropped` naming the cause, the aggregate carries a warning,
  and both human review artifacts render it.
- **AC-5** — both direct-Gemini arms send `thinking_config` with
  `thinking_budget == REASONING_MAX_TOKENS`.
- **AC-6** — `llm_review` imports cleanly under BOTH `import llm_review` (with
  the lib dir on `sys.path`) and `from lib.llm_review import run_review` (with
  `shared/scripts` on `sys.path`), each proven in an **isolated subprocess** so
  neither mode can be assisted by the other's `sys.modules` / `sys.path` state;
  a dependency missing inside the sibling is re-raised, not mistaken for the
  sibling itself being absent.
- **AC-7** (drift pin) — the two paths cannot silently diverge: for the same
  provider arm, the kwargs captured from `llm_review` and from
  `external_review` carry the **same** budget and the **same** reasoning cap,
  and both degrade a `finish_reason="length"` reply. Behavioral parity, not a
  source-literal scan.
- **AC-9** — a degraded-only result cannot read as a completed adopt review:
  `review_runner.run_review` returns `status != "completed"` when every leg of
  the underlying result is degraded. One complete leg remains usable, but the
  aggregate carries `partial: true` and warnings rather than representing a
  degraded peer as a clean two-leg pass.
- **AC-10** — the direct-Gemini arm survives a model that rejects
  `thinking_config`: when the first call raises, the arm retries once without
  the reasoning parameter and still returns a classified reply. Eligibility is
  limited to local config incompatibility or HTTP 400; timeout, connection,
  401/403, 429 and 5xx failures never trigger an unbounded retry. If that one
  fallback also fails, its error preserves both attempt failures.
- **AC-8** (empirical, medium+) — a real OpenRouter call against the same
  209k-char prompt with the shipped configuration returns
  `finish_reason == "stop"` with ≥ 8000 visible characters.

## Verification (medium+)

- **Surface:** `cli` — pytest
- **Runner (shared root — AC-1..7 + AC-10):**
  `uv run --extra dev pytest shared/tests/test_external_review_budget.py shared/tests/test_external_review_gemini_budget.py shared/tests/test_external_review_gemini_retry.py shared/tests/test_llm_review_import_modes.py shared/tests/test_llm_review.py shared/tests/test_external_review_openai_param.py shared/tests/test_external_review_reply.py shared/tests/test_review_assistant_ui_plan.py -v`
- **Runner (adopt root — AC-9):** from `plugins/shipwright-adopt/`,
  `uv run --extra dev --with pytest-mock pytest tests/test_review_runner_degraded.py -v`
  — a **second invocation** is required, not a convenience: the repo enforces
  one test root per pytest process (ADR-044), so appending this path to the
  shared-root command aborts with exit 4.
- **Coverage note:** the shared runner covers AC-1..7 and AC-10; AC-9 lives in
  the adopt root and needs the second invocation; AC-8 is empirical and is
  evidenced separately below rather than by pytest. Both runner lines are
  load-bearing — naming only the shared one would let the recorded evidence
  under-report by one AC.
- **Evidence (F0.5 gate):** `.shipwright/runs/<run_id>/surface_verification.json`
  — written by `surface_verification.py`, fixed schema, and **gitignored**, so
  it is local gate evidence and never ships.
- **AC-8 / AC-8b evidence:** the live-provider aggregates live in the run's
  **F5c `live_provider_probe` block** under
  `.shipwright/agent_docs/iterates/<run_id>.json`, which is tracked and ships in
  the PR. They are deliberately *not* in the F0.5
  artifact: that file has a fixed schema this run does not own, and it is
  gitignored, so it could carry neither the fields nor the shipping guarantee.
  The doubt review was right that the earlier wording promised evidence the
  artifact did not contain (doubt 1); this is the correction.
  Aggregates only — `finish_reason`, `reasoning_tokens`, completion tokens,
  visible-char count, elapsed seconds. No prompt, response or credential.

## Out of scope (stated, not forgotten)

- **Direct-OpenAI reasoning control.** `gpt-5.x` exposes `reasoning_effort`
  rather than a token cap. No direct OpenAI key exists in this environment, so
  the knob is unmeasurable here; guessing at it would ship an unverified
  parameter. That arm gets the raised budget only. The brief's own measurement
  (GPT never truncated at 4096) makes this the low-risk arm.
- **Model swap.** Explicitly rejected by the brief and not revisited: Flash
  would fit the ceiling by thinking less (an argument against 4096, not for
  Flash), and GLM would reverse the settled GPT+Gemini decision.
- **`touches_shared_infra` pattern gap.** The detector's patterns are JS-shaped
  (`src/lib/`), so `shared/scripts/lib/` raises nothing in this Python
  monorepo. Observed while scouting this run; filed as an observation, not
  fixed here (it would widen an unrelated gate).

## External plan review — dispositions

Round 1, `openrouter` (gpt-5.6-terra + gemini-3.1-pro-preview), both verdicts
**revise**, 10 findings. Full text in the run's `reviews.json`.

**Accepted and folded into the design:**

1. *(gemini high / openai low)* **Do not mutate `sys.path` inside
   `llm_review.py`** — it is a process-global side effect that can shadow
   unrelated modules for every later import. Both reviewers independently
   proposed a dual-name `try/except ImportError`; adopted, then narrowed to
   `ModuleNotFoundError` after code review so a stale sibling fails loudly.
2. *(openai low)* **Prove each import mode in an isolated subprocess** — a
   same-process test can pass because the other mode already populated
   `sys.modules`. Folded into AC-6.
3. *(gemini low)* **Drop the source-literal scan from the drift pin** — static
   parsing is brittle; captured-kwarg parity covers the same invariant. Folded
   into AC-3 and AC-7.
4. *(openai high)* **Regression-test the adopt consumer boundary** — new AC-9.
   (Tracing already showed adopt maps `success:false` → `skipped` and renders
   per-leg status, so this pins existing-correct behavior rather than fixing a
   defect — worth pinning because the status vocabulary is what changed.)
5. *(gemini medium / openai medium)* **Guard the reasoning kwarg against models
   that reject it** — new AC-10, applied to the direct-Gemini arm only.
   Measured: `openai/gpt-4o-mini`, a non-reasoning model, accepted
   `extra_body={"reasoning": …}` through OpenRouter without error, so the
   OpenRouter arms need no guard. The direct-Gemini arm is unmeasurable here
   (no direct key), so it gets a retry-without-reasoning fallback rather than
   model-name matching, which would rot as model names change.
6. *(openai low)* **Record only aggregates as probe evidence** — no prompt, no
   raw response, no credentials. The probe script stays in the scratchpad and
   is not committed.
7. *(gemini low)* **Confirm the SDK supports `thinking_config`** — already
   verified before planning: `google.genai.types.ThinkingConfig` exposes
   `thinking_budget`. No dependency bump needed.

**Rejected, with reason:**

8. *(openai medium)* **"Treat unknown / missing `finish_reason` as degraded."**
   Declined. `external_review_degraded.py` documents the opposite as a
   deliberate decision from `iterate-2026-07-27-name-the-blocker`: *"An absent
   or unrecognised `finish_reason` is neutral: missing metadata is not evidence
   of truncation"*, because a classifier that guesses will eventually reject a
   real review — and rejecting real reviews is the worse failure. Reversing
   that is a separate, evidence-led decision, not a rider on a budget fix. The
   concrete sub-cases the finding lists that *are* real — `content=None`,
   whitespace-only — are already handled by `classify_reply`'s
   `not (text or "").strip()` guard, and are covered by tests.
9. *(openai medium)* **"Normalize provider response shapes before
   `classify_reply`."** Already satisfied: `openai_finish_reason` /
   `gemini_finish_reason` are the normalizers, and `_normalize_finish_reason`
   already handles google-genai's dotted enum (`FinishReason.MAX_TOKENS`).
   `llm_review.py` will use the same two helpers per arm, exactly as
   `external_review.py` does. Added llm_review-side tests rather than new code.

## External CODE review — dispositions

Run against this run's own 61KB diff via `external_review.py --mode code`.
**This doubled as the live end-to-end proof of the fix:** both legs returned
`status: success` with `degraded: false`, on exactly the workload class that
produced three degraded Gemini legs in the run that filed this bug.

Verdicts contradicted (gemini `approve`, openai `reject`), so the CLI set
`contradiction.requires_resolution = true`. Resolved as follows.

- **openai HIGH ×2 — "unterminated string literal / injected specification
  text" in `external_review.py:108` and `test_external_review_budget.py:108`.
  FALSE POSITIVE, disproven, not waived.** The reviewer mistook the prompt's
  own concatenation (`{DIFF}` followed by `{SPEC}`) for document text injected
  into the source files. Evidence: `python -m py_compile` parses all five
  touched Python files; line 108 of `external_review.py` is docstring prose
  inside `_render_user_prompt`, and line 108 of the test is an ordinary
  `review_with_openrouter(...)` call; ruff is clean and the tests collect and
  pass (64 in the shared root). A syntax error of the kind described would
  make all three impossible.
- **openai MEDIUM — AC-8's live-provider evidence is asserted in this spec but
  not present as a verification artifact. ACCEPTED.** The aggregate metrics are
  recorded in the tracked, run-specific F5c entry under
  `.shipwright/agent_docs/iterates/<run_id>.json` (aggregates only — no prompt,
  response or credential), so the claim survives Snapshot restore and ships.
- **gemini — `approve`, no actionable findings.** Recorded, but weighted for
  what it is: a 353-character reply that names no specific risk. It completed
  (`finish_reason=stop`, not degraded), so this is reviewer shallowness, not
  truncation — worth stating plainly rather than counting as corroboration.

## Code-review cascade — dispositions

`spec-reviewer` REJECT → fixed → **APPROVE**; `code-reviewer` **approve with
changes**; `doubt-reviewer` **advisory — proceed after addressing**. All three
sets are answered below. Three of them changed shipped behavior.

**Changed the code:**

1. *(code-review medium; doubt C3 — refuted)* **The reasoning cap no longer
   ships on the GPT arm.** I had sent it to both OpenRouter arms. Measured
   `gpt-5.6-terra` with and without it (reasoning 1235 vs 1220, 33 findings
   both, `stop` both) — but as the doubt pass pointed out, that proves the cap
   was *non-binding on that prompt*, not that it is harmless where GPT wants
   more than 2000. Since GPT never truncated at 4096, the cap buys that arm
   nothing and risks an effort-tier downgrade on the fleet's highest-yield
   pass. `openrouter_extra_body(model_key)` now returns `{}` for it.
2. *(doubt C4 — REFUTED outright)* **The coupled-pair invariant was wrong.**
   `MAX_OUTPUT_TOKENS >= REASONING_MAX_TOKENS * 4` is scale-invariant, but the
   failure is absolute: `(4096, 1024)` satisfies it and reproduces the original
   truncation exactly. Replaced with the mechanism the measurements support —
   the total must absorb a 3.5×-overshot cap *plus* a full answer — and a
   meta-test asserting the constructed bug values are rejected. That meta-test
   then caught a second error of mine: the constant block claimed "raising the
   cap to 4000 stays safe at 16000", and it does not (16000 − 14000 = 2000,
   below the ~3500 an answer needs). Both the test and the comment are fixed.
3. *(doubt 5 — validated by new measurement)* **`timeout_seconds` raised
   120 → 240**, and `llm_review.run_review`'s default with it. Raising the
   output budget 4× raised generation time: measured 89.2s for a 10500-token
   completion, i.e. only 30.8s of headroom under the old 120s. Shipping the
   bigger budget under the old timeout would have converted a *partial* review
   into *no* review — the same failure in a new costume. A drift test now pins
   the default to the shipping config, closing a parity gap the doubt pass
   found (the two paths derive the timeout differently and neither was
   asserted).

**Changed the record, not the code:**

4. *(doubt 8)* **The "~96% of any ceiling" claim was over-stated** and is now
   restated as what was measured: reasoning consumed essentially the whole
   ceiling *on both uncapped runs*. The 96% figure was computed against
   completion tokens on two runs that were both truncated, where it is close to
   tautological — and the third row (3332 of 6986 = 48%) contradicts the
   general form. A third data point also showed the cap producing **6909**
   reasoning tokens at the same cap of 2000, so the honest characterisation is
   "weak cap, 1.7×–3.5× overshoot, 2× run-to-run variance", not a scaling law.
5. *(code-review medium; doubt 3)* **`gemini_generate` now returns
   `(response, note)`** and both callers merge `reasoning_cap_dropped` into the
   reply, so a dropped cap survives into `reviews.json` / `review.md`. A stderr
   line alone was invisible to every machine-readable consumer — which
   contradicted this module's own charter.
6. *(code-review low)* **`except ImportError` → `except ModuleNotFoundError`**
   in `llm_review`. The broader form also swallowed "cannot import name
   gemini_generate", i.e. a partially-stale plugin-cache sibling, and would
   silently retry under the other module name instead of failing loudly.
7. *(code-review low)* **`review_assistant_ui_plan.py` regression fixed.** It
   printed a body only for `status == "success"`, so a degraded leg's partial
   text — which `classify_reply` deliberately preserves — was dropped. Before
   this change that text arrived as `success` and *was* rendered, so my change
   caused the regression.
8. *(doubt C5 — refuted)* **A third consumer exists.**
   `plugins/shipwright-build/agents/code-reviewer.md` instructs the reviewer
   subagent to call `from lib.llm_review import run_review`. The consumer list
   above is corrected. I am deliberately **not** repairing that snippet: it is
   written as `uv run -c "…"`, which is not a valid invocation, so the path is
   dead. Making dead code live is a behavior change nobody asked for and one I
   cannot test here; filed as an observation instead.
9. *(code-review low)* **A model override now carries a 16000-token output
   requirement.** `SHIPWRIGHT_REVIEW_MODEL_*` applies no validation, so pointing
   an arm at a model with an 8192 ceiling may 400. That fails loudly
   (`status: error` → degraded → non-zero exit), not silently, so it is
   recorded rather than guarded — adding a budget-reduction fallback for an
   unmeasured scenario is speculative complexity.

**Superseded by the doubt pass:** the first code-review disposition accepted a
broad `gemini_generate` retry. The final implementation instead separates local
config construction from the provider call and retries the latter only on an
explicit HTTP 400. End-to-end tests pin non-retry on timeout and preservation
of both errors when the single fallback fails. Tests for the old-SDK fallback,
client timeout in milliseconds, and real-SDK config shape close the low items.

## Confidence Calibration

- **Boundaries touched:** the OpenRouter / Gemini / OpenAI API boundary (request
  parameters and response-metadata reading); the `llm_review` → `adopt` return
  contract (a new `degraded` status value); the dual-name module-import boundary.
- **Empirical probes run:**
  - *Reproduce the bug (4096, no cap):* `finish_reason=length`, 3928/4092
    reasoning (96%), **621** visible chars — cut mid-sentence. `llm_review`
    would have called it `success`.
  - *Falsify "raise the budget" as a standalone fix (16000, no cap):*
    `finish_reason=length`, 15360/15996 reasoning (**still 96%**), 2352 visible
    chars. Finding: raising the budget alone failed on both measured uncapped
    runs. Two points do not distinguish scaling demand from demand that simply
    exceeds both ceilings; either way this changed the design.
  - *Does the reasoning cap bind? (16000, cap 2000):* `finish_reason=stop`,
    3332 reasoning — **the cap overshot by 1.7×**. Finding: it is a soft hint,
    so the total must keep margin; the two numbers are a coupled pair.
  - *Does the reasoning field break a non-reasoning model?* `openai/gpt-4o-mini`
    via OpenRouter accepted `extra_body={"reasoning": …}` and returned normally.
    Finding: the OpenRouter arms need no model guard; only the unmeasurable
    direct-Gemini arm gets a fallback.
  - *Dual-import hazard:* a bare sibling import inside `llm_review.py` raises
    `ModuleNotFoundError` under the `lib.llm_review` name. Finding: confirmed
    the ADR-045 trap before writing the import, not after.
  - **AC-8, after the fix, shipped constants:** `finish_reason=stop`, 3791
    reasoning, 7500/16000 completion tokens, **14134** visible chars,
    `classify_reply → success`. Visible review grew **22.8×** (621 → 14134).
  - *Does the cap hurt the GPT arm? (AC-8b, `gpt-5.6-terra`, same prompt):*
    without cap 1235 reasoning / 22008 chars / 33 findings; with cap 1220 /
    21613 / 33; `stop` both. Finding: non-binding **on this prompt** — which is
    why the cap was then scoped OFF that arm rather than kept (a prompt where
    GPT wants >2000 was never tested, and could not be cheaply).
  - *Does the raised budget survive production's timeout?* Same prompt at the
    **production** 120s client timeout: 89.2s elapsed, 10500 completion tokens,
    `stop` — only **30.8s of headroom**. Finding: the 4× budget raise pushed
    latency to 74% of the old timeout, so `timeout_seconds` went 120 → 240.
    Without this the fix would have traded truncation for timeouts.
  - *How reliable is the cap?* Across three capped runs at cap 2000, reasoning
    came back **3332, 3791 and 6909** — 1.7×–3.5× overshoot, 2× variance.
    Finding: the cap is weak, so the total must absorb a multiple of it. This
    is what refuted the ratio-based invariant.

- **Test Completeness Ledger:** every behavior this diff introduces or changes,
  each `tested` or `untestable` — 0 testable-but-untested.

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | OpenRouter arm (llm_review) sends the shared budget and provider-scoped reasoning config | tested | `test_openrouter_arms_agree_on_budget_and_cap` |
  | 2 | OpenRouter arm (external_review) sends the same budget and provider-scoped config | tested | same test — parity asserted across both |
  | 3 | Direct-OpenAI arm (llm_review) uses `max_completion_tokens` | tested | `test_direct_openai_arms_agree_on_budget`, `test_llm_review_openai_uses_max_completion_tokens` |
  | 4 | Direct-OpenAI arm (external_review) uses the same | tested | `test_direct_openai_arms_agree_on_budget`, `test_review_with_openai_uses_max_completion_tokens` |
  | 5 | Direct-Gemini arms send `max_output_tokens` + `thinking_budget` | tested | `test_direct_gemini_arms_send_thinking_budget` |
  | 6 | A truncated reply is `degraded`, not `success` (both paths) | tested | `test_both_paths_degrade_a_truncated_reply` |
  | 7 | An empty reply is `degraded` (both paths) | tested | `test_both_paths_degrade_an_empty_reply` |
  | 8 | A complete reply is still `success` (no over-correction) | tested | `test_a_complete_reply_is_still_a_success` |
  | 9 | `run_review` aggregate `success` is False when all legs degrade | tested | `test_run_review_success_is_false_when_every_leg_is_degraded` |
  | 10 | Both google-genai finish-reason renderings degrade — `.name` (bare) AND the dotted `FinishReason.MAX_TOKENS` that exercises the normalizer's `rsplit(".")` branch | tested | `test_direct_gemini_degrades_a_truncated_reply[named]` and `[dotted]` (parametrized; the `named` case alone left the dotted branch unexercised — spec-reviewer finding 5) |
  | 11 | Direct-Gemini retries once without `thinking_config` on rejection | tested | `test_direct_gemini_retries_without_reasoning_when_model_rejects_it` |
  | 12 | Retry keeps the budget, drops only the reasoning knob | tested | same test (asserts call 2's `max_output_tokens`) |
  | 13 | `llm_review` imports as a bare module (adopt path) | tested | `test_llm_review_imports_as_a_bare_module` (subprocess) |
  | 14 | `llm_review` imports as `lib.llm_review` (review_assistant path) | tested | `test_llm_review_imports_as_lib_llm_review` (subprocess) |
  | 15 | Budget and cap remain a coupled pair | tested | `test_budget_leaves_room_for_an_overshot_cap_plus_a_full_answer` |
  | 16 | `openrouter_extra_body(model_key)` payload shape | tested | `test_extra_body_caps_only_the_arm_that_needed_it` |
  | 17 | adopt: a degraded-only review is not `completed` | tested | `test_degraded_only_review_is_not_completed` |
  | 18 | adopt: degraded status is visible in `review.md` | tested | `test_degraded_status_is_visible_in_the_written_review` |
  | 19 | adopt: a real review still completes | tested | `test_a_real_review_still_completes` |
  | 20 | The cap ships on gemini and NOT on the openai arm | tested | `test_extra_body_caps_only_the_arm_that_needed_it` |
  | 21 | The budget/cap pair leaves room for a 3.5×-overshot cap plus a full answer | tested | `test_budget_leaves_room_for_an_overshot_cap_plus_a_full_answer` |
  | 22 | That invariant rejects the values that reproduce the bug, in both directions | tested | `test_the_invariant_rejects_the_values_that_reproduce_the_bug` (meta-test; it caught a wrong claim in the constant block) |
  | 23 | Both paths, every provider fallback, active consumers, and the shipping config agree on the timeout | tested | `test_default_timeout_matches_shipping_config`, `test_external_review_openai_clients_default_to_shared_timeout`, `test_direct_gemini_client_carries_a_bounded_timeout`, `test_degraded_review_keeps_reason_and_partial_body` |
  | 24 | Both direct-Gemini clients bound the call, in milliseconds | tested | `test_direct_gemini_client_carries_a_bounded_timeout` |
  | 25 | A dropped reasoning cap reaches the caller as data, not just stderr | tested | `test_direct_gemini_retries_without_reasoning_when_model_rejects_it` (asserts `reasoning_cap_dropped`) |
  | 26 | An old SDK without `ThinkingConfig` still returns a review | tested | `test_an_old_sdk_without_thinking_config_still_reviews` |
  | 27 | A missing `google-genai` is reported, not swallowed | tested | `test_missing_google_genai_is_reported_not_swallowed` |
  | 28 | The two import modes resolve genuinely distinct module names | tested | `test_the_two_modes_resolve_distinct_module_names` |
  | 29 | The real SDK accepts the config shape we send (rename guard) | tested | `uv run --project plugins/shipwright-plan --extra dev pytest shared/tests/test_external_review_gemini_budget.py::test_real_sdk_accepts_the_config_shape_we_send` PASSED; the ordinary shared-root run still records the expected dependency-gated skip. |
  | 30 | Live provider honours the shipped config end-to-end | untestable — `requires-external-nondeterministic-service` | Not a repeatable assertion (paid, non-deterministic, network-dependent). Compensating control: measured explicitly as AC-8 / AC-8b and recorded above; the deterministic half is covered by rows 1–2. |
  | 31 | `review_assistant_ui_plan` renders a degraded leg's reason and partial body | tested | `test_degraded_review_keeps_reason_and_partial_body` |
  | 32 | Known abnormal provider terminal reasons never count as success | tested | `test_known_abnormal_finish_reasons_are_degraded` |
  | 33 | Auth, rate-limit, server, connection and timeout errors never retry unbounded | tested | `test_only_http_400_is_a_provider_retry_signal`, `test_network_timeout_is_not_retried` |
  | 34 | One usable leg remains usable but the aggregate is explicitly partial | tested | `test_one_usable_leg_keeps_success_but_marks_the_result_partial` |
  | 35 | A dropped reasoning cap is visible in both human artifacts and aggregate warnings | tested | `test_degraded_review_keeps_reason_and_partial_body`, `test_a_real_review_still_completes` |
  | 36 | A failed direct-Gemini fallback preserves both attempt errors | tested | `test_failed_fallback_preserves_both_attempt_errors` |
  | 37 | A nested missing dependency is not mistaken for the sibling module being absent | tested | `test_nested_module_not_found_is_not_mistaken_for_the_sibling` |

## Final Codex doubt-review dispositions

The post-handoff doubt pass blocked on two remaining fail-open paths and four
durability/visibility gaps. All must-address findings were resolved:

1. **Known abnormal finish reasons — fixed.** `content_filter`, Gemini safety
   and related terminal reasons now degrade while missing and genuinely unknown
   metadata remain neutral.
2. **Broad Gemini retry — fixed.** Local config-shape failures and HTTP 400 may
   retry without reasoning; 401/403, 429, 5xx, timeout and connection failures
   re-raise. A failed fallback reports both attempts.
3. **Fallback visibility — fixed.** Per-leg notes render in adopt and the
   assistant-plan artifact; `run_review` also emits aggregate `warnings`.
4. **Partial-success policy — explicit.** One complete leg keeps the review
   usable, but `partial: true` records degraded peers or a dropped cap.
5. **180-second consumer override — fixed.** The consumer uses
   `DEFAULT_TIMEOUT_SECONDS`, behaviorally captured by its test.
6. **Adopt-root durability — fixed.** Its separate command, exit code, count and
   timestamp are stored in F5c under `additional_test_runs`.
7. **Model override ceiling — accepted limitation.** An incompatible override
   fails loudly; no unmeasured budget downgrade is added.
8. **Dual-name fallback — narrowed.** The fallback checks `exc.name`, so a
   future nested missing dependency re-raises rather than binding another copy.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the probes stopped changing the answer — the third one
    and the AC-8 re-run agree (`stop`, ~3300–3800 reasoning, 13.4k–14.1k visible
    chars). The mechanism is measured at the API boundary rather than inferred:
    `reasoning_tokens` is read from the provider's own usage block.
  - *Coverage (breadth):* all six call sites are asserted, in both files, across
    all three provider arms — not only the live OpenRouter one. Both import
    modes are proven in isolated subprocesses so neither can pass on the other's
    leftovers. The consumer whose status vocabulary changed (adopt) is pinned at
    its own boundary.
  - *Integration composition:* the diff-driven detectors return False for
    `cross_component` on this file set (no merge/churn/event-log resolver, no
    hook, no phase validator, no campaign driver), so no `category:"integration"`
    behavior is owed. Re-checked against the real diff at F11 rather than
    assumed from the planned file list.
  - *Known blind spot, stated:* the direct-OpenAI arm's reasoning is not bounded
    (only its total), because `gpt-5.x` exposes `reasoning_effort` rather than a
    token cap and no direct OpenAI key exists here to measure it. That arm has
    never been observed truncating at 4096, so raising it to 16000 strictly
    widens its headroom — but this is an untested widening, not a verified fix,
    and is recorded as such.
