/*
 * Chat-style bubble transcript for external-launch tasks.
 *
 * Replaces the flat event-card list from Sub-iterate 1. Each event maps
 * to a "bubble":
 *   - user → right-aligned, neutral grey.
 *   - assistant → left-aligned, subtle blue.
 *   - tool_use → left-aligned card under the assistant bubble (sibling
 *     to tool_result chronologically; correlation deferred to a future
 *     iterate per plan).
 *   - tool_result → left-aligned card with ANSI-stripped content.
 *   - AskUserQuestion → amber pending banner, flips green when a
 *     matching tool_result arrives later in the stream.
 *   - unknown / attachment → neutral chip with a details disclosure.
 *
 * Auto-scroll = CSS `overflow-anchor: auto` on the scroll container plus
 * a `useAutoScroll` safety net (ADR-035).
 *
 * Virtualization = `@tanstack/react-virtual`, engaged only when the
 * visible event list reaches `VIRTUALIZE_THRESHOLD`. Below that, plain
 * mapping is faster (no measurement passes).
 *
 * "Load older" expands the visible tail in 200-event steps; the server
 * already returns the full content, so this is a client-side window only.
 */

import { useMemo, useRef, useState, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

import {
  askUserQuestionSummary,
  assistantText,
  parseSessionJsonl,
  toolResults,
  toolUses,
  userText,
  type ParsedEvent,
} from "../../external/session-parser";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import { MarkdownText } from "./MarkdownText";
import { ToolOutputBlock } from "./ToolOutputBlock";

const DEFAULT_TAIL = 200;
const TAIL_PAGE = 200;
const VIRTUALIZE_THRESHOLD = 200;
const FALLBACK_ROW_PX = 96;

interface Props {
  content: string;
  /** Override the initial tail size (test seam). */
  initialTail?: number;
}

export function BubbleTranscript({ content, initialTail = DEFAULT_TAIL }: Props) {
  const parsed = useMemo(() => parseSessionJsonl(content), [content]);
  const [tail, setTail] = useState<number>(initialTail);

  const allEvents = parsed.events;
  const visible = useMemo(
    () => (allEvents.length > tail ? allEvents.slice(-tail) : allEvents),
    [allEvents, tail],
  );

  // Resolve AskUserQuestion lifecycle: any tool_use with name AskUserQuestion
  // is "pending" until a tool_result with the same tool_use_id appears
  // anywhere later in the stream.
  const resolvedToolUseIds = useMemo(() => {
    const set = new Set<string>();
    for (const e of allEvents) {
      if (e.kind === "user") {
        for (const r of toolResults(e)) set.add(r.tool_use_id);
      }
    }
    return set;
  }, [allEvents]);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const { isAtBottom, scrollToBottom } = useAutoScroll(containerRef, content);

  const showVirtualized = visible.length >= VIRTUALIZE_THRESHOLD;

  if (parsed.events.length === 0) {
    return (
      <div className="py-4 text-sm text-neutral-400" data-testid="transcript-empty">
        No events yet — waiting for JSONL content.
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col" data-testid="bubble-transcript">
      <Toolbar
        total={allEvents.length}
        visible={visible.length}
        canLoadOlder={allEvents.length > tail}
        onLoadOlder={() => setTail((t) => t + TAIL_PAGE)}
      />
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden"
        style={{ overflowAnchor: "auto" }}
        data-testid="transcript-scroll"
      >
        {showVirtualized ? (
          <VirtualBubbles events={visible} resolved={resolvedToolUseIds} containerRef={containerRef} />
        ) : (
          <PlainBubbles events={visible} resolved={resolvedToolUseIds} />
        )}
      </div>
      {!isAtBottom && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-3 right-3 rounded-full bg-neutral-900 px-3 py-1 text-xs text-white shadow-md hover:bg-neutral-700"
          data-testid="jump-to-latest"
        >
          ↓ Jump to latest
        </button>
      )}
      {parsed.malformedLines > 0 && (
        <div className="mt-2 rounded border border-amber-300 bg-amber-50 p-1 text-xs text-amber-900">
          {parsed.malformedLines} malformed line(s) (likely a torn read on the trailing partial line being written).
        </div>
      )}
    </div>
  );
}

function Toolbar({
  total,
  visible,
  canLoadOlder,
  onLoadOlder,
}: {
  total: number;
  visible: number;
  canLoadOlder: boolean;
  onLoadOlder: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-b border-neutral-200 bg-white px-2 py-1 text-xs text-neutral-500">
      <span data-testid="transcript-event-count">
        Showing {visible} of {total} events
      </span>
      {canLoadOlder && (
        <button
          type="button"
          onClick={onLoadOlder}
          className="rounded border border-neutral-300 bg-white px-2 py-0.5 hover:bg-neutral-50"
          data-testid="load-older-btn"
        >
          ↑ Load older
        </button>
      )}
    </div>
  );
}

function PlainBubbles({
  events,
  resolved,
}: {
  events: ParsedEvent[];
  resolved: Set<string>;
}) {
  return (
    <div className="flex flex-col gap-2 p-3" data-testid="bubble-list-plain">
      {events.map((e, i) => (
        <BubbleRow
          key={`${i}-${e.uuid ?? i}`}
          event={e}
          previous={i > 0 ? events[i - 1] : null}
          resolved={resolved}
        />
      ))}
    </div>
  );
}

function VirtualBubbles({
  events,
  resolved,
  containerRef,
}: {
  events: ParsedEvent[];
  resolved: Set<string>;
  containerRef: React.RefObject<HTMLDivElement | null>;
}) {
  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => FALLBACK_ROW_PX,
    overscan: 8,
  });
  return (
    <div
      style={{ height: virtualizer.getTotalSize(), position: "relative", padding: "12px" }}
      data-testid="bubble-list-virtual"
    >
      {virtualizer.getVirtualItems().map((vi) => {
        const event = events[vi.index];
        const previous = vi.index > 0 ? events[vi.index - 1] : null;
        return (
          <div
            key={vi.key}
            ref={virtualizer.measureElement}
            data-index={vi.index}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              transform: `translateY(${vi.start}px)`,
              padding: "4px 0",
            }}
          >
            <BubbleRow event={event} previous={previous} resolved={resolved} />
          </div>
        );
      })}
    </div>
  );
}

function BubbleRow({
  event,
  previous,
  resolved,
}: {
  event: ParsedEvent;
  previous: ParsedEvent | null;
  resolved: Set<string>;
}) {
  const turnSeparator = isTurnBoundary(previous, event);
  return (
    <div className="flex flex-col gap-2">
      {turnSeparator && <hr className="my-2 border-t border-neutral-200" data-testid="turn-separator" />}
      {renderBubble(event, resolved)}
    </div>
  );
}

function isTurnBoundary(prev: ParsedEvent | null, current: ParsedEvent): boolean {
  if (!prev) return false;
  if (prev.kind === current.kind) return false;
  // Tool result + tool_use are continuation, not turn boundary.
  const continuationKinds = new Set(["assistant", "user"]);
  if (prev.kind === "user" && current.kind === "assistant") return true;
  if (prev.kind === "assistant" && current.kind === "user" && continuationKinds.has("user")) {
    return false; // tool_result-as-user is a continuation, not a turn flip
  }
  return false;
}

function renderBubble(event: ParsedEvent, resolved: Set<string>): ReactNode {
  if (event.kind === "user") {
    const results = toolResults(event);
    if (results.length > 0) {
      return (
        <div className="flex" data-testid="bubble-tool-result">
          <div className="max-w-[90%] rounded-lg border border-neutral-200 bg-white p-2 shadow-sm">
            <BubbleHeader role="tool_result" timestamp={event.timestamp} />
            {results.map((r) => (
              <ToolOutputBlock key={r.tool_use_id} text={r.content} isError={r.is_error} />
            ))}
          </div>
        </div>
      );
    }
    const t = userText(event);
    return (
      <div className="flex justify-end" data-testid="bubble-user">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-neutral-200 px-3 py-2 text-sm text-neutral-900">
          <BubbleHeader role="user" timestamp={event.timestamp} />
          <div className="whitespace-pre-wrap break-words">
            {t || <em className="text-neutral-500">(empty user message)</em>}
          </div>
        </div>
      </div>
    );
  }

  if (event.kind === "assistant") {
    const text = assistantText(event);
    const tools = toolUses(event);
    return (
      <div className="flex flex-col gap-1" data-testid="bubble-assistant">
        <div className="flex justify-start">
          <div className="max-w-[90%] rounded-2xl rounded-tl-sm bg-blue-50 px-3 py-2 text-sm text-neutral-900">
            <BubbleHeader role="assistant" timestamp={event.timestamp} />
            {text && <MarkdownText text={text} />}
          </div>
        </div>
        {tools.map((tu) => (
          <div className="flex justify-start" key={tu.id}>
            <ToolUseBubble id={tu.id} name={tu.name} input={tu.input} resolved={resolved} />
          </div>
        ))}
      </div>
    );
  }

  if (event.kind === "attachment") {
    return (
      <div className="flex justify-start" data-testid="bubble-attachment">
        <div className="max-w-[60%] rounded border border-neutral-200 bg-neutral-50 px-2 py-1 text-xs text-neutral-600">
          <BubbleHeader role="attachment" timestamp={event.timestamp} />
          attachment
        </div>
      </div>
    );
  }

  if (event.kind === "unknown") {
    return (
      <div className="flex justify-start" data-testid="bubble-unknown">
        <details className="max-w-[80%] rounded border border-amber-300 bg-amber-50 p-2 text-xs">
          <summary className="cursor-pointer">Unknown event: {event.originalType}</summary>
          <pre className="mt-1 overflow-x-auto text-[10px]">{JSON.stringify(event.raw, null, 2)}</pre>
        </details>
      </div>
    );
  }

  return (
    <div
      className="rounded border border-neutral-200 bg-white p-1 text-[10px] text-neutral-500"
      data-testid={`bubble-${event.kind}`}
    >
      {event.kind}
    </div>
  );
}

function ToolUseBubble({
  id,
  name,
  input,
  resolved,
}: {
  id: string;
  name: string;
  input: unknown;
  resolved: Set<string>;
}) {
  if (name === "AskUserQuestion") {
    const q = askUserQuestionSummary(input);
    const isResolved = resolved.has(id);
    return (
      <div
        className={`max-w-[90%] rounded-lg border-2 p-2 text-xs shadow-sm ${
          isResolved
            ? "border-green-400 bg-green-50 text-green-900"
            : "border-amber-400 bg-amber-50 text-amber-900"
        }`}
        data-testid={isResolved ? "askuser-resolved" : "askuser-pending"}
        data-tool-use-id={id}
      >
        <div className="text-[10px] font-semibold uppercase tracking-wide">
          {isResolved ? "✓ Answered" : "→ Answer in your terminal"}
        </div>
        <div className="mt-1 text-sm font-medium">{q.question}</div>
        {q.options.length > 0 && (
          <ul className="mt-1 list-disc pl-4">
            {q.options.map((o, i) => (
              <li key={i}>{o}</li>
            ))}
          </ul>
        )}
        {q.fallback && (
          <div className="mt-1 italic">
            (Question payload schema differed from expected — open the task in your terminal to see the original.)
          </div>
        )}
      </div>
    );
  }
  return (
    <div
      className="max-w-[90%] rounded-lg border border-neutral-300 bg-white p-2 text-xs shadow-sm"
      data-testid="bubble-tool-use"
      data-tool-use-id={id}
    >
      <span className="font-semibold text-neutral-700">tool_use</span>{" "}
      <span className="font-mono">{name}</span>
    </div>
  );
}

function BubbleHeader({
  role,
  timestamp,
}: {
  role: string;
  timestamp?: string;
}) {
  const fmt = formatTimestamp(timestamp);
  return (
    <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
      <span>{role}</span>
      {fmt && (
        <span className="text-[10px] font-normal normal-case text-neutral-400" title={fmt.iso}>
          {fmt.short}
        </span>
      )}
    </div>
  );
}

function formatTimestamp(iso: string | undefined): { short: string; iso: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return { short: `${hh}:${mm}`, iso };
}
