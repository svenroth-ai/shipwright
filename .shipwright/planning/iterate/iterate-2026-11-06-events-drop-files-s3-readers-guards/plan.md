Goal: Migrate every event-log reader, alias and path classifier to the assembling reader and the three event folders, with a reference guard
Reason: Readers and classifiers must see per-run drop files before any writer switches (issue 978)
Reference: .shipwright/planning/campaigns/2026-11-04-events-drop-files-BRIEF.md unit S3
