# Architecture Brief: skill prose uses the stack-profile resolver (campaign unit S4)

## The problem

Skill instructions tell Claude to open a stack profile at a fixed path inside the installed Shipwright tree. A profile the user wrote in their project or home directory is never looked at by those instructions, and a mistyped name is treated as a missing file. The Python programs were already moved to the resolver.

## What already exists here

- A command-line resolver that prints the winning profile path (or nothing for the built-in "generic"), lists profiles, and exits 2/3 with a message on problems.
- Test runners that accept a profile name and project root and resolve it themselves.
- Prose that still builds the installed path by hand in about twenty places.

## What would newly, permanently exist

A test that scans markdown and hook config for hand-built profile paths (with a small allowlist), and a test that runs every resolver command found in the edited prose.

## Options on the table

- **A:** Rewrite the prose sites to call the resolver or pass the profile name, and add the scanning tests.
- **B:** Leave the prose; rely on the loaders mapping an installed path back to a name.
- **C:** Do nothing.

## Constraints that are not negotiable

Files already over the size limit must not grow. Documentation under docs/ is left for a later unit.
