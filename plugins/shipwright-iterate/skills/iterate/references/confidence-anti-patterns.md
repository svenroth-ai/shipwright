# Confidence Anti-Patterns Reference

Confidence collapses without an empirical anchor. This doc catalogs the
specific anti-patterns that allowed bugs through 47 unit tests + two
external LLM reviews on the 2026-05-03 env-iterate, and encodes the
counter-patterns the **Confidence Calibration** phase
(`SKILL.md` Path A Step 7.5) enforces.

> **Why this doc exists.** On the env-iterate
> (`adopt-env-local-scaffold`), the answer to *"are you confident?"*
> was twice "yes" — and both times a probe afterwards found a real bug.
> Three rounds of *"are you confident?" → probe → bug found"*
> established the asymptote: the area is not exhausted until at least
> one probe finds nothing. This doc encodes that calibration heuristic
> so future iterates ask the calibration question structurally rather
> than ad-hoc.

See also:
- `references/boundary-probes.md` — the 8-category probe checklist
- `references/round-trip-tests.md` — producer→file→consumer test patterns
- `references/iteration-reviews.md` — Self-Review item 7 (Affected Boundaries)

---

## The "Are You Confident?" Anti-Pattern

### What it is

A reviewer (human or another LLM) asks the agent: *"Are you confident
in the diff?"* The agent reads its own diff once more, sees no
problems, and answers *"yes"*. The reviewer accepts the answer and
ships.

This is a confidence-attestation pattern, not a verification pattern.
The agent's confidence in its own work is a **prior**, not evidence.
A "yes" to *"are you confident?"* is empirically uncorrelated with
whether bugs exist in the diff — on the env-iterate, the agent was
"confident" twice in a row while shipping two latent bugs each time.

### Why it fails

1. **Self-attestation is unfalsifiable.** The same brain that wrote
   the bug is being asked whether it sees the bug. If it did, it
   wouldn't have written it.
2. **Confidence ≠ correctness.** Calibration studies on LLMs
   consistently show that confidence is overestimated on tasks at
   the edge of competence — exactly the regime where bugs live.
3. **The question shapes the answer.** *"Are you confident?"*
   biases toward *"yes"* (assertive, decisive). The information-
   dense question is *"what would my probe miss?"*

### Counter-pattern: instead of asking, run a probe

Replace *"are you confident?"* with one of:

- *"What would a producer→file→consumer round-trip catch that the
  current unit tests miss?"* — then run that probe.
- *"What edge case from `boundary-probes.md` did I not cover?"* —
  then write the test for it.
- *"If the consumer changes representation tomorrow, would my
  test catch the drift?"* — then add the duplicated-consumer
  drift-protection probe (`round-trip-tests.md` Section 2).

The Confidence Calibration phase (Step 7.5 in `SKILL.md` Path A)
forces this substitution by requiring the runner to populate four
named bullets in the iterate spec — a probe + finding for each, not
a yes/no answer.

---

## The Asymptote Heuristic

### Statement

You are **not done probing** until at least one probe has found
nothing. The first probe finding a bug is evidence the area is
under-tested; one more probe is mandatory. The first probe finding
nothing is evidence the area's bugs are exhausted in the dimensions
you can think of.

Stated as a stopping rule: probe until the marginal probe returns
no finding. If the previous probe found a bug, the next probe is
**not optional**.

### Worked example: 2026-05-03 env-iterate

| Round | Question asked | Answer | Probe run | Finding |
|---|---|---|---|---|
| 1 | "Are you confident in the env parser?" | yes | round-trip with `KEY=value` | UTF-8 BOM not stripped |
| 2 | "Confident now after BOM fix?" | yes | round-trip with inline `# comment` | comment not stripped |
| 3 | "Confident now?" | yes | round-trip with `URL=...#anchor` | over-eager strip mangled value |
| 4 | (asymptote forced) | — | round-trip with quoted `MSG="hello # world"` | **no finding** — exhausted |

Three "confident" answers in a row, each followed by a probe-found
bug. The fourth probe found nothing — that's the asymptote signal.
Stopping at round 1, 2, or 3 (where the agent reported confidence)
would have shipped 1–3 bugs.

### Why "one more probe" is structural

If you stop after a probe that finds a bug, you have evidence of
*at least one bug class in the area*. The base rate of *"this was
the only bug class"* is empirically low — bugs cluster around the
same code path. The "one more probe" rule converts evidence-of-bugs
into evidence-of-exhaustion at constant marginal cost (one probe).

The cost asymmetry is the load-bearing argument:

- **Cost of one extra probe:** ~5 minutes of test scaffolding
- **Cost of shipping the missed bug:** investigation + hotfix +
  trust hit + the meta-cost of the post-mortem documenting why the
  probe wasn't run

The asymptote heuristic structurally converts the cheap probe into
a precondition for the expensive ship.

---

## When to Stop Probing — Decision Rule

The Confidence Calibration phase declares *exhausted* when ALL of
the following hold:

1. **Last probe found nothing.** The most recent empirical probe
   (round-trip, edge case, drift check) returned no finding.
2. **All probes from `boundary-probes.md` that apply to this
   format are run.** For user-edited formats (env, JSON config
   operators inspect by hand): all 8 categories. For machine-only
   formats: round-trip + format-specific categories with one-line
   justification for each skipped operator-input category.
3. **Drift-protection in place when N>1 consumers exist.** If the
   producer's format is read by more than one consumer, the
   duplicated-consumer drift-protection test
   (`round-trip-tests.md` Section 2) is in place.
4. **The "are you confident?" question has not produced a
   yes-followed-by-finding in this iterate run.** If yes-then-bug
   has happened even once, run one more probe before declaring
   exhausted, regardless of conditions 1–3 above.

If any condition fails: run one more probe, document the finding
(or the no-finding), re-evaluate.

### Negative case: when the calibration phase doesn't apply

The phase is **mandatory at medium+** AND **mandatory whenever
`touches_io_boundary` is set** (any complexity). Trivial/small
without the flag may skip — the phase has no purchase if there's
no producer/consumer pair to probe. A pure refactor of internal
state, a docstring fix, or a markdown edit don't trigger the
phase.

The phase is **NOT** triggered by SKILL.md edits, conventions.md
edits, or other markdown reference edits — these are documentation
formats consumed by humans, not serialized formats consumed by
parsers. (Drift-protection tests for the markdown structure itself
are a separate pattern; they don't make the doc a serialized format
in the calibration sense.)

---

## Completeness — the Coverage Stopping Rule

The asymptote heuristic above governs **depth** — how far to probe a
*single* dimension before it is exhausted. It says nothing about
**breadth** — whether *every* behavior the diff introduces has been
probed at all. The "I should still test X, Y, Z" answer at merge time is
a breadth failure, not a depth one: the agent probed one area to the
asymptote and left three others untouched, then reported them as
"acceptable to skip."

The **Coverage Stopping Rule** closes that gap and replaces the
"acceptable to skip" escape hatch:

> You are **not done** until every testable behavior introduced or
> changed by the diff is either **`tested`** (with named evidence) or
> **`untestable`** (with a structural, falsifiable reason). The
> disposition "could test but chose not to" does not exist.

This is the **Test Completeness Ledger** (Step 7.5). "Testable ⇒ tested"
is enforced mechanically: the F5 `iterate_latest.test_completeness` block
records the ledger and the F11 verifier
`check_test_completeness_ledger`
(`shared/scripts/tools/verifiers/iterate_checks.py`) STOPs the run if any
behavior is testable-but-untested. "I should still test X" therefore
becomes a **blocking work item** — test X now, or prove X structurally
untestable — never a note that ships.

### The closed `UNTESTABLE` vocabulary

`untestable` is honest only with a structural, falsifiable reason. The
reason must come from this closed set (SSoT: `UNTESTABLE_REASON_CODES`
in `shared/scripts/tools/verifiers/iterate_checks.py`; a reverse-drift
test asserts this list and the code agree):

- `requires-prod-credential` — needs a real production secret/credential
  absent from CI.
- `requires-external-nondeterministic-service` — depends on a live
  third-party service with non-deterministic output.
- `requires-physical-device` — needs hardware/peripheral not available
  in CI.
- `requires-manual-visual-judgment` — correctness is a human visual or
  aesthetic judgment (covered by design-fidelity / browser-verify, not a
  unit assertion).
- `requires-interactive-tty` — needs an interactive terminal or login the
  harness cannot drive.
- `covered-by-existing-test` — already pinned by a named pre-existing
  test (cite it in `reason`).

"Hard to test", "out of time", or "low risk" are **not** in this set —
they are the escape hatch the gate exists to kill.

---

## Cross-References

The Confidence Calibration phase consumes outputs from these docs:

- **`references/boundary-probes.md`** — the 8 probe categories the
  phase iterates through when `touches_io_boundary` fires. Source
  of truth for which edge cases to probe.
- **`references/round-trip-tests.md`** — the producer→file→consumer
  test pattern (Section 1) and the duplicated-consumer drift-
  protection pattern (Section 2). Source of truth for *how* to
  write the probes.
- **`references/iteration-reviews.md`** — Self-Review item 7
  (Affected Boundaries) is the upstream gate that surfaces the
  producer/consumer pairs the calibration phase then probes.
- **`SKILL.md`** Phase Matrix (Section 6) — the normative table
  marking the phase as mandatory at medium+ and safety-enforced at
  small with the flag.
- **`SKILL.md`** Override Classes — the formal classification:
  Mandatory at medium+, Safety-enforced at small with
  `touches_io_boundary`, Advisory otherwise.

The phase is the empirical anchor that makes the upstream
producer/consumer identification (Self-Review item 7 + Affected
Boundaries section in the spec) load-bearing rather than
ceremonial. Without the calibration phase, "yes I identified the
boundaries" can ship bugs; with the phase, "yes" must be backed
by named probes + findings.
