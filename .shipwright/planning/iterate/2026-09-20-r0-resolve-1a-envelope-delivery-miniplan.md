# Mini-Plan: r0-resolve-1a-envelope-delivery

- **Run ID:** iterate-2026-09-20-r0-resolve-1a-envelope-delivery

## Files to create/modify

- `.shipwright/agent_docs/decision_log.md` — **NOT edited directly.** F3.md
  is explicit that an iterate run never appends to `decision_log.md`
  itself: two parallel iterates would each compute `max(ADR)+1` in their
  own worktree and collide, and `check_iterate_no_direct_decision_log`
  (F11) fails closed on exactly this. A first draft of this run did append
  directly — caught by Stage-2 `code-reviewer`, reverted. The sequential
  `ADR-NNN` is assigned at exactly one serialized point,
  `/shipwright-changelog` release time (`aggregate_decisions.py`).
- `.shipwright/agent_docs/decision-drops/*.json` — new decision drop (new,
  via `write_decision_drop.py` at F3) — **this is the durable record this
  run actually ships**, not a placeholder for a hand-written ADR
- `.shipwright/planning/adr/<run_id>-envelope-delivery.md` — new long-form
  spec-ref file (the `--spec-ref` target; holds the full decision text,
  since several fields exceed the decision-drop's 500-char budget) — no
  `ADR-NNN` token in its heading, per F3.md (the real number isn't
  assigned yet and a guessed one would be a false claim)
- `.shipwright/planning/iterate/campaigns/codex-plugin-execution-reliability/status.json`
  and `campaign.md` — mark R0 **`decision-complete, dependency-blocked`**
  (not bare `done` — Branch A external review flagged that "done" reads as
  "implementable as designed," when two R2 preconditions are still open:
  ordinary trusted-hook denial, and the end-to-end mint→store→consume
  proof) and record the decision-drop pointer (**not** an ADR number — none
  is assigned yet), with the two blocking R2 preconditions linked (edit) —
  **gitignored**, so this edit lands only in the local main-tree copy after
  merge, not in the PR diff — the decision-drop + spec-ref (tracked) is the
  durable record; this file is a local convenience only
- `Spec/codex-plugin-execution-reliability.md` — **not edited** (gitignored,
  out of the tracked diff by design; the ADR is the durable record instead)

## Work breakdown

1. Resolve Resolution B's delivery-variant choice from the live probe
   evidence already gathered (7 Codex-CLI 0.155.0 probes, recorded in the
   iterate spec). No new probing needed for this step — it is a synthesis
   step over already-collected evidence.
2. Resolve Resolution A's two falsification questions (operator-poking,
   cross-runtime) from M3's own already-specified activation-record design
   (session_id/turn_id/generation/expiry-scoped, not bare cwd) — again a
   synthesis step, not new building.
3. Write the long-form ADR spec-ref file
   (`.shipwright/planning/adr/<run_id>-envelope-delivery.md`, plain heading,
   no `ADR-NNN` token) recording both resolutions, the rationale, and the
   named gaps the choice creates — inlined in full, not cited by section
   number, since the iterate spec itself is gitignored and this file is the
   durable, tracked record.
4. Write the F3 decision drop referencing this run.
5. Update the campaign's local `status.json`/`campaign.md` to mark R0
   `decision-complete, dependency-blocked` (local-only artifact, gitignored —
   not part of the shipped diff, but kept current for whoever runs R1 next).

Test expectation per step: none of these steps produce testable production
code (see Iterate Spec's Confidence Calibration — this run's "testable
behaviors" are the 8 live-probe claims already gathered pre-plan, not
something the plan's own steps 1-5 produce).

## Data model changes

None.

## Test strategy

No new tests — this run ships no production code. The Test Completeness
Ledger in the iterate spec covers the empirical claims the decision rests on.

## Alternative approaches (considered and rejected)

**Alternative 1: pick exactly one Resolution B variant as the sole,
permanent delivery mechanism (either CLI-helper-only or
webui-adapter-only).**

Rejected — the operator uses two real launch surfaces (`shipwright-webui`
first, Codex Desktop app second), plus the campaign's own R1-R4 sub-iterates
need a terminal path to dogfood the mechanism first. Picking one exclusively
would either strand the operator's actual daily usage or block on a
cross-repo `shipwright-webui` change before Phase 2 could even start.

**Alternative 2 (superseded by the Decision section above): implement
"adapter emits" and "CLI helper" as two separate, divergent
implementations, one per surface, rather than one mechanism with thin
per-surface adapters.**

Rejected once reading `Spec/codex-light-webui.md` showed `buildCodexCommands`
already spawns `codex exec` as a subprocess — meaning the webui's own
addition can be "embed the same envelope grammar directly into the first
prompt text it already composes," not a bespoke envelope-construction
implementation. (Not "prepend a CLI-helper invocation" — that earlier framing
risked changing `buildCodexCommands`'s own command construction/quoting for
no benefit once minting moved to `UserPromptSubmit`; Branch A external review
caught this drift between the mini-plan and the revised Decision.) Building
two divergent mechanisms would double the surface needing its own
correctness proof for no benefit, and would not extend to the Desktop app at
all (which needs the "local durable state, surface-agnostic" property
specifically).

**Alternative 3: scope this as Codex-only, since the motivating incident was
Codex-specific.**

Rejected as *fully* Codex-only — but **not** accepted as "build it
runtime-neutral from the start" either; that framing is what the two review
rejections caught in the first draft and the revised Decision replaced. The
actual choice, checked directly against Claude-side `hooks.json` files (no
`PreToolUse` pre-worktree denial exists for Claude either): R2 registers the
consumer hook in Codex's `hooks.json` only and ships no Claude-side
consumer. The activation-record *schema* is versioned so a Claude-side
consumer could reuse it later without a breaking change, but that is a
forward-compatibility property of the format, not a decision to build or
register anything for Claude now — whether to do so at all is the Decision's
own explicitly separate, later question (see "Claude-side registration
explicitly deferred"), not something this run or R2 decides by default.
