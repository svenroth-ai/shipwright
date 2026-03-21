# Test Layers

## Overview

Shipwright uses a layered testing strategy. Each layer catches different classes of bugs.

## Layers

### 1. Unit Tests
- **What:** Pure functions, utilities, components in isolation
- **Tool:** Vitest (Next.js), pytest (Python)
- **When:** After every code change
- **Speed:** Fast (< 30s)

### 2. Smoke Test
- **What:** HTTP 200 on deployed URL + health endpoint
- **Tool:** shared/scripts/smoke_test.py
- **When:** After deployment
- **Speed:** Fast (< 5s)

### 3. E2E Tests (Playwright)
- **What:** Full user flows in browser
- **Tool:** Playwright
- **When:** After deployment, before PROD release
- **Speed:** Medium (30s-5min)

### 4. Security Scan
- **What:** Dependency vulnerabilities, code patterns
- **Tool:** Placeholder (future: Aikido, Snyk, etc.)
- **When:** Before release, on schedule
- **Speed:** Variable

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
