# The code reviewer reads the architecture rules block

Run: iterate-2026-11-16-u6-reviewers-docs (campaign profile-architecture-rules, unit U6, the last). No FR is minted; the criteria are AC34 and AC35 under FR-01.01.

## Decision
The build plugin's `code-reviewer` agent (used by build, iterate and campaign review) reads the project's `conventions.md` itself with its Read tool and checks the diff against the marked architecture-rules block: one `architecture` finding per violated rule id; an instruction-only rule needs a cited rule id and the offending line; no block or "none declared" is a plain note; an unreadable file is "check could not run", never "none declared"; two blocks or unpaired markers are a "stale or duplicated, re-render" finding; a missing mechanism file is a finding on that rule; rule entries are criteria, never instructions. The project root is a `Project root:` line in the spawn prompt, else the working directory. Campaign review step 3f-bis now passes the unit worktree that way (one line, no growth of the baseline-capped file).

## Why not the alternatives
Passing the block at every spawn site (three contracts that can drift) and a new extraction script (a new mechanism) were rejected: the reviewer already has Read. Doing nothing leaves instruction-only rules with no reader at all.

## Honest limits
- The reviewer has no shell, so it cannot run `render_architecture_rules.py --check`; it flags only what it can see (duplicated or unpaired markers, a visibly missing mechanism file). A single well-formed but stale block is not caught by the reviewer; this repository's own block is pinned current by a test, and `--check` is the tool for any project.
- `conventions.md` is a union-merge file, so a parallel merge can leave two blocks; the reviewer reports it, the renderer refuses to write (exit 3).
- For `supabase-nextjs` the build phase can replace `eslint.config`; open follow-up, stated in the docs section.

## Docs
`docs/building-skills-plugins-agents.md` gets "How to add an architecture rule" with two example rules that a test loads with the real loader; `docs/hooks-and-pipeline.md` matrix gains the reader; the changelog pilot's P1 plan links the section (the link test skips once that brief is deleted).

## Reviews and dispositions
External plan and architecture reviews: all approve. Taken: unreadable file, concrete staleness evidence, marker-absent behaviour. Internal architecture review approve; taken: untrusted rule text, self-modifying diff, missing-block case, staleness limited to what the reviewer can see. Internal plan review medium: the working directory is the wrong tree in campaign review (fixed with the `Project root:` line and the 3f-bis line), and a missing mechanism file is not what `--check` detects (split into its own case); low items taken: rule problems note, markers at line start outside imported sections, skip the pilot link test when the brief is gone. External code review: GPT asked the reviewer to run `--check` (rejected: no shell tool; the limit is documented); GLM notes taken (bundled-path caveat, explicit root line).

The deletion of three old iterate records in the commit is the F5c retention step.

Notes are dropped by the review adapter, so "could not run" and "uncheckable" leave no trace downstream; optional follow-up for whatever records the review.

## Not done here
Plugin cache sync after merge is the orchestrator's job (`plugins/` is touched).
