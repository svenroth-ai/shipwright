# Architecture brief: release steps as CLI

Change: the release skill's Steps 5.3-7 are shell chains the model types; they carry stop rules (commit before HEAD, tag only on exit 0, push rules by branch kind) and a close block that writes derived files.
Options: (a) leave the chains in the skill prose; (b) move each chain into a release.py subcommand that runs the same tools and returns their own exit codes, keeping outward commands literal; (c) one release.py "run everything" command.
New permanent surface under (b): four subcommands, a run-state file in the git directory, one runtime file release_state.json, two small subprocess scripts.
