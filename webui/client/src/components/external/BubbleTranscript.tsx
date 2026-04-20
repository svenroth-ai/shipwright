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

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
const SYSTEM_VISIBILITY_KEY = "webui.transcript.showSystem";

/**
 * Global toggle state for "system" event visibility. Persists to
 * localStorage so the preference survives reloads and applies across
 * every transcript viewer in the app (single default — not per-task,
 * per plan § 3 section 01 + external review O16).
 */
function useSystemVisibility(): [boolean, (next: boolean) => void] {
  const [visible, setVisibleState] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(SYSTEM_VISIBILITY_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    // Cross-tab sync: if another tab flips the flag, reflect it here.
    const onStorage = (ev: StorageEvent) => {
      if (ev.key === SYSTEM_VISIBILITY_KEY) {
        setVisibleState(ev.newValue === "true");
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setVisible = (next: boolean) => {
    try {
      window.localStorage.setItem(SYSTEM_VISIBILITY_KEY, next ? "true" : "false");
    } catch {
      // ignore quota/denied — in-memory flip still applies for this session.
    }
    setVisibleState(next);
  };

  return [visible, setVisible];
}

interface Props {
  content: string;
  /** Override the initial tail size (test seam). */
  initialTail?: number;
}

export function BubbleTranscript({ content, initialTail = DEFAULT_TAIL }: Props) {
  const parsed = useMemo(() => parseSessionJsonl(content), [content]);
  const [tail, setTail] = useState<number>(initialTail);
  const [showSystem, setShowSystem] = useSystemVisibility();

  const allEvents = parsed.events;
  const filtered = useMemo(
    () => (showSystem ? allEvents : allEvents.filter((e) => e.kind !== "system")),
    [allEvents, showSystem],
  );
  const visible = useMemo(
    () => (filtered.length > tail ? filtered.slice(-tail) : filtered),
    [filtered, tail],
  );

  // Resolve AskUserQuestion lifecycle: any tool_use with name AskUserQuestion
  // is "pending" until a tool_result with the same tool_use_id appears
  // anywhere later in the stream.
  const resolvedToolUseIds = useMemo(() => {
    const set = new Set<string>();
    for (const e of filtered) {
      if (e.kind === "user") {
        for (const r of toolResults(e)) set.add(r.tool_use_id);
      }
    }
    return set;
  }, [filtered]);

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
        total={filtered.length}
        visible={visible.length}
        canLoadOlder={filtered.length > tail}
        onLoadOlder={() => setTail((t) => t + TAIL_PAGE)}
        showSystem={showSystem}
        onToggleSystem={() => setShowSystem(!showSystem)}
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
  showSystem,
  onToggleSystem,
}: {
  total: number;
  visible: number;
  canLoadOlder: boolean;
  onLoadOlder: () => void;
  showSystem: boolean;
  onToggleSystem: () => void;
}) {
  return (
    <div
      className="flex items-center justify-between gap-2 border-b bg-white px-2 py-1 text-xs text-neutral-500"
      style={{ borderColor: "var(--color-border)" }}
    >
      <span data-testid="transcript-event-count">
        Showing {visible} of {total} events
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleSystem}
          aria-pressed={showSystem}
          className="px-2 py-0.5 text-xs transition-colors"
          style={{
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-button)",
            background: showSystem ? "var(--color-primary)" : "var(--color-surface)",
            color: showSystem ? "#fff" : "var(--color-muted, #6b7280)",
          }}
          data-testid="system-toggle"
        >
          {showSystem ? "Hide system messages" : "Show system messages"}
        </button>
        {canLoadOlder && (
          <button
            type="button"
            onClick={onLoadOlder}
            className="px-2 py-0.5 hover:bg-neutral-50"
            style={{
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-button)",
              background: "var(--color-surface)",
            }}
            data-testid="load-older-btn"
          >
            ↑ Load older
          </button>
        )}
      </div>
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
    const payload = event.attachment;
    const filename = readStringField(payload, "filename") ?? readStringField(payload, "name");
    const thumbnailUrl =
      readStringField(payload, "thumbnailUrl") ?? readStringField(payload, "thumbnail_url");
    if (filename) {
      return (
        <div className="flex justify-start" data-testid="bubble-attachment">
          <div
            className="flex max-w-[380px] items-center gap-2 px-2 py-1 text-xs"
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-button)",
              boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
            }}
          >
            {thumbnailUrl ? (
              <img
                src={thumbnailUrl}
                alt=""
                className="h-9 w-9 flex-shrink-0 rounded object-cover"
                style={{ borderRadius: "6px" }}
              />
            ) : (
              <div
                className="flex h-9 w-9 flex-shrink-0 items-center justify-center"
                style={{
                  borderRadius: "6px",
                  background: "var(--color-background, #f5f0eb)",
                  color: "var(--color-primary)",
                  fontSize: "10px",
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                  textTransform: "uppercase",
                }}
              >
                {extensionHint(filename)}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div
                className="truncate font-medium"
                style={{ color: "var(--color-text, #1a1a1a)" }}
              >
                {filename}
              </div>
              <div style={{ color: "var(--color-muted, #6b7280)", fontSize: "11px" }}>
                attachment
              </div>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="flex justify-start" data-testid="bubble-attachment">
        <div
          className="max-w-[60%] px-2 py-1 text-xs"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-button)",
            color: "var(--color-muted, #6b7280)",
          }}
        >
          attachment
        </div>
      </div>
    );
  }

  if (event.kind === "system") {
    return (
      <div className="flex justify-start" data-testid="bubble-system">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate px-2 py-0.5 text-[11px]"
          style={{
            fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, monospace)",
            color: "var(--color-muted, #6b7280)",
            background: "rgba(107,114,128,0.10)",
            borderRadius: "10px",
          }}
          title={event.text}
        >
          system · <strong style={{ color: "var(--color-text, #1a1a1a)", fontWeight: 500 }}>
            {event.subtype ?? "meta"}
          </strong>
          {event.text && <span className="ml-1 truncate opacity-80">{event.text}</span>}
        </span>
      </div>
    );
  }

  if (event.kind === "custom-title") {
    return (
      <div className="flex justify-start" data-testid="bubble-custom-title">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate px-2 py-0.5 text-[11px]"
          style={{
            fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, monospace)",
            color: "#1E40AF",
            background: "rgba(59,130,246,0.08)",
            borderRadius: "10px",
            opacity: 0.9,
          }}
        >
          Title set: <strong style={{ color: "#1E40AF", fontWeight: 500 }}>{event.title}</strong>
        </span>
      </div>
    );
  }

  if (event.kind === "agent-name") {
    return (
      <div className="flex justify-start" data-testid="bubble-agent-name">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate px-2 py-0.5 text-[11px]"
          style={{
            fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, monospace)",
            color: "var(--color-accent, #857568)",
            background: "rgba(133,117,104,0.10)",
            borderRadius: "10px",
            opacity: 0.9,
          }}
        >
          Agent:{" "}
          <strong style={{ color: "var(--color-primary, #6b5e56)", fontWeight: 500 }}>
            {event.name}
          </strong>
        </span>
      </div>
    );
  }

  if (event.kind === "permission-mode") {
    return (
      <div className="flex justify-start" data-testid="bubble-permission-mode">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate px-2 py-0.5 text-[11px]"
          style={{
            fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, monospace)",
            color: "#6B21A8",
            background: "rgba(168,85,247,0.10)",
            borderRadius: "10px",
            opacity: 0.9,
          }}
        >
          Permission mode:{" "}
          <strong style={{ color: "#6B21A8", fontWeight: 500 }}>{event.mode}</strong>
        </span>
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

function readStringField(value: unknown, key: string): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const v = (value as Record<string, unknown>)[key];
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function extensionHint(filename: string): string {
  const dot = filename.lastIndexOf(".");
  if (dot === -1 || dot === filename.length - 1) return "FILE";
  return filename.slice(dot + 1, dot + 4).toUpperCase();
}

function formatTimestamp(iso: string | undefined): { short: string; iso: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return { short: `${hh}:${mm}`, iso };
}
