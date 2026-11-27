Goal: Route every root / _sp.rel(key) join through _sp.path(key, root) and forbid new ones
Reason: R1c puts the new-then-old lookup inside path(); a join that bypasses path() would keep reading only the old location
Reference: campaign root-files-into-config, R1b (BRIEF sections 5 and 12 item 1)
