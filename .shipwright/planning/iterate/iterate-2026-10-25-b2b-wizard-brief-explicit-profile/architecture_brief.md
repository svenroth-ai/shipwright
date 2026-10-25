# Architecture Brief: keep the stack profile a wizard brief names

## The problem
The WebUI Intent Wizard writes the chosen stack profile name into the brief it hands /shipwright-run, but the run intake derives the profile only from the persistence answer, so a named profile (including a project or user profile) is lost and the run falls back to a guess.

## What already exists here
- shared/scripts/lib/brief_intake.py (296 lines, at its size limit) maps four answers to a profile; adopt shares it.
- shared/scripts/profile_resolver.py: one resolver (project > user > bundled) used by every phase; write-config --profile already stores the profile in the run config, later phases read it from there.
- The WebUI writes the profile as an item of a single prose line, not as a JSON field.

## What would newly, permanently exist
A small sibling module that finds the named profile and asks the resolver; an optional `profile` field in the file brief; extra result keys only when a profile is named.

## Options on the table
- **A:** Sibling module + an optional field + reading the WebUI trailer; unusable name stays null with an error and exit 3.
- **B:** Do nothing in the repo; ask the WebUI to write JSON.
- **C:** Validate in write-config only.

## Constraints that are not negotiable
Adopt and brief-less runs behave exactly as before; additive fields only; the resolver decides which file a name means; an unusable name is never silently replaced; brief_intake.py gets no net growth.
