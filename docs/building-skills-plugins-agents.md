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
- A script reports a documented exit code and a message that names the fix;
  it handles its own errors instead of leaving them for the AI to cope with.
  A number a script uses carries its reason next to it.

## The machine-readable half

Whatever a tool can read, and that is true for every project whatever its
stack, lives in `shared/config/conventions.json`: one file, one section per
topic. The `skill_authoring` section holds, once, **every number** (name and
description length, `SKILL.md` body size, reference depth, table-of-contents
threshold, the two Claude Code runtime caps, which are still unverified) and
the alignment list with Anthropic's guidance. The four rules above are prose
and stay only here. This file explains and links; it does not repeat a
number, so a limit changes in one place. Values that depend on the stack do not
go there: they live in the stack profiles (`shared/profiles/`), which refine
the conventions and never contradict them.

`uv run shared/scripts/tools/check_skill_authoring.py --all` reports every
skill that breaks a limit. It is a report, not a gate: it is not in CI, a
`hard` finding exits 1, a `recommended` one only with `--strict`. A rule that
can be written as data belongs in that file, not in prose here; the
deterministic-first conversion of a skill moves such rules out of its
`SKILL.md` the same way.

## How to add an architecture rule

An architecture rule says what a project of a stack must keep and how that is
kept. Rules live in a stack profile under `architecture_rules`; the format and
the profile lookup are in [stack-profiles.md](stack-profiles.md#architecture-rules-architecture_rules),
which this section does not repeat. The code reviewer reads the rendered rules
from `conventions.md` and checks every diff against them.

**The fields.** `id` (lowercase letters, digits, hyphens), `text` (what is
required), `why` (the reason, one sentence), `enforcement` (how it is kept),
and either `lint` or `mechanism`, never both, plus a `note` (required for `prompt-only (mechanisable)` and `unimplemented`, optional otherwise). A rule
with a lint fragment is class `validator`; `hook`, `test` and `validator` carry
the files that do the checking, the other classes carry neither.

**Enforcement is a closed list:** `hook`, `validator`, `test`,
`prompt-only (mechanisable)`, `prompt-only (judgement)`, `unimplemented`. Be
honest: a mechanism counts only if something invokes it in the project. A checker
nobody runs is `prompt-only (mechanisable)` with a `note` saying so. A rule that
needs judgement is `prompt-only (judgement)`; the reviewer then needs a cited rule
and the offending line before it raises a finding.

An example of a judgement rule:

```json
{
  "id": "one-place-for-retry-policy",
  "text": "Retry and backoff settings are defined once in the shared client module, never per call site.",
  "why": "One place to change how the project behaves under failure.",
  "enforcement": "prompt-only (judgement)"
}
```

And a rule whose check is a test that runs (the path must exist, relative to the
repository for a bundled profile and to the project root for your own):

```json
{
  "id": "rules-keep-their-shape",
  "text": "Every architecture rule declares an id, a text, a why and an enforcement class.",
  "why": "A rule without its class looks enforced when it is not.",
  "enforcement": "test",
  "mechanism": ["shared/tests/test_profile_architecture_rules.py"]
}
```

A test loads both examples with the real loader, so they cannot drift from it.

**Where the profile lives.** A bundled profile is a file in `shared/profiles/`;
a project's own profile is a file in `.shipwright/profiles/` and wins over a
bundled one of the same name. To start from a bundled profile, copy it under
your own name. Mechanism paths of a bundled profile are relative to the
Shipwright repository and do not exist in your project: change such a rule to
`prompt-only (mechanisable)` or `prompt-only (judgement)` in the copy, or point
it at a file of your own. The Shipwright repository's own
`.shipwright/profiles/shipwright-monorepo.json` is the worked example.

**Check and re-render.** `uv run shared/scripts/tools/resolve_profile.py validate`
reports rule errors (a wrong rule never invalidates the profile, it is left out).
`uv run shared/scripts/tools/render_architecture_rules.py --project-root .`
writes the rules into the marked block of `.shipwright/agent_docs/conventions.md`;
with `--check` it writes nothing and exits 1 when the block is stale. The drift and
pin tests (`shared/tests/test_profile_architecture_rules.py`,
`test_render_architecture_rules.py`, `test_claude_plugin_profile.py`,
`test_shipwright_monorepo_profile.py`) fail when a profile, its mechanism paths or
this repository's rendered block go out of step.

**Known limits.**
- `conventions.md` is merged with the union strategy, so a parallel merge can leave
  a stale or duplicated block. `render_architecture_rules.py --check` catches a stale
  one (exit 1) and a duplicated one (exit 3). The reviewer has no shell: it reports
  duplicated or unpaired markers and, for a project profile found under the project root, rule ids that differ from it (a bundled or user-level profile is noted as uncheckable), and only
  `--check` is the full staleness test.
- For `supabase-nextjs` the build phase can replace `eslint.config`, which drops the
  lint fragments of its rules. This is an open follow-up.

## Relation to Anthropic's skill guidance

Anthropic's [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
gives the same direction: scripts for fragile operations that must be exact,
prose for steps that need judgement. It adds measurable limits, which the JSON
file carries, and the point that references stay one level deep and that a long
reference opens with a table of contents. This file is stricter in two ways:
it requires code to validate every AI output, and it requires a chosen
fallback per AI step. The `alignment` list in the JSON says, rule by rule,
whether it is adopted, already covered, not adopted (with the reason) or left
to a reviewer. **On any conflict, the Shipwright rule in this file wins.**

**Read this before** building or changing a skill, hook or agent, and before
running the deterministic-first conversion of a plugin. `CLAUDE.md` and
`shared/prompts/writing-plugin.md` point here for that reason.
