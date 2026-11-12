# Mini-plan U2 triage consistency
1. G4 audit check (new module group_g4.py, registered into group G composite): verb-adjacent closing-token grammar, range since latest release tag else last 500 commits, one git log call, report-only, MEDIUM, Revert ignored, unknown id = info.
2. triage_cli: --project-root accepted before and after the subcommand via default=SUPPRESS on subparsers.
3. read_all_items pass 1: append with missing/null/unknown status -> 'triage' + stderr integrity warning, via new lib helper triage_status_normalize.initial_record (triage.py net-zero). is_triage_record no longer requires `status` on appends so a status-less append is not corruption.
Tests in three new files. Docs: hooks-and-pipeline.md G4 paragraph.
Measured on this repo: 20 tokens in last 1500 commits, all dismissed -> 0 findings.
