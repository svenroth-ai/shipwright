# Architecture Brief: hooks-uv-run-project-pin

## The problem
Every plugin's `hooks.json` invokes hook scripts as plain `uv run "<script>"`.
`uv run` resolves its target project from the session's current working
directory, not from the script's own path — so when that CWD happens to be
an unrelated uv-managed Python project, every hook silently tries to
sync/reinstall that unrelated project instead of running standalone. On
Windows this can hard-fail with a file-lock error when that project has a
running process holding an entry-point executable open, breaking every hook
for the whole session.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: a `--no-project` flag
is added to each already-existing `uv run` invocation in each plugin's
already-existing `hooks.json` file.
