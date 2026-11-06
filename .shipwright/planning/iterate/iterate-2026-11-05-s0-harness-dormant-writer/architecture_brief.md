# Architecture Brief: dormant per-run event files, harness and standing replay gate

## The problem
Two iterate PRs that run in parallel both append to the one tracked `shipwright_events.jsonl`. GitHub's mergeability check ignores the local-only `merge=union` attribute, so every such pair shows CONFLICTING and auto-merge stalls (7 of 7 merges in a two-day window of one consumer repo).

## What already exists here
- `lib/events_log.py` resolves the single log; `record_event.py` appends under an untracked `.lock`; `lib/config.read_events*` reads it.
- `merge=union` in `.gitattributes` (local only); `ensure_current` (F11) integrates main before arming.

## What would newly, permanently exist
A second, dormant event-log layout (one file per run in `shipwright_events.d/`) selected by a config key (default legacy) and a test-only env override; a bare-origin integration test; a standing CI step that replays all event-related tests under the drops layout against a committed, shrink-only list of known failures (about 100 entries). The campaign's later units migrate readers and writers; this unit keeps default behaviour byte-identical. Whoever owns each later unit keeps the known list shrinking.

## Options on the table
- **A:** Per-run drop files behind a layout switch, with a replay gate in CI.
- **B:** Keep one file; rebase or re-run `ensure_current` on every open PR when main moves.
- **C:** Stop tracking the log (store it outside git).
- **D:** Do nothing; resolve conflicts by hand.

## Constraints that are not negotiable
Legacy bytes written by existing plugins must not change; old readers keep working; the plain env var must never change behaviour without the test flag.
