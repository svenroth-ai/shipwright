# Iterate — reviewer verdicts are read, and disagreement is its own outcome

- **Run ID:** `iterate-2026-07-27-plan-verdict-record`
- **Date:** 2026-07-27
- **Intent:** CHANGE · **Complexity:** medium · **Spec Impact:** MODIFY (FR-01.03)
- **Triage:** `trg-88f721be` (high, P1) — part 1 of 3
- **Evidence:** `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  → FR-01.03 row 10

## Why this is one of three

`trg-88f721be` is a per-plugin work unit covering three gaps in
`/shipwright-plan`. Built as one change it came to ~5,000 diff lines, which is
past what the Tier-3 PR review gate can read — it truncates and fails closed,
so **the change could not be reviewed at all**. The documented override is a
manual review plus a `skip-pr-review` label; the operator declined it, on the
grounds that a change whose whole subject is "a gate must not be satisfiable
without the guarantee behind it holding" should not itself ship through a
bypass.

So it ships as three PRs the gate can read, in dependency order:

1. **this one** — reviewer verdicts + contradiction recording;
2. section dependency declaration + order check (independent of this);
3. the four Step-9 gates (needs `evaluate_review_state` from here, and the
   manifest parser from 2).

Four review rounds were run against the combined branch first
(`iterate/plan-phase-gates`, 2aa8a105); nine defects found and fixed. Their
dispositions are recorded in `2026-07-27-plan-phase-gates.md`, and the fixes
are carried into these three PRs. The truncation itself is filed separately —
a review gate with no way to review a large change is a gap in its own right.

## Problem

`external_review.py` runs Gemini and OpenAI in parallel and preserves both
full texts. Everything downstream — `mark-review-state.py` →
`external_review_state.json` → `plan_compliance.check_w5_external_review_marker`
→ the `setup-planning-session.py` resume gate — reduced the pair to one
`status` and one integer `findings_count`. One reviewer approving while the
other called the approach fundamentally wrong was therefore indistinguishable
from an ordinary finding count. Two independent reviewers exist so that
disagreement gets noticed; averaging it away made the second reviewer
worthless.

## Acceptance Criteria

**AC1 — verdicts are read, not summarised.** Each reviewer ends with
`SHIPWRIGHT_VERDICT: approve | revise | reject`. The parser accepts it only
when exactly one line of the reply *purports* to be a sentinel line (the token
opens the line), that line is the reply's last non-empty line, and it is
well-formed. Zero, two or more, an unrecognised word, trailing prose or
punctuation, or a truncated reply all yield `unknown`. A sentinel quoted inside
prose is not a line and is ignored. Tolerated on that line: markdown emphasis,
code ticks, a list marker or blockquote, case variation, padding around the
colon — a closed set; a heading marker and trailing punctuation are not in it.
A verdict is never inferred from prose, headings, or finding severities.

**AC2 — contradiction is its own outcome.** One reviewer approving while the
other rejects is recorded as a contradiction, not a finding count. The
comparison is a pure function of the two verdicts: rank approve/revise/reject
0/1/2, and a contradiction is ranks two apart. `approve` vs `revise` is a
difference of degree the finding list already carries.

**AC3 — anything that stops the pair being comparable is put to the person.**
The plan cannot be declared reviewed while any of these lacks a recorded
resolution: the reviewers contradict each other; a verdict could not be read;
only one of the two answered (one approving review is not what two reviewers
guarantee); or the recorded pair is not the two reviewers that run. A
`completed` marker where **neither** answered asks for no decision — there are
no sides — but still blocks: it is not a review, and the remedy is to re-run it
or record the appropriate `skipped_*` status with a reason.

**AC4 — the disagreement is derived on read, not trusted.** The marker's
stored `contradiction` block is a convenience for readers; every gate
recomputes it from `verdicts`. A hand-edited or half-written marker whose
summary disagrees with its own verdicts must not walk through.

**AC5 — one authoritative reading of review state.** The compliance `W5`
check and the `setup-planning-session.py` resume gate decide via one shared
`evaluate_review_state`, so they cannot drift into two definitions of
"reviewed". (The in-session Step-6 gate joins them in PR 3.)

**AC6 — a marker written before verdicts existed is flagged, not stranded.**
A `completed` marker with no verdicts is ambiguous by construction: either it
predates the field, or this run omitted `--verdict`. The evaluator returns a
third state and the callers resolve it differently — `W5` warns, because it
audits plans of any age; the in-session gate blocks, because the marker it
reads was written moments ago and omitting the flags must not be a way to opt
out of the check.

## Non-goals

- The section-dependency and Step-9 gate work — PRs 2 and 3.
- Raising the PR review gate's size limit; filed separately.

## Affected Boundaries

| Boundary | Producer | Consumer |
|---|---|---|
| reviewer feedback text | Gemini / OpenAI | `review_verdict.parse_verdict` |
| `external_review.py` stdout JSON | the CLI | plan SKILL Step 5, iterate Step 4 |
| `external_review_state.json` | `mark-review-state.py` | `plan_compliance` W5, `setup-planning-session` resume gate |

Round-trip pair: `external_review_state.json` — written by the CLI, read back
by two independent consumers.

## Design decisions

**Why a sentinel and not derived severity.** An approving reviewer routinely
files a high-severity refinement, and a rejecting one may file none because the
objection is structural. Severity measures individual findings; the
contradiction that matters is about the approach as a whole. Deriving it would
manufacture disagreement where there is none and miss the case that matters.

**Why not a third LLM adjudicating.** Not deterministic, and it re-hides the
disagreement behind another summary. The decision is the operator's; the
machine's job is to make sure they see it.

**Why counting sentinel *lines*, not tokens.** An earlier version counted the
token anywhere in the reply and a real review broke it immediately: a reviewer
whose finding quoted the sentinel mid-sentence, then gave its actual verdict at
the end, was read as `unknown` and a genuine `reject` was thrown away. A quoted
mention inside prose is not a line. A reviewer that genuinely wrote two
verdicts on two lines is still ambiguous and still reads `unknown`.

**Why `unknown` blocks.** An unreadable verdict is not agreement. Being wrong
in the blocking direction costs one recorded sentence; being wrong the other
way is exactly the hole this closes.

## Confidence Calibration

- **Boundaries touched:** reviewer feedback text, `external_review.py` stdout,
  `external_review_state.json`.
- **Empirical probes run:**

  | Probe | Finding |
  |---|---|
  | Ran the parser against the real reviewer replies this work received | The decisive probe, twice over. It disproved two successive versions of the rule — see "Design decisions" |
  | `mark-review-state.py` writes a contradicting marker; read back by both consumers | `evaluate_review_state` → `block`; `W5` → `FAIL`. Two readers, one answer |
  | Fed `external_review.py`'s own `verdicts` block through the CLI | Gate blocks; the stored contradiction block is byte-identical to the live one |
  | `external_review.py` line count vs its bloat baseline | 430 → 414: the default prompts moved beside the loaders they back up, so the file shrank rather than needing an exception |

- **Test Completeness Ledger:** machine-readable block in
  `shipwright_test_results.json.iterate_latest.test_completeness`. Every
  behaviour `tested` or `untestable` with a closed-vocabulary reason code;
  **0 testable-but-untested**.

- **Confidence-pattern check.** *Asymptote:* the verdict rule was rewritten
  three times, each time because real reviewer output disproved the version in
  place — depth came from running it, not from thinking harder. *Coverage:*
  every AC has a test that fails if the behaviour regresses. *Integration:*
  `cross_component` did not fire — no hook, phase-validator entry point, merge
  resolver or campaign machinery is touched; the composition that matters here
  is the marker round-trip, probed above.

- **Degraded conditions:** `touches_auth` fired from message prose (the
  classifier keyword-matches the message, not the diff); `risk_detectors.py` is
  diff-authoritative and no auth path is touched. Recorded as a known false
  positive.

## Rollout / blast radius

This repo was adopted, not planned, so it has no `plan.md` — `W5` and the
resume gate are exercised by synthetic fixtures here. The behaviour lands for
projects that run `/shipwright-plan`. Markers written before this change carry
no verdicts and are handled by AC6 rather than failed.
