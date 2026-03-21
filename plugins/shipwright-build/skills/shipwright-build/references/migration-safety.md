# Migration Safety (Shipwright Enhancement)

## Purpose

Prevent accidental data loss from destructive SQL operations.
Build generates migration files; Deploy executes them.

## Rules

### 1. Always Generate down.sql

When creating a migration `up.sql`, also generate `down.sql` (best-effort):

| up.sql | down.sql |
|--------|----------|
| CREATE TABLE users (...) | DROP TABLE IF EXISTS users; |
| ALTER TABLE users ADD COLUMN email TEXT | ALTER TABLE users DROP COLUMN email; |
| CREATE INDEX idx_email ON users(email) | DROP INDEX IF EXISTS idx_email; |

For complex migrations (data transforms), add a comment:
```sql
-- down.sql: Manual rollback required. See decision_log.md.
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

```
supabase/migrations/
  YYYYMMDDHHMMSS_description/
    up.sql       # Forward migration
    down.sql     # Rollback migration (best-effort)
```

### 4. Build vs Deploy Responsibility

**Build (this plugin):**
- Generates up.sql and down.sql
- Detects destructive changes and warns
- Does NOT execute migrations

**Deploy (shipwright-deploy):**
- DEV: `supabase db push` (automatic)
- PROD: `supabase db push --dry-run` → user review → manual confirm
