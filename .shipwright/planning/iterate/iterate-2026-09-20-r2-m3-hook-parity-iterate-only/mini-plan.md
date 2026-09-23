# Mini-Plan: r2-m3-hook-parity-iterate-only

- **Run ID:** iterate-2026-09-20-r2-m3-hook-parity-iterate-only

> Revised three times: after Internal Plan Review (opus-plan-reviewer,
> REJECT, 13 findings, all fixed), after External Plan Review (Branch A —
> glm=approve, openai=revise, 13 findings, all fixed), and after Architecture
> Review (glm=revise, openai=revise, both recommending the same cut — see the
> iterate spec's three review sections). **This version reflects the final
> scope: the Stop-gate mechanism is cut entirely and deferred to campaign
> sub-iterate R2b.** R2 now ships only the pre-worktree `PreToolUse` denial
> (AC1a), its supporting activation-record/grammar machinery, the payload-
> capture probe, and the hook-inventory audit.

## 0. Resume note (2026-09-22, post-R1b) — read before anything below

R2 was paused when R1's plugin-bundled hooks were found dead-on-arrival; R1b
(PR #786, merged `42e45008d`) shipped the fix — a config-layer sync
(`codex_hooks_sync.py`/`codex_hooks_launcher.py`) that installs into the
global `~/.codex/hooks.json`, live-proven both interactively and via
`codex exec`. Two consequences for this plan, found during re-verification
(a fork's gap analysis, then an independent Opus second opinion) before
resuming build:

1. **`shared/scripts/lib/codex_runtime.py` already exists and is more
   hardened than planned below — reuse it, do not rebuild it.** R1b's
   shipped `is_codex_runtime(plugin_root: Path | None = None) -> bool`
   already does exactly what external review's glm finding (originally
   below) asked for: resolves via `resolve_plugin_root()`, then verifies
   BOTH bundle-marker files are actually present, not a bare env-var
   presence check. Drop the "New" bullet that follows in the original plan;
   `import` it instead.
2. **AC0's discriminator is broken as designed and needs one new
   prerequisite change, not in R2's own hook scripts.** `resolve_plugin_root()`
   — which `is_codex_runtime()` calls — finds its answer via env vars
   (`SHIPWRIGHT_PLUGIN_ROOT` > `CLAUDE_PLUGIN_ROOT` > `PLUGIN_ROOT`). Real
   captured payloads from R1b's live proof confirm Codex injects **none** of
   these for hooks delivered via the config-layer path (`"env": {}`, every
   capture, every event) — that injection only happens for plugin-bundled
   hooks, the delivery path that's dead. So inside a real Codex-invoked hook
   right now, `is_codex_runtime()` always returns False — permanently inert,
   not just "PLUGIN_ROOT absent means Claude", the exact case AC0 needs to
   tell apart from "Codex, but the discriminator broke".

   **Fix (new mini-plan step, do FIRST):** `codex_hooks_launcher.py` already
   substitutes the bundle's absolute root into each generated launcher body
   at generation time — have it also inject `SHIPWRIGHT_PLUGIN_ROOT=<that
   same root>` as an env var, immediately before the real invocation, in
   every launcher it writes. This is literally what `plugin_root.py`'s own
   docstring already prescribes ("provider packaging or **a thin launcher**
   is expected to derive `SHIPWRIGHT_PLUGIN_ROOT`") — the launcher R1b
   already generates IS that thin launcher, it just doesn't do this one
   thing yet. Needs zero changes to `codex_runtime.py`, `plugin_root.py`, or
   `resolve_plugin_root()` — and fixes every OTHER consumer of the same
   resolver running under a Codex-invoked hook, not just this one check.
   Platform-specific (Opus review, checked against Codex's own
   `command.env_clear()` behavior — no ambient-env leakage risk either
   direction):
   - Windows: `set "SHIPWRIGHT_PLUGIN_ROOT=<root>"` — the quote-the-whole-
     assignment form (avoids trailing-space capture; the existing
     `_UNSAFE_BUNDLE_ROOT_RE` allowlist already bans `% ! & ^ "`, so no
     expansion/injection risk). No `setlocal` needed, each `cmd /C` already
     gets its own environment.
   - POSIX: do **not** write `VAR=val exec cmd` inline — assignment-before-a-
     special-builtin export semantics are murky across shells. Three
     separate lines: assign, `export`, then `exec`. Wrap the value in
     `shlex.quote()` regardless of the existing path-character allowlist
     (belt-and-braces, cheap).
   - Re-run `codex_hooks_sync.py` after this change and confirm via a fresh
     live-proof capture (mirroring R1b's AC4) that `env.SHIPWRIGHT_PLUGIN_ROOT`
     actually appears in a real payload before trusting the rest of this
     plan's fixtures — don't just unit-test the launcher body string.
3. **Scope clarification (Opus review) — `is_codex_runtime()` answers "is my
   resolved plugin root a real Codex bundle", never "is this the live,
   armed session I care about".** Since `~/.codex/hooks.json` is global,
   every Codex session on the machine shares the same bundle root — fixing
   (2) makes the check permanently *true* for every session, not a
   per-session gate. That's fine and expected: AC0/`is_codex_runtime()` was
   always meant as the coarse "are we even under Codex at all" pre-check;
   the actual per-session scoping is the activation-record layer below
   (AC1a, `codex_activation_record.py`, keyed on session_id/turn_id/cwd),
   which is unaffected by any of this and doesn't need rethinking. Don't
   read AC0 as R2's real gate — it never was; keep that reasoning explicit
   in the spec so a future reader doesn't re-litigate it.

## 1. Files to create/modify

**New:**
- ~~`shared/scripts/lib/codex_runtime.py`~~ — **dropped, see §0.1.** Reuse
  R1b's shipped version unchanged.
- `shared/scripts/lib/codex_envelope_grammar.py` — the closed grammar M7
  names: `compose(skill_id, args) -> str` (embeds into a first prompt) and
  `parse(prompt_text) -> Envelope | None` (returns `None` on no/malformed
  match — never raises). One module, both directions, so helper and mint
  hook can never drift apart. Round-trip tested first (TDD step 1).
- `shared/scripts/lib/codex_activation_record.py` — mint is **exclusive-
  create only** (`open(path, "x")`): the FIRST `UserPromptSubmit` on a
  session creates the record (`armed: true` with session_id/turn_id/cwd/
  generation/expiry, or `armed: false` marker if the grammar didn't match);
  every subsequent `UserPromptSubmit` on the same session finds the path
  already exists, the create raises `FileExistsError`, and the hook treats
  that as "already decided, nothing to do" — **not** an overwrite (external
  review, openai high-1: writing on every prompt let a later ordinary
  message downgrade an armed session to unarmed, or arm one mid-session).
  This is what makes "first eligible prompt only" true by construction, not
  by convention. Consume (by the `PreToolUse` gate) is a SEPARATE exclusive-
  create of a sibling `.consumed` marker next to the (never-deleted) record
  — a one-time claim, not an overwrite. Expiry check: expired → fail-open
  with a warning, same as absent — never deny. cwd normalization via
  `shared/scripts/lib/git_base.main_repo_root`.
- `plugins/shipwright-iterate/scripts/hooks/codex_activation_mint.py` —
  `UserPromptSubmit` hook. No-ops (writes nothing, `additionalContext`
  unchanged) unless `is_codex_runtime()`. Parses the first prompt via the
  grammar module; exclusive-creates the marker (see above) — silently no-ops
  on every later prompt in the same session, by construction.
- `plugins/shipwright-iterate/scripts/hooks/codex_pretooluse_gate.py` —
  `PreToolUse` hook. No-ops unless `is_codex_runtime()`. Reads the session's
  marker: `armed: false` or no marker at all → allow, always (fail-open,
  matches R0's Contract verbatim). `armed: true` → this is the session's
  first-eligible-call gate (own durable "first-call-settled" flag, same
  exclusive-consume primitive): if unsettled, the tool call's local-
  function-tool class is looked up against the allow/deny matrix built from
  the payload-capture probe (step 2) — **unknown/unrecognized classes deny
  by default while armed-and-unsettled** (external review, openai medium-4:
  a shell-only matcher leaves any non-`Bash` local tool free to bypass); a
  `Bash`-class call is tokenized (shlex) and basename-matched against
  `setup_iterate_worktree.py`, never substring-matched. Denial
  (`hookSpecificOutput.permissionDecision: "deny"`) includes the exact
  runnable setup command in the reason text (external review, glm medium:
  tell the model what to run, don't just say no), and is scoped to the
  local function-tool path only — hosted tools bypass this hook entirely,
  a Codex-side fact this hook cannot change. A matching setup call consumes
  and allows, settling the flag.
- `shared/scripts/tools/codex_activation_helper.py` — terminal helper CLI.
  Composes the envelope via `codex_envelope_grammar.compose()`. Launches
  Codex via an argument-vector process call (never a shell-interpolated
  command string — external review, openai low-7: a shell-built launch
  command risks injection from the composed prompt text). Windows
  shell-quoting handled explicitly at the argv level. Explicit reject/warn
  when pointed at an existing session or a non-first-prompt use.
- `shared/tests/test_codex_envelope_grammar.py` — round-trip (compose→parse
  recovers the same skillId+args) + malformed/partial/pasted-log-text cases
  (envelope-authenticity risk R0 already named).
- `shared/tests/test_codex_activation_record.py` — Boundary Probe: mint→
  consume round-trip, the state-transition table (duplicate submission,
  failed gated call after consumption, mid-turn expiry → fail-open not deny,
  concurrent consumers → exactly one wins via the exclusive-create
  primitive), cwd-mismatch → treated as absent.
- `plugins/shipwright-iterate/tests/test_codex_pretooluse_denial.py` — AC1a's
  three fixtures (armed+wrong-first-call denies, armed+correct-first-call
  allows, unarmed never denies), plus the tokenization cases (the `echo
  setup_iterate_worktree.py` false-allow and the `cd <root> && uv run
  setup_iterate_worktree.py` false-deny the reviewer named) and one fixture
  per allow/deny-matrix tool class.
- `plugins/shipwright-iterate/tests/test_codex_hooks_noop_under_claude.py` —
  AC0: both new hooks, invoked without `PLUGIN_ROOT` set (and with a
  "wrong-value" `PLUGIN_ROOT` — external review, glm), never deny regardless
  of activation-record state.
- `.shipwright/planning/iterate/iterate-2026-09-20-r2-m3-hook-parity-iterate-only/hook-inventory.md`
  — the all-plugin hook classification (audit artifact, no code), including
  the per-tool-class matcher inventory (`Bash` aliased, `spawn_agent`-class
  raw-with-dot-stripped, `Agent` matcher confirmed to also catch
  `spawn_agent` per R0's live probes), and an explicit recommendation section
  for R2b scoping the Stop-gate/finalization generalization from this run's
  payload-capture evidence.

**Edit:**
- `shared/scripts/tools/codex_hooks_launcher.py` — see §0.2. Inject
  `SHIPWRIGHT_PLUGIN_ROOT=<bundle_root>` into every generated launcher body
  (platform-specific form there). This is R1b's file, being extended, not
  R2's own new surface — do this FIRST, before any of R2's own hook work,
  since AC0 depends on it working.
- `plugins/shipwright-iterate/hooks-codex/hooks.json` — a NEW sibling
  manifest to `hooks/hooks.json` (post-mid-run design pushback, corrected
  here — see step 8 and `hook-inventory.md`'s "Runtime-scoped hook
  registration" section), read only by the Codex bundle build, never by
  Claude Code's own plugin loader: a `PreToolUse` group with the gate hook,
  and a `UserPromptSubmit` group with the mint hook. `hooks/hooks.json`
  itself (Claude-visible) is NOT touched by this run —
  `iterate_stop_finalize.py` and the rest of its `Stop` group stay
  untouched too. All new command strings use `uv run --no-project` for the
  same cold-start-cost reason the existing `suggest_iterate.py` entry does.
- `docs/hooks-and-pipeline.md` — new subsection under "Codex Plugin Bundle"
  (R1's own section) documenting the activation-record contract, the
  runtime-discriminator convention (including the bundle-root check, not
  bare presence), the allow/deny matrix for local-function-tool classes, and
  the matcher inventory; PLUS new rows in the `### shipwright-iterate` Hooks
  Registry table for the two new hooks; PLUS an artifact-write-matrix row
  for the activation record; PLUS an explicit statement of the threat model
  (external review, openai low-7: this is cooperative local-process
  enforcement — a model or process with shell access in the same workspace
  can write its own `armed`/`.consumed` state; the guarantee is "a
  cooperating-but-forgetful session can't silently skip the worktree-setup
  step," not an adversarial boundary, consistent with how R0 already framed
  envelope authenticity); PLUS a note that the Stop-gate/finalization-
  enforcement mechanism was designed, reviewed, then deliberately deferred
  to R2b (Architecture Review, proportionality) — named so a future reader
  doesn't assume it was overlooked. No `.gitignore` change needed —
  `.shipwright/runtime/` is already covered by the existing `/.shipwright/*`
  wildcard (confirmed against `shared/templates/shipwright-gitignore.template`).
- `.shipwright/planning/01-adopted/spec.md` — FR-01.21 description + ACs
  (MODIFY, per Spec Impact above).
- **Unplanned, attributed extra (found by Step 7 code review, MEDIUM —
  duplicated PATH-hijack guard; recorded post-hoc after `spec-reviewer`
  Stage 1 round 1 flagged it as unrecorded):** `shared/scripts/lib/cmd_resolver.py`
  (new — hoists `resolve_trusted_executable()` out of duplication),
  `shared/scripts/lib/external_review_default_legs.py` (`_resolve_codex_binary`
  now delegates to it), and the monkeypatch targets in
  `shared/tests/test_external_review_codex_availability.py` +
  `shared/tests/test_external_review_codex_leg.py` retargeted accordingly.
  Outside this run's own scope on its merits (see iterate-spec.md's Spec
  Impact section for the full rationale) — named here so the file list is
  honest about what actually shipped.

## 2. Work breakdown

0. **Launcher env-injection fix** (§0.2) — do this before step 1. Re-run
   `codex_hooks_sync.py` afterward and confirm via a live capture that
   `env.SHIPWRIGHT_PLUGIN_ROOT` is actually present before proceeding —
   everything below silently no-ops forever if this isn't actually working,
   the same failure class this whole campaign started from.
1. **Grammar module** (`codex_envelope_grammar.py`) — compose + parse, one
   module. **Exact wire format now decided — see iterate-spec.md's Design
   Notes section** (was blocking, a build agent correctly stopped rather
   than guess it, 2026-09-22): `[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=<id>|args_b64=<b64url-json>]`,
   ASCII-only, single-line, `parse()` never raises, two-or-more-matches →
   `None`. Test: round-trip + the six-case malformed-input matrix listed
   there, written first (TDD).
2. **Payload-capture live probe** (moved ahead of hook implementation, per
   internal review finding 9 — still valuable even with the Stop gate cut,
   since it's R2b's own required evidence too) — R1b's own AC4 live proof
   already captured real `UserPromptSubmit`/`PreToolUse`(`Bash`)/`Stop`
   payloads via config-layer hooks (`turn_id` confirmed present;
   `stop_hook_active`/`last_assistant_message` confirmed on `Stop`) — reuse
   those shapes, don't re-derive them. Still needed fresh: the complete set
   of locally hook-visible tool names/classes beyond `Bash` (nothing
   triggered a non-Bash local tool in R1b's proof) — one live Codex CLI turn
   against a throwaway scratch repo that exercises a non-Bash local tool,
   with the now-fixed launcher/env in place. Also still settles: whether
   `iterate_stop_finalize.py`
   behaves safely under a real Codex-shaped Stop payload (external review,
   glm low-5) — both recorded as evidence for R2b, not consumed by any
   enforcement this run ships. Captured payloads become the fixture inputs
   for steps 3-4 — fixtures are not written from a guess.
3. ~~Runtime discriminator~~ — dropped (§0.1). Every later hook imports R1b's
   `is_codex_runtime()` as-is; no new file, no new test here.
4. **Activation-record library** (`codex_activation_record.py`) — mint-once
   (armed/unarmed), exclusive-consume, expiry (fail-open), state machine.
   Test: round-trip + full state-transition table (Boundary Probe).
5. **`UserPromptSubmit` mint hook** — no-ops unless `is_codex_runtime()`
   (§0.1 — not a bare `PLUGIN_ROOT` presence check); exclusive-creates the
   armed-or-not marker once per session via Step 4's `mint()`. Test: AC0's
   Claude no-op case (including the wrong-value-env-var case, feeding
   `is_codex_runtime()` False) + both armed branches + the "second prompt
   never overwrites" case (Step 4 already proved this at the library level —
   this test proves the hook wires it through correctly, not re-proving the
   library).
6. **`PreToolUse` deny hook** — build the allow/deny matrix from step 2's
   captured tool-class inventory (unknown classes deny by default while
   armed-and-unsettled); tokenized/basename command matching for the
   `Bash` class (not substring); first-eligible-call durable flag;
   local-function-tool-only scope; deny reason includes the exact runnable
   setup command. Test: AC1a's three fixtures + the tokenization edge cases
   + one fixture per matrix class.
7. **Terminal helper CLI** — composes via the grammar module from step 1;
   argument-vector launch, Windows shell-quoting; explicit reject/warn on
   wrong-target invocation. Test: shape/quoting unit tests.
8. **Wire into `plugins/shipwright-iterate/hooks-codex/hooks.json`** (a NEW
   sibling manifest, corrected post-mid-run design pushback — NOT
   `hooks/hooks.json`, which stays Claude-visible and untouched, per
   `hook-inventory.md`'s "Runtime-scoped hook registration" section),
   rebuild the Codex bundle (`build_codex_plugin.py`), verify with
   `verify_codex_plugin_bundle.py`.
9. ~~**AC0/AC5 regression**~~ — **done, corrected on build** (2026-09-22): the
   five checkers do NOT live per-plugin as originally assumed here — they're
   centralized in `shared/scripts/tools/verifiers/`, tested from the shared
   `shared/tests` root (per `.github/workflows/ci.yml`'s own invocation), not
   five separate plugin roots. AC5 verified via
   `uv run pytest shared/tests -m "not slow and not cross_plugin" -k "<the 5
   checkers>"` from the repo root (259/259 passed) — NOT a new file importing
   across plugins
   (avoids the ADR-044/045 `scripts`/`lib` package-collision the reviewer
   flagged).
10. **Live-probe run for AC1a's two blocking preconditions** — real rebuilt
    bundle, installed and trusted, `codex /hooks` confirmation recorded as
    evidence: (a) ordinary trusted-hook denial (no bypass flag), (b) mint→
    store→consume chained in one live turn. Both required before AC1a can
    be considered actually met, not just fixture-proven.
11. **Hook inventory audit + R2b handoff** — classify every hook in all 14
    `plugins/*/hooks/hooks.json` into M3's three relevance tiers, including
    the matcher inventory; write `hook-inventory.md` with an explicit
    "recommended starting point for R2b" section citing this run's payload-
    capture findings (Stop-payload shape, `iterate_stop_finalize.py`'s
    behavior under it, the reviewed-then-deferred Stop-gate design from the
    Internal/External Plan Review sections of this run's iterate spec).
12. **Docs + spec.md** — as listed in Files above.

## 3. Component hierarchy

n/a (no UI).

## 4. Data model changes

None (no DB). New serialized formats: the envelope grammar (prompt text) and
the activation record (file) — both covered under Affected Boundaries.

## 5. Test strategy

- Unit: grammar round-trip, runtime discriminator (including the "wrong
  `PLUGIN_ROOT` value" case), activation-record library (mint-once/no-
  overwrite, exclusive-consume, expiry, cwd-mismatch → absent).
- Fixture (hook contract level, built from step 2's captured real payloads):
  AC0 (both hooks, absent/wrong-value `PLUGIN_ROOT`), AC1a (3 cases + one
  per matrix class + tokenization edge cases).
- AC5 regression: existing per-plugin suites, run from their own roots —
  no new cross-plugin test file.
- Live (real Codex CLI, throwaway scratch repo): step 2's payload capture,
  then step 10's two-item AC1a probe. Neither is fixture-simulable — the
  whole point is proving Codex's own runtime behavior, not this repo's code.
- No E2E/browser layer — `surface: cli`, no UI exists for this change.

## 6. Alternative approach (considered, rejected)

**Alternative: skip the terminal helper, have the operator hand-type the
envelope grammar into Codex's first prompt.** Rejected — R0's Contract
explicitly requires "one defined invocation shape... explicit Windows
shell-quoting handling" for the terminal producer, precisely because a
hand-typed envelope is exactly the "plain, model-visible, user-pasteable
first-prompt text" authenticity risk R0's ADR already named and accepted for
the *authorized* path; leaving the *only* path fully manual would make that
residual risk the common case instead of an edge case, and would give R2's
own AC1a fixture nothing deterministic to launch against. A thin CLI wrapper
composing the exact grammar is cheap relative to that cost.

**Alternative (this run's actual history, kept for the record): build the
Stop-gate mechanism now, iterate-only.** This was the original plan,
substantially hardened across two review rounds (mint-once semantics,
armed-record validation, `run_id` binding, a loop-breaker with defined
identity/atomicity/monotonicity, a defaulted-off capability flag). Cut by
Architecture Review — both reviewers independently found it disproportionate
to what it adds over the existing `iterate_stop_finalize.py` repair pass and
`codex_completion_oracle.py` detection, given it would also be this repo's
first-ever turn-blocking hook. Deferred to R2b in full (see the iterate
spec's `## Architecture Review` section for the complete reconciliation);
the hardening work is not wasted — it is R2b's starting design.
