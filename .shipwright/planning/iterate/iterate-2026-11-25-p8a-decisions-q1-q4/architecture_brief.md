# Architecture Brief: changelog release fixes (preview before write, push before PR, default branch)

## The problem
The release skill writes the changelog before asking the user to confirm it, opens a pull request before its branch
is on the remote, assumes the default branch is called `main`, and states the merge rule two different ways.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: the release CLI's prepare and record-event steps, the release
skill's prose order, and one line in the prompt-mechanics command registry.
