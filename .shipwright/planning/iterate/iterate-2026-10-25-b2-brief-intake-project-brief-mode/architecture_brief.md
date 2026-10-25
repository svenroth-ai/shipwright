# Architecture Brief: brief intake from a package directory, and Project brief mode

## The problem
/shipwright-run can be handed a committed "Brief package" directory (layout and hash already have a shared library). Today `--brief` accepts only a file; a directory silently becomes a plain description, the profile is derived from guesses, the brief's location is not stored so a resumed run cannot find it, and nothing re-checks that the package is unchanged since a person approved it. The Project phase then still interviews the human, and its grill gate checks only the shape of its records, so a package could be "confirmed" with evidence that points at empty text.

## What already exists here
- shared/scripts/lib/brief_intake.py (296 lines, at its size limit) reads one brief file or payload; adopt loads it by file path and has its own tests.
- shared/scripts/lib/brief_package.py: layout rules and a manifest hash; nobody yet consumes it.
- The grill-trace writer, the glossary writer and the completeness gate for Project, all shape-only.
- A driven run never calls `update-step`, so the Project completeness checks do not run there.

## What would newly, permanently exist
A sibling module for the directory route (verify, approval rules, store the location and the approved hash in run_config, re-verify on resume), a small tool that turns the package into the Project artifacts and checks their content, wiring in the project config writer, and prose in the run and project skills.

## Options on the table
- **A:** New sibling modules that import from brief_intake; brief_intake gets only a routing hook (net zero lines). Hash held in run_config.
- **B:** Split brief_intake into core + file route + directory route first, then add the directory route.
- **C:** Do nothing; keep reading the package only inside the later unattended-mode work.

## Constraints that are not negotiable
Adopt shares brief_intake and must behave exactly as before; the file route is unchanged; hash and approval are verified before write-config and on every resume; fixture approvals only with an operator switch; brief_intake.py stays at or below 300 lines (the operator dropped the extraction unit).
