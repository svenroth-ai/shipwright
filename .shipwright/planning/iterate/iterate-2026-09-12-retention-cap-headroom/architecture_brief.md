# Architecture Brief: retention-cap-headroom

## The problem
Under current iterate-branch concurrency, `.shipwright/agent_docs/iterates/`'s
retention prune (evicting the oldest unpinned entry beyond a 50-entry cap on
every finalize) sits close enough to its cap that different concurrent
branches can prune different other-run entry files as an incidental side
effect of their own finalize, sometimes landing on `origin/main` as part of
an unrelated PR.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: the numeric cap
(`ITERATE_RETENTION`) a pre-existing prune step reads, raised for headroom.
