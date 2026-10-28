# Architecture brief: E1

Problem: the design phase's write-boundary gate reads the whole dirty working tree; output an earlier phase left uncommitted trips it.
Options:
- A. Do nothing: agent keeps asking the operator to commit earlier output first (every brief run).
- B. Make the gate session-aware: record the dirty set (path to content hash) when the design session starts; gate judges only paths new or changed since. One small plugin-local module plus one call in setup.
- C. Have the design agent commit the earlier phase's output itself before starting.
- D. Widen the allowed-prefix list to cover whatever the project phase writes.
