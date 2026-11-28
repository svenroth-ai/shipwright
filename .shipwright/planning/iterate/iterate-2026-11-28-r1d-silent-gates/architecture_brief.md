# Architecture brief: R1d-1 (silent-failure gates read a moving file per commit)

**Problem.** The campaign moves about 30 root `shipwright_*` files into `.shipwright/config/` (R3). Readers on disk already find either place (R1c). Readers of a HISTORICAL commit (`git show <sha>:<path>`) still ask for the root name, through `rel_at(key, commit)`, which ignores the commit. After a move they see "absent" and treat it as benign: the bloat gate diffs against an empty base baseline, the AC-baseline growth check calls a move a "bootstrap" and misses growth, the events-layout CI reads no layout, the rollout snapshot reads no manifest. Separately the bloat anti-ratchet SKIPS (exit 0) when no baseline is found, and the pre-commit hook only runs it if the root file exists: delete or move the baseline and the gate passes green without checking anything.

**Proposed change.** `rel_at(key, commit, root)` answers per commit: the new path if it exists in that commit's tree (`git cat-file -e`), else the root path. "Migrated?" is decided by the new path existing, never by the root blob missing (after R3 the root holds a pointer stub). An unreadable commit reads as "root", so the caller's own read reports the real error. Every historical reader passes its repo. A small CLI prints the same answer for YAML and bash. The anti-ratchet gains `--require-baseline` (absent in both places = exit 1); this repo's hook and CI pass it. Consumer projects without a baseline keep today's skip.

**Alternatives.**
1. Try both paths in every reader (`git show new || git show old`). Rejected: duplicated at every reader, and with both blobs present (R3 stub) it needs the same "new first" rule anyway; one function is simpler and testable.
2. Make a missing baseline a hard failure for everyone. Rejected: consumer projects legitimately start without one; only a repo that has a baseline should require it.

**Constraints.** No behaviour change in an unmigrated repo (the new path never exists, so every answer is the root). Files at or under 300 lines. One extra `git cat-file` per historical read.
