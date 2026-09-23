# Codex first-eligible-call gate (M3, R2)

## Context

R0 selected the design: a prompt-borne activation envelope, minted into a
per-session record on the first `UserPromptSubmit`, consumed by the first
eligible `PreToolUse` call. R2 implements it and performs M3's required
hook-inventory audit. Mid-run Architecture Review (both GLM and OpenAI:
`revise`) found the originally-planned third hook — a `Stop`-gated
dispatcher enforcing the setup step persistently — disproportionate: a
first-ever turn-blocking hook duplicating existing repair
(`iterate_stop_finalize.py`) and detection (`codex_completion_oracle.py`)
machinery. That mechanism was cut to R2b in full.

## Decision

Ship two Codex-only hooks: `codex_activation_mint.py` (`UserPromptSubmit`,
mints an exclusive-create-once `armed`/`unarmed` record from the envelope)
and `codex_pretooluse_gate.py` (`PreToolUse`, exclusive-consume-once —
denies the session's first eligible call unless it is
`setup_iterate_worktree.py`, tokenized-matched, never substring). Register
both in a NEW sibling manifest, `plugins/shipwright-iterate/hooks-codex/hooks.json`
— read only by the Codex bundle build (`codex_hook_inventory.py`), structurally
invisible to Claude Code's own plugin loader (verified against official docs:
Claude Code reads hooks only from `<plugin-root>/hooks/hooks.json` or a `hooks`
field in `.claude-plugin/plugin.json`, no directory scanning). This is a
one-shot "exactly one deny budget" on the session's first evaluated call, not
a persistent block — a denied first call followed by a *different* second
call sails through unevaluated; the Stop-gate that would close this gap is
the deferred R2b work.

Activation-record storage: `<project_root>/.shipwright/runtime/codex-activation/
<session>.json` + `.consumed` sidecar (gitignored), exclusive-create via
`os.O_CREAT | os.O_EXCL`, fail-open contract (absent/corrupt/schema-mismatched/
cwd-mismatched/expired = "no record", never an exception).

## Consequences

Positive: a Codex-driven iterate's first eligible tool call is nudged toward
the mandated setup step without any Claude-visible cost (the `hooks-codex`
split keeps both new hooks off Claude's own hook fan-out entirely). Negative:
per-turn cost is not fully eliminated under Codex — the hook wrappers must
resolve `project_root` (a git subprocess, `normalize_cwd()`) BEFORE the
library's own `Path.exists()` short-circuit can run, since the record's
storage path is itself keyed by `project_root`; this is a real circular
dependency, not an oversight, and is left as an R2b perf follow-up rather than
introducing new on-disk caching state under this run's scope. The
Stop-gate/finalization-enforcement half (parent-spec AC1b/AC3) is explicitly
NOT closed by R2 — recorded honestly rather than silently dropped, and
inherited whole by R2b alongside the all-phase generalization already planned
there.

## Rejected alternatives

1. **Persistent Stop-gated enforcement across the whole session** (the
   originally-planned AC1b/AC3 third hook) — rejected by both external
   plan reviewers as disproportionate; a first-ever turn-blocking hook
   duplicating existing repair/detection machinery. Deferred to R2b.
2. **Registering the two new hooks in the shared, Claude-visible
   `plugins/shipwright-iterate/hooks/hooks.json`** — would have silently
   gated Claude Code sessions too (an internal plan-review HIGH finding),
   contradicting the Codex-only scope. Replaced by the `hooks-codex/hooks.json`
   sibling-manifest convention.
3. **Substring/regex matching for the setup-script invocation** — an
   earlier version allowed any compound command containing a matching
   segment anywhere (`rm -rf x && uv run setup_iterate_worktree.py`),
   smuggling arbitrary other commands past the gate. Replaced with
   tokenized (shlex), segment-aware matching that denies outright on any
   `|`/`||`/redirection/grouping operator, keyed on the actually-invoked
   program rather than a substring anywhere in the command.

## External code review (Stage 4, this run)

GLM and OpenAI (via `external_review.py --mode code`) both returned
`revise`. Findings addressed in this run: two matcher bugs (missing
redirection/grouping-operator deny, `uv run` value-flag false-deny),
`read()` missing JSON field-type validation before use, the mint hook
missing a `skill_id` allowlist (any valid envelope armed the gate
regardless of skill), `_exclusive_create`'s `mkdir` sitting outside its
own OSError fail-open guard, and three doc-drift items (`mini-plan.md`
still naming `hooks/hooks.json`, `iterate-spec.md` AC0 still saying
"three new hooks", a missing `shared/scripts/tools/tests` runner
invocation). One HIGH finding — OpenAI flagging `codex_activation_helper.py`'s
refusal to launch through a `.bat`/`.cmd`-resolved `codex` binary as a
usability defect — is a deliberate, empirically-verified security decision
(Windows `CreateProcess` re-parses `.bat`/`.cmd` targets through `cmd.exe`
regardless of `shell=False`, corrupting the envelope grammar's own `|`
characters) that GLM's own independent review explicitly listed as
"checked and cleared." Adjudicated as correct-as-designed, not a defect;
no code change, documented here as the rebuttal.
