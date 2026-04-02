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
- Generates forward migration in `supabase/migrations/`
- Generates rollback migration in `supabase/migrations/_rollback/`
- Detects destructive changes and warns
- Does NOT execute migrations

**Deploy (shipwright-deploy):**
- DEV: `supabase db push --linked` (automatic)
- PROD: `supabase db push --linked --dry-run` → user review → manual confirm

### 5. Post-Migration Manual Steps

Some Supabase features require Dashboard activation after the migration SQL runs:

| Feature | Migration creates... | Dashboard action required |
|---------|---------------------|--------------------------|
| Auth Hooks | Function + grants | Authentication → Hooks → Enable and select function |
| Database Webhooks | Edge Function | Database → Webhooks → Configure |
| Realtime | Publication | Database → Replication → Enable table |

The deploy skill will remind the user of any required manual steps after migration push.
