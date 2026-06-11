# Iterate Spec — Tier-3 PR Review (B4.5 Phase 2, Step 4)

- **Run ID:** `iterate-2026-06-11-automerge-pr-review`
- **Branch:** `iterate/automerge-pr-review`
- **Intent:** FEATURE
- **Complexity:** medium (keyword-sourced; confidence 0.7)
- **Risk flags:** `touches_io_boundary` (OpenRouter JSON response + env-var parsing in
  `pr_review.py`), sensitive path `.github/workflows/` (repo's own workflow)
- **Spec source:** `Spec/early-access-readiness-plan.md` § B4.5 → "Components — was committed wird"
- **Triage anchor:** `trg-52cd3143` (Phase 2 Step 4)

## Context

B4.5 activates GitHub-native auto-merge with a **proportional-to-risk** review model.
Tier 1 (iterate-branch PRs) and Tier 2 (Sven's manual PRs) get **no** API review at the
PR stage — `/shipwright-iterate` Step 8 already runs the `iterate_reviewer` subagent in
the local Claude subscription, so a second API review would pay for the same judgment
twice. Only **Tier 3** (external contributor OR sensitive paths OR label `needs-review`)
gets an OpenRouter LLM review via a custom script.

Phase 1 (loop-closing `gh-pr-ci` producer) already shipped in PR #191 (commit f9cf3624).
Phase 3 (auto-merge activation, branch protection, the F11 `--auto` patch) are **separate**
out-of-scope follow-ups. This iterate is Phase 2 Step 4: the Tier-3 review *components*.

## Scope (this iterate ONLY)

1. `.github/workflows/pr-review.yml` — thin wrapper; tier filters in the `decide` job,
   review logic in the Python script. Required-check job name **`PR Review`**.
2. `plugins/shipwright-security/scripts/tools/pr_review.py` — custom script (~150 LOC):
   fetch PR diff (`gh pr diff`), call OpenRouter (`/chat/completions`,
   `response_format: json_object`), post a PR comment + review state, exit-code per decision.
3. `shared/prompts/pr_reviewer/{system,user}` — prompt files (directory form, analog to
   `code_reviewer/`, `iterate_reviewer/`), tuned for external-contributor context + strict
   JSON output.
4. Two snapshot tests:
   - `plugins/shipwright-security/tests/test_pr_review_workflow_shape.py`
   - `plugins/shipwright-security/tests/test_pr_review_script.py`

## Out of scope (explicit)

- OpenRouter dedicated CI key + `OPENROUTER_API_KEY` repo secret (manual, Phase 2 steps 2-3)
- Smoke tests (Phase 2 steps 5-6 — need a live repo + live key)
- `gh pr merge --auto` F11 patch (Phase 3 Step 9 — separate iterate, `trg-bdc160e2`)
- Branch-protection / repo auto-merge settings (manual UI)
- Fork-PR reviews: forks have no secret access; the `decide` job is fork-guarded, so the
  `review` job does not run on fork PRs. Documented as a known limitation (handled manually
  during Early Access). Not solved in this iterate.

## Acceptance Criteria

- **AC1** — `pr_review.py` fetches the PR diff, calls OpenRouter with the system+user prompts,
  parses the strict-JSON decision, and posts a rendered PR comment.
- **AC2** — Exit codes: `0` for decision `approve`/`comment`, `1` for `block`, `2` for any
  error (OpenRouter down/rate-limited, JSON parse failure, unknown decision).
- **AC3** — JSON-parse failure dumps the raw response to logs (redacted) and exits 2.
- **AC4** — A diff `> 200_000` chars is truncated; truncation is recorded and the run does
  **not** auto-block (comment-state + ⚠️ warning in the body, exit 0) per spec.
- **AC5** — The OpenRouter API key is never written to logs (redaction helper).
- **AC6** — `pr-review.yml` exists with: fork-PR guard, the four tier rules in `decide`
  (`skip-pr-review`, `needs-review`, sensitive paths, external author), job name `PR Review`,
  `needs: decide` + `if: needs.decide.outputs.needs_review == 'true'`, `secrets.OPENROUTER_API_KEY`
  (no literal key, no `ANTHROPIC_API_KEY`), and it calls `pr_review.py` (not a 3rd-party action).
- **AC7** — The workflow is Semgrep-clean: no `${{ github.* }}` interpolated directly into a
  `run:` body (run-shell-injection); third-party actions SHA-pinned.

## Mini-Plan + Alternative

**Chosen — stdlib `urllib.request` for the OpenRouter POST.** Self-contained, zero new
dependency, env-agnostic under `uv run`, and trivially mockable (tests monkeypatch a single
`_post_openrouter` boundary function). On-brand for a security plugin minimizing its dep surface.

**Alternative considered — reuse `openai` SDK (mirror `shared/scripts/lib/llm_review.py`).**
Rejected: adds a heavyweight dep to the env the CI script resolves, couples a security tool to
the SDK, and is harder to unit-test offline. The spec's pseudocode already describes a raw POST.

## Affected Boundaries

- **OpenRouter HTTP** (`/chat/completions`) — request build + response JSON parse.
- **Environment variables** — `OPENROUTER_API_KEY`, `SHIPWRIGHT_PR_REVIEW_MODEL`, `GH_TOKEN`.
- **`gh` CLI subprocess** — `gh pr diff`, `gh pr comment`, `gh pr review`.
- **Prompt files** — `shared/prompts/pr_reviewer/{system,user}` (read).
- **GitHub Actions YAML** — `.github/workflows/pr-review.yml` (the `decide` tier contract).

## Confidence Calibration

- **Boundaries touched:** OpenRouter HTTP request/response JSON; env vars
  (`OPENROUTER_API_KEY`, `SHIPWRIGHT_PR_REVIEW_MODEL`, `GH_TOKEN`); `gh` CLI subprocess;
  prompt-file read; the `decide`-job tier contract in workflow YAML.
- **Empirical probes run** (5, all passed — see build log):
  1. Request payload serializes to valid JSON with the user-template filled (`{PR_META}`/`{DIFF}`).
  2. OpenRouter response envelope → `content` → `parse_review_response` round-trips to the
     same object; `block` → exit 1; rendered comment contains the summary + 🔴 BLOCK badge.
  3. Env model default (`anthropic/claude-sonnet-4.6`) vs override (`openai/gpt-5-codex`).
  4. Truncation boundary: `== MAX_DIFF_CHARS` → not truncated; `+1` → truncated, len ≤ cap.
  5. Malformed (rate-limit HTML) response → `ValueError`; redaction strips the key token.

### Test Completeness Ledger (testable ⇒ tested; 0 testable-but-untested)

| Behavior (AC) | Disposition | Evidence |
|---|---|---|
| Redaction never logs key (AC5) | tested | `test_pr_review_lib::TestRedaction` (3) + `test_script::test_api_key_never_logged` |
| decision → exit-code (AC2) | tested | `TestDecisionToExit` (5) + 4 `TestMainOrchestration` exit tests |
| strict-JSON parse + parse-fail dump (AC3) | tested | `TestParseResponse` (4) + `test_json_parse_fail_exits_2_and_dumps_raw` |
| diff truncation, no auto-block (AC4) | tested | `TestTruncation` (3) + `test_truncation_forces_exit_0_even_on_block` |
| comment rendering (decision/summary/lists/warning) | tested | `TestRenderComment` (4) |
| prompt load + message build (AC1) | tested | `TestPromptLoadingAndMessages` (3) |
| OpenRouter request build — URL/auth/response_format (AC1) | tested | `TestPostOpenRouter` |
| OpenRouter content extract + HTTP/URL error wrap | tested | `TestCallOpenRouter` (4) |
| `gh` diff/comment/review wrappers + exit handling | tested | `TestGhWrappers` (5) |
| `main()` all exit paths (AC1/2/3/4/5) | tested | `TestMainOrchestration` (8) |
| workflow tier contract + hardening (AC6/AC7) | tested | `test_pr_review_workflow_shape` (16) |
| Live OpenRouter API call (real network) | untestable: `requires-external-nondeterministic-service` | Phase 2 smoke-test 6 (manual, out of scope) |
| Live `gh` post to a real PR | untestable: `requires-prod-credential` | Phase 2 smoke-test 6 (manual) |
| `decide`-job bash tier logic on a real GitHub runner | untestable: `requires-external-nondeterministic-service` | structurally covered by the snapshot; Phase 2 smoke-tests 5-6 (manual) |
| Skipped-job → required-check-green behavior | untestable: `requires-external-nondeterministic-service` | open question; Phase 2 smoke-test 5 (manual) |

- **Confidence-pattern check:**
  - *Asymptote (depth):* went past "looks right" by adding direct tests for every I/O wrapper
    and an out-of-band 5-probe round-trip. Remaining unknowns are purely GitHub-runtime
    (skipped-job-green, live API) — genuinely external, flagged as the spec's open questions.
  - *Coverage (breadth):* all 7 ACs have tests; happy + error paths covered; the full tier
    matrix (skip label, force label, sensitive path, external author, internal-skip) is in the
    workflow snapshot. 60 new tests; full plugin suite 396→ green (3 binary-smoke skips).
