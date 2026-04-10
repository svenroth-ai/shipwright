import type { NdjsonMessage } from "../../../client/src/types/chat.js";

export function parseNdjsonLine(line: string): NdjsonMessage | null {
  const trimmed = line.trim();
  if (!trimmed) return null;

  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed.type !== "string") return null;
    return parsed as NdjsonMessage;
  } catch {
    console.warn(JSON.stringify({ level: "warn", message: "Malformed NDJSON line skipped" }));
    return null;
  }
}

export function isAskUserQuestion(msg: NdjsonMessage): boolean {
  if (msg.type === "tool_use") {
    const toolName = msg.tool_name ?? (msg.message as { tool_name?: string } | undefined)?.tool_name;
    return toolName === "AskUserQuestion";
  }
  return false;
}
