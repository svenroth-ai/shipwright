# Migration Safety (Shipwright Enhancement)

## Purpose

Prevent accidental data loss from destructive SQL operations.
Build generates migration files; Deploy executes them.

## Rules

### 1. Always Generate down.sql

When creating a migration, also generate a rollback file in `supabase/migrations/_rollback/` (best-effort):

| Forward migration | Rollback migration |
|--------|----------|
| CREATE TABLE users (...) | DROP TABLE IF EXISTS users; |
| ALTER TABLE users ADD COLUMN email TEXT | ALTER TABLE users DROP COLUMN email; |
| CREATE INDEX idx_email ON users(email) | DROP INDEX IF EXISTS idx_email; |

For complex migrations (data transforms), add a comment:
```sql
-- Manual rollback required. See decision_log.md.
```

### 2. Destructive Change Detection

The PostToolUse hook (`check_destructive_migration.sh`) scans for:
- `DROP TABLE`
- `DROP COLUMN`
- `ALTER TYPE` (lossy type changes, e.g., TEXT → INTEGER)
- `TRUNCATE`
- `DELETE FROM` (without WHERE)

**When detected:** Hook exits with code 2 (soft block) and message:
```
⚠️ Destructive migration detected: DROP TABLE users
This will permanently delete data. Confirm before proceeding.
```

The agent MUST ask the user for explicit confirmation via AskUserQuestion
regardless of autonomy level.

### 3. Migration File Conventions

**CRITICAL:** The Supabase CLI (`supabase db push`) treats EVERY `.sql` file in
`supabase/migrations/` as a forward migration. Rollback files placed there will
cause duplicate key errors.

```
supabase/migrations/
  NNN_description.sql              # Forward migration (executed by supabase db push)

supabase/migrations/_rollback/
  NNN_description_down.sql         # Rollback migration (NOT executed, stored for manual use)
```

**Rules:**
- Forward migrations: flat files in `supabase/migrations/`, named `NNN_description.sql`
- Rollback migrations: matching files in `supabase/migrations/_rollback/`, named `NNN_description_down.sql`
- **NEVER** place `_down.sql` files directly in `supabase/migrations/` — the CLI will try to execute them
- Create the `_rollback/` directory if it doesn't exist (`mkdir -p supabase/migrations/_rollback`)

### 4. Build vs Deploy Responsibility

**Build (this plugin):**
- Generates forward migration in the profile's `migrations.dir`
- Generates rollback migration in `{migrations.dir}/_rollback/`
- Detects destructive changes and warns
- **Applies migration** after preflight verification via profile commands
- Falls back to manual SQL instructions if preflight or apply fails

**Deploy (shipwright-deploy):**
- PROD: Profile's `migrations.dry_run_cmd` → user review → `migrations.apply_cmd`
- DEV: Verify-only (`migrations.list_cmd`) — migrations already applied during Build/Iterate

**Migration apply is a serialized critical section.** In autonomous mode with parallel section-builders, only one agent at a time may create/apply migrations. See section-builder agent docs for serialization protocol.

### 5. Post-Migration Manual Steps

Some migrations require manual activation that cannot be automated.
These steps are defined in the stack profile under `migrations.post_apply_manual_steps`.

After applying migrations:
1. Check each `trigger_tag` against the migration content and implementation changes
2. If a trigger matches, inform the user via AskUserQuestion with the action and note
3. Note which test areas are blocked (`blocks_tests_for`) until the manual step is completed
4. Wait for user confirmation before running tests that depend on the manually activated feature

In autonomous subagent mode: log the manual step as a warning, skip tests matching `blocks_tests_for` keywords, and flag in result JSON.
