# E2E Test Plan Generation (Shipwright Enhancement)

## Purpose

Generate a Playwright E2E test plan based on the implementation plan.
This plan is used by /shipwright-test to create actual Playwright tests.

## When Generated

Only when `e2e_test_plan.enabled` is true in config.json (default: true).

## Structure

Write `{planning_dir}/claude-plan-e2e.md` with:

```markdown
# E2E Test Plan

## Test Environment
- Base URL: http://localhost:3000
- Auth: Test user credentials
- Browser: Chromium (default)

## User Flows

### Flow 1: User Registration
- Navigate to /auth/signup
- Fill email, password, confirm password
- Submit form
- Expect: redirect to /dashboard
- Expect: welcome toast notification

### Flow 2: ...

## Page Object Model

### LoginPage
- URL: /auth/login
- Elements: emailInput, passwordInput, submitButton, errorMessage
- Actions: login(email, password), getError()

### DashboardPage
- URL: /dashboard
- Elements: ...
```

## Downstream Usage

The E2E test plans are **automatically implemented** by `/shipwright-test` (Step 2.5) during the
Test phase. The test-runner reads all `claude-plan-e2e.md` files and generates Playwright specs:

- `e2e/flows/NN-flow-name.spec.ts` — one file per flow group
- `e2e/pages/*.page.ts` — Page Object Models
- `e2e/fixtures/test-data.ts` — seed data

The generated specs are then executed by Playwright (Step 3). Results flow into
`shipwright_test_results.json` → compliance reports → build dashboard.

## Required Layers on the FR

Every user-flow you plan an E2E for corresponds to a Functional Requirement whose
spec.md `Layers` column MUST include `e2e` (see spec-generation.md — a UI/flow FR
gets `unit, e2e`; a CRUD/DB FR gets `unit, integration`; every FR gets `unit`). When
planning surfaces a flow whose FR does not yet declare `e2e`, add `e2e` to that FR's
`Layers` — the E2E plan is the *evidence* that the layer is required. Keep the default
conservative: a genuinely API-only or purely-internal requirement stays `unit` (or
`unit, integration`) and gets no flow here. This is what makes the compliance
cross-layer coverage check meaningful rather than noise.

## Guidelines

- Focus on user-visible flows (not API-only routes)
- Use descriptive test names
- Include both happy path and key error cases
- Suggest Page Object Model for maintainability
- Reference specific UI components from the plan
- Mark flows requiring external services (Stripe, CRM API) with a note — these will be `test.skip()`'d
- Use consistent flow naming (NN prefix) — the test-runner maps these to spec file names
