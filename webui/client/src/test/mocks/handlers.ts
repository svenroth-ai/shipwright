import type { HttpHandler } from 'msw';

// API mock handlers — filled in by later sections
// GET /api/projects
// GET /api/projects/:id/tasks
// GET /api/inbox
// POST /api/inbox/:id/answer
// GET /api/projects/:id/chat
// GET /api/projects/:id/pipeline
// GET /api/projects/:id/docs
// GET /api/events (SSE)

export const handlers: HttpHandler[] = [];
