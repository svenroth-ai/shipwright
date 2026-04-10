# Section 09: SSE Manager — Real-Time Event Streaming

## Goal

Implement the SSE endpoint that streams real-time events to connected browser clients, manages multiple concurrent connections with proper cleanup on disconnect, provides a broadcast API that other server modules use to push events, and formats events according to the SSE protocol specification.

## FRs Covered

- **FR-01.04** — SSE endpoint at GET /api/events
- **FR-01.05** — Broadcast project state changes, inbox updates, task transitions, process lifecycle events
- **FR-01.06** — Multiple concurrent SSE connections with disconnection cleanup

## Files to Create/Modify

| Action | Path |
|--------|------|
| Create | `server/src/core/sse-manager.ts` |
| Create | `server/src/routes/sse.ts` |
| Create | `server/src/core/sse-manager.test.ts` |
| Create | `server/src/routes/sse.test.ts` |

## Implementation Steps

### Step 1: Define SSEClient Interface

Create `server/src/core/sse-manager.ts`. Define an internal interface for tracking connected clients:

```typescript
interface SSEClient {
  id: string;
  controller: ReadableStreamDefaultController;
  connectedAt: string;
}
```

### Step 2: Implement SSEManager Class

Export `class SSEManager`:

- **Private state:** `clients: Map<string, SSEClient>` keyed by client ID.

### Step 3: Implement `addClient()` Method

```typescript
addClient(id: string, controller: ReadableStreamDefaultController): void
```

- Create `SSEClient` with the provided id, controller, and current timestamp.
- Store in `clients` Map.
- Log connection with client ID and total client count (structured log with `{ event: "sse:connect", clientId, clientCount }`).

### Step 4: Implement `removeClient()` Method

```typescript
removeClient(id: string): void
```

- Remove from `clients` Map.
- Log disconnection with client ID and remaining client count.

### Step 5: Implement `broadcast()` Method

```typescript
broadcast(event: SSEEvent): void
```

- For each client in the Map:
  - Format the event as SSE: `event: ${event.type}\ndata: ${JSON.stringify(event.payload)}\n\n`.
  - Encode the string as a `Uint8Array` using `TextEncoder`.
  - Try to enqueue the encoded data on the client's `controller`.
  - If the enqueue throws (client disconnected), call `removeClient(client.id)`.

### Step 6: Implement `broadcastToProject()` Method

```typescript
broadcastToProject(projectId: string, event: SSEEvent): void
```

- For this single-user local app, broadcast to all clients (same as `broadcast()`). The method exists as an API surface for future per-project subscription filtering.

### Step 7: Implement Utility Methods

- `getClientCount(): number` — return `clients.size`.
- `closeAll(): void` — iterate all clients, try to close each controller, clear the Map. Used during graceful shutdown.

### Step 8: Create SSE Route Handler

Create `server/src/routes/sse.ts`. Export a function that returns a Hono route handler:

```typescript
export function createSSERoute(sseManager: SSEManager): Hono
```

Register `GET /api/events`:

- Create a `ReadableStream` with a start callback that:
  1. Generates a unique client ID (UUID).
  2. Calls `sseManager.addClient(id, controller)`.
  3. Sends an initial `connected` event: encode and enqueue `event: connected\ndata: ${JSON.stringify({ timestamp: new Date().toISOString() })}\n\n`.
- The stream's cancel callback (triggered when client disconnects / abort signal fires) calls `sseManager.removeClient(id)`.
- Return a `Response` with the readable stream body and headers:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`

Alternative approach using Hono's `streamSSE()` from `hono/streaming`:

```typescript
app.get("/api/events", (c) => {
  return streamSSE(c, async (stream) => {
    const clientId = crypto.randomUUID();
    // Register with manager using a push mechanism
    // Send initial connected event
    // Keep stream alive until abort
    stream.onAbort(() => sseManager.removeClient(clientId));
  });
});
```

Use whichever approach integrates more cleanly with the SSEManager's `ReadableStreamDefaultController`-based broadcast. The `ReadableStream` approach is recommended because it gives direct access to the controller that `broadcast()` needs.

### Step 9: Write Unit Tests for SSEManager

Create `server/src/core/sse-manager.test.ts`:

1. `addClient` increases client count from 0 to 1.
2. `addClient` with two clients increases count to 2.
3. `removeClient` decreases client count.
4. `removeClient` for non-existent ID does not throw.
5. `broadcast` writes SSE-formatted data to all client controllers.
6. `broadcast` event format: verify output contains `event: <type>\n` and `data: <json>\n\n`.
7. `broadcast` auto-removes client if controller.enqueue throws.
8. `broadcastToProject` sends to all clients (single-user behavior).
9. `closeAll` empties the client map.
10. `getClientCount` returns correct count after add/remove operations.

Mock `ReadableStreamDefaultController` with a spy on `enqueue()` and optionally throw to simulate disconnected clients.

### Step 10: Write Integration Tests for SSE Route

Create `server/src/routes/sse.test.ts`:

1. `GET /api/events` returns status 200.
2. Response has `Content-Type: text/event-stream` header.
3. Response has `Cache-Control: no-cache` header.
4. Response body is a readable stream (streaming response, not buffered).

Use Hono's `app.request()` test helper. Note: verifying actual SSE event delivery in integration tests may require reading from the response stream, which can be done by consuming the `ReadableStream` reader.

## Test Strategy

### Unit Tests

| File | Coverage |
|------|----------|
| `server/src/core/sse-manager.test.ts` | Client add/remove, broadcast formatting, error handling, cleanup |
| `server/src/routes/sse.test.ts` | HTTP response headers, status code, content type |

### Integration Tests

| File | Coverage |
|------|----------|
| `server/src/routes/sse.test.ts` | GET /api/events returns streaming response with correct headers |

### Mocking Strategy

- `ReadableStreamDefaultController` — create mock objects with `enqueue` and `close` spy functions.
- For route tests: use Hono's `app.request("/api/events")` which returns a standard `Response` object. Inspect headers and status. Optionally use `response.body.getReader()` to verify initial connected event.

## Dependencies

- **Section 01 (Project Setup)** — Hono app instance, middleware stack.
- **Section 02 (Shared Types)** — `SSEEvent`, `SSEEventType` interfaces from `client/src/types/sse.ts`.
- **npm packages:** none beyond Hono (already installed in Section 01).

## Acceptance Criteria

**FR-01.04: SSE Endpoint**
- [ ] GET /api/events returns Content-Type: text/event-stream
- [ ] Events are formatted as valid SSE (event: + data: + double newline)
- [ ] Connection stays open and receives subsequent events
- [ ] Initial `connected` event is sent on connection

**FR-01.05: Event Broadcasting**
- [ ] Project state changes are broadcast to connected clients
- [ ] Inbox updates are broadcast to connected clients
- [ ] Task status transitions are broadcast to connected clients
- [ ] Process lifecycle events are broadcast to connected clients

**FR-01.06: Multiple Connections & Cleanup**
- [ ] Multiple concurrent SSE connections are supported
- [ ] Disconnected clients are cleaned up automatically
- [ ] Failed writes to a disconnected client remove that client from the map
- [ ] `closeAll()` cleanly shuts down all connections during server shutdown
