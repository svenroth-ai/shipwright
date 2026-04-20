/*
 * Renders raw tool output (stdout / stderr / structured payload) safely.
 * Strips ANSI escape sequences before display — terminals interpret them
 * for colour, but in HTML they show up as garbage like `[31mERROR[0m`.
 *
 * Uses `strip-ansi` (Sindre Sorhus, ~200 M weekly downloads). One library,
 * one job — kept here as a separate primitive so future iterates can
 * upgrade to a colour-aware renderer (`anser` or `ansi_up`) without
 * touching the bubble layout.
 */

import stripAnsi from "strip-ansi";

interface Props {
  text: string;
  isError?: boolean;
}

export function ToolOutputBlock({ text, isError = false }: Props) {
  const cleaned = stripControl(stripAnsi(text));
  return (
    <pre
      className="max-h-[400px] overflow-auto whitespace-pre-wrap break-words p-2 font-mono text-[11px] leading-snug"
      style={{
        borderRadius: "var(--radius-button)",
        border: isError ? "1px solid #FECACA" : "1px solid var(--color-border)",
        background: isError ? "#FEF2F2" : "var(--color-background, #f5f0eb)",
        color: isError ? "#7F1D1D" : "var(--color-text, #1a1a1a)",
      }}
      data-testid="tool-output-block"
      data-is-error={isError ? "true" : "false"}
    >
      {cleaned}
    </pre>
  );
}

/**
 * Strip control characters (other than tab, newline, CR) that survive
 * `strip-ansi` — e.g. BEL (\u0007), backspace (\u0008), form feed (\u000C).
 * These confuse text rendering and serve no purpose in a transcript.
 */
function stripControl(s: string): string {
  // Allow LF (0x0A), CR (0x0D), TAB (0x09); strip the rest in 0x00–0x1F + 0x7F.
  return s.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
}
