import { useMemo } from "react";
import {
  assistantText,
  askUserQuestionSummary,
  parseSessionJsonl,
  toolResults,
  toolUses,
  userText,
  type ParsedEvent,
} from "../../external/session-parser";
import { MarkdownText } from "./MarkdownText";
import { ToolOutputBlock } from "./ToolOutputBlock";

interface Props {
  content: string;
  /** Tail default per plan (round-2 GPT MAJOR 9). 200 events = ~two long turns of context. */
  tail?: number;
}

/**
 * Read-only transcript. Parses raw JSONL client-side, renders the
 * `user` + `assistant` events prominently and collapses metadata
 * (queue-op / file-history-snapshot / ai-title / last-prompt) to one-line
 * chips. Unknown top-level types fall through with an expandable raw-JSON
 * viewer so no CLI event is silently dropped.
 */
export function TranscriptViewer({ content, tail = 200 }: Props) {
  const parsed = useMemo(() => parseSessionJsonl(content), [content]);
  const visible = parsed.events.slice(-tail);

  if (visible.length === 0) {
    return (
      <div className="py-4 text-sm text-neutral-400" data-testid="transcript-empty">
        No events yet — waiting for JSONL content.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2" data-testid="transcript-viewer">
      {parsed.events.length > visible.length && (
        <div className="text-xs text-neutral-500">
          Showing last {visible.length} of {parsed.events.length} events.
        </div>
      )}
      {visible.map((event, i) => (
        <EventCard key={i} event={event} />
      ))}
      {parsed.malformedLines > 0 && (
        <div className="rounded border border-amber-300 bg-amber-50 p-1 text-xs text-amber-900">
          {parsed.malformedLines} malformed line(s) (likely the trailing partial line being written).
        </div>
      )}
    </div>
  );
}

function EventCard({ event }: { event: ParsedEvent }) {
  if (event.kind === "user") {
    const results = toolResults(event);
    // Tool results take priority over plain text rendering: when the user
    // event carries any tool_result block, we surface it as a tool_result
    // card with ANSI-stripped output. The legacy `[tool_result] <text>`
    // string from userText() would lose structure.
    if (results.length > 0) {
      return (
        <div className="rounded border border-neutral-200 bg-white p-2" data-testid="event-tool-result">
          <div className="text-xs font-semibold text-neutral-600">tool_result</div>
          {results.map((r) => (
            <ToolOutputBlock key={r.tool_use_id} text={r.content} isError={r.is_error} />
          ))}
        </div>
      );
    }
    const t = userText(event);
    return (
      <div className="rounded border border-neutral-200 bg-neutral-50 p-2" data-testid="event-user">
        <div className="text-xs font-semibold text-neutral-600">user</div>
        <div className="whitespace-pre-wrap break-words text-sm">
          {t || <em className="text-neutral-400">(tool result or empty)</em>}
        </div>
      </div>
    );
  }
  if (event.kind === "assistant") {
    const text = assistantText(event);
    const tools = toolUses(event);
    return (
      <div className="rounded border border-blue-200 bg-blue-50 p-2" data-testid="event-assistant">
        <div className="text-xs font-semibold text-blue-700">assistant</div>
        {text && <MarkdownText text={text} />}
        {tools.map((tu) => (
          <ToolUseChip key={tu.id} name={tu.name} input={tu.input} />
        ))}
      </div>
    );
  }
  if (event.kind === "attachment") {
    return (
      <div className="rounded border border-neutral-200 bg-neutral-50 p-1 text-xs text-neutral-600" data-testid="event-attachment">
        attachment
      </div>
    );
  }
  if (event.kind === "unknown") {
    return (
      <details
        className="rounded border border-amber-300 bg-amber-50 p-1 text-xs"
        data-testid="event-unknown"
      >
        <summary className="cursor-pointer">Unknown event: {event.originalType}</summary>
        <pre className="overflow-x-auto text-[10px]">{JSON.stringify(event.raw, null, 2)}</pre>
      </details>
    );
  }
  return (
    <div
      className="rounded border border-neutral-200 bg-white p-1 text-[10px] text-neutral-500"
      data-testid={`event-${event.kind}`}
    >
      {event.kind}
    </div>
  );
}

function ToolUseChip({ name, input }: { name: string; input: unknown }) {
  if (name === "AskUserQuestion") {
    const q = askUserQuestionSummary(input);
    return (
      <div
        className="mt-1 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900"
        data-testid="event-ask-user-question"
      >
        <div className="text-[10px] font-semibold uppercase tracking-wide">
          AskUserQuestion — answer in your terminal
        </div>
        <div className="mt-1 text-sm">{q.question}</div>
        {q.options.length > 0 && (
          <ul className="mt-1 list-disc pl-4">
            {q.options.map((o, i) => (
              <li key={i}>{o}</li>
            ))}
          </ul>
        )}
        {q.fallback && (
          <div className="mt-1 text-[10px] italic text-amber-700">
            (Question payload schema differed from expected — open the task in your terminal to see the original.)
          </div>
        )}
      </div>
    );
  }
  return (
    <div
      className="mt-1 rounded border border-blue-300 bg-white p-1 text-xs"
      data-testid="event-tool-use"
    >
      <span className="font-semibold">tool_use</span>: {name}
    </div>
  );
}
