# Codex activation-envelope delivery: prompt-borne, minted reactively by UserPromptSubmit

Long-form decision text for the decision-drop at
`.shipwright/agent_docs/decision-drops/iterate-2026-09-20-r0-resolve-1a-envelope-delivery_001.json`
(run_id `iterate-2026-09-20-r0-resolve-1a-envelope-delivery`). The
sequential `ADR-NNN` number for this decision is assigned by
`/shipwright-changelog`'s `aggregate_decisions.py` at release time, not
here — do not cite a number for this decision until `decision_log.md`
actually carries it.

## Context

Parent spec `Spec/codex-plugin-execution-reliability.md` M3/M7 needs a
pre-worktree activation signal so a Codex CLI session cannot proceed past
tool calls until `setup_iterate_worktree.py`'s own precondition has
actually run. Sub-iterate R0 had to resolve which of two envelope-delivery
variants mints that signal before Codex's first turn, and answer two
falsification questions (operator-poking false-arm; cross-runtime
Claude/Codex false-arm). A 2026-09-20 amendment to the sub-iterate spec
made this a hard feasibility gate: prove live, against installed Codex CLI
0.155.0, that the enforcement mechanism actually works the way the spec's
prose assumed — not just docs-reading. Resolves the parent spec's **§5
Phase 0.5 only** — not §5 Phase 0, which is a separate, still-open gate for
whoever plans R1–R4.

## Decision — mechanism

The envelope is **prompt-borne**, delivered as part of the session's first
prompt text (a closed, recognizable grammar carrying `skillId` + arguments,
per M7), not a pre-existing file. `UserPromptSubmit` — which fires *after*
a session exists, with real `session_id`/`turn_id` already resolved —
reads that first prompt, validates the grammar, and mints the activation
record (M3's own fields: `session_id`, `turn_id`, `cwd`, `generation`,
`expiry`). `PreToolUse` denies the gated tool call unless a matching,
unconsumed record exists for the current `session_id`/`turn_id`; consuming
it is atomic and one-time.

**Live-proven (Codex CLI 0.155.0, 7 probes against a throwaway scratch
repo, never this monorepo):** an untrusted hook is silently inert with
zero signal anywhere (no query interface exists, only
`--dangerously-bypass-hook-trust` to bypass); under bypass, `PreToolUse`
deny genuinely blocks a `Bash`-class call (the model's own turn reports the
block, the shell command never runs); Codex's hook-visible tool names
differ by class (`"Bash"` aliased, `spawn_agent`-class calls
raw-with-dot-stripped, `"Agent"` matcher confirmed via official docs to
also catch `spawn_agent`, correcting an earlier probe's wrong conclusion);
named `.codex/agents/*.toml` profiles genuinely steer subagent dispatch,
but only in non-`--ephemeral` sessions; `UserPromptSubmit` carries real
`session_id`/`turn_id`/`cwd`/`prompt` and its `additionalContext` output
reaches the model verbatim (though this is the model self-reporting the
token back, not a structured event-stream confirmation — an open item for
R2's first live check, not yet closed).

**Not live-proven this run, and R2's two blocking preconditions:**
1. A normally-trusted, non-bypassed hook has never been proven to fire at
   all — every deny observed used the bypass flag.
2. The mint→store→consume chain was proven in two separate probes, never
   chained in one live turn.

## Decision — R2 scope, trimmed by Architecture Review

R2 builds the **terminal producer only** — the campaign's own hand-driven
R1–R4 dogfood via terminal and nothing else needs it yet. The
`shipwright-webui` (Codex Light) and Codex Desktop app producers are
explicitly **deferred to their own later iterates**, not part of R2's
definition of done: the record's opt-in, fail-open nature means its
guarantee is "cannot proceed *when armed*," not an absolute, and building
three producers plus a state-transition table plus a per-tool-class
matcher inventory up front was disproportionate to that guarantee
(external Architecture Review finding, accepted).

Claude-side registration is **out of scope for R2 and a separate, later
decision** — not bundled here: the first draft proposed registering the
same consumer logic in Claude's own `hooks.json` as "runtime-neutral by
design," which directly contradicted the cross-runtime false-arm defense
argued in the same breath (a Claude session can't false-arm a signal it
never loads — until it has its own registered copy of that same signal).
Checked directly against every `plugins/*/hooks/hooks.json` in this repo
(2026-09-20): Claude-side Shipwright has no `PreToolUse` hook today denying
a fresh iterate's first tool call; only `shipwright-build` (Bash
validation) and `shipwright-compliance` register `PreToolUse` at all,
neither for this purpose — so this gap is genuinely new for both runtimes,
worth naming as a future option, but "build it now" and "name it as an
option" are different claims and only the second is this run's to make.

## Decision — falsification questions

Answered analytically (contingent on R2 correctly implementing the
record's documented state machine, not independently proven against a live
two-actor fixture):

- **Operator poking around by hand, including resuming the same session
  after real work finished:** a fresh, unrelated interactive turn never
  submits the envelope-carrying first prompt, so no record is minted —
  covered. The same-session case (operator continues chatting in a session
  whose activation is still `active`/unconsumed) is **not** closed by that
  reasoning alone; it depends on the record's `consumed` state
  transitioning once the gated action happens or the turn ends, so a later
  unrelated ask in the same session finds no live grant. This is a
  requirement for R2's state machine, not new scope R0 invented — and not
  something R0 can call closed without R2.
- **Cross-runtime (a Claude session in the same worktree):** with
  Claude-side registration explicitly deferred, a Claude session never runs
  Codex's `hooks.json` today, so there is no shared consumer to false-arm —
  this closes the *shared-consumer false-arm* question only, not a claim of
  equivalent AC1a-style protection for Claude, which remains exactly as
  unenforced after this decision as before it. If Claude-side registration
  is ever built later, the honest answer changes: a Claude session could
  see the same on-disk record, and safety would then depend on one-time
  consumption + expiry + an explicit runtime-identity field in the record —
  a requirement for whoever builds that future iterate.

## Decision — envelope authenticity

Resolved by the Architecture Review pass (both external reviewers
converged independently): the envelope is plain, model-visible,
user-pasteable first-prompt text — a pasted log, README example, or
injected prompt containing the grammar could cause an unintended mint. R2
takes the "document the residual risk" option (one-time-consume + expiry
only), not a per-launch secret/nonce: a nonce is a new standing credential
mechanism (generation, storage, validation, its own failure modes) built to
harden a channel that already fails open by design and is independently
documented (Codex's own docs) as "a guardrail, not a complete enforcement
boundary" — disproportionate to what the guarantee delivers.

## Named gaps this decision creates

1. Only direct-CLI-launched Codex sessions get AC1a's pre-worktree denial
   after R2 — webui and Desktop adapters are their own later iterates.
2. Arming is opt-in; M3's own documented fail-open means a session
   launched *without* the envelope-carrying first prompt behaves exactly
   like an unguarded session today. R2 should make an unarmed launch
   **visible** (e.g. a `SessionStart` warning when no envelope was
   recognized), even though fail-open is the correct default.
3. Hook-trust inertness: the whole mechanism can be installed and silently
   inert if the bundled hook is never actually trusted, and nothing in
   this slice detects that — blocking precondition 1 above.
4. The mint→store→consume chain is not yet proven end-to-end in one live
   turn — blocking precondition 2 above.
5. Subagent tool-name asymmetry means the `PreToolUse` matcher inventory
   needs a per-tool-class entry, not one universal rule.
6. The `--ephemeral` limitation on named-profile dispatch constrains any
   stateless subagent fixture a later R3/M4 build might want.

## Contract for R2 (binding defaults, not silently left implicit)

Envelope location under a gitignored `.shipwright/runtime/`-style path,
never committed; schema versioned from day one; scoping keys `session_id`
+ `turn_id` + `cwd` + `generation` + `expiry`; a record present but not
matching current session/turn is treated as absent (fail-open), not an
error; Windows cwd normalization reuses the existing main-root/cwd resolver
rather than reinventing it; a concurrency-safe atomic-consume mechanism is
required (e.g. atomic file rename), since `UserPromptSubmit` and
`PreToolUse` are separate hook invocations sharing durable state; envelope
recognition applies to the session's first eligible prompt only, with
re-arm semantics on a later prompt explicitly defined by R2 (allowed under
what conditions, or denied) rather than left to fall out of the
implementation; the terminal helper needs one defined invocation shape (how
the envelope text reaches `codex`'s first prompt), explicit Windows
shell-quoting handling, and an explicit reject/warn when pointed at an
existing session or non-first prompt; a per-session/turn state-transition
table covering duplicate submission, a failed gated call after
consumption, mid-turn expiry, and concurrent/interrupted turns; Codex's
own hosted-tools bypass of `PreToolUse` (e.g. `WebSearch`) means AC1a's
guarantee holds for the local function-tool path, not as an absolute claim
over every conceivable tool call.

## Rationale

The first draft of this decision proposed a CLI helper that pre-writes a
file "scoped to cwd + session identity" before Codex starts. Two
independent internal/external reviews (`opus-plan-reviewer`, then an
additional `gpt-5.6-sol` adversarial pass run at the operator's specific
request) rejected this on convergent grounds: at mint time there is no
session to scope the file to, so the file could only be keyed by cwd —
exactly the "latest by cwd" lookup M3's own text forbids. Re-reading M3/M7
after that rejection showed they never actually required a pre-session
file; M3 already specifies `UserPromptSubmit` as what "creates an atomic
turn record... mints an unguessable activation token," which only needs to
exist *after* a session does. The corrected mechanism above removes the
pre-session binding problem by construction (the envelope and the session
it belongs to are, by design, the same event) and was live-proven for its
`UserPromptSubmit` half before being re-asserted.

Branch A external review (two passes: first over the redesign,
`revise`/`revise`; second after fixes, `approve`/`revise` with only wording
refinements remaining) and the Architecture Review pass (`glm=approve`,
`openai=reject`) both ran afterward; `openai`'s rejection proposed gating
directly on cwd being an "already-valid worktree" with no minted record at
all — this is a near-restatement of the parent spec's own original §1a
prose ("cwd is a `.worktrees/<slug>` tree with a live run_id"), which an
earlier review of the parent spec had already flagged as spoofable (a
worktree-shaped directory or a live-looking `run_id` can exist without the
actual precondition having happened) — precisely why M3 specifies an
unguessable, minted, session-scoped record instead of a
directly-observable filesystem predicate. Given the reviewer split, the
operator was asked directly and chose to keep the current design, record
this reasoning, and additionally trim R2's scope per `glm`'s
proportionality findings (terminal-only, document-the-risk over a nonce)
rather than take `openai`'s simpler-but-already-rejected alternative or
rework further.

## Consequences

R2 (M3's actual build) inherits two hard blocking preconditions (ordinary
trusted-hook denial; end-to-end mint→consume proof) that must be
demonstrated before AC1a can be considered met — this decision is
architecturally sound but **not** a claim that R2 is unblocked to ship.
R2's scope shrinks to terminal-only, so webui/Desktop coverage becomes
future work rather than a Phase-2 deliverable. Claude-side parity is named
but explicitly not decided here, so Claude sessions remain exactly as
unenforced as before this decision.

The activation-record format becomes a new serialized producer/consumer
boundary that R2 must build to the Contract above, not invent ad hoc:

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| terminal helper (R2's only in-scope producer) / webui launch composition / (future) Desktop pre-step — the latter two deferred out of R2 | `UserPromptSubmit` hook (mints record from it) | first-prompt-embedded closed grammar (M7) |
| `UserPromptSubmit` hook (mints) | `PreToolUse` hook (consumes) | activation record — schema pinned in "Contract for R2" above |

## Rejected alternatives

The original pre-session file-binding design (session-identity-impossible
at mint time, both internal reviews). Registering the same consumer hook
in Claude's `hooks.json` now, framed as "runtime-neutral by design"
(self-contradicts the cross-runtime false-arm defense; scope belongs to a
separate future decision). "Build it runtime-neutral from the start" as a
middle ground between Codex-only and full Claude parity (the schema is
versioned for possible future reuse; that is a forward-compatibility
property, not a decision to build or register anything for Claude now). A
per-launch secret/nonce for envelope authenticity (disproportionate new
standing-credential mechanism for a channel that already fails open by
design). Building all three producers (terminal/webui/Desktop) as R2's
scope (disproportionate standing surface relative to an opt-in, fail-open
guarantee — Architecture Review). Gating directly on cwd being an
"already-valid worktree" with no minted record (`openai`'s Architecture
Review alternative — this is the spoofable signal the parent spec's own
earlier review already rejected).

## Review history

Internal Plan Review (`opus-plan-reviewer`) — REJECT, 12 findings, all
fixed. Additional adversarial pass (`gpt-5.6-sol`, operator-requested,
outside the standard cascade) — REJECT, 8 findings, all fixed; both
reviews independently converged on the same root design flaw. Branch A
external review (`glm`, `openai`/`gpt-5.6-terra`) — pass 1 `revise`/`revise`
(mini-plan staleness, envelope authenticity, first-prompt-only scope,
atomic-consume mechanism — all fixed); pass 2 `approve`/`revise` (remaining
items were wording/explicitness requests, satisfied). Architecture Review
(`glm`/`openai`) — `approve`/`reject`; reconciled above, operator decision
recorded. Full detail for all of the above, including the raw review
payloads, the two adversarial-review write-ups
(`gpt56sol-review-findings.md`, `opus-plan-reviewer-findings.md`), and the
12-row Test Completeness Ledger: the iterate spec itself,
`.shipwright/planning/iterate/2026-09-20-r0-resolve-1a-envelope-delivery.md`
— **committed as part of this same PR, not gitignored** (only the
campaign-level `status.json`/`campaign.md` files this decision also updates
are gitignored local convenience copies). The live-probe raw run logs
(`run1.jsonl` through `run7_ups.jsonl` and related hook-invocation logs)
were captured against a throwaway scratch repository outside this monorepo
and are not committed anywhere; the specific evidence excerpts that matter
(exact hook payloads, the model's own quoted responses) are reproduced
inline above and in the iterate spec's Live Feasibility Probes section, not
solely cited by reference.
