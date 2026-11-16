# Architecture rules reach agents through one render tool (campaign profile-architecture-rules, U2)

Run: `iterate-2026-11-16-u2-rules-reach-agents`. Spec: `.shipwright/planning/iterate/campaigns/profile-architecture-rules/sub-iterates/U2-rules-reach-agents.md`.

## Decision

New `shared/scripts/tools/render_architecture_rules.py` writes the rules of the resolved profile into ONE marked block of `conventions.md` (begin/end HTML-comment markers). First placement: the unfilled `{ARCHITECTURE_RULES}` placeholder, else under an existing `## Architecture Rules` heading, else appended with that heading. Later runs replace the block only and are byte-identical on unchanged input; CRLF files stay CRLF. Instruction-only rules (judgement, or class undeclared in the legacy format) are labelled; a profile with no rules gets an explicit "none declared" line; invalid rules are left out and the block says how many problems exist (never "none declared"). Damaged markers (not exactly zero or one ordered pair) exit 3 without writing. Rule text is flattened to one line and comment delimiters are neutralised so it cannot close the markers.

Call sites: `/shipwright-project` step 7 (`project-scaffolding.md`: leave the placeholder, run the tool with `--profile`) and adopt (`adopt_profile.write_rules_block`, called once from `generate_adoption_artifacts.py` after `write_agent_docs`; `artifact_writer.py` sits at its bloat ceiling, so it is not touched). Run once for this repo: python-plugin-monorepo declares no rules, so the block says "none declared" until U5.

## Architecture Review

Brief carried the campaign context (U1 merged, U3a concurrent, U3b/U4/U5/U6 consume the tool). Verdicts verbatim from `architecture-review-raw.json`: `{"glm": "approve", "openai": "approve"}`. Both: option A (shared render tool) is the smallest thing that reaches agents in adopted projects; B duplicates hand-written prose, D leaves the working agent blind. The internal arms are `not_applicable` (effective complexity small by the diff-driven re-check).

## External-Plan-Review-Findings (glm approve, openai revise)

| Finding | Disposition |
|---|---|
| Placeholder must be consumed on first fill (glm medium) | accepted-and-fixed: the placeholder is replaced by the block; tests assert it is gone and a second run is a no-op |
| Sanitisation undefined (glm medium) | accepted-and-fixed: documented in the module, tested; no extra warning (rejected-with-reason: the replaced `<!-` form is visible in the output) |
| Damaged markers need a definition (glm low, openai low) | accepted-and-fixed: exactly zero or one ordered pair, else exit 3, no write; tests for lone begin and two blocks |
| Invalid rules must not read as success / none declared (openai medium) | accepted-and-fixed: the block states the problem count; rejected-with-reason: a non-zero exit, because rule errors are phase-local by campaign design (BRIEF 2.6) |
| Fenced-code marker text (glm low) | rejected-with-reason: rule text is flattened to one line and comment delimiters neutralised, so a marker cannot appear inside a block |
| Adopt loads the tool by path (glm low) | rejected-with-reason: `tools` is a package name adopt owns; the CLI stays the tested surface, the library functions are shared |
| One-time repo run not gated (glm low) | rejected-with-reason: the committed conventions.md carries the block; U5 re-renders |

## External-Code-Review-Findings (openai approve, glm revise)

| Finding | Disposition |
|---|---|
| adopt `write_rules_block` let OSError / damaged markers abort adoption (glm medium) | accepted-and-fixed: returned as a note, adoption continues; test added |
| no adopt test for missing or damaged conventions.md (glm medium) | accepted-and-fixed |
| heading at end of file without newline (glm low) | accepted-and-fixed: the block ends with a newline; test added |
| no end-to-end test of the project step 7 prose (glm low) | rejected-with-reason: step 7 is agent prose; the tool it calls is tested against the real template |
| double space before `--project-root` in the fenced command (glm low) | rejected-with-reason: it is the conventional continuation indent |

## Internal cascade findings (code-reviewer PASS, doubt-reviewer, model=opus)

| Finding | Disposition |
|---|---|
| CRLF file with the heading got a stray CR and a bare LF (code medium, doubt medium) | accepted-and-fixed: heading match stops before the CR; CRLF heading test added |
| Block placed above old hand-written bullets, or inside adopt's verbatim "Imported from" section (doubt medium) | accepted-and-fixed for the imported section (never a target); old bullets: documented in docs/stack-profiles.md, rejected-with-reason for auto-removal (the tool never deletes user text) |
| Missing shared render tool crashed adopt halfway (doubt low-medium) | accepted-and-fixed: a note, adoption continues |
| Notes only in result JSON; loader warnings dropped (doubt/code low) | accepted-and-fixed: notes and warnings also go to stderr |
| Quoted marker strings mid-line could be taken as a block (doubt low) | accepted-and-fixed: markers count only at line start; test added |
| sys.modules cleanup pops a name it did not insert (doubt low) | accepted-and-fixed: previous entry restored |
| Fenced-code placeholder or heading (doubt low) | rejected-with-reason: edge only; a block there is still replaced in place on every run |
| "instruction only (prompt-only (mechanisable))" wording (code low) | accepted-and-fixed: "instruction only (mechanisable)" |

## Orchestrator review round (follow-up commit)

Reading of BRIEF design 2.5: "nothing is committed as a render in the Shipwright repo" means no pre-rendered output is shipped for OTHER projects (the render always comes from the resolved profile); this repo's own conventions.md carries the block because BRIEF U2 ("run once for this repo") and U5's done-when ("this repo's conventions.md carries the rendered block") ask for it.

| Finding | Disposition |
|---|---|
| AC16/AC17 also added by U3a (high) | accepted: U2 merges first and keeps AC16/AC17; U3a renumbers; test files tag both |
| block at EOF after `## Convention Updates` would strand appended bullets (medium) | accepted-and-fixed: a new section is placed before the first `## ...Updates` / `## Learnings`; this repo's file re-rendered; test added |
| template anchor (medium) | accepted-and-fixed: test asserts the template heading directly precedes the placeholder and the block follows the heading |
| union merge can duplicate block bodies (medium) | accepted: documented in docs/stack-profiles.md; the tool refuses two blocks (exit 3); no new verifier |
| marker scan and placeholder match too wide (medium) | accepted-and-fixed: scan only before `## Imported from`; placeholder only alone on its line; case-insensitive heading; tests |
| adopt: other exceptions during load (medium) | accepted-and-fixed: any exception becomes a "block NOT written" note; adopt SKILL banner prints `architecture_rules_notes` |
| stale module docstring; F2 bullet edited directly | accepted-and-fixed (docstring names render_into / load_rules / DamagedMarkers; bullet is a write_doc_bullet drop) |
| test pinned supabase-nextjs's legacy format (U3a doubt) | accepted-and-fixed: dropped; the synthetic project-local legacy profile test remains |

Complexity: BRIEF rates U2 medium and it touches protected paths, while the diff-driven re-check classified it small. The internal plan and architecture arms were first closed not_applicable; they were then run (model=opus) and recorded completed.

## Internal arms (model=opus, run in the follow-up round)

architecture-internal-reviewer: approve (option A is the smallest that reaches adopted repos; B cannot guarantee idempotency, C spreads across agent prompts, D leaves adopted repos blind). opus-plan-reviewer: approve; findings dispositions: union-merge interaction accepted-and-documented (tool refuses two blocks, exit 3); who-writes-what row in docs/hooks-and-pipeline.md accepted-and-fixed; interpolated fields through `_one_line` and CLI catch-all exit codes accepted-and-fixed; heading with old prose above documented; staleness check (`--check` from a cheap place), validate_adoption warning for a missing block and the `---` divider layout in adopt output are deferred follow-ups for U5/U6 (rejected for U2: no new verifiers, per the orchestrator decision).

## Consequences

Rules reach agents in new and adopted projects. The block is a snapshot: a changed profile reaches `conventions.md` only on a rerun. No new requirement is minted; criteria are FR-01.01 AC16 and AC17.
