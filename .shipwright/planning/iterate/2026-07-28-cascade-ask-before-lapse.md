# Iterate — "cannot run" must not mean "was never asked"

- **Run ID:** `iterate-2026-07-28-cascade-ask-before-lapse`
- **Intent:** CHANGE (prose contract)
- **Complexity:** medium (`prior_source: history`; kept rather than reduced —
  this is the file that governs whether reviews happen at all)
- **Spec Impact:** NONE (no spec.md text changes)
- **Risk flags:** `touches_auth` / `touches_rls` were reported by
  `classify_complexity` from message prose and are false positives; no auth or
  RLS file is touched. `risk_detectors.py` recomputes from the diff and is
  authoritative.

## 1. Problem

PR #482 gave the cascade an owner: SKILL.md Step 8 now says *"this session
spawns the cascade itself"*. It says nothing about the case that actually
occurs, so the lifecycle still loses the pass.

**The session-level directive.** Sessions in this project carry a standing rule
in the system prompt:

> Do not call the AgentTool unless the user requested it

It is **conditional** — one sentence from the operator satisfies it for the rest
of the session — and it is **not** a capability limit. Measured across
`~/.claude/projects` on 2026-07-28: 552 Agent-tool calls (shipwright 266 in 81
of 145 sessions; webui 243 in 45 of 77; content 43 in 4 of 12). Subagents work
and are used constantly. This is a **default**, not a block.

**What the prose does with it.** `iteration-reviews.md` → "When the internal
reviewer cannot run — escalate, never lapse" opens the ladder at *cannot be
run* and never distinguishes it from *was never requested*. So an agent that
hits the directive reads itself as being in the escalation case, records
`code = not_run` with an honest-sounding disposition, lets the external review
carry the floor, and ships. The gate is green and the operator is never asked a
question they would have answered in four words.

**Observed, repeatedly.** Four runs recorded exactly this disposition in their
`reviews.json` — `iterate-2026-07-27-f0-race-triage`,
`…-phase-gate-override-evidence` (twice, `code` and `doubt`),
`…-checks-that-gate-nothing`, and `iterate-2026-07-28-grade-snapshot-lineage`
(after #482 merged). In session `209a092a` the agent did ask — but only at
**06:46**, after F0, eight hours into the run; everything before that had
already been built unreviewed.

**Why it matters.** The external route is not a substitute: per
`iteration-reviews.md` the spec-compliance and doubt roles are not cascaded to
external providers, and PR #438 measured the internal cascade finding 13+8
issues the external review missed.

## 2. Decision

- **AC1 — Ask at the top of Step 8, not at the end.** SKILL.md Step 8 states
  that when the cascade is required, the `Agent` tool **is present**, and the
  session has not already been given permission, the session **requests the
  operator's go-ahead as its first action in Step 8** — before Stage 1 — because
  the answer decides whether the next three stages run at all. The gain is not
  that the work is unbuilt — Step 8 follows Build and Self-Review by
  construction — it is that the answer arrives **before F6**, while the diff can
  still be fixed, instead of at F11 where the only remaining move is to close
  the row. All three
  conditions are guards against a pointless interrupt: no cascade required → no
  question; no `Agent` tool in this agent's capabilities → asking would win a
  "yes" and still fail; permission already granted earlier in the session → it
  holds for the rest of it and is not re-requested.
- **AC2 — "cannot run" is defined, and a conditional policy is not it.**
  `iteration-reviews.md`'s escalation section gains a step 0 naming the **four**
  real blockers: the agent type has no `Agent` tool (the sub-iterate-runner);
  the tool errored (a permission *denial* counts, and says so); the run is a
  **campaign sub-iterate built by the runner under `--autonomous`**, where there
  is no operator to ask; or the operator was asked and **declined**. **A
  standing policy that a request would lift is not a blocker until the request
  has been made and declined**, and **anything not on the list is not a blocker
  either** — the four are not exhaustive over reachable states (an unanswered
  question, a token-budget refusal), so the list closes itself explicitly.
- **AC3 — The autonomous case is named, not glossed — and it defers to existing
  permission.** Under `--autonomous` blocking to ask is forbidden, but that only
  prevents obtaining *new* permission: if the session already carries it, the
  cascade runs normally. Only when permission is absent *and* cannot be obtained
  without blocking is the honest path to record `code = not_run` with a
  disposition naming the mode, run the external review, and **surface the
  ungated pass in F12's closing banner** — a conditional `Reviews:` row this run
  adds, because the promise pointed at a template that had no such field.
  Because nothing on disk carries a grant across compaction, a handoff or a
  resume, the rule **fails open to asking**: if it cannot be established from
  this session, ask. `iterate-2026-07-28-grade-snapshot-lineage` already did the
  honest-recording half by hand.
- **AC4 — The disposition names which of the four it was.** A `not_run`
  disposition for `code`/`doubt` must state whether the blocker was
  no-Agent-tool, a tool failure, autonomous-mode, or operator-declined — not
  merely "a session directive", which reads the same whether or not anyone
  asked. `doubt` is `not_run` only when Stage 3 **would have applied**; on a
  docs-only or trivial surface it is `not_applicable`, because calling a
  never-due pass "blocked" is the same false statement in the same artifact.

## 2a. What the external plan review changed

gemini `approve`, openai `revise`, 6 findings, 5 applied.

- **openai #1 (medium)** — the original three blocker classes had no value for
  the case that matters most: asked and **declined**. Added as the fourth.
- **openai #2 (medium)** — "ask as the first action" would fire again in a
  session that already has permission, and in runs where the cascade does not
  apply. AC1 is now conditional on all three guards.
- **openai #3 (medium)** — `--autonomous` was treated as unconditional; it only
  blocks *acquiring* permission. AC3 now defers to permission already held.
- **gemini #1 (medium)** — asking without the `Agent` tool present wins a "yes"
  and then fails anyway. Folded into AC1's second guard.
- **gemini #2 (low, reducibility)** — a new test file per ticket fragments the
  drift guards. Accepted: the guards are organised **by artifact**, not by
  change, which also keeps each file under the 300-line cap.
- **openai #4 (low)** — the guards assert phrases, not *ordering*. Accepted in
  part: one guard compares the two positions inside Step 8. (Stage 1 then found
  the guard was still an `or` over phrase presence, and Stage 3 found its anchor
  was reusable — both fixed; see §3b.)

## 3. Alternative considered — and why not

**Remove the directive at its source** (the operator's preferred fix). Searched
exhaustively on 2026-07-28 and **not found**: the live process command line
carries no `--append-system-prompt`; the launcher is
`shipwright-webui/server` via node-pty → pwsh → claude and none of its
`command_templates` contains it; ruled out `~/.claude/settings.json`, project
`.claude/settings.json`, `~/.claude.json` incl. per-project entries, both
`CLAUDE.md`, `conventions.md`, `architecture.md`, `decision_log.md`,
`session_handoff.md`, managed policy, output styles, shell profiles, PATH
shims, Windows Terminal, VS Code settings, webui state, env vars, and the repo
itself. Every remaining hit is a transcript or a `reviews.json` disposition.
Given the 552 measured Agent calls, the thing being searched for is not a block
anyway — so the lever is the prose, not a deletion.

## 3a. Measured during this run — nested subagents WORK

ADR-029 rejected "give the sub-iterate-runner the `Agent` tool" (option a) on
token cost alone, and `iterate-2026-07-28-cascade-delegated-to-nobody` §4
deferred it further as an **unverified** runtime capability. It is no longer
unverified. Probe run 2026-07-28: a `general-purpose` subagent reported `Agent`
in its own tool list, called it, and its nested child returned `NESTED_OK`.

Config side agrees: `Explore` and `Plan` are declared *"All tools **except
Agent**"* while `general-purpose` and `claude` carry `Tools: *` — the explicit
exclusion only makes sense if `*` includes `Agent`.

**Consequence for the campaign follow-up — now `trg-71d7a4fa`, which supersedes
`trg-d6cc3d3d` precisely because this measurement answered its first step.**
That item opens with *"FIRST STEP: measure whether a subagent can spawn a
subagent — if yes, giving the runner the Agent tool is simpler than any
orchestrator step."* That step is now answered, so the follow-up can likely
drop the whole `3f-bis` before-merge state machine and instead add `Agent` to
`sub-iterate-runner.md`'s `tools:` frontmatter, letting the runner spawn its own
cascade **before its own commit** — which is where reviews belong. What still
needs deciding there is ADR-029's actual objection: the token cost of a runner
that fans out. Out of scope here; recorded so the follow-up starts from a fact
instead of a question.

## 3b. What Stage 3 changed — the rule was written in the wrong place

The doubt pass landed three high findings, and the first invalidated the
original scope:

- **The rule was absent from where every observed lapse was actually decided.**
  All four cited runs closed the row at **F11**, not at Step 8. The artifacts an
  agent reads there are `references/F11.md` and
  `review_record_check._remediation()`, and both simply printed the sanctioned
  `close-missing --status not_run` command. The rule was written only where a
  compliant agent already was. **Fixed by extending scope**: both artifacts now
  say that a `code` row outstanding at F11 means Step 8 never ran, and that a
  session policy is not a blocker. This makes `review_record_check.py` part of
  the diff — §4's original "out of scope" covered *enforcement*, not *where the
  instruction lives*, and the distinction is now stated there.
- **`--autonomous` became a blessed self-serve escape.** Operators really do
  write `Mode: --autonomous` on standalone runs (three planning docs do), so
  blocker #3 would have handed the exact failure mode an approved name — harder
  to spot than the vague disposition it replaced. Now bound to *campaign
  sub-iterates built by the runner*; a standalone run described as autonomous
  still asks, because the operator who wrote that invocation is present.
- **"Permission already held" had no carrier.** Nothing survives compaction, a
  handoff or a resume, and SKILL.md B1's replay-check re-runs Steps 4 and 7 but
  never Step 8 — so a resumed run reaches F11 having never asked. Now fails
  **open to asking**: if the grant cannot be established from this session, ask.

Also applied: the four blockers gained an explicit *"anything not on this list
is not a blocker"* (they were not exhaustive — unanswered questions, permission
denials and token-budget refusals are all reachable); `doubt` is `not_applicable`
rather than `not_run` when Stage 3 would not have applied at all; the file's own
canonical campaign dispositions were violating the new rule and now name a
blocker class; F12's banner gained the conditional `Reviews:` row that AC3
promised the operator would see; and all six guards were re-anchored on the
obligations rather than on tokens near them, after the reviewer constructed a
green-while-broken edit for every one of them.

## 4. Out of scope

**Truthfulness cannot be gated; form can, and is filed.** A verifier cannot tell
"asked and declined" from "never asked" — both produce `code = not_run` with a
disposition, and no prompt-driven lifecycle can prove who decided. That half is
genuinely unprovable (same reasoning as `review_record_check.py`'s own
docstring).

The *form* half is not: `disposition_ok()` accepts any string of ≥12 characters
containing a space, so "a session directive applies" — the exact string this run
exists to abolish — still passes. A closed four-token vocabulary for `code` /
`doubt` `not_run` dispositions would catch it, and this repo already has the
precedent in the Test Completeness Ledger's `reason_code`. Not folded in here
because it changes a schema every existing record is validated against; filed as
a follow-up so the narrower claim is not silently absorbed by the broader one.

## 5. Affected Boundaries

None. No serialized format, producer or consumer changes; this is runtime-prompt
prose plus its drift guards.

## 6. Confidence Calibration

*(populated at Step 7.5)*

## 7. Test Completeness Ledger

*(populated at Step 7.5)*
