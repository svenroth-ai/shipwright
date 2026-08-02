# Mini-Plan — External review: truncation guard + reasoning budget

- **run_id:** `iterate-2026-08-01-llm-review-truncation-guard`
- **Spec:** `.shipwright/planning/iterate/2026-08-01-llm-review-truncation-guard.md`

## Chosen values (empirically derived, not guessed)

```
MAX_OUTPUT_TOKENS    = 16000
REASONING_MAX_TOKENS = 2000
```

Measured on a 209,549-char prompt against `google/gemini-3.1-pro-preview`:
this pair produced `finish_reason=stop`, 3332 reasoning tokens and 13448
visible chars, using 6986 of 16000 — better than 2× headroom. The two numbers
are **coupled**: the cap overshoots ~1.7×, so the total must stay well above
`cap + expected answer`.

## Files to create / modify

| File | Change |
|---|---|
| `shared/scripts/lib/external_review_degraded.py` | EDIT — add the two budget constants, `openrouter_extra_body()`, and `gemini_generate()` (the shared direct-Gemini call carrying the thinking budget + the AC-10 retry), with the measured table as the rationale comment |
| `shared/scripts/lib/llm_review.py` | EDIT — dual-name `try/except ModuleNotFoundError` sibling import; route all 3 arms through `classify_reply`; budgets/timeouts from constants; Gemini-scoped reasoning cap; document both live import names in the docstring |
| `shared/scripts/tools/external_review.py` | EDIT — budgets and timeout fallbacks from constants; Gemini-scoped reasoning cap on OpenRouter + direct-Gemini arms |
| `shared/tests/test_llm_review.py` | EDIT — `4096` → constant; add degraded-classification + dual-import tests |
| `shared/tests/test_external_review_openai_param.py` | EDIT — `4096` → constant (Test-Update-Klausel) |
| `shared/tests/test_external_review_budget.py` | NEW — the cross-path drift pin (AC-1..4, AC-7); F0.5 `cli` runner target |
| `shared/tests/test_external_review_gemini_budget.py` | NEW — direct-Gemini thinking budget + retry fallback + the dual-import contract (AC-5, AC-6, AC-10). Split from the file above to stay inside the 300-LOC limit |
| `shared/tests/test_external_review_gemini_retry.py` | NEW — only local config incompatibility / HTTP 400 may drop the cap; timeout, auth, rate-limit and server failures do not retry |
| `shared/tests/test_review_assistant_ui_plan.py` | NEW — degraded text, fallback warning, and shared timeout rendering contract |
| `plugins/shipwright-adopt/tests/test_review_runner_degraded.py` | NEW — the adopt consumer boundary (AC-9). Separate pytest root: needs its own invocation from the plugin's cwd |

## Work breakdown

1. **Constants + helper** in `external_review_degraded.py`.
   *Test:* importing the module exposes both ints and
   `openrouter_extra_body("gemini") == {"reasoning": {"max_tokens": 2000}}`
   while `openrouter_extra_body("openai") == {}`.
2. **`llm_review.py` import wiring** — ~~anchor `os.path.dirname(__file__)` onto
   `sys.path` (guarded)~~ **SUPERSEDED by spec disposition 1**: both external
   plan reviewers flagged `sys.path` mutation as a process-global side effect.
   Shipped instead as `try: from external_review_degraded import … / except
   ModuleNotFoundError: from lib.external_review_degraded import …`, then import
   `classify_reply` + the budget constants.
   *Test:* AC-6 — module imports under BOTH `import llm_review` and
   `from lib.llm_review import run_review`.
3. **`llm_review.py` OpenRouter arm** — `max_tokens=MAX_OUTPUT_TOKENS`,
   `extra_body=openrouter_extra_body(model_key)`, return `classify_reply(...)`.
   *Test:* AC-1 (`finish_reason="length"` → degraded), AC-4 (extra_body).
4. **`llm_review.py` Gemini + OpenAI arms** — budgets from constants,
   `thinking_config` on Gemini, `classify_reply` on both.
   *Test:* AC-2 (empty → degraded), AC-5 (`thinking_budget`).
5. **`external_review.py`** — same six-site treatment; it already calls
   `classify_reply`, so budget, timeout fallback and provider-scoped reasoning config change.
   *Test:* AC-3/AC-4/AC-5 assertions against captured kwargs.
6. **Drift pin** — ~~asserts both source files carry no budget literal~~
   **SUPERSEDED by spec disposition 3**: static source parsing is brittle.
   `test_external_review_budget.py` instead asserts captured-kwarg parity —
   same budget and same cap from both implementations — and that both classify
   through `classify_reply`.
   *Test:* AC-7; mutation-check by re-introducing a literal locally.
7. **AC-8 re-measurement** — re-run the probe with the shipped configuration
   and record `finish_reason` + `reasoning_tokens` in the spec.

## Test strategy

- Unit: stubbed provider clients capturing `create()` kwargs (the existing
  `_make_fake_openai` idiom in both test files, monkeypatched **by module
  object** per ADR-045).
- Drift: behavioral parity over captured kwargs from both implementations,
  plus an assertion that both paths degrade a truncated reply. (No source-level
  scan — dropped per spec disposition 3.)
- Empirical: one real OpenRouter call before (recorded) and one after (AC-8).
- No E2E/browser layer — no UI surface. F0.5 surface = `cli`.

## Alternative approach considered — and why rejected

**Expose the budget as two keys in `shared/config/external_review.json`
(`llm_client.max_output_tokens`, `llm_client.reasoning_max_tokens`),** read by
both paths, mirroring the existing `timeout_seconds` knob.

Rejected for two reasons:

1. **The two numbers are coupled, and config makes them look independent.** The
   cap only works because the total keeps margin above it; an operator setting
   `reasoning_max_tokens: 15000` alongside `max_output_tokens: 16000` would
   silently recreate the exact bug being fixed, with no gate to catch it. A
   measured pair in code, pinned by a drift test, cannot be misconfigured.
2. **It widens `llm_review.py`'s import surface.** That module deliberately
   takes no config; adding a config loader puts another import on the adopt
   Layer-3 path, which is the path that carries the dual-import-name hazard
   documented in the spec. The fix already needs exactly one new import edge —
   this alternative would make it two, for a knob nobody has asked for (YAGNI).

If per-environment tuning is ever genuinely needed, the precedent already
exists (`SHIPWRIGHT_REVIEW_MODEL_*` env overrides) and can be added then
without re-litigating the default.
