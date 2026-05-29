<!--
================================================================================
READ THIS BEFORE OPENING THE PR
================================================================================
Most AI-generated PRs to this repo are rejected. Not because the code is
bad — because the process around the code is skipped. The questions
below exist to stop that. Fill them in completely; PRs that leave them
blank or paste fluff like "n/a — small change" are closed without review.

If you are an AI agent (Claude, Codex, Copilot, …):
  1. You may not open this PR until a human has approved the approach
     in a preceding issue, ADR, or iterate spec.
  2. You may not open this PR if a duplicate already exists (search
     `is:pr in:title <keywords>` in BOTH open and closed PRs first).
  3. You may not open this PR if any unchecked statement below is
     still unverified. "I think it passes" is not verification.
================================================================================
-->

## Human Authorization

> **Iron Law:** NO PR WITHOUT A HUMAN-APPROVED APPROACH FIRST.
> (See `CONTRIBUTING.md` — skill/hook/agent changes require an issue;
> all other changes require either an issue, an iterate spec, or an
> ADR.)

- [ ] A human reviewed and approved the approach before code was written.
- [ ] Approval is linked: issue, ADR, or iterate-spec → #_____ /
      `path/to/spec.md` / `path/to/adr.md`.

## Duplicate Search

> **Iron Law:** NO PR WITHOUT A DUPLICATE SEARCH FIRST.

- [ ] Searched **open AND closed** PRs for the same change.
- [ ] No duplicate found, OR: this PR explicitly supersedes #____ (note
      why).

## Summary

<!-- What does this PR do? One or two sentences. Concrete, not vague. -->

## Motivation

<!-- Why is this change needed? Link the issue / ADR / spec. -->

Closes #

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation / comments
- [ ] Tests only
- [ ] Refactor (no functional change)
- [ ] Build / CI / tooling

## Verification

> **Iron Law:** NO PR WITHOUT EMPIRICAL VERIFICATION FIRST.
> Each statement below is a claim about reality. If you cannot point at
> a command, a log, a screenshot, or a test output that proves it, do
> not check the box — go run it.

- [ ] Tests added or updated where applicable, AND **the new tests fail
      without my change** (verified by running them on the base SHA).
- [ ] Full relevant test suite run locally; **exit code 0** captured in
      the Test Plan below (paste the last 10 lines or attach a log link).
- [ ] Linter / type-check run locally; exit code 0.
- [ ] Security scanners run locally
      (`uv run plugins/shipwright-security/scripts/tools/scan.py` +
      `prompt_injection_scan.py`); findings addressed or explicitly
      deferred with rationale.
- [ ] No "all tests pass" claim when output shows failures — actual
      numbers reported below.

## Test Plan

<!--
Paste the EXACT commands run and the LAST FEW LINES of their output.
Screenshots welcome for UI changes. "It works on my machine" is not a
test plan.
-->

```
$ <command>
<output excerpt>
```

## Anti-Slop Self-Check

> Apply the four Karpathy principles from `shared/constitution.md`
> ("Pre-Phase Principles") to this diff before requesting review.

- [ ] **Think Before Coding** — The linked issue/ADR/spec captures the
      problem, at least one alternative considered, and the decision.
- [ ] **Simplicity First** — No premature abstractions, no single-use
      helpers, no flags with one caller. Three similar lines beat a
      wrong-shape abstraction.
- [ ] **Surgical Changes** — Every file in this diff is here for the
      stated intent. Bug-fix scope = bug. Refactor scope = refactor.
      Docs scope = docs. Mixed scope = split into separate PRs.
- [ ] **Goal-Driven Execution** — Every edit traces back to an
      acceptance criterion, FR, ADR, or iterate intent. No drive-by
      improvements without a goal.

## High-Sensitivity Change?

<!-- Check if this touches any of these areas (see CONTRIBUTING.md for the full list): -->

- [ ] Changes to hooks configuration
- [ ] Changes to skills or agents
- [ ] Changes to the orchestrator (`shipwright-run`)
- [ ] Changes to the security plugin
- [ ] Changes to CI/CD workflows
- [ ] New external dependency
- [ ] None of the above

If any box is checked, link the preceding design issue: #

## Checklist (mechanical)

- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/).
- [ ] Commits are signed off (`git commit -s`).
- [ ] Documentation updated where applicable (CLAUDE.md / `docs/guide.md` / `docs/hooks-and-pipeline.md`).
- [ ] For skill/hook/agent changes: I opened an issue first and had the approach approved.

## Additional Context

<!-- Anything else the reviewer should know. -->

---

<sub>Anti-slop framing (Iron-Law / human-approval / duplicate-search / verification-before-completion) adapted from [`obra/superpowers`](https://github.com/obra/superpowers) (MIT, © Jesse Vincent). Karpathy 4 principles cited verbatim from [`multica-ai/andrej-karpathy-skills`](https://github.com/multica-ai/andrej-karpathy-skills) (MIT, © 2025 multica-ai).</sub>
