# Post-build per-AC check, phase 1 (warning only)

Run: `iterate-2026-11-07-ac-q2-post-build-check`. Plan: `.shipwright/planning/campaigns/2026-11-07-ac-at-start-Q2-PLAN.md`. Measurement: `.shipwright/planning/campaigns/2026-11-07-ac-at-start-Q2-MEASURE.md`.

## What was decided
- Code builds the claims file (`ac-claims.json`) from the committed AC record and the merge-base catalog; the shared `spec-reviewer` takes it as an optional third input and answers `matches|diverges` per claim with the diff line; `record_review_pass.py` carries the cleaned `ac_verdicts` onto the completed `spec` row; the F11 check `check_post_build_ac_review` reports them as a warning and says visibly when no AC review ran.
- An unconfirmed `auto` item can only ever warn (operator decision, both phases). Operator-confirmed and code-decided items are reject-grade, but phase 1 never refuses anything and per-AC answers do not change the Stage-1 verdict.
- `ac-claims.json` is derived and gitignored; F11 recomputes the claims from the committed record.

## Measurement, both readings
5/5 altered copies caught. 2 of 5 "correct" ACs were flagged (#859 backfill AC09, #920): checked against the real code, both are genuine overstatements in the AC wording (guard failure can block via the fallback grep; the start path writes the config before the package is verified). Literal label reading: bar missed (2/5). Evidence reading: bar met (0 unsupported alarms). n=10, assistant-written alterations: it cannot show the real false-alarm rate, which is measured on the first 20 iterates.

## Known follow-ups
PHASE-2 PRECONDITIONS (needed before any refusal is wired):
1. Verdicts are matched to claims by AC id only; there is no claims fingerprint, so a verdict cannot be proven to belong to this claims file.
2. The `reviews.json` spec row is not cross-checked against the committed `spec_review_reply.json`.

Other:
- Campaign 3f-bis and the Codex dispatch path never pass the claims file, so they always print "no AC review ran"; measure them separately in the 20-iterate report.
- BRIEF Q2.1 and the PLAN differ on `weakens` for operator-approved changes; the operator must decide before phase 2.
- Code-decided items are reject-grade although `confirmed=false`; revisit with the phase-2 decision.
- Two backfilled ACs overstate the code (AC09 #859, the #920 AC): correct the wording or the code.
- Not done on purpose: a shared prologue helper with the Q1 check, a claims fingerprint, the reply cross-check.

## Architecture Review
glm approve; openai REJECT (prefers the prose-only option 2: no claims file, no F11 reporting). Not halted: the operator approved the design in the plan (`2026-11-07-ac-at-start-Q2-PLAN.md`, item 1: code builds the input, the model only judges), and the coordinator handed this run a closed fix list on that design. The rejected alternative stays on record; the first 20 iterates decide whether the claims file earns its keep.

## External-Plan-Review-Findings (glm revise, openai revise)
| Finding | Disposition |
|---|---|
| Wiring of claims into the iterate flow and an end-to-end test (openai high) | accepted-in-part: SKILL.md and iteration-reviews.md say when to build and pass the file; tests cover each hop (record, claims, reply to spec row, F11) but there is no single end-to-end test |
| Missing, duplicate, unknown verdicts leave claims unchecked (openai) | accepted-and-fixed: repeated ids merge, an unknown verdict value counts as no verdict, an unreviewed claim is named |
| Staleness between claims, run and reviewed revision (openai) | rejected-with-reason: phase-2 precondition (claims fingerprint), listed above |
| Require a usable line for `diverges` (both) | rejected-with-reason: F11 prints "no line given"; schema enforcement is a phase-2 item |
| Net-zero lines in the bloat-capped file (glm) | rejected-with-reason: the baseline forbids growing it |
| Prompt drift for /shipwright-build (glm) | accepted-and-fixed: prompt-contract test, optional-input wording |

## External-Code-Review-Findings (openai revise, glm approve)
| Finding | Disposition |
|---|---|
| Unknown verdict value counted as a match (openai medium) | accepted-and-fixed: such rows count as no verdict (test) |
| `diverges` without a line retained (openai medium) | rejected-with-reason: shown as "no line given", visible; see above |
| `weakens` label on a non-change claim (glm low) | accepted-and-fixed: only reported for `change` |
| Remove claim with no resolvable base text (glm low) | follow-up |
| Test patched a module attribute directly (glm low) | accepted-and-fixed: monkeypatch.setattr |

The coordinator-spawned opus reviewers (spec PASS, code no HIGH + 7 edge items, doubt no HIGH + 2 medium + 4 low) are summarised in the review record; the spawn guard allows 3 spec-reviewer spawns per runner.
