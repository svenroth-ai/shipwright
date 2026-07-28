# ADR-115 — The requirement write-back loop: one declaration, two call sites

> Renumbered from 113 after merge: #438 took that number first and other
> decision records already cite ADR-113 meaning
> `113-override-the-verdict-not-the-check.md`. Two parallel iterates each
> read the highest number before the other landed.

- **Run ID:** iterate-2026-07-27-requirement-writeback-loop
- **Date:** 2026-07-27
- **Status:** accepted
- **Requirements:** FR-01.04 (`/shipwright-design`), FR-01.05 (`/shipwright-build`)
- **Triage anchor:** trg-e9e5188e (supersedes trg-35785118, trg-ed419fd7)

## Context

Two phases could learn something about the product and not tell the requirements.

**Design.** A feedback round already wrote back into the requirements file — but
only *pointers*: which screen stands for which requirement, and cross-reference
tags. Nothing wrote back *substance*. So when a round added an option, removed a
step, or reordered a path through the product, that stayed in the mockup and the
requirement kept describing the older intent. This sat in the phase where flows
are rightly rethought, which makes it a first-class source of exactly the drift
the surrounding campaign exists to remove.

**Build.** Two criteria governed the phase — *implement exactly what the section
specified* and *never ignore the mockup*. When the approved mockup and the
section's description contradict each other, both cannot be satisfied, so
whichever one the builder happened to follow won **silently**. The autonomous
path made it worse: its documented source-of-truth ladder (`Spec > … > Mockup`)
resolved the contradiction automatically, discarding the design a human had
judged against real use. Separately, "nothing outside the section's scope", read
literally, made a section that cannot function without touching something shared
**unbuildable** — never the intent; the rule is aimed at unrequested extra work.

## Decision

Give both call sites the declaration `/shipwright-iterate` already runs: declare
a requirement impact per unit, and refuse to finish unless a requirements file
was genuinely touched or a one-line reason was given for touching none.

- **Design** (`review-loop.md` Option B): a behaviour-vs-appearance read, a
  Spec Backflow row for **substance**, and a per-round declaration. Option A
  gains a Requirement Write-Back Gate that *exits non-zero*.
- **Build** (SKILL.md Step 1 / Step 10b): a contradiction **STOP** rule naming
  the expected resolution (correct the requirement to match the mockup), a
  per-section declaration, and an attribution check over the section's own
  commit. The shared-touch carve-out is stated at every site that states the
  scope rule.

Judging behaviour-versus-appearance, and detecting a prose-versus-markup
contradiction, stay **human reads** — both need comprehension no check can
supply. The declaration and the touch check do not, and those are mechanised.

## Evidence is never the caller's to supply

This is the load-bearing part, and it took three review rounds to get right.

A build section is judged against **its own commit** (`HEAD^..HEAD`, immediately
after Step 8). Passing the branch base instead puts every earlier section inside
the current section's range; a degenerate range (`base == head`) is refused
outright, because an empty diff would pass any declaration.

A design round has no commit, so it captures **a baseline** before it revises
anything and is judged against that. The first implementation used
`git diff HEAD` plus `git ls-files --others`; adversarial review showed it was
**vacuous in the standard pipeline** — nothing commits before the build phase, so
every `spec.md` the project phase wrote is untracked, was therefore listed as
"changed", and *any* `--impact modify` passed on a spec nobody had edited. The
baseline restores the boundary a commit gives a section, and works whether or not
anything has ever been committed. The baselines double as the round registry the
completion gate reads — deliberately not the gitignored
`design-feedback-round*.md` scratch, whose absence resolved to PASS.

## Storage: one file per declaration

`.shipwright/planning/requirement-impact/<run_id>__<phase>__<scope>__<digest>.json`

The first draft used a single tracked JSONL. Four independent review findings
killed it: concurrent append tearing, an undefined merge-conflict policy for a
new tracked append-log, corruption that hides rather than names itself, and a
scope identity (`round-1`) that recurs across runs so a stale row could satisfy a
later run's gate. A file per declaration answers all four **structurally** — no
`merge=union` entry, no churn-resolver participation, identity enforced by the
filesystem, damage isolated and nameable. The digest is over the raw
`(run_id, phase, scope)` tuple because filename sanitization is lossy.

## Consequences

- Design finalization refuses while a round is silent about what it did.
- A build section fails if it records no declaration, changes an undeclared file,
  or **deletes** one — the most destructive out-of-scope change was previously
  the one class needing no record at all.
- Artifacts the phase itself must write are excluded as a named category
  (`section_file_list.FRAMEWORK_BOOKKEEPING`), because `git add -A` sweeps the
  previous section's bookkeeping into the next commit. Stated, not hidden.
- New tracked artifact directory; no `.gitignore` change was needed (the canon
  `!/.shipwright/planning/` re-include already covers it).

## Alternatives rejected

1. **A `requirement_impact` event on `record_event.py`.** It is already over its
   bloat baseline (the FR gates were extracted for exactly this reason); a design
   *round* and a build *section* are neither a phase nor an iterate, so identity
   would have to be smuggled into `detail` — precisely the un-checkable shape
   this work replaces; and `shipwright_events.jsonl` has a churn-merge resolver
   tuned to its current producers.
2. **Have the design round edit the spec with no declaration.** It cannot express
   the honest `none` case. Most rounds *are* appearance-only, so forcing a spec
   edit on each would train the phase to make empty edits — worse than no check.
3. **A single tracked `requirement-impact.jsonl`.** See "Storage" above.
4. **Letting the caller pass a path list as evidence.** A declaration able to
   name its own evidence checks nothing.

## Verification

243 new tests, all executed and passing. Full suites green: shared 5158,
build 110, design 32, integration 418; `uvx ruff@0.15.15` clean; anti-ratchet
clean. Five review passes recorded (self, plan, code, doubt, external_code) —
each of the last three found defects that arrived *after* the work looked
finished, which is why the Confidence Calibration in the iterate spec treats
them as probes rather than formalities.
