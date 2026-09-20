# Iterate Spec: r0-resolve-1a-envelope-delivery

- **Run ID:** iterate-2026-09-20-r0-resolve-1a-envelope-delivery
- **Campaign:** codex-plugin-execution-reliability / sub-iterate R0
- **Type:** change
- **Complexity:** medium (overridden from auto-classified `small` — the
  sub-iterate spec itself mandates the medium+ External Architecture Review
  as this decision's sign-off; see Model/Process Notes below)
- **Status:** implemented

## Goal

Resolve `Spec/codex-plugin-execution-reliability.md` §1a/§5 Phase 0.5: choose
which of Resolution B's two envelope-delivery variants mints the pre-worktree
M7 activation envelope before Codex's first turn (webui adapter-emits vs. a
monorepo-only CLI helper), and answer Resolution A's two falsification
questions for the post-worktree case (operator-poking-by-hand false-arm;
cross-runtime false-arm with a Claude session in the same worktree). Per the
2026-09-20 amendment, treat this as a feasibility gate: prove live, against
installed Codex CLI 0.155.0, that the PreToolUse enforcement mechanism the
whole resolution depends on actually works the way the spec's prose assumed.
Output is a decision ADR — no production code ships from this iterate.

## Acceptance Criteria

- [x] ADR records which Resolution B variant is chosen and why
- [x] Cross-runtime false-arm question (Claude vs Codex sharing a worktree) is
      answered with evidence, not assumption — **re-derived after two review
      rejections; see "Revision history" below**
- [x] Operator-poking-around-by-hand false-arm question is answered
- [x] Phase 2 (R2/M3) can be scoped precisely from this decision without
      further architectural ambiguity — closed by the "Contract for R2"
      section added after review
- [ ] Live proof (not just docs-reading) that a PreToolUse-class hook against
      the real tool names (`exec_command`/`Bash`, `collaboration.spawn_agent`,
      etc.) actually DENIES a call, **with the hook's trust state confirmed**
      — **NOT met.** Deny was proven only under
      `--dangerously-bypass-hook-trust`; trust itself was never confirmed via
      `codex /hooks` (TUI-only, not scriptable). Left unchecked deliberately —
      see the blocking finding this triggers, immediately below.
- [x] If live proof fails or trust cannot be confirmed cheaply, that failure
      is recorded explicitly as a blocking finding for R2 — **this is that
      record:** *BLOCKING FINDING FOR R2 — the only Codex-side deny ever
      observed used `--dangerously-bypass-hook-trust`; a normally-trusted,
      non-bypassed bundled hook has never been proven to fire at all. Given
      an untrusted hook is silently inert (probe 1) with zero signal anywhere
      in the event stream, R2's M3 build is **not done** until it proves deny
      once through ordinary interactive `/hooks` trust in a scratch repo
      (cheap, minutes) — or M9 (hook-trust readiness, excluded from this
      slice per parent spec §2) is reopened for at least this one check.
      Do not let R2 ship on the strength of this run's bypass-mode proof
      alone.*

### Revision history

This spec originally recorded a file-based envelope design and checked all
six ACs. Both the internal plan review (`opus-plan-reviewer`) and an
additional adversarial pass with `gpt-5.6-sol` (run at the operator's request,
outside the standard cascade — see "Model/Process Notes") independently
**rejected** that draft on convergent grounds: the envelope was described as
"scoped to cwd + session identity" while being minted *before* a session
exists, which is impossible as stated, and the same design's own
"runtime-neutral, register in both hooks.json" claim invalidated its own
cross-runtime false-arm defense. Both reviews are preserved in full at
`gpt56sol-review-findings.md` and `opus-plan-reviewer-findings.md` (this
directory) rather than summarized away. The `## Decision`, `## Affected
Boundaries`, `## Live Feasibility Probes`, and `## Confidence Calibration`
sections below are the **post-review revision** — a live probe (run 7) was
added specifically to test the corrected design before re-asserting any
claim about it.

## Decision

**Resolution B — delivery variant: the envelope is prompt-borne and minted
reactively by `UserPromptSubmit`, once a real session exists — not a
free-standing file minted before one does.**

The first draft of this section proposed a CLI helper that pre-writes a file
"scoped to cwd + session identity" before Codex starts. Both review passes
(`opus-plan-reviewer`, then an additional `gpt-5.6-sol` adversarial pass)
independently rejected this: **at mint time there is no session to scope the
file to** — the file can only be keyed by cwd, which is exactly the "latest
by cwd" lookup M3's own text explicitly forbids ("Helpers look up only the
exact token, never 'latest by cwd/session'"). Re-reading M7/M3 after that
rejection: they never actually required a pre-session file. M7 names the
envelope as **prompt-borne** ("the adapter emits a closed, validated
Shipwright invocation envelope carrying `skillId` and arguments"; "Direct CLI
usage gets the same envelope from a documented helper") and M3 says
`UserPromptSubmit` — which fires *after* the session exists, with real
`session_id`/`turn_id` already in hand — is what "creates an atomic turn
record... mints an unguessable activation token." The file-based design was
an unforced complication that then had to invent a binding problem M3's own
design never has.

**Corrected mechanism, live-proven (run 7):**

1. **Deliver** — the envelope is the *first prompt text itself*: a
   documented helper (terminal) or the webui/Desktop launch composition
   embeds a closed, recognizable grammar (per M7 — `skillId` + arguments) as
   part of what gets sent as the session's first message. No pre-existing
   file, no pre-session binding problem — the envelope and the session it
   belongs to are, by construction, the same event.
2. **Mint** — `UserPromptSubmit` reads that first prompt (plus the real
   `session_id`/`turn_id`/`cwd` its own payload already carries — confirmed
   live, run 7: `{"session_id":"01a0bf99...","turn_id":"01a0bf99...",
   "cwd":"...","hook_event_name":"UserPromptSubmit","prompt":"..."}`),
   validates the envelope grammar, and mints the activation token/record —
   now genuinely scoped to a real session, because one exists at this exact
   point. **Live-proven:** a probe `UserPromptSubmit` hook returned
   `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit",
   "additionalContext":"R0_PROBE_MINTED_TOKEN=R0PROBE-TOKEN-01a0bf99"}}`
   (the suffix derived from the real `session_id`), and the model's own
   response quoted that exact token back verbatim — `additionalContext`
   delivery genuinely reaches the model, not just the hook's own stdout.
3. **Consume** — `PreToolUse` denies unless the record minted in step 2 is
   present, valid, and unconsumed for the current `session_id`/`turn_id`.
   **Not independently live-proven this run** — probe 2 proved deny with a
   static always-deny hook; step 2's mint was proven separately; the two
   were never chained in one live turn (mint → store → a *later* `PreToolUse`
   in the *same* turn reads that specific record and allows/denies
   accordingly). This is the one piece of the corrected chain R2 must prove
   before M3 ships — see "Contract for R2".

The mechanism design covers all three launch surfaces, each via a thin
adapter that only has to get the envelope into the first prompt, not
implement any new storage/lookup logic — but **R2's own scope is
terminal-only, per the Architecture Review pass**, not all three:

- **Terminal (direct CLI):** a documented helper composes/prints the
  envelope-carrying first message; the operator (or a thin wrapper) passes it
  as `codex`'s initial prompt. **This is R2's entire producer scope — its
  full definition of done, not just the first of several producers R2
  builds.** The campaign's own hand-driven R1–R4 dogfood the mechanism via
  terminal first, and nothing else needs it yet.
- **`shipwright-webui` (Codex Light):** confirmed by reading
  `Spec/codex-light-webui.md` (§1/§2.1/§2.3 — "Headless `codex exec`...
  driven by an external" harness; `pty-manager.spawn` spawns `codex exec`
  directly) that webui already composes the exact prompt text it sends as
  the first message, so embedding the envelope grammar there would be a
  small addition when it happens. **Explicitly deferred out of R2 by the
  Architecture Review pass:** the record format's opt-in, fail-open nature
  (named gap #2 above) means the guarantee it delivers is proportional to
  "cannot proceed *when armed*," not an absolute — building three producers,
  a state-transition table, and a matcher inventory up front for that
  guarantee was flagged as disproportionate standing surface. Becomes its
  own later iterate when webui integration is actually needed, not part of
  R2.
- **Codex Desktop app (OpenAI's own native app):** same deferral, and
  additionally the harder case — Shipwright does not compose the first
  prompt there, the operator types it, and two premises remain genuinely
  unchecked (whether the Desktop app loads project-level `.codex/hooks.json`
  at all; whether an operator-typed envelope-carrying line is recognized
  identically to a programmatically-composed one). **Not live-proven,
  operator explicitly declined a dedicated Desktop-app test this run** —
  listed as *unverified*, not *covered*, and now also explicitly *not R2's
  problem*: its own future iterate, checked cheaply on first real Desktop
  use.

**Claude-side registration is explicitly out of scope for R2, and a
separate, later decision — not bundled into this one.** The first draft
proposed registering the same consumer logic in Claude's own `hooks.json` as
a "runtime-neutral by design" claim, and used "Claude never loads Codex's
`hooks.json`" as part of the cross-runtime false-arm defense in the same
breath — a direct contradiction the reviews caught (the defense stops being
true the moment Claude gets its own copy). Separately, the campaign's own §4
AC5 and R2's own sub-iterate spec (`R2-m3-hook-parity-iterate-only.md`,
"Register ... for Codex") both scope Claude as *unaffected*, not *extended*.
**What's still true and worth recording:** grepped every
`plugins/*/hooks/hooks.json` directly (2026-09-20) — Claude-side Shipwright
has **no** `PreToolUse` hook today denying a fresh iterate's first tool call
unless it is `setup_iterate_worktree.py`; only `shipwright-build` (Bash
command validation) and `shipwright-compliance` register `PreToolUse` at all,
neither for this purpose. So AC1a's guarantee is genuinely new for both
runtimes, and the parent spec's §6 is right to flag it as worth not hiding —
but "worth naming as a future option" and "build it now, in R2" are
different claims, and only the first is R0's to make. If Claude-side parity
is wanted later, it is its own scoped iterate, informed by whatever R2
actually builds — not decided here.

**Resolution A — falsification, corrected.** The original §1a prose
described the post-worktree signal loosely as "cwd is a `.worktrees/<slug>`
tree with a live run_id" — the weaker, spoofable framing the second parent-
spec review flagged. M3's own text already specifies the actual signal as an
activation record carrying `session_id`, `turn_id`, `cwd`, `generation`, and
`expiry` — the corrected mechanism above *is* that record, minted by
`UserPromptSubmit` in step 2. Reasoning is **analytic, not empirically
tested against a live two-actor fixture** (see Confidence Calibration —
these ledger rows were relabeled after the earlier draft mislabeled them
`covered-by-existing-test` with no such test existing):

- **Operator poking around by hand — including resuming the *same* session
  after real work finished (a case the first draft missed).** An ad-hoc
  interactive turn never submitted the envelope-carrying first prompt, so no
  record was minted for it — covers a fresh unrelated session. The
  *same*-session case (operator continues chatting in a session whose
  activation is `active`/unconsumed) is **not** closed by this reasoning
  alone; it needs the record's documented `consumed` state — once the gated
  action happens (or the turn legitimately ends), the record moves out of
  `active`, so a later, unrelated ask in the same session finds no live
  grant. Genuinely contingent on R2/M3 implementing that state machine
  correctly, per M3's own acceptance bar ("missing/stale/conflicting records
  never cause phase guessing") — not new scope for R0 to invent, but not
  something R0 can call closed without R2 either.
- **Cross-runtime (Claude session in the same worktree):** with Claude-side
  registration now explicitly deferred (above), the practical answer is
  simple — a Claude session never runs Codex's `hooks.json` at all today, so
  there is no shared consumer to false-arm. If Claude-side registration is
  ever built later, the honest answer changes to: a Claude session *can* see
  the same on-disk record if one is ever introduced, and safety would then
  depend on one-time consumption + expiry + an explicit runtime-identity
  field in the record — a requirement for whoever builds that future
  iterate, not something already proven here. **Scope of this answer, stated
  narrowly (Branch A external review):** this closes the *shared-consumer
  false-arm* question only — it is not a claim that Claude gets equivalent
  AC1a-style protection; Claude remains as unenforced after this decision as
  before it, and closing that gap is the separate parity decision named
  above, not a side effect of this one.

**Named gap this decision creates (complete list, corrected):**

1. Only direct-CLI-launched Codex sessions get AC1a's pre-worktree denial
   after R2 — webui and Desktop adapters are explicitly deferred to their
   own later iterates (Architecture Review pass), not part of R2's scope.
2. **Arming is opt-in, and a forgotten mint is silently indistinguishable
   from today's unenforced behavior.** M3's own documented fail-open
   ("missing/stale/conflicting records never cause phase guessing") means a
   session launched *without* the envelope-carrying first prompt behaves
   exactly like an unguarded session today — the headline claim "Codex
   cannot proceed past worktree setup without it having actually happened"
   is, in practice, "cannot proceed *when the launcher remembered to arm
   it*." R2 should make an unarmed launch **visible** (e.g. `SessionStart`
   warns when no envelope was recognized in the first prompt) rather than
   leaving it silent, even though fail-open is the correct default per M3.
3. Hook-trust inertness (the blocking finding in Acceptance Criteria above) —
   the whole mechanism can be installed and silently inert if the bundled
   hook is never actually trusted, and nothing in this slice detects that.
4. The mint→store→consume chain (step 3 above) is not yet proven end-to-end
   in one live turn.
5. The subagent tool-name asymmetry (probe 3 below) means the matcher
   inventory needs a per-tool-class entry, not one universal rule.
6. Probe 6's `--ephemeral` limitation constrains any stateless subagent
   fixture R3/M4 might want to build.

This is a smaller, more honest gap list than the first draft's single line —
seven items were hiding behind "webui/Desktop not built yet," corrected after
two independent reviews.

## Contract for R2 (added after review — AC4's actual content)

Undecided items the first draft left implicit, now pinned as defaults for R2
to build against (or explicitly revise, not silently fill in):

- **Envelope location:** a `.shipwright/runtime/`-style path, gitignored —
  never committed, never swept by `git add -A` (this repo's own documented
  `git-add-all-sweeps-derived-snapshots` footgun applies here too).
- **Schema:** versioned from day one (cross-repo consumers: webui, monorepo,
  eventually Claude if ever extended) — `skillId`, arguments, a schema
  version field, mint timestamp.
- **Activation-record scoping keys:** `session_id` + `turn_id` + `cwd` +
  `generation` + `expiry` (M3's own fields — not cwd alone).
- **Consumption semantics:** atomic one-time consume on the gated action;
  record moves to `consumed` and cannot arm a second call. **Storage
  mechanism unresolved, named explicitly (Branch A external review, both
  reviewers):** `UserPromptSubmit` and `PreToolUse` are separate hook
  invocations (possibly separate processes) sharing durable state, so R2
  must pick a concurrency-safe atomic-consume mechanism (e.g. atomic file
  rename on a Windows-safe path, reusing the existing main-root/cwd
  resolver) rather than a plain read-then-write. No probe in this run
  exercised concurrent turns or the mint→store→consume chain end-to-end
  (ledger row 10) — **R2 cannot claim AC1a met until it does; this is a
  second blocking precondition alongside the hook-trust one above, not an
  optional nice-to-have.**
- **Envelope authenticity — resolved by the Architecture Review pass (both
  reviewers converged, independently, on the same answer):** the envelope is
  plain first-prompt text, which is inherently model-visible and
  user-pasteable — a pasted log, a README example, or an injected prompt
  containing the closed grammar could cause `UserPromptSubmit` to mint a
  record the operator never intended. Nothing in this decision distinguishes
  a genuine launch composition from an envelope-shaped string that merely
  *appears* in a prompt. **R2 takes option (b):** accept and document the
  residual risk that the mint is armable by prompt content, mitigated only
  by one-time-consume + expiry — not option (a), a per-launch secret/nonce.
  A nonce would be a new standing credential mechanism (generation,
  storage, validation, its own failure modes) built to harden a channel
  that already fails open by design and is independently documented
  (Codex's own hosted-tools caveat above) as "a guardrail, not a complete
  enforcement boundary" — disproportionate to what the guarantee actually
  delivers. This is a decision, not an open fork left to R2.
- **First-prompt-only recognition scope (Branch A external review, glm):**
  `UserPromptSubmit` fires on *every* prompt in a session, not only the
  first. This decision's operator-poking-by-hand analysis (Resolution A)
  assumes the envelope is recognized on the session's first eligible prompt
  only; whether a later, mid-session prompt can re-arm after the record was
  already consumed is undefined here and load-bearing for that analysis to
  keep holding. R2 must define re-arm semantics explicitly (allowed under
  what conditions, or denied outright) rather than let it fall out of
  whatever the implementation happens to do.
- **Session-mismatch behavior:** a record present but not matching the
  current `session_id`/`turn_id` is treated as absent (fail-open per M3), not
  as an error and not as a match.
- **Windows cwd normalization:** case, drive-letter vs. POSIX form, and
  main-root vs. `.worktrees/<slug>` resolution — a documented footgun in this
  repo's own main-root-resolver history; reuse that resolver, don't
  reinvent.
- **Matcher inventory is per-tool-class, not universal:** `Bash` is aliased
  by Codex's hook layer; `spawn_agent` is *also* matched by an `"Agent"`
  matcher per official docs (corrected below — the first draft's probe 3
  conclusion that no such alias exists was wrong) — but the two tool
  classes still need their own inventory rows, not one shared assumption.
- **Enforcement-boundary caveat, stated honestly:** Codex's own docs name
  *hosted tools* (e.g. `WebSearch`) as bypassing `PreToolUse` entirely,
  with the explicit framing "a useful guardrail, not a complete enforcement
  boundary." AC1a's guarantee holds for the local function-tool path
  `setup_iterate_worktree.py` itself uses, not as an absolute claim over
  every conceivable Codex tool call.
- **Hook-trust precondition:** prove deny once through ordinary,
  non-bypassed `/hooks` trust in a scratch repo before M3 is considered done
  (the blocking finding above).
- **Terminal-helper invocation shape (Branch A external review, openai):**
  the helper's exact contract is undefined here and must be R2's, not
  discovered ad hoc — one supported invocation shape (how the envelope text
  reaches `codex`'s first prompt: argv, stdin, or an interactive paste),
  explicit handling for Windows shell quoting of the envelope grammar, and
  an explicit reject/warn when the helper is pointed at an **existing**
  session or a **non-first** prompt (arming mid-session is not a supported
  use of this mechanism per the first-prompt-only scope above).
- **Per-session/turn state-transition table (Branch A external review,
  openai):** "atomic one-time consume" above names the end states, not the
  full machine. R2 must define the table covering: duplicate envelope
  submission in the same turn, a failed gated tool call after the record
  was already consumed (does the operator get a way to re-arm, or must they
  restart?), expiry mid-turn, and concurrent/interrupted turns racing the
  same record. Left undefined, "atomic consume" is a name for a requirement,
  not the requirement itself.

## Spec Impact

- **Classification:** none
- **NONE justification:** This iterate produces an architecture-decision ADR
  and a feasibility-proof record. It does not add, modify, or remove any
  Shipwright FR — `Spec/codex-plugin-execution-reliability.md` is itself a
  held-in-reserve design document (not yet planned/built), and R1–R4 (the
  sub-iterates that will actually build M1–M5) are the ones that will touch
  FR-bearing code and spec files, gated on this decision.

## Out of Scope

- Building any of M1–M5 (that is R1–R4, gated on this decision)
- M9 (hook-trust readiness automation) — explicitly excluded by the parent
  spec §2; this iterate manually confirms trust behavior instead, per the
  amendment's own instruction
- Resolving `launcher-codex.ts`/`buildCodexCommands` code changes — those
  belong to whichever R1–R4 sub-iterate ends up implementing the chosen
  Resolution B variant

## Design Notes

n/a — no UI surface.

## Affected Boundaries

**Not n/a — corrected after review.** This decision's whole content is a new
serialized boundary: an activation-envelope/record format that a launch
adapter (producer) writes and `UserPromptSubmit`/`PreToolUse` (consumer)
reads, across up to three launch surfaces and two repos once R2+ builds it.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| terminal helper / webui launch composition / (future) Desktop pre-step | `UserPromptSubmit` hook (mints record from it) | first-prompt-embedded closed grammar (M7) |
| `UserPromptSubmit` hook (mints) | `PreToolUse` hook (consumes) | activation record — schema pinned in "Contract for R2" below |

No production code implementing either side ships from *this* run — R0 is
the design decision, R2 builds it — so there is no boundary in *this diff*'s
own changed files, but marking this `n/a` (the first draft's framing)
understated what R2 inherits. The live probes below write to a throwaway
scratch git repo outside this monorepo (`{scratchpad}/codex-hook-probe/`);
nothing from that probe ships in this diff either.

## Live Feasibility Probes (Codex CLI 0.155.0, Windows)

All 7 probe runs (`run1.jsonl`...`run7_ups.jsonl`) ran against a throwaway,
ephemeral scratch git repository created for this purpose
(`{scratchpad}/codex-hook-probe/`), never against this monorepo or the
operator's real projects. Four runs (2, 4, 6, 7) required
`--dangerously-bypass-hook-trust`; the operator explicitly approved each of
those calls in-session (Claude Code's own safety classifier auto-blocks that
flag by default) — approved separately for the original PreToolUse-deny
probes and again, after the redesign, specifically for probe 7's
`UserPromptSubmit`-mint test.

1. **(run1) Untrusted hook is silently inert.** A `.codex/hooks.json`
   PreToolUse hook matching `Bash`, installed but never reviewed/trusted,
   produced *zero* observable effect: no log entry from the hook script, no
   denial, no warning anywhere in the `--json` event stream, and the shell
   command ran normally. `codex doctor` has no hook-trust section at all
   (checked directly — `doctor_full.txt`, grepped for "hook", zero matches).
   The only documented non-interactive lever is `--dangerously-bypass-hook-trust`;
   there is no documented non-interactive way to *query* trust state, only to
   *bypass* the check. This matches (and sharpens) the parent spec's M9
   claim ("documented noninteractive trust-status interface does not
   exist") — it is not merely undocumented, there is empirically no such
   interface at all as of 0.155.0. **This is why the trust-confirmation AC
   above is unchecked and carries a blocking finding for R2** — every deny
   this run observed ran under bypass, never under confirmed trust.
2. **(run2) PreToolUse deny is real, not advisory — for the `Bash` tool
   class.** Under bypass, the same hook returning
   `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"R0 probe: denying tool_name=Bash"}}`
   produced a genuine block: the model's own turn reported *"The command was
   not run. It was blocked before execution: `Command blocked by PreToolUse
   hook: R0 probe: denying tool_name=Bash. Command: echo hello-from-codex-probe-2`"*
   — the shell command never executed. The hook payload's `tool_name` was
   literally `"Bash"`. **Scoped claim, corrected from the first draft:** this
   proves deny works for the `Bash` class under bypass; it does not, by
   itself, prove deny for `spawn_agent` (see probe 4) or under normal
   (non-bypassed) trust (see probe 1 / the blocking finding).
3. *(superseded — folded into probes 2 and 4; kept only so the numbering
   below matches the run-file numbering exactly)*
4. **(run3 + run4) Hook-visible tool names, and the `Agent`-matcher
   correction.** Without bypass, a subagent-delegation prompt (no hook could
   fire, since it was untrusted per probe 1) still let the model self-report
   using `collaboration.spawn_agent` (run3). With bypass (run4), the
   `PreToolUse` payload's `tool_name` field was literally
   `"collaborationspawn_agent"` / `"collaborationwait_agent"` — the real
   internal Codex name with the dot stripped, for a call the log-all (allow,
   not deny) hook only *observed*, never denied. **Correction after review:**
   the first draft concluded "no `Agent` alias exists at the hook layer" and
   that a Claude-shaped `Agent` matcher would "silently never match" this
   case — checked directly against the docs a second time, this is **wrong**:
   the docs' own "Tool coverage" table states *"`spawn_agent` also matches
   `Agent`"* — i.e. the matcher string `"Agent"` in `hooks.json` **does**
   catch this tool class, even though the raw payload reports the internal
   name. What was actually proven: the payload's `tool_name` field itself is
   the internal name, not an alias — useful for a hook script's own logging/
   branching — but that is a separate fact from what a *matcher* string can
   catch. What was **not** proven: that a `deny` decision against this tool
   class actually blocks a spawn the way probe 2 proved for `Bash` — only
   observation, not denial, was tested here.
5. **(run5 + run6) Named `.codex/agents/*.toml` profiles do steer
   dispatch — with an `--ephemeral` caveat.** A custom profile
   (`shipwright-r0-probe.toml`, `developer_instructions` requiring a literal
   marker token as the first word of any response) was referenced by name.
   Under `codex exec --ephemeral` (run5), named-profile delegation failed
   outright ("no thread with id ..."). Removing `--ephemeral` (run6, plain
   session-persisted `codex exec`), the same request correctly spawned the
   named profile and its response began `"R0PROBEMARKER 72"` (marker +
   correct product), confirming the profile's `developer_instructions`
   really did steer the spawned session. M4's generated
   `.codex/agents/shipwright-*.toml` files do get read and do steer dispatch
   — but only in non-ephemeral sessions.
6. **(run4, same data as probe 4) `spawn_agent`'s hook-visible arguments
   carry no profile-name field.** `tool_input` for `collaborationspawn_agent`
   exposed `task_name`, `fork_turns`, and an opaque encrypted `message` blob
   — no field a hook could read to identify *which* `.codex/agents/*.toml`
   profile was requested. Profile selection/resolution happens above the
   hook-visible tool-call boundary, so a `PreToolUse` hook cannot gate "only
   trusted named profiles may be spawned" — it can only see that *some*
   spawn happened, not which profile. Real scope boundary for any future
   M9-adjacent enforcement idea, for R3/M4 to design around, not assume away.
7. **(run7) `UserPromptSubmit` sees real session identity and can mint a
   token the model actually receives — the load-bearing proof for the
   corrected Resolution B design.** A `UserPromptSubmit` hook (no
   `PreToolUse` involved) logged its full payload —
   `{"session_id":"01a0bf99-64d5-...","turn_id":"01a0bf99-6a72-...",
   "cwd":"...","hook_event_name":"UserPromptSubmit","prompt":"..."}` —
   confirming the documented `session_id`/`turn_id`/`cwd`/`prompt` fields are
   genuinely present and real (not placeholders) at the exact moment M3 says
   the activation token should be minted. The hook then returned
   `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit",
   "additionalContext":"R0_PROBE_MINTED_TOKEN=R0PROBE-TOKEN-01a0bf99"}}`
   (a token derived from the real `session_id`), and the model's response
   quoted it back verbatim — proving `additionalContext` injection actually
   reaches the model, not just the hook's own log. **Still not proven:** a
   `PreToolUse` hook, later in the *same* turn, independently reading the
   record this step minted (the full mint→store→consume chain) — see
   "Contract for R2".

**Also confirmed via docs, not a live probe:** Codex's own "Tool coverage"
table names *hosted tools* (e.g. `WebSearch`) as **not** covered by
`PreToolUse`/`PostToolUse` at all ("these don't use the local function-tool
hook path"), with an explicit caveat: *"treat tool hooks as a useful
guardrail, not a complete enforcement boundary."* AC1a's guarantee is scoped
to the local function-tool path (`Bash`/`exec_command`, which
`setup_iterate_worktree.py` itself uses) — not an absolute claim over every
conceivable Codex tool call.

## Confidence Calibration

- **Boundaries touched:** the activation-envelope/record boundary named in
  "Affected Boundaries" above (design-only in this diff; R2 implements it).
- **Empirical probes run:** 7 live `codex exec`/`codex doctor` runs against a
  throwaway scratch repo — see "Live Feasibility Probes" above for each probe
  + finding. Run count corrected from the first draft's "5" (which cited
  `run6` while claiming 5 — an internal inconsistency the reviews caught).
- **Test Completeness Ledger:**

  | # | Testable claim | Disposition | Evidence |
  |---|---|---|---|
  | 1 | An untrusted PreToolUse hook is silently skipped (no denial, no signal) | tested | probe 1 — `run1.jsonl`/`.codex/hook_invocations.log` (absent) |
  | 2 | PreToolUse `permissionDecision: deny` blocks tool execution, `Bash` class | tested | probe 2 — `run2.jsonl`: `"The command was not run. It was blocked before execution"` |
  | 3 | Hook-visible `tool_name` for a shell command | tested | probe 2 — `hook_invocations.log`: `"tool_name":"Bash"` |
  | 4 | Hook-visible `tool_name` for a subagent spawn | tested | probe 4 — `hook_invocations_all.log`: `"tool_name":"collaborationspawn_agent"` / `"collaborationwait_agent"` |
  | 5 | `"Agent"` matcher string catches a `spawn_agent` call | tested (via docs, not live matcher run) | probe 4 correction — official "Tool coverage" table: `"spawn_agent" also matches "Agent"`; **not independently live-confirmed with a matcher:"Agent" hook in this run** — carried to R2 as a cheap live check, not asserted as fully proven |
  | 6 | PreToolUse `deny` blocks a `spawn_agent`-class call specifically (not just `Bash`) | untestable-this-run, testable-next | not tested — only observation (probe 4), not denial, was exercised against this tool class; genuinely testable, carried forward to R2/M3 build time rather than untested-and-hidden |
  | 7 | Named `.codex/agents/*.toml` profile actually steers a spawned subagent | tested | probe 6 (run6) — `run6.jsonl`: response begins `"R0PROBEMARKER 72"` (correct product + marker) |
  | 8 | `codex doctor` reports hook-trust state (a non-interactive query path) | tested (negative result) | `doctor_full.txt` — no `hook` section present |
  | 9 | `UserPromptSubmit` payload carries real `session_id`/`turn_id`/`cwd`/`prompt`, and its `additionalContext` reaches the model | tested, with a caveat | probe 7 (run7) — `ups_invocations.log` + `run7_ups.jsonl`: model quoted `R0_PROBE_MINTED_TOKEN=R0PROBE-TOKEN-01a0bf99` verbatim. **Caveat (Branch A external review, glm):** this is the model self-reporting the token, not a structured event-stream field proving the injection channel is distinct from prompt text — a model can echo text present anywhere in what it was given. Acceptable evidence for R0's feasibility-gate purpose; R2's first live check should confirm the token via a structured field (or a token never present in the prompt text) before load-bearing on it. |
  | 10 | Full mint (`UserPromptSubmit`) → store → consume (`PreToolUse`, same turn) chain works end-to-end | untestable-this-run, testable-next | not tested — the two hook types were proven independently (probes 2, 7), never chained; genuinely testable, explicit precondition in "Contract for R2", not silently assumed |
  | 11 | Cross-runtime false-arm risk (a Claude session tripping a Codex-authored durable-state signal) | reasoned, not empirically tested | **relabeled from `covered-by-existing-test` — no such test exists, that was a misuse of the closed vocabulary (caught by both reviews).** Answered analytically: Claude-side registration is explicitly deferred (see Decision), so no shared consumer exists today; if built later, the answer is a design requirement (one-time consume + expiry + runtime field), not a closed fact. No live dual-runtime fixture was built or run. |
  | 12 | Operator-poking-by-hand false-arm risk (incl. same-session resume, a case the first draft missed) | reasoned, not empirically tested | **relabeled, same reason as row 11.** Answered analytically from the activation record's documented `consumed`/expiry state machine (M3's own text) — contingent on R2 implementing that state machine correctly; not something R0 built or probed live. |

- **Confidence-pattern check:** asymptote — this run's own first draft
  already produced one "are you confident?" moment that turned out to hide a
  real hole: two independent reviews (`opus-plan-reviewer`, then an
  additional `gpt-5.6-sol` adversarial pass requested specifically because it
  had already caught a real problem in this same document once) rejected the
  first draft on convergent, substantive grounds — not overlapping noise.
  Per the anti-pattern rule, one more probe (run7) was run specifically to
  re-test the corrected design's own core claim before re-asserting it, and
  it held. Coverage — all 12 ledger rows now disposed: 7 tested empirically
  (rows 1-4, 7-9), 1 tested via docs with a named follow-up (row 5), 2
  explicitly carried to R2 as testable-but-not-yet-tested rather than hidden
  (rows 6, 10), 2 reasoned/analytic with the mislabeled reason_code corrected
  (rows 11-12). **0 rows use `covered-by-existing-test`** (both prior uses
  were the mislabeling the reviews caught) and **0 rows are silently
  "could-test-but-didn't"** — rows 6 and 10 are named as a blocking
  precondition in "Contract for R2", not quietly dropped.

## Internal Plan Review

- **Reviewer:** `opus-plan-reviewer` (medium+, before Branch A/B/C).
- **Verdict on first draft:** REJECT — 12 findings, severity high (7) /
  medium (4) / low (1). Full write-up: `opus-plan-reviewer-findings.md`.
- **Disposition:** all 12 accepted; none declined or disclosed-only. Zero
  carried forward unresolved. Findings 1 and 8 drove the explicit
  blocking-finding-for-R2 on hook trust (Acceptance Criteria, item 5).
  Finding 2, together with live probe 7 (run after this review), drove the
  `UserPromptSubmit`-mint redesign that replaced the impossible pre-session
  file-binding design. Findings 4 and 5 drove scoping Claude-side hook
  registration out of R2 entirely, as a separate future decision. Findings 6
  and 7 drove the new "Contract for R2" section. Findings 3, 9, 10, 11, 12
  drove direct edits to "Named gap", the Confidence Calibration ledger, probe
  numbering, and the Desktop-app framing — all present in this file's current
  `## Decision`, `## Contract for R2`, `## Affected Boundaries`, `## Live
  Feasibility Probes`, and `## Confidence Calibration` sections.
- **Re-check:** the redesigned `## Decision` was not sent back through a
  second `opus-plan-reviewer` pass — the operator-requested additional
  `gpt-5.6-sol` adversarial pass (see Model/Process Notes) independently
  reviewed the same first draft in parallel and converged on the same root
  causes (its findings 1-4 map onto this review's findings 1, 2, 3, 1
  respectively), which is treated as the re-check: two independent reviewers
  on two different models, same rejection grounds, same fix. Branch A/2a
  external review (next step) reviews the corrected design fresh.

## External Review (Branch A)

- **Driver:** `claude` (this session runs under Claude Code) → roster
  `{glm, openai}` (`openai` = identity-locked `gpt-5.6-terra`, not `sol`).
- **Pass 1** (over the first fully-corrected draft, post-Internal-Plan-Review
  and post-`gpt-5.6-sol`): `glm=revise`, `openai=revise`. Both converged on:
  the mini-plan being stale relative to the corrected Decision (probe count
  "5" vs. actual 7, an outdated single-item gap description, `Alternative 3`
  still arguing "build runtime-neutral now" — directly contradicting the
  Decision's explicit Claude-registration deferral); envelope authenticity
  never addressed (prompt-borne text is forgeable by pasted/injected
  content); first-prompt-only recognition semantics and the atomic-consume
  storage mechanism left unstated; webui's "prepend a CLI-helper invocation"
  phrasing risking unneeded `buildCodexCommands` changes.
- **Fix, before pass 2:** mini-plan probe count and gap-list references
  corrected; `Alternative 3` reframed (Codex-only R2 implementation, schema
  versioned for possible future reuse, no Claude build implied); webui
  phrasing changed to "embed the envelope in the already-composed prompt";
  `## Contract for R2` gained four new named items (storage/atomicity
  mechanism, envelope authenticity as an explicit R2 fork, first-prompt-only
  recognition scope, per-session/turn state-transition table) plus the
  mint→store→consume chain named as a **second** blocking precondition
  alongside hook-trust.
- **Pass 2** (over the fixed material, redirected to the canonical payload
  path): `glm=approve` (five low-severity wording refinements only — probe 7
  self-report caveat, local-status/ADR merge-drift risk, ADR list authority,
  Resolution A contingency restated, security-fork framing in the ADR — all
  folded in or noted for the ADR-writing step), `openai=revise` (one
  ambiguity — which Resolution B variant is the required R2 baseline, now
  fixed explicitly to terminal — one status-wording point — fixed, `done` →
  `decision-complete, dependency-blocked` — one request to make the
  authenticity fork an explicit required R2 decision in the ADR, not
  background — already satisfied by the Contract for R2 wording — one
  terminal-helper invocation-shape gap — added — one state-transition-table
  gap — added — and one request to narrow the cross-runtime framing —
  added).
- **Not run a third time:** per SKILL.md, `revise` is not a stop —
  "integrate it like any other finding," the same rule the Architecture
  Review step states explicitly. Every substantive pass-2 finding is fixed
  in this file (Decision, Contract for R2, Confidence Calibration) and the
  mini-plan; the remaining `openai` verdict of `revise` on pass 2 reflects
  wording/explicitness requests that are now satisfied, not an unresolved
  architectural objection — the payload at
  `external-plan-review-raw.json` is pass 2's raw output, recorded as-is;
  this reconciliation is the durable record of what changed after it.
- **Payload:** `external-plan-review-raw.json` (pass 2, the recorded row).

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-20-r0-resolve-1a-envelope-delivery/architecture_brief.md`
- **Verdicts:** glm=approve · openai=reject
- **Smallest thing that would do (per reviewers):** disagreement. `openai`:
  a single `PreToolUse` gate that directly checks the current cwd is an
  already-valid Shipwright worktree — no envelope, no minted record, no
  producer/consumer protocol. `glm`: option B as designed, but with R2
  scoped to the terminal producer only and the authenticity fork resolved
  to "document the risk" rather than "build a nonce."
- **Findings:** `openai` (severity high×2, medium×1) — the whole
  envelope/record protocol is disproportionate to establishing a condition
  ("is this cwd an already-set-up worktree?") that should be directly
  observable from existing state; the mechanism is silently inert until a
  human trusts the hook, with no durable readiness signal; opt-in-per-surface
  enforcement means a missed producer silently restores today's unguarded
  behavior — **rejected-with-reason, see Reconciliation.** `glm` (severity
  medium×2, low×1) — three-surface producer scope is disproportionate to an
  opt-in, fail-open guarantee (**accepted-and-fixed** — R2 scope trimmed to
  terminal-only above); the authenticity nonce option is a disproportionate
  new standing-credential mechanism to harden an already-fail-open,
  guardrail-only channel (**accepted-and-fixed** — option (b) chosen
  explicitly in `## Decision`); hook-trust inertness is a permanent
  "who notices it's broken" hazard, suggest folding an unarmed-launch
  warning and a trust/record-presence check into one liveness signal
  (**disclosed** — a real, cheap-to-build suggestion for whoever implements
  R2's `SessionStart` warning named in gap #2, not something this ADR-only
  run builds; recorded here so R2 doesn't lose it).
- **Reconciliation:** `openai`'s alternative — gate directly on cwd being an
  "already-valid worktree," no minted record — is not a fresh option this
  run failed to consider; it is a **near-restatement of the original §1a
  prose this decision explicitly superseded**. The parent spec's own text
  described the post-worktree signal exactly this way ("cwd is a
  `.worktrees/<slug>` tree with a live run_id"), and an earlier review of
  the *parent spec itself* (predating this run) already flagged that framing
  as the weaker, **spoofable** signal — a `.worktrees/<slug>`-shaped
  directory or a live-looking `run_id` can be created by hand, by a stale
  worktree, or by an unrelated process, without the actual precondition
  (worktree setup genuinely having run and completed) having happened. That
  is precisely why M3 specifies an unguessable, minted, session-scoped
  activation record rather than a directly-observable filesystem/cwd
  predicate — the "simpler" option is simpler because it drops the one
  property (unforgeability) the mechanism exists to add. **Operator decision
  (asked directly, given the reviewer split): keep the current design,
  record why the simpler alternative was rejected (above), and additionally
  trim scope per `glm`'s proportionality findings — R2 ships terminal-only;
  webui/Desktop become separate future iterates; authenticity takes the
  document-the-risk option, not a nonce.** These three scope/wording fixes
  are now reflected directly in `## Decision` and `## Contract for R2`
  above, not left as a dangling disagreement.

Self-Review:
  1. Spec Compliance:    [pass] The decision-drop + spec-ref record the chosen Resolution B variant + rationale, both Resolution A falsification answers, and close the live-feasibility amendment (7 probes); no scope beyond the sub-iterate's 6 ACs.
  2. Error Handling:     [n/a] No code/API routes ship. write_decision_drop.py's own 500-char field guard was hit and handled correctly (--spec-ref), not worked around.
  3. Security Basics:    [pass] No secrets/user input in any artifact. The run's own subject (envelope authenticity) is resolved explicitly in the ADR, not left implicit.
  4. Test Quality:       [n/a] No production code/tests. Confidence Calibration ledger (12 rows) is this run's equivalent instrument.
  5. Performance Basics: [n/a] No code paths.
  6. Naming & Structure: [pass] Decision-drop + spec-ref follow write_decision_drop.py's documented naming and F3's no-ADR-number-in-heading rule exactly (a first draft appended directly to decision_log.md instead — caught by code-reviewer, reverted, fixed to the correct decision-drop-only shape).
  7. Affected Boundaries:[pass] New serialized boundary (activation envelope/record) named with producer/consumer pairs in Affected Boundaries + Contract for R2; no round-trip test yet because R0 ships no implementation — explicitly R2's job (blocking precondition 2), not silently skipped.
  8. Test Hygiene Probe: [pass] `scan_test_hygiene.py --diff` → "no findings", exit 0.

Action: All clear, proceed to commit.

## Model/Process Notes

- **Why medium, not the auto-classified small:** the sub-iterate spec's own
  text states *"This sub-iterate's medium+ external architecture review
  (iterate Step 3.5 Branch A) IS the architectural sign-off for this
  decision — no separate `/shipwright-plan` needed."* Running this at `small`
  would skip that review entirely, contradicting the sub-iterate's explicit
  design. Complexity was overridden by the operator/spec, not by a risk flag.
- **Interview:** skipped beyond the sub-iterate spec's own text — the
  sub-iterate file plus its 2026-09-20 amendment already fully scope this
  decision with explicit ACs; no additional scoping ambiguity remained to ask
  about.
- **Manual sub-iterate stamp:** this run is a hand-driven invocation of a
  campaign sub-iterate (`campaign.md` states *"Not run autonomously — each
  sub-iterate is hand-driven and reviewed individually"*), so F5b's
  `--event-extras-json` carries `"campaign": "codex-plugin-execution-reliability"`
  and `"sub_iterate_id": "R0"` per SKILL.md's Campaign S1 stamp rule.
- **Extra review pass, operator-requested:** in addition to the standard
  cascade (Internal Plan Review via `opus-plan-reviewer`, then Branch A/2a
  external review via the identity-locked `gpt-5.6-terra`/GLM pair), the
  operator asked specifically for an additional adversarial pass with
  `gpt-5.6-sol` — the exact model that caught the original §1a gap in the
  parent spec's own review history — run directly via `codex exec -m
  gpt-5.6-sol`, outside `external_review.py` (whose "openai" identity is
  config-pinned to `gpt-5.6-terra` and rejects overrides by design). Findings
  preserved at `gpt56sol-review-findings.md`; disposition folded into the
  revised `## Decision`.
- **Scope boundary, stated explicitly (opus-plan-reviewer finding 12):** this
  ADR resolves the parent spec's **§5 Phase 0.5 only** (which delivery
  variant, and the two falsification questions). It does **not** resolve
  **Phase 0** — the parent spec's own gate that "a deliberate decision that
  the [architectural] reasoning alone justifies the [M1-M4] spend" is still
  open and belongs to whoever plans R1-R4, not to this run.
- **F3 process violation, caught and fixed:** the first attempt at recording
  this decision hand-appended a numbered `### ADR-398` entry directly to
  `.shipwright/agent_docs/decision_log.md` — exactly what F3.md forbids
  (iterates never write to `decision_log.md` directly; the sequential
  number is assigned only at `/shipwright-changelog` release time via
  `aggregate_decisions.py`, and `check_iterate_no_direct_decision_log`
  fails closed on a direct append). Caught by Stage-2 `code-reviewer`,
  which also caught a second, related defect (an `ADR-NNN` token embedded
  in the spec-ref file's heading, which F3.md separately forbids and which
  broke the auto-generated `INDEX.md` row). Both fully reverted/fixed: the
  decision now ships only as a `write_decision_drop.py` decision-drop plus
  a long-form `--spec-ref` file with a plain heading, re-verified clean by
  a fresh `spec-reviewer` + `code-reviewer` pass. The decision content
  itself was unaffected — only its delivery mechanism was wrong.
- **F0.5 surface verification:** `surface=none` — this run ships no
  production code or UI/API surface, only an ADR (decision-drop +
  long-form spec-ref); no startable surface exists to drive end-to-end.
- **External code-review cascade:** ran at this run's medium complexity
  (default-on trigger) over the final decision-drop + spec-ref diff.
  `openai`/`gpt-5.6-terra`=approve ("ship-as-is"), `glm`=approve with 3
  advisory findings, all addressed: a factual error in the spec-ref's
  Review History section (wrongly claimed the iterate spec is gitignored —
  it is not; only the campaign status files are) corrected; the
  producer/consumer boundary table (previously stated only in this iterate
  spec's own Affected Boundaries section) copied inline into the spec-ref's
  Consequences section for a self-contained committed record; `INDEX.md`
  re-verified byte-for-byte identical to `rebuild_adr_index.py`'s own
  output.
