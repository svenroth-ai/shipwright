# Mini-plan: U1 events open-file warning, A7 wording, adopt seeder LF

1. New leaf `shared/scripts/lib/events_open_warning.py`: constant `OPEN_FILES_WARN_THRESHOLD = 150`, `count_open_drop_files`, `open_files_warning` (returns one WARN line or None; legacy layout silent; never raises).
2. `shared/scripts/tools/main_health.py` prints the line to stderr after the JSON; the exit-code mapping is untouched. B1b and F11 both run it, so an iterate sees it at start and before merge.
3. `adopt_compliance.py` A7 failure text names `shipwright_events.jsonl` or `shipwright_events.d/`.
4. `event_seeder.py` append opens with `newline="\n"`.
5. Tests: threshold boundary, legacy silent, exit code identical with/without warning, failing warning never breaks main_health, A7 text, seeder name vs shared `DROP_NAME`, seeder append LF under CRLF-translating platform (monkeypatched).
6. Docs: one paragraph in `docs/hooks-and-pipeline.md` B1b.

Alternative considered: put the warning in the JSON report too. Not done: stdout JSON is a parsed contract.
