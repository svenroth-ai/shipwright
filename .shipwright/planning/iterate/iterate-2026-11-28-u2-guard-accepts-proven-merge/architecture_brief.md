# Architecture Brief: let the release guard and the closing check accept a release that was squash-merged

## The problem
A release made through the changelog plugin cannot be finished on a repository that only allows squash merges: after the
squash, the commit the release was checked on never reaches the main branch, so the guard that protects the tag push and the
closing check both refuse the merge commit that did. The last release had to be finished by hand with the guard switched off.
The closing summary also kept saying "the tag will be pushed after the merge" even once it was pushed.

## What already exists here
- A release record file written at tagging time naming the checked release commit.
- A guard hook that blocks tag pushes / merges / release creation while a release is in progress unless the commit is the recorded one (or that commit plus an event-only commit).
- A shared stdlib rule file ("event-only descendant") used by both the guard and the tag-push decision.
- A read-only closing check (8 checks) and a closing summary printed by code.

## What would newly, permanently exist
Three optional fields in the existing release record (the merge commit, the merge method, and a small proof: PR head, tree id,
base before the merge), and one small stdlib rule file that both the guard and the closing check call: a commit passes if it is
the release as today, or if it is the recorded merge commit and its content (tree) is still identical to the release's PR head.
Kept correct by the changelog plugin's tests; a later unit writes the fields.

## Options on the table
- **A:** Extend the record with the merge commit and a content proof; one shared rule judges it (guard and closing check).
- **B:** Let the guard and closing check ask the hosting service (`gh`) which commit the PR was merged as, each time.
- **C:** Keep refusing squash merges in the plugin and document that releases need a merge-commit repository setting.
- **D:** Do nothing; finish squash-merged releases by hand with the guard lifted.

## Constraints that are not negotiable
- The operator decided (2026-11-27) a release must finish with any merge method, without hand work and without lifting the guard.
- The guard hook must not ask the remote on every command (a hung git helper on Windows, finding D90).
- A record without the new fields must behave exactly as before; frozen golden traces must not move.
