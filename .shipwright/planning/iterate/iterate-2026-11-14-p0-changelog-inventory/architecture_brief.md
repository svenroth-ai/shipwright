# Architecture Brief: inventory data and checker for the changelog skill

## The problem
A later campaign moves mechanics out of the changelog skill's prose into a CLI. Before that starts, the operator needs a complete, checkable list of what the prose contains, who decides each question in each mode, and which external programs a release spawns.

## What would newly, permanently exist
- Three data files next to the skill (sections with class and target, a decision table, a spawn map) and a checker with tests, all retired when the conversion ends.
- Reports under the campaign planning folder.

## Options
1. Write the inventory as a report only (markdown), no checker.
2. Data files plus a checker that reds when the prose or the cited lines move (chosen by the brief).
3. Do nothing now; extract the CLI directly and discover the pins as tests break.
