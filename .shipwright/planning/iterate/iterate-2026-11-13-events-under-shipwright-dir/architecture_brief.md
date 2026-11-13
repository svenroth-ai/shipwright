# Architecture brief: event folders under `.shipwright/events/`

**Decision to judge:** move the three event folders of the drops layout from the repo root into `.shipwright/events/{drops,archive,quarantine}`, with a HARD ABORT (no compatibility reader) for a repo that still has the old root folders.

**Why now:** the drops layout is new (released v0.35.0, ~2 weeks ago). One known external adopter (a person on issue 978) uses it; this repo uses it; three local sibling repos (leadwright, shipwright-webui, aiportal) still run the legacy single file and have no folder. The root is being cleaned so everything Shipwright produces lives under `.shipwright/`.

**Alternatives considered**
1. Leave at the root (status quo): clutter stays; later move costs more users.
2. Flat `.shipwright/events.d/` (+ `.archive`, `.quarantine`): less change, three loose siblings.
3. Bundled `.shipwright/events/{drops,archive,quarantine}` (chosen).
4. Move with a transition period (reader reads old and new, warns): safer for stragglers, more code, a window where two locations are live.

**Costs / risks to weigh**
- `/.shipwright/*` is ignored by the managed `.gitignore` block; the new folder needs a whitelist line in the canonical block and in the self-heal, or events are silently dropped from commits.
- The integrity check (PR may only ADD event files) assumed the folder is the first path segment.
- One cross-repo consumer hardcodes the old names: the WebUI (server/src/core/event-log-assemble.ts). It stops showing a drops repo's events until it follows.
- ~70 open worktrees/branches of this repo: a branch that merges main afterwards and still has old-location files hits the hard abort and must run the migration tool once.
- The one-off move PR itself must pass the integrity check (accepted as a recognised move: deleted old file whose identical blob is added under the matching new folder).

**Out of scope:** root config files (`shipwright_*_config.json`), the legacy single file `shipwright_events.jsonl` and its lock.
