# Architecture Brief: guard test for stack-profile callers

## The problem
Skill code and Python modules should reach stack profiles only through the shared resolver and should never swallow its errors. Nothing mechanical stops a later change from hand-building a profile path or catching the resolver's ValueError and carrying on with defaults, which would silently run another stack's commands.

## What already exists here
- A markdown guard test (index based) that flags hand-built bundled profile paths in prose.
- The resolver, its consumer glue and a CLI, all with exit codes.

## What would newly, permanently exist
One more test module (AST based, about 200 lines) that scans every tracked non-test python module under plugins/ and shared/scripts/ on each CI run, with two small allowlists that are checked for staleness. The maintainers of the resolver keep its patterns (the resolver call names) current.

## Options on the table
- **A:** An AST guard test over all python modules, keyed on the try/except pattern around resolver calls.
- **B:** Extend the existing regex-based markdown guard to python files with a text pattern only.
- **C:** Do nothing; rely on code review.

## Constraints that are not negotiable
Exception classes are not nameable across the plugins' import paths, so any rule cannot depend on class identity.
