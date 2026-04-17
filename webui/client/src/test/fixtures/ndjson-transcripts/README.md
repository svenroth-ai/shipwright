# NDJSON Transcript Fixtures

Recorded `ChatMessage[]` transcripts used by:

- Converter contract tests (`webui/client/src/chat-rendering/*.test.ts`)
- Playwright DOM/ARIA specs (replay via test helper)
- Perf gate (long-transcript variants)

Each `.jsonl` file is one `ChatMessage` per line, ordered by timestamp — the shape emitted by `GET /api/projects/:pid/chat/:tid`.

## Manifest

| File | Source | Count | Purpose |
| --- | --- | --- | --- |
| `short-happy-path.jsonl` | live task `e2064f1d` | 4 | user → assistant → result, minimal turn |
| `tool-heavy.jsonl` | live task `6a719e36` | 22 | many `tool_use` interleaved with assistant text |
| `askuser-roundtrip.jsonl` | live task `e08753f5` | 9 | AUQ: `tool_use` (AskUserQuestion) → user answer → `tool_result` pair |
| `resume-scenario.jsonl` | live task `c522d15d` | 6 | two distinct `session_id`s in system/init blobs (pre- and post-resume) |
| `live-task-7f1815f3.jsonl` | live task `7f1815f3` | 50 | multi-model (4.5 / 4.7 / haiku), long history |
| `thinking-heavy.jsonl` | synthetic | 7 | `type: "thinking"` blocks interleaved with assistant text |
| `markdown-streaming.jsonl` | synthetic | 6 | incomplete mid-stream code fence + tables/lists |

## Why some are synthetic

The live transcript corpus has no `type: "thinking"` messages — the CLI sessions that produced these fixtures ran without extended-thinking enabled. The thinking fixture is authored by hand to exercise the `reasoning` part-type path in the converter.

The markdown-streaming fixture covers a partial code fence mid-stream. This does occur live but was not cleanly isolatable from a live task; a focused synthetic fixture makes the assertion deterministic.

## Adding new fixtures

1. Capture: `fetch('http://localhost:3847/api/projects/<pid>/chat/<tid>')` → write each message as one JSON line.
2. Strip secrets: inspect `system.content` JSON blobs for API keys, local paths containing usernames, etc. Current fixtures contain Windows user paths — acceptable for our repo since they are public on GitHub but authors names are already baked into commit authors.
3. Append to the manifest above with a short purpose line.
4. Contract tests in `webui/client/src/chat-rendering/` automatically pick up any `*.jsonl` file in this dir if they use the `loadAllFixtures()` helper.
