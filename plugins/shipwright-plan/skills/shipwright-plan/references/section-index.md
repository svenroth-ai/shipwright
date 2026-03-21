# Section Index (SECTION_MANIFEST)

## Format

plan.md MUST contain a SECTION_MANIFEST block:

```markdown
<!-- SECTION_MANIFEST
01-auth
02-database
03-api
04-frontend
05-deployment
END_MANIFEST -->
```

## Rules

- Must be in plan.md (not a separate file)
- One section per line, format: `NN-kebab-case`
- Numbers must be two digits with leading zero
- Numbers represent execution order
- Names should be descriptive of the section's purpose

## Section Files

Each section declared in the manifest gets a file in `sections/`:
```
{planning_dir}/sections/01-auth.md
{planning_dir}/sections/02-database.md
...
```

## Parsing

Scripts parse SECTION_MANIFEST to:
- Generate section writing tasks
- Track section completion
- Validate all sections were written
