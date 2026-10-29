# Project brief mode (a Brief package replaces the interview)

**Applies when** `shipwright_run_config.json` carries `brief_dir` (the run was started with
`--brief <package dir>`; `/shipwright-run` Step 4 recorded and verified it). Otherwise ignore
this file: the interview runs as always.

The package was approved by a person and its hash was verified; this mode satisfies the Project
gates **by content**, in code, and writes the same artifacts the interview would.

## Format of `<brief_dir>/brief.md`

Every `##` section is one **capability**, except `## Glossary`. The heading is the FR `Name`
verbatim; its lower-kebab slug is the `requirement_key` and the anchor `brief.md#<slug>`.
Text before the first `##` (the `#` title, an introduction) is free.

```markdown
## Capture note
Requirement: A user can add a note with a title and a body.
- Outcome: a saved note appears in the list
- Fit criterion: a note added with a title is listed within one second
- Purpose: ...        - Boundaries: ...        - Failure: ...
- Glossary: n/a: no new term      (optional when a ## Glossary term occurs in the section)
- Rationale: n/a: the simplest flow            - Out of scope: ...

## Glossary
- **Notes**: the user's saved short texts, each with a title and a body.
```

A dimension is `answered` text or `n/a: <reason>`. `assumed` is refused (this surface permits none),
and so is an empty section, an empty dimension, an outcome without a fit criterion, and a
duplicate or empty key.

## Procedure (replaces Steps 1 and 4's interview and confirmation)

```bash
uv run "{shared_root}/scripts/tools/brief_project_mode.py" apply --project-root "$(pwd)"
```

Package intake (`write_run_config.py --brief-dir`, `/shipwright-run --brief`) already ran this content check (`brief_project_mode.py check`) and refused a thin brief as `invalid_content`, so an issue here means the package changed after intake.

It verifies the package against the hash `run_config` holds (exit 3 = changed or unapproved:
stop), checks the content, and only then writes `shipwright_project_interview.md` (a pointer, not
a transcript: no interview was held), `requirements.md`, one grill-trace per capability
(`evidence: ["brief.md#<slug>"]`, `confirmed_by: "brief:<brief_dir>/brief.md"`) and the glossary
terms in `CONTEXT.md` (the `write_context_term.py` producer path). Exit 1 prints the issues:
fix the package (which needs a new approval), never the traces by hand.

Continue with Step 5 (directories) and Step 6 (spec generation). **FR `Name` cells are the brief
headings verbatim** (the interview's requirement_key slug rule is unchanged).

## Checks in Step 8 (in addition to the grill-trace gate)

`run_project_checks` (the dispatcher the apply-path phase gate and `update-step` run) adds two
results for a run that records `brief_dir`, from `verifiers/brief_mode_checks.py`:

- `brief_evidence_anchors`: every brief-confirmed trace's evidence anchor resolves to a non-empty
  `brief.md` section (the shape-only gate cannot see that);
- `brief_fr_names`: the Names in the `spec.md` FR tables equal the brief's capability Names
  (skipped until a spec.md exists).

Red means the phase is not complete. The same checks run early, with details, as
`brief_project_mode.py verify-traces` and `check-fr-names` (`--project-root "$(pwd)"`).
