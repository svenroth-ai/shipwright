/*
 * Chat-style bubble transcript for external-launch tasks.
 *
 * Replaces the flat event-card list from Sub-iterate 1. Each event maps
 * to a "bubble":
 *   - user → right-aligned, warm-beige muted bg (VS Code Claude Code style).
 *   - assistant → left-aligned, surface white with subtle border.
 *   - tool_use → left-aligned card under the assistant bubble (sibling
 *     to tool_result chronologically; correlation deferred to a future
 *     iterate per plan).
 *   - tool_result → left-aligned card with ANSI-stripped content.
 *   - AskUserQuestion → amber pending banner, flips green when a
 *     matching tool_result arrives later in the stream.
 *   - attachment → chip card; consecutive attachments pack inline in
 *     an AttachmentStrip (mockup FR-03.53).
 *   - unknown → neutral details disclosure with warning styling.
 *
 * Auto-scroll = CSS `overflow-anchor: auto` on the scroll container plus
 * a `useAutoScroll` safety net (ADR-035). The hook re-keys on
 * `content.length + visible.length + showSystem` so it fires on JSONL
 * polling ticks, tail expansion (Load older), and system-toggle flips.
 *
 * Virtualization = `@tanstack/react-virtual`, engaged only when the
 * visible event list reaches `VIRTUALIZE_THRESHOLD`. Below that, plain
 * mapping is faster (no measurement passes).
 *
 * "Load older" expands the visible tail in 200-event steps; the server
 * already returns the full content, so this is a client-side window only.
 *
 * Iterate 3.7c-2 UAT fixes (2026-04-21):
 *   - system-toggle now uses functional setState so rapid clicks flip
 *     reliably (FR-03.51 regression).
 *   - auto-scroll dep keys on visible.length so virtualized mode pins
 *     the viewport to the newest bubble after measurement (ADR-035).
 *   - bubble tokens migrated off Tailwind neutral-* / blue-50 onto
 *     CSS variables from index.css (warm-beige palette parity with the
 *     task-detail-3pane mockup).
 *   - attachment chips group into a flex-wrap strip instead of stacking
 *     vertically in separate `msg-turn` rows.
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
function useSystemVisibility(): [boolean, (next: boolean | ((prev: boolean) => boolean)) => void] {
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

  const setVisible = (next: boolean | ((prev: boolean) => boolean)) => {
    setVisibleState((prev) => {
      const resolved = typeof next === "function" ? next(prev) : next;
      try {
        window.localStorage.setItem(SYSTEM_VISIBILITY_KEY, resolved ? "true" : "false");
      } catch {
        // ignore quota/denied — in-memory flip still applies for this session.
      }
      return resolved;
    });
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
  // Re-key on a derived tuple so auto-scroll fires on
  //   (a) new JSONL bytes (polling tick) → content.length grows,
  //   (b) tail expansion via "Load older" → visible.length grows,
  //   (c) system-toggle flip that changes the visible event count.
  // Plain string concatenation keeps the dep serializable.
  const scrollDepKey = `${content.length}:${visible.length}:${showSystem ? 1 : 0}`;
  const { isAtBottom, scrollToBottom } = useAutoScroll(containerRef, scrollDepKey);

  const showVirtualized = visible.length >= VIRTUALIZE_THRESHOLD;

  if (parsed.events.length === 0) {
    return (
      <div
        className="py-4 text-sm"
        style={{ color: "var(--color-muted, #6b7280)" }}
        data-testid="transcript-empty"
      >
        No events yet — waiting for JSONL content.
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col" data-testid="bubble-transcript">
      <Toolbar
        total={filtered.length}
        visible={visible.length}
        canLoadOlder={filtered.length > tail}
        onLoadOlder={() => setTail((t) => t + TAIL_PAGE)}
        showSystem={showSystem}
        onToggleSystem={() => setShowSystem((prev) => !prev)}
      />
      <div
        ref={containerRef}
        className="scroll-themed flex-1 overflow-y-auto overflow-x-hidden"
        style={{
          overflowAnchor: "auto",
          scrollPaddingBottom: "40px",
          background: "var(--color-bg, #f5f0eb)",
        }}
        data-testid="transcript-scroll"
      >
        {showVirtualized ? (
          <VirtualBubbles
            events={visible}
            resolved={resolvedToolUseIds}
            containerRef={containerRef}
          />
        ) : (
          <PlainBubbles events={visible} resolved={resolvedToolUseIds} />
        )}
      </div>
      {!isAtBottom && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-3 right-3 rounded-full px-3 py-1 text-xs font-medium shadow-md transition-colors"
          style={{
            background: "var(--color-primary, #6b5e56)",
            color: "#fff",
            boxShadow: "var(--shadow-sm, 0 2px 8px rgba(0,0,0,0.06))",
          }}
          data-testid="jump-to-latest"
        >
          ↓ Jump to latest
        </button>
      )}
      {parsed.malformedLines > 0 && (
        <div
          className="mx-3 mb-2 rounded p-1 text-xs"
          style={{
            border: "1px solid var(--color-warning, #D97706)",
            background: "var(--color-warning-bg, #FEF3C7)",
            color: "var(--color-warning-text, #92400E)",
          }}
        >
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
      className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs"
      style={{
        borderBottom: "1px solid var(--color-border, #e0dbd4)",
        background: "var(--color-surface, #ffffff)",
        color: "var(--color-muted, #6b7280)",
      }}
    >
      <span data-testid="transcript-event-count">
        Showing {visible} of {total} events
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleSystem}
          aria-pressed={showSystem}
          className="px-2.5 py-0.5 text-[11px] font-medium transition-colors"
          style={{
            border: "1px solid var(--color-border, #e0dbd4)",
            borderRadius: "12px",
            background: showSystem
              ? "var(--color-primary, #6b5e56)"
              : "var(--color-surface, #ffffff)",
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
            className="px-2.5 py-0.5 text-[11px] font-medium transition-colors"
            style={{
              border: "1px solid var(--color-border, #e0dbd4)",
              borderRadius: "12px",
              background: "var(--color-surface, #ffffff)",
              color: "var(--color-muted, #6b7280)",
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

type BubbleGroup =
  | { kind: "single"; event: ParsedEvent; baseIndex: number }
  | { kind: "attachments"; events: ParsedEvent[]; baseIndex: number };

function groupConsecutiveAttachments(events: ParsedEvent[]): BubbleGroup[] {
  const out: BubbleGroup[] = [];
  let i = 0;
  while (i < events.length) {
    const e = events[i];
    if (e.kind === "attachment") {
      const start = i;
      const bucket: ParsedEvent[] = [];
      while (i < events.length && events[i].kind === "attachment") {
        bucket.push(events[i]);
        i += 1;
      }
      out.push({ kind: "attachments", events: bucket, baseIndex: start });
    } else {
      out.push({ kind: "single", event: e, baseIndex: i });
      i += 1;
    }
  }
  return out;
}

function AttachmentStrip({
  events,
  indexBase,
}: {
  events: ParsedEvent[];
  indexBase: number;
}) {
  return (
    <div
      className="flex flex-wrap items-start justify-start"
      style={{ gap: "8px" }}
      data-testid="bubble-attachment-strip"
    >
      {events.map((e, i) => (
        <div key={`${indexBase}-${i}`} data-testid="bubble-attachment">
          {renderAttachmentCard(e)}
        </div>
      ))}
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
  // Pack consecutive attachments into a single flex-wrap row so chips
  // render side-by-side (mockup FR-03.53 visual grouping).
  const groups = useMemo(() => groupConsecutiveAttachments(events), [events]);

  return (
    <div
      className="flex flex-col"
      style={{ gap: "14px", padding: "20px 22px 80px" }}
      data-testid="bubble-list-plain"
    >
      {groups.map((group, gi) => {
        if (group.kind === "attachments") {
          return (
            <AttachmentStrip
              key={`att-${gi}`}
              events={group.events}
              indexBase={group.baseIndex}
            />
          );
        }
        const e = group.event;
        const i = group.baseIndex;
        const previous = i > 0 ? events[i - 1] : null;
        return (
          <BubbleRow
            key={`${i}-${e.uuid ?? i}`}
            event={e}
            previous={previous}
            resolved={resolved}
          />
        );
      })}
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
      style={{
        height: virtualizer.getTotalSize(),
        position: "relative",
        padding: "20px 22px 80px",
      }}
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
              padding: "7px 0",
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
    <div className="flex flex-col" style={{ gap: "10px" }}>
      {turnSeparator && (
        <hr
          className="my-2"
          style={{ borderTop: "1px solid var(--color-border, #e0dbd4)" }}
          data-testid="turn-separator"
        />
      )}
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
        <div className="flex justify-start" data-testid="bubble-tool-result">
          <div
            className="max-w-[90%] p-2"
            style={{
              background: "var(--color-surface, #ffffff)",
              border: "1px solid var(--color-border, #e0dbd4)",
              borderRadius: "var(--radius-button, 8px)",
              boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
            }}
          >
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
        <div
          className="max-w-[80%] px-3 py-2 text-sm"
          style={{
            background: "var(--color-muted-bg, #ede8e1)",
            color: "var(--color-text, #1a1a1a)",
            border: "1px solid var(--color-border, #e0dbd4)",
            borderRadius: "14px",
            borderTopRightRadius: "4px",
          }}
        >
          <BubbleHeader role="user" timestamp={event.timestamp} />
          <div className="whitespace-pre-wrap break-words">
            {t || (
              <em style={{ color: "var(--color-muted, #6b7280)" }}>(empty user message)</em>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (event.kind === "assistant") {
    const text = assistantText(event);
    const tools = toolUses(event);
    return (
      <div className="flex flex-col gap-1.5" data-testid="bubble-assistant">
        <div className="flex justify-start">
          <div
            className="max-w-[90%] px-3 py-2 text-sm"
            style={{
              background: "var(--color-surface, #ffffff)",
              color: "var(--color-text, #1a1a1a)",
              border: "1px solid var(--color-border, #e0dbd4)",
              borderRadius: "14px",
              borderTopLeftRadius: "4px",
              boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
            }}
          >
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
        {renderAttachmentCard(event)}
      </div>
    );
  }

  if (event.kind === "system") {
    return (
      <div className="flex justify-center" data-testid="bubble-system">
        <span
          className="inline-flex max-w-[95%] items-center gap-1.5 truncate px-2.5 py-1 text-[11px]"
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
      <div className="flex justify-center" data-testid="bubble-custom-title">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate px-2.5 py-1 text-[11px]"
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
      <div className="flex justify-center" data-testid="bubble-agent-name">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate px-2.5 py-1 text-[11px]"
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
      <div className="flex justify-center" data-testid="bubble-permission-mode">
        <span
          className="inline-flex max-w-full items-center gap-1 truncate px-2.5 py-1 text-[11px]"
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
        <details
          className="max-w-[80%] p-2 text-xs"
          style={{
            border: "1px solid var(--color-warning, #D97706)",
            background: "var(--color-warning-bg, #FEF3C7)",
            color: "var(--color-warning-text, #92400E)",
            borderRadius: "var(--radius-button, 8px)",
          }}
        >
          <summary className="cursor-pointer">Unknown event: {event.originalType}</summary>
          <pre className="mt-1 overflow-x-auto text-[10px]">{JSON.stringify(event.raw, null, 2)}</pre>
        </details>
      </div>
    );
  }

  return (
    <div
      className="p-1 text-[10px]"
      style={{
        border: "1px solid var(--color-border, #e0dbd4)",
        background: "var(--color-surface, #ffffff)",
        color: "var(--color-muted, #6b7280)",
        borderRadius: "var(--radius-button, 8px)",
      }}
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
        className="max-w-[90%] p-3 text-xs"
        style={{
          background: "var(--color-surface, #ffffff)",
          border: "1px solid var(--color-border, #e0dbd4)",
          borderLeft: `3px solid ${
            isResolved
              ? "var(--color-success, #059669)"
              : "var(--color-warning, #D97706)"
          }`,
          borderRadius: "var(--radius-button, 8px)",
          boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
          color: "var(--color-text, #1a1a1a)",
        }}
        data-testid={isResolved ? "askuser-resolved" : "askuser-pending"}
        data-tool-use-id={id}
      >
        <div
          className="text-[10px] font-semibold uppercase tracking-wide"
          style={{
            color: isResolved
              ? "var(--color-success, #059669)"
              : "var(--color-warning, #D97706)",
          }}
        >
          {isResolved ? "✓ Answered" : "→ Answer in your terminal"}
        </div>
        <div className="mt-1.5 text-sm font-medium">{q.question}</div>
        {q.options.length > 0 && (
          <ul className="mt-1.5 list-disc pl-4">
            {q.options.map((o, i) => (
              <li key={i}>{o}</li>
            ))}
          </ul>
        )}
        {q.fallback && (
          <div className="mt-1 italic" style={{ color: "var(--color-muted, #6b7280)" }}>
            (Question payload schema differed from expected — open the task in your terminal to see the original.)
          </div>
        )}
      </div>
    );
  }
  return (
    <div
      className="max-w-[90%] p-2 text-xs"
      style={{
        background: "var(--color-surface, #ffffff)",
        border: "1px solid var(--color-border, #e0dbd4)",
        borderRadius: "var(--radius-button, 8px)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      }}
      data-testid="bubble-tool-use"
      data-tool-use-id={id}
    >
      <span
        className="font-semibold"
        style={{ color: "var(--color-text, #1a1a1a)" }}
      >
        tool_use
      </span>{" "}
      <span
        className="font-mono"
        style={{ color: "var(--color-primary, #6b5e56)" }}
      >
        {name}
      </span>
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
    <div
      className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide"
      style={{ color: "var(--color-muted, #6b7280)" }}
    >
      <span>{role}</span>
      {fmt && (
        <span
          className="text-[10px] font-normal normal-case"
          style={{ color: "var(--color-muted, #6b7280)", opacity: 0.75 }}
          title={fmt.iso}
          data-testid="bubble-timestamp"
        >
          {fmt.short}
        </span>
      )}
    </div>
  );
}

/**
 * Standalone attachment card render — reusable between the single-event
 * bubble flow and the AttachmentStrip that packs consecutive attachments
 * inline (mockup FR-03.53).
 */
function renderAttachmentCard(event: ParsedEvent): ReactNode {
  if (event.kind !== "attachment") return null;
  const payload = event.attachment;
  const filename = readStringField(payload, "filename") ?? readStringField(payload, "name");
  const thumbnailUrl =
    readStringField(payload, "thumbnailUrl") ?? readStringField(payload, "thumbnail_url");
  if (filename) {
    return (
      <div
        className="flex items-center gap-2 text-xs"
        style={{
          maxWidth: "320px",
          background: "var(--color-surface, #ffffff)",
          border: "1px solid var(--color-border, #e0dbd4)",
          borderRadius: "var(--radius-button, 8px)",
          padding: "8px 12px",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}
      >
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt=""
            className="flex-shrink-0 object-cover"
            style={{ width: "36px", height: "36px", borderRadius: "6px" }}
          />
        ) : (
          <div
            className="flex flex-shrink-0 items-center justify-center"
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "6px",
              background: "var(--color-muted-bg, #ede8e1)",
              color: "var(--color-primary, #6b5e56)",
              fontSize: "10px",
              fontWeight: 700,
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
            style={{ color: "var(--color-text, #1a1a1a)", fontSize: "12.5px" }}
          >
            {filename}
          </div>
          <div style={{ color: "var(--color-muted, #6b7280)", fontSize: "11px" }}>
            attachment
          </div>
        </div>
      </div>
    );
  }
  return (
    <div
      className="px-2 py-1 text-xs"
      style={{
        background: "var(--color-surface, #ffffff)",
        border: "1px solid var(--color-border, #e0dbd4)",
        borderRadius: "var(--radius-button, 8px)",
        color: "var(--color-muted, #6b7280)",
      }}
    >
      attachment
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
