# Iterate Spec: r2-m3-hook-parity-iterate-only

- **Run ID:** iterate-2026-09-20-r2-m3-hook-parity-iterate-only
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented
- **Campaign:** codex-plugin-execution-reliability, sub-iterate R2

## Goal

Turn "Codex is told to run `setup_iterate_worktree.py` first" into "Codex's
first eligible tool call in an armed session is denied unless it is that
setup call" — the pre-worktree half of the enforcement mechanism M3 names,
armed via the prompt-borne envelope R0 selected. **This is a one-shot nudge
on the session's first call, not a persistent block** (code review, MEDIUM:
the Goal previously overclaimed "cannot proceed... without it having
actually happened" — the actual mechanism, `consume()`'s exclusive-consume-
once, settles the session after exactly ONE evaluated call regardless of
its outcome, so a denied first call followed by a *different* second call
sails through unevaluated; the external plan review deliberately chose this
one-shot "exactly one deny budget" over a persistent gate, and the Stop-gate
mechanism that would have closed this gap is the very thing cut to R2b — see
Out of Scope). Also perform M3's own required
hook-inventory audit across all 14 plugins (classification only, not
enforcement) and capture real Codex hook payloads live, so a later
sub-iterate (**R2b**) can design the Stop-gate/finalization-enforcement half
— generalized across all plugin phases, not just iterate — from real
evidence instead of a guess. **Scope note (post Architecture Review, both
reviewers `revise`):** the Stop-gate mechanism itself, originally planned for
this run (armed iterate-only), was cut from R2 as a disproportionate,
first-ever-blocking-hook standing mechanism duplicating existing repair
(`iterate_stop_finalize.py`) and detection (`codex_completion_oracle.py`)
machinery — see `## Architecture Review`. It moves to R2b in full, alongside
the all-phase generalization already planned there.

## Acceptance Criteria

- [x] AC0 — Runtime discriminator: every new hook script is a documented
  no-op (returns allow / no decision) whenever `is_codex_runtime()` (R1b's
  shipped primitive, reused unchanged — see mini-plan §0) is false. Fixture
  proves a Claude-shaped invocation is never denied and never blocked by
  either of the two new hooks (the mint hook, the gate hook — the
  originally-planned third, Stop-gate hook was cut mid-run; see the
  Architecture Review), regardless of activation-record state. **Depends
  on a prerequisite fix to `codex_hooks_launcher.py`** (mini-plan §0.2):
  config-layer hooks get no env vars from Codex at all, so
  `is_codex_runtime()` is permanently false today even under real Codex —
  the launcher must inject `SHIPWRIGHT_PLUGIN_ROOT` itself before this AC is
  achievable. `is_codex_runtime()` answers "is my plugin root a real Codex
  bundle", not "is this my session" — since the global hooks file makes the
  bundle root constant across every Codex session on the machine, this AC is
  deliberately the coarse under-Codex-at-all pre-check, not the per-session
  gate; AC1a's activation-record layer is what does that (mini-plan §0.3).
- [x] AC1a — Scope: the local function-tool path only (Codex's hosted tools,
  e.g. `WebSearch`, bypass `PreToolUse` entirely — not this AC's claim to
  make). A fixture launches a fresh, **armed** Codex-driven iterate session
  (a valid `UserPromptSubmit`-minted record with `armed: true`) whose first
  gated tool call is NOT `setup_iterate_worktree.py` (tokenized match, not
  substring — `echo setup_iterate_worktree.py` must NOT satisfy it). The
  `PreToolUse` hook denies the call (`permissionDecision: deny` + reason). A
  second fixture with the same armed record and `setup_iterate_worktree.py`
  as the first gated call is allowed through. A **third** fixture proves an
  **unarmed** session (no matching first-prompt grammar — `armed: false`
  marker) is never denied, regardless of its first tool call — matching R0's
  fail-open contract.
- [ ] ~~AC1b/AC3 (Stop-gated dispatcher)~~ — **dropped from R2's scope after
  Architecture Review** (both glm and openai independently: `revise`,
  recommending exactly this cut — see `## Architecture Review` below). The
  Stop gate would have been this repo's first-ever turn-blocking hook, to
  guard a failure the existing `iterate_stop_finalize.py` repair pass
  already re-attempts and the webui completion-oracle/nudge already
  surfaces — a disproportionate standing mechanism whose own design already
  conceded it might ship "installed but disabled" pending live evidence.
  Deferred to **R2b**, alongside the all-phase generalization already
  planned there, now informed by this run's payload-capture probe instead
  of a guess. Parent-spec AC1b/AC3 are correspondingly NOT closed by R2 —
  recorded honestly, not silently dropped.
- [x] AC5 (regression) — every existing `check_c1_phase_event_recorded`-class
  Claude caller (`project_checks.py`, `plan_checks.py`, `design_checks.py`,
  `changelog_checks.py`, `deploy_checks.py`) keeps passing, unmodified, run
  from its own plugin's test root (never a cross-plugin import — see Mini-
  Plan §5). AC0's fixture is what actually proves Claude sessions are
  unaffected by the new hooks; this AC proves the pre-existing Claude
  machinery itself is untouched.
- [ ] Live proof — payload capture (`PreToolUse`/`Stop`/`UserPromptSubmit` full
  JSON shapes, `turn_id` presence, the hook-visible name Codex uses for
  non-`Bash`-class calls). **Attempted live 2026-09-22, not completed**: the
  probe session (real bundle + additive capture-only bundle, scratch
  `CODEX_HOME`, `cwd` = the real R2 worktree) diverged before reaching the
  capture steps — `setup_iterate_worktree.py` detected "already inside a
  linked worktree" and Codex's own `/shipwright-iterate` resume logic (SKILL.md
  §B1) took over, driving a real review cascade (`spec_reviewer` started)
  against R2's own actual diff instead of the scripted scratch probe. Stopped
  before any commit; session and scratch `CODEX_HOME` fully torn down, no
  residue in the repo. **Left open, non-blocking for R2:** the `Stop` payload
  shape isn't load-bearing for anything R2 itself ships (the Stop gate is
  deferred whole to R2b, which inherits this proof requirement); the
  non-`Bash` tool-class name only affects the *default-deny* path, which the
  design already treats as correct without knowing the exact name (`### PreToolUse
  gate matching logic` above). A repeat run would need `cwd` pointed at an
  isolated throwaway repo (not this worktree) to avoid re-triggering the same
  resume-flow divergence — judged not worth doing for R2 given the above.
- [x] Live proof — the two blocking preconditions inherited from R0, required
  for AC1a: (a) an ordinary, non-bypassed, trusted Codex hook fires and
  denies a gated call; (b) the mint → store → consume chain is exercised
  end-to-end in one live turn. **Confirmed live 2026-09-22** in the same probe
  session: (a) the wrong-first-call (`ls`) was denied by the real,
  Codex-trusted `PreToolUse` gate ("Blocked by hook", trust granted via
  Codex's own "Trust all and continue" — not bypassed), with the deny reason
  containing the documented `<slug>`/`<run-id>` unresolved-placeholder text
  exactly as spec'd; the correct setup-script call was let through with no
  denial (failed only afterwards on an unrelated local `uv`-cache permission
  error, orthogonal to this gate). (b) the on-disk activation record
  (`.shipwright/runtime/codex-activation/<session>.json` + `.consumed`
  sidecar) showed a record minted for this run and consumed exactly once —
  read directly off disk as evidence, then deleted during cleanup. **Not
  captured:** `codex /hooks` output naming the trust source explicitly — the
  session diverged before that step; the "Trust all and continue" dialog text
  itself is treated as sufficient confirmation that trust was genuine and
  non-bypassed, per the same evidence bar.
  (Two further probes — Codex honoring a `Stop` hook's `decision: block`,
  and same-group command-hook execution ordering — remain captured only in
  the (not-yet-run) payload-capture probe above, but are no longer this run's
  own gating precondition now that the Stop gate itself is deferred to R2b;
  R2b inherits them as its own required live proof instead.)
- [x] Unarmed-launch visibility (R0 named gap 2) — a `SessionStart` hook (or
  the first ungated call) surfaces a visible warning when no activation
  record was recognized, so the fail-open default is never silent.
  **Implemented via the "first ungated call" alternative** (a `SessionStart`
  hook cannot know the armed/unarmed outcome yet — mint happens on the
  session's first `UserPromptSubmit`, which runs after `SessionStart`):
  `codex_pretooluse_gate.py`'s `_unarmed_visibility_warning()` fires exactly
  once, on the genuinely-first eligible `PreToolUse` call of an unarmed
  session (`consume()`'s own exclusive-create settles which call that is),
  returning a non-blocking `hookSpecificOutput.permissionDecision: "allow"`
  with a `permissionDecisionReason` explaining the session is unarmed and
  the mandatory setup step will not be enforced — reusing the exact JSON
  shape already live-confirmed visible for a deny, never a new, unverified
  surface. Tested in `test_codex_pretooluse_denial.py::TestUnarmedVisibilityWarning`
  (fires once, content, never a deny). Found missing by `spec-reviewer`
  Stage 1 (round 1, REJECT) and fixed before re-review.
- [x] `docs/hooks-and-pipeline.md` updated in the same diff: the new
  `PreToolUse` group, the activation-record producer/consumer contract, the
  per-tool-class matcher inventory, new rows in the `### shipwright-iterate`
  Hooks Registry table, an artifact-write matrix row for the activation
  record, and a note naming the Stop-gate deferral to R2b (so a future
  reader doesn't assume it was overlooked).
- [x] Hook inventory — every hook across all 14 `plugins/*/hooks/hooks.json`
  files classified into M3's own three relevance tiers (global-safe /
  durable-state-selected / explicit-activation-required), recorded as
  `.shipwright/planning/iterate/iterate-2026-09-20-r2-m3-hook-parity-iterate-only/hook-inventory.md`.
  Audit only — this AC does not itself change any non-iterate hook's
  behavior; it is the scoping input for campaign sub-iterate R2b.

## Spec Impact

- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.21 (Codex Plugin Distribution) — extends the existing
  "Shipwright can be installed for Codex as a bundle" capability with
  "...and a Codex-driven iterate's first eligible tool call is denied unless
  it runs that bundle's mandatory setup step" (code review, MEDIUM: downgraded
  from "cannot silently skip" — see Goal's own correction above; this is a
  one-shot first-call check, not a persistent block). Same capability's next
  phase, not a new one (MINT-vs-FOLD gate: this completes/extends FR-01.21's
  own arc — R1 built the bundle to install hooks into, R2 is the first hook
  that actually enforces something through it).
- **REMOVE:** none
- **NONE justification:** n/a
- **Attributed extra (unrecorded shared-surface touch, found by `spec-reviewer`
  Stage 1, round 1):** `shared/scripts/lib/cmd_resolver.py` (new
  `resolve_trusted_executable()`) and `shared/scripts/lib/external_review_default_legs.py`
  (`_resolve_codex_binary` now delegates to it, plus retargeting ~15
  monkeypatch call sites in `shared/tests/test_external_review_codex_availability.py`
  and `shared/tests/test_external_review_codex_leg.py` from `legs.shutil.which`
  to `cmd_resolver.shutil.which`) are outside this run's own scope — the
  external-review Codex leg appears nowhere in this spec, its Spec Impact, or
  the mini-plan's file lists. R2 needed the BatBadBut cwd-hijack guard only for
  its own new `codex_activation_helper._resolve_codex_binary`; a same-run
  code-review finding (Step 7, MEDIUM — duplicated PATH-hijack guard) found
  that guard byte-for-byte duplicated an existing copy already living in the
  external-review leg, and deduped both onto one shared module rather than
  leave two copies to drift. Behavior-preserving (all touched tests still
  pass), but genuinely a de-duplication of code this run does not otherwise
  own — recorded here as the fix, per spec-reviewer's own re-review scope,
  rather than reverted (reverting would restore the duplicate the finding
  flagged in the first place).

## Out of Scope

- **The Stop-gate/finalization-enforcement mechanism entirely — both the
  iterate-only version originally planned for this run, and the all-phase
  generalization.** Cut by Architecture Review (both reviewers `revise`,
  proportionality: it would have been this repo's first-ever turn-blocking
  hook, duplicating `iterate_stop_finalize.py`'s existing repair pass and
  `codex_completion_oracle.py`'s existing detection). Deferred whole to
  **R2b**, informed by this run's hook-inventory audit and payload-capture
  probe. Per `codex-runtime-integration-spec.md` §9, the all-phase half of
  this was already "Slice 2" territory; the iterate-only half now joins it
  there too rather than shipping as a separate, smaller precedent first.
- `shipwright-webui` / Codex Desktop activation producers (R0's decision —
  terminal producer only).
- Claude-side pre-worktree `PreToolUse` registration (R0's decision — a
  separate, later decision; Claude remains exactly as unenforced as before).
- M4 (subagent-role mapping — campaign R3) and M5 (AGENTS.md/TOML drift tests
  — campaign R4).
- Parent spec §4 AC4 ("N ≥ 3 consecutive real Codex-driven iterates complete
  unattended") — a campaign-level validation bar across R2/R3/R4's combined
  output, not a per-sub-iterate AC this run can close alone.
- A per-launch secret/nonce for envelope authenticity — R0's Contract already
  decided "document the residual risk" over a new credential mechanism.
- **Activation-record garbage collection** (code review, LOW): one record
  file plus a `.consumed` sidecar accumulates per session under
  `.shipwright/runtime/codex-activation/` with no pruning of expired
  entries. Low severity (gitignored runtime state, one small file per
  session, `read()`/`consume()` already fail-open past expiry regardless of
  whether the stale file is deleted) — deferred, not fixed here.

## Design Notes

No UI surface, but the envelope grammar (M7) itself was underspecified past
"a closed grammar" until now — a build agent correctly stopped rather than
guess it (2026-09-22), since the wire format is load-bearing for the
accidental-collision defense the Out of Scope nonce-rejection relies on.
Decided here, ASCII-only (this campaign already hit enough Windows
cmd.exe/codepage quoting surprises — see R1b — to avoid non-ASCII markers on
principle) and single-line (parse must reject anything the marker's own
regex can't match without `re.DOTALL`, so a reflowed/line-wrapped paste of a
genuine envelope is treated as absent, not fuzzy-matched):

**Literal wire form**, produced verbatim by `compose()`:
```
[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=<skill_id>|args_b64=<b64url-json-no-padding>]
```
- `skill_id` charset: `[A-Za-z0-9_.:/-]+` (covers both bare ids and
  `plugin:skill`-shaped ids already used elsewhere in this repo).
- `args_b64`: `json.dumps(args, sort_keys=True, separators=(",", ":"))` →
  UTF-8 → `base64.urlsafe_b64encode` → `=` padding stripped. Empty string is
  valid and means `{}`.
- `parse(prompt_text) -> Envelope | None`, **never raises**: regex-search
  (not anchor-required — the marker can sit inside a larger first prompt)
  for exactly one match of
  `\[SHIPWRIGHT-CODEX-ACTIVATE-v1\|skill_id=([A-Za-z0-9_.:/-]+)\|args_b64=([A-Za-z0-9_-]*)\]`
  on a single line. **Two or more matches in the same text → `None`**
  (ambiguous input is rejected outright, not resolved by taking the first —
  closed-grammar discipline over untrusted/attacker-influenceable text). Then
  base64-decode (re-padding to a multiple of 4 with `=`) and `json.loads`;
  any failure at any step (bad base64, bad JSON, decoded value not a JSON
  object) → `None`. Success → `Envelope(skill_id=str, args=dict)`.
- `compose(skill_id, args) -> str` validates `skill_id` against the same
  charset and **raises `ValueError`** on a bad id — this side is
  programmer-controlled (the terminal helper's own call site), so failing
  loudly here is correct; only `parse()`'s input is untrusted and must never
  raise.
- Round-trip: `parse(compose(skill_id, args)) == Envelope(skill_id, args)`
  for any valid `skill_id`/JSON-serializable `args` dict.
- Malformed-input test matrix: no marker present → `None`; marker split
  across a line break (reflowed paste) → `None`; two markers in one text →
  `None`; marker present but `args_b64` is invalid base64 → `None`; valid
  base64 but not JSON → `None`; valid JSON but not an object (e.g. a bare
  list/number) → `None`.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| terminal helper (mints envelope in the first prompt text) | grammar module (parses); `UserPromptSubmit` hook (calls the grammar module, mints the activation record) | first-prompt-embedded closed grammar (M7) — compose + parse live in one shared module, round-trip tested |
| `UserPromptSubmit` hook (mints `active.json` with `armed: true`, or an `armed: false` marker) | `PreToolUse` hook (consumes via exclusive-create of a `.consumed` marker — one-time claim, not overwrite) | activation record — gitignored `.shipwright/runtime/`-style path, schema versioned, keys: session_id+turn_id+cwd+generation+expiry |

*(The Codex Stop-gate boundary row — reading `shipwright_events.jsonl` for
`work_completed[source=iterate, adr_id=run_id]` — is deferred to R2b along
with the mechanism itself; the field-name correction it already surfaced
(`adr_id`, not `run_id`) is recorded here for whoever builds it.)*

## Confidence Calibration

{Filled at Step 7.5, before F0.}

## Verification (medium+)

- **Surface:** cli
- **Runner command:** THREE separate invocations, one per test root (this
  repo's hard one-root-per-process rule — `shared/tests`,
  `plugins/shipwright-iterate/tests`, and `shared/scripts/tools/tests` are
  three different roots and a combined invocation is refused by the
  repo-root `conftest.py`, exit 4; the single-command form this line
  originally had was never actually runnable and is corrected here,
  2026-09-22; the third root was missing entirely until the external
  code review caught it, glm low, 2026-09-23 — it covers the launcher/
  bundle-build/helper-CLI surface, not just the record/hook logic the
  other two roots exercise):
  `uv run pytest shared/tests/test_codex_envelope_grammar.py shared/tests/test_codex_activation_record.py shared/tests/test_codex_activation_record_consume.py shared/tests/test_codex_activation_record_validation.py -v`
  and
  `uv run pytest plugins/shipwright-iterate/tests/test_codex_pretooluse_denial.py plugins/shipwright-iterate/tests/test_codex_pretooluse_tokenization.py plugins/shipwright-iterate/tests/test_codex_pretooluse_matcher.py plugins/shipwright-iterate/tests/test_codex_hooks_noop_under_claude.py plugins/shipwright-iterate/tests/test_codex_hooks_ac0_combined.py -v`
  and
  `uv run pytest shared/scripts/tools/tests/ -v` (the whole root, not the
  three files individually — `test_codex_hook_inventory_runtime_scope.py`
  imports a sibling `_bundle_fixtures` module via the directory being on
  `sys.path`, which individual-file invocation does not guarantee)
  (file list also grew via three bloat-gate splits during the build,
  2026-09-22 — each split kept its tests, just relocated them) — plus the
  live-probe script run against a throwaway scratch repo (not this monorepo)
- **Evidence path:** `.shipwright/planning/iterate/iterate-2026-09-20-r2-m3-hook-parity-iterate-only/live-probe-*.jsonl` (mirrors R0's own evidence convention)

## Internal Plan Review (opus-plan-reviewer)

- **Ran:** yes
- **Severity:** high
- **Summary:** The chosen mechanism (R0's) is sound and reuses the right
  primitives, but the plan as first drafted would have shipped a gate that is
  green in fixtures and inert-or-harmful in production: AC1a's deny-on-absent
  contradicted R0's own fail-open contract; wiring into the shared
  `hooks.json` would have silently gated Claude too; and the Stop gate was
  self-satisfying against `iterate_stop_finalize.py`'s own repair pass.
- **Findings:** (13 total — 7 high, 5 medium, 1 low; all fixed, none
  disclosed/declined)
  1. [high, fixed] Deny-on-absent vs. R0's fail-open contract — added
     explicit `armed: true|false` marker; AC1a restated with an unarmed
     fixture.
  2. [high, fixed] Shared `hooks.json` would gate Claude too — added `AC0`:
     every new hook script no-ops without `PLUGIN_ROOT` (Codex-only env
     signal).
  3. [high, fixed] Stop gate self-satisfying against
     `iterate_stop_finalize.py`'s repair pass — reordered the new gate FIRST
     in the Stop chain; it performs the same repair itself and only blocks
     if that repair genuinely fails, matching AC1b/AC3's "blocked or
     continued" wording exactly.
  4. [high, fixed] No loop-breaker on the first-ever blocking Stop hook in
     this repo — added a fail-open cap/`stop_hook_active`-equivalent check
     as its own AC1b/AC3 fixture, contingent on the payload-capture probe.
  5. [high, fixed] Two required live proofs were missing (Codex honoring
     `Stop` block; sequential same-group hook ordering) — added as probes
     (c)/(d), with an explicit "must not ship armed if these fail" rule.
  6. [high, fixed] Event-matching predicate named the wrong field
     (`run_id` vs. actual `adr_id`) and didn't specify which root's
     events.jsonl to read — corrected in Affected Boundaries and AC1b/AC3.
  7. [high, fixed] Cited atomic-write primitive (`replace_retrying`) is
     overwrite semantics, not an exclusive one-time claim — switched to
     exclusive-create (`open(..., "x")`) of a `.consumed` marker.
  8. [medium, fixed] No round-trip test for the terminal-helper→grammar
     boundary — grammar compose+parse moved into one shared module in Mini-
     Plan step 1, round-trip tested before either hook is written.
  9. [medium, fixed] TDD ordering broke at steps 3-4 (fixtures encode a
     payload shape no probe had captured yet) — added a payload-capture
     probe as its own live-proof AC, run before the fixtures are finalized.
  10. [medium, fixed] No PreToolUse matcher inventory / no
      local-function-tool-only caveat on AC1a — both added.
  11. [medium, fixed] Substring match on shell command text (false-allow via
      `echo`, false-deny on legitimate variants) — Mini-Plan now specifies
      tokenized (shlex) + basename matching.
  12. [medium, fixed] Hook cost on every tool call, undocumented — Mini-Plan
      specifies `uv run --no-project` + O(1) short-circuit before any
      heavy import.
  13. [medium, fixed] Self-mint threat model undocumented; expiry/generation
      undefined; AC5 fixture would have cross-imported five plugins'
      `scripts` packages (ADR-044/045 collision) — threat model added to the
      Mini-Plan design notes, expiry pinned with fail-open-on-expired
      behavior, AC5 verification changed to per-plugin suite runs instead of
      a new cross-importing test file.
  14. [low, fixed] Unarmed-launch visibility and `/hooks` trust confirmation
      (both explicitly named by R0/parent-spec as R2's job) were missing
      from the ACs — both added.
- **Known limitations:** none disclosed — every finding was integrated.
- **Status:** 13 fixed, 0 disclosed, 0 declined

## External Plan Review

- **Ran:** yes (Branch A, driver=claude, providers glm + openai)
- **Verdicts:** glm=approve · openai=revise (one step apart per the
  contradiction check — not a hard conflict; both integrated regardless)
- **Findings:** 13 total (glm: 6 — 3 medium/edge-case, 1 medium/risk, 2 low;
  openai: 7 — 3 high, 3 medium, 1 low). All fixed, none disclosed/declined —
  see the corrected design in the Mini-Plan (§1, §2) for exactly what
  changed against each finding.
  - [high, fixed] Mint hook overwrote the armed marker on every prompt
    instead of only the first — switched to exclusive-create-once.
  - [high, fixed] Stop gate would have enforced against unarmed/unrelated
    sessions — now validates a matching, unexpired armed record first.
  - [high, fixed] `run_id` binding to the Stop-gate's completion-event check
    was undefined — now explicit: resolved independently of the activation
    record (which cannot carry one at mint time), via the existing
    worktree-pointer/latest-entry lookup.
  - [medium, fixed] Shell-command-only tool matching left non-`Bash` local
    tools free to bypass — added a per-tool-class allow/deny matrix,
    unknown classes deny by default while armed-and-unsettled.
  - [medium, fixed] No concrete fallback if the Stop-block/ordering live
    probes fail — added a shipped, defaulted-off capability flag, flipped
    on only by recorded evidence.
  - [medium, fixed] Loop-breaker counter had no defined identity/atomicity/
    reset — scoped to `(session_id, generation)`, its own file, monotonic.
  - [medium, fixed] `PLUGIN_ROOT` bare-presence check is a fragile Claude/
    Codex boundary — now also verifies the value resolves to the built
    bundle's own root marker.
  - [low, fixed] Deny reason didn't name the runnable fix — now includes the
    exact setup command.
  - [low, fixed] Record consume-vs-delete lifecycle and counter storage were
    underspecified — consume marks (sibling `.consumed` file), never
    deletes; counter lives in its own file.
  - [low, fixed] `iterate_stop_finalize.py`'s behavior under a real
    Codex-shaped Stop payload was untested — added to the payload-capture
    probe (Mini-Plan step 2).
  - [low, fixed] Threat model (cooperative-enforcement, not adversarial) and
    the terminal helper's process-launch method (argv, not shell string)
    were undocumented — both added to the docs delta.
- **Status:** 13 fixed, 0 disclosed, 0 declined

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-20-r2-m3-hook-parity-iterate-only/architecture_brief.md`
- **Verdicts:** glm=revise · openai=revise
- **Smallest thing that would do (per reviewers):** Option B from the brief —
  ship only the armed `PreToolUse` first-step gate (plus its supporting
  activation-record/grammar machinery and the hook-inventory audit); keep
  the existing finalization repair pass and dashboard nudge exactly as they
  are; drop the Stop gate from this run entirely.
- **Findings:**
  - [proportionality, high (glm) / medium (openai)] The Stop gate's actual
    increment over what already exists is only the *blocking* behavior — its
    repair step is a re-call of the same function `iterate_stop_finalize.py`
    already calls, and the webui completion-oracle already detects the
    failure it guards against. Its full permanent cost (a loop-breaker with
    its own identity/atomicity/reset semantics, a capability flag defaulted
    off, this repo's first-ever blocking Stop hook, a chain-ordering
    constraint ahead of an existing hook) buys only "the turn ends slightly
    later or not at all" on top of a repair that already happens anyway.
    **Accepted and fixed:** cut from R2, deferred to R2b in full.
  - [simpler-alternative, medium (glm)] The design's own "must not ship armed
    if the live probes fail" rule, plus the off-by-default capability flag,
    already concedes the Stop gate may ship inert — i.e. R2b's own work,
    built early and parked. **Accepted and fixed:** same disposition as
    above.
  - [existence, low (glm)] The PreToolUse gate's own supporting machinery
    (activation record, exclusive-consume marker, grammar module) is real
    new standing state, but is the proportionate minimum a fail-open,
    session-scoped deny hook needs, with its fail-open boundaries pinned by
    the ACs rather than left emergent. **Kept as proposed** — this is the
    half both reviewers approved building now.
- **Reconciliation:** The mini-plan's own Alternative-approach section had
  not considered "build only the PreToolUse half, defer the Stop gate" as an
  option at all — the brief process surfaced it precisely because the brief
  omits rejection reasoning and lets the reviewer reason from the problem
  fresh. Both external plan reviewers (Branch A, above) had already spent
  real effort hardening the Stop gate's design (mint-once, armed-record
  validation, run_id binding, loop-breaker identity) before this pass asked
  whether it should exist at all — that work is not wasted: it is now R2b's
  starting design, informed by real findings instead of a blank page, and by
  this run's own live payload-capture evidence once gathered. Operator was
  not asked to arbitrate a `reject` (neither verdict was reject) — both
  `revise` verdicts pointed at the same cut, so it was integrated directly,
  consistent with how every other `revise` finding in this run was handled.
