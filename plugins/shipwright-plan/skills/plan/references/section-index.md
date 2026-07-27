# Section Index (SECTION_MANIFEST)

## Format

plan.md MUST contain a SECTION_MANIFEST block:

```markdown
<!-- SECTION_MANIFEST
01-auth
02-database
03-api: 01-auth, 02-database
04-frontend: 03-api
05-deployment
END_MANIFEST -->
```

## Rules

- Must be in plan.md (not a separate file)
- One section per line, format: `NN-kebab-case`
- Numbers must be two digits with leading zero
- Numbers represent execution order
- Names should be descriptive of the section's purpose
- A line beginning `#` is a comment and is ignored

## Declaring dependencies

A section that needs something another section produces names it after a
colon:

```
03-api: 01-auth, 02-database
```

A bare `NN-slug` line means "no declared dependencies" and is always valid —
every manifest written before this format keeps working.

**Why the declaration exists.** The numbering is documented as the build
order, but until a section could say what it presupposes, nothing could
establish that the order was right: a section could be scheduled before the
one that produces what it needs and no check would notice. Declaring the
dependency is what turns an unverifiable promise into a checkable one.

Rules, all enforced by `check-sections.py`, `check-plan-gates.py` and the plan
phase verifier:

- **Only sections in this plan.** A dependency must be a section declared in
  the same manifest. Do not name components that already exist, packages, or
  anything outside this plan — those belong in the section's
  `## Prerequisites` prose, not here.
- **Complete canonical ids.** Write `01-auth`, not `auth` and not `01`.
- **A prerequisite comes first.** Every dependency must appear *earlier* in
  the manifest than the section naming it. A numbering that places a
  prerequisite after its user fails. (This also rules out cycles: no cycle can
  put every member before every other member.)
- No self-dependency, no duplicate section id, no duplicate or empty
  dependency token.

Diagnostics name the manifest line number.

## Section Files

Each section declared in the manifest gets a file in `sections/`:
```
{planning_dir}/sections/01-auth.md
{planning_dir}/sections/02-database.md
...
```

Each file must carry a `Requirements:` line naming the requirement ids it
serves, and must say what the section is for, list at least two implementation
steps, and state how it will be tested — see
[section-splitting.md](section-splitting.md) for the structure and
[step-9-completion.md](step-9-completion.md) for the gates.

## Parsing

`shared/scripts/lib/plan_manifest.py` is the single parser. Scripts use it to:
- Generate section writing tasks
- Track section completion
- Validate all sections were written
- Check the numbering against the declared dependencies
