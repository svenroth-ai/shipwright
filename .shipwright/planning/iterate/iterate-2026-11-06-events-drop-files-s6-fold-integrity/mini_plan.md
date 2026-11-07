# Mini-plan S6: fold, quarantine, emergency/full fold, integrity check (issue 978)

Goal: the housekeeping that makes drop files sustainable and keeps them append-only, while the layout stays dormant (default legacy).

1. `lib/events_fold_io.py`: file-name grammar (key `[A-Za-z0-9._-]{1,80}`, one segment, no traversal), record parsing with the shared `split_records` recovery, per-event hash, `git cat-file` blob reads (never `git show`: "Filename too long" on the Windows runner).
2. `lib/events_fold.py` + `tools/fold_events.py`: `fold` (merged + unmodified + every event older than 14 days -> ONE archive file named by the hash of the set; idempotent), `emergency` (all ok drops -> archive, `events_layout` -> legacy), `quarantine` (zero recoverable records AND non-ok at the base ref -> quarantine folder, byte-identical). Whole-log duplicate-id scan first: conflicting content stops the fold. Under the events lock.
3. `lib/events_fold_full.py`: full fold into the legacy log (rollback 2).
4. `lib/events_integrity.py` + `checks/check_events_integrity.py`: change vs merge-base may only ADD; fold exception = every deleted event hash in an added archive file; quarantine exception re-derived from the base blob + byte-identical twin; bad paths, symlinks, forged `run` stamps, foreign keys. No-op without folders.
5. Carry-in S2 F1: the reader lists drops before the archive and re-reads once when a file vanished (a fold racing a read); the vanished file stays `unreadable` (absence gates stay fail-closed).
6. Directory-rename guard: a fold that empties the drops folder reads as a directory rename to git and breaks an open PR; the fold keeps an empty tracked `.keep`.
7. Tests (fold, integrity, reader race, bare-origin race) incl. the real log shape; docs in hooks-and-pipeline.

Risks: bloat anti-ratchet (events_read kept at 300, events_log at 313); no workflow touched (wiring the checker into CI is the operator's call).
