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

import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { MessageSquare, Terminal as TerminalIcon } from "lucide-react";

import {
  askUserQuestionSummary,
  assistantText,
  fileSnapshotBasenames,
  hasVisibleBubbleContent,
  isOnlyToolResults,
  isThinkingOnly,
  parseSessionJsonl,
  toolResults,
  toolUses,
  userText,
  type ParsedEvent,
} from "../../external/session-parser";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import { useLaunchTask } from "../../hooks/useLaunchTask";
import { AttachmentCard } from "./AttachmentCard";
import { MarkdownText } from "./MarkdownText";
import { SkillChip } from "./SkillChip";
import { SlashCommandChip } from "./SlashCommandChip";
import { ToolCard } from "./ToolCard";
import { ToolOutputBlock } from "./ToolOutputBlock";
import type { CopyCommandForms, ExternalTask } from "../../lib/externalApi";

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
  /**
   * Optional task used by the in-bubble Resume button on AskUserQuestion
   * tool_use bubbles (3.7d-b2). When omitted, no Resume button renders —
   * keeps unit tests that only stub `content` working unchanged.
   */
  task?: ExternalTask;
}

export function BubbleTranscript({ content, initialTail = DEFAULT_TAIL, task }: Props) {
  const parsed = useMemo(() => parseSessionJsonl(content), [content]);
  const [tail, setTail] = useState<number>(initialTail);
  const [showSystem, setShowSystem] = useSystemVisibility();

  const allEvents = parsed.events;
  // Count system events up-front so the toolbar toggle can report "(N)"
  // instead of being silently inert when the stream has no system bubbles
  // (UAT 3.7d — Sven clicked the toggle on seeded tasks that had zero
  // system events and concluded the button was broken; the toggle is
  // actually working, there's just nothing to reveal). Also used by the
  // toolbar to disable the button when N == 0.
  const systemCount = useMemo(
    () => allEvents.reduce((n, e) => (e.kind === "system" ? n + 1 : n), 0),
    [allEvents],
  );
  // 2026-04-23 — iterate-20260423-chat-followups AC-4: file-history-snapshot
  // is redundant with the Edit/Write ToolCards and clutters the transcript.
  // Filter at the data-array level (pre-virtualizer) rather than returning
  // null in renderBubble — a null-return risks zero-height rows for the
  // virtualizer per Gemini's external-review finding.
  const filtered = useMemo(() => {
    return allEvents.filter((e) => {
      if (e.kind === "file-history-snapshot") return false;
      if (!showSystem && e.kind === "system") return false;
      return true;
    });
  }, [allEvents, showSystem]);
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

  // 2026-04-23 — iterate-20260423-chat-followups AC-1. Map every
  // tool_result in the FULL filtered scope (NOT the narrower `visible`
  // slice — per Gemini external-review, scoping to the visible window
  // would drop the output whenever the tool_use stays rendered but the
  // tool_result scrolls out of the tail). Duplicate-id handling:
  // last-write-wins, with one refinement — a successful (non-error)
  // result overwrites a prior error result so retries surface the good
  // outcome instead of the stale failure. Still O(n) over filtered.
  const toolResultsById = useMemo(() => {
    const map = new Map<string, { content: string; is_error: boolean }>();
    for (const e of filtered) {
      if (e.kind !== "user") continue;
      for (const r of toolResults(e)) {
        const prior = map.get(r.tool_use_id);
        // Replace unless doing so would downgrade a prior success to an
        // error (retries must surface the successful outcome, not the
        // stale failure).
        const wouldDowngrade = prior && !prior.is_error && r.is_error;
        if (!wouldDowngrade) {
          map.set(r.tool_use_id, { content: r.content, is_error: r.is_error });
        }
      }
    }
    return map;
  }, [filtered]);

  // ids of every tool_use block whose parent assistant event sits in the
  // currently VISIBLE tail slice. Used exclusively as the suppression
  // predicate for the tool_result bubble — orphans (matching tool_use
  // scrolled out) still render their bubble so data is never dropped.
  const visibleToolUseIds = useMemo(() => {
    const set = new Set<string>();
    for (const e of visible) {
      if (e.kind !== "assistant") continue;
      for (const tu of toolUses(e)) set.add(tu.id);
    }
    return set;
  }, [visible]);

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
    // 3.7d-b2 — centered empty state with Lucide icon + heading + hint.
    // The parent pane provides the flex container; we fill it and center.
    return (
      <div
        className="flex h-full min-h-[240px] w-full flex-col items-center justify-center gap-3 p-8 text-center"
        data-testid="transcript-empty"
      >
        <MessageSquare
          size={48}
          aria-hidden="true"
          style={{ color: "var(--color-muted, #6b7280)" }}
        />
        <div
          className="text-[16px] font-semibold"
          style={{ color: "var(--color-text, #1a1a1a)" }}
          data-testid="transcript-empty-heading"
        >
          No events yet
        </div>
        <div
          className="max-w-[320px] text-[13px]"
          style={{ color: "var(--color-muted, #6b7280)" }}
        >
          Launch the task to start streaming the assistant transcript here.
        </div>
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
        systemCount={systemCount}
        onToggleSystem={() => setShowSystem((prev) => !prev)}
      />
      <div
        ref={containerRef}
        className="scroll-themed flex-1 overflow-y-auto overflow-x-hidden"
        style={{
          overflowAnchor: "auto",
          scrollPaddingBottom: "40px",
          background: "var(--color-bg, #f5f0eb)",
          // 2026-04-23 — AC-6: root font-size 13px (matches mockup
          // `body { font-size: 13px }`). Nested elements like code/pre,
          // chips, tool-card titles/body set their own sizes explicitly
          // so the cascade doesn't leak unintended sizing. Line-height
          // 1.6 matches mockup .msg-content.
          fontSize: "13px",
          lineHeight: 1.6,
        }}
        data-testid="transcript-scroll"
      >
        {showVirtualized ? (
          <VirtualBubbles
            events={visible}
            resolved={resolvedToolUseIds}
            toolResultsById={toolResultsById}
            visibleToolUseIds={visibleToolUseIds}
            containerRef={containerRef}
            task={task}
          />
        ) : (
          <PlainBubbles
            events={visible}
            resolved={resolvedToolUseIds}
            toolResultsById={toolResultsById}
            visibleToolUseIds={visibleToolUseIds}
            task={task}
          />
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
  systemCount,
  onToggleSystem,
}: {
  total: number;
  visible: number;
  canLoadOlder: boolean;
  onLoadOlder: () => void;
  showSystem: boolean;
  /** Count of system events available to reveal (may be 0). */
  systemCount: number;
  onToggleSystem: () => void;
}) {
  // 3.7d-b2 — if the stream has zero system events, disable the toggle and
  // show a neutral label so it isn't mistaken for a broken button.
  const hasSystem = systemCount > 0;
  const toggleLabel = !hasSystem
    ? "No system messages"
    : showSystem
    ? `Hide system messages (${systemCount})`
    : `Show system messages (${systemCount})`;
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
          disabled={!hasSystem}
          className="px-2.5 py-0.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60"
          style={{
            border: "1px solid var(--color-border, #e0dbd4)",
            borderRadius: "12px",
            background: showSystem
              ? "var(--color-primary, #6b5e56)"
              : "var(--color-surface, #ffffff)",
            color: showSystem ? "#fff" : "var(--color-muted, #6b7280)",
          }}
          data-testid="system-toggle"
          data-system-count={systemCount}
          title={!hasSystem ? "This task has no system events" : undefined}
        >
          {toggleLabel}
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
  toolResultsById,
  visibleToolUseIds,
  task,
}: {
  events: ParsedEvent[];
  resolved: Set<string>;
  toolResultsById: Map<string, { content: string; is_error: boolean }>;
  visibleToolUseIds: Set<string>;
  task?: ExternalTask;
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
            toolResultsById={toolResultsById}
            visibleToolUseIds={visibleToolUseIds}
            task={task}
          />
        );
      })}
    </div>
  );
}

function VirtualBubbles({
  events,
  resolved,
  toolResultsById,
  visibleToolUseIds,
  containerRef,
  task,
}: {
  events: ParsedEvent[];
  resolved: Set<string>;
  toolResultsById: Map<string, { content: string; is_error: boolean }>;
  visibleToolUseIds: Set<string>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  task?: ExternalTask;
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
            <BubbleRow
              event={event}
              previous={previous}
              resolved={resolved}
              toolResultsById={toolResultsById}
              visibleToolUseIds={visibleToolUseIds}
              task={task}
            />
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
  toolResultsById,
  visibleToolUseIds,
  task,
}: {
  event: ParsedEvent;
  previous: ParsedEvent | null;
  resolved: Set<string>;
  toolResultsById: Map<string, { content: string; is_error: boolean }>;
  visibleToolUseIds: Set<string>;
  task?: ExternalTask;
}) {
  const turnSeparator = isTurnBoundary(previous, event);
  const bubble = renderBubble(event, resolved, toolResultsById, visibleToolUseIds, task);
  // 2026-04-23 — AC-1: renderBubble may now return null for tool_result-
  // only user events whose ids are all folded into ToolCards. Skip the
  // wrapper entirely so we don't leave an empty flex row — AND skip the
  // turn separator too, since a separator without a bubble beneath it
  // is an orphan visual artefact.
  if (bubble == null) return null;
  return (
    <div className="flex flex-col" style={{ gap: "10px" }}>
      {turnSeparator && (
        <hr
          className="my-2"
          style={{ borderTop: "1px solid var(--color-border, #e0dbd4)" }}
          data-testid="turn-separator"
        />
      )}
      {bubble}
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

function renderBubble(
  event: ParsedEvent,
  resolved: Set<string>,
  toolResultsById: Map<string, { content: string; is_error: boolean }>,
  visibleToolUseIds: Set<string>,
  task?: ExternalTask,
): ReactNode {
  if (event.kind === "user") {
    const results = toolResults(event);
    if (results.length > 0) {
      // 2026-04-23 — iterate-20260423-chat-followups AC-1 suppression.
      // All three must hold to suppress: (1) event content is strictly an
      // array of tool_result blocks (no text, no mix); (2) every block's
      // tool_use_id has a matching tool_use in the visible window so a
      // ToolCard will display the output. Orphans and mixed-content
      // events continue to render the existing bubble so data is never
      // silently dropped.
      const isOnly = isOnlyToolResults(event);
      const allFolded =
        isOnly && results.every((r) => visibleToolUseIds.has(r.tool_use_id));
      if (allFolded) return null;
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
            // Darker than --color-muted-bg (too light per UAT 3.7d).
            // --color-border (#e0dbd4) is the next-darker existing token;
            // gives readable contrast without inventing a new token.
            background: "var(--color-border, #e0dbd4)",
            color: "var(--color-text, #1a1a1a)",
            // R5 (iterate 3.7e-a): no border. Subtle shadow matching the
            // assistant bubble below (see `boxShadow: 0 1px 3px rgba(0,0,0,0.04)`
            // on the assistant branch). Gives both bubbles consistent
            // visual weight without the heavy accent border from 3.7d-a.
            border: "none",
            borderRadius: "14px",
            borderTopRightRadius: "4px",
            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
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
    // 2026-04-23 — AC-5: suppress empty assistant bubbles for COMPLETED
    // turns (caller passes the completed event through this path). An
    // empty bubble = no visible text AND no tool_use blocks. Tool cards
    // render as siblings outside the bubble, so a tool-only assistant
    // turn still shows its tools without the empty speech bubble above.
    // During active streaming, assistant events still arrive with empty
    // content initially; that path is handled by useStreamingChat which
    // injects a "typing" indicator upstream — we don't need to render
    // an empty bubble here.
    const bubbleHasContent = hasVisibleBubbleContent(event);
    const thinkingOnly = isThinkingOnly(event);
    return (
      <div className="flex flex-col gap-1.5" data-testid="bubble-assistant">
        {bubbleHasContent && (
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
              {/* R4 (iterate 3.7e-a): role label reads "CLAUDE" instead of
                  "ASSISTANT". The uppercase CSS styling is unchanged. The
                  `data-testid="bubble-assistant"` on the outer wrapper is
                  load-bearing — renaming to `bubble-claude` would break
                  ~5 existing tests. The internal `role=` prop is the only
                  user-visible string that flips. */}
              <BubbleHeader role="claude" timestamp={event.timestamp} />
              {text && <MarkdownText text={text} />}
            </div>
          </div>
        )}
        {!bubbleHasContent && thinkingOnly && (
          <div className="flex justify-start" data-testid="thinking-card">
            <div
              className="max-w-[90%] px-3 py-2 text-[12px] italic"
              style={{
                color: "var(--color-muted, #6b7280)",
                background: "rgba(107,114,128,0.05)",
                border: "1px dashed var(--color-border, #e0dbd4)",
                borderRadius: "var(--radius-button, 8px)",
              }}
            >
              Thinking…
            </div>
          </div>
        )}
        {tools.map((tu) => (
          <div className="flex justify-start" key={tu.id}>
            <ToolUseBubble
              id={tu.id}
              name={tu.name}
              input={tu.input}
              resolved={resolved}
              toolResultsById={toolResultsById}
              task={task}
            />
          </div>
        ))}
      </div>
    );
  }

  // 2026-04-23 — AC-3: slash-command invocation → centered grey chip.
  if (event.kind === "slash-command") {
    return <SlashCommandChip commandName={event.commandName} />;
  }

  // 2026-04-23 — iterate-20260423-chat-followups AC-3: skill-loader body
  // collapses to a centered chip. The full manual text is intentionally
  // dropped from the visible transcript — it's injected context, not
  // user-authored content.
  if (event.kind === "skill-body") {
    return <SkillChip skillName={event.skillName} />;
  }

  // 2026-04-23 — AC-4: file-history-snapshot renders as AttachmentCard
  // with basename + `+N more` suffix when multiple files are tracked.
  if (event.kind === "file-history-snapshot") {
    const names = fileSnapshotBasenames(event);
    if (names.length === 0) return null; // silent suppression (no speculative "no files" chip)
    const [first, ...rest] = names;
    return (
      <div className="flex justify-start" data-testid="bubble-file-snapshot">
        <AttachmentCard basename={first} extraCount={rest.length} />
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
  toolResultsById,
  task,
}: {
  id: string;
  name: string;
  input: unknown;
  resolved: Set<string>;
  toolResultsById: Map<string, { content: string; is_error: boolean }>;
  task?: ExternalTask;
}) {
  if (name === "AskUserQuestion") {
    const q = askUserQuestionSummary(input);
    const isResolved = resolved.has(id);
    // 3.7d-b2 — ask-bubble polish:
    //   - Options rendered as readable chips (13 px) instead of tiny bullets.
    //   - Unresolved asks get a compact Resume button bottom-right so the
    //     user can jump from bubble → terminal without scrolling up to the
    //     header. Resolved asks don't need the button (answer is visible).
    return (
      <div
        className="max-w-[90%] p-3 text-[13px]"
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
        <div className="mt-1.5 text-[14px] font-medium">{q.question}</div>
        {q.options.length > 0 && (
          <ul
            className="mt-2 flex flex-wrap gap-1.5 pl-0"
            style={{ listStyle: "none" }}
            data-testid="askuser-options"
          >
            {q.options.map((o, i) => (
              <li
                key={i}
                data-testid={`askuser-option-${i}`}
                className="inline-flex items-center"
                style={{
                  background: "var(--color-muted-bg, #ede8e1)",
                  border: "1px solid var(--color-border, #e0dbd4)",
                  borderRadius: "999px",
                  color: "var(--color-text, #1a1a1a)",
                  fontSize: "13px",
                  fontWeight: 500,
                  lineHeight: 1.3,
                  padding: "4px 10px",
                }}
              >
                {o}
              </li>
            ))}
          </ul>
        )}
        {q.fallback && (
          <div
            className="mt-1 italic text-[12px]"
            style={{ color: "var(--color-muted, #6b7280)" }}
          >
            (Question payload schema differed from expected — open the task in your terminal to see the original.)
          </div>
        )}
        {!isResolved && task && (
          <div
            className="mt-2.5 flex justify-end"
            data-testid="askuser-resume-row"
          >
            {/* R6 (iterate 3.7e-a): label reads "Answer in Terminal" (was
                "Resume" in 3.7d-b2). Brown solid with Terminal icon LEFT
                of the label, consistent with R3. Click still copies the
                resume command to the clipboard — no behavior change, only
                the label + rendering switches from the compact variant
                to an inline button. The testid stays `askuser-resume-row`
                on the wrapper for back-compat. */}
            <AnswerInTerminalButton task={task} />
          </div>
        )}
      </div>
    );
  }
  // 2026-04-23 — AC-1/AC-2: render non-AskUser tool_use blocks as a
  // ToolCard (collapsed by default, click to expand input). The outer
  // flex wrapper keeps data-testid="bubble-tool-use" + data-tool-use-id
  // for back-compat with existing tests.
  //
  // 2026-04-23 — iterate-20260423-chat-followups AC-1: when a matching
  // tool_result exists in `toolResultsById`, pass it to the card so the
  // expanded body shows input AND output. The separate tool_result
  // bubble is suppressed upstream (see renderBubble user branch).
  const result = toolResultsById.get(id);
  return (
    <div
      className="max-w-[90%] w-full"
      data-testid="bubble-tool-use"
      data-tool-use-id={id}
    >
      <ToolCard id={id} name={name} input={input} result={result} />
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
 *
 * 2026-04-23 — AC-4: only render if we actually have a filename.
 * `attachment` events in the wild sometimes carry Claude Code internal
 * payloads like `deferred_tools_delta` / `skill_listing` with NO
 * filename field — rendering those as an `attachment` card produced the
 * mysterious "attachment" chips the user reported. When no filename is
 * resolvable, return null (silent suppression) so the transcript isn't
 * polluted with meaningless chips.
 */
function renderAttachmentCard(event: ParsedEvent): ReactNode {
  if (event.kind !== "attachment") return null;
  const payload = event.attachment;
  const filename = readStringField(payload, "filename") ?? readStringField(payload, "name");
  if (!filename) {
    // 2026-04-23 — AC-4: attachment events without filename are silently
    // suppressed (typically Claude Code internals like deferred_tools_delta
    // or skill_listing that the CLI files under `type: "attachment"`).
    // Dev-mode warn so schema drift surfaces in the next iterate rather
    // than in a future user bug report. Guarded by import.meta.env so
    // production builds stay quiet.
    if (import.meta.env?.DEV && payload && typeof payload === "object") {
      // eslint-disable-next-line no-console
      console.warn(
        "[BubbleTranscript] Dropping attachment event with no filename/name field. Keys:",
        Object.keys(payload as Record<string, unknown>),
      );
    }
    return null;
  }
  return <AttachmentCard basename={basenameOf(filename)} />;
}

function basenameOf(p: string): string {
  const idx = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return idx >= 0 ? p.slice(idx + 1) : p;
}

function readStringField(value: unknown, key: string): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const v = (value as Record<string, unknown>)[key];
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function formatTimestamp(iso: string | undefined): { short: string; iso: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return { short: `${hh}:${mm}`, iso };
}

/**
 * R6 (iterate 3.7e-a) — compact brown-solid button rendered inside the
 * ask-bubble. Label: "Answer in Terminal". Icon: Lucide Terminal, LEFT of
 * label. Click copies the resume command to the clipboard (same path the
 * old compact-variant button used). Does NOT navigate — the user
 * interprets the button as "paste this into your already-open terminal".
 *
 * Retained testid: `askuser-resume-row` lives on the parent wrapper; the
 * button itself gets `askuser-answer-in-terminal` as a distinct testid so
 * b2 Playwright specs can scope the label assertion.
 */
function AnswerInTerminalButton({ task }: { task: ExternalTask }) {
  const launchMut = useLaunchTask();
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const platform: "windows" | "posix" = useMemo(() => {
    if (typeof navigator === "undefined") return "posix";
    return /windows/i.test(navigator.userAgent) ? "windows" : "posix";
  }, []);

  const handleClick = useCallback(
    async (ev: MouseEvent<HTMLButtonElement>) => {
      // Don't let the click bubble to any ancestor click-handler (ask-bubble
      // parent may add one in a later iterate).
      ev.stopPropagation();
      setError(null);
      try {
        const result = await launchMut.mutateAsync({
          taskId: task.taskId,
          resume: true,
        });
        const command = pickBubbleCommand(result.commands, platform);
        await writeBubbleClipboard(command);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [launchMut, task.taskId, platform],
  );

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={(ev) => void handleClick(ev)}
        disabled={launchMut.isPending}
        className={
          "inline-flex items-center justify-center gap-1.5 " +
          "font-semibold text-white transition-colors " +
          "disabled:cursor-not-allowed disabled:opacity-60 " +
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1"
        }
        style={{
          borderRadius: "var(--radius-button, 8px)",
          background: "var(--color-primary, #6b5e56)",
          padding: "5px 12px",
          fontSize: "12px",
          fontWeight: 600,
        }}
        onMouseEnter={(ev) => {
          ev.currentTarget.style.background =
            "var(--color-primary-hover, #5a4f48)";
        }}
        onMouseLeave={(ev) => {
          ev.currentTarget.style.background = "var(--color-primary, #6b5e56)";
        }}
        title={copied ? "Copied!" : "Copy resume command"}
        aria-label="Answer — copy resume command to clipboard"
        data-testid="askuser-answer-in-terminal"
      >
        <TerminalIcon size={13} />
        <span className="leading-none">
          {copied ? "Copied" : "Answer"}
        </span>
      </button>
      {error && (
        <span
          role="alert"
          className="text-[11px]"
          style={{ color: "var(--color-error, #DC2626)" }}
        >
          {error}
        </span>
      )}
    </div>
  );
}

function pickBubbleCommand(
  commands: CopyCommandForms,
  platform: "windows" | "posix",
): string {
  return platform === "windows" ? commands.powershell : commands.posix;
}

async function writeBubbleClipboard(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
  } finally {
    document.body.removeChild(ta);
  }
}
