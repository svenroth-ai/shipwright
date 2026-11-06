# Architecture Brief: one assembling reader for the event log

## The problem
Event-log readers each open the one legacy file. Once events live in per-run files (and an archive), every reader must see one ordered log, and gates that look for an event's absence must not conclude "absent" when a file of their own run is damaged.

## What already exists here
- `lib/events_log.py` resolves the legacy file; `lib/config.read_events*` reads it; `lib/jsonl_records` recovers records per line; S0 has a first, status-less assembled read inside `events_layout.py`.
- Several renderers pick "the last event" by list position.

## What would newly, permanently exist
A reader module with per-file status and a duplicate rule, an absence-gate helper, and newest-by-timestamp helpers used by the position readers.

## Options on the table
- **A:** One new reader module over the existing record recovery; legacy first in file order, then archive and drops by instant and id; status per file.
- **B:** Merge all files into one sorted list, legacy included.
- **C:** Each reader opens the folders itself.
- **D:** Do nothing yet; migrate everything in the reader unit at once.

## Constraints that are not negotiable
A tree without the folders reads byte-for-byte as before; legacy is never deduplicated or reordered; only a damaged drop file of the run's own key blocks an absence gate.
