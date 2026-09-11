# Architecture Brief: triage-cross-tree-precedence

## The problem
`triage.read_all_items`'s cross-tree fold-in lets a stale sibling worktree's
`status` event outrank a status this tree already decided on its own, purely
because the sibling's event carries a later timestamp — resurrecting an
already-dismissed triage card as open, with no way to make the resurrection
stop recurring short of removing the abandoned worktree from disk.

## What would newly, permanently exist
Nothing. This changes an ordering rule inside existing resolution machinery
(`triage.read_all_items` pass 2): a foreign `status` event is applied only
when this tree's own tracked+outbox union has no `status` event for that id.
No new file, process, schedule, credential, or service is introduced.
