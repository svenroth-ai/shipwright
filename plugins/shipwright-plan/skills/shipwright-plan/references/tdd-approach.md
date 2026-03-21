# TDD Approach in Planning

## Philosophy

Plans should describe tests before implementation. Each section in the plan
should specify what tests to write and what they should verify.

## Test Layers

1. **Unit tests** — Pure functions, utilities, data transformations
2. **Integration tests** — API routes, database operations, auth flows
3. **Component tests** — React components with mocked deps (Vitest + Testing Library)
4. **E2E tests** — Full user flows via Playwright (if enabled, see Step 8)

## In the Plan

For each section, specify:
- What to test first (before writing implementation)
- Expected test file locations
- Key assertions
- Edge cases to cover

## Example Section Test Strategy

```
Tests for Auth Section:
  - Unit: validateEmail(), hashPassword() utilities
  - Integration: POST /api/auth/login returns 200 with valid creds, 401 with invalid
  - Component: LoginForm renders, submits, shows errors
  - E2E: Full login flow (enter email → submit → redirect to dashboard)
```
