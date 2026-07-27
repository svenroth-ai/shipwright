# Iterate — the code review becomes a floor, not a chain

> Run ID: `iterate-2026-07-27-review-floor-not-chained`
> Type: CHANGE · Complexity: medium
> Follows the operator review of `iterate-2026-07-27-project-granularity-basis`

## 1. Problem

Three defects, one shape: **the only mandatory code review at medium+ is
conditional on a subagent firing, and the external second opinion is chained
behind it instead of being an independent floor.**

**(1) The external cascade is chained to the internal one.**
`references/iteration-reviews.md` → "External Code-Review Cascade" → Trigger Rule:

> Cascade fires **iff the internal `code-reviewer` subagent fired in this run**

So if the internal reviewer does not fire — for any reason: tool unavailable,
session directive, crash, or simply not requested — then by the letter of the
rule the external review does not fire either. The two are wired in series, and
the series has a single point of failure.

**(2) Nothing says where the responsibility goes when the internal pass cannot
run.** ADR-029 solved this for campaign mode ("delegated to orchestrator, since
the runner has no Agent tool") but that decision is scoped to the
sub-iterate-runner. A standalone iterate has no equivalent sentence, so the
responsibility simply lapses.

**(3) The F11 gate checks bookkeeping, not substance.**
`review_record_check.py` verifies only that a record exists, that no type is
still `pending`, and that it is committed. All five types may be `not_run` with
dispositions and the gate returns green:

```python
outstanding = pending_types(record)      # only "unanswered"
...
return CheckResult(CHECK_NAME, True, "all five review types are recorded")
```

A medium+ iterate can therefore finish with **no code review of any kind** and
F11 stays green.

## 2. Measurement first (the operator asked for this before any fix)

Scanned all 27 review records in the repo, joined with each run's recorded
complexity.

| `code` × `external_code` | runs |
|---|---|
| `not_run` × `completed` | 15 |
| `completed` × `completed` | 11 |
| `not_run` × `not_run` | 1 |

| complexity | runs | with NO code review of either kind |
|---|---|---|
| medium | 24 | **0** |
| large | 1 | **0** |
| small | 2 | 1 |

**Two findings, and the second corrects the first impression.**

- The hole is **latent, not realised**: 25 of 25 medium+ runs did get a review.
  The single zero-review run was `small`, where the phase matrix legitimately
  says "only if risk flags" and the external cascade "does NOT run" — that run
  was **correct**, not a violation.
- But the protection is **not coming from the contract**. In 15 of 27 runs the
  agent recorded `code = not_run` and ran the external review *anyway*, which
  the trigger rule as written does not authorise. A rule that everybody
  overrides is evidence about the rule, not about the people. Today's safety
  rests on agent judgement; this iterate moves it into the contract.

**Blast radius of the new gate: measurably zero.** Applied retroactively to all
27 records, the medium+ floor would have failed **no** run.

## 3. Decision

- **Decouple.** The external cascade's trigger no longer references the internal
  subagent. It fires on the same conditions the internal one does (medium+, or
  risk flags, or diff > 100 lines) — independently.
- **Escalate, never lapse.** When the internal `code-reviewer` cannot run, the
  responsibility moves outward rather than disappearing: the external review
  becomes mandatory, and it is recorded as carrying the pass.
- **Floor it.** At medium+, `check_review_record` additionally requires that at
  least one of `code` / `external_code` is `completed`.

**`not_applicable` deliberately does NOT satisfy the floor.** If it did, the
gate would be bypassable by re-labelling — the exact bookkeeping-instead-of-
substance failure this fixes. At medium+ the phase matrix says review "always",
so there is no "not applicable" for the pair as a whole; an individual type may
still be `not_applicable`, but not both.

**No bypass flag.** A project that has disabled external review *and* cannot run
the internal reviewer has no code review at medium+, and that should stop the
run rather than pass quietly. The remediation message names both routes.

## 4. Alternative considered — and why not

**Give the sub-iterate-runner the Agent tool** so it can spawn the reviewer
itself (ADR-029's rejected option (a), rejected then purely on token cost, and
plausibly re-openable now that agents can be declared with nested tool access).

Not done here, for two reasons. It only addresses **campaign** mode, so it
leaves the standalone hole (2) and the gate hole (3) untouched. And whether
nested subagent invocation actually works at runtime is **unverified** — the
config side permits it (several agents are declared with `Tools: *`), but
confirming it means spawning one, which this session's standing directive
forbids. Building a contract on an unmeasured capability is what §2 exists to
avoid. Recorded as a follow-up rather than assumed.

## 5. Also in this diff — an honesty correction

`iterate-2026-07-27-project-granularity-basis` recorded `code` and `doubt` as
`completed` with a disposition explaining that the subagent pass was
substituted. Two sibling runs the same day recorded the same situation as
`not_run`. Theirs is the more honest bookkeeping: `completed` should mean *the
pass the contract describes ran*, and it did not. Re-recorded as `not_run` with
the disposition preserved, at the operator's instruction, so the three runs read
consistently.

## 6. Affected Boundaries

- `review_record_check.py` → F11 verdict → `run_audit` exit code. A too-strict
  floor blocks real runs; a too-lax one restores the hole. Pinned by replaying
  the historical corpus shape in tests.
- `iteration-reviews.md` is a runtime prompt read by the iterate skill; its
  trigger wording is what agents actually follow.

## 7. Confidence Calibration

- **Boundaries touched:** the F11 gate verdict and the review-cascade prompt.
- **Empirical probes run:**
  - 27-record corpus scan, joined with complexity → 0/25 medium+ runs would be
    newly blocked (§2). The gate is a ratchet on future behaviour, not a
    retroactive failure.
  - Read `review_record_core.pending_types` and the status vocabulary
    (`completed` / `not_run` / `not_applicable` / `pending`) before designing
    the predicate, so the floor is expressed in the schema's own terms.
  - Confirmed ADR-029's scope is campaign-only by reading its Context and
    Decision fields, not by inference from its title.
- **Test Completeness Ledger:** §8.
- **Confidence-pattern check:** depth — the floor is tested at each complexity
  boundary and for every status combination of the pair, not just the happy
  path. Breadth — both the gate and the prompt that tells agents what to do are
  changed together, since either alone leaves the contradiction in place.

## 8. Test Completeness Ledger

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | medium+ with both `code`/`external_code` non-completed → FAIL | `tested` | `test_review_record_floor.py::test_medium_blocks_when_neither_ran` |
| 2 | medium+ with only `external_code` completed → PASS (the substitution path) | `tested` | `::test_external_alone_satisfies_the_floor` |
| 3 | medium+ with only `code` completed → PASS | `tested` | `::test_internal_alone_satisfies_the_floor` |
| 4 | `not_applicable` on both does NOT satisfy the floor | `tested` | `::test_not_applicable_does_not_satisfy_the_floor` |
| 5 | small is unaffected (floor is medium+ only) | `tested` | `::test_small_is_not_floored` |
| 5a | `large` is floored too — not an `== "medium"` check | `tested` | `::test_large_is_floored_too` |
| 5b | trivial skips the gate entirely | `tested` | `::test_trivial_is_skipped_entirely` |
| 5c | unknown complexity skips — and the sibling check catches the missing entry | `tested` | `::test_unknown_complexity_skips_the_gate_and_is_caught_elsewhere` |
| 6 | the floor runs only after the pending check, so an unanswered type still reports as unanswered | `tested` | `::test_pending_still_reported_first` |
| 7 | the historical corpus would not be newly blocked | `tested` | `::test_historical_shapes_still_pass` |
| 8 | the trigger rule no longer chains external to internal | `tested` | `test_review_cascade_decoupled.py::test_trigger_is_not_conditional_on_internal` |
| 9 | the escalation sentence is present | `tested` | `::test_escalation_is_stated` |
| 10 | the doc names the enforcing gate (prose ↔ code pointer) | `tested` | `::test_doc_names_the_enforcing_gate` |
| 11 | `close-missing` still writes a complete record in one command | `tested` | `test_record_review_pass_cli.py::test_close_missing_closes_every_outstanding_type` |
| 12 | `close-missing` no longer green-lights a medium+ run | `tested` | `::test_close_missing_does_not_satisfy_the_floor_at_medium` |
| 13 | `close-missing` still unblocks a small run | `tested` | `test_record_review_pass_cli_floor.py::test_close_missing_still_unblocks_a_small_run` |
| 14 | `close-missing` still unblocks a trivial run | `tested` | `::test_close_missing_still_unblocks_a_trivial_run` |
| 15 | the repair path the failure message names actually clears the floor | `tested` | `::test_recording_one_real_review_clears_the_floor` — a gate that blocks without a working way forward is a trap, so the remediation is exercised rather than asserted |

Zero untested-testable behaviours.

## 8a. Collision found during verification — AC10, and the operator's ruling

The floor collided with a shipped acceptance criterion. `AC10` of the review
record says a run already past its review phases *"must be one command away from
finalizing, not trapped"*, implemented as `close-missing --status not_run`
closing all five types at once. At medium+ the floor now refuses exactly that.

This was **not** in the plan and is more than closing a hole — it narrows a
delivered promise — so it went back to the operator rather than being decided
here. **Ruling: the floor wins.**

The narrowing is de-risked by measurement rather than by argument: the escape
hatch was built for the migration window when the record landed (2026-07-21),
and that window is measurably closed — 27 records exist and all 25 medium+ runs
already satisfy the floor, so no real run is trapped by it.

What changed concretely:

- `close-missing` still writes a **complete** record in one command; what it no
  longer does is make a medium+ run **green** while nothing was reviewed. Those
  were always two different things, and conflating them was the hole.
- At small it is untouched.
- The gate's remediation text now says so up front, so the operator learns it
  when reading the failure rather than after trying the command.

## 8b. Where the new CLI tests live, and why not in the obvious file

`test_record_review_pass_cli.py` was **496 lines against a 300-line limit before
this change**. Appending three tests to it took it to 534 — growing an already
oversize file, which is a ratchet whether or not a baseline entry happens to
exist for it (none does, so the anti-ratchet hook stayed silent; the Stop-hook
Iron Law caught it).

The first attempt moved only the new cases out and trimmed the original back to
495 — one fewer than it started. **That was not enough**, and the gate said so
again: it blocks on `delta == "crossing" and not in_baseline`, which is a
property of the file being over the limit at all, not of it having grown. A file
196 lines over its ceiling with no grandfathering entry is a blocker whoever
touches it, and "it was already like that" is the deferral the Iron Law names.

So the file is split along **its own section headers** — the seams its author
already drew, not ones invented for the line count:

| file | lines | holds |
|---|---|---|
| `_review_cli_harness.py` | 96 | fixture builder, subprocess wrapper, reviewer payloads |
| `test_record_review_pass_cli.py` | 192 | AC8 / AC7 / AC3 / AC2 |
| `..._cli_regressions.py` | 171 | the code-review round's findings |
| `..._cli_doubt.py` | 160 | the Stage-3 doubt pass's findings |
| `..._cli_floor.py` | 113 | `close-missing` × the floor |

29 tests before, 29 after. The harness is a plain module rather than a
`conftest.py` because `shared/tests/conftest.py` loads for the whole suite, and
a `project` fixture visible to ~5,900 unrelated tests is a collision waiting to
happen. It exports `make_project()` as a function, not a fixture: importing a
fixture makes ruff read every test taking `project` as an F811 redefinition (28
of them), and silencing that per test is noisier than a three-line wrapper.

## 9. Out of scope

- Giving the sub-iterate-runner the Agent tool (§4) — needs the runtime
  capability measured first.
- Changing the phase matrix itself (what triggers a review at which complexity).
- The `doubt` pass, which is Advisory/Stage-3 by design and is not part of the
  floor.
