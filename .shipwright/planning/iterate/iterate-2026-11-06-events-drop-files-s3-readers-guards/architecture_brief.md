# Architecture Brief

Problem: the event log is moving from one append-only file to a folder of per-run files (dormant behind a layout switch). About 40 code paths read the single file by name, and about 15 path classifiers treat the file name specially.

Options:
1. Migrate every reader to one shared assembling reader and every classifier to a shared folder list, with a guard test that fails on any file naming the old log that is not registered.
2. Make a compatibility shim that materialises a virtual single-file view (concatenation) on demand so readers stay unchanged.
3. Do nothing now: leave the readers on the single file and flip layout later in one large change.

Constraint: legacy behaviour and bytes stay unchanged while the layout is off; the folders hold facts (absence of a record must fail closed when a file is unreadable).
