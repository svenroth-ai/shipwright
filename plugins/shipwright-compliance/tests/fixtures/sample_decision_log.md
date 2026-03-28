# Decision Log

> Project-specific decisions only. Profile-level decisions are implicit in the stack profile.

---

## ADR-001 | 2026-03-20 | 01-login | Commit abc123

### Status: Accepted

### Context
No password management needed, better UX for initial MVP

### Decision
Use Supabase Auth with magic link

### Consequences
- Simpler onboarding flow
- Alternatives rejected: Password auth, OAuth-only

---

## ADR-002 | 2026-03-20 | 01-login | Commit abc123

### Status: Accepted

### Context
Need form validation with strong TypeScript support

### Decision
Choose Zod over Yup for validation

### Consequences
- Better TypeScript inference, smaller bundle size
- Alternatives rejected: Yup, io-ts

---

## ADR-003 | 2026-03-20 | 02-rbac | Commit def456

### Status: Accepted

### Context
Need to enforce access control at the data layer

### Decision
Implement RLS policies in Supabase

### Consequences
- Row-level security enforced at database level, not application code
- Alternatives rejected: Application-level middleware

---

## ADR-004 | 2026-03-20 | 02-rbac | Commit def456

### Status: Accepted

### Context
Need type safety for role assignments

### Decision
Use enum for roles instead of string

### Consequences
- Type safety prevents invalid role assignments
- Alternatives rejected: String constants

---

## ADR-005 | 2026-03-21 | 03-profile | Commit ghi789

### Status: Accepted

### Context
Need avatar storage integrated with auth

### Decision
Store avatars in Supabase Storage

### Consequences
- Integrated with auth, automatic CDN delivery
- Alternatives rejected: S3, Cloudinary
