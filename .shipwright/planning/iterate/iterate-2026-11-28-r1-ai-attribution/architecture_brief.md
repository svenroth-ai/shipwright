# Architecture Brief
Problem: compliance report counts AI-assisted commits by git author name only; repos whose commits are authored by a human with a Claude co-author trailer report 0.
Options: (A) read co-author trailers from git log in the existing collector and add a field on the commit record; (B) count AI commits from the Shipwright event log instead of git; (C) do nothing / document the limitation.
Permanent additions in A: one defaulted dataclass field and one property; no new files or dependencies.
