# Conventions — Shipwright Command Center

## TypeScript
- Strict mode (`"strict": true` in tsconfig)
- No `any` — use `unknown` + type guards
- Shared types in `client/src/types/` (imported by both server and client via path aliases)
- Prefer interfaces over type aliases for object shapes
- Use `as const` for literal unions

## Server (Hono)
- One route file per resource in `server/src/routes/`
- Route files export a Hono app instance (grouped routes)
- Core managers are singletons initialized at startup
- All async errors caught by Hono's error handler
- JSON responses: `{ data: T }` on success, `{ error: string, detail?: string }` on failure
- SSE events: `{ type: string, payload: T }`

## Client (React)
- Functional components only, no class components
- TanStack React Query for ALL server data (no raw fetch in components)
- Custom hooks in `client/src/hooks/` for query/mutation logic
- Radix UI for accessible primitives (Dialog, Popover, Tooltip, etc.)
- TailwindCSS 4 for styling — no CSS modules, no styled-components
- Component files: PascalCase (e.g., `ChatMessage.tsx`)
- Hook files: camelCase with `use` prefix (e.g., `useProjects.ts`)

## File Organization
- Components grouped by UI area: `nav/`, `board/`, `detail/`, `chat/`, `viewer/`, `explorer/`, `inbox/`, `wizard/`, `settings/`
- Max 300 lines per file — split into subcomponents if larger
- Co-locate tests next to source: `ChatMessage.tsx` → `ChatMessage.test.tsx`
- Index files only for barrel exports of public API

## Naming
- React components: PascalCase
- Functions/variables: camelCase
- Constants: UPPER_SNAKE_CASE
- Types/interfaces: PascalCase
- API routes: kebab-case (`/api/projects/:id/chat`)
- SSE event types: colon-separated (`task:created`, `chat:message`)

## Git
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- Scope: `feat(chat):`, `fix(sidebar):`, `refactor(adapter):`
- One logical change per commit
