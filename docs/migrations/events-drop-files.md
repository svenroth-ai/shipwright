# Migration — per-run event files (`events-drop-files`)

**Applies to:** every project that uses Shipwright plugins.
**Introduced by:** the `events-drop-files` campaign (issue 978).
**Do you have to do anything?** Not to upgrade. Update the plugins and carry on —
your project keeps working exactly as before. Switching to the new layout is a
separate, deliberate step that you take later, per project (see "Switching a
project over" below).

## What changed

Until now every finished piece of work appended one line to a single file,
`shipwright_events.jsonl`. Two branches that both finished work at the same time
both changed the end of that file, so merging the second one conflicted.

The new layout, called `drops`, gives each run its own small file in the folder
`shipwright_events.d/`. Two branches then add two different files and never
touch the same one, so there is nothing to conflict. Old, folded-away files live
in `shipwright_events.archive/`. A file that cannot be read and holds nothing
recoverable can be moved to `shipwright_events.quarantine/` with the fold
tool's `quarantine` mode; until someone does that, it is reported and the run
it belongs to does not pass.

Architecture and convention notes work the same way: each note is its own small
file under `.shipwright/agent_docs/decision-drops/bullets/` and is folded into
the curated document when a release is made.

The layout is chosen by one key, `events_layout`, in `shipwright_sync_config.json`:

| Value | Meaning |
|---|---|
| absent or `legacy` | the single `shipwright_events.jsonl` (the default; nothing changes) |
| `drops` | one file per run in `shipwright_events.d/` |

## What an existing project must do

### Right now, on upgrade: nothing, with two things to know

1. **The WebUI (Command Center) must be updated first.** Notes about
   architecture and conventions are written as separate files from this release
   on, even while the layout is `legacy`. An older WebUI does not show them
   until the next release folds them in. The minimum WebUI version is stated in
   the release notes; update the WebUI before or together with the plugins.
2. **Everyone on the team should update the plugins.** A plugin from before
   this release does not know the new layout. On a project that has been
   switched over it keeps appending to the single `shipwright_events.jsonl`,
   and nothing on that machine stops it. Only the optional CI check (below)
   flags such a change. A plugin from this release on refuses to write when it
   meets a layout it does not know, but that protects only the updated
   machines.

### Switching a project over (later, your decision)

Do this only when your team is ready, and only after the release notes say the
switch is supported. For a solo maintainer it is a few minutes:

1. Make sure you and everyone who works on the project use the updated plugins.
2. Finish or merge open work first, so no branch is in the middle of a run.
3. Set `"events_layout": "drops"` in `shipwright_sync_config.json` and commit it.

Two consequences to expect:

- A branch that was started before the switch and is rebased (not merged) over
  it must re-record its own events as drop files. Nothing is lost, but nothing
  in the plugin warns you either; only the optional CI check flags it. After
  such a rebase, look at the branch: if its run's event sits in
  `shipwright_events.jsonl` instead of a file in `shipwright_events.d/`,
  record it again.
- Going back is supported (see "Going back" below).

## Extra protection in CI — optional

Two check scripts exist that can run in your CI and block a pull request that
loses events or writes to the wrong layout (`check_events_layout_ci.py`,
`check_events_integrity.py`). **They are optional and are not part of any
shipped CI template.** Be clear about what you give up without them: they are
the only thing that flags a change written to the wrong layout (for example by
a plugin that was not updated, or a branch rebased across the switch). The
check at the end of every run (F11) looks only at the event folders, not at
that. So:

- Working alone, on one machine, with the plugins updated: skip them. There is
  nothing that could write to the wrong layout.
- Several people, or several machines, with mixed plugin versions: add them, or
  make sure everyone has updated before you switch.

If you add them, the checkout step needs `fetch-depth: 0` so the check can find
the point where your branch left the main branch.

A local alternative needs no CI: run the same scripts from a git pre-push hook.
Shipwright does not install one for you; it is simply a way to get the same
check without GitHub.

## Going back

Rollback is a supported path, not an emergency. The fold tool
(`fold_events.py`) has two modes, and they differ in who can read the result:

- `emergency` moves every readable drop file into `shipwright_events.archive/`
  and sets `events_layout` back to `legacy`. Updated plugins read the archive;
  a plugin from before this release does not.
- `full` appends the archive and the drops to the single
  `shipwright_events.jsonl` and sets `legacy`. Use this when older plugins must
  see the events too.

A drop file that cannot be read stays where it is in `emergency`; the tool
lists it. If a drop file is open in another program on Windows, the tool says
which file it could not remove; close the program and run the same command
again. No event is lost either way.
