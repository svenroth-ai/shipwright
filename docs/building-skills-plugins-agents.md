# Building Skills, Plugins and Agents: What Goes in Code, What Goes to the AI

> The rule for deciding, step by step, whether a skill, plugin, hook or agent
> does something in code or asks the AI to do it. It applies to every plugin
> in this monorepo and to the deterministic-first programme that converts
> skill prose into code. For the maintenance steps after a plugin change
> (cache sync, restart), read `shared/prompts/writing-plugin.md`.

## The rule

1. **Checks and comparisons go in code.** Counting, matching, comparing,
   checking that a file, an id or a field exists, checking an order: a
   script, a test or a gate does it, not an instruction in a `SKILL.md`.
2. **Interpretation and wording go to the AI.** Reading what a user meant,
   judging whether a sentence states one capability, writing release notes,
   summarising a diff.
3. **Code validates every AI output.** The AI's answer goes through a schema
   or a rule check before anything acts on it. An answer that fails the check
   is never used as if it had passed.
4. **Every AI step has a fallback.** When the AI fails, times out or returns an
   answer that fails validation, the step knows what happens next (see
   "Choosing the fallback" below).

The goal is to be as deterministic as possible, and no more than that. The
three sharpenings below keep the rule from turning into false determinism.

## The deciding question

**Can the answer be checked without understanding language?** Then code. If
not, the AI.

A code heuristic that guesses meaning (a keyword list deciding whether a
change is "a feature", a regex deciding whether a sentence is "atomic") is
wrong reliably, and it looks trustworthy because it is code. Never let such a
heuristic decide. It may *propose*, labelled as a proposal, when a judge (the
AI or the operator, the person running Shipwright) confirms or rejects it.

The pattern to copy is `fr_cluster_report.py`, from the atomic-frs work on
splitting requirements that hold more than one capability. Code groups a
requirement's acceptance criteria (ACs) by the tests, source files and wording
they share, and proposes a cut. The AI or the operator then judges whether a
sentence states one capability. Each side does only what it can do reliably.

## Code checks form and rules, not truth

Code can check that every AC appears exactly once, that an id exists, that a
file was touched. It cannot check that a wording is right or that a declared
fact is true.

- Whether something is *correct* needs a second judge: a review (the review
  of each AC after the build, `post_build_ac_check.py`, is the pattern) or
  the operator.
- "Checked by code" never reads as "correct", in a report, a PR body or a
  gate message. Say what was checked: "every AC is named once", not "the ACs
  are right".
- When a check rests on something the AI declared (for example the kind of
  change it says it made, or the files it says it touched), say so where the
  check reports its result.

## Choosing the fallback

The fallback is chosen per AI step when the step is built, never left to
whatever happens at runtime.

| Where a wrong answer… | Fallback | Today's example |
|---|---|---|
| does harm: a wrong cut, a wrong version, a wrong merge, lost data | **stop** and hand the decision to the operator | the STRICT-STOP of the deterministic-first campaigns: a unit that converts prose to code halts and waits for the operator |
| is cosmetic, and a later reviewer sees it | **continue with a warning** that names what was not checked | the review of each AC after the build, which only warns for now |

When in doubt, the case does harm.

A step that has no written fallback is not finished.

## When building a skill

- The `SKILL.md` names the decision and the script that makes it. It does not
  restate the script's logic in prose; prose that copies code drifts from it.
- A script whose result the next step must check offers structured output
  (for example a `--json` flag with a fixed shape) and documented exit codes.
- An AI prompt states the exact shape of the answer it expects, and the code
  that receives the answer checks that shape.
- Tests pin behaviour, not prose. A test that greps a `SKILL.md` for a
  sentence protects the sentence, not the behaviour. Checks of a `SKILL.md`'s
  structure, and tests of a file that code reads at runtime, are behaviour
  and stay.

## Relation to Anthropic's skill guidance

Anthropic's [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
gives the same direction: scripts for fragile operations that must be exact,
prose for steps that need judgement. This file is stricter in two ways: it
requires code to validate every AI output, and it requires a chosen fallback
per AI step. **On any conflict, the Shipwright rule in this file wins.**
