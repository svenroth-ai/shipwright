/*
 * SlashCommandChip — 2026-04-23 iterate-20260423-chat-rendering-polish AC-3.
 *
 * Renders a compact, centered, grey pill for Claude Code slash-command
 * invocations (e.g. `/shipwright-compliance:compliance`). The
 * session-parser detects paired <command-message>+<command-name> tags
 * exclusively in a user-message content (strict match — mixed content
 * falls back to user-bubble) and emits a `slash-command` kind event.
 * This component is the renderer for that kind.
 *
 * The mockup (bubble-states.html) does not yet include a slash-command
 * state — this design is local and documented in the iterate ADR. Visual
 * language borrowed from the mockup's event-chip pattern: grey monospace
 * pill, centered in the transcript flow.
 *
 * Security: `commandName` is rendered as a React text node only, never
 * via dangerouslySetInnerHTML or derived classNames. Even though the
 * parser's regex should only match legitimate Claude Code output, this
 * invariant guards against future parser changes.
 */

interface Props {
  commandName: string;
}

export function SlashCommandChip({ commandName }: Props) {
  return (
    <div
      className="flex justify-center my-2"
      data-testid="slash-command-chip"
    >
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-mono text-[11px]"
        style={{
          background: "rgba(107,114,128,0.10)",
          color: "var(--color-muted, #6b7280)",
        }}
      >
        <span style={{ opacity: 0.6 }}>↳</span>
        <span
          style={{ color: "var(--color-text, #1a1a1a)", fontWeight: 500 }}
          data-testid="slash-command-name"
        >
          {commandName}
        </span>
      </span>
    </div>
  );
}
