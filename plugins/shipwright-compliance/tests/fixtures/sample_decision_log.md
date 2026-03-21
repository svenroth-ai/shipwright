# Decision Log

Architectural and design decisions made during implementation.

## 01-login (2026-03-20 10:15 UTC)

- **Use Supabase Auth with magic link** [architecture]
  - Reason: No password management needed, better UX for initial MVP
- **Choose Zod over Yup for validation** [library]
  - Reason: Better TypeScript inference, smaller bundle size

## 02-rbac (2026-03-20 14:30 UTC)

- **Implement RLS policies in Supabase** [architecture]
  - Reason: Row-level security enforced at database level, not application code
- **Use enum for roles instead of string** [code-quality]
  - Reason: Type safety prevents invalid role assignments

## 03-profile (2026-03-21 09:00 UTC)

- **Store avatars in Supabase Storage** [architecture]
  - Reason: Integrated with auth, automatic CDN delivery
