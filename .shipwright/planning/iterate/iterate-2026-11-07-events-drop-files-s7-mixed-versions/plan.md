Goal: Mixed-version safety for the per-run event drop layout: layout sentinel, release-evidence refusal, merge-base consumer CI check, explicit events_layout in init and adopt, conditional gitignore re-include
Reason: Teammates run different plugin generations; an unknown layout must fail closed and a PR must not keep writing the legacy log after the flip (issue 978)
Reference: .shipwright/planning/campaigns/2026-11-04-events-drop-files-BRIEF.md unit S7
