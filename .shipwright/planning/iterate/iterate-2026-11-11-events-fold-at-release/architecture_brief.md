# Architecture Brief: events-fold-at-release

## The problem
A project that records events as many small per-run files must tidy the old ones into one archive now and then, or
every write gets slower as the open files pile up. Today a person has to remember to run the tidy-up, stage it and
commit it. The people using the product do not care about this; it is housekeeping that has to happen in the background.

## What would newly, permanently exist
One small command that does the tidy-up and commits it, called by the release procedure.

## Options
- A: the release procedure runs the tidy-up itself as one extra commit before the release commit, and never stops the release.
- B: a scheduled CI workflow opens a tidy-up pull request now and then (the product ships little CI and keeps it optional).
- C: every ordinary change checks the count and tidies when it is high.
- D: keep it manual and only warn when the count is high.
