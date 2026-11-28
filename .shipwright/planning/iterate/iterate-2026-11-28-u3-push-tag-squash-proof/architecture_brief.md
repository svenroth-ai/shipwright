# Architecture Brief: finish a release after its request was squash- or rebase-merged

## The problem
On a repository that only allows squash merges, a release made through the changelog plugin stops after the merge: the
commit the release was checked on never reaches the main branch, so the step that publishes the version tag refuses. The
last release was finished by hand, and a change another person merged in the meantime shipped inside it without its
release-note entry.

## What already exists here
- A release record (written at tagging time) that can already carry an optional "merge commit + proof" claim; the guard
  that protects tag pushes and the closing check both accept the tag on that merge commit when the proof holds. Nothing
  writes the claim yet.
- A tag-push decision step that answers "which push line to run, or why not"; it waits while the request is open.
- A local test double of the code host's command-line tool that can only merge with a merge commit.

## What would newly, permanently exist
The tag-push decision step writes the merge-commit claim after proving it, moves the local tag onto the merge commit
(never a tag already published), or stops and names the foreign changes. The proof rule gets stricter about where the merge
commit sits. The test double learns squash and rebase merges and reports the merge commit.

## Options on the table
- **A:** After a squash/rebase merge, prove the merge commit (request head is the release, merge commit on the fetched
  branch, identical content on top of a base the release already held), record it, retag locally, else stop and report.
- **B:** Accept the merge commit when its changelog section and version numbers match the release.
- **C:** Fold the pending entries of foreign changes into the release automatically, then tag.
- **D:** Keep refusing squash merges; require repositories to allow merge commits for releases.
- **E:** Do nothing; finish such releases by hand.

## Constraints that are not negotiable
- Operator decisions 2026-11-27/28: a release finishes with any merge method, with no hand work and no lifting of the
  guard; code never ships without its changelog entry; when foreign changes are in the merge, stop and report.
- A tag already on the remote is never moved.
- Frozen golden traces must not move; frozen prose changes only with an approved delta.
