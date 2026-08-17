# ADR: Keeping shipped profile security floors honest over time

- **Run ID:** iterate-2026-08-17-vite-hono-floor
- **Iterate spec:** `.shipwright/planning/iterate/2026-08-17-vite-hono-floor.md`

## Context

`shared/profiles/vite-hono.json` declared `"hono": "^4.7.0"`, a floor
vulnerable to CVE-2026-69207/-71848/-71849/-71850 (fix line 4.12.34). Every
project scaffolded from this profile started from that floor. This is not
hypothetical: shipwright-webui carried the identical `^4.7.0` string until
it was hand-patched in PR #180, and leadwright independently patched its own
copy in its PR #8 — two consumer repos, two separate manual remediations,
one shipped floor that never itself changed. The next scaffold would have
reintroduced it a third time.

Investigation (recorded in the iterate spec) traced every reader of
`shared/profiles/*.json`'s `stack` block and found no script that
mechanically writes those values into a generated `package.json`. The
consumption is an LLM-agentic one: `/shipwright-project` scaffolding and
`/shipwright-build` read the profile as descriptive text and copy it by
hand when authoring a new project. There is no code chokepoint today that a
"resolve latest matching version at scaffold time" step could attach to.

## Decision

Fixed the immediate floor (`^4.12.34`). For drift prevention, chose
**option (a) — nothing structural, plus one narrow pinned regression test**:
`shared/tests/test_profile_dependency_floors.py` reads
`shared/profiles/vite-hono.json` directly and asserts its declared hono
floor is `>= 4.12.34`, with a fail-before-proof companion test confirming
the same comparison would have flagged the pre-fix `^4.7.0` value. As a
second, independent, near-zero-cost mitigation, `shared/profiles/vite-hono.json`'s
`notes` field and `plugins/shipwright-project/skills/project/references/
project-scaffolding.md` now tell the scaffolding agent that `stack`
versions are minimums to resolve-latest-against, not strings to copy
verbatim — attacking the same root cause at its actual point of
consumption, not just detecting a regression after the fact.

**This reverses an earlier decision made during this same run.** A general
hand-maintained registry (`shared/config/profile_security_floors.json`) plus
a generic checker script (`check_profile_security_floors.py`) was built
first, and hardened through two real review rounds (internal plan review —
one HIGH + five MEDIUM findings, all fixed; external `--mode iterate`
review — findings fixed or verified false). It was then put through the
architecture-review pass (`--mode architecture`, the pass that asks
*should this exist at all*, run over a brief listing options without their
rejection reasons — see `shared/templates/architecture_brief.md`). Both
independent reviewers pushed back: `openai` verdict `revise`, `deepseek`
verdict `reject`, converging without seeing each other on the same
alternative — a registry + generic checker is more permanent, generally-
applicable machinery than one known stale floor in one profile justifies;
a single pinned test says the same thing with nothing left to explain to a
future reader. Per this pipeline's protocol, a `reject` verdict stops the
run for the operator to decide rather than being resolved unilaterally; the
operator chose to adopt the reviewers' simplification. The registry, checker
and its test file were deleted; nothing was salvaged from them except the
CVE ids (now in this file and the pinned test's docstring) and the
scaffold-instruction sentence, which neither reviewer's objection touched.

## Options weighed

- **(chosen) (a) Nothing structural, plus a narrow pinned test** — bump the
  known-stale floor now; a future vulnerable floor is fixed directly and
  gets its own pinned test at discovery time, the same way this one did.
  Explicitly offered by the requester as a legitimate outcome if chosen and
  stated honestly. Chosen because two independent architecture reviewers
  converged on it being the smallest thing that would actually do the job.
- **(b) A live gate** — check profile floors against a live vulnerability
  database at CI time. Rejected: this repo runs no Dependabot and no live
  vulnerability-database dependency in any existing gate, by standing
  decision (`shipwright-security` IS the scanner, run on-demand against
  built projects, never as a framework-CI dependency).
- **(bounded variant of (b), built then reverted) A hand-curated registry +
  generic checker** — avoids (b)'s live-network cost via a hand-maintained
  registry, same trust model as `shipwright_accepted_risks.yaml`. Built,
  hardened through two review rounds, then reverted on architecture
  review's proportionality objection (see "Decision" above): a registry is
  general, reusable machinery for a problem this pass currently has exactly
  one instance of, and — being hand-maintained — it depends on the same
  human discovery a pinned test also depends on, so it buys generality, not
  more actual coverage, for the ongoing cost of a parser, validation rules,
  and a registry file someone has to remember exists.
- **(c) Scaffold-time resolution** — whatever consumes the profile resolves
  the latest matching version at scaffold time and writes that. The heavy
  reading (a resolver *script*) is rejected: the investigation found no
  mechanical scaffold chokepoint to attach one to. The light reading —
  instruct the LLM-agentic consumer directly — was adopted as a
  complementary mitigation (see Decision above), since it costs one
  sentence and attacks the actual point of consumption.

## Accepted cost — stated honestly

This is a **regression guard for one known floor, not general drift
detection.** It catches this profile's hono floor moving backward below
4.12.34; it says nothing about a *different* package or profile going stale
in the future, and nothing detects that until someone notices and adds
their own pinned test the way this one was added. That is deliberately a
smaller promise than the registry approach made, and — per architecture
review — an honest one: the registry's promise of broader coverage was
never backed by more than the same manual discovery this narrower approach
also depends on. The scaffold-instruction sentence is prose, not an
enforced gate — it lowers the odds of a future stale floor being copied
into a new project, it does not guarantee it.

The scaffold-instruction sentence was added only to `vite-hono.json`'s
`stack._comment` (and the corresponding `project-scaffolding.md` doc), not to
`supabase-nextjs.json` or the repo's other profiles — code-review flagged this
asymmetry. Left as-is deliberately: this card scoped a known-vulnerable floor
in one profile, explicitly ruled out opening a general dependency-refresh
campaign, and no known-vulnerable floor was found in the other profiles in
this pass. Extending the sentence to profiles with nothing currently wrong
would be exactly that out-of-scope campaign, one profile at a time.

## Consequences

Every future scaffold from `vite-hono.json` starts at `^4.12.34` or above.
A regression in *this specific* profile/package pair fails CI immediately.
A vulnerable floor discovered in a different profile or package in the
future gets the same treatment applied fresh: fix it, pin it with its own
test, done — no registry entry, no shared parser to keep correct.

## Rejected alternatives

See "Options weighed" above: (b) a live vulnerability-database gate
(rejected — no live network dependency in this repo's gates, by standing
decision), the hand-curated registry + generic checker (built, reviewed,
then reverted on the architecture-review pass's proportionality objection —
converging `revise`/`reject` from two independent reviewers), and (c)'s
heavy resolver-script reading (rejected — no mechanical chokepoint exists
to attach one to; its light prompt-level reading was adopted instead).

## Tests

`shared/tests/test_profile_dependency_floors.py` — two tests: a pinned
assertion that the real, shipped `vite-hono.json` hono floor is `>=
4.12.34`, and a fail-before-proof test confirming the same comparison logic
would have flagged the exact pre-fix `^4.7.0` value. Both the external
review round (deepseek + openai, `--mode iterate`) and the internal plan
review (opus-plan-reviewer, HIGH severity) drove real fixes to the
now-deleted registry/checker before the architecture-review pass concluded
that mechanism was disproportionate; see the iterate spec's `##
Architecture Review` and `## Internal Plan Review` sections, and the
mini-plan's `## Review Findings — Reconciliation`, for the full history.
