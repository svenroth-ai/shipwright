/*
 * TextRenderer — minimal whitespace-preserving viewer for plain text /
 * log / csv / txt files (iterate 3 section 04). Line numbers via CSS
 * counter so no JS splits + joins per render.
 */

interface Props {
  text: string;
  "data-testid"?: string;
}

export function TextRenderer({ text, ...rest }: Props) {
  const testId = rest["data-testid"] ?? "smart-viewer-text";
  return (
    <pre
      className="smart-viewer-text whitespace-pre overflow-auto p-4 text-[12px] leading-[1.55]"
      style={{
        fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace)",
        background: "var(--color-surface, #ffffff)",
        color: "var(--color-text, #1a1a1a)",
        counterReset: "ln",
      }}
      data-testid={testId}
    >
      {text.split("\n").map((line, i) => (
        <span
          key={i}
          className="grid"
          style={{ gridTemplateColumns: "3.5ch 1fr", columnGap: "14px" }}
        >
          <span
            aria-hidden="true"
            className="select-none text-right opacity-50"
            style={{ color: "var(--color-muted, #6b7280)" }}
          >
            {i + 1}
          </span>
          <span>{line || " "}</span>
        </span>
      ))}
    </pre>
  );
}
