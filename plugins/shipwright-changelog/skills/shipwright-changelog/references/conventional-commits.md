# Conventional Commits Parsing

## Format

```
<type>[(<scope>)][!]: <description>

[body]

[footer(s)]
```

## Parsing Rules

1. First line is the header: `type(scope): description`
2. `!` after scope or type indicates BREAKING CHANGE
3. Footer `BREAKING CHANGE: <text>` also marks breaking
4. Scope is optional, in parentheses
5. Type is lowercase

## Recognized Types

| Type | Meaning |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring |
| `docs` | Documentation |
| `test` | Test changes |
| `chore` | Maintenance, deps, config |
| `style` | Formatting only |
| `perf` | Performance improvement |
| `ci` | CI/CD changes |
| `build` | Build system changes |

## Non-Conventional Commits

Commits that don't match the format are categorized as "Other".
They are included in the changelog but may need manual categorization.

## Examples

```
feat(auth): implement magic link login
fix(api): handle null response from Supabase
refactor(dashboard): extract chart component
chore(deps): upgrade Next.js to 16.2
feat!: redesign user onboarding flow
```
