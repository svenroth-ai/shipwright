# Architecture Brief
Problem: (a) commits that say "Closes trg-X" leave the card open when nobody records a status; (b) triage_cli accepts --project-root only before the subcommand; (c) an append record without a usable status is treated as undecodable corruption instead of a malformed item.
Options: (1) do nothing, rely on operators; (2) a report-only detective audit check reading git log + the resolved triage store; (3) a commit-msg hook that appends the status automatically; (4) for (c): treat as corruption (today), or read as 'triage' with a warning, or add a validator class.
Nothing permanent is added to the data model; one new audit check and one small lib helper.
