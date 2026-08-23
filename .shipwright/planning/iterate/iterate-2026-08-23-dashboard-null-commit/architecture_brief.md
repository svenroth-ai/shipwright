# Architecture Brief: dashboard-null-commit

## The problem
`update_build_dashboard.py` crashes whenever a `work_completed` event's
`commit` field is explicit JSON `null` rather than missing; the crash is
swallowed and logged, so `build_dashboard.md` silently stops updating
forever once one such event exists in a repo's history.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: the commit-cell
formatting expression inside the existing dashboard renderer.
