# Mini-Plan: Codex CLI as an internal-review-cascade transport

## Chosen approach

Add a new tier literal `"codex"` to `shared/schemas/model_config.schema.json`
and `model_tier_config.TIERS`, valid only for the `review`/`plan_review`
roles. `agent_model_param()` keeps returning the raw tier string; it is the
**caller** (skill prose in `build`'s `code-review.md` and `iterate`'s
`iteration-reviews.md`) that must branch on it — `"codex"` is not a legal
Agent-tool `model` value, so a resolved `"codex"` skips the `Task(...)` spawn
entirely and instead invokes a new script, e.g.
`shared/scripts/tools/review_via_codex.py --role spec|code|doubt|plan
--spec-file <path> --diff-file <path> --worktree-root <path>`.

That script is modeled directly on `review_codex()` in
`shared/scripts/lib/external_review_default_legs.py`, reusing
`_resolve_codex_binary()` / `is_codex_available()` / `codex_settings()`
as-is (already transport-agnostic — nothing in them assumes the scratch-dir
isolation), but differs in three deliberate ways:

1. **`--cd` targets the real worktree root**, not a fresh empty scratch
   directory. This is the whole point of the exercise: Opus-parity repo
   exploration. `--sandbox read-only` still applies, so Codex can read
   anything in the worktree but write nothing.
2. **`--output-schema <role>.json` replaces the `SHIPWRIGHT_VERDICT`
   sentinel contract.** The internal reviewers' existing output shapes are
   structured JSON (findings arrays, spec citations, doubt lists), not a
   single approve/reject line — `classify_reply()`/`review_verdict.py`'s
   sentinel parser does not apply here. `--output-schema` was empirically
   proven this session to (a) enforce OpenAI's strict-schema requirement —
   `additionalProperties: false` on every nested object, discovered via a
   real rejected call — and (b) produce a correct, schema-conformant verdict
   from a model that had genuinely read the target files itself.
3. **A new, independently locked model identity**, not the external review's
   `models.codex` (`gpt-5.6-terra`). Sven's explicit requirement: the two
   use cases may diverge, so a second binding —
   `models.codex_internal_review = "gpt-5.6-sol"` in
   `shared/config/external_review.json` (or a new sibling config; naming
   TBD at build time) — sits beside the existing one, both locked
   independently via the same `resolve_reviewer_model`-style anti-drift
   mechanism (raise before launching a process if a configured value
   disagrees with the code-owned binding).

Three JSON Schema files (`spec_reviewer_output.schema.json`,
`code_reviewer_output.schema.json`, `doubt_reviewer_output.schema.json`,
exact location TBD — likely beside the agent `.md` files or under
`shared/schemas/`) mirror each agent's existing documented output shape
verbatim (see `plugins/shipwright-build/agents/{spec-reviewer,code-reviewer,
doubt-reviewer}.md`), each strict-mode compliant per the probe finding above.

Fallback: `is_codex_available()` returning `False` degrades the resolved tier
to `"inherit"` (ordinary Agent-tool spawn) with a recorded reason — never a
hard failure — matching `resolve_openai_route`'s existing precedent for the
external-review leg.

## Empirical verification (run this session, 2026-09-13)

1. **Model access.** `codex exec -m gpt-5.6-sol --skip-git-repo-check
   --sandbox read-only --ephemeral --ignore-user-config --ignore-rules --cd
   <scratch> -o <file>` (the existing leg's exact flag set) against Codex CLI
   v0.147.0, logged in via ChatGPT: exit 0, real response
   (`SHIPWRIGHT_VERDICT: approve`), session ID assigned.
2. **Validation sanity check.** The same call with `-m
   definitely-not-a-real-model-xyz123`: exit 1, a real OpenAI 400
   `invalid_request_error` ("model is not supported"), proving `-m` is
   genuinely checked against the account's real model list rather than
   silently substituted — the positive result in (1) is trustworthy.
3. **Real-repo access + structured output.** Built a fake two-file "repo"
   (`spec.md` with two ACs, `diff.txt` implementing only one) and a strict
   JSON schema. First call failed with a real, informative 400 naming the
   exact missing `additionalProperties: false` at a nested level — fixed the
   schema. Re-ran: Codex's own tool-call log showed it running
   `Get-Content -Raw spec.md; Get-Content -Raw diff.txt` inside the target
   directory (genuine live file access, not just the piped prompt) and
   returned `{"stage":"spec-compliance-review","verdict":"REJECT",
   "spec_citations":[{"spec_ref":"AC-2","divergence":"..."}]}` — correct,
   schema-conformant, and semantically right (the diff genuinely does not
   implement AC-2).

This closes the two biggest open risks from the prior conversation: whether
`gpt-5.6-sol` is real/accessible, and whether Codex can be given real
repo-read access with enforced structured output shaped exactly like an
existing internal reviewer's contract.

## Alternatives considered and rejected

**Reuse the external review's exact `review_codex()` / `SHIPWRIGHT_VERDICT`
sentinel contract unmodified for internal review too.** Rejected: internal
reviewers need structured, multi-field JSON (findings arrays with
file/line/severity, spec citations, doubt lists) that a single sentinel line
cannot carry without a lossy re-parse. `--output-schema` is the correct
primitive and is now proven to work for this exact shape of prompt.

**Point the new `"codex"` tier at the same model binding as external review
(`gpt-5.6-terra`).** Rejected per Sven's explicit instruction (2026-09-13):
keep two independently locked identities so the two use cases — a flat
diff+spec second opinion vs. a repo-exploring internal reviewer — can use
different models, the same separation-of-identity principle GLM and GPT
already have as distinct bindings today.

**Extend `RankedTier`/`floors` to include `"codex"`.** Rejected: floors rank
Anthropic tiers by capability (haiku < sonnet < opus) for the "did this run
below the configured floor" check. Codex is a different provider entirely,
not a point on that scale — it stays floor-exempt, the same way `"inherit"`
already is (not orderable).

**Keep the scratch-dir isolation (external review's existing pattern) for
this leg too, for consistency/lower risk.** Rejected per Sven's explicit
requirement: the whole point is Opus-parity exploration capability, which
the isolated pattern cannot provide. Traded a slightly larger sandboxed
surface (read-only across the real worktree, not just two files) for
capability parity with the Agent-tool reviewers it replaces.

## Files touched (projected — this is a planning artifact, not yet built)

- `shared/schemas/model_config.schema.json` — `"codex"` added to `Tier`
  enum, `review`/`plan_review` only; `RankedTier` unchanged.
- `shared/scripts/lib/model_tier_config.py` — `TIERS` gains `"codex"`;
  confirm `RANKED_TIERS`/`RANK` untouched; docstring update explaining the
  new non-Agent-tool dispatch fork.
- `shared/config/external_review.json` (or a new sibling config) — new
  locked binding `gpt-5.6-sol` for the internal-review-via-codex identity,
  distinct from `models.codex` (`gpt-5.6-terra`).
- New: `shared/scripts/tools/review_via_codex.py` (or a `lib/` module +
  thin CLI, naming TBD) — the real-worktree, schema-driven transport
  described above.
- New: three strict-mode JSON Schema files, one per reviewer role
  (`plan_review`'s schema needs `opus-plan-reviewer.md`'s actual output
  shape read and pinned first — not yet done, see spec's Non-Goals).
- `plugins/shipwright-build/skills/build/references/code-review.md`,
  `code-review-protocol.md` — the `"codex"`-tier dispatch branch, replacing
  the `Task(...)` spawn for that case.
- `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md`
  — same branch for `plan_review`.
- `shared/scripts/tools/resolve_model_tier.py` — likely unchanged (already
  returns the raw tier string; the branch lives in the calling skill), but
  its docstring/usage example should show the new `"codex"` value.
- `record_review_pass.py` / reviews.json evidence — transport + model fields
  alongside the existing `--model-tier` self-report.
- `docs/hooks-and-pipeline.md`, `docs/guide.md`, `shared/glossary.md`.
- Tests: schema validation, `model_tier_config` accepting/rejecting
  `"codex"` per role, the new transport's fallback-on-unavailable path,
  identity-lock rejection of a mismatched configured model — mirroring the
  existing `test_model_tier_*` / `test_record_review_pass_model_tier.py`
  suites.

## Open items for whoever builds this

- Exact config key/file for the new `gpt-5.6-sol` binding (reuse
  `external_review.json` vs. a new `internal_review.json` — the former
  already carries the sibling `models.codex` identity and the `codex.{...}`
  timeout/retry block, which this leg can likely share as-is).
- Exact module/CLI naming and location for the new transport.
- `plan_review`'s output schema — read `opus-plan-reviewer.md` and pin its
  exact JSON shape before writing that schema file.
- Whether `--ephemeral` should still be passed (no session persistence) even
  though `--cd` now points at the real worktree — the probe above ran
  without `--ephemeral` on the real-dir case and worked; confirm this is
  intentional (a persisted session touching the real worktree path is
  arguably fine since sandbox stays read-only) before locking the flag set.
