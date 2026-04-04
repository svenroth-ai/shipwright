# Performance Checklist

Quick performance review reference. Check during self-review for performance-sensitive sections.

---

## When to Apply

- Section touches data fetching, API routes, or database queries
- Section introduces new UI components rendering lists or large datasets
- Section adds dependencies or increases bundle size
- Profile has `performance_budget` defined

---

## Backend Checks

### Data Fetching
- **No N+1 queries:** Avoid looping DB calls. Use joins, includes, or batch queries.
  ```typescript
  // BAD: N+1
  const tasks = await db.tasks.findMany();
  for (const t of tasks) { t.owner = await db.users.findOne(t.ownerId); }

  // GOOD: single query with join
  const tasks = await db.tasks.findMany({ include: { owner: true } });
  ```
- **Pagination on list endpoints:** Never return unbounded results.
  Use `take`/`skip` or cursor-based pagination.
- **No unnecessary data:** Select only needed fields. Avoid `SELECT *` patterns.

### Async & Blocking
- No synchronous blocking in async request handlers
- Heavy computation offloaded to background jobs or workers
- Database connections pooled, not created per request

### Caching
- Frequently read, rarely changed data cached (user sessions, config, lookups)
- API responses with stable data set `Cache-Control` headers
- Static assets served with long-lived cache headers + content hashing

---

## Frontend Checks

### Bundle Size
- Tree-shakable imports (`import { x } from 'lib'` not `import lib from 'lib'`)
- Heavy libraries loaded via dynamic import (`React.lazy`, `next/dynamic`)
- No duplicate dependencies (check with `npm ls <pkg>`)

### Rendering
- Lists with 50+ items use virtualization (react-window, tanstack-virtual)
- Expensive computations wrapped in `useMemo` (only when measured as slow)
- Stable references for props passed to memoized children
- No object/array literals created inline as props in render

### Images & Assets
- Images have explicit `width` and `height` attributes (prevents CLS)
- Below-fold images use `loading="lazy"`
- Responsive images use `srcset` and `sizes`
- Images served in modern formats (WebP, AVIF) where supported

---

## Core Web Vitals Targets

| Metric | Good | Needs Work | Poor |
|--------|------|------------|------|
| **LCP** (Largest Contentful Paint) | ≤ 2.5s | ≤ 4.0s | > 4.0s |
| **INP** (Interaction to Next Paint) | ≤ 200ms | ≤ 500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | ≤ 0.1 | ≤ 0.25 | > 0.25 |

---

## Performance Budget (reference defaults)

| Asset | Budget |
|-------|--------|
| JS bundle (initial, gzipped) | < 200 KB |
| CSS (gzipped) | < 50 KB |
| Images (above-fold, each) | < 200 KB |
| Fonts (total) | < 100 KB |
| API response time (p95) | < 200 ms |
| Time to Interactive (4G) | < 3.5s |

---

## Anti-Rationalization

| Rationalization | Reality |
|---|---|
| "We'll optimize later" | Performance debt compounds. Fix obvious issues now |
| "It's fast on my machine" | Test on representative hardware and network conditions |
| "This optimization is obvious" | Measure first. Assumptions about bottlenecks are often wrong |
| "Users won't notice 100ms" | Research shows even small delays impact conversion and engagement |
| "The framework handles it" | Frameworks prevent some issues but can't fix structural problems like N+1 queries |
