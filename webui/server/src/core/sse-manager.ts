import type { SSEEvent } from "../../../client/src/types/sse.js";

interface SSEClient {
  id: string;
  controller: ReadableStreamDefaultController;
  connectedAt: string;
}

export class SSEManager {
  private clients = new Map<string, SSEClient>();
  private encoder = new TextEncoder();

  addClient(id: string, controller: ReadableStreamDefaultController): void {
    this.clients.set(id, {
      id,
      controller,
      connectedAt: new Date().toISOString(),
    });
    console.log(
      JSON.stringify({
        event: "sse:connect",
        clientId: id,
        clientCount: this.clients.size,
      })
    );
  }

  removeClient(id: string): void {
    this.clients.delete(id);
    console.log(
      JSON.stringify({
        event: "sse:disconnect",
        clientId: id,
        clientCount: this.clients.size,
      })
    );
  }

  broadcast(event: SSEEvent): void {
    const data = `event: ${event.type}\ndata: ${JSON.stringify(event.payload)}\n\n`;
    const encoded = this.encoder.encode(data);

    for (const [id, client] of this.clients) {
      try {
        client.controller.enqueue(encoded);
      } catch {
        this.removeClient(id);
      }
    }
  }

  broadcastToProject(_projectId: string, event: SSEEvent): void {
    this.broadcast(event);
  }

  getClientCount(): number {
    return this.clients.size;
  }

  closeAll(): void {
    for (const [id, client] of this.clients) {
      try {
        client.controller.close();
      } catch {
        // Already closed
      }
      this.clients.delete(id);
    }
  }
}
