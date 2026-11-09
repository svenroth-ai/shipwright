# Mini-plan: Q1 pre-build AC

Goal: before the build of a feature or change, record the exact AC text (old and new for a change), or an exemption by outcome, or the AC a restore restores; ask the operator on a fixed short list; freeze the text with a hash.

Work: lib/ac_decision.py (lexical HOW test, table, validation, hash, stub lines); tools/ac_decision.py (CLI, exit 0/10/2, autonomous escalation); write_plan_stub --ac-decision; advisory F11 check pre_build_ac_check; runner schema reason_code ac_question_requires_operator; prose in path-a Step 2a, path-b, runner Step 3 (net-zero lines), F5b, hooks-and-pipeline; AC49 under FR-01.11; tests.
Measure: replay of 25 baseline PRs, question sheet, post-merge report note.

## Architecture Review

Source: `architecture-review-raw.json` in this folder (mode architecture, run `iterate-2026-11-01-q1-pre-build-ac`, captured 2026-11-01). Verdicts as recorded: **glm = approve, openai = revise** (the file's own contradiction check: "verdicts agree within one step", no resolution required).

- **glm (approve)** said option 3 is the right size, with three low findings: keep the ask/auto table to the fixed triggers (a new trigger is a campaign-level change); include one signal that the advisory output influenced a decision; and drop back to option 2 if the control comes within 1-2 PRs.
- **openai (revise)**, one medium finding (proportionality), verbatim: "The eleven omissions justify moving the decision before the build, but do not establish that prose with an explicit decision record is insufficient. Adding several permanent enforcement parts before measuring that smaller intervention is premature." Suggestion: "Measure option 2 against the required control first. Add a local check only if observed failures show agents skipping or altering the pre-build record, and target that demonstrated failure."

**Reconciliation (what was asked, what we did, what we deliberately did not do).**

- Asked: measure the prose-only option against a control before adding enforcement; keep any check narrow and targeted.
- Done: the design was cut down after the first measure instead of growing. The lexical HOW test, the hash protocol and the label exemptions were dropped; one ask rule remains (an existing AC is changed or removed, or no single requirement owns the new one). The check is advisory only (an F11 warning, never a PR block), the ask/auto/off modes keep the operator able to turn the question off, and every record item carries `decided_by` and `confirmed`, which is the signal glm asked for that the advisory output influenced a decision. Success is measured on the first 20 real iterates with a stop rule (ask rate above 30 percent, or the operator rejects more than 3 of 10 sampled ACs).
- Deliberately not done: the prose-only arm was not measured against a control, because the label-based control is not measurable in the deterministic design (see the MEASURE document, which records this and the decision taken under delegation on 2026-11-07). There is no blocking PR check, and no further trigger was added in this unit. The reason the code path stays: the eleven omissions came from the author choosing the exemption by label, which prose alone had already failed to stop; the operator decided on 2026-11-01 that everything code can decide is decided by code.
- Evidence: the decision drop `iterate-2026-11-01-q1-pre-build-ac_001.json` and the three review rounds on this branch (spec-reviewer, code-reviewer, doubt-reviewer), each closed by a commit.
- Reversible: if the first 20 iterates miss the stop rule, drop back to prose plus the freeze, as glm and openai both describe.
