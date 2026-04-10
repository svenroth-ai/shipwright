# Section 01: Vite Project Setup

## Goal

Create the Vite 6 + React 19 project scaffold with TailwindCSS 4, Radix UI, TanStack React Query, and all required runtime/dev dependencies. Configure TypeScript strict mode, Vite dev server proxy to the backend (port 3847), and the test toolchain (Vitest + React Testing Library + MSW). This section produces no visible UI — it is pure infrastructure that all subsequent sections build upon.

## FRs Covered

None directly — this section is infrastructure. It supports all FRs by providing the build toolchain and dependency foundation.

## Constraints Addressed

- **CO-02.01** — React 19 + Vite 6 + TailwindCSS 4 + Radix UI
- **CO-02.02** — TanStack React Query installed
- **CO-02.03** — Native EventSource (no SSE library)
- **CO-02.04** — react-markdown + remark-gfm + rehype-highlight installed
- **CO-02.05** — react-diff-viewer installed
- **CO-02.06** — No Monaco Editor
- **CO-02.10** — Inter font configured

## Files to Create

| File | Purpose |
|------|---------|
| `client/package.json` | Dependencies, scripts, project metadata |
| `client/tsconfig.json` | TypeScript strict configuration with path aliases |
| `client/tsconfig.node.json` | TypeScript config for Vite config file |
| `client/vite.config.ts` | Vite 6 config: React plugin, proxy to :3847, path aliases |
| `client/index.html` | HTML entry point with Inter font link, root div |
| `client/src/main.tsx` | React 19 entry: createRoot, QueryClientProvider, App |
| `client/src/App.tsx` | Root component placeholder (renders "Shipwright Command Center") |
| `client/src/index.css` | TailwindCSS 4 imports + CSS custom properties for brand tokens |
| `client/src/vite-env.d.ts` | Vite client type reference |
| `client/vitest.config.ts` | Vitest configuration: jsdom, React Testing Library, coverage |
| `client/src/test/setup.ts` | Test setup: MSW server lifecycle, cleanup |
| `client/src/test/mocks/handlers.ts` | MSW request handlers (empty scaffold with typed imports) |
| `client/src/test/mocks/server.ts` | MSW setupServer export |
| `client/src/App.test.tsx` | Smoke test: App renders without crashing |

## Implementation Steps

1. **Create `client/package.json`** with:
   - `name: "shipwright-command-center-client"`, `version: "0.1.0"`, `type: "module"`
   - Scripts: `dev` (vite), `build` (tsc -b && vite build), `preview` (vite preview), `test` (vitest), `test:ui` (vitest --ui), `lint` (eslint src/), `typecheck` (tsc --noEmit)
   - Dependencies:
     - `react: "^19.0.0"`, `react-dom: "^19.0.0"`
     - `react-router-dom: "^7.0.0"`
     - `@tanstack/react-query: "^5.0.0"`
     - `@radix-ui/react-dialog`, `@radix-ui/react-popover`, `@radix-ui/react-tooltip`, `@radix-ui/react-collapsible`, `@radix-ui/react-select`, `@radix-ui/react-tabs`, `@radix-ui/react-scroll-area`, `@radix-ui/react-dropdown-menu`
     - `react-markdown: "^9.0.0"`, `remark-gfm: "^4.0.0"`, `rehype-highlight: "^7.0.0"`
     - `react-diff-viewer-continued: "^4.0.0"` (maintained fork)
     - `lucide-react: "^0.400.0"` (icon library)
   - Dev dependencies:
     - `vite: "^6.0.0"`, `@vitejs/plugin-react: "^4.0.0"`
     - `typescript: "^5.6.0"`, `@types/react: "^19.0.0"`, `@types/react-dom: "^19.0.0"`
     - `tailwindcss: "^4.0.0"`, `@tailwindcss/vite: "^4.0.0"`
     - `vitest: "^3.0.0"`, `@testing-library/react: "^16.0.0"`, `@testing-library/jest-dom: "^6.0.0"`, `@testing-library/user-event: "^14.0.0"`, `jsdom: "^25.0.0"`
     - `msw: "^2.0.0"`
     - `eslint`, `@typescript-eslint/eslint-plugin`, `@typescript-eslint/parser`

2. **Create `client/tsconfig.json`** with:
   - `"strict": true`, `"target": "ES2022"`, `"module": "ESNext"`, `"moduleResolution": "bundler"`
   - `"jsx": "react-jsx"`, `"lib": ["ES2022", "DOM", "DOM.Iterable"]`
   - `"outDir": "./dist"`, `"rootDir": "./src"`
   - Path aliases: `"@/*": ["./src/*"]`, `"@shared/*": ["./src/types/*"]`
   - `"noUnusedLocals": true`, `"noUnusedParameters": true`, `"noFallthroughCasesInSwitch": true`

3. **Create `client/tsconfig.node.json`** — extends tsconfig, includes vite config files, targets Node for build tooling.

4. **Create `client/vite.config.ts`** with:
   - `@vitejs/plugin-react` plugin
   - `@tailwindcss/vite` plugin
   - `resolve.alias`: `@` -> `./src`
   - `server.proxy`: `/api` -> `http://localhost:3847` (proxy all API calls to backend)
   - `server.port`: `5173`

5. **Create `client/index.html`** with:
   - `<!DOCTYPE html>`, `<html lang="en">`
   - `<head>`: charset, viewport meta, Inter font from Google Fonts (`weights 400;500;600;700`), title "Shipwright Command Center"
   - `<body>`: `<div id="root"></div>`, `<script type="module" src="/src/main.tsx"></script>`

6. **Create `client/src/main.tsx`** with:
   - Import React 19 `createRoot`
   - Create a `QueryClient` with default options: `staleTime: 30_000`, `retry: 1`, `refetchOnWindowFocus: false`
   - Wrap `<App />` in `<QueryClientProvider>` and `<React.StrictMode>`
   - Mount to `#root`

7. **Create `client/src/App.tsx`** with:
   - Minimal functional component returning a div with text "Shipwright Command Center"
   - This is a placeholder replaced in Section 02 with the router

8. **Create `client/src/index.css`** with:
   - TailwindCSS 4 import: `@import "tailwindcss";`
   - CSS custom properties under `:root`:
     ```css
     --color-primary: #6b5e56;
     --color-background: #f5f0eb;
     --color-surface: #ffffff;
     --color-sidebar-bg: #5c5652;
     --color-sidebar-text: #ffffff;
     --color-phase-project: #9ca3af;
     --color-phase-design: #a855f7;
     --color-phase-plan: #3b82f6;
     --color-phase-build: #f97316;
     --color-phase-test: #22c55e;
     --color-phase-deploy: #14b8a6;
     --font-family: 'Inter', sans-serif;
     --radius: 12px;
     --shadow-card: 0 1px 3px rgba(0,0,0,0.1);
     ```
   - `body` styles: `font-family: var(--font-family)`, `background: var(--color-background)`, `margin: 0`

9. **Create `client/src/vite-env.d.ts`** — triple-slash reference to `vite/client` types.

10. **Create `client/vitest.config.ts`** with:
    - `test.environment: "jsdom"`
    - `test.globals: true`
    - `test.setupFiles: ["./src/test/setup.ts"]`
    - `test.css: true`
    - Same resolve aliases as vite.config.ts

11. **Create `client/src/test/setup.ts`** with:
    - Import `@testing-library/jest-dom` for extended matchers
    - Import MSW server from `./mocks/server`
    - `beforeAll(() => server.listen({ onUnhandledRequest: "warn" }))`
    - `afterEach(() => server.resetHandlers())`
    - `afterAll(() => server.close())`

12. **Create `client/src/test/mocks/server.ts`** — export `server` from `msw/node` `setupServer()` with handlers.

13. **Create `client/src/test/mocks/handlers.ts`** — export empty `handlers` array with `HttpHandler[]` type. Add comment scaffolds for each API endpoint to be filled in by later sections.

14. **Create `client/src/App.test.tsx`** — smoke test that renders `<App />` wrapped in `QueryClientProvider` and asserts "Shipwright Command Center" is in the document.

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/App.test.tsx` | App renders without crashing, displays expected text |

### Test Infrastructure

- Vitest with jsdom environment
- @testing-library/react for component rendering
- @testing-library/user-event for interaction simulation
- MSW for API mocking (scaffold only in this section)
- Tests run via `npm test` (vitest in watch mode) or `npm test -- --run` (single run)

## Dependencies

None — this is the foundation section.

## Acceptance Criteria

- [ ] `npm install` completes without errors
- [ ] `npm run dev` starts Vite dev server on port 5173
- [ ] `npm run typecheck` passes with zero errors
- [ ] `npm test -- --run` passes the App smoke test
- [ ] Vite proxy forwards `/api/*` requests to `http://localhost:3847`
- [ ] TailwindCSS 4 classes are applied (visible in browser devtools)
- [ ] Inter font loads from Google Fonts
- [ ] Brand CSS custom properties are available in `:root`
