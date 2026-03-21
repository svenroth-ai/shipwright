# Git Operations

## Feature Branch Workflow

Every build session works on a feature branch:

```bash
# Create branch (new session)
git checkout -b shipwright/{section_name}

# Resume branch (existing session)
git checkout shipwright/{section_name}
```

## Conventional Commits

All commits MUST follow Conventional Commits format:

```
<type>(<scope>): <short description>

<optional body — what and why, not how>

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Types
| Type | When |
|------|------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring, no behavior change |
| `test` | Adding or updating tests only |
| `docs` | Documentation only |
| `chore` | Build config, dependencies, tooling |
| `style` | Formatting, no logic change |

### Scope
Use the section name without number prefix:
- `01-auth` → scope is `auth`
- `03-dashboard` → scope is `dashboard`

### Examples
```
feat(auth): implement magic link authentication
fix(auth): handle expired token gracefully
test(auth): add E2E test for login flow
refactor(api): extract validation middleware
chore(deps): upgrade @supabase/supabase-js to 2.99
```

## Staging

```bash
# Stage all changes
git add -A

# Or stage specific files
git add src/auth/ tests/auth/
```

## Auto-push

If `auto_push` is true in config:
```bash
git push -u origin shipwright/{section_name}
```

Default: **disabled**. User or /shipwright-changelog handles pushing.
