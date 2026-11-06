# Architecture Brief: housekeeping and integrity for per-run event drop files

## The problem
Per-run drop files make parallel PRs conflict-free only while committed files are never edited or deleted by a PR. The folder also grows by one file per run forever, and a corrupt file that reached main blocks the absence gates of its run.

## What already exists here
- The dormant drops layout (writers rotate on commit, so a committed drop is never edited) and the assembling reader with per-file status.
- No tool moves or removes committed drops, and nothing checks that a PR only adds.

## What would newly, permanently exist
A fold tool (archive per fold set, emergency and full rollbacks, quarantine), a CI/F11 integrity checker with two recognised exceptions (fold, quarantine), and a tracked `.keep` in the drops folder.

## Options on the table
- **A:** fold tool + checker as described, exceptions recognised by content (events present in an added archive file; byte-identical quarantine twin).
- **B:** never fold; let the folder grow and rely on the reader's speed.
- **C:** fold by rewriting files in place (fewer files, but a PR that races it conflicts).

## Constraints that are not negotiable
A fold racing an open PR must merge clean; the integrity check must block modify/delete of any file existing at the merge-base, path traversal and a forged run id; legacy-layout bytes stay unchanged.
