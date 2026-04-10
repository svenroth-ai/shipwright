# Section 01: Project Setup & Hono Server

## Goal

Establish the Node.js project structure, install all dependencies, configure TypeScript strict mode, and create a minimal Hono server with CORS, static file serving, and a health endpoint. This is the scaffold that all subsequent sections build on.

## FRs Covered

- **FR-01.01** — The system SHALL start a Hono HTTP server on a configurable port with a default of 3847.
- **FR-01.02** — The system SHALL serve static files from the frontend build directory at the root path.
- **FR-01.03** — The system SHALL enable CORS for localhost origins during development.

## Files to Create

| File | Purpose |
|------|---------|
| `server/package.json` | Dependencies and scripts |
| `server/tsconfig.json` | TypeScript strict configuration |
| `server/src/index.ts` | Hono app entry point, middleware, server startup |
| `server/src/config.ts` | Centralized configuration (port, paths, defaults) |
| `server/vitest.config.ts` | Test runner configuration |
| `server/src/middleware/error-handler.ts` | Hono error middleware returning JSON error bodies |
| `server/src/middleware/logger.ts` | Structured request logging middleware |
| `server/src/config.test.ts` | Unit tests for config |
| `server/src/index.test.ts` | Integration tests for server endpoints |
| `server/src/middleware/error-handler.test.ts` | Unit tests for error handler |

## Implementation Steps

1. **Initialize `server/package.json`** with:
   - `name: "shipwright-command-center-server"`, `version: "0.1.0"`, `type: "module"`
   - Scripts: `dev` (tsx watch src/index.ts), `build` (tsc), `start` (node dist/index.js), `test` (vitest)
   - Dependencies: `hono`, `@hono/node-server`, `chokidar`, `node-cron`, `proper-lockfile`, `uuid`
   - Dev dependencies: `typescript`, `vitest`, `@types/node`, `tsx`

2. **Create `server/tsconfig.json`** with:
   - `"strict": true`, `"target": "ES2022"`, `"module": "NodeNext"`, `"moduleResolution": "NodeNext"`
   - `"outDir": "./dist"`, `"rootDir": "./src"`
   - Path alias `@shared/*` pointing to `../client/src/types/*` so server can import shared types

3. **Create `server/src/config.ts`**:
   - Export a `ServerConfig` interface with: `port`, `maxConcurrent`, `registryDir`, `heartbeatIntervalMs`, `staticDir`
   - Export a `getConfig()` function reading from `process.env` with fallback defaults:
     - `port`: `PORT` env var or `3847`
     - `maxConcurrent`: `SHIPWRIGHT_MAX_CONCURRENT` env var or `3`
     - `registryDir`: resolving `~/.shipwright-webui/`
     - `heartbeatIntervalMs`: `30000`
     - `staticDir`: path to client build output

4. **Create `server/src/middleware/error-handler.ts`**:
   - Export a custom `AppError` class extending `Error` with a `statusCode` property and optional `detail` field
   - Export a Hono `onError` handler that:
     - Catches all unhandled errors
     - Returns `{ error: string, detail?: string }` with appropriate HTTP status codes (400 for validation, 404 for not found, 500 for unexpected)
     - Logs structured error context (QR-01.08)

5. **Create `server/src/middleware/logger.ts`**:
   - Export a Hono middleware that logs each request with method, path, status code, and duration in milliseconds
   - Use `console.log` with JSON-structured output for machine parseability (QR-01.08)

6. **Create `server/src/index.ts`**:
   - Import Hono and `@hono/node-server`'s `serve()`
   - Instantiate Hono app
   - Register CORS middleware for `localhost:*` origins using Hono's built-in `cors()` from `hono/cors` (FR-01.03)
   - Register error handler middleware
   - Register logger middleware
   - Serve static files from `config.staticDir` at `/` using Hono's `serveStatic()` from `@hono/node-server/serve-static`
   - Add `GET /api/health` returning `{ status: "ok", version: string, uptime: number }`
   - Call `serve({ fetch: app.fetch, port: config.port })` and log the listening address
   - Export the `app` object for testing

7. **Create `server/vitest.config.ts`**:
   - Configure TypeScript path aliases matching tsconfig
   - Test file pattern `**/*.test.ts`
   - `threads: true`

## Test Strategy

### Unit Tests

**`server/src/config.test.ts`**:
- `getConfig()` returns default port 3847 when no `PORT` env var is set
- `getConfig()` reads `PORT` env var and returns parsed number
- `getConfig()` returns default `maxConcurrent` of 3
- `getConfig()` reads `SHIPWRIGHT_MAX_CONCURRENT` env var

**`server/src/middleware/error-handler.test.ts`**:
- `AppError` class creates proper error instances with status codes
- `AppError` with statusCode 404 produces correct JSON response
- `AppError` with statusCode 400 includes detail field when provided
- Unknown errors produce 500 with generic message

### Integration Tests

**`server/src/index.test.ts`** (using Hono's `app.request()` test helper — no real HTTP server needed):
- `GET /api/health` returns 200 with `{ status: "ok", version: string, uptime: number }`
- Unknown routes return 404 with JSON error body
- CORS headers are present on responses for localhost origins
- Error handler produces correct JSON for thrown `AppError` instances

## Dependencies

None — this is the foundation section.

## Acceptance Criteria

**FR-01.01: Hono Server Startup**
- [ ] Server starts on port 3847 by default
- [ ] Port is configurable via settings.json or environment variable
- [ ] Server logs the listening address on startup

**FR-01.02: Static File Serving**
- [ ] Static files from the frontend build directory are served at the root path

**FR-01.03: CORS**
- [ ] CORS is enabled for localhost origins during development
- [ ] CORS headers are present on responses
