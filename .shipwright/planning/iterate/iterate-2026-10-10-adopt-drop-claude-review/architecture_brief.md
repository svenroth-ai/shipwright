# Architecture Brief: adopt-drop-claude-review

## The problem
`/shipwright-adopt` writes two always-active GitHub workflows into every adopted repo that run an AI review on each pull request using an `ANTHROPIC_API_KEY` secret. Repos without that secret get a red or pending review check on every PR (and the automerge guide tells them to require it, so merges hang). The independent review (spec / code / doubt reviewers) already happens inside each iterate.

## What would newly, permanently exist
Nothing. This removes machinery that already exists: the adopt scaffold step, its two templates and constants, and the corresponding Required-Check entry in the generated automerge guide.
