# Architecture brief - R0a survey

Change: a read-only survey of every root `shipwright_*` file (readers, writers, locks, old-reader behaviour, CI and WebUI surfaces), appended as section 11 to the campaign BRIEF plus one machine-derived inventory file. No code, schema or runtime behaviour changes.

Options:
1. Do nothing: let each later unit (R0b resolver, R1 dual-read, R3 flip) discover its own call sites as it goes.
2. Append the survey to the BRIEF and add a separate inventory file (this change).
3. Generate the inventory as a checked-in script plus a CI guard instead of a one-off document.

Nothing permanent is added to the runtime; the two files are planning records.
