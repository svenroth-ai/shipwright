# Test Layers

## Overview

Shipwright uses a layered testing strategy. Each layer catches different classes of bugs.

## Layers

### 1. Unit Tests
- **What:** Pure functions, utilities, components in isolation
- **Tool:** Vitest (Next.js), pytest (Python)
- **When:** After every code change
- **Speed:** Fast (< 30s)

### 1.5. Integration Tests (Real DB)
- **What:** CRUD operations, API routes, server actions against real Supabase (localhost only)
- **Tool:** Vitest with `vitest.integration.config.ts` (NO mocks, `.env.test`)
- **When:** After unit tests pass, before smoke test
- **Speed:** Medium (10-30s)
- **Cleanup:** Cascade delete via test user (`ON DELETE CASCADE`)
- **Blocking:** Yes — with autofix (3 retries, fast-fail for infra errors like ECONNREFUSED)
- **Safety:** URL must be localhost/127.0.0.1. Service-role for setup/teardown only. Never weaken RLS to pass tests.

### 1.6. pgTAP Database Tests
- **What:** RLS policies, constraints, DB functions at schema level
- **Tool:** `supabase test db` (pgTAP + supabase-test-helpers)
- **When:** After integration tests, before smoke test. Only if `supabase/tests/database/` exists
- **Speed:** Fast (< 10s)
- **Blocking:** Yes — with autofix (3 retries)

### 2. Smoke Test
- **What:** HTTP 200 on deployed URL + health endpoint
- **Tool:** shared/scripts/smoke_test.py
- **When:** After deployment
- **Speed:** Fast (< 5s)

### 2.5. Browser Verify (in shipwright-build)
- **What:** Quick visual check — load page, screenshot, check console errors
- **Tool:** `browser-verify.ts` (TypeScript helper using Playwright)
- **When:** After each section implementation (Step 4.5 in shipwright-build)
- **Speed:** Fast (5-15s)
- **Auto-fix:** Yes — `browser-fixer` subagent analyzes screenshot + console errors

### 3. E2E Tests (Playwright)
- **What:** Full user flows in browser (all `e2e/*.spec.ts` files)
- **Tool:** Playwright via `playwright_runner.py`
- **When:** After all sections built, as part of `/shipwright-test`
- **Speed:** Medium (30s-5min)
- **Setup:** Automated via `playwright_setup.py` (idempotent)
- **Config:** `playwright.config.ts` generated from template (Chromium only, JSON reporter)
- **Results:** Parsed from `e2e-results.json` (Playwright JSON reporter)

### 3.6. Cross-Page UI Consistency Check
- **What:** Detects inconsistencies across pages (heading sizes, spacing, component patterns, form structure, token usage, interactive patterns)
- **Tool:** `ui_consistency_check.py` (static source analysis, no browser needed)
- **When:** After E2E results verification (3.5), before visual comparison (3.7). Only for UI projects with `designs/visual-guidelines.md`
- **Speed:** Fast (< 10s, static file analysis)
- **Non-blocking:** WARNING level — outliers logged, autofix attempted, never hard-fails pipeline
- **Algorithm:** Majority-wins — most common pattern = expected, deviations are outliers

### 4. Security Scan
- **What:** Dependency vulnerabilities, SAST, secrets detection
- **Tool:** /shipwright-security (Aikido API)
- **When:** After test, before deploy (via /shipwright-run or standalone)
- **Speed:** Variable (API-dependent)

## Profile-Aware Strategy

The test runner reads the stack profile to determine:
- Which unit test runner to use
- Whether E2E makes sense (UI project vs API-only)
- What the DEV URL pattern is

## Auto-Fix Mode (`--fix`)

When enabled:
1. Run tests
2. If failures: analyze error output
3. Attempt code fix
4. Re-run tests
5. Max 3 retries
6. Report remaining failures

The agent uses its code understanding to fix tests — it reads the error,
finds the relevant source code, and applies a fix. This is not a dumb retry.

For Playwright/E2E failures, the `browser-fixer` subagent is used instead:
- Receives screenshot, console errors, and DOM snippet
- Uses multimodal analysis (Claude sees the screenshot)
- Returns a specific file + fix recommendation with confidence level
