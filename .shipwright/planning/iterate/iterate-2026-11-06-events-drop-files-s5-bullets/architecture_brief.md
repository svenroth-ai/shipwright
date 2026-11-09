# Architecture Brief: bullets as drop files

## The problem
Two iterate PRs that each add one line to the same section of `conventions.md` or `architecture.md` show CONFLICTING on GitHub (6 of 7 merges measured in the reporter's repo), which stalls auto-merge.

## What already exists here
- Per-run ADR drops (`decision-drops/<run_id>_NNN.json`) folded at release by `aggregate_decisions`.
- `agent_doc_budget` / `agent_doc_shape` / `architecture_doc` checks that read the two curated docs.
- Context load reads the 20 most recent pending ADR drops.

## What would newly, permanently exist
A second kind of drop file (one bullet line per run, in a `bullets/` subfolder) with a writer, a release-time fold into the curated docs, and the readers that merge pending bullets with the folded text. The release step and the readers keep it correct.

## Options on the table
- **A:** one `.md` file per run in a subfolder of the existing decision-drops store, folded at release.
- **B:** keep editing the shared sections and rely on `merge=union` / a rebase bot.
- **C:** stop curating the two docs; derive them from the ADR drops alone.

## Constraints that are not negotiable
Old plugins and old WebUI versions must never show a bullet as an ADR; the event-log bytes under the legacy layout stay unchanged.
