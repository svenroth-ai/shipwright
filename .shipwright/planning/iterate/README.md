# Iterate Plans (pre-adoption history)

This directory holds iterate plans written **before** the shipwright monorepo
adopted itself into its own SDLC on 2026-05-02. They were transparently
hidden by the broad `.shipwright/` gitignore rule until the self-adoption
restructured `.gitignore` to track canonical artifact homes.

The files are preserved as historical context for `/shipwright-compliance`
detective audits and for anyone tracing why a particular framework decision
was made. They follow no single template — each plan was written ad-hoc
during the framework's own development.

After self-adoption, new iterate plans live alongside this directory under
`.shipwright/planning/<split>/` (e.g. `01-adopted/`) or as ephemeral plans
under `~/.claude/plans/` per the standard `/shipwright-iterate` workflow.
