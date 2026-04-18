# Third-Party Attribution

Vendored/consumed packages that ship in the client bundle with their own licenses.

## Runtime — production bundle

### `@assistant-ui/react` — MIT

- Source: <https://github.com/Yonom/assistant-ui>
- License: MIT
- Version pinned in `package.json` (bump only with an explicit ADR).
- Usage: message rendering layer — `ThreadPrimitive`, `MessagePrimitive`, `ComposerPrimitive`, `ChainOfThoughtPrimitive`, `MessagePartPrimitive`, `ExternalStoreRuntime`. See [`webui/agent_docs/chat-rendering.md`](../agent_docs/chat-rendering.md) for the state-ownership contract and upstream-watch policy.

## Build-time / runtime transitive

`assistant-ui` pulls in several Radix UI packages (MIT), `@ai-sdk/provider`, and Zustand. All MIT-licensed. Aggregate license notice regenerated during release by scanning `package-lock.json`.

## Historical attribution

### `MarkdownContent` — MIT (ported, 2026-04-11)

- Originally adapted from [The-Vibe-Company/companion](https://github.com/The-Vibe-Company/companion) under MIT. The current component lives at `webui/client/src/components/chat/MarkdownContent.tsx`. If the assistant-ui migration ends up removing every chat callsite of this component (verified per Sub-iterate A grep policy), the file may still be used by viewer/explorer code — do not delete without a full grep.
